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

1. On the Analysis landing page, choose **Upload .fit file** in the
   center of the placeholder course map. The dashboard switches into
   the ride workflow after the file loads.
2. Use the main map in the Analysis page for each setup step: trim the
   ride, set and confirm the lap start/finish, then mark feature starts
   and ends. The same map area changes to show the current step, so
   zooming/panning state and route context stay together.
3. Set the lap start/finish point. Zoom in if course sections are close,
   then adjust the detection radius (2–20 m; default 6 m) to avoid
   selecting a nearby section. Lap detection also requires a 20 second
   minimum gap between crossings. After laps are detected, mark feature
   areas on the single reference lap (not the full multi-lap recording):
   enter a type (for example, "Barrier"), click start and end in the
   direction of travel, and select **Confirm**. Reuse types for comparable
   features; blank names are numbered automatically. Feature intervals
   are timed by type and excluded from cornering/corner-speed detection.
4. After setup, the main map shows Ride 1's speed-colored course and the
   panel beside it contains Ride 1 metrics and lap data only, including
   numbered corner tags that match the Ride 1 lap-by-corner speed table.
   Scroll down for comparison upload, paired maps, comparison tables,
   charts, and the written Ride 1/Ride 2 analysis.
5. **Add the main ride to history** at the bottom of Analysis to track
   trends over time. Download the history CSV periodically if you're
   using the hosted version. Ride History shows an overview plus
   cross-course graphs for corner retention and power after corners.
6. To compare another race on the same course, upload its `.fit` file
   in the Ride 2 card below the main map. The confirmed timing
   point and feature areas are reused; lap times, cornering retention,
   average power, and feature times are shown side by side with Ride 2 −
   Ride 1 differences.
   The comparison ride is not saved. Ride history also stores per-lap
   speed, power, duration, and cadence; those values remain editable and
   downloadable even though the progress graphs focus on retention and
   power out of corners. You can restore a CSV backup or explicitly
   confirm deletion of either local history file.

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
