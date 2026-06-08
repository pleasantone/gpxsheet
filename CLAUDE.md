# GPXSheet — project context for Claude

GPXSheet converts GPX routes into glanceable, map-centric **motorcycle tank-bag
navigation PDFs** (sport-touring). Full design spec + as-built notes:
[PRODUCT.md](PRODUCT.md) — read its "Implementation Status & Engineering Notes"
section when resuming.

- **Repo:** private GitHub `pleasantone/gpxsheet`, branch `main`.
- **Owner:** Paul Traina.
- **Python:** 3.14, project-local `.venv` (NOT `~/.venv`, an unrelated scraping
  env). `source .venv/bin/activate`.
- **Status:** Phase 1 milestones **1–4 complete** (analysis engine, schematic
  strip, tank-bag PDF in landscape + portrait, publish-ready package). Portrait
  roadbook + OSM are the CLI defaults; OSM degrades to geometry-only gracefully.

## Commands

```bash
.venv/bin/ruff check .      # lint (CI runs it; keep clean)
.venv/bin/pytest -q         # all should pass
GPXSHEET_LIVE_OSM=1 .venv/bin/pytest tests/test_enrich.py::test_enrich_route_live_against_osm
.venv/bin/gpxsheet generate <gpx> -o route.pdf            # portrait + OSM (defaults)
.venv/bin/gpxsheet generate <gpx> --landscape --no-osm    # opt-outs
```

Install: `pip install -e ".[dev]"` (core) + `pip install -e ".[osm]"` (OSM stack:
osmnx 2.1 + shapely + geopandas; installs fine on 3.14).

## Architecture (src/gpxsheet/)

- `geo.py` — haversine, bearings, cumulative distance (pure).
- `models.py` — Route graph dataclasses (Route, Segment, DecisionPoint, …).
- `gpx.py` — `load_route()` (gpxpy). `simplify.py` — RDP cleanup.
- `analysis.py` — engine: `analyze_route()` orchestrates; `detect_decision_points`,
  `merge_close_decisions`, reassurance, fuel, `build_segments`; helpers
  `coord_at_meters` (interpolates), `turn_angle_at_mile`, `looks_sparse`. Tuning
  constants at top of file.
- `enrich.py` — optional OSM (osmnx): durable road-name-change decisions
  (`_durable_runs`/`_decisions_from_runs`), named segments, fuel; `_chunk_ranges`
  chunks big routes. `profiles.py` — minimalist/sport-touring/rally thresholds.
- `layout.py` — pure Schematic Layout Engine: `build_strip_layout` → stylized
  jogging ribbon + placed markers (stylized vs faithful turns; `show_start/end`).
- `strip.py` — matplotlib renderer: `render_route_strip`/`generate_strip` →
  `route_strip.png`; `draw_strip` shared with the PDF (Agg, lazy import).
- `paginate.py` — `paginate` (decision-cap, breaks only at decisions) +
  `slice_route` (`rebase=True` landscape / `rebase=False` portrait lane =
  absolute miles).
- `pdf.py` — `render_pdf`/`generate_pdf`. Landscape (one strip/page, framed hug,
  progress bar) + portrait (`orientation="portrait"`: stacked `_draw_lane`
  strips, `lanes_per_page`/`decisions_per_lane`). Header = name + green mileage +
  page counter; no cue zone.
- `report.py` — `analyze` text. `cli.py` — typer CLI (generate/analyze/strip/
  validate; `--portrait/--landscape --osm/--no-osm --lanes --lane-decisions`).

`analyze_route` flow: geometry detect → merge → segments → **if use_osm** enrich
(replaces decisions+segments; falls back to geometry-only w/ warning if osmnx
missing / `looks_sparse` / Overpass fails) → profile threshold → fuel + reassurance.

## Key decisions (don't re-litigate without reason)

- **Decision detection is two-tier.** Pure geometry floods twisty roads (can't
  tell a curve from a junction — Mt Hamilton Rd gave 100+ false turns). OSM mode
  uses *durable road-name changes* (PRODUCT.md Rule Set 1). Validated on real Bay
  Area tracks in `~/gpxtable/samples/`.
- **Tuned constants** (threshold sweeps on real tracks): analysis
  `MIN_ROAD_RUN_MILES=0.3`, `MERGE_MIN_SEPARATION_MILES=0.2`,
  `TURN_ANGLE_THRESHOLD_DEG=35`, `MAX_TURN_ARC_M=90`, `CONTINUE_MAX_ANGLE_DEG=25`;
  strip `MIN_SEGMENT_LEN=2.6`, `DIST_SCALE=1.0`, stylized angles 10/30/55°.
- **Library vs CLI defaults:** library fns (`analyze`, `generate_pdf`) default
  `use_osm=False` / landscape (predictable, offline). Only the CLI flips to the
  product defaults (portrait + OSM).
- OSM = live Overpass; slow in dense urban (~140s/5mi SF) vs ~3s rural; the live
  integration test is gated behind `GPXSHEET_LIVE_OSM=1` so CI stays offline.
