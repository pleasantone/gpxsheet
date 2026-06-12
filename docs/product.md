# GPXSheet Product Design Specification

### Version 1.0

### Motorcycle Sport-Touring Route Awareness Generator

---

# Executive Summary

GPXSheet is a Python-based command-line application and reusable library that converts GPX routes into highly glanceable, map-centric motorcycle navigation PDFs optimized for tank-bag use.

Unlike rally roadbooks, GPS turn-by-turn navigation, or printed map exports, GPXSheet is designed specifically for motorcycle sport-touring riders traveling long distances on back roads where:

* Navigation decisions are infrequent
* Situational awareness is more important than detailed navigation
* Riders need to understand where they are in the route at a glance
* Printed navigation remains valuable as a primary or backup navigation tool

Examples include roads such as:

* Skaggs Springs Road
* Mines Road
* CA-36
* Sierra Foothill routes
* Trinity County routes
* Backcountry paved touring routes
* Mixed-surface touring routes

The product's primary goal is:

> Allow a rider to glance at a tank-bag navigation sheet for less than one second and immediately understand:
>
> * What road they are on
> * What their next navigation decision is
> * How far away it is
> * What comes after that
> * Where they are within the overall route

---

# Design Philosophy

## Not a Rally Roadbook

GPXSheet is intentionally not optimized for:

* Rally navigation
* Tulip diagrams
* Off-road rally racing
* Constant navigation prompts

Those use cases are already well served by existing roadbook software.

---

## Not a GPS Replacement

GPXSheet is not intended to replace:

* Garmin
* CarPlay
* Android Auto
* Smartphone navigation

Instead, it provides:

* Route context
* Route awareness
* Backup navigation
* Enhanced situational understanding

---

## Primary Design Principle

The rider should never need to ask:

* Am I still on the route?
* What road am I on?
* What is my next decision?
* How far away is it?
* How much farther is the ride?

---

# Supported Inputs

## Initial Support

### GPX Track

```xml
<trk>
```

### GPX Route

```xml
<rte>
```

### GPX Track + Waypoints

```xml
<trk>
<wpt>
```

### GPX Route (Garmin BaseCamp / Trip Planner)

```xml
<rte> + gpxx:RoutePointExtension/gpxx:rpt + trp:ViaPoint
```

A BaseCamp route stores its real road-snapped geometry inside per-`<rtept>`
`gpxx:RoutePointExtension`/`gpxx:rpt` extensions (not the sparse `<rtept>` list),
and tags announced stops with `trp:ViaPoint`. The loader reconstructs the dense
track from the `rpt` children and lifts via points to waypoints (shaping points
excluded); optional via arrival/departure times are kept as display-only metadata.
See [basecamp-routes.md](basecamp-routes.md).

---

## Future Support

* Kurviger exports
* Furkot exports
* REVER exports
* Combined route/track files

---

# System Architecture

```text
GPX
 ↓
Geometry Cleanup
 ↓
OSM Enrichment
 ↓
Decision Point Detection
 ↓
Reassurance Marker Detection
 ↓
Fuel Analysis
 ↓
Route Simplification
 ↓
Route Graph Construction
 ↓
Schematic Layout Engine
 ↓
PDF Rendering
```

---

# Product Components

## Command Line Interface

```bash
gpxsheet route.gpx
```

Default behavior:

```bash
gpxsheet route.gpx \
  --profile sport-touring
```

Advanced example:

```bash
gpxsheet route.gpx \
  --profile sport-touring \
  --fuel-range 180 \
  --reassurance-interval 15 \
  --output route.pdf
```

---

## Library API

```python
import gpxsheet

# Three entry points mirror the web API (render / analyze / validate).
gpxsheet.render(
    "route.gpx",
    "route.pdf",
    layout="portrait",  # portrait | landscape | preview | strip
    format="pdf",       # pdf | png
    profile="sport-touring",
    fuel_range=180,
)
route = gpxsheet.analyze("route.gpx", fuel_range=180)
report = gpxsheet.validate("route.gpx", fuel_range=180)
```

