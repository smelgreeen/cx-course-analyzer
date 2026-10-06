# CX Course Analyzer

A small Streamlit app for analyzing cyclocross (or any lap-based) `.fit`
files: trim out the ride to/from the course, click to mark the
start/finish line and any features (barrier, flyover, hairpin, chicane,
...), and get back:

- Clean lap splitting based on your own marked start/finish line
- Feature-area timing grouped by feature type, with feature segments
  excluded from cornering-retention evaluation
- A course-independent "cornering retention" number (how much entry
  speed you keep through a corner), so you can compare sessions even
  when the course itself is different
- A course map colored by average speed
- A speed-vs-distance chart with your marked features labeled
- A simple session history log so you can track the retention number
  over time across practices and races, plus per-lap ride metrics

## Running it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL it prints (usually `http://localhost:8501`).
The sidebar navigation switches between **Analysis** and **Ride history**.

## How to use it

1. **Upload a `.fit` file** in the sidebar.
2. **Trim the ride** by dragging the start and stop handles below the
   route. Blue **S** and red **E** dots track the endpoints as the route
   redraws in the browser. Confirm the selected range to continue.
3. **Mark and confirm the lap start/finish point** by clicking the
   course route where each lap crosses the timing line.
4. Lap detection uses fixed settings for now: a 12 m gate radius and a
   20 second minimum gap between crossings.
5. **Mark feature areas** on the single reference-lap map (not the full
   multi-lap recording). Enter a feature type (for example, "Barrier"),
   then click its start and end in the direction of travel. Short
   segments stay local to that reference lap. Use the same type for
   comparable features; click **Confirm** to save each area, then
   **Add new feature** to mark another. If the name is blank, features receive
   the next available numbered name. Their times are grouped by type
   and excluded from cornering retention.
6. **Save the course** (optional) so you don't have to re-mark it next
   time you analyze a ride from the same spot. You can also download
   the course marking as a small `.json` file and re-upload it later,
   which is the more reliable option once this is hosted somewhere
   with non-persistent storage (see below).
7. Scroll down for the lap table, feature times, the retention number,
   the course map, and the speed chart.
8. **Add the session to history** if you want to track trends over
   time. Download the history CSV periodically if you're using the
   hosted version.
9. To compare another race on the same course, upload its `.fit` file
   under **Compare another race on this course**. The confirmed timing
   point and feature areas are reused; lap times, cornering retention,
   average power, and feature times are shown side by side with Ride 2 −
   Ride 1 differences. Course downloads include their GPS origin so
   markings can be aligned when loaded for a later ride.
10. **Add the main ride to history** to save its summary and individual
    lap duration, speed, power, and cadence for season/career tracking.
    The comparison ride is intentionally not saved. Download the
    `history\\sessions.csv` and `history\\lap_history.csv` files as
    backups; hosted Streamlit disk storage may not persist between restarts.
    Open **Ride history** from the sidebar to view cross-course progress
    graphs focused on cornering speed retention and power during the
    8-second recovery after corner apexes. Other metrics remain stored in
    the editable history tables. You can restore a CSV backup or explicitly
    confirm deletion of either local history file.
    The **Add to history** control remains at the bottom of the analysis
    page.

Ride-comparison tables place matching Ride 1 and Ride 2 metrics beside
each other and use compact headers to reduce unnecessary table width.
Ride 1 and Ride 2 columns use subtle indigo and red tints, while
differences use a neutral slate tint. Dark text and compact table spacing
keep the values easy to scan. The interface uses the supplied indigo,
red, olive, slate-blue, and near-black colors as restrained accents, with
lighter surface tints and darker chart variants where accessibility
requires them.

The course-marking map and analysis maps use smooth speed-colored route
lines instead of dots. The comparison maps use distinct speed palettes
with a shared speed range. Speed and power profile comparisons
are shown in separate side-by-side charts, with Ride 1 and Ride 2 using
distinct colors on the same metric scale. Power is also summarized as
lap and feature average watts and corner recovery power when the FIT data
includes power.

The Ride 1/Ride 2 graph colors use the original green-red and
blue-purple palettes. Use the **Ride history** link in the sidebar to
open history, and the **Analysis** link on that page to return.

### Lap detection

Lap detection currently uses fixed values: the gate radius is 12 m from
the start/finish marker, and crossings must be at least 20 seconds apart.

Feature segments are recorded as course-relative start/end distances on
the reference lap. Each interval is timed on every lap and measurements
are grouped by the feature type you entered.

## Deploying for free (Streamlit Community Cloud)

1. Push this folder to a **public** GitHub repository.
2. Go to <https://share.streamlit.io>, sign in with GitHub, and click
   "New app".
3. Point it at your repo, branch, and `app.py`.
4. Deploy. You'll get a shareable `*.streamlit.app` URL.

**Important caveat about hosted use:** free hosting tiers (Streamlit
Community Cloud included) don't guarantee the app's local disk
persists between restarts or redeploys. The "Save course" and "Add to
history" buttons write to local files (`courses/` and `history/`),
which is fine for running it on your own machine, but on the hosted
version that data can disappear if the app goes to sleep and restarts.
Use the **download buttons** (course `.json`, history `.csv`) to keep
your own copies, and re-upload them when you come back. If this grows
into something more people lean on regularly, swapping in a small
hosted database (e.g. a free Postgres instance on Render or Railway)
is the natural next step so saved data stops depending on the app's
local disk at all.

**Privacy note:** anyone who uses a version you host is uploading
their own GPS ride data. Nothing in this app sends that data anywhere
outside the app itself, but if you share the link publicly it's worth
deciding up front whether you want that to be a shared/public space or
something closer to invite-only, since there's no per-user login or
data separation in this version.

## Project layout

```
app.py             Streamlit page navigation
analysis_page.py   Ride analysis UI
fit_utils.py        Parsing + analysis logic (no Streamlit dependency,
                     reusable/testable on its own)
route_map.py        Python wrapper for the interactive route component
route_map_frontend/ Browser-side route rendering and interaction
pages/History.py    Sidebar history dashboard
history_utils.py    History CSV loading and append helpers
.streamlit/         Streamlit app configuration
requirements.txt
courses/             Saved course markings (local use; see caveat above)
history/             Saved session history (local use; see caveat above)
```
