# GPXSheet — TODO

Planned work, queued. As-built status lives in [docs/product.md](docs/product.md);
architecture/context and conventions in [CLAUDE.md](CLAUDE.md).

## Input / GPX support (open)

- **✅ Garmin BaseCamp routes** — done. The loader reconstructs the dense track
  from `gpxx:RoutePointExtension`/`gpxx:rpt` and lifts `trp:ViaPoint` stops to
  waypoints (with optional arrival/departure times). See
  [docs/basecamp-routes.md](docs/basecamp-routes.md); fixture
  `gpxsamples/basecamp-route.gpx`.
- **Broaden GPX route/track support across more planners** — ingest GPX from
  **Kurviger** and **Furkot**, using each tool's route extensions to reconstruct
  a real track from route points (shaping/via points and any embedded geometry),
  so a `<rte>`-only export still yields trackpoints for analysis. Handle files
  that carry **both** a `<rte>` and a `<trk>` (combined route + track) — decide
  which is authoritative and merge consistently. Add fixtures from each planner
  under `gpxsamples/`/`tests/`. (BaseCamp, above, is the reference implementation.)

## Analysis (open)

- **✅ Seasonal-closure risk check** — done. `validate.validate_route` now warns
  on seasonal roads via a *hybrid* check (`gpxsheet.seasonal`): a curated list of
  well-known seasonal roads (Sierra/Cascade passes) matched on OSM road names, plus
  an OSM-tag supplement (`seasonal` / `*:conditional` / `snowmobile`). Mirrors the
  ferry hazard (`Route.seasonal_closures`; `None`=not assessed, `[]`=clear).
  Possible follow-up: expand the curated list; parse closure windows for a
  date-aware verdict (validate carries no trip date today).
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
