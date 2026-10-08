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
    .cx-dashboard-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        background: #2F2C88;
        color: #FFFFFF;
        padding: 0.75rem 1.2rem;
        border-radius: 8px;
        margin: 0 0 1rem;
    }
    .cx-dashboard-header h1 {
        color: #FFFFFF;
        font-family: Georgia, serif;
        font-size: 2.1rem;
        margin: 0;
    }
    .st-key-landing-map-card {
        position: relative !important;
        min-height: 465px;
    }
    .st-key-landing-map-card [data-testid="stMarkdown"] svg {
        display: block;
        width: 100%;
        height: 385px;
        border-radius: 8px;
        background: #DDE8E2;
    }
    .st-key-landing-map-card .st-key-main_fit_upload {
        position: absolute !important;
        top: 200px !important;
        left: 50%;
        z-index: 5;
        width: min(250px, 75%);
        transform: translate(-50%, -50%);
        padding: 0.4rem 0.65rem;
        border-radius: 8px;
        background: rgba(255, 255, 255, 0.96);
        box-shadow: 0 2px 10px rgba(15, 14, 42, 0.18);
    }
    .st-key-landing-map-card .st-key-main_fit_upload [data-testid="stFileUploader"] section,
    .st-key-landing-map-card .st-key-main_fit_upload [data-testid="stFileUploaderDropzone"] {
        padding: 0;
        border: 0;
        background: transparent;
    }
    .st-key-landing-map-card .st-key-main_fit_upload small {
        display: none;
    }
    .cx-placeholder-map {
        width: 100%;
        height: 385px;
        border-radius: 8px;
        background: linear-gradient(145deg, #D9E6DF, #B9CEC6);
    }
    .cx-placeholder-label {
        fill: #425F80;
        font: 600 16px system-ui, sans-serif;
    }
    .cx-comparison-placeholder {
        min-height: 220px;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 1px solid #DEDEE8;
        border-radius: 8px;
        background: #E6E8E8;
        color: #425F80;
        font-weight: 600;
        text-align: center;
        padding: 1rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

COURSES_DIR = "courses"
HISTORY_DIR = "history"
LAP_HISTORY_FILE = "lap_history.csv"
GATE_RADIUS_M = 6
MIN_LAP_GAP_S = 20
os.makedirs(COURSES_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)
SPEED_RED_TO_GREEN = ["#d73027", "#ffd166", "#b8d96c", "#16803c"]


def render_comparison_placeholder():
    with st.container(border=True):
        st.subheader("Ride comparison")
        st.caption(
            "Ride 1 stays visible while you set up the course. Upload a second "
            "FIT file any time; comparisons will appear once setup is complete."
        )
        map_col_one, map_col_two = st.columns(2, gap="medium")
        ride_1_df = (
            st.session_state.trimmed_df
            if st.session_state.trimmed_df is not None
            else st.session_state.raw_df
        )
        with map_col_one.container(border=True):
            st.markdown("**Ride 1 course map**")
            if (
                ride_1_df is not None
                and {"x", "y"}.issubset(ride_1_df.columns)
                and len(ride_1_df) > 1
            ):
                speed_column = next(
                    (column for column in ("mph", "speed_mph")
                     if column in ride_1_df.columns),
                    None,
                )
                figure = go.Figure()
                if speed_column is not None:
                    ride_speed = pd.to_numeric(
                        ride_1_df[speed_column], errors="coerce",
                    ).to_numpy(dtype=float)
                else:
                    ride_speed = np.array([], dtype=float)
                if speed_column is not None and np.isfinite(ride_speed).any():
                    add_gradient_route(
                        figure, ride_1_df["x"], ride_1_df["y"], ride_speed,
                        SPEED_RED_TO_GREEN, "Ride 1",
                    )
                else:
                    figure.add_trace(go.Scatter(
                        x=ride_1_df["x"], y=ride_1_df["y"],
                        mode="lines", line=dict(color="#16803c", width=6),
                        showlegend=False,
                    ))
                figure.update_layout(
                    height=360, dragmode="pan",
                    yaxis=dict(scaleanchor="x", scaleratio=1),
                    margin=dict(l=10, r=15, t=10, b=10),
                    showlegend=False,
                )
                st.plotly_chart(
                    figure, use_container_width=True,
                    config={"scrollZoom": True, "displayModeBar": True},
                    key="ride1-comparison-map-setup",
                )
            else:
                st.markdown(
                    '<div class="cx-comparison-placeholder">'
                    'Ride 1 map will appear after uploading a FIT file</div>',
                    unsafe_allow_html=True,
                )
        with map_col_two.container(border=True):
            st.markdown("**Ride 2**")
            st.markdown(
                '<div class="cx-comparison-placeholder">'
                'Upload a second FIT file to compare</div>',
                unsafe_allow_html=True,
            )
            comparison_upload = st.file_uploader(
                "Upload second FIT file",
                type=["fit"],
                key="comparison_fit_upload",
                help="This file will be compared after Ride 1 course setup is complete.",
            )
        if comparison_upload is not None:
            st.session_state.comparison_upload_data = comparison_upload.getvalue()
            st.session_state.comparison_upload_name = comparison_upload.name
        else:
            st.session_state.pop("comparison_upload_data", None)
            st.session_state.pop("comparison_upload_name", None)
        table_col_one, table_col_two = st.columns(2)
        with table_col_one:
            st.dataframe(pd.DataFrame({
                "Metric": ["Laps", "Average lap", "Average power", "Corner retention"],
                "Ride 1": ["—", "—", "—", "—"],
                "Ride 2": ["—", "—", "—", "—"],
                "Δ": ["—", "—", "—", "—"],
            }), hide_index=True, use_container_width=True)
        with table_col_two:
            st.info("Lap-by-lap comparison appears here after both rides are analyzed.")


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
        corner_editing=False,
        corner_added_positions=[],
        corner_removed_positions=[],
        last_gate_map_event_id=None,
        last_feature_map_event_id=None,
        map_revision=0,
        gate_radius_m=GATE_RADIUS_M,
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


def append_corner_history(rows):
    append_history_rows(os.path.join(HISTORY_DIR, "corner_history.csv"), rows)


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
    x, y, values = map(
        lambda item: np.asarray(item, dtype=float), (x, y, values),
    )
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
    left, right = values[:-1], values[1:]
    edge_values = np.where(
        np.isfinite(left) & np.isfinite(right),
        (left + right) / 2,
        np.where(
            np.isfinite(left), left,
            np.where(np.isfinite(right), right, (low + high) / 2),
        ),
    )
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


def course_speed_figure(
    rx, ry, speed, colorscale, name, cmin, cmax,
    feature_positions, grid, course_length, corner_positions=(),
):
    route_x, route_y = np.r_[rx, rx[0]], np.r_[ry, ry[0]]
    figure = go.Figure()
    add_gradient_route(
        figure, route_x, route_y, np.r_[speed, speed[0]],
        colorscale, name, cmin, cmax,
    )
    for feature_name, start_pos, end_pos in feature_positions:
        start_i = course_position_index(start_pos, grid, course_length)
        end_i = course_position_index(end_pos, grid, course_length)
        if start_i >= len(route_x) or end_i >= len(route_x):
            continue
        area_indices = (
            list(range(start_i, end_i + 1)) if end_i >= start_i
            else list(range(start_i, len(route_x))) + list(range(0, end_i + 1))
        )
        figure.add_trace(go.Scatter(
            x=route_x[area_indices], y=route_y[area_indices],
            mode="lines", line=dict(color="#0F0E2A", width=2, dash="dot"),
            name=f"{feature_name} feature area", showlegend=False,
            hovertemplate=f"{feature_name} feature area<extra></extra>",
        ))
        for position, label in (
            (start_pos, f"{feature_name} start"),
            (end_pos, f"{feature_name} end"),
        ):
            index = course_position_index(position, grid, course_length) % len(rx)
            figure.add_trace(go.Scatter(
                x=[rx[index]], y=[ry[index]], mode="markers+text",
                marker=dict(size=10, color="#0F0E2A"),
                text=[label], textposition="top center",
                showlegend=False, hoverinfo="skip",
            ))
    if corner_positions:
        corner_indices = [index for index, _ in corner_positions]
        figure.add_trace(go.Scatter(
            x=np.asarray(rx)[corner_indices],
            y=np.asarray(ry)[corner_indices],
            mode="markers+text",
            marker=dict(size=20, color="#2F2C88", line=dict(color="white", width=2)),
            text=[f"C{number}" for number in range(1, len(corner_indices) + 1)],
            textposition="middle center",
            textfont=dict(size=9, color="white"),
            name="Ride 1 corners",
            showlegend=False,
            hovertemplate="Corner %{text}<extra></extra>",
        ))
    figure.update_layout(
        height=420, dragmode="pan",
        yaxis=dict(scaleanchor="x", scaleratio=1),
        margin=dict(l=10, r=15, t=10, b=10), showlegend=False,
    )
    return figure


def detect_ride1_corners(
    grid, rx, ry, profiles, course_length, excluded_intervals,
):
    mean_speed = np.nanmean(profiles, axis=0)
    if (
        not len(grid) or not np.isfinite(mean_speed).any()
        or course_length <= 0 or len(rx) != len(grid) or len(ry) != len(grid)
        or len(grid) < 5
        or not np.isfinite(rx).all() or not np.isfinite(ry).all()
    ):
        return []

    grid_steps = np.diff(grid)
    grid_step = float(np.median(grid_steps))
    if grid_step <= 0 or not np.isfinite(grid_step):
        return []
    sample_count = len(grid)

    # Smooth the lap join before using circular differences. The reference
    # lap's final GPS point may not land exactly on its first point.
    closing_step = max(0.0, float(course_length - grid[-1]))
    if len(grid_steps):
        last_step = float(grid_steps[-1])
        end_x = rx[-1] + (rx[-1] - rx[-2]) * closing_step / last_step
        end_y = ry[-1] + (ry[-1] - ry[-2]) * closing_step / last_step
        seam_blend_m = min(150.0, course_length / 4)
        progress = np.clip(
            (grid - (course_length - seam_blend_m)) / seam_blend_m,
            0.0, 1.0,
        )
        smooth_source_x = np.asarray(rx, dtype=float) - progress * (end_x - rx[0])
        smooth_source_y = np.asarray(ry, dtype=float) - progress * (end_y - ry[0])
    else:
        smooth_source_x = np.asarray(rx, dtype=float)
        smooth_source_y = np.asarray(ry, dtype=float)
    weights = (1, 2, 3, 2, 1)
    smooth_x = sum(
        weight * np.roll(smooth_source_x, offset)
        for weight, offset in zip(weights, range(-2, 3))
    ) / sum(weights)
    smooth_y = sum(
        weight * np.roll(smooth_source_y, offset)
        for weight, offset in zip(weights, range(-2, 3))
    ) / sum(weights)

    # Sum absolute changes in route heading at several scales. Unlike one
    # long chord angle, this does not cancel opposing turns in an S-bend.
    segment_x = np.roll(smooth_x, -1) - smooth_x
    segment_y = np.roll(smooth_y, -1) - smooth_y
    heading = np.arctan2(segment_y, segment_x)
    heading_delta = np.arctan2(
        np.sin(heading - np.roll(heading, 1)),
        np.cos(heading - np.roll(heading, 1)),
    )
    absolute_turn = np.abs(np.degrees(heading_delta))
    turn_signal = np.zeros(sample_count, dtype=float)
    window_sizes = sorted({
        max(3, int(round(distance / grid_step)))
        for distance in (30, 50, 70)
    })
    for window_size in window_sizes:
        window_size = min(window_size, sample_count - 1)
        first_offset = -(window_size // 2)
        window_turn = sum(
            np.roll(absolute_turn, offset)
            for offset in range(first_offset, first_offset + window_size)
        )
        turn_signal = np.maximum(turn_signal, window_turn)

    candidate_scores = {}
    for index in range(sample_count):
        position = float(grid[index])
        if any(
            start <= position <= end if start <= end
            else position >= start or position <= end
            for start, end in excluded_intervals
        ):
            continue
        if not (
            turn_signal[index] >= np.roll(turn_signal, 1)[index]
            and turn_signal[index] >= np.roll(turn_signal, -1)[index]
            and (
                turn_signal[index] > np.roll(turn_signal, 1)[index]
                or turn_signal[index] > np.roll(turn_signal, -1)[index]
            )
        ):
            continue
        backward = (float(grid[index]) - grid) % course_length
        forward = (grid - float(grid[index])) % course_length
        surrounding = turn_signal[
            ((backward >= 80) & (backward <= 140))
            | ((forward >= 80) & (forward <= 140))
        ]
        turn_prominence = (
            float(
                turn_signal[index]
                - np.nanpercentile(surrounding, 25)
            )
            if surrounding.size else float(turn_signal[index])
        )
        if turn_signal[index] >= 8 and turn_prominence >= 4:
            candidate_scores[index] = (
                float(turn_signal[index]) + turn_prominence
            )

    # Keep speed-based detection as a second signal for corners that have a
    # clear speed loss but only a modest geometric change.
    smooth_speed = (
        np.roll(mean_speed, 1) + mean_speed + np.roll(mean_speed, -1)
    ) / 3
    local_minima = (
        (smooth_speed > 2)
        & (smooth_speed <= np.roll(smooth_speed, 1))
        & (smooth_speed <= np.roll(smooth_speed, -1))
        & (
            (smooth_speed < np.roll(smooth_speed, 1))
            | (smooth_speed < np.roll(smooth_speed, -1))
        )
    )
    for index in np.flatnonzero(local_minima):
        position = float(grid[index])
        if any(
            start <= position <= end if start <= end
            else position >= start or position <= end
            for start, end in excluded_intervals
        ):
            continue
        backward = (position - grid) % course_length
        forward = (grid - position) % course_length
        left = smooth_speed[(backward >= 20) & (backward <= 80)]
        right = smooth_speed[(forward >= 20) & (forward <= 80)]
        if not left.size or not right.size:
            continue
        surrounding_speed = min(float(np.nanmax(left)), float(np.nanmax(right)))
        prominence = surrounding_speed - float(smooth_speed[index])
        required_prominence = max(0.4, surrounding_speed * 0.03)
        if prominence >= required_prominence:
            candidate_scores[int(index)] = max(
                candidate_scores.get(int(index), 0.0),
                float(turn_signal[index]) + prominence * 5,
            )

    # Merge nearby speed/geometry peaks into one table/map corner label.
    selected = []
    for index, _ in sorted(
        candidate_scores.items(), key=lambda item: item[1], reverse=True,
    ):
        position = float(grid[index])
        if all(
            min(
                abs(position - grid[other]),
                course_length - abs(position - grid[other]),
            ) >= 30
            for other in selected
        ):
            selected.append(index)
    selected.sort(key=lambda item: grid[item])
    return [(index, float(grid[index])) for index in selected]


def ride1_corner_speed_table(
    grid, profiles, course_length, corners,
):
    rows = []
    for lap_number, lap_profile in enumerate(profiles, start=1):
        row = {"Lap": lap_number}
        for corner_number, (index, position) in enumerate(corners, start=1):
            distance = np.abs(grid - position)
            distance = np.minimum(distance, course_length - distance)
            speeds = lap_profile[distance <= 20]
            valid_speeds = speeds[np.isfinite(speeds) & (speeds > 2)]
            row[f"Corner {corner_number} · {position:.0f} m"] = (
                round(float(np.min(valid_speeds)), 1) if valid_speeds.size else None
            )
        rows.append(row)
    return pd.DataFrame(rows)


def merge_corner_positions(
    grid, course_length, detected, added_positions, removed_positions,
    excluded_intervals,
):
    def is_excluded(position):
        return any(
            start <= position <= end if start <= end
            else position >= start or position <= end
            for start, end in excluded_intervals
        )

    corners = [
        (index, position)
        for index, position in detected
        if all(
            min(abs(position - removed), course_length - abs(position - removed)) > 20
            for removed in removed_positions
        )
    ]
    for added_position in added_positions:
        added_position = float(added_position) % course_length
        if is_excluded(added_position) or any(
            min(
                abs(added_position - position),
                course_length - abs(added_position - position),
            ) < 20
            for _, position in corners
        ):
            continue
        added_index = course_position_index(added_position, grid, course_length)
        corners.append((added_index, float(grid[added_index])))
    return sorted(corners, key=lambda item: item[1])


def split_practice_efforts(frame, rest_threshold_s=30):
    """Split a practice into moving efforts around sustained stationary rests."""
    if frame.empty:
        return []
    speed = pd.to_numeric(frame["mph"], errors="coerce").fillna(0).to_numpy()
    times = pd.to_numeric(frame["t"], errors="coerce").to_numpy(dtype=float)
    x = pd.to_numeric(frame["x"], errors="coerce").to_numpy(dtype=float)
    y = pd.to_numeric(frame["y"], errors="coerce").to_numpy(dtype=float)
    stopped = speed <= 1.5
    stopped_indices = np.flatnonzero(stopped)
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
        displacement = np.hypot(
            x[group] - x[group[0]], y[group] - y[group[0]],
        )
        if np.nanmax(displacement) <= 15:
            rests.append((int(group[0]), int(group[-1])))

    efforts = []
    cursor = 0
    for rest_start, rest_end in rests:
        if rest_start - cursor >= 2:
            efforts.append(frame.iloc[cursor:rest_start].reset_index(drop=True))
        cursor = rest_end + 1
    if len(frame) - cursor >= 2:
        efforts.append(frame.iloc[cursor:].reset_index(drop=True))
    return [effort for effort in efforts if len(effort) >= 3]


def corner_history_rows(
    effort, corners, grid, rx, ry, course_length, metadata,
    effort_number, effort_type, lap_number=None,
):
    """Summarize the covered corner passes for one lap or practice effort."""
    if effort.empty or not corners:
        return []
    if effort_type == "race lap":
        positions = (
            pd.to_numeric(effort["distance"], errors="coerce").to_numpy(dtype=float)
            - float(effort["distance"].iloc[0])
        ) % course_length
    else:
        coordinates = effort[["x", "y"]].to_numpy(dtype=float)
        positions = np.empty(len(coordinates), dtype=float)
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

    times = pd.to_numeric(effort["t"], errors="coerce").to_numpy(dtype=float)
    speeds = pd.to_numeric(effort["mph"], errors="coerce").to_numpy(dtype=float)
    powers = pd.to_numeric(
        effort.get("power", pd.Series(np.nan, index=effort.index)),
        errors="coerce",
    ).to_numpy(dtype=float)
    rows = []
    for corner_number, (_, corner_position) in enumerate(corners, start=1):
        around_corner = np.minimum(
            np.abs(positions - corner_position),
            course_length - np.abs(positions - corner_position),
        ) <= 20
        candidate_indices = np.flatnonzero(
            around_corner & np.isfinite(speeds) & (speeds > 2)
        )
        if not len(candidate_indices):
            continue

        apex_indices = []
        last_apex_time = -np.inf
        for index in candidate_indices:
            previous_speed = speeds[index - 1] if index > 0 else np.inf
            next_speed = speeds[index + 1] if index + 1 < len(speeds) else np.inf
            if (
                speeds[index] <= previous_speed
                and speeds[index] <= next_speed
                and times[index] - last_apex_time >= 15
            ):
                apex_indices.append(index)
                last_apex_time = times[index]
        if not apex_indices:
            apex_indices = [int(candidate_indices[np.argmin(speeds[candidate_indices])])]

        entry_speeds = []
        apex_speeds = []
        retentions = []
        recovery_powers = []
        for index in apex_indices:
            before = (times >= times[index] - 5) & (times < times[index])
            entry = speeds[before & np.isfinite(speeds)]
            if len(entry):
                entry_speeds.append(float(np.max(entry)))
                retentions.append(float(speeds[index] / np.max(entry)))
            apex_speeds.append(float(speeds[index]))
            recovery = (
                (times >= times[index]) & (times <= times[index] + 8)
                & np.isfinite(powers)
            )
            if recovery.any():
                recovery_powers.append(float(np.mean(powers[recovery])))

        rows.append({
            **metadata,
            "effort_number": effort_number,
            "effort_type": effort_type,
            "lap_number": lap_number,
            "corner_id": f"C{corner_number}",
            "course_position_m": round(float(corner_position), 1),
            "covered_passes": len(apex_speeds),
            "entry_mph": round(float(np.mean(entry_speeds)), 2)
            if entry_speeds else None,
            "apex_mph": round(float(np.mean(apex_speeds)), 2),
            "retained_ratio": round(float(np.mean(retentions)), 4)
            if retentions else None,
            "power_after_corner_w": round(float(np.mean(recovery_powers)), 1)
            if recovery_powers else None,
        })
    return rows


# --------------------------------------------------------------------------
# Sidebar: file upload
# --------------------------------------------------------------------------

st.sidebar.title("CX Course Analyzer")
if st.sidebar.button("Start over with a new file"):
    for k in list(st.session_state.keys()):
        del st.session_state[k]
    st.rerun()

if st.session_state.raw_df is None:
    st.markdown(
        '<div class="cx-dashboard-header"><h1>Analyzer 3000</h1>'
        '<span>Ride analysis</span></div>', unsafe_allow_html=True,
    )
    landing_map_col, landing_data_col = st.columns([1.8, 1], gap="medium")
    with landing_map_col:
        with st.container(border=True, key="landing-map-card"):
            st.markdown(
                """
                <svg class="cx-placeholder-map" viewBox="0 0 900 500"
                     role="img" aria-label="Placeholder course map">
                  <path d="M90 255 C55 170 130 155 170 185 C205 207 180 112 262 132
                    C330 148 340 195 420 166 C495 139 525 73 598 105
                    C672 139 625 205 566 223 C500 243 526 310 610 305
                    C703 300 770 242 803 295 C836 350 762 395 690 363
                    C625 335 573 420 499 389 C424 357 400 287 327 321
                    C258 353 216 407 160 365 C111 328 132 294 90 255 Z"
                    fill="none" stroke="#E4A78E" stroke-width="19"
                    stroke-linecap="round" stroke-linejoin="round"/>
                  <path d="M90 255 C55 170 130 155 170 185 C205 207 180 112 262 132
                    C330 148 340 195 420 166 C495 139 525 73 598 105
                    C672 139 625 205 566 223 C500 243 526 310 610 305
                    C703 300 770 242 803 295 C836 350 762 395 690 363
                    C625 335 573 420 499 389 C424 357 400 287 327 321
                    C258 353 216 407 160 365 C111 328 132 294 90 255 Z"
                    fill="none" stroke="#F3C4AE" stroke-width="12"
                    stroke-linecap="round" stroke-linejoin="round"/>
                  <circle cx="263" cy="132" r="12" fill="#A9AC2F"/>
                  <text x="670" y="115" class="cx-placeholder-label">Course map</text>
                </svg>
                """,
                unsafe_allow_html=True,
            )
            landing_upload = st.file_uploader(
                "Upload .fit file",
                type=["fit"],
                key="main_fit_upload",
                help="Choose the main ride file to start your analysis.",
            )
    with landing_data_col:
        with st.container(border=True):
            st.subheader("Ride 1")
            st.caption("Your ride metrics will appear here after upload.")
            metric_a, metric_b = st.columns(2)
            metric_a.metric("Corner speed retained", "—")
            metric_b.metric("Power after corner", "—")
            metric_c, metric_d = st.columns(2)
            metric_c.metric("Entry speed", "—")
            metric_d.metric("Apex speed", "—")
            st.markdown("**Lap data**")
            st.info("Upload a ride to see lap times, speed, and power.")

    render_comparison_placeholder()

    if landing_upload is not None:
        st.session_state.ride_1_filename = landing_upload.name
        try:
            ride_data, _laps_fit = fu.parse_fit(landing_upload.getvalue())
        except Exception as exc:
            st.error(f"Couldn't read this FIT file: {exc}")
        else:
            if ride_data.empty or not {"lat", "lon"}.issubset(ride_data.columns):
                st.error("This FIT file does not contain usable GPS coordinates.")
            else:
                lat0, lon0 = ride_data["lat"].mean(), ride_data["lon"].mean()
                ride_data = fu.to_local_xy(ride_data, lat0, lon0)
                st.session_state.raw_df = ride_data
                st.session_state.lat0 = lat0
                st.session_state.lon0 = lon0
                st.session_state.trimmed_df = ride_data
                st.session_state.trim_end_idx = len(ride_data) - 1
                st.rerun()
    st.stop()

r = st.session_state.raw_df

st.markdown(
    '<div class="cx-dashboard-header"><h1>Analyzer 3000</h1>'
    '<span>Ride analysis</span></div>', unsafe_allow_html=True,
)
ride_1_name = st.session_state.ride_1_filename or "Ride 1"
map_col, ride1_col = st.columns([1.8, 1], gap="medium")
map_slot = map_col.empty()
ride1_slot = ride1_col.empty()
with ride1_slot.container(border=True):
    st.subheader(f"Ride 1 · {ride_1_name}")
    st.caption("Ride data is being prepared.")
    placeholder_metrics = st.columns(2)
    placeholder_metrics[0].metric("Corner speed retained", "—")
    placeholder_metrics[1].metric("Power after corner", "—")
    placeholder_metrics = st.columns(2)
    placeholder_metrics[0].metric("Average entry speed", "—")
    placeholder_metrics[1].metric("Average apex speed", "—")
    st.markdown("**Lap data**")
    st.info("Lap times, speed, power, and features will appear here.")

# --------------------------------------------------------------------------
# Step 1: trim to the part of the ride you want analyzed
# --------------------------------------------------------------------------

if not st.session_state.trim_confirmed:
    if st.session_state.trim_end_idx is None:
        st.session_state.trim_end_idx = len(r) - 1
    st.session_state.trim_start_idx = min(st.session_state.trim_start_idx, len(r) - 2)
    st.session_state.trim_end_idx = min(st.session_state.trim_end_idx, len(r) - 1)
    with map_slot.container(border=True):
        st.header("Trim to the course")
        st.caption(
            "Drag the start and stop handles. The route redraws immediately; "
            "zoom in on tight sections before setting the trim endpoints."
        )
        trim_result = route_map(
            map_points(r), mode="trim",
            start_index=st.session_state.trim_start_idx,
            end_index=st.session_state.trim_end_idx,
            key="trim-map",
        )
        trimmed_preview = r.iloc[
            st.session_state.trim_start_idx:st.session_state.trim_end_idx + 1
        ]
        st.caption(
            f"{len(trimmed_preview)} GPS points, "
            f"{trimmed_preview['t'].iloc[-1] - trimmed_preview['t'].iloc[0]:.0f}s, "
            f"{trimmed_preview['distance'].iloc[-1] - trimmed_preview['distance'].iloc[0]:.0f} m"
        )
        if st.button(
            "Confirm trim and continue",
            disabled=len(trimmed_preview) < 2,
            key="confirm_trim_in_map",
        ):
            st.session_state.trimmed_df = trimmed_preview.reset_index(drop=True)
            st.session_state.trim_confirmed = True
            st.session_state.start_finish = None
            st.session_state.start_finish_confirmed = False
            st.session_state.features = []
            st.session_state.corner_editing = False
            st.session_state.corner_added_positions = []
            st.session_state.corner_removed_positions = []
            st.rerun()
    if isinstance(trim_result, dict) and trim_result.get("type") == "trim":
        start_idx = int(trim_result["start_index"])
        end_idx = int(trim_result["end_index"])
        if (start_idx, end_idx) != (
            st.session_state.trim_start_idx, st.session_state.trim_end_idx,
        ):
            st.session_state.trim_start_idx = start_idx
            st.session_state.trim_end_idx = end_idx
            st.session_state.trim_revision += 1
            st.rerun()

else:
    trimmed_preview = st.session_state.trimmed_df

# --------------------------------------------------------------------------
# Step 2: confirm the lap start/finish point
# --------------------------------------------------------------------------

if not st.session_state.trim_confirmed:
    render_comparison_placeholder()
    st.stop()

trimmed = st.session_state.trimmed_df
if not st.session_state.start_finish_confirmed:
    with map_slot.container(border=True):
        st.header("Set lap start/finish")
        st.caption(
            "Zoom in on the timing line if two course sections are close. "
            "Use a smaller detection radius to avoid catching the nearby section."
        )
        st.slider(
            "Start/finish detection radius",
            min_value=2,
            max_value=20,
            step=1,
            key="gate_radius_m",
            help=(
                "Reduce this when another part of the course passes close to "
                "the timing point. Increase it if GPS drift makes crossings miss."
            ),
            format="%d m",
        )
        gate_markers = []
        if st.session_state.start_finish:
            gate_markers.append({
                "index": nearest_index(trimmed, *st.session_state.start_finish),
                "color": "#0F0E2A",
            })
        gate_result = route_map(
            map_points(trimmed), mode="click", markers=gate_markers,
            key="gate-map",
        )
        if st.session_state.start_finish:
            st.caption("Timing point selected.")
            if st.button("Confirm start/finish", key="confirm_start_finish_in_map"):
                st.session_state.start_finish_confirmed = True
                st.session_state.map_revision += 1
                st.rerun()
    if (
        isinstance(gate_result, dict)
        and gate_result.get("type") == "point"
        and gate_result.get("event_id")
        != st.session_state.last_gate_map_event_id
    ):
        st.session_state.last_gate_map_event_id = gate_result.get("event_id")
        point = trimmed.iloc[int(gate_result["index"])]
        st.session_state.start_finish = (float(point["x"]), float(point["y"]))
        st.session_state.start_finish_confirmed = False
        st.session_state.map_revision += 1
        st.rerun()
if not st.session_state.start_finish_confirmed:
    render_comparison_placeholder()
    st.info("Select and confirm the lap start/finish point to continue.")
    st.stop()

# --------------------------------------------------------------------------
# Detect laps and build a single reference lap
# --------------------------------------------------------------------------

gx, gy = st.session_state.start_finish
passes = fu.find_gate_passes(
    trimmed, gx, gy, radius=st.session_state.gate_radius_m,
    min_gap_s=MIN_LAP_GAP_S,
)
if len(passes) < 2:
    st.error(
        f"Only found {len(passes)} crossing(s) of the start/finish point. "
        "At least two crossings (one complete lap) are needed to establish "
        "the course reference. Check that the start/finish marker is on the "
        "route and the trim includes a complete lap."
    )
    render_comparison_placeholder()
    st.stop()

laps = fu.filter_short_laps(fu.split_laps(trimmed, passes))
if not laps:
    st.error("No complete lap found. Adjust the course trim or start/finish marker.")
    render_comparison_placeholder()
    st.stop()

grid, rx, ry, L = fu.build_reference_path(laps)
profs = fu.all_profiles(laps, grid, "mph")
st.session_state.laps, st.session_state.grid = laps, grid
st.session_state.rx, st.session_state.ry, st.session_state.L = rx, ry, L
st.session_state.profs = profs

# --------------------------------------------------------------------------
# Step 4: mark feature areas on the shared primary map
# --------------------------------------------------------------------------

feature_markers = []
feature_segments = []
feature_intervals = []
feature_positions = []
for feature in st.session_state.features:
    start_m, end_m = feature_course_interval(feature, grid, rx, ry)
    feature_intervals.append((start_m, end_m))
    feature_positions.append((feature["name"], start_m, end_m))
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
corner_positions = merge_corner_positions(
    grid, L,
    detect_ride1_corners(grid, rx, ry, profs, L, feature_intervals),
    st.session_state.corner_added_positions,
    st.session_state.corner_removed_positions,
    feature_intervals,
)
feature_markers.extend(
    {
        "index": index,
        "label": f"C{number}",
        "color": "#2F2C88",
        "corner_position": position,
    }
    for number, (index, position) in enumerate(corner_positions, start=1)
)

feature_result = None
with map_slot.container(border=True):
    st.header(
        "Edit corner markers" if st.session_state.corner_editing
        else "Mark feature areas" if st.session_state.feature_editing
        else "Ride 1 course map"
    )
    st.caption("Lap start/finish point confirmed.")
    if st.button("Change start/finish point", key="change_start_finish_in_map"):
        st.session_state.start_finish_confirmed = False
        st.session_state.corner_editing = False
        st.session_state.corner_added_positions = []
        st.session_state.corner_removed_positions = []
        st.session_state.map_revision += 1
        st.rerun()
    if st.session_state.corner_editing:
        st.caption(
            "Click an empty route point to add a corner marker. Click an "
            "existing marker to remove it. Changes update the map and "
            "Ride 1 corner speed table."
        )
    elif st.session_state.feature_editing:
        st.caption(
            "Click the start and end of each feature in the direction of travel. "
            "Confirm the feature here; blank names are numbered automatically."
        )
        st.text_input(
            "Feature type (reuse types to compare similar features)",
            key="feature_type",
            placeholder="e.g. Barrier, Sand, Corner",
        )
    else:
        st.caption(
            "Speed-colored Ride 1 map. Edit detected corner markers or add "
            "another feature."
        )
    feature_result = route_map(
        [[float(x), float(y), float(pos)] for x, y, pos in zip(rx, ry, grid)]
        + [[float(rx[0]), float(ry[0]), float(L)]],
        mode=(
            "corner_edit" if st.session_state.corner_editing
            else "click" if st.session_state.feature_editing else "view"
        ),
        markers=feature_markers,
        segments=feature_segments,
        point_colors=speed_point_colors(
            np.concatenate((profs.mean(axis=0), profs.mean(axis=0)[:1])),
            SPEED_RED_TO_GREEN,
        ),
        key="feature-map",
    )
    control_col, secondary_col, tertiary_col = st.columns([1, 1, 1])
    if st.session_state.corner_editing:
        if control_col.button("Finish editing corners", key="finish_corner_editing"):
            st.session_state.corner_editing = False
            st.session_state.map_revision += 1
            st.rerun()
    elif st.session_state.feature_editing:
        if control_col.button(
            "Confirm feature",
            disabled=(
                st.session_state.feature_start_index is None
                or st.session_state.feature_end_index is None
            ),
            key="confirm_feature_in_map",
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
        if st.session_state.feature_start_index is not None:
            if secondary_col.button(
                "Clear selected points", key="clear_feature_points_in_map",
            ):
                st.session_state.feature_start_index = None
                st.session_state.feature_end_index = None
                st.session_state.map_revision += 1
                st.rerun()
        if tertiary_col.button("Skip features", key="skip_features_in_map"):
            st.session_state.feature_start_index = None
            st.session_state.feature_end_index = None
            st.session_state.feature_editing = False
            st.session_state.map_revision += 1
            st.rerun()
    else:
        if control_col.button("Edit corners", key="edit_corners_in_map"):
            st.session_state.corner_editing = True
            st.session_state.map_revision += 1
            st.rerun()
        if secondary_col.button("Add new feature", key="add_feature_in_map"):
            st.session_state.feature_editing = True
            st.session_state.feature_start_index = None
            st.session_state.feature_end_index = None
            st.session_state.map_revision += 1
            st.rerun()
if (
    st.session_state.feature_editing
    and not st.session_state.corner_editing
    and isinstance(feature_result, dict)
    and feature_result.get("type") == "point"
    and feature_result.get("event_id")
    != st.session_state.last_feature_map_event_id
):
    st.session_state.last_feature_map_event_id = feature_result.get("event_id")
    point_index = int(feature_result["index"])
    if st.session_state.feature_start_index is None:
        st.session_state.feature_start_index = point_index
    else:
        st.session_state.feature_end_index = point_index
    st.session_state.map_revision += 1
    st.rerun()
if (
    st.session_state.corner_editing
    and isinstance(feature_result, dict)
    and feature_result.get("type") == "point"
    and feature_result.get("event_id")
    != st.session_state.last_feature_map_event_id
):
    st.session_state.last_feature_map_event_id = feature_result.get("event_id")
    point_index = int(feature_result["index"]) % len(grid)
    position = float(grid[point_index])
    inside_feature = any(
        start <= position <= end if start <= end
        else position >= start or position <= end
        for start, end in feature_intervals
    )
    if inside_feature:
        st.info("Corner markers cannot be added inside a marked feature area.")
    elif any(
        min(abs(position - existing), L - abs(position - existing)) < 20
        for _, existing in corner_positions
    ):
        st.info("A corner marker already exists near that point.")
    else:
        st.session_state.corner_added_positions.append(position)
        st.session_state.map_revision += 1
        st.rerun()
elif (
    st.session_state.corner_editing
    and isinstance(feature_result, dict)
    and feature_result.get("type") == "remove_corner"
    and feature_result.get("event_id")
    != st.session_state.last_feature_map_event_id
):
    st.session_state.last_feature_map_event_id = feature_result.get("event_id")
    position = float(feature_result["position"])
    added_match = next(
        (
            added for added in st.session_state.corner_added_positions
            if min(abs(position - added), L - abs(position - added)) <= 1
        ),
        None,
    )
    if added_match is not None:
        st.session_state.corner_added_positions.remove(added_match)
    else:
        st.session_state.corner_removed_positions.append(position)
    st.session_state.map_revision += 1
    st.rerun()
# --------------------------------------------------------------------------
# Run the analysis
# --------------------------------------------------------------------------

primary_lap_summary = fu.lap_summary(laps)

# --- feature stats ---
feature_samples = {}
feature_power_samples = {}
feature_rows = []
for ft, (_, start_pos, end_pos) in zip(
    st.session_state.features, feature_positions,
):
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

# --- course-independent cornering number ---
ret = fu.corner_retention(
    laps, excluded_intervals=feature_intervals, course_length=L,
)
ride1_slot.empty()
with ride1_slot.container(border=True):
    st.subheader(f"Ride 1 · {ride_1_name}")
    st.caption(f"{len(laps)} laps · {L:.0f} m reference lap")
    metric_row_one = st.columns(2)
    metric_row_one[0].metric(
        "Speed retained through corners",
        f"{ret['retained_ratio'] * 100:.0f}%"
        if np.isfinite(ret["retained_ratio"]) else "n/a",
    )
    metric_row_one[1].metric(
        "Power after corner",
        f"{ret['power_after']:.0f} W"
        if np.isfinite(ret["power_after"]) else "n/a",
    )
    metric_row_two = st.columns(2)
    metric_row_two[0].metric(
        "Average entry speed",
        f"{ret['entry_mph']:.1f} mph"
        if np.isfinite(ret["entry_mph"]) else "n/a",
    )
    metric_row_two[1].metric(
        "Average apex speed",
        f"{ret['apex_mph']:.1f} mph"
        if np.isfinite(ret["apex_mph"]) else "n/a",
    )
    st.caption(
        "Power after corner is the average over the 8-second recovery after "
        "detected corner apexes. Retention compares apex to entry speed."
    )
    st.markdown("**Lap data**")
    lap_display = primary_lap_summary[[
        "lap", "duration_s", "avg_mph", "avg_power",
    ]].rename(columns={
        "lap": "Lap", "duration_s": "Time (s)",
        "avg_mph": "Speed", "avg_power": "Power (W)",
    })
    st.dataframe(lap_display, hide_index=True, use_container_width=True)
    corner_speed_display = ride1_corner_speed_table(
        grid, profs, L, corner_positions,
    )
    if len(corner_speed_display.columns) > 1:
        st.markdown("**Corner speed by lap · Ride 1**")
        st.caption(
            "Corners are identified from the reference route shape and lap "
            "speed profile. Values are the minimum speed within 20 m of each "
            "point; marked feature areas are excluded."
        )
        st.dataframe(
            corner_speed_display, hide_index=True, use_container_width=True,
        )
    else:
        st.caption("No additional corner speed points were detected outside marked features.")
    if feature_rows:
        st.markdown("**Feature data**")
        st.dataframe(pd.DataFrame(feature_rows), hide_index=True, use_container_width=True)

# --- compare another race on this course ---
comparison_map_data = None
ride_1_name = st.session_state.ride_1_filename or "Ride 1"
mean_prof = profs.mean(0)
with st.container(border=True):
    st.subheader("Compare rides")
    st.caption(
        "Ride 1 is shown on the left. Upload a second FIT file on the right "
        "to compare maps, lap data, power, and features."
    )
    compare_map_cols = st.columns(2, gap="medium")
    with compare_map_cols[0].container(border=True):
        st.markdown(f"**Ride 1 · {ride_1_name}**")
        primary_map_slot = st.empty()
        primary_map_slot.plotly_chart(
            course_speed_figure(
                rx, ry, mean_prof, SPEED_RED_TO_GREEN, "Ride 1",
                float(np.nanmin(mean_prof)), float(np.nanmax(mean_prof)),
                feature_positions, grid, L, corner_positions,
            ),
            use_container_width=True,
            config={"scrollZoom": True, "displayModeBar": True},
            key="ride1-comparison-map-initial",
        )
    with compare_map_cols[1].container(border=True):
        st.markdown("**Ride 2**")
        comparison_map_slot = st.empty()
        comparison_map_slot.markdown(
            '<div class="cx-comparison-placeholder">'
            'Upload a FIT file to compare</div>',
            unsafe_allow_html=True,
        )
        comparison_upload = st.file_uploader(
            "Upload second FIT file",
            type=["fit"],
            key="comparison_fit_upload",
            help="The confirmed course start/finish and feature areas will be reused.",
        )
if comparison_upload is not None:
    st.session_state.comparison_upload_data = comparison_upload.getvalue()
    st.session_state.comparison_upload_name = comparison_upload.name

comparison_upload_data = st.session_state.get("comparison_upload_data")
comparison_upload_name = st.session_state.get("comparison_upload_name")
if comparison_upload_data is not None:
    try:
        comparison_raw, _comparison_laps_fit = fu.parse_fit(comparison_upload_data)
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
            radius=st.session_state.gate_radius_m, min_gap_s=MIN_LAP_GAP_S,
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
                        f"Ride 1: {ride_1_name} · Ride 2: {comparison_upload_name}"
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
                        f"R1: {ride_1_name} · R2: {comparison_upload_name} · "
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
                        st.caption(f"R1: {ride_1_name} · R2: {comparison_upload_name}")
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
                    comparison_length, comparison_upload_name,
                )

# --- comparison maps ---
if comparison_map_data:
    (comparison_grid, comparison_rx, comparison_ry, comparison_mean_speed,
     comparison_mean_power, comparison_length, comparison_name) = comparison_map_data
    color_min = float(min(np.nanmin(mean_prof), np.nanmin(comparison_mean_speed)))
    color_max = float(max(np.nanmax(mean_prof), np.nanmax(comparison_mean_speed)))
    primary_map_slot.plotly_chart(
        course_speed_figure(
            rx, ry, mean_prof, SPEED_RED_TO_GREEN, "Ride 1",
            color_min, color_max, feature_positions, grid, L,
            corner_positions,
        ),
        use_container_width=True,
        config={"scrollZoom": True, "displayModeBar": True},
        key="ride1-comparison-map-shared-scale",
    )
    comparison_map_slot.plotly_chart(
        course_speed_figure(
            comparison_rx, comparison_ry, comparison_mean_speed,
            SPEED_RED_TO_GREEN, f"Ride 2 · {comparison_name}",
            color_min, color_max,
            [
                (name, start_pos / L * comparison_length,
                 end_pos / L * comparison_length)
                for name, start_pos, end_pos in feature_positions
            ],
            comparison_grid, comparison_length,
        ),
        use_container_width=True,
        config={"scrollZoom": True, "displayModeBar": True},
        key="ride2-comparison-map",
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
    st.header("Save this session")
    sess_date = pd.Timestamp(r["timestamp"].iloc[0]).date()
    st.caption(f"Ride date from FIT file: {sess_date.isoformat()}")
    sess_type = st.selectbox("Type", ["practice", "race"])
    sess_course = st.text_input("Course name for history", value=st.session_state.course_name)
    st.caption("Use the same course name each time to group corner trends together.")
    rest_threshold_s = 30
    if sess_type == "practice":
        rest_threshold_s = st.slider(
            "Split practice efforts after a stationary rest",
            min_value=15,
            max_value=180,
            value=30,
            step=5,
            format="%d seconds",
            help=(
                "A low-speed pause with less than 15 m of GPS movement for "
                "at least this long starts a new practice effort."
            ),
        )

    if st.button("Add to history"):
        primary_lap_summary = fu.lap_summary(laps)
        average_power = primary_lap_summary["avg_power"].mean()
        row = dict(
            date=str(sess_date), type=sess_type, course=sess_course,
            n_laps=len(laps) if sess_type == "race" else None,
            retained_ratio=round(ret["retained_ratio"], 3)
            if sess_type == "race" and np.isfinite(ret["retained_ratio"]) else None,
            power_after_corner_w=round(ret["power_after"], 1)
            if sess_type == "race" and np.isfinite(ret["power_after"]) else None,
            entry_mph=round(ret["entry_mph"], 2)
            if sess_type == "race" and np.isfinite(ret["entry_mph"]) else None,
            apex_mph=round(ret["apex_mph"], 2)
            if sess_type == "race" and np.isfinite(ret["apex_mph"]) else None,
            cadence_apex=round(ret["cadence_apex"], 1)
            if sess_type == "race" and np.isfinite(ret["cadence_apex"]) else None,
            avg_power_w=round(float(average_power), 1)
            if sess_type == "race" and np.isfinite(average_power) else None,
            avg_lap_s=round(float(primary_lap_summary["duration_s"].mean()), 1)
            if sess_type == "race" else None,
            avg_speed_mph=round(float(primary_lap_summary["avg_mph"].mean()), 2)
            if sess_type == "race" else None,
        )
        if sess_type == "race":
            for fr in feature_rows:
                row[f"{fr['feature_type']}_avg_time_s"] = fr["avg_time_s"]
                row[f"{fr['feature_type']}_avg_power_w"] = fr["avg_power_w"]
        if sess_type == "race":
            append_lap_history([
                {
                    "date": str(sess_date), "type": sess_type,
                    "course": sess_course, "ride_file": ride_1_name, **lap,
                }
                for lap in primary_lap_summary.to_dict(orient="records")
            ])
        corner_metadata = {
            "date": str(sess_date),
            "type": sess_type,
            "course": sess_course or "Unspecified course",
            "ride_file": ride_1_name,
        }
        if sess_type == "practice":
            efforts = split_practice_efforts(trimmed, rest_threshold_s)
            corner_rows = []
            for effort_number, effort in enumerate(efforts, start=1):
                effort_distance = float(
                    effort["distance"].iloc[-1] - effort["distance"].iloc[0]
                )
                effort_type = (
                    "practice effort"
                    if effort_distance >= L * 0.8 else "partial effort"
                )
                corner_rows.extend(corner_history_rows(
                    effort, corner_positions, grid, rx, ry, L,
                    corner_metadata, effort_number, effort_type,
                ))
        else:
            corner_rows = []
            for lap_number, lap in enumerate(laps, start=1):
                corner_rows.extend(corner_history_rows(
                    lap, corner_positions, grid, rx, ry, L,
                    corner_metadata, lap_number, "race lap", lap_number,
                ))
        if sess_type == "practice":
            for column, field, digits in (
                ("entry_mph", "entry_mph", 2),
                ("apex_mph", "apex_mph", 2),
                ("retained_ratio", "retained_ratio", 3),
                ("power_after_corner_w", "power_after_corner_w", 1),
            ):
                values = [
                    observation[field] for observation in corner_rows
                    if observation[field] is not None
                ]
                row[column] = round(float(np.mean(values)), digits) if values else None
        append_history(row)
        append_corner_history(corner_rows)
        st.success("Saved to history.")
        if corner_rows:
            st.caption(
                f"Saved {len(corner_rows)} corner observations for historical "
                f"corner speed and recovery-power trends."
            )
        elif corner_positions:
            st.info(
                "No corner observations were saved; the recorded effort did "
                "not cover any detected corner locations."
            )
