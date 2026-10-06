import os

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from history_utils import read_history_csv

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
    </style>
    """,
    unsafe_allow_html=True,
)

HISTORY_DIR = "history"
SESSION_HISTORY_PATH = os.path.join(HISTORY_DIR, "sessions.csv")
LAP_HISTORY_PATH = os.path.join(HISTORY_DIR, "lap_history.csv")
os.makedirs(HISTORY_DIR, exist_ok=True)


def load_csv(path):
    return read_history_csv(path)


def add_history_editor(frame, path, key_prefix, label, download_name):
    edited = st.data_editor(
        frame, key=f"{key_prefix}_editor", num_rows="dynamic",
        use_container_width=False,
    )
    save_col, download_col = st.columns(2)
    with save_col:
        if st.button(f"Save {label} edits", key=f"{key_prefix}_save"):
            edited.to_csv(path, index=False)
            st.success(f"{label} updated.")
            st.rerun()
    with download_col:
        st.download_button(
            f"Download {label} CSV",
            data=frame.to_csv(index=False),
            file_name=download_name,
            mime="text/csv",
            key=f"{key_prefix}_download",
        )


st.title("Ride history")
st.caption(
    "Progress graphs focus on cornering speed retention and power out of "
    "corners, which are more useful across different courses. Other ride "
    "metrics remain stored in the history tables."
)
session_history = load_csv(SESSION_HISTORY_PATH)
lap_history = load_csv(LAP_HISTORY_PATH)

with st.container(border=True):
    st.header("Season overview")
    latest_sessions = session_history.copy()
    if not latest_sessions.empty and "date" in latest_sessions:
        latest_sessions["_date"] = pd.to_datetime(
            latest_sessions["date"], errors="coerce",
        )
        latest_sessions = latest_sessions.sort_values(
            "_date", kind="stable", na_position="first",
        )
    latest = latest_sessions.iloc[-1] if not latest_sessions.empty else None

    def latest_metric(column, suffix="", multiplier=1):
        if latest is None or column not in latest.index:
            return "n/a"
        value = pd.to_numeric(pd.Series([latest[column]]), errors="coerce").iloc[0]
        return f"{value * multiplier:.0f}{suffix}" if pd.notna(value) else "n/a"

    total_laps = (
        pd.to_numeric(session_history["n_laps"], errors="coerce").sum()
        if "n_laps" in session_history else 0
    )
    overview_cols = st.columns(3)
    overview_cols[0].metric("Rides saved", len(session_history))
    overview_cols[1].metric(
        "Latest speed retained through corners",
        latest_metric("retained_ratio", "%", 100),
    )
    overview_cols[2].metric(
        "Latest power out of corners",
        latest_metric("power_after_corner_w", " W"),
    )
    st.caption(f"{int(total_laps)} laps saved · comparison rides are not included.")

with st.container(border=True):
    st.header("Progress graphs")
    if session_history.empty:
        st.info("No session history yet. Add a ride from the Analysis page.")
    else:
        chart_history = session_history.copy()
        if "date" in chart_history:
            chart_history["date"] = pd.to_datetime(
                chart_history["date"], errors="coerce",
            )
            chart_history = (
                chart_history.dropna(subset=["date"])
                .sort_values("date", kind="stable")
                .reset_index(drop=True)
            )
            chart_history["ride_number"] = range(1, len(chart_history) + 1)
            same_day_order = chart_history.groupby(
                chart_history["date"].dt.normalize(),
            ).cumcount()
            chart_history["ride_label"] = chart_history["date"].dt.strftime("%b %d")
            chart_history.loc[same_day_order > 0, "ride_label"] += (
                " (#" + (same_day_order[same_day_order > 0] + 1).astype(str) + ")"
            )
        else:
            chart_history = pd.DataFrame()

        if chart_history.empty:
            st.info("No valid ride dates are available to plot.")
        else:
            specs = [
                ("retained_ratio", "Speed retained through corners (%)", "#16803c", 100),
                ("power_after_corner_w", "Power out of corners (W)", "#ef8a17", 1),
            ]
            columns = st.columns(2)
            rendered = 0
            for metric, title, color, multiplier in specs:
                if metric not in chart_history:
                    continue
                chart_history[metric] = pd.to_numeric(
                    chart_history[metric], errors="coerce",
                )
                series = chart_history.dropna(subset=[metric])
                if series.empty:
                    continue
                values = series[metric] * multiplier
                course = (
                    series["course"].fillna("").astype(str)
                    if "course" in series else pd.Series("", index=series.index)
                )
                ride_type = (
                    series["type"].fillna("").astype(str)
                    if "type" in series else pd.Series("", index=series.index)
                )
                chart = go.Figure(go.Scatter(
                    x=series["ride_number"], y=values, mode="markers+lines",
                    marker=dict(color=color, size=8),
                    line=dict(color=color, width=2), name=title,
                    customdata=pd.concat(
                        [series["date"].dt.strftime("%Y-%m-%d"), course, ride_type],
                        axis=1,
                    ).to_numpy(),
                    hovertemplate=(
                        "Ride %{x} (%{customdata[0]})<br>%{y:.1f}"
                        "<br>Course: %{customdata[1]}"
                        "<br>Ride type: %{customdata[2]}<extra></extra>"
                    ),
                ))
                chart.update_layout(
                    height=300, title=title, xaxis_title="Ride order (date)",
                    yaxis_title=title, margin=dict(l=10, r=10, t=45, b=10),
                )
                chart.update_xaxes(
                    tickmode="array",
                    tickvals=series["ride_number"],
                    ticktext=series["ride_label"],
                )
                columns[rendered % 2].plotly_chart(
                    chart, use_container_width=True,
                )
                rendered += 1
            if not rendered:
                st.info("No numeric session metrics are available to graph.")

with st.container(border=True):
    st.header("Session history")
    if session_history.empty:
        st.info("No saved sessions yet.")
    else:
        add_history_editor(
            session_history, SESSION_HISTORY_PATH, "session_history",
            "session history", "cx_session_history.csv",
        )

with st.container(border=True):
    st.header("Per-lap history")
    if lap_history.empty:
        st.info("No saved lap records yet.")
    else:
        add_history_editor(
            lap_history, LAP_HISTORY_PATH, "lap_history",
            "per-lap history", "cx_lap_history.csv",
        )

with st.container(border=True):
    st.header("Restore or delete history")
    restore_col, delete_col = st.columns(2)
    with restore_col:
        st.caption("Restore replaces the corresponding local history file.")
        session_upload = st.file_uploader(
            "Restore session summary CSV", type=["csv"], key="restore_session_csv",
        )
        if session_upload is not None and st.button(
            "Restore session summary", key="restore_session_button",
        ):
            restored = pd.read_csv(session_upload)
            restored.to_csv(SESSION_HISTORY_PATH, index=False)
            st.success(f"Restored {len(restored)} session records.")
            st.rerun()
        lap_upload = st.file_uploader(
            "Restore per-lap CSV", type=["csv"], key="restore_lap_csv",
        )
        if lap_upload is not None and st.button(
            "Restore per-lap history", key="restore_laps_button",
        ):
            restored = pd.read_csv(lap_upload)
            restored.to_csv(LAP_HISTORY_PATH, index=False)
            st.success(f"Restored {len(restored)} per-lap records.")
            st.rerun()

    with delete_col:
        st.caption("Deletion permanently removes the selected CSV. Download a backup first.")
        confirm_session_delete = st.checkbox(
            "Confirm deleting sessions.csv", key="confirm_sessions_delete",
        )
        if st.button(
            "Delete session history",
            key="delete_sessions",
            disabled=not confirm_session_delete or not os.path.exists(SESSION_HISTORY_PATH),
        ):
            os.remove(SESSION_HISTORY_PATH)
            st.success("Deleted session history.")
            st.rerun()
        confirm_lap_delete = st.checkbox(
            "Confirm deleting lap_history.csv", key="confirm_laps_delete",
        )
        if st.button(
            "Delete per-lap history",
            key="delete_laps",
            disabled=not confirm_lap_delete or not os.path.exists(LAP_HISTORY_PATH),
        ):
            os.remove(LAP_HISTORY_PATH)
            st.success("Deleted per-lap history.")
            st.rerun()
