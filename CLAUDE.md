# GPXSheet — project context for Claude

GPXSheet converts GPX routes into glanceable, map-centric **motorcycle tank-bag
navigation PDFs** (sport-touring). Full design spec + as-built notes:
[docs/product.md](docs/product.md) — read its "Implementation Status & Engineering Notes"
section when resuming.

- **Repo:** private GitHub `pleasantone/gpxsheet`, branch `main`.
- **Python:** 3.14, project-local `.venv`. `source .venv/bin/activate`.

Planned work is in [TODO.md](TODO.md).

## Commands

```bash
.venv/bin/ruff check .      # lint (CI runs it; keep clean)
.venv/bin/mypy src tests docs  # type-check ALL our code, not just the core (CI gate)
.venv/bin/pytest -q         # all should pass; deterministic + offline (cached OSM)
GPXSHEET_RECORD_OSM=1 .venv/bin/pytest tests/test_enrich.py  # re-record OSM cache
.venv/bin/gpxsheet generate <gpx> -o route.pdf            # portrait (default)
.venv/bin/gpxsheet generate <gpx> --layout landscape     # one strip/page
.venv/bin/gpxsheet generate <gpx> --layout strip -o strip.png   # single strip PNG
```

Install: `pip install -e ".[dev]"` (core deps include osmnx 2.1 + shapely +
geopandas; install fine on 3.14). Add `,service` for the web-service stack.

### Frontend + dev server modes

The web UI lives in `frontend/` and builds to `src/gpxsheet/service/static/`
(gitignored). Full breakdown: [docs/dev-workflow.md](docs/dev-workflow.md).

```bash
make frontend       # build SPA: npm ci && npm run build → service/static/
make dev-api        # simple mode: EagerRunner, no deps, :8000
make dev-ui         # Vite dev server :5173, proxies /v1/ to :8000

# Full-stack mode (real Dramatiq queue + MinIO — requires Docker):
make infra          # Redis + MinIO in Docker (loopback ports, .env.dev creds)
make dev-api-full   # uvicorn --reload, prod path
make dev-worker     # Dramatiq worker
make infra-down     # stop containers
```

Non-obvious: `service/static/` must exist for the SPA to be served at `/`.
Without the build, `/` falls through to Swagger at `/docs`.

Sample routes live in the `gpxsamples/` git submodule; a fresh clone needs
`git submodule update --init` to populate it.

### Claude Code on the web / remote sandbox

No project-local `.venv` here — the repo is cloned fresh into an ephemeral
container and deps aren't installed yet. Set up and run against the ambient
interpreter instead of `.venv/bin/...`:

```bash
pip install -e ".[dev,service]"   # install BOTH extras (see why below)
ruff check .
python3 -m mypy src tests docs    # module form: see the mypy note below
python3 -m pytest -q
```

- **Install `,service` too, not just `[dev]`:** mypy type-checks `src/gpxsheet/
  service/` (which imports pydantic/fastapi) and `pyproject.toml` enables the
  `pydantic.mypy` plugin — without the service deps mypy aborts with
  "Error importing plugin 'pydantic.mypy'" before checking anything.
- **Run mypy/pytest as `python3 -m …`:** a different `mypy` may sit earlier on
  `PATH` (installed for another interpreter, without our pydantic plugin); the
  module form pins the run to the interpreter the project is installed into.
- Sandbox Python may be 3.11 (vs 3.14 locally); the code installs and the suite
  passes on both. Commit + push before the container is reclaimed.

## Architecture (src/gpxsheet/)

Non-obvious structural facts (module purpose is derivable from filenames/docstrings):

- **Lazy imports are intentional** in `strip.py`, `pdf.py`, `paginate.py` —
  keeps matplotlib out of the import path for non-rendering use.
- **`analyze_route` is three steps:** `_geometry_baseline` → `_osm_enrich_pass`
  (replaces decisions+segments; falls back to geometry-only w/ warning+log if
  `looks_sparse` or Overpass fails) → `_apply_profile` (threshold, fuel, reassurance).
- **`decisions_per_lane=0`** is the universal default for `render()`, CLI, web,
  and all `pdf.py` renderer functions — means auto-fit via `paginate.plan_pages()`.
  Positive value → fixed cap. All render-knob defaults live in `defaults.py`.
- **`enrich.py` imports `turn_word`/`significance_for_turn` from `analysis.py`** —
  an intentional cross-module dependency; don't inline copies.
- **`_apply_junction_topology` is best-effort** (`log.exception` on failure) —
  a topology error degrades to plain turns, never aborts enrichment.

## Key decisions (don't re-litigate without reason)

- **Decision detection is two-tier.** Pure geometry floods twisty roads (can't
  tell a curve from a junction — Mt Hamilton Rd gave 100+ false turns). OSM mode
  uses *durable road-name changes* (docs/product.md Rule Set 1). Validated on real Bay
  Area tracks in the `gpxsamples/` submodule.
- **Tuned constants** (threshold sweeps on real tracks): analysis
  `MIN_ROAD_RUN_MILES=0.3`, `MERGE_MIN_SEPARATION_MILES=0.2`,
  `TURN_ANGLE_THRESHOLD_DEG=35`, `MAX_TURN_ARC_M=90`, `CONTINUE_MAX_ANGLE_DEG=25`;
  strip `MIN_SEGMENT_LEN=2.6`, `DIST_SCALE=1.0`, stylized angles 10/30/55°.
- **Decisions/segments come from OSM**, falling back to the geometry baseline
  automatically (with a warning) on `looks_sparse` routes or Overpass failure.
  Layout default is **portrait** for both the library `render` and the CLI;
  `portrait`/`landscape`/`preview`/`strip` are peer layouts.
- OSM = live Overpass; slow in dense urban (~140s/5mi SF) vs ~3s rural. **Tests
  are deterministic + offline:** `conftest` points osmnx at a committed response
  cache (`tests/fixtures/osm_cache`) and replays cache-only (a miss raises, never
  hits the network). Re-record with `GPXSHEET_RECORD_OSM=1`. The onshore enrich
  fixture is `tests/fixtures/enrich_route.gpx`; the offshore synthetic `l_route`
  exercises the fallback path (empty Overpass → geometry-only).
- **Rider waypoints win over OSM.** Every named GPX `<wpt>` always renders as a
  POI; an OSM fuel station within `FUEL_BUFFER_M` of a waypoint is suppressed as a
  duplicate (the rider already marked that stop). Fuel comes from OSM, with GPX
  fuel waypoints as the geometry-only fallback.

## Test data

`gpxsamples/*.gpx` (git submodule) — real California/PNW moto routes.
`examples/sample_route.gpx` is synthetic & offshore (no OSM → geometry-only fallback).
For iteration prefer synthetic routes.

Non-obvious fixture relationships:
- **`zumo1/2/3`** are sparse waypoint-only routes (`looks_sparse` → geometry-only path).
- **`ich-north` / `ich-north-4`** are multi-day (multiple `<trk>` elements).
- **`ich-north[-4]` vs `…-fixed`**: `-fixed` corrects mis-tagged `<sym>` values
  (restaurant tagged as `Gas Station`); relevant to fuel detection from symbols.
- **`scenic` / `scenic2`**: same route in different GPX encodings (track + vias,
  plain `<rte>`, Garmin Trip Extension, etc.) — logical-equivalence test cases.
- **`bad-xml.gpx`**: intentionally malformed; error-handling fixture.
