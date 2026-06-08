# GPXSheet — TODO

Planned work, queued. As-built status lives in [PRODUCT.md](PRODUCT.md);
architecture/context and conventions in [CLAUDE.md](CLAUDE.md).

## Phase 1 — remaining

- **`validate` CLI command** — still a stub (the only remaining Phase-1 gap).
  Should detect fuel-gap-exceeds-range, unpaved segments, seasonal-closure risk,
  ferry crossings (see PRODUCT.md "Validate").
- **PyPI `twine upload`** — maintainer step (needs PyPI credentials). The package
  already builds clean and `twine check` passes.
- **Vault note** — wire one via `/project-init` when the Obsidian MCP is responsive.

## Phase 2 — features (requested)

- **Security audit (architecture + code, esp. the service) — required before
  public internet exposure.** Cover: auth/API keys + per-key quotas; XML upload
  safety (XXE/billion-laughs — check whether gpxpy uses lxml; harden the parser);
  SSRF & egress from OSM/Overpass fetches; upload validation beyond size (content
  sniffing, point/length caps that reject monster routes early); DoS/resource
  limits (worker time/memory, queue depth); MinIO creds + bucket policy +
  presigned expiry; CORS + security headers (HSTS/CSP/etc.); secrets via
  env/secret-store not defaults; `pip-audit` / dependency CVEs; run the worker
  non-root (already) and least-privilege. Produce a findings doc + fixes.
- **Preview image output** — a single overview image (PNG/JPEG), no pagination:
  reuse the strip renderer (`gpxsheet.strip`) for the whole route. Add a CLI flag
  and a service endpoint (e.g. `POST /v1/preview` returning an image, or a
  `format=png` option on jobs). Fast/low-res; good for a UI thumbnail.
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
- **Junction-degree detection** — catch nameless forks (OSM node topology).
- **Roads/directions NOT taken at a junction** — at each decision, surface the
  other branch(es) you do *not* take to disambiguate forks, roundabouts, and
  multi-way intersections (e.g. a ghosted stub). Needs OSM node degree + the
  junction's other edges (builds on junction-degree detection).
- **Roundabout exit numbers** — detect roundabouts (OSM `junction=roundabout` /
  circular ways) and emit "take the Nth exit" + a roundabout glyph instead of a
  plain turn; make roundabouts part of the decision output.

## Service hardening (future)

- Auth / API keys + quotas.
- Metrics / observability.
- Distributed (Redis-backed) rate limiting (current limiter is per-process).
