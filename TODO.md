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
- **Day cards — live conditions (Phase 2/3)** — the `daycard` output
  (`gpxsheet.daycard`, CLI `daycard`, `/v1/daycard`) ships Phase 1 (offline: stats,
  sun/golden-hour/after-dark, passes/scenic/gravel/construction/wildlife,
  no-services gaps). Add the live providers per
  [day-cards-design.md](docs/day-cards-design.md): **Phase 2** keyless Open-Meteo
  weather (+crosswind from route bearings), air/smoke, elevation, and NIFC wildfire,
  behind a cached, graceful provider interface; **Phase 3** key-gated AirNow /
  OpenWeather and cell-coverage dead zones. **Resume at the "Phase 2 — kickoff"
  section** of [day-cards-design.md](docs/day-cards-design.md) for the exact
  step-by-step (provider layer, Open-Meteo fields, crosswind formula, test harness).
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
