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
- Make sure waypoints are displayed and labeled on the strip, if they are real waypoints or non-via non-shaping points.

- Use emoji or proper symbols to indicate fuel, ferry boarding/disembarking, and food stops. Include milage.

- When displaying unpaved segments, make the ribbon brown and dashed between the start and end of the unpaved segment. Label the beginning and end of unpaved segments similar to waypoints.

- When displaying ferry segments, make the ribbon blue and dashed between the start and end of the ferry segment. Label the beginning and end of ferry segments similar to waypoints.


## Service hardening (future)

- Distributed (Redis-backed) rate limiting + quotas (current limiter is
  per-process, so quotas are per-replica). Optional API-key auth already exists.
- Per-container memory limits + bounded queue depth (see security-audit §8).
- Metrics / observability.
