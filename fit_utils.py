"""
Core analysis logic for the cyclocross course analyzer.

This module has no Streamlit dependency so it can be tested and reused
on its own. Everything operates on plain pandas DataFrames / numpy arrays.
"""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import fitdecode
import numpy as np
import pandas as pd

MPS_TO_MPH = 2.236936


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

def parse_fit(file_bytes: bytes) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Parse a .fit file (as raw bytes) into (records_df, laps_df)."""
    records, laps = [], []
    with fitdecode.FitReader(io.BytesIO(file_bytes)) as f:
        for frame in f:
            if isinstance(frame, fitdecode.FitDataMessage):
                d = {field.name: field.value for field in frame.fields}
                if frame.name == "record":
                    records.append(d)
                elif frame.name == "lap":
                    laps.append(d)

    r = pd.DataFrame(records)
    if r.empty:
        raise ValueError("No GPS record data found in this .fit file.")

    r = r.dropna(subset=["position_lat", "position_long"]).reset_index(drop=True)
    if r.empty:
        raise ValueError("This .fit file has no GPS fixes (position_lat/long).")

    r["t"] = (r["timestamp"] - r["timestamp"].iloc[0]).dt.total_seconds()
    r["lat"] = r["position_lat"] * 180 / 2**31
    r["lon"] = r["position_long"] * 180 / 2**31
    speed_col = "enhanced_speed" if "enhanced_speed" in r.columns else "speed"
    r["mph"] = r[speed_col].fillna(0) * MPS_TO_MPH
    if "distance" not in r.columns:
        r["distance"] = np.nan
    for col in ("power", "cadence"):
        if col not in r.columns:
            r[col] = np.nan

    laps_df = pd.DataFrame(laps)
    return r, laps_df


def to_local_xy(df: pd.DataFrame, lat0: float, lon0: float) -> pd.DataFrame:
    """Add local flat-earth x/y columns (meters) around a reference point."""
    df = df.copy()
    df["x"] = (df["lon"] - lon0) * 111320 * np.cos(np.radians(lat0))
    df["y"] = (df["lat"] - lat0) * 110540
    return df


def latlon_to_xy(lat, lon, lat0, lon0):
    x = (lon - lon0) * 111320 * np.cos(np.radians(lat0))
    y = (lat - lat0) * 110540
    return x, y


def xy_to_latlon(x, y, lat0, lon0):
    lon = x / (111320 * np.cos(np.radians(lat0))) + lon0
    lat = y / 110540 + lat0
    return lat, lon


# --------------------------------------------------------------------------
# Lap splitting via a gate (start/finish) point
# --------------------------------------------------------------------------

def find_gate_passes(df: pd.DataFrame, gx: float, gy: float,
                      radius: float = 12.0, min_gap_s: float = 20.0) -> list[int]:
    """Return row indices of the closest approach each time the rider
    passes within `radius` meters of (gx, gy), collapsing passes that are
    within `min_gap_s` seconds of each other into a single crossing."""
    dd = np.hypot(df["x"].values - gx, df["y"].values - gy)
    idx = np.where(dd < radius)[0]
    if len(idx) == 0:
        return []
    groups = [[idx[0]]]
    for i in idx[1:]:
        if df["t"].iloc[i] - df["t"].iloc[groups[-1][-1]] > min_gap_s:
            groups.append([i])
        else:
            groups[-1].append(i)
    passes = [g[int(np.argmin(dd[g]))] for g in groups]
    return passes


def split_laps(df: pd.DataFrame, pass_indices: list[int]) -> list[pd.DataFrame]:
    laps = []
    for k in range(len(pass_indices) - 1):
        a, b = pass_indices[k], pass_indices[k + 1]
        laps.append(df.iloc[a:b + 1].reset_index(drop=True))
    return laps


def filter_short_laps(laps: list[pd.DataFrame], min_frac: float = 0.5) -> list[pd.DataFrame]:
    """Drop laps whose distance is much shorter than the median lap —
    these are usually a double-crossing of the gate radius (e.g. the
    start/finish sits right next to another part of the course) rather
    than a real lap."""
    if len(laps) < 3:
        return laps
    dists = np.array([l["distance"].iloc[-1] - l["distance"].iloc[0] for l in laps])
    med = np.median(dists)
    return [l for l, d in zip(laps, dists) if d >= med * min_frac]


# --------------------------------------------------------------------------
# Course-position alignment
# --------------------------------------------------------------------------

def build_reference_path(laps: list[pd.DataFrame], grid_step: float = 10.0):
    """Pick the lap closest to the median length as the reference line,
    and return (grid, ref_x, ref_y) — the course laid out as x/y at
    regular distance intervals."""
    lens = [l["distance"].iloc[-1] - l["distance"].iloc[0] for l in laps]
    L = float(np.median(lens))
    ref_i = int(np.argmin([abs(x - L) for x in lens]))
    ref = laps[ref_i].drop_duplicates("distance").copy()
    ref["s"] = ref["distance"] - ref["distance"].iloc[0]
    grid = np.arange(0, L, grid_step)
    rx = np.interp(grid, ref["s"], ref["x"])
    ry = np.interp(grid, ref["s"], ref["y"])
    return grid, rx, ry, L


def project_point_to_course(px: float, py: float, grid: np.ndarray,
                             rx: np.ndarray, ry: np.ndarray) -> float:
    """Return the course distance (meters into the lap) of the nearest
    point on the reference path to (px, py)."""
    dd = np.hypot(rx - px, ry - py)
    j = int(np.argmin(dd))
    return float(grid[j])


def lap_profile(lap: pd.DataFrame, grid: np.ndarray, col: str = "mph") -> np.ndarray:
    l = lap.drop_duplicates("distance")
    s = l["distance"] - l["distance"].iloc[0]
    values = l[col].astype(float)
    if col == "power":
        values = values.interpolate(limit_direction="both")
        if values.notna().sum() == 0:
            return np.full(grid.shape, np.nan, dtype=float)
    else:
        values = values.fillna(0)
    return np.interp(grid, s, values)


def all_profiles(laps: list[pd.DataFrame], grid: np.ndarray, col: str = "mph") -> np.ndarray:
    return np.array([lap_profile(l, grid, col) for l in laps])


# --------------------------------------------------------------------------
# Feature (corner / obstacle) stats
# --------------------------------------------------------------------------

@dataclass
class FeatureStat:
    name: str
    course_pos_m: float
    mean_mph: float
    std_mph: float
    cv_pct: float
    per_lap_mph: list[float] = field(default_factory=list)
    mean_power: float | None = None


def feature_stats(laps: list[pd.DataFrame], grid: np.ndarray,
                   profs: np.ndarray, pos_m: float, name: str,
                   window_m: float = 20.0) -> FeatureStat:
    """Stats for a marked feature: average/consistency of speed in a
    window around its course position, taking the *minimum* speed in
    that window per lap (the apex / slowest point of the feature)."""
    mask = (grid >= pos_m - window_m) & (grid <= pos_m + window_m)
    if not mask.any():
        mask = np.array([np.argmin(np.abs(grid - pos_m))])
    per_lap = profs[:, mask].min(axis=1)
    pw = None
    try:
        pwprofs = all_profiles(laps, grid, "power")
        pw = float(np.nanmean(pwprofs[:, mask]))
    except Exception:
        pass
    return FeatureStat(
        name=name,
        course_pos_m=pos_m,
        mean_mph=float(np.nanmean(per_lap)),
        std_mph=float(np.nanstd(per_lap)),
        cv_pct=float(np.nanstd(per_lap) / np.nanmean(per_lap) * 100) if np.nanmean(per_lap) else float("nan"),
        per_lap_mph=per_lap.tolist(),
        mean_power=pw,
    )


# --------------------------------------------------------------------------
# Generic cornering-retention metric (course-independent)
# --------------------------------------------------------------------------

def corner_retention(laps: list[pd.DataFrame], vmin_thresh: float = 11.0,
                      recover_s: int = 8,
                      excluded_intervals: list[tuple[float, float]] | None = None,
                      course_length: float | None = None) -> dict:
    """Find local speed minima (corner apexes) across all laps and
    compute how much entry speed is retained at the apex, on average.
    This number is comparable across *different* courses."""
    entries, apexes, exits, cads, pws = [], [], [], [], []
    for l in laps:
        l = l.reset_index(drop=True)
        v = l["mph"].values
        pw = l["power"].values if "power" in l else np.full(len(v), np.nan)
        cad = l["cadence"].values if "cadence" in l else np.full(len(v), np.nan)
        for i in range(3, len(v) - recover_s - 1):
            if v[i] < v[i - 1] and v[i] <= v[i + 1] and 2 < v[i] < vmin_thresh:
                if course_length and excluded_intervals:
                    position = float(l["distance"].iloc[i] - l["distance"].iloc[0]) % course_length
                    inside_feature = any(
                        start <= position <= end if start <= end
                        else position >= start or position <= end
                        for start, end in excluded_intervals
                    )
                    if inside_feature:
                        continue
                entry = v[max(0, i - 5):i].max() if i > 0 else v[i]
                exitv = v[i + recover_s]
                entries.append(entry)
                apexes.append(v[i])
                exits.append(exitv)
                cads.append(np.nanmean(cad[max(0, i - 2):i + 2]))
                pws.append(np.nanmean(pw[i:i + recover_s]))
    entries, apexes, exits = map(np.array, (entries, apexes, exits))
    ratio = apexes / np.where(entries > 0, entries, np.nan)
    return dict(
        n=len(entries),
        entry_mph=float(np.nanmean(entries)) if len(entries) else float("nan"),
        apex_mph=float(np.nanmean(apexes)) if len(apexes) else float("nan"),
        exit_mph=float(np.nanmean(exits)) if len(exits) else float("nan"),
        retained_ratio=float(np.nanmean(ratio)) if len(ratio) else float("nan"),
        cadence_apex=float(np.nanmean(cads)) if len(cads) else float("nan"),
        power_after=float(np.nanmean(pws)) if len(pws) else float("nan"),
    )


def feature_lap_times(laps: list[pd.DataFrame], start_m: float, end_m: float,
                      course_length: float) -> list[float]:
    """Return elapsed seconds through a course segment for each lap."""
    if course_length <= 0:
        return []

    lap_times = []
    wraps = end_m < start_m
    for lap in laps:
        distance = lap["distance"].to_numpy(dtype=float)
        elapsed = lap["t"].to_numpy(dtype=float)
        if len(distance) < 2:
            continue
        lap_distance = distance[-1] - distance[0]
        if lap_distance <= 0:
            continue
        positions = (distance - distance[0]) / lap_distance * course_length
        start_pos = start_m / course_length * lap_distance
        end_pos = end_m / course_length * lap_distance
        if wraps:
            end_pos += lap_distance
            positions = np.concatenate((positions, positions[1:] + lap_distance))
            elapsed = np.concatenate((elapsed, elapsed[1:] + (elapsed[-1] - elapsed[0])))
        start_time = np.interp(start_pos, positions, elapsed)
        end_time = np.interp(end_pos, positions, elapsed)
        if end_time > start_time:
            lap_times.append(float(end_time - start_time))
    return lap_times


def feature_lap_mean_power(laps: list[pd.DataFrame], start_m: float,
                           end_m: float, course_length: float) -> list[float]:
    """Return time-weighted mean watts within a feature area for each lap."""
    if course_length <= 0:
        return []

    means = []
    wraps = end_m < start_m
    for lap in laps:
        distance = lap["distance"].to_numpy(dtype=float)
        elapsed = lap["t"].to_numpy(dtype=float)
        power = lap["power"].to_numpy(dtype=float)
        if len(distance) < 2:
            means.append(float("nan"))
            continue
        lap_distance = distance[-1] - distance[0]
        if lap_distance <= 0:
            means.append(float("nan"))
            continue

        positions = (distance - distance[0]) / lap_distance * course_length
        if wraps:
            positions = np.concatenate((positions, positions[1:] + course_length))
            elapsed = np.concatenate((elapsed, elapsed[1:] + elapsed[-1] - elapsed[0]))
            power = np.concatenate((power, power[1:]))
        start_pos = start_m / course_length * lap_distance
        end_pos = end_m / course_length * lap_distance
        if wraps:
            end_pos += lap_distance
        start_time = float(np.interp(start_pos, positions, elapsed))
        end_time = float(np.interp(end_pos, positions, elapsed))
        valid = np.isfinite(power) & np.isfinite(elapsed)
        if end_time <= start_time or not valid.any():
            means.append(float("nan"))
            continue

        power_times = elapsed[valid]
        power_values = power[valid]
        interior = power_times[(power_times > start_time) & (power_times < end_time)]
        sample_times = np.concatenate(([start_time], interior, [end_time]))
        sample_power = np.interp(sample_times, power_times, power_values)
        area = np.sum(
            (sample_power[:-1] + sample_power[1:]) * 0.5 * np.diff(sample_times),
        )
        means.append(float(area / (end_time - start_time)))
    return means


# --------------------------------------------------------------------------
# Lap summary table
# --------------------------------------------------------------------------

def lap_summary(laps: list[pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for i, l in enumerate(laps, start=1):
        rows.append(dict(
            lap=i,
            duration_s=round(float(l["t"].iloc[-1] - l["t"].iloc[0]), 1),
            distance_m=round(float(l["distance"].iloc[-1] - l["distance"].iloc[0]), 0),
            avg_mph=round(float(l["mph"].mean()), 2),
            avg_power=round(float(l["power"].mean()), 0) if l["power"].notna().any() else None,
            avg_cadence=round(float(l["cadence"][l["mph"] > 2].mean()), 0) if l["cadence"].notna().any() else None,
        ))
    return pd.DataFrame(rows)
