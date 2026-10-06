# CX Course Analyzer

A small Streamlit app for analyzing cyclocross (or any lap-based) `.fit`
files: trim out the ride to/from the course, click to mark the
start/finish line and any features (barrier, flyover, hairpin, chicane,
...), and get back:

- Clean lap splitting based on your own marked start/finish line
- Per-feature consistency stats (average speed, lap-to-lap variability)
- A course-independent "cornering retention" number (how much entry
  speed you keep through a corner), so you can compare sessions even
  when the course itself is different
- A course map colored by average speed
- A speed-vs-distance chart with your marked features labeled
- A simple session history log so you can track the retention number
  over time across practices and races

## Running it locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL it prints (usually `http://localhost:8501`).

## How to use it

1. **Upload a `.fit` file** in the sidebar.
2. **Trim the time range** to cut out the ride there/back and any long
   stops. The map updates live as you drag the slider.
3. **Mark the start/finish line**: with "Start/finish" selected, click
   the spot on the map where your lap timer should reset.
4. **Mark features**: switch to "A feature", type a name (e.g.
   "Barrier"), and click its spot on the map. Repeat for each feature
   you care about.
5. **Save the course** (optional) so you don't have to re-mark it next
   time you analyze a ride from the same spot. You can also download
   the course marking as a small `.json` file and re-upload it later,
   which is the more reliable option once this is hosted somewhere
   with non-persistent storage (see below).
6. Scroll down for the lap table, feature stats, the retention number,
   the course map, and the speed chart.
7. **Add the session to history** if you want to track trends over
   time. Download the history CSV periodically if you're using the
   hosted version.

### Tuning knobs

- **Gate radius**: how close you need to pass your marked start/finish
  point to count as crossing it. Widen it if laps aren't being
  detected; narrow it if nearby parts of the course are getting
  mistaken for the line.
- **Minimum time between laps**: raise this if a single real lap is
  getting split into two because the course passes near the
  start/finish line partway through.
- **Feature window**: how far around your marked point (in meters) to
  search for that feature's slowest moment. If a feature's numbers
  look noisy, GPS drift between laps is probably letting the window
  miss the true dip on some laps — try widening it.

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
app.py             Streamlit UI
fit_utils.py        Parsing + analysis logic (no Streamlit dependency,
                     reusable/testable on its own)
requirements.txt
courses/             Saved course markings (local use; see caveat above)
history/             Saved session history (local use; see caveat above)
```
