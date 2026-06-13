# GPXSheet — project context for Claude

GPXSheet converts GPX routes into glanceable, map-centric **motorcycle tank-bag
navigation PDFs** (sport-touring). Full design spec + as-built notes:
[docs/product.md](docs/product.md) — read its "Implementation Status & Engineering Notes"
section when resuming.

- **Repo:** private GitHub `pleasantone/gpxsheet`, branch `main`.
- **Python:** 3.14, project-local `.venv`. `source .venv/bin/activate`.

Planned work is in [TODO.md](TODO.md).

## Merge discipline — docs must mirror the code

**Before merging any PR, verify the documentation still mirrors the changes in
that PR.** The user-facing docs that go stale most easily: `docs/web-api.md`
(endpoints, params, sample output), `docs/library-api.md` (public API surface,
return structures), `docs/product.md`, `README.md`, this `CLAUDE.md`, and
`TODO.md`. Walk the PR diff and ask: did any endpoint/param/CLI flag, public
function signature, returned data structure, default, or behavior change without
the matching doc being updated?

- If docs are out of sync, **warn the user**, **draft** the documentation update
  (edit the files locally) but **do not commit it**, and **hold the merge** until
  the user has reviewed the draft.
- Only proceed with the merge once the user signs off.

## Commands

```bash
.venv/bin/ruff check .      # lint (CI runs it; keep clean)
.venv/bin/mypy src tests docs  # type-check ALL our code, not just the core (CI gate)
.venv/bin/pytest -q         # all should pass; deterministic + offline (cached OSM)
GPXSHEET_RECORD_OSM=1 .venv/bin/pytest tests/test_enrich.py  # re-record OSM cache
.venv/bin/gpxsheet generate <gpx> -o route.pdf            # portrait (default)
.venv/bin/gpxsheet generate <gpx> --layout landscape     # one strip/page
.venv/bin/gpxsheet generate <gpx> --layout strip -o strip.png   # single strip PNG
.venv/bin/gpxsheet table <gpx> -o route.html --departure "9am"  # route table (html|md|json)
.venv/bin/gpxsheet table <gpx> --no-osm -o route.md             # fast, fully offline
```

The `table` command renders a markdown/HTML route table — waypoints, distances,
fuel/lunch markers, ETAs — **natively from the `analyze` pipeline** (`src/gpxsheet/
routetable.py`), so it inherits OSM enrichment: OSM is **on by default** (auto-
discovered `amenity=fuel`, road-snapped distance), with `--no-osm` for a fast,
fully offline table. ETAs need `--departure`. OSM also drives **variable ETAs**
(per-segment `maxspeed`/highway-class speed; a user `--speed` overrides it), a
**Road column** (from `route.segments` names), `--cue` (a turn-by-turn cue sheet
from `decision_points`), and **per-day sections** for multi-`<trk>` routes
(`route.day_breaks`, +24h/day). Supporting seams: `waypoints.py` (the classifier
— G/L/GL markers, layover, fuel-reset; schema-compatible with a GPXtable
`--config`) and `timing.py` (`SpeedProfile` + ETA/layover/since-gas + sun).
Web op `"table"` → `/v1/table` (`TableParams`, incl. `osm`/`cue`); the SPA
exposes it under a **Table** tab (vs the **Sheet** tab). `format` is
**html|markdown|json** — JSON (`build_table_data`/`build_table_json`, a typed
`TableDocument` of per-day sections→rows) is **always imperial** (1-decimal, ISO
datetimes) and always carries lat/lon + the cue, so `units`/`coordinates`/`cue`
only affect md/HTML. Both md and JSON render from one shared `_day_slices` seam.