- **Iterate the renderers visually** — produce PNGs (rasterize PDFs with
  `/opt/homebrew/bin/pdftoppm`; the Read tool's PATH lacks it) and review with
  Paul. See [[gpxsheet-strip-iteration]] in memory.

## Test data

`~/gpxtable/samples/*.gpx` — gaia, scenic, ich-dual-gas (=Mt Hamilton),
basecamp-tracks, twixtmas (583mi monster), zumo* (sparse `<rte>`), … `bad-xml.gpx`
is intentionally malformed. `examples/sample_route.gpx` is synthetic & offshore
(no OSM coverage — use `--no-osm`). For iteration prefer synthetic Routes; live
Overpass hangs intermittently in this sandbox.

## Open work / TODO

### Phase 2 (requested)
- **Security audit (architecture + code, esp. the service) — required before
  public internet exposure.** Cover: auth/API keys + per-key quotas; XML upload
  safety (XXE/billion-laughs — check whether gpxpy uses lxml; harden the parser);
  SSRF & egress from OSM/Overpass fetches; upload validation beyond size (content
  sniffing, point/length caps that reject monster routes early); DoS/resource
  limits (worker time/memory, queue depth); MinIO creds + bucket policy + presigned
  expiry; CORS + security headers (HSTS/CSP/etc.); secrets via env/secret-store not
  defaults; `pip-audit` / dependency CVEs; run the worker non-root (already) and
  least-privilege. Produce a findings doc + fixes.
- **Magic-numbers sweep** — find hard-coded constants that should be named/commented
  (e.g. `1609.344` mi↔m everywhere, enrich buffers `road_buffer_m`/`fuel_buffer_m`/
  sample spacing, strip placement pixels `_OFFSET/_PAD/_LINE_CLEAR/...`, layout
  `MIN_SEGMENT_LEN/DIST_SCALE`, pagination caps, Dramatiq `time_limit`). Promote to
  documented module constants; add a `METERS_PER_MILE`-style helper where missing.
- **A4 paper size** — add a page-size option (letter | a4) to `generate_pdf`
  (figure dims + the layout fraction math), the CLI (`--paper`), and the service
  params. US Letter is currently hard-coded (11×8.5 / 8.5×11).
- **Preview image output** — a single overview image (PNG/JPEG), no pagination:
  reuse the strip renderer (`gpxsheet.strip`) for the whole route. Add a CLI flag
  and a service endpoint (e.g. `POST /v1/preview` returning an image, or a
  `format=png` option on jobs). Fast/low-res; good for a UI thumbnail.
- **Front end for the service** — a small, secure web UI (upload GPX → choose
  profile/orientation/paper/OSM → live preview image → download PDF). Must be
  hardened for **public internet exposure** (ties into the security audit: auth,
  CSRF, CSP, rate limits, no creds in the browser, served behind TLS/reverse
  proxy). Decide SPA vs server-rendered; keep deps minimal.

### Rendering / analysis polish
- **Strip label de-collision** (`_place_labels_with_leaders`) is heuristic; can
  bunch on very dense routes. Possible: leader routing, smarter side selection,
  per-page label caps.
- **Stylized "curl"** — same-direction turns accumulate; long routes can spiral.
  May need gentle relaxation toward horizontal.
- **PDF: fuel stop at mile 0 overlaps the START label** — small offset needed.
- **Reassurance-label prominence** (towns render small/gray) — revisit.
- **OSM determinism near `MIN_ROAD_RUN_MILES`** — a ~0.3mi run flipped a decision
  in/out across runs; consider hysteresis.
- **Down-weight straight "Continue onto"** name changes (residential noise);
  needs a ground-truth set. **Junction-degree detection** for nameless forks.
- ✅ **Milestone 5 DONE (verified live)** — `gpxsheet.service` FastAPI app
  (`[service]` extra): `POST /v1/jobs` (async render via Dramatiq+Redis, result in
  MinIO), `GET /v1/jobs/{id}[/result]`, `POST /v1/analyze`, `/healthz`, `/docs`.
  Hardened: per-client rate limit, upload-size cap, result caching (GPX+params
  hash), presigned URLs signed against `GPXSHEET_MINIO_PUBLIC_ENDPOINT` with
  region pinned (else GetBucketLocation 500s). `docker compose up` verified live
  end-to-end incl. external PDF download. Dev: `uvicorn gpxsheet.service.asgi:app`;
  worker: `dramatiq gpxsheet.service.jobs`. Tests: dev path via `TestClient`;
  gated prod integration test (`GPXSHEET_SERVICE_IT=1`). Future: auth, metrics,
  Redis-backed (distributed) rate limiting.
- **`validate`** CLI is still a stub (the only remaining Phase-1 gap).
- PyPI `twine upload` is the maintainer's step. Wire a vault note via
  `/project-init` when the Obsidian MCP is responsive.

## Conventions

- Commit/push only when asked; commit messages end with the Co-Authored-By
  trailer. Keep ruff clean + tests green before committing.
- Typer needs `B008` ignored (in pyproject). Use `zip(..., strict=...)`.
