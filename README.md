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

v0.1.0 — **Phase 1 (milestones 1–4) complete:** analysis engine, schematic strip,
tank-bag PDF, and a publish-ready package.

- **Route analysis** — GPX (track/route/waypoints) → decision points, fuel,
  reassurance markers, road segments; `analyze` text output.
- **Decision detection is two-tier.** A geometry baseline (honest, but
  over-detects on twisty roads — it can't tell a curve from a junction) and an
  OSM mode that derives decisions from *durable road-name changes*, so a 22 mi
  switchback climb collapses to one clean segment ("onto Mount Hamilton Road").
- **Schematic map strip** — stylized (default) or faithful turns, collision-placed
  labels with dashed leaders, and the road-name ribbon.
- **Tank-bag PDF** — route-aware pagination; **portrait** roadbook (stacked strip
  lanes, the default) or **landscape** (one strip/page); page mileage in the
  header, progress bar.
- **Packaged** for `pip install gpxsheet` (+ `[osm]` extra); PEP 561 typed.

`validate` (CLI) is still a stub; a web service is future work.

## Installation

```bash
pip install gpxsheet            # core (GPX -> strip / PDF)
pip install "gpxsheet[osm]"     # + OpenStreetMap enrichment (heavy geo stack)
```

### Development

```bash
git clone <repo-url> gpxsheet && cd gpxsheet
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,osm]"             # drop ,osm to skip the OSM stack
python -m build && twine check dist/*   # build + check the distribution
# publish (maintainer only): twine upload dist/*
```

## Usage

OpenStreetMap enrichment and the portrait roadbook layout are **on by default**;
both can be turned off, and OSM degrades gracefully (to geometry-only, with a
warning) when the `osm` extra is missing, the route is too sparse to follow
roads, or the live Overpass query fails.

```bash
gpxsheet generate route.gpx -o route.pdf            # portrait roadbook + OSM (defaults)
gpxsheet generate route.gpx --landscape -o route.pdf
gpxsheet generate route.gpx --no-osm -o route.pdf   # geometry-only (no network)
#   portrait knobs: --lanes N (lanes/page) --lane-decisions M (decisions/lane)

gpxsheet analyze route.gpx                           # text analysis
gpxsheet strip   route.gpx -o route_strip.png        # single schematic strip PNG
```

OSM queries the live Overpass API (seconds for rural routes, up to minutes for
dense urban; cached by `osmnx`). The end-to-end query is covered by an
integration test gated behind `GPXSHEET_LIVE_OSM=1` so CI/offline stay network-free.

### Library

```python
from gpxsheet import generate_pdf

# Library defaults are landscape + geometry-only (predictable/offline); pass
# use_osm=True and/or orientation="portrait" to match the CLI product defaults.
generate_pdf("route.gpx", "route.pdf", profile="sport-touring", fuel_range=180)
```

## Web service (Milestone 5)

A FastAPI service exposes the engine over REST. Renders are slow (matplotlib +
live OSM), so generation runs as a background job (Dramatiq + Redis) with results
in object storage (MinIO); `/v1/analyze` returns the structured analysis as JSON.

Self-hosted stack (API + worker + Redis + MinIO):

```bash
docker compose up --build
#   API   -> http://localhost:8000/docs
#   MinIO -> http://localhost:9001  (minioadmin / minioadmin)

curl -F gpx=@route.gpx "http://localhost:8000/v1/jobs?orientation=portrait" # -> {id, status}
curl http://localhost:8000/v1/jobs/<id>          # poll until status=done
curl -L http://localhost:8000/v1/jobs/<id>/result -o route.pdf
```

Endpoints: `POST /v1/jobs` (upload GPX + params → 202), `GET /v1/jobs/{id}`,
`GET /v1/jobs/{id}/result` (streams, or 303 → presigned URL), `POST /v1/analyze`,
`GET /healthz`. Single-process dev mode (in-memory, synchronous, no Redis/MinIO):

```bash
pip install -e ".[service]"
uvicorn gpxsheet.service.asgi:app        # worker not needed in dev mode
```

Config is env-driven (`GPXSHEET_REDIS_URL` switches on the prod path; see
`gpxsheet/service/settings.py`).

## License

MIT
