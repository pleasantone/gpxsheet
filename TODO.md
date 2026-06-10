# GPXSheet — TODO

Planned work, queued. As-built status lives in [PRODUCT.md](PRODUCT.md);
architecture/context and conventions in [CLAUDE.md](CLAUDE.md).

## Features (requested)

- **Front end for the service** — a small, secure web UI (upload GPX → choose
  profile/orientation/paper/OSM → live preview image → download PDF). Must be
  hardened for **public internet exposure** (ties into the security audit: auth,
  CSRF, CSP, rate limits, no creds in the browser, served behind TLS/reverse
  proxy). Decide SPA vs server-rendered; keep deps minimal.

## Analysis (open)

- **Seasonal-closure risk check** — `validate.validate_route` only emits an INFO
  "Seasonal-closure risk is not checked yet" placeholder (the `seasonal` finding
  code is already reserved in the validate report, the web API, and PRODUCT.md).
  Implement a real assessment (e.g. OSM seasonal / `access:conditional` tags, or a
  curated pass/closure list for known seasonal roads).
- **Y/T-intersection & junction-geometry significance scoring** — PRODUCT.md's
  scoring table includes Y/T-intersection scores (`SCORE_Y_INTERSECTION` /
  `SCORE_T_INTERSECTION` exist in `profiles.py` but are unused); only road-name /
  highway-name / sharp-turn scoring is wired up today.
- **Stylized-angle / compression tuning** — revisit `CONTINUE/NORMAL/SHARP_TURN_DEG`,
  `CURL_RELAX`, and `MIN_SEGMENT_LEN`/`DIST_SCALE` against more real routes.
- **Waypoint projection has no off-route cutoff** — `detect_pois` (and
  `detect_fuel_stops`) project every named waypoint to its *nearest* route vertex
  with no max-distance check, so a waypoint that isn't actually near the route
  still renders at whatever vertex is closest. On a sub-route slice this stacks
  out-of-window waypoints onto the start/end vertex (seen while rendering a 6 mi
  twixtmas clip that carried all 13 full-route waypoints at 0.0/5.9 mi).
  Consider a proximity threshold (cf. the 1.0 mi cap in `_label_near`) so distant
  waypoints are dropped, and de-conflict multiple waypoints landing on one mile.
- **Rider-sequence waypoint name prefixes** — many GPX waypoints carry an authored
  ordering prefix (twixtmas uses day×10+stop: `11 SilverCreek` … `34 Livermore`;
  others `01 Evergreen`, `76 Bodega Bay`). These render verbatim today; decide
  whether to keep, strip, or surface them (e.g. as a stop number) on the strip.

## Rendering (open)

- **Strip label de-collision** — alternating sides + repulsion is much better but
  still heuristic; very dense lanes may want leader routing or per-lane caps
  beyond the current auto-fit pagination.

## Service hardening (future)

- Distributed (Redis-backed) rate limiting + quotas (current limiter is
  per-process, so quotas are per-replica). Optional API-key auth already exists.
- Per-container memory limits + bounded queue depth (see security-audit §8).
- Metrics / observability.
