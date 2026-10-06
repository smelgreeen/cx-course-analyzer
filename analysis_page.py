"""
Cyclocross Course Analyzer
---------------------------
Upload a .fit file, trim it to the part you want analyzed, click to mark
the start/finish line and any features (barrier, flyover, hairpin, ...),
and get lap splits, per-feature consistency stats, a course map colored
by speed, and a course-independent cornering number you can compare
across different courses and sessions.

Run locally:
    streamlit run app.py

Deploy for free:
    push this folder to a public GitHub repo and deploy it on
    https://share.streamlit.io (Streamlit Community Cloud).
"""
from __future__ import annotations

import json
import os
from datetime import datetime

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.colors import sample_colorscale

import fit_utils as fu
from history_utils import append_history_rows
from route_map import route_map

st.markdown(
    """
    <style>
    :root {
        --cx-indigo: #2F2C88;
        --cx-red: #D74642;
        --cx-olive: #A9AC2F;
        --cx-slate: #425F80;
        --cx-ink: #0F0E2A;
        --cx-red-dark: #A8322E;
        --cx-olive-dark: #66691C;
        --cx-slate-dark: #344D69;
        --cx-page: #FAFAFC;
        --cx-panel: #F5F5F9;
    }
    .stApp {
        background: var(--cx-page);
        color: var(--cx-ink);
    }
    [data-testid="stSidebar"] {
        background: #F2F1F8;
        border-right: 1px solid #D8D7E7;
        color: var(--cx-ink);
    }
    [data-testid="stSidebar"] a,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] p {
        color: var(--cx-ink);
    }
    div[data-testid="stHeading"] {
        color: var(--cx-ink);
        border-left: 4px solid var(--cx-indigo);
        padding: 0.15rem 0.55rem;
        margin-top: 0.8rem;
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background-color: var(--cx-panel);
        color: var(--cx-ink);
        border-color: #DEDEE8;
        border-radius: 8px;
        box-shadow: 0 1px 3px rgba(15, 14, 42, 0.04);
    }
    div[data-testid="stDataFrame"] {
        border: 1px solid #DEDEE8;
        border-radius: 5px;
        overflow: hidden;
    }
    div[data-testid="stDataFrame"] [role="columnheader"] {
        background: var(--cx-indigo) !important;
        color: #FFFFFF !important;
    }
    div[data-testid="stDataFrame"] [role="gridcell"] {
        padding: 0.18rem 0.35rem !important;
        font-size: 0.84rem;
    }
    div[data-testid="stDataEditor"] [role="columnheader"] {
        background: var(--cx-indigo) !important;
        color: #FFFFFF !important;
    }
    div[data-testid="stDataEditor"] [role="gridcell"] {
        padding: 0.18rem 0.35rem !important;
    }
    div[data-testid="stButton"] > button,
    div[data-testid="stDownloadButton"] > button,
    div[data-testid="stFormSubmitButton"] > button {
        background-color: var(--cx-indigo) !important;
        border: 1px solid var(--cx-indigo) !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }
    div[data-testid="stButton"] > button *,
    div[data-testid="stDownloadButton"] > button *,
    div[data-testid="stFormSubmitButton"] > button * {
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }
    div[data-testid="stButton"] > button:hover,
    div[data-testid="stDownloadButton"] > button:hover,
    div[data-testid="stFormSubmitButton"] > button:hover,
    div[data-testid="stButton"] > button:focus,
    div[data-testid="stDownloadButton"] > button:focus,
    div[data-testid="stFormSubmitButton"] > button:focus {
        background-color: var(--cx-red-dark) !important;
        border-color: var(--cx-red-dark) !important;
        color: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }
    div[data-testid="stButton"] > button:hover *,
    div[data-testid="stDownloadButton"] > button:hover *,
    div[data-testid="stFormSubmitButton"] > button:hover *,
    div[data-testid="stButton"] > button:focus *,
    div[data-testid="stDownloadButton"] > button:focus *,
    div[data-testid="stFormSubmitButton"] > button:focus * {
        color: #FFFFFF !important;
        fill: #FFFFFF !important;
        -webkit-text-fill-color: #FFFFFF !important;
    }
    div[data-testid="stButton"] > button:disabled,
    div[data-testid="stDownloadButton"] > button:disabled,
    div[data-testid="stFormSubmitButton"] > button:disabled {
        background-color: #E6E6EC !important;
        border-color: #B8B8C6 !important;
        color: #4A4A5B !important;
        opacity: 1 !important;
    }
    a { color: var(--cx-indigo); }
    input, textarea, [data-baseweb="select"] > div {
        border-color: var(--cx-slate);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

COURSES_DIR = "courses"
HISTORY_DIR = "history"
LAP_HISTORY_FILE = "lap_history.csv"
GATE_RADIUS_M = 12
MIN_LAP_GAP_S = 20
os.makedirs(COURSES_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)
SPEED_GREEN_TO_RED = ["#16803c", "#b8d96c", "#ffd166", "#d73027"]
SPEED_BLUE_TO_PURPLE = ["#d9f0ff", "#54a6d8", "#5145a5", "#30104b"]


# --------------------------------------------------------------------------
# Session state setup
# --------------------------------------------------------------------------

def init_state():
    defaults = dict(
        raw_df=None,
        ride_1_filename=None,
        lat0=None, lon0=None,
        trimmed_df=None,
        trim_start_idx=0,
        trim_end_idx=None,
        trim_revision=0,
        trim_confirmed=False,
        start_finish=None,       # (x, y)
        start_finish_confirmed=False,
        features=[],             # list of dicts: name and course-relative interval
        feature_start_index=None,
        feature_end_index=None,
        feature_editing=True,
        map_revision=0,
        feature_type="",
        laps=None,
        grid=None, rx=None, ry=None, L=None,
        profs=None,
        course_name="",
    )
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


init_state()


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def list_saved_courses():
    return sorted(f[:-5] for f in os.listdir(COURSES_DIR) if f.endswith(".json"))


def map_points(df):
    return [[float(row.x), float(row.y), float(row.t)]
            for row in df[["x", "y", "t"]].itertuples(index=False)]


def nearest_index(df, x, y):
    dd = np.hypot(df["x"].to_numpy() - x, df["y"].to_numpy() - y)
    return int(np.argmin(dd))


def convert_xy_origin(x, y, source_origin, target_origin):
    if not source_origin or not target_origin:
        return float(x), float(y)
    lat, lon = fu.xy_to_latlon(x, y, source_origin["lat"], source_origin["lon"])
    target_x, target_y = fu.latlon_to_xy(
        lat, lon, target_origin["lat"], target_origin["lon"],
    )
    return float(target_x), float(target_y)


def normalize_course(course, source_origin, target_origin):
    """Move saved course markers into the current ride's local coordinate frame."""
    course_origin = course.get("origin") or source_origin
    start_x, start_y = convert_xy_origin(
        *course["start_finish"], course_origin, target_origin,
    )
    features = []
    for feature in course.get("features", []):
        if "start_m" in feature and "end_m" in feature:
            features.append({
                "name": feature["name"],
                "start_m": float(feature["start_m"]),
                "end_m": float(feature["end_m"]),
            })
            continue
        old_start_x = feature.get("start_x", feature.get("x"))
        old_start_y = feature.get("start_y", feature.get("y"))
        old_end_x = feature.get("end_x", old_start_x)
        old_end_y = feature.get("end_y", old_start_y)
        start_x_feature, start_y_feature = convert_xy_origin(
            old_start_x, old_start_y, course_origin, target_origin,
        )
        end_x_feature, end_y_feature = convert_xy_origin(
            old_end_x, old_end_y, course_origin, target_origin,
        )
        features.append(dict(
            name=feature["name"],
            start_x=start_x_feature, start_y=start_y_feature,
            end_x=end_x_feature, end_y=end_y_feature,
        ))
    return (start_x, start_y), features


def save_course(name, start_finish, features, origin):
    path = os.path.join(COURSES_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(dict(
            start_finish=start_finish, features=features, origin=origin,
        ), f, indent=2)


def feature_course_interval(feature, grid, rx, ry):
    if "start_m" in feature and "end_m" in feature:
        return float(feature["start_m"]), float(feature["end_m"])
    start_x = feature.get("start_x", feature.get("x"))
    start_y = feature.get("start_y", feature.get("y"))
    end_x = feature.get("end_x", start_x)
    end_y = feature.get("end_y", start_y)
    return (
        fu.project_point_to_course(start_x, start_y, grid, rx, ry),
        fu.project_point_to_course(end_x, end_y, grid, rx, ry),
    )


def load_course(name):
    path = os.path.join(COURSES_DIR, f"{name}.json")
    with open(path) as f:
        return json.load(f        )


def course_position_index(position, grid, course_length):
        if position >= course_length:
            return len(grid)
        return int(np.argmin(np.abs(grid - position)))


def history_path():
    return os.path.join(HISTORY_DIR, "sessions.csv")


def append_history(row: dict):
    path = history_path()
    append_history_rows(path, [row])


def append_lap_history(rows):
    path = os.path.join(HISTORY_DIR, LAP_HISTORY_FILE)
    append_history_rows(path, rows)


def speed_point_colors(values, colorscale, cmin=None, cmax=None):
    values = np.asarray(values, dtype=float)
    finite = values[np.isfinite(values)]
    if not finite.size:
        return [sample_colorscale(colorscale, [0.5])[0]] * len(values)
    low = float(np.nanmin(finite)) if cmin is None else cmin
    high = float(np.nanmax(finite)) if cmax is None else cmax
    if high <= low:
        high = low + 1.0
    return [
        sample_colorscale(
            colorscale,
            [min(1.0, max(0.0, (value - low) / (high - low)))
             if np.isfinite(value) else 0.5],
        )[0]
        for value in values
    ]


def style_ride_comparison(frame, ride_1_columns, ride_2_columns, delta_columns=()):
    ride_1_style = "background-color: #F0EFFA; color: #0F0E2A"
    ride_2_style = "background-color: #FBEDEC; color: #0F0E2A"
    delta_style = "background-color: #EDF1F5; color: #0F0E2A"
    return frame.style.apply(
        lambda column: [ride_1_style] * len(column)
        if column.name in ride_1_columns else
        [ride_2_style] * len(column)
        if column.name in ride_2_columns else
        [delta_style] * len(column)
        if column.name in delta_columns else [""] * len(column),
        axis=0,
    ).set_table_styles([
        {"selector": "th", "props": [
            ("background-color", "#2F2C88"),
            ("color", "#FFFFFF"),
            ("font-size", "0.82rem"),
            ("padding", "0.25rem 0.4rem"),
            ("white-space", "nowrap"),
        ]},
        {"selector": "td", "props": [
            ("font-size", "0.82rem"),
            ("padding", "0.2rem 0.4rem"),
            ("white-space", "nowrap"),
        ]},
        {"selector": "table", "props": [
            ("width", "auto"),
            ("table-layout", "auto"),
        ]},
    ])


def next_default_feature_name(features):
    numbered_names = [
        int(name.removeprefix("Feature "))
        for name in (feature["name"] for feature in features)
        if name.startswith("Feature ") and name.removeprefix("Feature ").isdigit()
    ]
    return f"Feature {max(numbered_names, default=0) + 1}"


def add_gradient_route(fig, x, y, values, colorscale, name, cmin=None,
                       cmax=None):
    """Draw a visually continuous route from short, speed-colored line runs."""
    x, y, values = map(lambda item: np.asarray(item, dtype=float), (x, y, values))
    size = min(len(x), len(y), len(values))
    x, y, values = x[:size], y[:size], values[:size]
    if size < 2:
        return
    finite = values[np.isfinite(values)]
    if not finite.size:
        return
    low = float(np.min(finite)) if cmin is None else cmin
    high = float(np.max(finite)) if cmax is None else cmax
    if high <= low:
        high = low + 1.0
    edge_values = (values[:-1] + values[1:]) / 2
    normalized = np.clip((edge_values - low) / (high - low), 0, 1)
    buckets = np.rint(normalized * 63).astype(int)
    begin = 0
    for end in range(1, len(buckets) + 1):
        if end < len(buckets) and buckets[end] == buckets[begin]:
            continue
        color = sample_colorscale(colorscale, [buckets[begin] / 63])[0]
        fig.add_trace(go.Scatter(
            x=x[begin:end + 1], y=y[begin:end + 1],
            mode="lines", line=dict(color=color, width=6),
            name=name, showlegend=False,
            hovertemplate=f"{name}<br>speed: %{{customdata:.1f}} mph<extra></extra>",
            customdata=values[begin:end + 1],
        ))
        begin = end
    fig.add_trace(go.Scatter(
        x=[None, None], y=[None, None], mode="markers",
        marker=dict(
            size=0.1, color=[low, high], cmin=low, cmax=high,
            colorscale=colorscale, showscale=True,
            colorbar=dict(title="Speed (mph)"),
        ),
        showlegend=False, hoverinfo="skip",
    ))


# --------------------------------------------------------------------------
# Sidebar: file upload
# --------------------------------------------------------------------------

st.sidebar.title("CX Course Analyzer")
uploaded = st.sidebar.file_uploader("Upload a .fit file", type=["fit"])

if uploaded is not None and st.session_state.raw_df is None:
    st.session_state.ride_1_filename = uploaded.name
    try:
        r, _laps_fit = fu.parse_fit(uploaded.read())
    except Exception as e:
        st.sidebar.error(f"Couldn't read this file: {e}")
        r = None
    if r is not None:
        lat0, lon0 = r["lat"].mean(), r["lon"].mean()
        r = fu.to_local_xy(r, lat0, lon0)
        st.session_state.raw_df = r
        st.session_state.lat0 = lat0
        st.session_state.lon0 = lon0
        st.session_state.trimmed_df = r
        st.session_state.trim_end_idx = len(r) - 1

if st.sidebar.button("Start over with a new file"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

if st.session_state.raw_df is None:
    st.title("Cyclocross Course Analyzer")
    st.write(
        "Upload a `.fit` file on the left to get started. You'll be able to "
        "trim out the ride to/from the course, click to mark the start/finish "
        "line and any features (barrier, flyover, hairpin, ...), and get lap "
        "splits, per-feature consistency stats, and a course map colored by speed."
    )
    st.stop()

r = st.session_state.raw_df

# --------------------------------------------------------------------------
# Step 1: trim to the part of the ride you want analyzed
# --------------------------------------------------------------------------

with st.container(border=True):
    st.header("1. Trim to the course")
    if not st.session_state.trim_confirmed:
        st.caption(
            "Drag the start and stop handles. Blue **S** and red **E** dots show the "
            "selected endpoints; the route redraws immediately as you trim."
        )
        if st.session_state.trim_end_idx is None:
            st.session_state.trim_end_idx = len(r) - 1
        st.session_state.trim_start_idx = min(st.session_state.trim_start_idx, len(r) - 2)
        st.session_state.trim_end_idx = min(st.session_state.trim_end_idx, len(r) - 1)
        trim_result = route_map(
            map_points(r), mode="trim",
            start_index=st.session_state.trim_start_idx,
            end_index=st.session_state.trim_end_idx,
            key=f"trim-map-{st.session_state.trim_revision}",
        )
        if isinstance(trim_result, dict) and trim_result.get("type") == "trim":
            start_idx = int(trim_result["start_index"])
            end_idx = int(trim_result["end_index"])
            if (start_idx, end_idx) != (st.session_state.trim_start_idx, st.session_state.trim_end_idx):
                st.session_state.trim_start_idx = start_idx
                st.session_state.trim_end_idx = end_idx
                st.session_state.trim_revision += 1
                st.rerun()

        trimmed_preview = r.iloc[
            st.session_state.trim_start_idx:st.session_state.trim_end_idx + 1
        ]
        st.caption(
            f"{len(trimmed_preview)} GPS points, "
            f"{trimmed_preview['t'].iloc[-1] - trimmed_preview['t'].iloc[0]:.0f}s, "
            f"{trimmed_preview['distance'].iloc[-1] - trimmed_preview['distance'].iloc[0]:.0f} m"
        )
        if st.button("Confirm trim and continue", disabled=len(trimmed_preview) < 2):
            st.session_state.trimmed_df = trimmed_preview.reset_index(drop=True)
            st.session_state.trim_confirmed = True
            st.session_state.start_finish = None
            st.session_state.start_finish_confirmed = False
            st.session_state.features = []
            st.rerun()
    else:
        trimmed_preview = st.session_state.trimmed_df
        st.success(
            f"Trim confirmed: {len(trimmed_preview)} GPS points, "
            f"{trimmed_preview['t'].iloc[-1] - trimmed_preview['t'].iloc[0]:.0f}s."
        )
        if st.button("Adjust trim"):
            st.session_state.trim_confirmed = False
            st.session_state.start_finish = None
            st.session_state.start_finish_confirmed = False
            st.session_state.features = []
            st.session_state.feature_start_index = None
            st.session_state.feature_end_index = None
            st.rerun()

# --------------------------------------------------------------------------
# Step 2: confirm the lap start/finish point
# --------------------------------------------------------------------------

if not st.session_state.trim_confirmed:
    st.stop()

trimmed = st.session_state.trimmed_df
with st.container(border=True):
    st.header("2. Confirm the lap start/finish point")
    if not st.session_state.start_finish_confirmed:
        st.caption("Click the route where each lap crosses the timing line, then confirm the marker.")
        gate_markers = []
        if st.session_state.start_finish:
            gate_markers.append({
                "index": nearest_index(trimmed, *st.session_state.start_finish),
                "color": "#0F0E2A",
            })
        gate_result = route_map(
            map_points(trimmed), mode="click", markers=gate_markers,
            key=f"gate-map-{st.session_state.map_revision}",
        )
        if isinstance(gate_result, dict) and gate_result.get("type") == "point":
            point = trimmed.iloc[int(gate_result["index"])]
            st.session_state.start_finish = (float(point["x"]), float(point["y"]))
            st.session_state.start_finish_confirmed = False
            st.session_state.map_revision += 1
            st.rerun()

        if st.session_state.start_finish:
            st.write("Lap timing point selected.")
            if st.button("Confirm start/finish"):
                st.session_state.start_finish_confirmed = True
                st.session_state.map_revision += 1
                st.rerun()
    else:
        st.success("Lap start/finish point confirmed.")
        if st.button("Change start/finish point"):
            st.session_state.start_finish_confirmed = False
            st.session_state.map_revision += 1
            st.rerun()
if not st.session_state.start_finish_confirmed:
    st.info("Select and confirm the lap start/finish point to continue.")
    st.stop()

# --------------------------------------------------------------------------
# Step 3: detect laps and build a single reference lap
# --------------------------------------------------------------------------

with st.container(border=True):
    st.header("3. Detect laps")
    st.caption(
        f"Using fixed lap detection values for now: a {GATE_RADIUS_M} m timing "
        f"radius and at least {MIN_LAP_GAP_S} seconds between crossings."
    )
    gx, gy = st.session_state.start_finish
    passes = fu.find_gate_passes(
        trimmed, gx, gy, radius=GATE_RADIUS_M, min_gap_s=MIN_LAP_GAP_S,
    )
    if len(passes) < 3:
        st.error(
            f"Only found {len(passes)} crossing(s) of the start/finish point. "
            "Check that the start/finish marker is on the route and the trimmed "
            "ride covers multiple laps. Lap detection currently uses fixed settings."
        )
        st.stop()

    laps = fu.filter_short_laps(fu.split_laps(trimmed, passes))
    if len(laps) < 2:
        st.error("Not enough complete laps found. Adjust the course trim or start/finish marker.")
        st.stop()

st.success(f"Found {len(laps)} complete laps. Features will be marked on one reference lap.")
grid, rx, ry, L = fu.build_reference_path(laps)
profs = fu.all_profiles(laps, grid, "mph")
st.session_state.laps, st.session_state.grid = laps, grid
st.session_state.rx, st.session_state.ry, st.session_state.L = rx, ry, L
st.session_state.profs = profs

# --------------------------------------------------------------------------
# Step 4: mark feature areas on a single course lap
# --------------------------------------------------------------------------

with st.container(border=True):
    st.header("4. Mark feature areas")
    st.caption(
        "This is one reference lap, not the full recording. Choose a feature type, "
        "then click its start and end points in the direction of travel, and confirm "
        "the feature before starting another. Short "
        "segments stay local to this single lap. Route color shifts from slate/olive "
        "for slower speed to red for faster speed."
    )
    name_col, confirm_col, add_feature_col = st.columns([4, 1.2, 1.6])
    with name_col:
        st.text_input(
            "Feature type (reuse the same type to compare similar features)",
            key="feature_type",
            placeholder="e.g. Barrier, Sand, Corner",
        )
feature_markers = []
feature_segments = []
for feature in st.session_state.features:
    start_m, end_m = feature_course_interval(feature, grid, rx, ry)
    feature_start = course_position_index(start_m, grid, L)
    feature_end = course_position_index(end_m, grid, L)
    feature_segments.append({"start_index": feature_start, "end_index": feature_end})
    feature_markers.extend([
        {"index": feature_start, "color": "#D74642"},
        {"index": feature_end, "color": "#ef9c28"},
    ])
if st.session_state.feature_start_index is not None:
    feature_markers.append({"index": st.session_state.feature_start_index, "color": "#D74642"})
if st.session_state.feature_end_index is not None:
    feature_markers.append({"index": st.session_state.feature_end_index, "color": "#ef9c28"})
if st.session_state.feature_start_index is not None and st.session_state.feature_end_index is not None:
    feature_segments.append({
        "start_index": st.session_state.feature_start_index,
        "end_index": st.session_state.feature_end_index,
    })

feature_result = route_map(
    [[float(x), float(y), float(pos)] for x, y, pos in zip(rx, ry, grid)]
    + [[float(rx[0]), float(ry[0]), float(L)]],
    mode="click" if st.session_state.feature_editing else "view",
    markers=feature_markers,
    segments=feature_segments,
    point_colors=speed_point_colors(
        np.concatenate((profs.mean(axis=0), profs.mean(axis=0)[:1])),
        SPEED_GREEN_TO_RED,
    ),
    key=f"feature-map-{st.session_state.map_revision}",
)
if (
    st.session_state.feature_editing
    and isinstance(feature_result, dict)
    and feature_result.get("type") == "point"
):
    point_index = int(feature_result["index"])
    if st.session_state.feature_start_index is None:
        st.session_state.feature_start_index = point_index
    else:
        st.session_state.feature_end_index = point_index
    st.session_state.map_revision += 1
    st.rerun()

with confirm_col:
    if st.button(
        "Confirm",
        disabled=(
            not st.session_state.feature_editing
            or st.session_state.feature_start_index is None
            or st.session_state.feature_end_index is None
        ),
        key="confirm_feature",
        help="Confirm the selected feature area; a name is generated if the name field is blank.",
    ):
        start_index = st.session_state.feature_start_index
        end_index = st.session_state.feature_end_index
        feature_name = st.session_state.feature_type.strip()
        if not feature_name:
            feature_name = next_default_feature_name(st.session_state.features)
        st.session_state.features.append(dict(
            name=feature_name,
            start_m=float(grid[start_index]) if start_index < len(grid) else float(L),
            end_m=float(grid[end_index]) if end_index < len(grid) else float(L),
        ))
        st.session_state.feature_start_index = None
        st.session_state.feature_end_index = None
        st.session_state.feature_editing = False
        st.session_state.map_revision += 1
        st.rerun()

with add_feature_col:
    if st.button(
        "Add new feature",
        disabled=st.session_state.feature_editing,
        key="add_new_feature",
        help="Start marking another feature area.",
    ):
        st.session_state.feature_editing = True
        st.session_state.feature_start_index = None
        st.session_state.feature_end_index = None
        st.session_state.map_revision += 1
        st.rerun()
if (
    st.session_state.feature_editing
    and st.session_state.feature_start_index is not None
):
    if st.button("Clear current feature endpoints"):
        st.session_state.feature_start_index = None
        st.session_state.feature_end_index = None
        st.session_state.map_revision += 1
        st.rerun()

if st.session_state.features:
    st.write("Marked feature areas:")
    for i, feature in enumerate(st.session_state.features):
        c1, c2 = st.columns([5, 1])
        c1.write(f"**{feature['name']}** — start and end marked")
        if c2.button("remove", key=f"rm_feature_{i}"):
            st.session_state.features.pop(i)
            st.rerun()

save_col1, save_col2 = st.columns([3, 1])
with save_col1:
    st.session_state.course_name = st.text_input(
        "Course name (to save this marking for next time)",
        value=st.session_state.course_name, placeholder="e.g. Humboldt Park loop",
    )
with save_col2:
    if st.button("Save course"):
        if st.session_state.course_name:
            save_course(st.session_state.course_name, st.session_state.start_finish,
                        st.session_state.features,
                        origin={"lat": st.session_state.lat0, "lon": st.session_state.lon0})
            st.success(f"Saved as '{st.session_state.course_name}'.")
        else:
            st.warning("Name the course before saving.")

saved = list_saved_courses()
col_saved, col_upload = st.columns(2)
with col_saved:
    if saved:
        pick = st.selectbox("Load a saved course", ["(none)"] + saved)
        if pick != "(none)" and st.button("Load saved course"):
            course = load_course(pick)
            st.session_state.start_finish, st.session_state.features = normalize_course(
                course,
                source_origin={"lat": st.session_state.lat0, "lon": st.session_state.lon0},
                target_origin={"lat": st.session_state.lat0, "lon": st.session_state.lon0},
            )
            st.session_state.start_finish_confirmed = True
            st.session_state.course_name = pick
            st.session_state.feature_editing = False
            st.session_state.feature_start_index = None
            st.session_state.feature_end_index = None
            st.session_state.map_revision += 1
            st.rerun()
with col_upload:
    course_upload = st.file_uploader("Import a course file", type=["json"], key="course_upload")
    if course_upload is not None:
        course = json.load(course_upload)
        st.session_state.start_finish, st.session_state.features = normalize_course(
            course,
            source_origin={"lat": st.session_state.lat0, "lon": st.session_state.lon0},
            target_origin={"lat": st.session_state.lat0, "lon": st.session_state.lon0},
        )
        st.session_state.start_finish_confirmed = True
        st.session_state.course_name = ""
        st.session_state.feature_editing = False
        st.session_state.feature_start_index = None
        st.session_state.feature_end_index = None
        st.session_state.map_revision += 1
        st.rerun()

if st.session_state.start_finish_confirmed:
    st.download_button(
        "Download this course marking as a file",
        data=json.dumps(dict(start_finish=st.session_state.start_finish,
                             features=st.session_state.features,
                             origin={"lat": st.session_state.lat0,
                                     "lon": st.session_state.lon0}), indent=2),
        file_name=f"{st.session_state.course_name or 'course'}.json",
        mime="application/json",
    )

# --------------------------------------------------------------------------
# Step 5: run the analysis
# --------------------------------------------------------------------------

st.header("5. Analysis")
with st.container(border=True):
    st.subheader(f"{len(laps)} laps found")
    st.dataframe(fu.lap_summary(laps), use_container_width=False)
    st.caption(f"Course length (reference lap): {L:.0f} m")

# --- feature stats ---
feature_samples = {}
feature_power_samples = {}
feature_rows = []
feature_intervals = []
feature_positions = []
for ft in st.session_state.features:
    start_pos, end_pos = feature_course_interval(ft, grid, rx, ry)
    feature_intervals.append((start_pos, end_pos))
    feature_positions.append((ft["name"], start_pos, end_pos))
    timings = fu.feature_lap_times(laps, start_pos, end_pos, L)
    if timings:
        feature_samples.setdefault(ft["name"], []).extend(timings)
    powers = fu.feature_lap_mean_power(laps, start_pos, end_pos, L)
    valid_powers = [power for power in powers if np.isfinite(power)]
    if valid_powers:
        feature_power_samples.setdefault(ft["name"], []).extend(valid_powers)

for feature_type, timings in feature_samples.items():
    feature_rows.append(dict(
        feature_type=feature_type,
        measurements=len(timings),
        avg_time_s=round(float(np.mean(timings)), 1),
        std_time_s=round(float(np.std(timings)), 1),
        avg_power_w=round(float(np.mean(feature_power_samples[feature_type])), 1)
        if feature_type in feature_power_samples else None,
    ))

if feature_rows:
    with st.container(border=True):
        st.subheader("Feature times and power by type")
        st.caption(
            "Each marked area is timed from its start point to its end point on every lap. "
            "Times are grouped by feature type; average watts show effort through that area. "
            "Feature areas are excluded from cornering retention."
        )
        st.dataframe(pd.DataFrame(feature_rows), use_container_width=False)

# --- course-independent cornering number ---
ret = fu.corner_retention(
    laps, excluded_intervals=feature_intervals, course_length=L,
)
with st.container(border=True):
    st.subheader("Cornering retention (comparable across different courses)")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Speed retained through corners", f"{ret['retained_ratio']*100:.0f}%" if ret["retained_ratio"] == ret["retained_ratio"] else "n/a")
    c2.metric("Avg entry speed", f"{ret['entry_mph']:.1f} mph")
    c3.metric("Avg apex speed", f"{ret['apex_mph']:.1f} mph")
    c4.metric("Cadence at apex", f"{ret['cadence_apex']:.0f} rpm")
    c5.metric("Power after corner", f"{ret['power_after']:.0f} W" if np.isfinite(ret["power_after"]) else "n/a")
    st.caption(
        "'Retained' = apex speed ÷ entry speed, averaged over every slow point found "
        "on every lap. Because it's a ratio rather than a raw speed, it travels better "
        "across different courses than mph does, so you can compare this number "
        "session to session even when the course changes."
    )

# --- compare another race on this course ---
st.subheader("Compare another race on this course")
comparison_map_data = None
ride_1_name = st.session_state.ride_1_filename or "Ride 1"
comparison_upload = st.file_uploader(
    "Upload another .fit file to compare",
    type=["fit"],
    key="comparison_fit_upload",
    help="The confirmed course start/finish and feature areas will be reused for this ride.",
)
if comparison_upload is not None:
    try:
        comparison_raw, _comparison_laps_fit = fu.parse_fit(comparison_upload.getvalue())
    except Exception as exc:
        st.error(f"Couldn't read the comparison file: {exc}")
        comparison_raw = None

    if comparison_raw is not None:
        comparison_origin = {
            "lat": float(comparison_raw["lat"].mean()),
            "lon": float(comparison_raw["lon"].mean()),
        }
        comparison_raw = fu.to_local_xy(
            comparison_raw, comparison_origin["lat"], comparison_origin["lon"],
        )
        comparison_gate_x, comparison_gate_y = convert_xy_origin(
            gx, gy,
            {"lat": st.session_state.lat0, "lon": st.session_state.lon0},
            comparison_origin,
        )
        comparison_passes = fu.find_gate_passes(
            comparison_raw, comparison_gate_x, comparison_gate_y,
            radius=GATE_RADIUS_M, min_gap_s=MIN_LAP_GAP_S,
        )
        if len(comparison_passes) < 3:
            st.error(
                f"Found only {len(comparison_passes)} start/finish crossing(s) "
                "in the comparison file. Check that it covers multiple laps "
                "of this course and that the timing marker aligns with the route."
            )
        else:
            comparison_laps = fu.filter_short_laps(
                fu.split_laps(comparison_raw, comparison_passes),
            )
            if len(comparison_laps) < 2:
                st.error("The comparison file did not contain enough complete laps.")
            else:
                comparison_grid, comparison_rx, comparison_ry, comparison_length = (
                    fu.build_reference_path(comparison_laps)
                )
                comparison_speed_profile = fu.all_profiles(
                    comparison_laps, comparison_grid, "mph",
                ).mean(axis=0)
                comparison_power_profiles = fu.all_profiles(
                    comparison_laps, comparison_grid, "power",
                )
                comparison_mean_power_profile = (
                    np.nanmean(comparison_power_profiles, axis=0)
                    if np.isfinite(comparison_power_profiles).any() else None
                )
                comparison_intervals = []
                comparison_feature_samples = {}
                comparison_feature_power_samples = {}
                for feature in st.session_state.features:
                    start_pos, end_pos = feature_course_interval(
                        feature, grid, rx, ry,
                    )
                    comparison_start_pos = start_pos / L * comparison_length
                    comparison_end_pos = end_pos / L * comparison_length
                    comparison_intervals.append((
                        comparison_start_pos, comparison_end_pos,
                    ))
                    timings = fu.feature_lap_times(
                        comparison_laps,
                        comparison_start_pos,
                        comparison_end_pos,
                        comparison_length,
                    )
                    if timings:
                        comparison_feature_samples.setdefault(
                            feature["name"], [],
                        ).extend(timings)
                    powers = fu.feature_lap_mean_power(
                        comparison_laps, comparison_start_pos,
                        comparison_end_pos, comparison_length,
                    )
                    valid_powers = [power for power in powers if np.isfinite(power)]
                    if valid_powers:
                        comparison_feature_power_samples.setdefault(
                            feature["name"], [],
                        ).extend(valid_powers)

                comparison_retention = fu.corner_retention(
                    comparison_laps,
                    excluded_intervals=comparison_intervals,
                    course_length=comparison_length,
                )
                primary_avg_lap = float(np.mean([
                    lap["t"].iloc[-1] - lap["t"].iloc[0] for lap in laps
                ]))
                comparison_avg_lap = float(np.mean([
                    lap["t"].iloc[-1] - lap["t"].iloc[0]
                    for lap in comparison_laps
                ]))
                primary_lap_summary = fu.lap_summary(laps)
                comparison_lap_summary = fu.lap_summary(comparison_laps)
                primary_mean_power = primary_lap_summary["avg_power"].mean()
                comparison_mean_power = comparison_lap_summary["avg_power"].mean()
                avg_lap_delta = comparison_avg_lap - primary_avg_lap
                avg_power_delta = comparison_mean_power - primary_mean_power
                retention_delta = (
                    comparison_retention["retained_ratio"] - ret["retained_ratio"]
                ) * 100
                summary_comparison = pd.DataFrame([
                    {
                        "Metric": "Laps",
                        "Ride 1": len(laps),
                        "Ride 2": len(comparison_laps),
                        "Δ": len(comparison_laps) - len(laps),
                    },
                    {
                        "Metric": "Average lap (s)",
                        "Ride 1": round(primary_avg_lap, 1),
                        "Ride 2": round(comparison_avg_lap, 1),
                        "Δ": round(avg_lap_delta, 1),
                    },
                    {
                        "Metric": "Average power (W)",
                        "Ride 1": round(primary_mean_power, 1)
                        if np.isfinite(primary_mean_power) else None,
                        "Ride 2": round(comparison_mean_power, 1)
                        if np.isfinite(comparison_mean_power) else None,
                        "Δ": round(avg_power_delta, 1)
                        if np.isfinite(avg_power_delta) else None,
                    },
                    {
                        "Metric": "Corner speed retained (%)",
                        "Ride 1": round(ret["retained_ratio"] * 100, 1)
                        if np.isfinite(ret["retained_ratio"]) else None,
                        "Ride 2": round(
                            comparison_retention["retained_ratio"] * 100, 1,
                        ) if np.isfinite(comparison_retention["retained_ratio"]) else None,
                        "Δ": round(retention_delta, 1)
                        if np.isfinite(retention_delta) else None,
                    },
                ])
                summary_ride_1 = "Ride 1"
                summary_ride_2 = "Ride 2"
                with st.container(border=True):
                    st.subheader("Race summary")
                    st.caption(
                        f"Ride 1: {ride_1_name} · Ride 2: {comparison_upload.name}"
                    )
                    st.dataframe(
                        style_ride_comparison(
                            summary_comparison, [summary_ride_1], [summary_ride_2],
                            ["Δ"],
                        ),
                        hide_index=True, use_container_width=False,
                    )

                primary_lap_table = primary_lap_summary.rename(columns={
                    "duration_s": "ride_1_lap_s",
                    "avg_mph": "ride_1_avg_mph",
                    "avg_power": "ride_1_avg_power_w",
                    "avg_cadence": "ride_1_avg_cadence_rpm",
                    "distance_m": "ride_1_distance_m",
                })
                comparison_lap_table = comparison_lap_summary.rename(columns={
                    "duration_s": "ride_2_lap_s",
                    "avg_mph": "ride_2_avg_mph",
                    "avg_power": "ride_2_avg_power_w",
                    "avg_cadence": "ride_2_avg_cadence_rpm",
                    "distance_m": "ride_2_distance_m",
                })
                lap_comparison = primary_lap_table.merge(
                    comparison_lap_table, on="lap", how="outer",
                )
                lap_comparison["lap_time_delta_s_ride2_minus_ride1"] = (
                    lap_comparison["ride_2_lap_s"] - lap_comparison["ride_1_lap_s"]
                ).round(1)
                lap_comparison["avg_power_delta_w_ride2_minus_ride1"] = (
                    lap_comparison["ride_2_avg_power_w"]
                    - lap_comparison["ride_1_avg_power_w"]
                ).round(1)
                lap_comparison = lap_comparison[[
                    "lap", "ride_1_lap_s", "ride_2_lap_s",
                    "lap_time_delta_s_ride2_minus_ride1",
                    "ride_1_avg_mph", "ride_2_avg_mph",
                    "ride_1_avg_power_w", "ride_2_avg_power_w",
                    "avg_power_delta_w_ride2_minus_ride1",
                ]].rename(columns={
                    "lap": "Lap",
                    "ride_1_lap_s": "R1 Time (s)",
                    "ride_2_lap_s": "R2 Time (s)",
                    "lap_time_delta_s_ride2_minus_ride1": "Δ Time",
                    "ride_1_avg_mph": "R1 Speed",
                    "ride_2_avg_mph": "R2 Speed",
                    "ride_1_avg_power_w": "R1 Power",
                    "ride_2_avg_power_w": "R2 Power",
                    "avg_power_delta_w_ride2_minus_ride1": "Δ Power",
                })
                lap_ride_1_columns = ["R1 Time (s)", "R1 Speed", "R1 Power"]
                lap_ride_2_columns = ["R2 Time (s)", "R2 Speed", "R2 Power"]
                with st.container(border=True):
                    st.subheader("Lap-by-lap comparison")
                    st.caption(
                        f"R1: {ride_1_name} · R2: {comparison_upload.name} · "
                        "Delta = Ride 2 minus Ride 1."
                    )
                    st.dataframe(
                        style_ride_comparison(
                            lap_comparison, lap_ride_1_columns, lap_ride_2_columns,
                            ["Δ Time", "Δ Power"],
                        ),
                        hide_index=True, use_container_width=False,
                    )

                all_feature_types = sorted(
                    set(feature_samples) | set(comparison_feature_samples),
                )
                feature_comparison_rows = []
                if all_feature_types:
                    for feature_type in all_feature_types:
                        primary_times = feature_samples.get(feature_type, [])
                        comparison_times = comparison_feature_samples.get(feature_type, [])
                        primary_mean = float(np.mean(primary_times)) if primary_times else np.nan
                        comparison_mean = (
                            float(np.mean(comparison_times))
                            if comparison_times else np.nan
                        )
                        feature_comparison_rows.append({
                            "Feature": feature_type,
                            "R1 Time (s)": round(primary_mean, 1) if np.isfinite(primary_mean) else None,
                            "R2 Time (s)": round(comparison_mean, 1) if np.isfinite(comparison_mean) else None,
                            "Δ Time": round(comparison_mean - primary_mean, 1)
                            if np.isfinite(primary_mean) and np.isfinite(comparison_mean)
                            else None,
                            "R1 Power (W)": round(
                                float(np.mean(feature_power_samples[feature_type])), 1,
                            ) if feature_power_samples.get(feature_type) else None,
                            "R2 Power (W)": round(
                                float(np.mean(comparison_feature_power_samples[feature_type])), 1,
                            ) if comparison_feature_power_samples.get(feature_type) else None,
                            "Δ Power": round(
                                float(np.mean(comparison_feature_power_samples[feature_type]))
                                - float(np.mean(feature_power_samples[feature_type])), 1,
                            ) if (comparison_feature_power_samples.get(feature_type)
                                  and feature_power_samples.get(feature_type)) else None,
                        })
                    feature_comparison_frame = pd.DataFrame(feature_comparison_rows)
                    with st.container(border=True):
                        st.subheader("Feature times by type")
                        st.caption(f"R1: {ride_1_name} · R2: {comparison_upload.name}")
                        st.dataframe(
                            style_ride_comparison(
                                feature_comparison_frame,
                                ["R1 Time (s)", "R1 Power (W)"],
                                ["R2 Time (s)", "R2 Power (W)"],
                                ["Δ Time", "Δ Power"],
                            ),
                            hide_index=True, use_container_width=False,
                        )

                st.subheader("Written comparison")
                narrative = []
                if abs(avg_lap_delta) < 0.5:
                    narrative.append(
                        f"**Lap pace:** The rides were close in average lap time "
                        f"(Ride 1 {primary_avg_lap:.1f}s; Ride 2 {comparison_avg_lap:.1f}s)."
                    )
                elif avg_lap_delta < 0:
                    narrative.append(
                        f"**Lap pace:** Ride 2 averaged {abs(avg_lap_delta):.1f}s "
                        f"faster per lap than Ride 1 ({comparison_avg_lap:.1f}s "
                        f"versus {primary_avg_lap:.1f}s)."
                    )
                else:
                    narrative.append(
                        f"**Lap pace:** Ride 2 averaged {avg_lap_delta:.1f}s "
                        f"slower per lap than Ride 1 ({comparison_avg_lap:.1f}s "
                        f"versus {primary_avg_lap:.1f}s)."
                    )

                primary_lap_spread = float(primary_lap_summary["duration_s"].std(ddof=0))
                comparison_lap_spread = float(comparison_lap_summary["duration_s"].std(ddof=0))
                if np.isfinite(primary_lap_spread) and np.isfinite(comparison_lap_spread):
                    spread_delta = comparison_lap_spread - primary_lap_spread
                    if abs(spread_delta) < 0.1:
                        narrative.append(
                            f"**Lap consistency:** Lap-time spread was similar "
                            f"({primary_lap_spread:.1f}s for Ride 1 and "
                            f"{comparison_lap_spread:.1f}s for Ride 2)."
                        )
                    else:
                        more_consistent = "Ride 1" if spread_delta > 0 else "Ride 2"
                        narrative.append(
                            f"**Lap consistency:** Lap-time spread (standard deviation) "
                            f"was {primary_lap_spread:.1f}s for Ride 1 and "
                            f"{comparison_lap_spread:.1f}s for Ride 2; "
                            f"{more_consistent} had the steadier lap times."
                        )

                if np.isfinite(primary_mean_power) and np.isfinite(comparison_mean_power):
                    direction = "higher" if avg_power_delta > 0 else "lower"
                    narrative.append(
                        f"**Power:** Ride 2 averaged {comparison_mean_power:.0f}W "
                        f"versus {primary_mean_power:.0f}W in Ride 1 "
                        f"({abs(avg_power_delta):.0f}W {direction}). This is an "
                        "effort comparison, not by itself a measure of efficiency."
                    )
                else:
                    narrative.append(
                        "**Power:** Average power could not be compared because "
                        "one or both FIT files lack usable power data."
                    )

                if np.isfinite(ret["retained_ratio"]) and np.isfinite(comparison_retention["retained_ratio"]):
                    if abs(retention_delta) < 0.5:
                        retention_text = "was about the same"
                    elif retention_delta > 0:
                        retention_text = f"was {retention_delta:.1f} percentage points higher"
                    else:
                        retention_text = f"was {abs(retention_delta):.1f} percentage points lower"
                    narrative.append(
                        f"**Cornering:** Speed retained through corners "
                        f"{retention_text} in Ride 2 "
                        f"({comparison_retention['retained_ratio'] * 100:.1f}% "
                        f"versus {ret['retained_ratio'] * 100:.1f}%)."
                    )
                else:
                    narrative.append(
                        "**Cornering:** There were not enough valid slow-point "
                        "measurements to compare speed retention reliably."
                    )

                primary_corner_power = ret["power_after"]
                comparison_corner_power = comparison_retention["power_after"]
                if (
                    np.isfinite(primary_corner_power)
                    and np.isfinite(comparison_corner_power)
                ):
                    corner_power_delta = comparison_corner_power - primary_corner_power
                    if abs(corner_power_delta) < 1:
                        corner_power_text = "was similar"
                    elif corner_power_delta > 0:
                        corner_power_text = (
                            f"was {corner_power_delta:.0f}W higher in Ride 2"
                        )
                    else:
                        corner_power_text = (
                            f"was {abs(corner_power_delta):.0f}W lower in Ride 2"
                        )
                    narrative.append(
                        f"**Power out of corners:** Average power during the "
                        f"8-second recovery after detected corner apexes "
                        f"{corner_power_text} "
                        f"({comparison_corner_power:.0f}W in Ride 2 versus "
                        f"{primary_corner_power:.0f}W in Ride 1). This compares "
                        "recorded effort, not efficiency on its own."
                    )
                else:
                    narrative.append(
                        "**Power out of corners:** Could not compare average "
                        "recovery power because one or both rides lack usable "
                        "power samples at detected corners."
                    )

                comparable_features = [
                    row for row in feature_comparison_rows
                    if row["R1 Time (s)"] is not None
                    and row["R2 Time (s)"] is not None
                ]
                if comparable_features:
                    feature_lines = []
                    for row in comparable_features:
                        delta = row["Δ Time"]
                        if delta is None:
                            continue
                        if delta < 0:
                            timing = f"{abs(delta):.1f}s faster"
                        elif delta > 0:
                            timing = f"{delta:.1f}s slower"
                        else:
                            timing = "the same time"
                        power_change = (
                            f"; average power {row['Δ Power']:+.0f}W"
                            if row["Δ Power"] is not None else ""
                        )
                        feature_lines.append(
                            f"- **{row['Feature']}:** Ride 2 averaged "
                            f"{row['R2 Time (s)']:.1f}s versus "
                            f"{row['R1 Time (s)']:.1f}s in Ride 1 "
                            f"({timing}{power_change})."
                        )
                    narrative.append(
                        "**Feature areas:**\n" + "\n".join(feature_lines)
                    )
                elif st.session_state.features:
                    narrative.append(
                        "**Feature areas:** No matching feature times could be "
                        "calculated for both rides."
                    )
                else:
                    narrative.append(
                        "**Feature areas:** No feature areas are marked, so there "
                        "are no segment times to compare."
                    )

                st.markdown("\n\n".join(narrative))
                st.caption(
                    "This summary describes the recorded metrics only. Differences "
                    "can also reflect course conditions, weather, equipment, or "
                    "sensor/GPS variation."
                )
                comparison_map_data = (
                    comparison_grid, comparison_rx, comparison_ry,
                    comparison_speed_profile, comparison_mean_power_profile,
                    comparison_length, comparison_upload.name,
                )

# --- course map colored by speed ---
st.subheader("Course map — speed gradient")
mean_prof = profs.mean(0)
if comparison_map_data:
    (comparison_grid, comparison_rx, comparison_ry, comparison_mean_speed,
     comparison_mean_power, comparison_length, comparison_name) = comparison_map_data
    color_min = float(min(np.nanmin(mean_prof), np.nanmin(comparison_mean_speed)))
    color_max = float(max(np.nanmax(mean_prof), np.nanmax(comparison_mean_speed)))
    st.caption(
        "Line color is speed (mph). Ride 1 uses slate-to-olive-to-red; "
        "Ride 2 uses slate-to-indigo-to-ink. Both maps share the same speed scale."
    )
    map1, map2 = st.columns(2)
else:
    color_min, color_max = float(np.nanmin(mean_prof)), float(np.nanmax(mean_prof))
    st.caption("Line color shifts from slate/olive at slower speeds to red at faster speeds.")
    map1 = st.container()
    map2 = None

with map1:
    st.markdown(f"**Ride 1: {ride_1_name}**")
    primary_map = go.Figure()
    primary_route_x, primary_route_y = np.r_[rx, rx[0]], np.r_[ry, ry[0]]
    add_gradient_route(
        primary_map, primary_route_x, primary_route_y,
        np.r_[mean_prof, mean_prof[0]],
        SPEED_GREEN_TO_RED, "Ride 1", color_min, color_max,
    )
    for name, start_pos, end_pos in feature_positions:
        start_i = course_position_index(start_pos, grid, L)
        end_i = course_position_index(end_pos, grid, L)
        if start_i < len(primary_route_x) and end_i < len(primary_route_x):
            area_indices = (
                list(range(start_i, end_i + 1)) if end_i >= start_i
                else list(range(start_i, len(primary_route_x))) + list(range(0, end_i + 1))
            )
            primary_map.add_trace(go.Scatter(
                x=primary_route_x[area_indices], y=primary_route_y[area_indices], mode="lines",
                line=dict(color="#0F0E2A", width=2, dash="dot"),
                name=f"{name} feature area", showlegend=False,
                hovertemplate=f"{name} feature area<extra></extra>",
            ))
            for position, label in ((start_pos, f"{name} start"), (end_pos, f"{name} end")):
                index = course_position_index(position, grid, L)
                index %= len(rx)
                if index < len(rx):
                    primary_map.add_trace(go.Scatter(
                        x=[rx[index]], y=[ry[index]], mode="markers+text",
                        marker=dict(size=10, color="#0F0E2A", symbol="circle"),
                        text=[label], textposition="top center",
                        showlegend=False, hoverinfo="skip",
                    ))
    primary_map.update_layout(
        height=600, dragmode="pan", yaxis=dict(scaleanchor="x", scaleratio=1),
        margin=dict(l=10, r=20, t=10, b=10), showlegend=False,
    )
    st.plotly_chart(
        primary_map, use_container_width=True,
        config={"scrollZoom": True, "displayModeBar": True},
    )

if map2 is not None:
    with map2:
        st.markdown(f"**Ride 2 — {comparison_name}**")
        comparison_map = go.Figure()
        comparison_route_x = np.r_[comparison_rx, comparison_rx[0]]
        comparison_route_y = np.r_[comparison_ry, comparison_ry[0]]
        add_gradient_route(
            comparison_map,
            comparison_route_x, comparison_route_y,
            np.r_[comparison_mean_speed, comparison_mean_speed[0]],
            SPEED_BLUE_TO_PURPLE, "Ride 2", color_min, color_max,
        )
        for name, start_pos, end_pos in feature_positions:
            comp_start = start_pos / L * comparison_length
            comp_end = end_pos / L * comparison_length
            start_i = course_position_index(comp_start, comparison_grid, comparison_length)
            end_i = course_position_index(comp_end, comparison_grid, comparison_length)
            if start_i < len(comparison_route_x) and end_i < len(comparison_route_x):
                area_indices = (
                    list(range(start_i, end_i + 1)) if end_i >= start_i
                    else list(range(start_i, len(comparison_route_x))) + list(range(0, end_i + 1))
                )
                comparison_map.add_trace(go.Scatter(
                    x=comparison_route_x[area_indices], y=comparison_route_y[area_indices],
                    mode="lines", line=dict(color="#0F0E2A", width=2, dash="dot"),
                    name=f"{name} feature area", showlegend=False,
                    hovertemplate=f"{name} feature area<extra></extra>",
                ))
                for position, label in (
                    (comp_start, f"{name} start"), (comp_end, f"{name} end"),
                ):
                    index = course_position_index(
                        position, comparison_grid, comparison_length,
                    )
                    index %= len(comparison_rx)
                    if index < len(comparison_rx):
                        comparison_map.add_trace(go.Scatter(
                            x=[comparison_rx[index]], y=[comparison_ry[index]],
                            mode="markers+text",
                            marker=dict(size=10, color="#0F0E2A", symbol="circle"),
                            text=[label], textposition="top center",
                            showlegend=False, hoverinfo="skip",
                        ))
        comparison_map.update_layout(
            height=600, dragmode="pan", yaxis=dict(scaleanchor="x", scaleratio=1),
            margin=dict(l=10, r=20, t=10, b=10), showlegend=False,
        )
        st.plotly_chart(
            comparison_map, use_container_width=True,
            config={"scrollZoom": True, "displayModeBar": True},
        )

# --- side-by-side speed and power comparisons ---
st.subheader("Ride profiles by metric")
speed_col, power_col = st.columns(2)
speed_fig = go.Figure()
speed_fig.add_trace(go.Scatter(
    x=grid, y=mean_prof, mode="lines", name="Ride 1",
    line=dict(color="#d73027", width=2),
))
if comparison_map_data:
    speed_fig.add_trace(go.Scatter(
        x=comparison_grid / comparison_length * L,
        y=comparison_mean_speed, mode="lines", name="Ride 2",
        line=dict(color="#5145a5", width=2),
    ))
for name, start_pos, end_pos in feature_positions:
    speed_fig.add_vline(x=start_pos, line_dash="dot", line_color="gray",
                        annotation_text=f"{name} start", annotation_position="top")
    speed_fig.add_vline(x=end_pos, line_dash="dot", line_color="gray",
                        annotation_text=f"{name} end", annotation_position="top")
speed_fig.update_layout(
    height=400, title="Speed comparison",
    xaxis_title="Meters into lap", yaxis_title="Speed (mph)",
    legend=dict(orientation="h"), margin=dict(l=10, r=10, t=45, b=10),
)
with speed_col:
    st.plotly_chart(speed_fig, use_container_width=True)

power_profiles = fu.all_profiles(laps, grid, "power")
mean_power_profile = (
    np.nanmean(power_profiles, axis=0)
    if np.isfinite(power_profiles).any() else None
)
if mean_power_profile is not None:
    power_fig = go.Figure()
    power_fig.add_trace(go.Scatter(
        x=grid, y=mean_power_profile, mode="lines", name="Ride 1",
        line=dict(color="#2878b5", width=2),
    ))
    if comparison_map_data and comparison_mean_power is not None:
        power_fig.add_trace(go.Scatter(
            x=comparison_grid / comparison_length * L,
            y=comparison_mean_power, mode="lines", name="Ride 2",
            line=dict(color="#ef8a17", width=2),
        ))
    for name, start_pos, end_pos in feature_positions:
        power_fig.add_vline(x=start_pos, line_dash="dot", line_color="gray",
                            annotation_text=f"{name} start", annotation_position="top")
        power_fig.add_vline(x=end_pos, line_dash="dot", line_color="gray",
                            annotation_text=f"{name} end", annotation_position="top")
    power_fig.update_layout(
        height=400, title="Power comparison",
        xaxis_title="Meters into lap", yaxis_title="Power (W)",
        legend=dict(orientation="h"), margin=dict(l=10, r=10, t=45, b=10),
    )
    with power_col:
        st.plotly_chart(power_fig, use_container_width=True)
        if comparison_map_data and comparison_mean_power is None:
            st.info("Ride 2 has no valid power samples to compare.")
else:
    with power_col:
        st.info("No valid power samples were recorded in Ride 1's FIT file.")

# --------------------------------------------------------------------------
# Step 6: save this session to history for trend tracking
# --------------------------------------------------------------------------

with st.container(border=True):
    st.header("6. Save this session")
    sess_date = st.date_input("Date of this ride", value=datetime.now().date())
    sess_type = st.selectbox("Type", ["practice", "race"])
    sess_course = st.text_input("Course name for history", value=st.session_state.course_name)

    if st.button("Add to history"):
        primary_lap_summary = fu.lap_summary(laps)
        average_power = primary_lap_summary["avg_power"].mean()
        row = dict(
            date=str(sess_date), type=sess_type, course=sess_course,
            n_laps=len(laps),
            retained_ratio=round(ret["retained_ratio"], 3)
            if np.isfinite(ret["retained_ratio"]) else None,
            power_after_corner_w=round(ret["power_after"], 1)
            if np.isfinite(ret["power_after"]) else None,
            entry_mph=round(ret["entry_mph"], 2), apex_mph=round(ret["apex_mph"], 2),
            cadence_apex=round(ret["cadence_apex"], 1),
            avg_power_w=round(float(average_power), 1) if np.isfinite(average_power) else None,
            avg_lap_s=round(float(primary_lap_summary["duration_s"].mean()), 1),
            avg_speed_mph=round(float(primary_lap_summary["avg_mph"].mean()), 2),
        )
        for fr in feature_rows:
            row[f"{fr['feature_type']}_avg_time_s"] = fr["avg_time_s"]
            row[f"{fr['feature_type']}_avg_power_w"] = fr["avg_power_w"]
        append_history(row)
        append_lap_history([
            {
                "date": str(sess_date), "type": sess_type, "course": sess_course,
                "ride_file": ride_1_name, **lap,
            }
            for lap in primary_lap_summary.to_dict(orient="records")
        ])
        st.success("Saved to history.")
