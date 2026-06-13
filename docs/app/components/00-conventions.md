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

## Graceful degradation (non-negotiable)

Any external dependency (Overpass, Valhalla, weather, fire) being down must
**degrade**, never fail the request: skip the enriched piece, attach a warning
`Finding`, log it. The plan still saves and renders. Mirror gpxsheet's
`looks_sparse` / Overpass-failure fallback to geometry-only analysis.

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
