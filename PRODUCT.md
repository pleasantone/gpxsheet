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

---

## Future Support

* Kurviger exports
* Garmin BaseCamp exports
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
from gpxsheet import generate_pdf

generate_pdf(
    gpx_file="route.gpx",
    output_file="route.pdf",
    profile="sport-touring",
    fuel_range=180
)
```

---

## Future Web Service

```http
POST /generate
```

Returns:

```json
{
  "pdf_url": "...",
  "decision_points": [...],
  "fuel_stops": [...],
  "markers": [...]
}
```

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
--fuel-range 180
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

US Letter, optimized for color printing, tank-bag viewing, and sunlight
readability. Two layouts (CLI default is **portrait**):

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

---

# Technology Stack (as built)

| Concern            | Library              | Notes                                    |
| ------------------ | -------------------- | ---------------------------------------- |
| GPX parsing        | `gpxpy`              | core                                     |
| Mapping / PDF      | `matplotlib`         | core; strip + PDF (Agg, `PdfPages`)      |
| CLI                | `typer`              | core                                     |
| OSM integration    | `osmnx`              | optional `[osm]` extra                   |
| Geometry           | `shapely`            | optional `[osm]` extra (used by enrich)  |

Notes: the strip and PDF are rendered with **matplotlib**, not `reportlab` (the
single matplotlib stack keeps the strip and page composition consistent and
vector). `networkx` is pulled in transitively by `osmnx`; GPXSheet does not use
it directly. The OSM extra also brings `geopandas`/`pyproj`/`pyogrio`.

---

# Phase 1 Deliverables

## Milestone 1

Route analysis engine.

Outputs:

* Decision points
* Fuel points
* Reassurance markers

---

## Milestone 2

Schematic map-strip renderer.

Outputs:

```text
route_strip.png
```

---

## Milestone 3

PDF generation.

Outputs:

```text
route.pdf
```

Including:

* Map strip
* Cue blocks
* Road ribbon
* Fuel analysis
* Progress indicator

---

## Milestone 4

Packaged CLI.

```bash
pip install gpxsheet
```

---

## Milestone 5

Web service extraction.

Expose the same engine through REST APIs.

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
> this section is the as-built reality. Last updated: Phase 1 (milestones 1–4)
> complete.

## Milestone progress

* **Milestone 1 — Route analysis engine: ✅ complete.**
  GPX loading (track/route/waypoint), geometry cleanup (RDP), decision-point
  detection, reassurance markers, fuel analysis, segmentation, `analyze` text
  output, and OSM enrichment — all implemented and tuned against real tracks.
* **Milestone 2 — Schematic map-strip renderer: ✅ complete.**
  `gpxsheet.layout` (pure Schematic Layout Engine) turns the route graph into a
  stylized strip: a ribbon that jogs at each decision, with segment length
  compressed sub-linearly (`sqrt`) in real distance. Two turn styles:
  **`stylized`** (default — quantized/exaggerated bends, reads like a transit
  map) and **`faithful`** (bend by the real turn angle, capped). `gpxsheet.strip`
  renders to `route_strip.png` (matplotlib) with decision/fuel/reassurance
  markers, dashed leader lines (collision-placed and connected to their dots),
  2-line-wrapped road names, and the road-name ribbon. CLI: `gpxsheet strip
  <gpx> [-o out.png] [--turns stylized|faithful]`. Validated on real OSM tracks.
  Remaining polish (non-blocking, in CLAUDE.md): reassurance-label prominence,
  stylized-angle/compression tuning, heading drift on long same-direction routes.
* **Milestone 3 — PDF generation: ✅ complete.** `gpxsheet.pdf` composes a
  US-Letter document with route-aware pagination (`gpxsheet.paginate`,
  decision-cap only — breaks at decisions, never mid-road). Header shows the
  (truncated) route name, page mileage in green, and page counter. Two layouts:
  - **portrait** (CLI default): stacked strip "lanes" per page (roadbook/TripTik),
    each a framed strip over its absolute mile range with its own road ribbon.
    Tunable via `--lanes N` / `--lane-decisions M`; partial pages top-aligned.
  - **landscape** (`--landscape`): one strip per page in a framed Map Zone that
    hugs the strip, with the road ribbon and a progress (YOU) bar.

  `generate_pdf` is wired into the API and `gpxsheet generate <gpx> -o route.pdf`.
  Open polish (CLAUDE.md): fuel-at-mile-0 overlaps the START label.
* **Defaults & graceful degradation:** the CLI defaults to **portrait + OSM**
  (`--landscape` / `--no-osm` opt out). OSM enrichment falls back to geometry-only
  (with a warning) when the `osm` extra is missing, the route `looks_sparse`
  (waypoint-only `<rte>`), or the live Overpass query fails — so the default works
  on core installs and offline. Sparse routes skip OSM; monster tracks are
  enriched in chunks. The *library* functions keep `use_osm=False` / landscape
  defaults for predictable programmatic use; only the CLI flips.
* **Milestone 4 — Packaged CLI: ✅ complete (publish-ready).** `pyproject.toml`
  builds a clean sdist + wheel (PEP 639 license, PEP 561 `py.typed`, dynamic
  version from `gpxsheet.__version__`). Core deps slimmed to gpxpy + matplotlib
  + typer (reportlab/networkx were unused; shapely moved to the `osm` extra).
  `twine check` passes; verified that a fresh **core-only** install runs the CLI
  and produces a PDF, degrading gracefully without the `osm` extra. Actual
  `twine upload` to PyPI is the maintainer's step (needs PyPI credentials).
* **Milestone 5 — Web service: 🟡 in progress.** `gpxsheet.service` is a FastAPI
  app (the `service` extra) exposing the engine over REST: `POST /v1/jobs`
  (upload GPX + params → 202 job), `GET /v1/jobs/{id}`, `.../result`,
  `POST /v1/analyze`, `/healthz`, `/docs`. Slow renders run as background jobs
  (Dramatiq + Redis) with results in MinIO; `process_job` is shared by an
  `EagerRunner` (dev/sync, in-memory + local dir) and a `DramatiqRunner` (worker).
  Self-hosted via `docker-compose.yml` (api/worker/redis/minio); the image builds
  on `python:3.13-slim` with the geo wheels (no system GDAL). Tested: the dev path
  end-to-end via `TestClient`; the Redis/MinIO prod path has a gated integration
  test (`GPXSHEET_SERVICE_IT=1`). Remaining: live-stack verification + polish
  (rate limits, input caps, result caching, the presigned-URL public-endpoint
  caveat).

`validate` (CLI) is still a stub.

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

2. **OSM mode (`--osm`).** Implements PRODUCT.md Rule Set 1 (road-name changes),
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
to 50, and a sharp turn (≥60°) adds 10. Y/T-intersection and explicit
junction-geometry scoring are **not yet implemented**.

### Known limitations (decision detection)

* **Nameless forks are missed in OSM mode.** A fork where you must bear one way
  but the road keeps its name produces no road-name change, so it isn't caught.
  Fixing this needs junction-degree / node topology from the OSM graph (future).
* **Residential areas show more decisions** (~0.6/mi) than highways (~0.24/mi)
  or mountain roads (~0.13/mi). These are real street-name changes (correctly
  surfaced in `sport-touring`; the `minimalist` threshold filters them), not
  noise — but worth knowing.
* **No ground-truth dataset.** Tuning constants were validated by inspecting
  known Bay Area routes, not against labeled correct answers.

## OSM enrichment — operational notes

* Optional, via `pip install -e ".[osm]"` (osmnx 2.x + geopandas stack;
  installs cleanly on Python 3.14).
* Queries the **live Overpass API**: needs network, slower than the geometry
  path (≈3 s rural, but tens of seconds to minutes for dense urban areas).
  `osmnx` caches responses, so repeat runs over the same area are fast.
* Graph is built from a buffered route polygon (not the whole bbox).
* Helper functions are unit-tested; the end-to-end query is an integration test
  skipped unless `GPXSHEET_LIVE_OSM=1` (so CI/offline don't depend on network).

## Real-world data quirks handled

* OSM edge `name` may be a string, a **list** (a way with several names), or
  NaN — normalized in `_edge_name`.
* `features_from_polygon` **raises** `InsufficientResponseError` (not empty) when
  a region has no matching features — caught in `_add_fuel`.
* OSM string cells are often NaN, and `float('nan')` is truthy, so `or`-fallback
  chains silently keep NaN — use `_clean_str`.

## Tech stack (as installed)

See the "Technology Stack (as built)" table above. Verified on Python 3.14: core
= gpxpy + matplotlib + typer; `[osm]` = osmnx 2.1 + shapely + geopandas/pyproj/
pyogrio; `[dev]` = pytest + ruff + mypy + build + twine.

