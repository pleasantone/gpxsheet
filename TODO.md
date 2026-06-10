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

Still open — these need a real-route ground-truth set and live-OSM validation
(the mechanisms above ship with conservative, eyeballed defaults, not
empirically tuned constants):

- **Stylized-angle / compression tuning** — revisit `CONTINUE/NORMAL/SHARP_TURN_DEG`,
  `CURL_RELAX`, and `MIN_SEGMENT_LEN`/`DIST_SCALE` against more real routes.
- **Validate "Continue onto" down-weighting** — `_MINOR_ROAD_SUFFIXES` and
  `SCORE_CONTINUE_PENALTY` were chosen by eye; confirm against a labeled set that
  real arterials are never dropped and grid noise reliably is.
- **Validate nameless-fork promotion** — `PROMOTE_FORK_MIN_ANGLE_DEG` and the
  "left a straight-ahead road" gate need checking on real tracks so genuine forks
  are caught without flagging side streets ridden straight through.
- **Roads-not-taken / roundabout tuning** — validate exit-counting and branch
  selection against real tracks with live OSM; revisit the ring-traversal
  heuristics on multi-chunk routes.
- **Strip label de-collision** — alternating sides + repulsion is much better but
  still heuristic; very dense lanes may want leader routing or per-lane caps
  beyond the current auto-fit pagination.


## Service hardening (future)

- Distributed (Redis-backed) rate limiting + quotas (current limiter is
  per-process, so quotas are per-replica). Optional API-key auth already exists.
- Per-container memory limits + bounded queue depth (see security-audit §8).
- Metrics / observability.
