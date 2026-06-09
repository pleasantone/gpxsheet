# GPXSheet — project context for Claude

GPXSheet converts GPX routes into glanceable, map-centric **motorcycle tank-bag
navigation PDFs** (sport-touring). Full design spec + as-built notes:
[PRODUCT.md](PRODUCT.md) — read its "Implementation Status & Engineering Notes"
section when resuming.

- **Repo:** private GitHub `pleasantone/gpxsheet`, branch `main`.
- **Python:** 3.14, project-local `.venv`. `source .venv/bin/activate`.
- **Status:** Phase 1 **complete** (analysis engine, schematic strip, tank-bag
  PDF in landscape + portrait, publish-ready package, web service verified live).
  Portrait roadbook is the default orientation. Decisions/segments come from OSM,
  degrading to the geometry baseline automatically on sparse routes or Overpass
  failure. Planned work is in [TODO.md](TODO.md).

## Commands

```bash
.venv/bin/ruff check .      # lint (CI runs it; keep clean)
.venv/bin/pytest -q         # all should pass; deterministic + offline (cached OSM)
GPXSHEET_RECORD_OSM=1 .venv/bin/pytest tests/test_enrich.py  # re-record OSM cache
.venv/bin/gpxsheet generate <gpx> -o route.pdf            # portrait (default)
.venv/bin/gpxsheet generate <gpx> --landscape            # one strip/page
```

Install: `pip install -e ".[dev]"` (core deps include osmnx 2.1 + shapely +
geopandas; install fine on 3.14). Add `,service` for the web-service stack.

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
- `strip.py` — matplotlib renderer: `render_route_strip`/`generate_strip` →
  `route_strip.png`; `draw_strip` shared with the PDF (Agg, lazy import). Draws
  ghosted `_draw_branch_stubs` (roads not taken) + a roundabout ring glyph.
- `paginate.py` — `paginate` (decision-cap, breaks only at decisions) +
  `slice_route` (`rebase=True` landscape / `rebase=False` portrait lane =
  absolute miles).
- `pdf.py` — `render_pdf`/`generate_pdf`. Landscape (one strip/page, framed hug,
  progress bar) + portrait (`orientation="portrait"`: stacked `_draw_lane`
  strips, `lanes_per_page`/`decisions_per_lane`). Header = name + green mileage +
  page counter; no cue zone.
- `report.py` — `analyze` text. `cli.py` — typer CLI (generate/analyze/strip/
  preview/validate; `--landscape --lanes --lane-decisions`; no OSM/dpi flags).

`analyze_route` flow: geometry detect → merge → segments → **OSM enrich**
(replaces decisions+segments; falls back to geometry-only w/ warning if
`looks_sparse` / Overpass fails) → profile threshold → fuel + reassurance.

## Key decisions (don't re-litigate without reason)

- **Decision detection is two-tier.** Pure geometry floods twisty roads (can't
  tell a curve from a junction — Mt Hamilton Rd gave 100+ false turns). OSM mode
  uses *durable road-name changes* (PRODUCT.md Rule Set 1). Validated on real Bay
  Area tracks in `~/gpxtable/samples/`.
- **Tuned constants** (threshold sweeps on real tracks): analysis
  `MIN_ROAD_RUN_MILES=0.3`, `MERGE_MIN_SEPARATION_MILES=0.2`,
  `TURN_ANGLE_THRESHOLD_DEG=35`, `MAX_TURN_ARC_M=90`, `CONTINUE_MAX_ANGLE_DEG=25`;
  strip `MIN_SEGMENT_LEN=2.6`, `DIST_SCALE=1.0`, stylized angles 10/30/55°.
- **Decisions/segments come from OSM**, falling back to the geometry baseline
  automatically (with a warning) on `looks_sparse` routes or Overpass failure.
  Orientation: library fns default landscape, CLI defaults portrait.
- OSM = live Overpass; slow in dense urban (~140s/5mi SF) vs ~3s rural. **Tests
  are deterministic + offline:** `conftest` points osmnx at a committed response
  cache (`tests/fixtures/osm_cache`) and replays cache-only (a miss raises, never
  hits the network). Re-record with `GPXSHEET_RECORD_OSM=1`. The onshore enrich
  fixture is `tests/fixtures/enrich_route.gpx`; the offshore synthetic `l_route`
  exercises the fallback path (empty Overpass → geometry-only).

## Test data

`~/gpxtable/samples/*.gpx` — 19 real California/PNW moto routes, picked to stress
every parser/analysis quirk. `examples/sample_route.gpx` is synthetic & offshore
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

## Open work / TODO

All planned and queued work is tracked in **[TODO.md](TODO.md)**.

The web service is shipped and verified live; run it with
`uvicorn gpxsheet.service.asgi:app` (dev) or `docker compose up`, worker
`dramatiq gpxsheet.service.jobs`. Typed POST per operation (GPX + params as
multipart **form fields** via `*Form` models): `/v1/render` (`RenderParams`:
`layout` portrait|landscape|preview|strip × `format` pdf|png), `/v1/analyze`,
`/v1/validate` (`ReportParams` → JSON); all create a job (`202`+`Location`, or
`200` if already done) polled at `GET /v1/jobs/{id}` and fetched at `.../result`
(`425` until ready, `409` on failure, immutable `ETag`). An internal `op` string
(not client-facing) routes the worker. Jobs are owned by their creating identity
(others 404 when keys configured). `/healthz` (live) + `/readyz` (deps reachable).
The layout×format matrix is dispatched by `pdf.render_layout` (paginated PNGs
stack pages via `render_pages_png`).

## Conventions

- Typer needs `B008` ignored (in pyproject). Use `zip(..., strict=...)`.
