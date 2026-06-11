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
.venv/bin/gpxsheet generate <gpx> --landscape            # one strip/page
```

Install: `pip install -e ".[dev]"` (core deps include osmnx 2.1 + shapely +
geopandas; install fine on 3.14). Add `,service` for the web-service stack.

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

- `geo.py` — haversine, bearings, cumulative distance (pure).
- `models.py` — Route graph dataclasses (Route, Segment, DecisionPoint, …).
- `gpx.py` — `load_route()` (gpxpy). `simplify.py` — RDP cleanup.
- `analysis.py` — engine: `analyze_route()` orchestrates; `detect_decision_points`,
  `merge_close_decisions`, reassurance, fuel, `build_segments`; helpers
  `coord_at_meters` (interpolates), `turn_angle_at_mile`, `looks_sparse`. Tuning
  constants at top of file.
- `enrich.py` — OSM (osmnx): durable road-name-change decisions
  (`_durable_runs`/`_decisions_from_runs`), named segments, fuel; `_chunk_ranges`
  chunks big routes. `_apply_junction_topology` (best-effort, try/except) reads
  the osmnx graph (node degree, edge bearings, `junction=roundabout`) to add
  roads-not-taken branches + roundabout "Nth exit" decisions. `profiles.py` —
  minimalist/sport-touring/rally thresholds.
- `junctions.py` — pure topology helpers (no osmnx): `branches_not_taken`,
  `roundabout_exit_number`, `relative_angle`/`direction_word`. Graph-reading in
  enrich is tested with hand-built networkx graphs (no Overpass).
- `layout.py` — pure Schematic Layout Engine: `build_strip_layout` → stylized
  jogging ribbon + placed markers (stylized vs faithful turns; `show_start/end`).
- `strip.py` — matplotlib renderer: `render_route_strip` → strip image;
  `draw_strip` shared with the PDF (Agg, lazy import). Draws ghosted
  `_draw_branch_stubs` (roads not taken) + a roundabout ring glyph.
- `paginate.py` — `paginate` (fixed decision-cap, breaks only at decisions) +
  `slice_route` (`rebase=True` landscape / `rebase=False` portrait lane =
  absolute miles). `decisions_per_lane=0/None` (the **public default** — `render()`,
  CLI, web) switches to `strip.fit_pages` (analytic greedy auto-fit: pack a lane
  until labels would overlap, then break); a positive value forces a fixed cap.
  Internal `pdf` renderer defaults stay at the fixed `FIXED_DECISIONS_PER_LANE=4`.
  Public render-knob defaults (`show_branches`, `turn_style`, `paper`,
  `lanes_per_page`, `decisions_per_lane`) have a single home in `defaults.py`,
  imported by the lib `render`, CLI, service models, and the `pdf`/`strip` renderers.
- `pdf.py` — renderers `render_pdf`/`render_pages_png`/`render_preview` + the
  `render_layout(layout, fmt)` dispatcher (layout × pdf/png). Landscape (one
  strip/page, framed hug, progress bar) + portrait (stacked `_draw_lane` strips,
  `lanes_per_page`/`decisions_per_lane`). Header = name + green mileage + page
  counter; no cue zone.
- `report.py` — `analyze` text. `cli.py` — typer CLI (generate/analyze/strip/
  preview/validate; `--landscape --lanes --lane-decisions`; no OSM/dpi flags),
  all wired through the library `render`/`analyze`/`validate` entry points.

`analyze_route` flow: geometry detect → merge → segments → **OSM enrich**
(replaces decisions+segments; falls back to geometry-only w/ warning if
`looks_sparse` / Overpass fails) → profile threshold → fuel + reassurance.

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

`gpxsamples/*.gpx` (git submodule) — real California/PNW moto routes, picked to
stress every parser/analysis quirk. `examples/sample_route.gpx` is synthetic & offshore
(no OSM coverage → enrichment falls back to geometry-only). For iteration prefer
synthetic Routes.

By data type (what the pipeline keys on):
- **Dense tracks** (`<trk>`, ~30–40 pts/mi): `ich-dual-gas` ("sep02 174mi" =
  Mt Hamilton; geometry-only floods it w/ 100+ false turns), `basecamp-tracks`,
  `ich-north*` (24k–31k pts), `twixtmas` (583mi).
- **Routes** (`<rte>`): `gaia` (1368pts, canonical 75mi Palo Alto·Skyline·coast —
  reaches lat 37.77 near SF, source of the ferry-terminal false-positives),
  `gaia2`, `onthegomap`, `basecamp-route` (23pts).
- **Sparse routes** (`looks_sparse` / OSM-reconstruction case): `zumo1` (4pts/62mi),
  `zumo2` (6/82), `zumo3` (12/564, + a nameless first `<rte>`) — ~1 pt per 15–45mi.
- **Track + route in one file:** `basecamp`, `inroute`, `scenic`, `scenic2`.

Sources (each app encodes GPX differently): Garmin BaseCamp (`basecamp*`), GaiaGPS
(`gaia*`), inRoute (`inroute`), onthegomap, Scenic (`scenic*`), Garmin zūmo XT
(`zumo*`), no-creator/processed (`ich-*`, `twixtmas`).

Special cases:
- **Multi-day = multiple tracks:** `ich-north` (D1/D2/D3, 1174mi), `ich-north-4`
  (+D3-coast alt, 1879mi), `twixtmas` (day1/2/3).
- **`-fixed` pairs** (`ich-north[-4]` vs `…-fixed`): fix = corrected waypoint
  `<sym>` tags (restaurant mis-tagged `Gas Station` → `Restaurant`) + trimmed
  track names. Relevant to fuel-detection-from-symbols.
- **Same route, many encodings** (logical-route equivalence): `scenic` = Track +
  Vias-as-Routepoints + Garmin-Extension; `scenic2` = Track + plain-`<rte>` +
  Garmin Trip Extension + Garmin RoutePoint Extension.
- **Waypoint conventions:** numbered rider sequences (`01 Evergreen`,
  `101 Los Altos`); gas in name (`76 Bodega Bay`, `03 Tracy and Gas`) and/or
  `<sym>Gas Station</sym>`.
- `bad-xml.gpx` — intentionally malformed (truncated `<rte>`, mismatched tag at
  line 599); error-handling fixture.


## Conventions

- Typer needs `B008` ignored (in pyproject). Use `zip(..., strict=...)`.
