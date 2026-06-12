# GPXSheet — TODO

Planned work, queued. As-built status lives in [docs/product.md](docs/product.md);
architecture/context and conventions in [CLAUDE.md](CLAUDE.md).

## Input / GPX support (open)

- **Broaden GPX route/track support across more planners** — ingest GPX from
  **Kurviger** and **Furkot**, using each tool's route extensions to reconstruct
  a real track from route points (shaping/via points and any embedded geometry),
  so a `<rte>`-only export still yields trackpoints for analysis. Handle files
  that carry **both** a `<rte>` and a `<trk>` (combined route + track) — decide
  which is authoritative and merge consistently. Add fixtures from each planner
  under `gpxsamples/`/`tests/`. (The shipped Garmin BaseCamp loader is the
  reference implementation.)

## Analysis (open)

- **Audit the curated seasonal-road list against OSM** — check `SEASONAL_ROADS`
  (`gpxsheet.seasonal`) against live OSM: if every road in it already carries
  reliable `seasonal` / `access:conditional` tags, drop the curated list and rely
  solely on the OSM-tag path (`seasonal.is_seasonal_edge`), removing the
  special-case code. Otherwise, expand the curated list; and parse closure windows
  for a date-aware verdict (validate carries no trip date today).
- **Day cards — live conditions (Phase 3)** — the `daycard` output
  (`gpxsheet.daycard`, CLI `daycard`, `/v1/daycard`) ships Phase 1 (offline: stats,
  sun/golden-hour/after-dark, passes/scenic/gravel/construction/wildlife,
  no-services gaps) **and Phase 2** (keyless live providers in
  `gpxsheet.live`: Open-Meteo weather with crosswind, air/smoke, an elevation
  DEM fallback, and NIFC wildfire — cached + graceful, gated by `live=` /
  `GPXSHEET_DISABLE_LIVE`). Remaining **Phase 3** per
  [day-cards-design.md](docs/day-cards-design.md): key-gated AirNow / OpenWeather
  (fresher smoke / forecasts) and cell-coverage dead zones (OpenCelliD / FCC,
  flagged approximate).
- **Y/T-intersection & junction-geometry significance scoring** — docs/product.md's
  scoring table defines Y/T-intersection scores, but only road-name / highway-name /
  sharp-turn scoring is wired up today. Implementing this would reintroduce the
  `SCORE_*` constants (county-road / Y / T / town-center) that were removed as dead.
- **Stylized-angle / compression tuning** — revisit `CONTINUE/NORMAL/SHARP_TURN_DEG`,
  `CURL_RELAX`, and `MIN_SEGMENT_LEN`/`DIST_SCALE` against more real routes.

## Rendering (open)

- **Strip label de-collision** — alternating sides + repulsion is much better but
  still heuristic; very dense lanes may want leader routing or per-lane caps
  beyond the current auto-fit pagination.
- **OSM map display with enrichment overlays** — a **dynamic, interactive** web
  map in the SPA (pan/zoom/click; e.g. Leaflet or MapLibre with OSM tiles)
  showing the route on an actual OSM basemap, overlaying the OSM-enrichment items
  — decisions/turns, fuel stops, rider waypoints, and named road segments — as
  clickable markers/labels. A geographic counterpart to the abstract strip view;
  useful for previewing and sanity-checking enrichment. Mind tile-usage/
  attribution limits (consider a tile provider / self-hosted tiles rather than
  the public OSM tile server for production traffic).

## Service hardening (future)

- Distributed (Redis-backed) rate limiting + quotas (current limiter is
  per-process, so quotas are per-replica). Optional API-key auth already exists.
- Per-container memory limits + bounded queue depth.
- Metrics / observability.

## Code cleanup / tech debt (open)

Duplicate-functionality items deferred from the day-cards Phase 2 dedup pass
(audit groups B/D) — judged not worth the churn/risk then, revisit if the code
around them changes:

- **`junctions.relative_angle` duplicates `geo.bearing_delta`** — same signed
  smallest-turn math (differs only in sign at exactly ±180°). Left as the named
  `+right/-left` domain helper, separately unit-tested. Could become a thin
  wrapper over `bearing_delta` if we reconcile the 180° edge case.
- **OSM corridor-feature query pattern** — `daycard._collect_pois` and
  `enrich`'s feature queries both do LineString → `.buffer` →
  `ox.features_from_polygon` → row-dict normalize. Shareable as an
  `enrich.corridor_features(route, tags, buffer_m)` helper, but daycard keeps
  osmnx import lazy + degrades to `{}`, so the seam needs care.
- **Parallel imperial/metric formatters** — `daycard._fmt_dist/_fmt_speed/
  _fmt_elev` vs `routetable._fmt_*`. Only the shared *constants* were unified
  (`geo.KM_PER_MILE`/`MILES_PER_KM`/`M_TO_FT`); the format functions differ in
  precision by design (glanceable card vs precise table). A shared `units.py`
  with precision params could merge them if a third consumer appears.
