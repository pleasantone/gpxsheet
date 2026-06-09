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

**Documentation:** [gpxsheet.readthedocs.io](https://gpxsheet.readthedocs.io) —
library API, web API guide + interactive reference, and deployment notes.
See [PRODUCT.md](PRODUCT.md) for the full design specification.

## Status

v0.1.0 — **Phase 1 complete:** analysis engine, schematic strip,
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
- **Packaged** for `pip install gpxsheet`; PEP 561 typed.
- **Web service** — a FastAPI app exposing the engine over REST (async jobs);
  see the [Web service](#web-service) section and [docs/web-api.md](docs/web-api.md).

## Installation

```bash
pip install gpxsheet
```

### Development

```bash
git clone <repo-url> gpxsheet && cd gpxsheet
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"                  # add ,service for the web service stack
python -m build && twine check dist/*    # build + check the distribution
# publish (maintainer only): twine upload dist/*
```

## Usage

Decisions and segments come from OpenStreetMap road topology (durable road-name
changes, named roads, fuel). It degrades to the geometry baseline *automatically*
(with a warning) when the route is too sparse to follow roads or the live
Overpass query fails. The portrait roadbook layout is the default; pass
`--landscape` for one strip/page.

```bash
gpxsheet generate route.gpx -o route.pdf            # portrait roadbook (default)
gpxsheet generate route.gpx --landscape -o route.pdf
#   layout knobs: --lane-decisions M (decisions per page); --lanes N (portrait lanes/page)

gpxsheet analyze route.gpx                           # text analysis
gpxsheet strip   route.gpx -o route_strip.png        # single schematic strip PNG
```

OSM queries the live Overpass API (seconds for rural routes, up to minutes for
dense urban; cached by `osmnx`). The test suite is deterministic and offline: it
replays committed Overpass responses from `tests/fixtures/osm_cache` (re-record
with `GPXSHEET_RECORD_OSM=1`; see `tests/fixtures/README.md`).

### Library

The library mirrors the web API — `render`, `analyze`, `validate` — but runs
synchronously:

```python
import gpxsheet

gpxsheet.render("route.gpx", "route.pdf", layout="portrait")   # also landscape/preview/strip, format=pdf|png
route = gpxsheet.analyze("route.gpx", fuel_range=180)
report = gpxsheet.validate("route.gpx", fuel_range=180)         # report.findings
```

## Web service

A FastAPI service exposes the engine over REST. Every operation is a background
job (Dramatiq + Redis) with results in object storage (MinIO): you POST to a
typed endpoint (GPX + params as multipart form fields), then poll and fetch via
the shared job URLs. `/v1/render` takes a `layout`
(`portrait`/`landscape`/`preview`/`strip`) and `format` (`pdf`/`png`);
`/v1/analyze` and `/v1/validate` return JSON reports.

Self-hosted stack (API + worker + Redis + MinIO):

```bash
docker compose up --build
#   API   -> http://localhost:8000/docs
#   MinIO -> http://localhost:9001  (minioadmin / minioadmin)

# render a portrait PDF (the defaults); the 202 response's Location header is the job
curl -F gpx=@route.gpx http://localhost:8000/v1/render                       # -> {id, status}
curl http://localhost:8000/v1/jobs/<id>                 # poll until status=done
curl -L http://localhost:8000/v1/jobs/<id>/result -o route.pdf

# other examples (same poll -> fetch flow):
curl -F gpx=@route.gpx -F layout=preview -F format=png http://localhost:8000/v1/render
curl -F gpx=@route.gpx -F layout=landscape -F paper=a4 http://localhost:8000/v1/render
curl -F gpx=@route.gpx http://localhost:8000/v1/analyze                      # JSON report
```

Endpoints: `POST /v1/render`, `POST /v1/analyze`, `POST /v1/validate` (each
uploads a GPX + params → `202` job with a `Location` header, or `200` if an
identical request is already done); `GET /v1/jobs/{id}` (status, incl.
`content_type` when done), `GET /v1/jobs/{id}/result` (streams the artifact with
an immutable `ETag`, or 303 → presigned URL; `425` until ready, `409` if failed);
`GET /healthz` (liveness) and `GET /readyz` (Redis/MinIO reachable). When API
keys are configured, jobs are visible only to the key that created them.
Single-process dev mode (in-memory, synchronous, no Redis/MinIO):

```bash
pip install -e ".[service]"
uvicorn gpxsheet.service.asgi:app        # worker not needed in dev mode
```

Config is env-driven (`GPXSHEET_REDIS_URL` switches on the prod path; see
`gpxsheet/service/settings.py`).

**Building a UI on the API?** See the front-end integration guide:
[docs/web-api.md](docs/web-api.md) (submit → poll → fetch flow, every endpoint,
auth, and browser `fetch` examples). Live OpenAPI docs are served at `/docs`.

**Before exposing the service to the public internet, read
[docs/security-audit.md](docs/security-audit.md).** Key hardening knobs:
`GPXSHEET_API_KEYS` (comma-separated; enables `X-API-Key`/`Bearer` auth + per-key
rate limits), `GPXSHEET_RATE_LIMIT_PER_MIN`, `GPXSHEET_MAX_UPLOAD_BYTES`,
`GPXSHEET_MAX_POINTS`, `GPXSHEET_CORS_ORIGINS`, `GPXSHEET_ENABLE_HSTS`, and the MinIO
credentials (the prod path refuses to boot on the `minioadmin` defaults). The
service must run behind a TLS-terminating reverse proxy.

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later) — see
[LICENSE](LICENSE). Copyright © 2026 Paul Traina. Because the AGPL covers use
over a network, anyone who runs a modified version of the web service must offer
its users the corresponding source.
