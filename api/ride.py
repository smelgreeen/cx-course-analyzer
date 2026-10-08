from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import numpy as np
import pandas as pd

import fit_utils as fu


MAX_RECORDS_RETURNED = 5000
MAX_UPLOAD_BYTES = 4 * 1024 * 1024


def json_safe(value):
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, np.ndarray):
        return json_safe(value.tolist())
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value) if np.isfinite(value) else None
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def local_frame(file_bytes):
    records, _fit_laps = fu.parse_fit(file_bytes)
    lat0 = float(records["lat"].mean())
    lon0 = float(records["lon"].mean())
    return fu.to_local_xy(records, lat0, lon0), (lat0, lon0)


def inspect_ride(file_bytes):
    records, origin = local_frame(file_bytes)
    record_count = len(records)
    indices = np.unique(np.linspace(
        0, record_count - 1, min(record_count, MAX_RECORDS_RETURNED),
        dtype=int,
    ))
    points = records.iloc[indices]
    return {
        "filename_date": pd.Timestamp(records["timestamp"].iloc[0]).date().isoformat(),
        "record_count": record_count,
        "origin": {"lat": origin[0], "lon": origin[1]},
        "points": [
            {
                "index": int(index),
                "lat": float(row.lat),
                "lon": float(row.lon),
                "x": float(row.x),
                "y": float(row.y),
                "seconds": float(row.t),
                "speed_mph": float(row.mph),
            }
            for index, row in zip(indices, points.itertuples())
        ],
    }


def analyze_ride(file_bytes, options):
    records, origin = local_frame(file_bytes)
    start_index = max(0, min(len(records) - 2, int(options.get("trim_start", 0))))
    end_index = max(
        start_index + 2,
        min(len(records), int(options.get("trim_end", len(records) - 1)) + 1),
    )
    trimmed = records.iloc[start_index:end_index].reset_index(drop=True)
    gate = options.get("start_finish")
    if not gate:
        raise ValueError("Choose a start/finish point before analyzing laps.")
    gate_radius = float(options.get("gate_radius_m", 6))
    if not 2 <= gate_radius <= 20:
        raise ValueError("The start/finish detection radius must be 2–20 m.")
    gate_x, gate_y = fu.latlon_to_xy(
        float(gate["lat"]), float(gate["lon"]), *origin,
    )
    passes = fu.find_gate_passes(
        trimmed, gate_x, gate_y,
        radius=gate_radius, min_gap_s=20,
    )
    laps = fu.filter_short_laps(fu.split_laps(trimmed, passes))
    if not laps:
        raise ValueError(
            f"Only found {len(passes)} start/finish crossing(s). "
            "At least two crossings are needed for one complete lap."
        )

    grid, rx, ry, length = fu.build_reference_path(laps)
    profiles = fu.all_profiles(laps, grid, "mph")
    power_profiles = fu.all_profiles(laps, grid, "power")
    feature_intervals = [
        (float(feature["start_m"]), float(feature["end_m"]))
        for feature in options.get("features", [])
    ]
    retention = fu.corner_retention(
        laps, excluded_intervals=feature_intervals, course_length=length,
    )
    lap_summary = fu.lap_summary(laps)
    corner_positions = auto_corner_positions(grid, rx, ry, profiles, length)
    corner_positions = merge_manual_corners(
        grid, length, corner_positions,
        options.get("added_corners", []),
        options.get("removed_corners", []),
        feature_intervals,
    )
    corner_history = {
        "race": [],
        "practice": [],
    }
    metadata = {
        "date": pd.Timestamp(trimmed["timestamp"].iloc[0]).date().isoformat(),
        "ride_file": str(options.get("filename", "Ride")),
    }
    history_type = options.get("history_type")
    if history_type == "race":
        for lap_number, lap in enumerate(laps, start=1):
            corner_history["race"].extend(corner_history_rows(
                lap, corner_positions, grid, rx, ry, length, metadata,
                lap_number, "race lap",
            ))
    elif history_type == "practice":
        rest_threshold_s = max(
            15, min(180, int(options.get("rest_threshold_s", 30))),
        )
        for effort_number, effort in enumerate(
            split_practice_efforts(trimmed, rest_threshold_s), start=1,
        ):
            effort_distance = float(
                effort["distance"].iloc[-1] - effort["distance"].iloc[0]
            )
            effort_type = (
                "practice effort"
                if effort_distance >= length * 0.8 else "partial effort"
            )
            corner_history["practice"].extend(corner_history_rows(
                effort, corner_positions, grid, rx, ry, length, metadata,
                effort_number, effort_type,
            ))

    corner_speeds = []
    for lap_index, profile in enumerate(profiles, start=1):
        row = {"lap": lap_index}
        for corner_number, (corner_index, position) in enumerate(
            corner_positions, start=1,
        ):
            distance = np.minimum(
                np.abs(grid - position), length - np.abs(grid - position),
            )
            speeds = profile[(distance <= 20) & np.isfinite(profile) & (profile > 2)]
            row[f"C{corner_number}"] = (
                float(np.min(speeds)) if len(speeds) else None
            )
        corner_speeds.append(row)

    feature_rows = []
    for feature, (start_m, end_m) in zip(
        options.get("features", []), feature_intervals,
    ):
        feature_name = str(feature.get("name") or "Feature")
        positions = fu.feature_lap_times(laps, start_m, end_m, length)
        power = fu.feature_lap_mean_power(laps, start_m, end_m, length)
        feature_rows.append({
            "name": feature_name,
            "start_m": start_m,
            "end_m": end_m,
            "times_s": positions,
            "mean_time_s": float(np.nanmean(positions)) if positions else None,
            "mean_power_w": float(np.nanmean(power)) if power else None,
        })

    return json_safe({
        "origin": {"lat": origin[0], "lon": origin[1]},
        "date": pd.Timestamp(trimmed["timestamp"].iloc[0]).date().isoformat(),
        "course_length_m": length,
        "route": {
            "distance_m": grid,
            "x": rx,
            "y": ry,
            "speed_mph": np.nanmean(profiles, axis=0),
            "power_w": np.nanmean(power_profiles, axis=0),
        },
        "lap_profiles_mph": profiles,
        "lap_profiles_power_w": power_profiles,
        "lap_summary": lap_summary.to_dict(orient="records"),
        "corner_positions": [
            {"number": number, "index": int(index), "distance_m": float(position)}
            for number, (index, position) in enumerate(corner_positions, start=1)
        ],
        "corner_speeds": corner_speeds,
        "corner_history": corner_history,
        "features": feature_rows,
        "retention": retention,
        "average_speed_mph": float(np.nanmean(profiles)),
        "average_power_w": (
            float(np.nanmean(power_profiles))
            if np.isfinite(power_profiles).any() else None
        ),
        "trimmed_records": len(trimmed),
    })


