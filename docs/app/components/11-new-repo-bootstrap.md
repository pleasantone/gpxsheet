# 11 — New-Repo Bootstrap & Read-Only References

How to start Convoy **in a fresh repository**, using `pleasantone/gpxsheet` and
`pleasantone/gpxsamples` as **read-only references** (no code reuse — gpxsheet is
being retired once Convoy absorbs its functionality). Parent:
[`../SPEC.md`](../SPEC.md). Read this before scaffolding.

## What moves to the new repo

Copy `docs/app/**` (this spec set) to the new repo's `docs/`. Then:

- **`app/` prefix disappears** — the new repo *is* Convoy, so the layout in
  [`00-conventions.md`](00-conventions.md) becomes the **repo root**:
  `backend/`, `frontend/`, `deploy/`, `docs/`. Drop the leading `app/`.
- **Cross-references to gpxsheet** in these specs (e.g. `product.md`,
  `basecamp-routes.md`, `analysis.py`) point at the **gpxsheet repo**, read-only.
  Resolve them at `https://github.com/pleasantone/gpxsheet/blob/main/<path>` (or a
  local read-only checkout). Don't try to make them repo-relative — they live in
  a different repo by design.

## gpxsheet modules to STUDY (reimplement, don't import)

gpxsheet is the **reference implementation** for the analysis. Read these to
reproduce behavior; rewrite cleanly in Convoy. (Paths under
`gpxsheet/src/gpxsheet/`.)

| Convoy component | Study in gpxsheet | For |
|---|---|---|
| Analysis: decisions | `analysis.py`, `enrich.py`, `junctions.py` | two-tier detection, significance scoring, junction topology, the tuned constants |
| Analysis: geometry | `geo.py` | RDP, bearings, haversine, mile/meter conversions |
| Analysis: GPX load | `gpx.py` + `docs/basecamp-routes.md` | track/route/waypoint parsing, Garmin BaseCamp via-point lifting |
| Analysis: classify | `waypoints.py` | G/L/GL stop classification, fuel-reset semantics |
| Timing/ETA/sun | `timing.py` | SpeedProfile, ETA, layover, since-gas, sunrise/sunset |
| Fuel/segments | `analysis.py` (fuel pass), `models.py` | fuel dedup vs waypoints, segment naming, `RouteSpan` |
| Live providers | `live/` (weather, air, fire, elevation), `sources.py` | provider shape, crosswind, the cache/env convention |
| Validate/findings | `validate.py`, `seasonal.py` | `Finding`, fuel/unpaved/ferry/seasonal checks |
| Perf | `perf.py` | the one-line phase breakdown + `span`/`annotate` API |
| Strip/PDF (later) | `strip.py`, `pdf.py`, `paginate.py` | the schematic strip + route-aware pagination (fast-follow artifact) |
| Test harness | `tests/conftest.py`, `tests/fixtures/` | the cache-only record/replay pattern for OSM/live |

Note the **deltas Convoy intentionally makes** vs gpxsheet (don't copy these
behaviors): Overpass/Valhalla down ⇒ **error not degrade** (conventions
§Reliability); map-matching via **Valhalla** not osmnx; OSM treated as a
**provider**; fuel **brand-aware scoring**; multi-user persistence; web-first.

## gpxsamples fixtures (read-only) to vendor into tests

Copy representative `.gpx` from `gpxsamples` into `backend/tests/data/` (it's a
small, license-clean set of real CA/PNW tracks). Use them for parity tests:
- twisty track (Mt-Hamilton-style) → decisions ≪ geometry-only count;
- multi-`<trk>` → multi-day; plain `<rte>` + Garmin BaseCamp → load + via-lift;
- a route with a long dry stretch → mandatory-fuel; `bad-xml.gpx` → error path.

## Pinned tech choices (so an agent doesn't stall)

These were under-specified; pin them now (swap with reason):

- **Job queue:** **Dramatiq + Redis** (gpxsheet precedent; simple, proven). RQ is
  an acceptable lighter alternative. Worker = same image, separate process.
- **DB access:** SQLAlchemy 2.x **async** + Alembic; `asyncpg` driver; `geoalchemy2`
  for PostGIS types.
- **HTML→PDF:** **WeasyPrint** (pure-Python, deterministic, offline) for the
  briefing/leader PDFs. No headless browser in the render path.
- **Static map image for the PDF** (the one real spike): use **tileserver-gl's
  static-map endpoint** (`/styles/{id}/static/...`) to get a PNG of the route
  bbox, then overlay numbered stop/bail-out markers (GeoJSON overlay params or a
  Pillow pass). This avoids a headless-MapLibre sidecar. **Validate early** — see
  Risks.
- **QR:** `qrcode` (Pillow). **GPX writer:** `gpxpy` (gpxsheet uses it) or
  hand-rolled ElementTree for the Garmin `trp:` extensions.
- **Frontend types:** `openapi-typescript` generates TS from the FastAPI OpenAPI
  schema; **PWA:** `vite-plugin-pwa` (Workbox). **Map:** `maplibre-gl`.
- **Auth email:** `aiosmtplib`; dev inbox MailHog.
- **Lint/type/test:** ruff + mypy(strict) + pytest (backend); eslint + tsc +
  Playwright (frontend) — release gates, mirroring gpxsheet CI.

## Risks / spikes to retire first

1. **Static map for the PDF** — confirm tileserver-gl static endpoint renders the
   route bbox + marker overlay acceptably; fallback is a headless-MapLibre Node
   sidecar (`@maplibre/maplibre-gl-native`). Spike in week 1.
2. **Valhalla map-matching quality** — `trace_attributes` on recorded tracks can
   mis-snap at complex junctions; spike against the twisty gpxsamples and tune
   `search_radius`/`gps_accuracy`. This underpins both geometry and enrichment.
3. **Decision-detection parity** — reproduce the two-tier result on gpxsamples
   before building UI on top; this is the crown-jewel risk.
4. **Region/tile footprint** — pick the default extract; measure Overpass DB +
   Valhalla tiles + mbtiles disk/RAM; document the swap.

## Suggested scaffold order (fresh repo)

1. Repo skeleton + `deploy/docker-compose.yml` + `.env.example` + CI (ruff/mypy/
   pytest, eslint/tsc) — empty but green.
2. **Geo infra** ([02](02-geo-infra.md)) + `seed`; retire spikes 1–2.
3. **Analysis engine** ([01](01-analysis-engine.md)) with gpxsamples parity tests
   (spike 3).
4. **Data model + migrations** ([04](04-data-model.md)) and **auth** ([05](05-auth.md))
   in parallel.
5. **Backend API** ([03](03-backend-api.md)) wiring 2–4 + **group math** ([10](10-group-math.md))
   + **live** ([08](08-live-data.md)).
6. **Frontend PWA** ([06](06-frontend.md)) + **artifacts** ([07](07-artifacts.md)).
7. Harden + **deploy** ([09](09-deployment.md)); the v1 acceptance demo (SPEC §5).

## Is the spec sufficient? (self-assessment)

Sufficient to start a multi-agent build **with** this bootstrap doc: the
architecture, decisions, data model, API surface, component boundaries, and
acceptance criteria are concrete, and the analysis algorithm is fully recoverable
from the named gpxsheet modules (read-only). The **two judgement-heavy areas** an
agent must still exercise are (a) reproducing decision-detection parity and (b)
the static-map render — both flagged as spikes with fallbacks. Everything else is
mechanical given the specs.
