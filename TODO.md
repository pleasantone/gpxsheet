# GPXSheet — TODO

Planned work, queued. As-built status lives in [PRODUCT.md](PRODUCT.md);
architecture/context and conventions in [CLAUDE.md](CLAUDE.md).

## Phase 2 — features (requested)

- **Security audit (architecture + code, esp. the service) — DONE.** Findings +
  fixes in [docs/security-audit.md](docs/security-audit.md): XML XXE/entity guard
  in the parser, optional API-key auth + per-key quotas, content sniff + point
  cap, OSM-egress toggle, error-leak sanitization, prod default-creds boot guard,
  security headers + CORS, and a `pip-audit` CI job. Remaining residuals tracked
  under "Service hardening" below (distributed quotas; move preview/analyze off
  the request path; container memory limits).
- **Front end for the service** — a small, secure web UI (upload GPX → choose
  profile/orientation/paper/OSM → live preview image → download PDF). Must be
  hardened for **public internet exposure** (ties into the security audit: auth,
  CSRF, CSP, rate limits, no creds in the browser, served behind TLS/reverse
  proxy). Decide SPA vs server-rendered; keep deps minimal.
- **Revisit decision-points-per-strip design** — pros/cons of removing the fixed
  decision cap per strip and instead fitting as many decision points on a single
  strip as needed to fill the area (while leaving appropriate whitespace).

## Rendering / analysis polish

- **Strip label de-collision** (`_place_labels_with_leaders`) is heuristic; can
  bunch on very dense routes. Possible: leader routing, smarter side selection,
  per-page label caps.
- **Stylized "curl"** — same-direction turns accumulate; long routes can spiral.
  May need gentle relaxation toward horizontal.
- **Stylized-angle / compression tuning** — revisit `CONTINUE/NORMAL/SHARP_TURN_DEG`
  and `MIN_SEGMENT_LEN`/`DIST_SCALE` against more real routes.
- **PDF: fuel stop at mile 0 overlaps the START label** — small offset needed.
- **Reassurance-label prominence** (towns render small/gray) — revisit.
- **OSM determinism near `MIN_ROAD_RUN_MILES`** — a ~0.3 mi run flipped a decision
  in/out across runs; consider hysteresis.
- **Down-weight straight "Continue onto"** name changes (residential noise);
  needs a ground-truth set.
- **Junction-degree detection** — *emit* decisions at nameless forks (OSM node
  topology). Node-degree reading now exists (`gpxsheet.junctions` +
  `enrich._junction_degree`, used for roads-not-taken); this remaining piece is
  promoting a high-degree node with no road-name change into its own decision.
- **Roads-not-taken / roundabout tuning** — both now implemented (ghosted branch
  stubs + roundabout "Nth exit" glyph). Validate exit-counting and branch
  selection against real tracks with live OSM; revisit `BRANCH_MATCH_TOL_DEG` and
  the ring-traversal heuristics on multi-chunk routes.

## Service hardening (future)

- Distributed (Redis-backed) rate limiting + quotas (current limiter is
  per-process, so quotas are per-replica). Optional API-key auth already exists.
- Move `/v1/preview` and `/v1/analyze` off the request path onto the job queue.
- Per-container memory limits + bounded queue depth (see security-audit §8).
- Metrics / observability.