def auto_corner_positions(grid, rx, ry, profiles, course_length):
    if len(grid) < 5 or not np.isfinite(rx).all() or not np.isfinite(ry).all():
        return []
    mean_speed = np.nanmean(profiles, axis=0)
    step = float(np.median(np.diff(grid)))
    if step <= 0:
        return []
    count = len(grid)
    closing_step = max(0.0, float(course_length - grid[-1]))
    last_step = float(grid[-1] - grid[-2])
    end_x = rx[-1] + (rx[-1] - rx[-2]) * closing_step / last_step
    end_y = ry[-1] + (ry[-1] - ry[-2]) * closing_step / last_step
    blend = min(150.0, course_length / 4)
    ramp = np.clip((grid - (course_length - blend)) / blend, 0, 1)
    source_x = rx - ramp * (end_x - rx[0])
    source_y = ry - ramp * (end_y - ry[0])
    weights = (1, 2, 3, 2, 1)
    x = sum(w * np.roll(source_x, i) for w, i in zip(weights, range(-2, 3))) / 9
    y = sum(w * np.roll(source_y, i) for w, i in zip(weights, range(-2, 3))) / 9
    heading = np.arctan2(np.roll(y, -1) - y, np.roll(x, -1) - x)
    delta = np.arctan2(
        np.sin(heading - np.roll(heading, 1)),
        np.cos(heading - np.roll(heading, 1)),
    )
    absolute_turn = np.abs(np.degrees(delta))
    signal = np.zeros(count)
    for window in sorted({max(3, round(meters / step)) for meters in (30, 50, 70)}):
        window = min(window, count - 1)
        start = -(window // 2)
        signal = np.maximum(
            signal,
            sum(np.roll(absolute_turn, offset) for offset in range(start, start + window)),
        )
    candidates = []
    for i in range(count):
        if not (
            signal[i] >= np.roll(signal, 1)[i]
            and signal[i] >= np.roll(signal, -1)[i]
            and (signal[i] > np.roll(signal, 1)[i] or signal[i] > np.roll(signal, -1)[i])
        ):
            continue
        backward = (grid[i] - grid) % course_length
        forward = (grid - grid[i]) % course_length
        surroundings = signal[
            ((backward >= 80) & (backward <= 140))
            | ((forward >= 80) & (forward <= 140))
        ]
        prominence = signal[i] - np.nanpercentile(surroundings, 25) if surroundings.size else signal[i]
        if signal[i] >= 8 and prominence >= 4:
            candidates.append((i, float(signal[i] + prominence)))

    smooth_speed = (np.roll(mean_speed, 1) + mean_speed + np.roll(mean_speed, -1)) / 3
    for i in range(count):
        if not (
            smooth_speed[i] > 2
            and smooth_speed[i] <= np.roll(smooth_speed, 1)[i]
            and smooth_speed[i] <= np.roll(smooth_speed, -1)[i]
            and (
                smooth_speed[i] < np.roll(smooth_speed, 1)[i]
                or smooth_speed[i] < np.roll(smooth_speed, -1)[i]
            )
        ):
            continue
        backward = (grid[i] - grid) % course_length
        forward = (grid - grid[i]) % course_length
        left = smooth_speed[(backward >= 20) & (backward <= 80)]
        right = smooth_speed[(forward >= 20) & (forward <= 80)]
        if not left.size or not right.size:
            continue
        surrounding = min(float(np.nanmax(left)), float(np.nanmax(right)))
        prominence = surrounding - float(smooth_speed[i])
        if prominence >= max(0.4, surrounding * 0.03):
            candidates.append((i, float(signal[i] + prominence * 5)))

    selected = []
    for index, score in sorted(candidates, key=lambda candidate: candidate[1], reverse=True):
        position = float(grid[index])
        if all(
            min(abs(position - grid[other]), course_length - abs(position - grid[other])) >= 30
            for other in selected
        ):
            selected.append(index)
    return sorted(
        [(index, float(grid[index])) for index in selected],
        key=lambda item: item[1],
    )


def merge_manual_corners(grid, length, detected, added, removed, features):
    def is_excluded(position, interval):
        start, end = interval
        return start <= position <= end if start <= end else position >= start or position <= end

    corners = [
        item for item in detected
        if not any(is_excluded(item[1], interval) for interval in features)
        and all(
            min(abs(item[1] - float(position)), length - abs(item[1] - float(position))) > 20
            for position in removed
        )
    ]
    for position in added:
        position = float(position) % length
        if any(is_excluded(position, interval) for interval in features):
            continue
        if any(
            min(abs(position - existing), length - abs(position - existing)) < 20
            for _, existing in corners
        ):
            continue
        index = int(np.argmin(np.abs(grid - position)))
        corners.append((index, float(grid[index])))
    return sorted(corners, key=lambda item: item[1])


def split_practice_efforts(frame, rest_threshold_s=30):
    speed = pd.to_numeric(frame["mph"], errors="coerce").fillna(0).to_numpy()
    times = pd.to_numeric(frame["t"], errors="coerce").to_numpy(dtype=float)
    x = frame["x"].to_numpy(dtype=float)
    y = frame["y"].to_numpy(dtype=float)
    stopped_indices = np.flatnonzero(speed <= 1.5)
    if not len(stopped_indices):
        return [frame.reset_index(drop=True)]
    groups = np.split(
        stopped_indices,
        np.flatnonzero(np.diff(stopped_indices) > 1) + 1,
    )
    rests = []
    for group in groups:
        if len(group) < 2 or times[group[-1]] - times[group[0]] < rest_threshold_s:
            continue
        displacement = np.hypot(x[group] - x[group[0]], y[group] - y[group[0]])
        if np.nanmax(displacement) <= 15:
            rests.append((int(group[0]), int(group[-1])))
    efforts = []
    cursor = 0
    for start, end in rests:
        if start - cursor >= 3:
            efforts.append(frame.iloc[cursor:start].reset_index(drop=True))
        cursor = end + 1
    if len(frame) - cursor >= 3:
        efforts.append(frame.iloc[cursor:].reset_index(drop=True))
    return efforts or [frame.reset_index(drop=True)]


def corner_history_rows(
    effort, corners, grid, rx, ry, course_length, metadata,
    effort_number, effort_type,
):
    if effort.empty or not corners:
        return []
    if effort_type == "race lap":
        lap_distance = float(
            effort["distance"].iloc[-1] - effort["distance"].iloc[0]
        )
        if lap_distance <= 0:
            return []
        positions = (
            (effort["distance"].to_numpy(dtype=float) - effort["distance"].iloc[0])
            / lap_distance * course_length
        )
    else:
        coordinates = effort[["x", "y"]].to_numpy(dtype=float)
        positions = np.full(len(coordinates), np.nan)
        for start in range(0, len(coordinates), 500):
            batch = coordinates[start:start + 500]
            distances = (
                (batch[:, None, 0] - rx[None, :]) ** 2
                + (batch[:, None, 1] - ry[None, :]) ** 2
            )
            nearest = np.argmin(distances, axis=1)
            batch_positions = grid[nearest].astype(float)
            batch_positions[np.min(distances, axis=1) > 30 ** 2] = np.nan
            positions[start:start + len(batch)] = batch_positions
    times = effort["t"].to_numpy(dtype=float)
    speeds = effort["mph"].to_numpy(dtype=float)
    powers = effort["power"].to_numpy(dtype=float)
    rows = []
    for number, (_, corner_position) in enumerate(corners, start=1):
        distance = np.minimum(
            np.abs(positions - corner_position),
            course_length - np.abs(positions - corner_position),
        )
        candidates = np.flatnonzero(
            (distance <= 20) & np.isfinite(speeds) & (speeds > 2)
        )
        if not len(candidates):
            continue
        apex = int(candidates[np.argmin(speeds[candidates])])
        entry = speeds[
            (times >= times[apex] - 5)
            & (times < times[apex])
            & np.isfinite(speeds)
        ]
        recovery = powers[
            (times >= times[apex])
            & (times <= times[apex] + 8)
            & np.isfinite(powers)
        ]
        rows.append({
            **metadata,
            "effort_number": effort_number,
            "effort_type": effort_type,
            "corner_id": f"C{number}",
            "course_position_m": round(float(corner_position), 1),
            "covered_passes": 1,
            "entry_mph": float(np.max(entry)) if len(entry) else None,
            "apex_mph": float(speeds[apex]),
            "retained_ratio": (
                float(speeds[apex] / np.max(entry))
                if len(entry) and np.max(entry) > 0 else None
            ),
            "power_after_corner_w": (
                float(np.mean(recovery)) if len(recovery) else None
            ),
        })
    return rows


class handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path = urlsplit(self.path).path
        if path not in ("/", "/index.html"):
            self._respond(404, {"error": "The requested page was not found."})
            return

        html_path = Path(__file__).resolve().parent.parent / "index.html"
        try:
            body = html_path.read_bytes()
        except OSError as error:
            print(f"Frontend could not be read: {error}")
            self._respond(500, {"error": "The application page could not be loaded."})
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
            if content_length <= 0:
                self._respond(400, {"error": "The uploaded FIT file is empty."})
                return
            if content_length > MAX_UPLOAD_BYTES:
                self._respond(413, {"error": "FIT files must be 4 MB or smaller."})
                return
            file_bytes = self.rfile.read(content_length)
            mode = parse_qs(urlsplit(self.path).query).get("mode", [None])[0]
            if mode == "inspect":
                result = inspect_ride(file_bytes)
            elif mode == "analyze":
                options = json.loads(self.headers.get("X-CX-Options", "{}"))
                result = analyze_ride(file_bytes, options)
            else:
                self._respond(400, {"error": "Use mode=inspect or mode=analyze."})
                return
            self._respond(200, result)
        except ValueError as error:
            self._respond(422, {"error": str(error)})
        except Exception as error:
            print(f"FIT analysis failed: {error}")
            self._respond(500, {"error": "The FIT file could not be analyzed."})

    def _respond(self, status, payload):
        body = json.dumps(json_safe(payload), allow_nan=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        print("%s - %s" % (self.address_string(), format % args))