`src/gpxsheet/daycard.py` is the **day card** — a per-day, *read-ahead* briefing
(distance/climb, sunset + riding-after-dark, passes/scenic, gravel/construction/
wildlife, no-services gaps), distinct from the tank-bag sheet/table. Built on the
analyzed `Route` + a best-effort OSM POI query; warnings reuse `validate.Finding`.
CLI `daycard`, web op `"daycard"` → `/v1/daycard` (`DayCardParams`; md/HTML/JSON),
lib `daycard.render_day_cards`/`build_day_cards`. The SPA exposes it under a **Day
card** tab (alongside **Sheet**/**Table**), rendering one stacked card per day from
the structured JSON (always imperial — the frontend converts units client-side) and
prefilling the departure from the GPX start time. **Phase 2 adds keyless live
conditions** behind `src/gpxsheet/live/` — Open-Meteo weather (with per-sample
**crosswind** from route bearings), air-quality/smoke, an elevation DEM fallback,
and NIFC wildfire perimeters. Providers are **graceful** (any source down →
section omitted) and cache every response on disk; `live=`/`--no-live` and
`GPXSHEET_DISABLE_LIVE=1` (or umbrella `GPXSHEET_OFFLINE=1`) gate them, weather/air
also need `--departure`. The OSM core and the live providers share one **external-
data-source env convention** — `GPXSHEET_<SRC>_CACHE_DIR` / `DISABLE_<SRC>` /
`RECORD_<SRC>` / `*_BASE_URL`, with `GPXSHEET_OFFLINE` as the umbrella — centralized
in `src/gpxsheet/sources.py` (`<SRC>` ∈ {`OSM`, `LIVE`}). Tests
replay a committed `tests/fixtures/live_cache` cache-only (autouse
`_live_cache` in conftest, mirroring the OSM harness; record with
`GPXSHEET_RECORD_LIVE=1`). Key-gated sources (AirNow/OpenWeather) and cell
coverage are Phase 3 — design + provider plan in
[docs/day-cards-design.md](docs/day-cards-design.md).

`src/gpxsheet/gpx.py` lifts named, non-shaping plain `<rtept>`s to waypoints (not
just Garmin ViaPoints), so plain `<rte>` stops drive POIs / the table. The
`gpxtable` runtime dependency is **gone** — the table is fully native; `astral`,
`markdown2` and `python-dateutil` are now direct deps. `routetable.py` carries
`parse_departure` + `markdown_to_html` (the HTML table keeps the `gpxtable` CSS
class the SPA styles). Distances are correct, unlike GPXtable's route path, which
lags by one point (drops the final leg).

Install: `pip install -e ".[dev]"` (core deps include osmnx 2.1 + shapely +
geopandas; install fine on 3.14). Add `,service` for the web-service stack.

### Running commands here (Bash gotchas)

- **Foreground `sleep` is blocked.** The harness rejects `sleep N && <check>`
  and `sleep`-based polling. To wait on a condition, use `Monitor` with an
  `until <check>; do sleep 2; done` loop, or start the work with
  `run_in_background: true` and wait for the completion notification.
- **Live OSM/Overpass needs FOREGROUND + `dangerouslyDisableSandbox`.**
  Background Bash (`run_in_background: true`) runs sandboxed with **no network**,
  so Overpass calls fail with `Connection refused` and fall back to
  geometry-only (no branches/decisions). Foreground + `dangerouslyDisableSandbox`
  reaches `overpass-api.de` fine. Mind the 10-min foreground cap — a full route
  (e.g. `basecamp-route.gpx`, ~195 mi) won't finish; clip to ~30 mi for live
  renders. `cd`/cwd does not persist between Bash calls, so use absolute paths.

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

Runner selection (in `default_components`): `GPXSHEET_REDIS_URL` → Dramatiq/Redis;
else `GPXSHEET_BACKGROUND_RENDER=1` → in-process thread pool (submit returns at
once, client polls — keeps a slow render from holding the request past a proxy
timeout); else the synchronous `EagerRunner` (the dev/test default). The Docker
image (Hugging Face Space) sets `GPXSHEET_BACKGROUND_RENDER=1`. Concurrency stays
1 (`GPXSHEET_RENDER_CONCURRENCY`): the renderers use global matplotlib `pyplot`,
which is not thread-safe, so renders serialize.

**Perf instrumentation.** Each web job logs one `gpxsheet.perf` INFO line with a
phase breakdown — e.g. `perf job:render 2.34s [bytes=1.7MB points=30909
cache=miss] load=… geometry=… enrich=… derive.pois=… derive.reassurance=…
render=…`. `cache=hit|miss` is the analysis-core cache (`service/analysis_cache.py`,
keyed on `(gpx, osm)`). Instrument new hot paths with `gpxsheet.perf`: `with
perf.span("name")` inside a `perf.track(...)` (set per job in `service/render.py`);
`perf.annotate(k=v)` adds context. Spans outside a track are ~free.

**Heavy analysis is cached + OSM-free per request.** `analysis.analyze_core`
(geometry + OSM enrich, always fuel+hazards) is the cacheable part; the cheap
`analysis.derive_products` (profile threshold, fuel report, POIs, reassurance,
hazard visibility) runs per request from the cached core without mutating it. Keep
expensive/OSM work in `analyze_core`; keep `derive_products` cheap (watch for
O(points) loops — reassurance/POIs precompute waypoint projections once).

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
- **OSM/Overpass is blocked by default.** The sandbox runs behind a security
  proxy with **Trusted** network access (package registries + GitHub only), so
  live enrichment fails with `403 Forbidden — Host not in allowlist` and falls
  back to geometry-only (which floods dense tracks like Mt Hamilton with false
  turns). The test suite is unaffected — `conftest` replays the committed OSM
  cache offline. To run *live* enrichment / `gpxsheet generate` against real
  routes, edit the environment's **Network access** → **Custom**, add
  `overpass-api.de` (and keep "include default package managers" checked so pip
  still works), then start a **new** session — resuming never re-runs setup. See
  https://code.claude.com/docs/en/claude-code-on-the-web#network-access

## Architecture (src/gpxsheet/)

Non-obvious structural facts (module purpose is derivable from filenames/docstrings):

- **Lazy imports are intentional** in `strip.py`, `pdf.py`, `paginate.py` —
  keeps matplotlib out of the import path for non-rendering use.
- **`analyze_route` = `analyze_core` then `derive_products`.** `analyze_core`
  (cacheable, profile-independent) is `_geometry_baseline` → `_osm_enrich_pass`
  (replaces decisions+segments, **always** computing fuel+hazards; falls back to
  geometry-only w/ warning+log if `looks_sparse` or Overpass fails).
  `derive_products` then applies the cheap per-request gating (profile threshold,
  fuel report, POIs, reassurance, hazard visibility) onto a fresh copy — see the
  cache note above. (There is no `_apply_profile`.)
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
`examples/sample_route.gpx` is synthetic & offshore: it's dense enough that
`looks_sparse` is False, so enrichment *does* query Overpass for its bbox (a live
round-trip), gets no results, and falls back to geometry-only — i.e. offshore
avoids OSM *results*, not the network call. To force geometry-only with no network
(air-gapped, rate-limited, or deterministic CI), set `GPXSHEET_DISABLE_OSM=1`
(honored in `analysis._osm_enrich_pass` via `sources.osm_disabled`; the e2e smoke
test sets it) — or `GPXSHEET_OFFLINE=1` to also silence the live providers.
For iteration prefer synthetic routes.

Non-obvious fixture relationships:
- **`zumo1/2/3`** are sparse waypoint-only routes (`looks_sparse` → geometry-only path).
- **`ich-north` / `ich-north-4`** are multi-day (multiple `<trk>` elements).
- **`ich-north[-4]` vs `…-fixed`**: `-fixed` corrects mis-tagged `<sym>` values
  (restaurant tagged as `Gas Station`); relevant to fuel detection from symbols.
- **`scenic` / `scenic2`**: same route in different GPX encodings (track + vias,
  plain `<rte>`, Garmin Trip Extension, etc.) — logical-equivalence test cases.
- **`bad-xml.gpx`**: intentionally malformed; error-handling fixture.