A fourth output, the **route table**, renders a markdown/HTML table of waypoints,
distances, fuel/lunch markers and ETAs natively from the `analyze` pipeline, so it
inherits OSM enrichment (auto-discovered fuel, road-snapped distance). OSM is on by
default with a `--no-osm` fast offline path; ETAs need `--departure`. See
`src/gpxsheet/routetable.py` (plus `waypoints.py` for stop classification and
`timing.py` for ETA/sun) and the `gpxsheet table` CLI command.

---

## Web Service (built)

Implemented as a FastAPI app (the `service` extra). Each operation is an async job
created by a typed POST — `/v1/render` (a map), `/v1/table` (a route table,
HTML/markdown), `/v1/analyze` and `/v1/validate` (JSON reports) — with the GPX and
parameters as multipart form fields. Submit
returns a job (`202` + `Location`, or `200` if already cached); poll
`GET /v1/jobs/{id}` and fetch `GET /v1/jobs/{id}/result`. See the **Web service**
entry under [What's built](#whats-built) for the full as-built description.

---

# User Profiles

## Minimalist

Purpose:

Maximum simplicity.

Includes:

* Critical navigation decisions only

Excludes:

* Fuel information
* Reassurance markers
* Supplemental annotations

---

## Sport-Touring (Default)

Primary target profile.

Includes:

* Critical navigation decisions
* Fuel opportunities
* Reassurance markers
* Town labels
* Road name ribbon

Suppresses:

* Navigation noise
* Unnecessary intersections

---

## Rally

Includes:

* All sport-touring features
* Confirmation points
* Additional route annotations
* More frequent markers

---

# OSM Enrichment

OpenStreetMap data is used to enrich the GPX.

Collected information:

* Road names
* Road classifications
* Intersections
* Junction geometry
* Towns
* Fuel stations
* Geographic features

---

# Decision Point Engine

The Decision Point Engine is the core intelligence layer.

---

## Significant Intersections

Significance is determined by three rule sets.

### Rule Set 1: Road Name Changes

Example:

```text
Skaggs Springs Rd
→ Annapolis Rd
```

Even if physically straight.

---

### Rule Set 2: Major Road Crossings

Examples:

* State highways
* County highways
* Major collectors
* Arterial roads

---

### Rule Set 3: Route Ambiguity

Examples:

```text
Y intersection
```

```text
T intersection
```

```text
Fork
```

```text
Roundabouts and Rotarys
```

Situations where a rider could easily choose the wrong path.

---

# Significance Scoring

Every route event receives a score.

Example scoring:

| Event                  | Score |
| ---------------------- | ----- |
| Road name change       | +40   |
| State highway junction | +50   |
| County road junction   | +30   |
| Roundabout intersection| +60   |
| Y intersection         | +60   |
| T intersection         | +60   |
| Fuel opportunity       | +20   |
| Town center            | +20   |

Profile settings determine display thresholds.

---

# Decision Point Types

## Critical Turn

Examples:

```text
Right on Skaggs Springs Rd
```

```text
Left on CA-1
```

```text
Continue onto Mines Rd
```

Highest priority.

---

## Confirmation Point

Displayed only in Rally profile.

Examples:

```text
Continue through stop sign
```

```text
Continue across bridge
```

---

## Fuel Point

Examples:

```text
Fuel Available
Gualala
```

---

# Reassurance Markers

Purpose:

Provide confidence between major navigation decisions.

---

## Placement Rules

Markers are generated when:

* Entering towns
* Crossing major geographic features
* Passing major landmarks
* Exceeding distance intervals

---

## Default Interval

```text
15 miles
```

---

## Examples

```text
Continue CA-36

Wildwood
15 mi

Platina
31 mi

South Fork Summit
44 mi
```

---

# Fuel Intelligence

User configurable.

Example:

```bash
--fuel-range 120
```

---

## Analysis Performed

* Fuel stations near route
* Longest fuel gap
* Recommended fuel locations
* Fuel-range warnings

---

## Example Output

```text
Longest Fuel Gap:
104 miles

Recommended Fuel:
Gualala
Fort Bragg
Leggett
```

---

## Warning Example

```text
⚠ Fuel gap exceeds configured range
```

---

# Route Simplification

Aggressive simplification is required.

---

## Goals

Preserve:

* Major curves
* Route character
* Junction geometry

Remove:

* GPS noise
* Redundant points
* Excessive detail

---

## Expected Reduction

Target:

```text
95%+ point reduction
```

for recorded tracks.

---

# Route Graph Model

Internal representation:

```python
Route
 ├─ Segments
 ├─ DecisionPoints
 ├─ ReassuranceMarkers
 ├─ FuelStops
 └─ Pages
```

Example segment:

```python
Segment(
    name="Skaggs Springs Rd",
    length_miles=35.7
)
```

Example decision:

```python
DecisionPoint(
    mile=35.7,
    instruction="Left onto CA-1",
    significance=95
)
```

---

# Hybrid Schematic Map System

## Core Philosophy

Do not render the GPX directly.

Instead:

```text
Route Graph
 ↓
Schematic Layout Engine
 ↓
Map Strip
```

---

## Hybrid Schematic Design

Characteristics:

* Preserves route character
* Preserves major bends
* Compresses low-information stretches
* Exaggerates important junctions
* Improves readability

Inspiration:

* AAA TripTik
* Aviation charts
* Transit maps

Not:

* GIS maps
* Garmin maps
* Google Maps printouts

---

# Segment Compression

Visual size is determined by information density.

Example:

| Segment                 | Real Distance | Visual Length |
| ----------------------- | ------------- | ------------- |
| Long uninterrupted road | 40 mi         | Medium        |
| Complex junction        | 2 mi          | Large         |
| Town center             | 1 mi          | Large         |
| Fuel stop               | 0 mi          | Medium        |

---

# Road Name Ribbon

Displayed on every page.

Example:

```text
Skaggs Springs Rd
========================

Annapolis Rd
============

CA-1
====================

Fort Bragg
```

Purpose:

Allow navigation by road names.

---

# Page Layout

US Letter or A4 (`--paper`, default Letter), optimized for color printing,
tank-bag viewing, and sunlight readability. Two layouts (CLI default is
**portrait**):

**Header** (both layouts): route name (left) · page mileage `start / total`
in green (right of center) · `Page X of Y` (right).

**Landscape** — one page per route-aware page: a framed Map Zone that hugs the
schematic strip (decisions, fuel, reassurance/town markers, road-name ribbon),
plus a horizontal progress bar with a YOU marker for at-a-glance route position.

**Portrait** (roadbook / TripTik) — several stacked strip "lanes" per page,
clearly separated, each a framed strip over its **absolute** mile range (shown in
green) with its own road ribbon. `--lanes N` / `--lane-decisions M`.

> **As-built note:** the original spec had a separate large-text *Cue Zone*
> (NEXT / AFTER / FUEL / TOTAL). In practice that duplicated information already
> on the strip (each decision is labeled "`<mi>  <turn> onto <road>`") and the
> ribbon, so it was dropped: the **TOTAL** moved to the header (green mileage) and
> the rest is read directly off the map strip. The progress bar is landscape-only;
> portrait conveys position via the per-lane mile ranges.

---

# Route-Aware Pagination

Pages are not split solely by mileage.

Page breaks should occur near:

* Major decisions
* Road transitions
* Significant route changes

This preserves continuity.

---

# Rendering Priorities

## Level 1

Next navigation decision.

---

## Level 2

Upcoming navigation decision.

---

## Level 3

Map strip.

---

## Level 4

Reassurance markers.

---

## Level 5

Metadata.

---

# Output Modes

## Analyze

```bash
gpxsheet analyze route.gpx
```

Produces route analysis.

Example:

```text
Route Length: 217.3 mi

Decision Points:
  35.7  L onto CA-1
  78.2  R onto CA-128

Fuel:
  Gualala
  Fort Bragg

Longest Fuel Gap:
  104 mi

Road Segments:
  Skaggs Springs Rd
  CA-1
  CA-128
```

---

## Generate PDF

```bash
gpxsheet route.gpx
```

Produces:

```text
route.pdf
```

---

## Validate

```bash
gpxsheet validate route.gpx
```

Detects:

```text
⚠ Fuel gap exceeds configured range

⚠ Route contains unpaved segment

⚠ Seasonal closure risk

⚠ Ferry crossing present
```

(Fuel-gap, unpaved, ferry, and seasonal-closure checks are all implemented. The
seasonal check is a hybrid of a curated seasonal-road list and OSM seasonal/
conditional tags; see `gpxsheet.seasonal`.)

---

## Day cards

A per-day, **read-ahead** briefing (`gpxsheet.daycard`; CLI `daycard`,
`/v1/daycard`) — distinct from the tank-bag sheet/table the rider glances at while
moving. Each card summarizes the day's distance and moving time, climb, sunset and
whether you'll be **riding after dark**, passes and scenic stops, cautions
(gravel, construction, wildlife, no-services gaps), and keyless **live conditions**
— weather at your ETA with **crosswind**, air quality / smoke, and nearby
wildfires — as markdown / HTML / JSON. Phases 1 (offline route + OSM) and 2
(keyless live data: Open-Meteo weather/air/elevation + NIFC wildfire, behind a
cached, graceful provider layer in `gpxsheet.live`, gated by `live=` /
`GPXSHEET_DISABLE_LIVE`) are built; key-gated sources (AirNow/OpenWeather) and
cell-coverage dead zones are Phase 3 — see
[day-cards-design.md](day-cards-design.md).

---

# Technology Stack (as built)

| Concern            | Library              | Notes                                    |
| ------------------ | -------------------- | ---------------------------------------- |
| GPX parsing        | `gpxpy`              | core                                     |
| Mapping / PDF      | `matplotlib`         | core; strip + PDF (Agg, `PdfPages`)      |
| CLI                | `typer`              | core                                     |
| OSM integration    | `osmnx`              | core; OSM enrichment                      |
| Geometry           | `shapely`            | core; used by enrich                       |

Notes: the strip and PDF are rendered with **matplotlib**, not `reportlab` (the
single matplotlib stack keeps the strip and page composition consistent and
vector). `networkx` is pulled in transitively by `osmnx`; GPXSheet reads the osmnx
graph through it (node degree, edges, bearings) for junction topology. The geo
stack also brings `geopandas`/`pyproj`/`pyogrio`.

---

# Success Criteria

The product succeeds if a rider can glance at the printed document for less than one second and reliably determine:

* Current road
* Next navigation decision
* Distance to that decision
* Upcoming fuel opportunities
* Overall route progress
* Confidence that they remain on the intended route

without needing to interpret a traditional map, tulip diagram, or turn-by-turn GPS interface.

---

# Implementation Status & Engineering Notes

> This section records what is actually built and the engineering decisions made
> while implementing the spec above. The sections above are the design intent;
> this section is the as-built reality. Release history is in the
> [CHANGELOG](https://github.com/pleasantone/gpxsheet/blob/main/CHANGELOG.md);
> planned/queued work is tracked in
> [TODO.md](https://github.com/pleasantone/gpxsheet/blob/main/TODO.md).

## What's built

* **Route analysis engine.**
  GPX loading (track/route/waypoint, incl. Garmin BaseCamp routes — see
  [basecamp-routes.md](basecamp-routes.md)), geometry cleanup (RDP), decision-point
  detection, reassurance markers, fuel analysis, segmentation, `analyze` text
  output, and OSM enrichment — all implemented and tuned against real tracks.
* **Schematic map-strip renderer.**
  `gpxsheet.layout` (pure Schematic Layout Engine) turns the route graph into a
  stylized strip: a ribbon that jogs at each decision, with segment length
  compressed sub-linearly (`sqrt`) in real distance. Two turn styles:
  **`stylized`** (default — quantized/exaggerated bends, reads like a transit
  map) and **`faithful`** (bend by the real turn angle, capped). `gpxsheet.strip`
  renders to `route_strip.png` (matplotlib) with markers for decisions, fuel,
  food/rest and generic waypoints, town reassurance, and roundabouts; fuel/food/
  ferry markers carry a symbol glyph (font-coverage-aware, with a plain fallback)
  plus mileage. Unpaved (brown-dashed) and ferry (blue-dashed) stretches draw as
  styled ribbon overlays with labeled ends. Labels are collision-placed with
  alternating above/below sides and dashed leaders to their dots; road names wrap
  to two lines. A marker landing on mile 0 / the route end is nudged clear of the
  START/END marker. CLI: `gpxsheet strip <gpx> [-o out.png]
  [--turns stylized|faithful]`. Validated on real OSM tracks.
* **PDF generation.** `gpxsheet.pdf` composes a
  US-Letter/A4 document with route-aware pagination (`gpxsheet.paginate`,
  breaks at decisions, never mid-road). Lanes **auto-fit by default** — as many
  decisions per lane as fit without label overlap (`strip.fit_pages`); pass
  `--lane-decisions N` for a fixed cap. Header shows the (truncated) route name,
  page mileage in
  green, and page counter. Two layouts:
  - **portrait** (CLI default): stacked strip "lanes" per page (roadbook/TripTik),
    each a framed strip over its absolute mile range with its own road ribbon.
    Tunable via `--lanes N` / `--lane-decisions M`; partial pages top-aligned.
  - **landscape** (`--landscape`): one strip per page in a framed Map Zone that
    hugs the strip, with the road ribbon and a progress (YOU) bar; page breaks
    honor `--lane-decisions` too.

  `render` (the library/web entry point) and `gpxsheet generate <gpx> -o route.pdf`
  drive this. (The earlier fuel-at-mile-0/START label overlap is fixed.) Remaining
  rendering tuning is in TODO.md.
* **Decisions/segments come from OSM; orientation defaults to portrait.** The
  OSM-derived navigation structure is the product. Enrichment falls back to the
  geometry baseline *automatically* (with a warning) when the route `looks_sparse`
  (waypoint-only `<rte>`) or the live Overpass query fails, so analysis still
  produces output. Monster tracks are enriched in chunks. Orientation defaults to
  portrait (`--landscape` for one strip/page).
* **Packaged + published.** `pyproject.toml` builds a
  clean sdist + wheel (PEP 639 license, PEP 561 `py.typed`, version from
  `gpxsheet.__version__`). Core deps are gpxpy + matplotlib + typer + osmnx +
  shapely (OSM is integral, not an optional extra); extras: `service`, `dev`,
  `docs`. `twine check` passes. Releases are automated: conventional commits →
  release-please PR → merging it tags `vX.Y.Z` → `publish.yml` publishes to
  TestPyPI then PyPI via OIDC trusted publishing (v0.2.0 shipped this way).
* **Web service.** `gpxsheet.service`
  is a FastAPI app (the `service` extra) exposing the engine over REST. Every
  operation is an async job created via a typed POST: `/v1/render` (a map),
  `/v1/table` (a route table), `/v1/analyze` and `/v1/validate` (JSON reports).
  These return a job polled at
  `GET /v1/jobs/{id}` (status + result `content_type`) and fetched at `.../result`
  (streams the artifact or 303 → presigned URL); plus `/healthz` and `/docs`.
  `/v1/render` takes `layout` ∈ {`portrait`, `landscape`, `preview`, `strip`} ×
  `format` ∈ {`pdf`, `png`} (paginated layouts as PNG stack their pages into one
  tall image; see `pdf.render_layout`/`render_pages_png`). An internal `op` string
  (set per endpoint, not client-facing) routes the worker.
  `process_job` is shared by an `EagerRunner` (dev/sync, in-memory + local dir) and
  a `DramatiqRunner` (worker). Self-hosted via `docker-compose.yml`
  (api/worker/redis/minio; `python:3.13-slim`, geo wheels, no system GDAL).
  Hardening: per-client rate limiting (with `Retry-After`/`RateLimit-*` headers),
  upload-size cap, result caching (by GPX + op + params + identity hash),
  per-identity job ownership (others get 404), and presigned download URLs signed
  against a host-reachable public endpoint (region pinned to avoid a
  GetBucketLocation round-trip). HTTP conventions: `202` + `Location` on submit
  (`200` for an already-finished/cached job), `425` while a result isn't ready,
  `409` on failure, immutable `ETag`/`Cache-Control` on results, and a `/readyz`
  probe (Redis/MinIO reachable) alongside `/healthz`.
  **Verified live** via `docker compose up`: async submit → worker render →
  status `done` → external PDF download through the presigned URL, plus cache
  hits. Tests: dev path end-to-end via `TestClient` (incl. cache/cap/limit); the
  Redis/MinIO prod path has a gated integration test (`GPXSHEET_SERVICE_IT=1`).
* **Web UI.** A React 19 + TypeScript + Vite 6 +
  Tailwind v4 SPA in `frontend/` bundles into `src/gpxsheet/service/static/` and
  is served by FastAPI at `/` via a `StaticFiles` mount (guarded by `is_dir()` so
  the service boots cleanly without a build). UX: full-page drop zone →
  simultaneous `/v1/analyze` + `/v1/render?layout=preview` on file drop → inline
  strip thumbnail + route stats (distance/turns/fuel) → options panel →
  "Generate" button → download. Job polling uses exponential backoff (500 ms →
  4 s cap). Smart options: `paper`/`lanes_per_page` hidden for `preview`/`strip`
  layouts; `format` locked to PNG for those layouts. Optional API key stored in
  `localStorage`. CSP split: API routes keep `default-src 'none'`; SPA HTML gets
  `default-src 'self'; img-src 'self' blob: data:`. Dev: `make dev-api` + `make
  dev-ui` (Vite on :5173 proxies `/v1/` to uvicorn on :8000). Build: `make
  frontend`; built files are gitignored (reproducible from source).

`validate` (CLI, library `gpxsheet.validate`, and `/v1/validate`) reports fuel-gap,
unpaved, ferry, and seasonal-closure findings as a `ValidationReport`. The
seasonal check is hybrid: a curated list of well-known seasonal roads (Sierra/
Cascade passes) matched on OSM road names, plus an OSM-tag supplement
(`seasonal` / `*:conditional` / `snowmobile`) — see `gpxsheet.seasonal`. Future
service hardening (auth/API keys, metrics, distributed rate limiting) is in TODO.md.

## Decision Point Engine — as built

The engine is **two-tier**, because pure geometry cannot tell a curving road
from a junction (this is the central lesson from testing on real tracks — a
recorded track of Mount Hamilton Road produced 100+ false "turns" from
curvature alone):

1. **Geometry baseline (no OSM).** Detects localized heading changes on the
   RDP-cleaned track: same-direction deltas confined to a short arc are grouped
   into one turn (`TURN_ANGLE_THRESHOLD_DEG=35`, `MAX_TURN_ARC_M=90`). Honest
   but **over-detects on twisty roads** — it has no way to know you stayed on
   the same road. Used as a fallback and to supply turn *direction*.

2. **OSM enrichment.** Implements Rule Set 1 (road-name changes),
   which is what the significance table is really about. The route is sampled
   for OSM road names (~60 m spacing); a name that does not persist for at least
   `MIN_ROAD_RUN_MILES=0.3` is discarded as nearest-edge "flapping" at junctions
   (tuned via a threshold sweep on real tracks). Each surviving road-name change
   becomes a decision: "Left/Right onto <road>" (or "Continue onto <road>" when
   the heading change is < `CONTINUE_MAX_ANGLE_DEG=25`), with the turn direction
   measured from the track geometry at that point. Segments become the durable
   named roads (the road ribbon).

**Cluster merging** (`merge_close_decisions`, `MERGE_MIN_SEPARATION_MILES=0.2`)
collapses decisions that are closer together than the threshold into a single
representative (highest significance), applied on both tiers — real recorded
tracks produce tight clusters of firings at complex intersections.

**Significance** currently uses a subset of the spec table: road-name change
= 40, highway-like name (regex over "Freeway"/"Highway"/"CA-1" etc.) raises it
to 50, and a sharp turn (≥60°) adds 10. A straight "Continue onto" change onto a
minor cul-de-sac road (unambiguous suffixes only) is penalized below the display
threshold as residential-grid noise, and promoted nameless forks (below) score by
turn angle. Y/T-intersection and explicit junction-geometry scoring are **not yet
implemented** (the corresponding `SCORE_*` constants were removed rather than
advertise unused scoring) — see TODO.md.

**Junction topology (OSM mode).** `enrich._apply_junction_topology` (best-effort;
any failure degrades to plain turns) reads the osmnx graph to enrich decisions:

* *Roads not taken* — at a fork/multi-way (node degree ≥ 3), the other branches
  are recorded on `DecisionPoint.branches` (name + relative angle/direction,
  excluding the road arrived on and the road taken). The strip draws each as a
  ghosted dashed stub so the rider can see which road to ignore. Drawing the
  stubs is optional (on by default): `show_branches` on the library `render`,
  `render_layout`, `draw_strip`/`render_route_strip`; `show_branches` on the web
  `/v1/render` form; `--branches/--no-branches` on the CLI (`generate`, `strip`,
  `preview`). Toggling it off keeps the `branches` data, just suppresses the stubs.
* *Roundabouts* — `junction=roundabout`/`circular` ways are reconstructed into
  ordered rings; the route's entry/exit nodes give the exit number (counted from
  *outgoing* spurs only, so one-way feeder roads don't inflate it), emitted as a
  `DecisionKind.ROUNDABOUT` decision ("Take the Nth exit onto …", drawn with a
  ring glyph). The roundabout's *other* exits (spurs you don't take) populate the
  same `branches` field, so they render as ghosted stubs like any junction.
* *Nameless forks* — a high-degree node where the route turns off a *named,
  differently-named* through-road (so no road-name change flags it) is promoted to
  its own decision ("Left/Right at the fork"), with that through-road as a ghosted
  branch. Gated (turn angle + named non-minor through-road, dropping the same-named
  road you stay on) so switchbacks and service-stub junctions aren't flagged.

The pure counting/geometry lives in `gpxsheet.junctions` and is unit-tested with
synthetic inputs; the graph-reading is tested with hand-built networkx graphs.

### Known limitations (decision detection)

* **Heuristic thresholds, not a labeled fit.** Nameless-fork promotion and the
  residential "Continue onto" down-weighting use conservative thresholds validated
  by inspecting real tracks (Mt Hamilton, a Riverbank roundabout, SF arterials),
  not a labeled ground-truth set; edge cases may still slip through.
* **Residential areas show more decisions** (~0.6/mi) than highways (~0.24/mi)
  or mountain roads (~0.13/mi). These are real street-name changes (correctly
  surfaced in `sport-touring`; the `minimalist` threshold filters them), not
  noise — but worth knowing.
* **No ground-truth dataset.** Tuning constants were validated by inspecting
  known Bay Area routes, not against labeled correct answers.

## OSM enrichment — operational notes

* Backed by `osmnx` 2.x + the geopandas stack (a core dependency; installs cleanly
  on Python 3.14).
* Queries the **live Overpass API**: needs network, slower than the geometry
  path (≈3 s rural, but tens of seconds to minutes for dense urban areas).
  `osmnx` caches responses, so repeat runs over the same area are fast.
* Graph is built from a buffered route polygon (not the whole bbox), in chunks for
  long routes. Each chunk graph is built through a network fallback
  (`drive` → `drive_service` → wider buffer); a chunk that still yields no drivable
  network is skipped rather than aborting enrichment for the whole route. Remote
  roads (e.g. Mt Hamilton Rd) only resolve under `drive_service`.
* Helper functions are unit-tested; the end-to-end enrichment path is tested
  deterministically against **committed Overpass responses**
  (`tests/fixtures/osm_cache`, replayed via `conftest`), so CI/offline never hit
  the network. Re-record fixtures with `GPXSHEET_RECORD_OSM=1`.

## Real-world data quirks handled

* OSM edge `name` may be a string, a **list** (a way with several names), or
  NaN — normalized in `_edge_name`.
* `features_from_polygon` **raises** `InsufficientResponseError` (not empty) when
  a region has no matching features — caught in `_add_fuel`.
* OSM string cells are often NaN, and `float('nan')` is truthy, so `or`-fallback
  chains silently keep NaN — use `_clean_str`.

## Tech stack (as installed)

See the "Technology Stack (as built)" table above. Verified on Python 3.14: core
= gpxpy + matplotlib + typer + osmnx 2.1 + shapely (+ geopandas/pyproj/pyogrio via
osmnx); `[dev]` = pytest + ruff + mypy + build + twine.

## Rendering backend — matplotlib vs. SVG (analysis)

We evaluated whether matplotlib is the right rendering backend, given how much
hand-written machinery the renderer carries (label de-collision, transform
juggling, the analytic `fit_pages` estimate, font-coverage probing, hand-composed
PDF pages). A throwaway SVG-emit spike for the `strip` layout (pure-Python SVG +
`cairosvg`, wired behind a `render_layout(engine="svg")` hook) informed these
conclusions. The spike was discarded; the findings are kept here.

* **matplotlib is being used as a vector canvas + ad-hoc layout engine**, not as a
  plotting library — there are no plots/axes/scales. That mismatch is the source of
  most incidental complexity (data↔pixel round-trips, draw-then-measure after
  `set_aspect`, the glyph-coverage fallback that exists only because matplotlib
  doesn't do font fallback, and the hand-rolled page composition in `pdf.py`).
* **Label de-collision is intrinsic, not a backend artifact.** Automatic map
  labeling is heuristic in *any* backend; the spike's simpler single-pass placement
  visibly collided where matplotlib's force-directed pass did not. Switching
  backends does **not** make this cheaper — it must be ported and improved either
  way. This is the renderer's real complexity.
* **The SVG architecture is clean and slots in trivially** (`layout.py` is already
  backend-agnostic; the `engine=` hook was ~10 lines): pure-Python emission, direct
  coordinates (no transforms), one document → SVG/PNG/PDF, and output that is
  unit-testable as XML. ~250 LOC covered the whole `strip`.
* **The font/glyph win depends on the rasterizer, not on SVG itself.** `cairosvg`
  rendered the ⚓/☕ marker glyphs as tofu (worse than matplotlib); the
  "real glyphs for free" benefit needs **resvg** or a browser, plus a runtime
  dependency cost (libcairo / resvg) that matters for the service container.

**Decision: keep matplotlib for now.** Migrating the strip alone is not worth it —
the label algorithm doesn't get simpler and the glyph win needs a heavier
rasterizer. The larger payoff, if revisited, is **CSS Paged Media (e.g. WeasyPrint)
for the portrait roadbook pagination**, where matplotlib's hand-composed pages cost
the most; the per-lane strip could be embedded SVG. Triggers to reconsider: wanting
reliable symbol glyphs, the label/transform code becoming a maintenance sink, or
needing finer typographic / pagination control.

