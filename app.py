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
from streamlit_plotly_events import plotly_events

import fit_utils as fu

st.set_page_config(page_title="CX Course Analyzer", layout="wide")

COURSES_DIR = "courses"
HISTORY_DIR = "history"
os.makedirs(COURSES_DIR, exist_ok=True)
os.makedirs(HISTORY_DIR, exist_ok=True)


# --------------------------------------------------------------------------
# Session state setup
# --------------------------------------------------------------------------

def init_state():
    defaults = dict(
        raw_df=None,
        lat0=None, lon0=None,
        trimmed_df=None,
        start_finish=None,       # (x, y)
        features=[],             # list of dicts: name, x, y
        add_mode="start_finish",  # or "feature"
        next_feature_name="",
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


def save_course(name, start_finish, features):
    path = os.path.join(COURSES_DIR, f"{name}.json")
    with open(path, "w") as f:
        json.dump(dict(start_finish=start_finish, features=features), f, indent=2)


def load_course(name):
    path = os.path.join(COURSES_DIR, f"{name}.json")
    with open(path) as f:
        return json.load(f)


def history_path():
    return os.path.join(HISTORY_DIR, "sessions.csv")


def append_history(row: dict):
    path = history_path()
    df = pd.DataFrame([row])
    if os.path.exists(path):
        df.to_csv(path, mode="a", header=False, index=False)
    else:
        df.to_csv(path, index=False)


def load_history() -> pd.DataFrame:
    path = history_path()
    if os.path.exists(path):
        return pd.read_csv(path)
    return pd.DataFrame()


def track_figure(df, start_finish=None, features=None, color_col="t",
                  colorbar_title="elapsed time (s)", colorscale="Viridis",
                  clim=None):
    fig = go.Figure()
    fig.add_trace(go.Scattergl(
        x=df["x"], y=df["y"], mode="markers",
        marker=dict(
            size=5, color=df[color_col], colorscale=colorscale,
            colorbar=dict(title=colorbar_title),
            cmin=clim[0] if clim else None, cmax=clim[1] if clim else None,
        ),
        name="track", hoverinfo="skip",
    ))
    if start_finish:
        fig.add_trace(go.Scatter(
            x=[start_finish[0]], y=[start_finish[1]], mode="markers+text",
            marker=dict(size=16, color="black", symbol="square"),
            text=["start/finish"], textposition="top center", name="start/finish",
        ))
    if features:
        for ft in features:
            fig.add_trace(go.Scatter(
                x=[ft["x"]], y=[ft["y"]], mode="markers+text",
                marker=dict(size=14, color="red", symbol="circle-open", line=dict(width=3)),
                text=[ft["name"]], textposition="top center", name=ft["name"],
            ))
    fig.update_layout(
        height=650, xaxis_title="meters (local)", yaxis_title="meters (local)",
        yaxis=dict(scaleanchor="x", scaleratio=1),
        margin=dict(l=10, r=10, t=10, b=10),
        clickmode="event+select",
    )
    return fig


def nearest_row(df, click_x, click_y):
    dd = np.hypot(df["x"] - click_x, df["y"] - click_y)
    return df.loc[dd.idxmin()]


# --------------------------------------------------------------------------
# Sidebar: file upload
# --------------------------------------------------------------------------

st.sidebar.title("CX Course Analyzer")
uploaded = st.sidebar.file_uploader("Upload a .fit file", type=["fit"])

if uploaded is not None and st.session_state.raw_df is None:
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

st.header("1. Trim to the course")
st.caption("Drag to exclude the ride there / ride home, or any stopped time you don't want counted.")

t_min, t_max = float(r["t"].min()), float(r["t"].max())
t0, t1 = st.slider(
    "Time range (seconds into the recording)",
    min_value=t_min, max_value=t_max, value=(t_min, t_max), step=1.0,
)
trimmed = r[(r["t"] >= t0) & (r["t"] <= t1)].reset_index(drop=True)
st.session_state.trimmed_df = trimmed

fig = track_figure(trimmed)
st.plotly_chart(fig, use_container_width=True)
st.caption(f"{len(trimmed)} GPS points, {(t1 - t0):.0f}s, "
           f"{(trimmed['distance'].iloc[-1] - trimmed['distance'].iloc[0]):.0f} m")

# --------------------------------------------------------------------------
# Step 2: mark start/finish and features (or load a saved course)
# --------------------------------------------------------------------------

st.header("2. Mark the start/finish line and features")

saved = list_saved_courses()
colA, colB = st.columns([2, 1])
with colB:
    if saved:
        pick = st.selectbox("Load a saved course", ["(none)"] + saved)
        if pick != "(none)" and st.button("Load"):
            c = load_course(pick)
            st.session_state.start_finish = tuple(c["start_finish"])
            st.session_state.features = c["features"]
            st.session_state.course_name = pick
            st.rerun()
    course_upload = st.file_uploader("...or import a course file", type=["json"], key="course_upload")
    if course_upload is not None:
        c = json.load(course_upload)
        st.session_state.start_finish = tuple(c["start_finish"])
        st.session_state.features = c["features"]
        st.info("Course loaded from file. Click elsewhere to continue.")

with colA:
    st.radio(
        "Clicking the map below adds:",
        ["start_finish", "feature"],
        format_func=lambda v: "Start/finish (one point)" if v == "start_finish" else "A feature",
        key="add_mode", horizontal=True,
    )
    if st.session_state.add_mode == "feature":
        st.session_state.next_feature_name = st.text_input(
            "Name for the next feature you click", value=st.session_state.next_feature_name,
            placeholder="e.g. Barrier, Flyover, Hairpin",
        )

mark_fig = track_figure(
    trimmed, start_finish=st.session_state.start_finish, features=st.session_state.features,
)
clicked = plotly_events(mark_fig, click_event=True, hover_event=False, select_event=False,
                         override_height=650, key="mark_map")

if clicked:
    cx, cy = clicked[0]["x"], clicked[0]["y"]
    if st.session_state.add_mode == "start_finish":
        st.session_state.start_finish = (cx, cy)
    else:
        name = st.session_state.next_feature_name.strip()
        if name:
            st.session_state.features.append(dict(name=name, x=cx, y=cy))
            st.session_state.next_feature_name = ""
        else:
            st.warning("Type a name for this feature before clicking the map.")
    st.rerun()

if st.session_state.features:
    st.write("Marked features:")
    for i, ft in enumerate(st.session_state.features):
        c1, c2 = st.columns([5, 1])
        c1.write(f"**{ft['name']}**")
        if c2.button("remove", key=f"rm_{i}"):
            st.session_state.features.pop(i)
            st.rerun()

save_col1, save_col2 = st.columns([3, 1])
with save_col1:
    st.session_state.course_name = st.text_input(
        "Course name (to save this marking for next time)",
        value=st.session_state.course_name, placeholder="e.g. Humboldt Park loop",
    )
with save_col2:
    st.write("")
    st.write("")
    if st.button("Save course"):
        if st.session_state.course_name and st.session_state.start_finish:
            save_course(st.session_state.course_name, st.session_state.start_finish,
                        st.session_state.features)
            st.success(f"Saved as '{st.session_state.course_name}'.")
        else:
            st.warning("Name the course and mark a start/finish point first.")

if st.session_state.start_finish:
    st.download_button(
        "Download this course marking as a file",
        data=json.dumps(dict(start_finish=st.session_state.start_finish,
                              features=st.session_state.features), indent=2),
        file_name=f"{st.session_state.course_name or 'course'}.json",
        mime="application/json",
        help="Keep this file yourself if you're using the hosted version — "
             "free hosting doesn't guarantee saved courses stick around between visits.",
    )

if not st.session_state.start_finish:
    st.info("Click the map above to mark the start/finish line to continue.")
    st.stop()

# --------------------------------------------------------------------------
# Step 3: run the analysis
# --------------------------------------------------------------------------

st.header("3. Analysis")

gate_radius = st.slider("Start/finish gate radius (m)", 5, 30, 12)
min_gap = st.slider("Minimum time between laps (s), to avoid double-counting "
                     "a start/finish that sits near another part of the course", 5, 60, 20)
window_m = st.slider("Feature window (m) — how far around your marked point "
                      "to look for the slowest moment of that feature", 5, 40, 20)

gx, gy = st.session_state.start_finish
passes = fu.find_gate_passes(trimmed, gx, gy, radius=gate_radius, min_gap_s=min_gap)

if len(passes) < 3:
    st.error(
        f"Only found {len(passes)} crossing(s) of the start/finish point in this "
        "time range. Try widening the gate radius, or check that the time range "
        "above actually covers multiple laps."
    )
    st.stop()

laps = fu.split_laps(trimmed, passes)
laps = fu.filter_short_laps(laps)

if len(laps) < 2:
    st.error("Not enough clean laps found. Try adjusting the gate radius or the time range.")
    st.stop()

st.subheader(f"{len(laps)} laps found")
st.dataframe(fu.lap_summary(laps), use_container_width=True)

grid, rx, ry, L = fu.build_reference_path(laps)
profs = fu.all_profiles(laps, grid, "mph")
st.session_state.laps, st.session_state.grid = laps, grid
st.session_state.rx, st.session_state.ry, st.session_state.L = rx, ry, L
st.session_state.profs = profs

st.caption(f"Course length (reference lap): {L:.0f} m")

# --- feature stats ---
feature_rows = []
feat_positions = []
for ft in st.session_state.features:
    pos = fu.project_point_to_course(ft["x"], ft["y"], grid, rx, ry)
    stat = fu.feature_stats(laps, grid, profs, pos, ft["name"], window_m=window_m)
    feat_positions.append((ft["name"], pos))
    feature_rows.append(dict(
        feature=ft["name"], course_pos_m=round(pos, 0),
        avg_mph=round(stat.mean_mph, 1), std_mph=round(stat.std_mph, 2),
        cv_pct=round(stat.cv_pct, 1), avg_power=round(stat.mean_power, 0) if stat.mean_power else None,
    ))

if feature_rows:
    st.subheader("Feature consistency")
    st.caption(
        "avg/std/CV are of each lap's *slowest* speed within the window around your "
        "marked point. A high CV% means your speed through that feature varies a lot "
        "lap to lap, a sign of inconsistent technique rather than just a hard feature."
    )
    st.dataframe(pd.DataFrame(feature_rows), use_container_width=True)

# --- course-independent cornering number ---
st.subheader("Cornering retention (comparable across different courses)")
ret = fu.corner_retention(laps)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Speed retained through corners", f"{ret['retained_ratio']*100:.0f}%" if ret["retained_ratio"] == ret["retained_ratio"] else "n/a")
c2.metric("Avg entry speed", f"{ret['entry_mph']:.1f} mph")
c3.metric("Avg apex speed", f"{ret['apex_mph']:.1f} mph")
c4.metric("Cadence at apex", f"{ret['cadence_apex']:.0f} rpm")
st.caption(
    "'Retained' = apex speed ÷ entry speed, averaged over every slow point found "
    "on every lap. Because it's a ratio rather than a raw speed, it travels better "
    "across different courses than mph does, so you can compare this number "
    "session to session even when the course changes."
)

# --- course map colored by speed ---
st.subheader("Course map, colored by average speed")
mean_prof = profs.mean(0)
mfig = go.Figure()
mfig.add_trace(go.Scatter(
    x=rx, y=ry, mode="markers",
    marker=dict(size=8, color=mean_prof, colorscale="RdYlGn_r",
                colorbar=dict(title="avg mph")),
))
for name, pos in feat_positions:
    j = int(np.argmin(np.abs(grid - pos)))
    mfig.add_trace(go.Scatter(
        x=[rx[j]], y=[ry[j]], mode="markers+text",
        marker=dict(size=16, color="black", symbol="circle-open", line=dict(width=3)),
        text=[name], textposition="top center",
    ))
mfig.update_layout(height=650, yaxis=dict(scaleanchor="x", scaleratio=1),
                    margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
st.plotly_chart(mfig, use_container_width=True)

# --- speed vs distance chart ---
st.subheader("Speed around the lap")
sfig = go.Figure()
sfig.add_trace(go.Scatter(x=grid, y=mean_prof, mode="lines", name="avg speed"))
for name, pos in feat_positions:
    sfig.add_vline(x=pos, line_dash="dot", line_color="gray",
                    annotation_text=name, annotation_position="top")
sfig.update_layout(height=400, xaxis_title="meters into lap", yaxis_title="speed (mph)",
                    margin=dict(l=10, r=10, t=10, b=10))
st.plotly_chart(sfig, use_container_width=True)

# --------------------------------------------------------------------------
# Step 4: save this session to history for trend tracking
# --------------------------------------------------------------------------

st.header("4. Save this session")
sess_date = st.date_input("Date of this ride", value=datetime.now().date())
sess_type = st.selectbox("Type", ["practice", "race"])
sess_course = st.text_input("Course name for history", value=st.session_state.course_name)

if st.button("Add to history"):
    row = dict(
        date=str(sess_date), type=sess_type, course=sess_course,
        n_laps=len(laps), retained_ratio=round(ret["retained_ratio"], 3),
        entry_mph=round(ret["entry_mph"], 2), apex_mph=round(ret["apex_mph"], 2),
        cadence_apex=round(ret["cadence_apex"], 1),
    )
    for fr in feature_rows:
        row[f"{fr['feature']}_avg_mph"] = fr["avg_mph"]
        row[f"{fr['feature']}_cv_pct"] = fr["cv_pct"]
    append_history(row)
    st.success("Saved to history.")

hist = load_history()
if not hist.empty:
    st.subheader("Session history")
    st.dataframe(hist, use_container_width=True)
    st.download_button(
        "Download full history as CSV", data=hist.to_csv(index=False),
        file_name="cx_session_history.csv", mime="text/csv",
        help="Keep a copy yourself — free hosting doesn't guarantee this sticks "
             "around between visits. You can re-upload it below next time.",
    )
    hist_upload = st.file_uploader("...or restore history from a CSV you saved earlier",
                                    type=["csv"], key="hist_upload")
    if hist_upload is not None:
        restored = pd.read_csv(hist_upload)
        restored.to_csv(history_path(), index=False)
        st.success("History restored. Refresh to see it merged in above.")
    if hist["retained_ratio"].notna().sum() > 1:
        tfig = go.Figure()
        tfig.add_trace(go.Scatter(x=hist["date"], y=hist["retained_ratio"], mode="markers+lines"))
        tfig.update_layout(height=350, yaxis_title="retained ratio",
                            margin=dict(l=10, r=10, t=10, b=10))
        st.subheader("Cornering retention over time")
        st.plotly_chart(tfig, use_container_width=True)
