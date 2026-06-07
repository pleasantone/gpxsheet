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

Early scaffolding (v0.1.0). The package layout, CLI, and library entry points
are stubbed out against the spec; the analysis, layout, and rendering engines
are being built out per the Phase 1 milestones in `PRODUCT.md`.

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
