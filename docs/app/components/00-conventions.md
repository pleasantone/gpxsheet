# 00 — Conventions (read before building any component)

Shared rules so independently-built components fit together. Parent: [`../SPEC.md`](../SPEC.md).

## Repo layout (new program under `app/`)

```
app/
  backend/            # Python package: convoy
    convoy/
      analysis/       # the rewritten engine (match, decisions, segments, fuel, timing)
      api/            # FastAPI routers
      models/         # SQLAlchemy ORM + Pydantic schemas
      live/           # weather/fire providers
      artifacts/      # PDF/GPX/QR builders
      group/          # group math (fuel, timing, bailouts)
      jobs/           # queue + worker entrypoints
      geo/            # Overpass + Valhalla + tile clients
      core/           # config, db, storage, auth, units, ids
    alembic/          # migrations
    tests/
    pyproject.toml
  frontend/           # React + TS + Vite PWA
  deploy/
    docker-compose.yml
    overpass/ valhalla/ tileserver/   # service configs + seed scripts
docs/app/             # these specs
```

## Language / tooling

- **Backend:** Python ≥ 3.12, FastAPI, SQLAlchemy 2.x (async), Alembic, Pydantic
  v2, `uv` or `pip`. Lint **ruff**, type-check **mypy** (strict on `convoy/`),
  test **pytest** (async). Keep parity with gpxsheet's gates (ruff+mypy+pytest).
- **Frontend:** Node 20+, React 19, TypeScript strict, Vite, Tailwind v4,
  MapLibre GL JS, `vite-plugin-pwa`. Lint eslint. E2E Playwright.

## Units & formats (hard rules)

- Internal + API numbers are **imperial floats**: miles, mph, feet, °F. Round
  for *display* only. Distances 1 decimal; the frontend has a client-side metric
  display toggle (never a server round-trip — mirrors gpxsheet).
- **Datetimes:** ISO 8601 **with offset** (`2026-06-13T08:00:00-07:00`); `null`
  when absent. Store tz-aware UTC + an IANA `timezone` field per Plan.
- **IDs:** UUIDv7 primary keys. **Tokens** (share/edit/magic-link): 128-bit,
  `secrets.token_urlsafe(16)`, stored hashed where they grant write.
- **Geometry:** WGS84 (EPSG:4326) in PostGIS `geography`; lengths via PostGIS or
  shapely-in-Python where a spatial index isn't needed.

## API conventions

- JSON everywhere except file upload (multipart) and artifact download (binary).
- Async work: `202 {job}` on submit, poll `GET /v1/jobs/{id}`, fetch
  `GET /v1/jobs/{id}/result`. Idempotent submits return the cached job (`200`).
- Errors: RFC-7807-ish `{type, title, detail, status}`. Validation → `422`.
- Auth: session cookie (httpOnly, SameSite=Lax). Public share routes need no
  auth and live under `/v1/share/{token}/…` (read-only).
- Versioned base `/v1`. Health: `/healthz`, `/readyz` (db/redis/minio/overpass/
  valhalla reachable).

## Reliability policy (two-tier — read carefully)

External dependencies split into **hard** and **soft**. This *changes* the
gpxsheet default (which degraded everything) because geometry-only decisions are
*wrong* on twisty roads — emitting them silently is worse than failing.

- **Hard (critical):** Postgres, Redis, MinIO, **Overpass**, **Valhalla
  map-matching**. Unreachable ⇒ the job **fails cleanly and clearly**:
  `503`-class error, a typed `GeoUnavailable`/`DependencyDown`, an actionable
  user message ("Route enrichment is temporarily unavailable — Overpass is not
  reachable. Try again shortly."), `/readyz` red, logged with the cause. **No
  degraded/geometry-only output is produced.**
- **Soft (optional):** weather, wildfire, and future 511/reviews. Down ⇒ skip
  that section, attach an info `Finding`, continue. Plan still computes/saves.

Two cases that are **not** errors and must not be treated as one:
1. **Sparse route** (waypoint-only `<rte>`): geometry-only is the *correct mode*,
   chosen because OSM enrichment can't help straight-line vias — not a failure.
2. **Overpass reachable but returns no features** for a corridor: valid empty
   data (e.g. genuinely no fuel), not an error.

## Providers (all external data, including OSM)

Every external source — weather, fire, **and Overpass** — implements one
**provider** shape: `filter → normalize to typed JSON → cache on disk`
(record/replay). Raw OSM geometry never enters the serialized model; only
normalized features do. Hard vs soft is a *policy flag* on the provider, not a
different code path. Env per provider (gpxsheet convention):
`<SRC>_CACHE_DIR / DISABLE_<SRC> / RECORD_<SRC> / <SRC>_BASE_URL`, umbrella
`OFFLINE`. (Disabling a *hard* provider via env is a config error in prod.)

## Instrumentation (so we can profile)

Every job emits **one `perf` log line** with a phase breakdown, e.g.
`perf job:analyze 4.2s [points=30911 cache=miss] match=1.1 enrich=2.4
decisions=0.4 fuel=0.2 render=0.1`. Hot code wraps spans:
```python
with perf.span("enrich"):
    feats = overpass.corridor_features(...)
perf.annotate(points=len(pts), cache="miss")
```
Spans outside a tracked job are ~free. Carry gpxsheet's `perf` module verbatim
in spirit. This is the cheap substitute for attaching a profiler in prod.

## Multiprocessing-ready (design now, build later)

Keep analysis **pure and side-effect-free** and split work into **independent
chunks** — per-day (`<trk>`), per-corridor-segment, per-provider-query — so a
later `ProcessPoolExecutor`/worker fan-out is a drop-in. **Do not** introduce
shared mutable global state in the analysis path (it would block this).
Renderers use global (matplotlib) state → keep them single-process; scale by
worker *processes*, never threads. v1 stays single-process for simplicity; the
seams must survive.

## Findings (shared warning type)

A single `Finding { level: "warning"|"info", code: str, message: str, mile?:
float, point?: {lat,lon} }` is produced by analysis, group math, and live
providers, and surfaced uniformly in the API, the map (markers), the briefing,
and the leader packet. Codes: `fuel`, `services`, `unpaved`, `ferry`,
`seasonal`, `dark`, `weather`, `wind`, `fire`, `closure` (later), `daylong`.

## Testing fixtures

Record/replay caches for Overpass, Valhalla, and live providers, committed and
replayed **cache-only in CI** (a miss raises, never hits the network) — copy
gpxsheet's `conftest` OSM/live cache harness. Provide `RECORD_*` env flags to
re-record. Deterministic + offline test suite is a release gate.
