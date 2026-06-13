# GPXSheet

> Motorcycle sport-touring route awareness generator.

[![PyPI](https://img.shields.io/pypi/v/gpxsheet.svg)](https://pypi.org/project/gpxsheet/)
[![Python versions](https://img.shields.io/pypi/pyversions/gpxsheet.svg)](https://pypi.org/project/gpxsheet/)
[![CI](https://github.com/pleasantone/gpxsheet/actions/workflows/ci.yml/badge.svg)](https://github.com/pleasantone/gpxsheet/actions/workflows/ci.yml)
[![Docs](https://readthedocs.org/projects/gpxsheet/badge/?version=latest)](https://gpxsheet.readthedocs.io/en/latest/)
[![License](https://img.shields.io/badge/License-AGPL%203.0--or--later-blue.svg)](https://github.com/pleasantone/gpxsheet/blob/main/LICENSE)

GPXSheet is a Python command-line application and reusable library that converts
GPX routes into highly **glanceable, map-centric** motorcycle navigation aids
optimized for tank-bag use.

It is **not** a rally roadbook and **not** a GPS replacement. The goal is route
*awareness*: a rider should be able to glance at the printed sheet for less than
one second and immediately understand what road they're on, what the next
navigation decision is, how far away it is, what comes after, and where they are
within the overall route.

**Documentation:** [gpxsheet.readthedocs.io](https://gpxsheet.readthedocs.io) —
library API, web API guide + interactive reference, and deployment notes.

<p align="center">
  <img alt="Example tank-bag PDF roadbook" height="320"
       src="https://raw.githubusercontent.com/pleasantone/gpxsheet/main/frontend/public/guide/example-sheet.png">
  &nbsp;&nbsp;
  <img alt="Example route table" height="320"
       src="https://raw.githubusercontent.com/pleasantone/gpxsheet/main/frontend/public/guide/example-table.png">
</p>

## Features

- **Route analysis** — GPX (track/route/waypoints) → decision points, fuel,
  reassurance markers, and road segments. Route *structure* comes from
  OpenStreetMap road topology rather than raw geometry, so twisty roads don't
  flood with false turns. `analyze` text output.
- **Schematic map strip** — a stylized (or faithful) map ribbon showing the
  road-name segments, decisions, fuel, and waypoints.
- **Tank-bag PDF** — route-aware pagination; a **portrait** roadbook (stacked
  strip lanes, the default) or **landscape** (one strip per page).
- **Route table** — a markdown/HTML trip plan (waypoints, distances, fuel/lunch
  markers, ETAs, sunrise/sunset; per-day sections for multi-day GPX); `table` CLI.
- **Packaged** for `pip install gpxsheet`; PEP 561 typed.
- **Web service** — a FastAPI app exposing the engine over REST (async jobs);
  see [Web service](#web-service) below.

How it works internally — the two-tier decision detection, schematic layout
engine, pagination, and OSM enrichment — is documented in
[docs/product.md](docs/product.md).

## Installation

```bash
pip install gpxsheet
```

### Development

```bash
git clone <repo-url> gpxsheet && cd gpxsheet
git submodule update --init          # populate gpxsamples/
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,service]"      # service required for mypy (pydantic plugin)
python -m build && twine check dist/*    # build + check the distribution
# publish (maintainer only): twine upload dist/*
```

**Dev server modes** — see [docs/dev-workflow.md](docs/dev-workflow.md) for the
full breakdown. Short version:

```bash
# Simple (no Docker needed — EagerRunner, synchronous):
make dev-api && make dev-ui

# Full stack (real async queue, requires Docker):
make infra && make dev-api-full && make dev-worker && make dev-ui
```

## Usage

### CLI

```bash
gpxsheet generate route.gpx -o route.pdf            # portrait roadbook (default)
gpxsheet generate route.gpx --landscape -o route.pdf
#   layout knobs: --lane-decisions M (decisions per page; default auto-fit); --lanes N (portrait lanes/page)

gpxsheet table   route.gpx --departure 9am -o route.md   # route table (html|md|json)
gpxsheet table   route.gpx --no-osm -o route.md          # fast, fully offline
gpxsheet analyze route.gpx                           # text analysis
gpxsheet strip   route.gpx -o route_strip.png        # single schematic strip PNG
```

### Library

`render`, `analyze`, and `validate` run synchronously, mirroring the web API; the
route table lives in `gpxsheet.routetable`. Full reference and examples: the
**[Library API](docs/library-api.md)**.

### Web service

A FastAPI service exposes the engine over REST and ships a built-in browser UI.

**Web UI** — drop a GPX onto the page, see a live strip preview and route stats,
adjust options, and download the PDF/PNG or route table. Build it once
(`make frontend`), then run `uvicorn gpxsheet.service.asgi:app` (UI at `/`,
Swagger at `/docs`); the hot-reload dev modes are covered under
[Development](#development) above.

**REST API** — every operation is an async job (submit → poll → fetch) over
`/v1/render`, `/v1/table`, `/v1/analyze`, and `/v1/validate`. The full reference —
every endpoint, parameter, auth, and browser `fetch`/curl examples — is the
**[Web API guide](docs/web-api.md)** (live OpenAPI at `/docs`). Config is
env-driven (`GPXSHEET_REDIS_URL` switches the prod path; see
`gpxsheet/service/settings.py`).

**Self-hosting & hardening** — run the single Docker image or the full
Redis/MinIO stack; see [docs/deploy.md](docs/deploy.md) before exposing the
service to the public internet.

## License

GNU Affero General Public License v3.0 or later (AGPL-3.0-or-later) — see
[LICENSE](LICENSE). Copyright © 2026 Paul Traina. Because the AGPL covers use
over a network, anyone who runs a modified version of the web service must offer
its users the corresponding source.
