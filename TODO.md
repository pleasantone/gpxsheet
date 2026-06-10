# GPXSheet — TODO

Planned work, queued. As-built status lives in [docs/product.md](docs/product.md);
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

## Service hardening (future)

- Distributed (Redis-backed) rate limiting + quotas (current limiter is
  per-process, so quotas are per-replica). Optional API-key auth already exists.
- Per-container memory limits + bounded queue depth (see security-audit §8).
- Metrics / observability.
