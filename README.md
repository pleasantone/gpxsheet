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
- ✅ Decision-point detection (geometry-based turn detection)
- ✅ Reassurance markers (distance intervals + nearest-waypoint labels)
- ✅ Fuel analysis (waypoint-based; longest gap + range warnings)
- ✅ Route segmentation + `analyze` text output
- 🚧 OSM enrichment (road names / fuel POIs) — optional `[osm]` extra, experimental
- ⏳ Milestone 2: schematic map-strip renderer
- ⏳ Milestone 3: PDF generation

Try it: `gpxsheet analyze examples/sample_route.gpx --fuel-range 6`

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
