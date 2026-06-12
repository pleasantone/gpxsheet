# GPXSheet — TODO

Planned work, queued. As-built status lives in [docs/product.md](docs/product.md);
architecture/context and conventions in [CLAUDE.md](CLAUDE.md).

## Input / GPX support (open)

- **Broaden GPX route/track support across planners** — ingest GPX from
  **Kurviger**, **Furkot**, and **Garmin BaseCamp**, using each tool's
  route extensions to reconstruct a real track from route points (e.g. the
  shaping/via points and any embedded geometry), so a `<rte>`-only export still
  yields trackpoints for analysis. Handle files that carry **both** a `<rte>` and
  a `<trk>` (combined route + track) — decide which is authoritative and merge
  consistently. Add fixtures from each planner under `gpxsamples/`/`tests/`.

## Analysis (open)

- **Seasonal-closure risk check** — `validate.validate_route` only emits an INFO
  "Seasonal-closure risk is not checked yet" placeholder (the `seasonal` finding
  code is already reserved in the validate report, the web API, and docs/product.md).
  Implement a real assessment (e.g. OSM seasonal / `access:conditional` tags, or a
  curated pass/closure list for known seasonal roads).
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
- Per-container memory limits + bounded queue depth (see security-audit §8).
- Metrics / observability.
