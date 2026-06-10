# GPXSheet — TODO

Planned work, queued. As-built status lives in [PRODUCT.md](PRODUCT.md);
architecture/context and conventions in [CLAUDE.md](CLAUDE.md).

## Features (requested)

- **Front end for the service** — a small, secure web UI (upload GPX → choose
  profile/orientation/paper/OSM → live preview image → download PDF). Must be
  hardened for **public internet exposure** (ties into the security audit: auth,
  CSRF, CSP, rate limits, no creds in the browser, served behind TLS/reverse
  proxy). Decide SPA vs server-rendered; keep deps minimal.

## Rendering / analysis polish

Shipped (`feat/render-analysis-polish`): START/END marker offset, stylized-curl
relaxation, prominent town labels, durable-run deadband near `MIN_ROAD_RUN_MILES`,
residential "Continue onto" down-weighting, nameless-fork promotion, waypoint
display + labeling, fuel/food/ferry glyphs + mileage, unpaved (brown-dashed) and
ferry (blue-dashed) span ribbons with labeled ends, and alternating label sides
for de-collision.

Validated against real tracks with live OSM and fixed (`feat/osm-enrichment-robustness`):
"Continue onto" down-weighting (suffix set narrowed to unambiguous cul-de-sac
types so arterials like "…Way" survive), nameless-fork promotion (no longer
floods switchbacks — requires a *named, differently-named* through-road), and
roundabout exit-counting (one-way feeders no longer inflate the exit number).
Committed offline regression fixtures cover the Mt Hamilton and Riverbank-
roundabout cases.

Still open:

- **Stylized-angle / compression tuning** — revisit `CONTINUE/NORMAL/SHARP_TURN_DEG`,
  `CURL_RELAX`, and `MIN_SEGMENT_LEN`/`DIST_SCALE` against more real routes.
- **Strip label de-collision** — alternating sides + repulsion is much better but
  still heuristic; very dense lanes may want leader routing or per-lane caps
  beyond the current auto-fit pagination.


## OSM enrichment robustness

- **Done — `drive` → `drive_service` fallback.** `graph_from_polygon` with
  `network_type="drive"` returned no graph nodes on some real sport-touring roads
  (e.g. Mt Hamilton Rd), silently degrading the whole route to the geometry-only
  baseline. Each chunk graph is now built through a fallback chain (`drive`, then
  `drive_service`, then a wider buffer) and a per-chunk failure is non-fatal, so
  one bad chunk no longer aborts enrichment for the entire route.


## Service hardening (future)

- Distributed (Redis-backed) rate limiting + quotas (current limiter is
  per-process, so quotas are per-replica). Optional API-key auth already exists.
- Per-container memory limits + bounded queue depth (see security-audit §8).
- Metrics / observability.
