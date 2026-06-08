# GPXSheet

> Motorcycle sport-touring route awareness generator.

GPXSheet is a Python command-line application and reusable library that converts
GPX routes into highly **glanceable, map-centric** motorcycle navigation PDFs
optimized for tank-bag use.

It is **not** a rally roadbook and **not** a GPS replacement. The goal is route
*awareness*: a rider should be able to glance at the printed sheet for less than
one second and immediately understand what road they're on, what the next
navigation decision is, how far away it is, what comes after, and where they are
within the overall route.

See [PRODUCT.md](PRODUCT.md) for the full design specification.

## Status

v0.1.0 — **Milestone 1 (route analysis engine) implemented.**

- ✅ GPX loading (tracks / routes / waypoints) → route graph
- ✅ Geometry cleanup (Ramer–Douglas–Peucker)
- ✅ Decision-point detection — two-tier:
  - **geometry baseline** (no OSM): localized turns with clustered firings
    collapsed. Honest but over-detects on twisty roads (it can't tell a curve
    from a junction).
  - **OSM mode** (`--osm`): decisions come from *durable* road-name changes
    ("Left/Continue onto Mount Hamilton Road"), so a 22 mi switchback climb is
    one segment with zero false turns. This is what PRODUCT.md's significance
    scoring is actually about (road-name changes / junctions).
- ✅ Reassurance markers (distance intervals + nearest-waypoint labels)
- ✅ Fuel analysis (waypoint-based, plus OSM fuel stations; longest gap + range warnings)
- ✅ Route segmentation (named roads under `--osm`) + `analyze` text output
- ✅ OSM enrichment (optional `[osm]` extra) — validated against live OpenStreetMap data
- ✅ **Milestone 2: schematic map-strip renderer** — a stylized transit-map-style
  strip (`route_strip.png`) that jogs at each decision, compresses long roads,
  and carries the decision/fuel/reassurance markers, dashed leaders, and ribbon
- ✅ **Milestone 3: PDF generation** — a landscape US-Letter tank-bag document
  with route-aware pagination, per-page map strip, cue zone (NEXT/AFTER/FUEL/
  TOTAL), and a progress indicator

Try it:

```bash
gpxsheet analyze  examples/sample_route.gpx --fuel-range 6
gpxsheet strip    examples/sample_route.gpx -o route_strip.png   # Milestone 2
gpxsheet generate your-route.gpx --osm -o route.pdf              # Milestone 3 (real road names)
```

### OSM enrichment

```bash
pip install -e ".[osm]"
gpxsheet analyze your-route.gpx --osm
```

Enrichment queries the live Overpass API, so it needs network access and is
slower than the geometry-only path — typically a few seconds for rural routes,
but tens of seconds to a couple of minutes for dense urban areas. Results are
cached by `osmnx`, so repeat runs over the same area are fast.

The OSM helper functions are unit-tested; the end-to-end query is covered by an
integration test that is skipped unless `GPXSHEET_LIVE_OSM=1` is set (so CI and
offline runs don't depend on the network).

## Installation (development)

```bash
git clone <repo-url> gpxsheet
cd gpxsheet
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
# Optional OSM enrichment stack (heavy: geopandas, scipy, ...):
pip install -e ".[osm]"
```

## Usage

```bash
# Generate a tank-bag PDF (default sport-touring profile)
gpxsheet route.gpx

# Text route analysis
gpxsheet analyze route.gpx

# Validate a route for hazards / fuel gaps
gpxsheet validate route.gpx
```

Library:

```python
from gpxsheet import generate_pdf

generate_pdf(
    gpx_file="route.gpx",
    output_file="route.pdf",
    profile="sport-touring",
    fuel_range=180,
)
```

## License

MIT
