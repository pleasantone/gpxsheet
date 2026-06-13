# 09 — Deployment (docker-compose, self-hosted)

One-box, self-hostable. Parent: [`../SPEC.md`](../SPEC.md). Pulls together every
service.

## Services (`app/deploy/docker-compose.yml`)

| Service | Image | Notes |
|---|---|---|
| `api` | build `app/backend` | FastAPI/Uvicorn; serves `/v1`, the built PWA at `/`, and proxies `/tiles`, `/maps` to tileserver (so the PWA is same-origin for offline caching). |
| `worker` | same image as `api` | Runs the job consumer (`convoy.jobs.worker`). Scale with `--scale worker=N`; concurrency 1/process (renderers). |
| `postgres` | `postgis/postgis:16` | data + PostGIS. Volume `pgdata`. |
| `redis` | `redis:7` | job queue + ephemeral computed cache. |
| `minio` | `minio/minio` | artifacts + offloaded route points. Volume `minio`. |
| `overpass` | `wiktorn/overpass-api` | enrichment; seeded from `REGION_PBF`. Big volume. |
| `valhalla` | `ghcr.io/gis-ops/valhalla` | map-match + routing; tiles built from `REGION_PBF`. Big volume. |
| `tileserver` | `maptiler/tileserver-gl` | vector tiles + touring style from `REGION_MBTILES`. |
| `seed` | build `app/deploy` (one-shot) | loads Overpass, builds Valhalla tiles, places mbtiles; idempotent (marker volume). |
| `mailhog` | `mailhog/mailhog` | **dev profile only** — magic-link inbox at :8025. |

`api`/`worker` share one image (the backend). Frontend is built (`vite build`)
into the image's static dir (served by `api`), mirroring gpxsheet.

## Bootstrap

```bash
cd app/deploy
cp .env.example .env            # set REGION_*, APP_URL, SMTP_URL, secrets
docker compose --profile dev up -d         # brings up mailhog too
docker compose run --rm seed               # one-time: load OSM/valhalla/tiles
# api waits on /readyz (db, redis, minio, overpass, valhalla, tileserver)
```
`make` targets mirror gpxsheet: `make up`, `make seed`, `make migrate`,
`make dev` (api+worker+vite), `make down`.

## Config / env (`.env`)

```
APP_URL=https://convoy.example.com
DATABASE_URL=postgresql+asyncpg://convoy:…@postgres/convoy
REDIS_URL=redis://redis:6379/0
S3_ENDPOINT=http://minio:9000  S3_BUCKET=convoy  S3_KEY=…  S3_SECRET=…
OVERPASS_URL=http://overpass/api   VALHALLA_URL=http://valhalla:8002
TILES_URL=http://tileserver:8080
REGION_PBF=/data/norcal.osm.pbf    REGION_MBTILES=/data/norcal.mbtiles
SMTP_URL=smtp://mailhog:1025       MAIL_FROM=rides@convoy.example.com
SECRET_KEY=…                       OFFLINE=0   LIVE_DISABLED=0
ENGINE_VERSION=1
```

## Migrations

`api` runs Alembic on start (or a `migrate` one-shot). Forward-only in prod.

## Resource notes (call out to the operator)

- Overpass + Valhalla + tiles dominate disk/RAM and scale with the region.
  Document per-region footprint (a US-state extract is GBs of DB + tiles + a
  Valhalla tile build of many minutes). Default region = owner's choice (SPEC §8);
  provide a documented **region-swap** procedure (replace `REGION_*`, re-run
  `seed`).
- For a small club, a single box suffices. Scale `worker` for render/analyze
  throughput; Postgres/MinIO are light at this scale.

## Production hardening (carry from gpxsheet's service)

- TLS at a reverse proxy (Caddy/Traefik) in front of `api`.
- Rate-limit auth + uploads; upload-size cap; per-identity job ownership.
- Presigned MinIO URLs signed against a host-reachable public endpoint.
- `/healthz` (live) + `/readyz` (deps reachable) for orchestration.
- Backups: **`postgres` is the irreplaceable data** (plans/users/stops) — routes
  and artifacts are regenerable. Document `pg_dump` + MinIO bucket backup.

## CI

- Backend: ruff + mypy + pytest (offline, fixture-replayed geo/live) — release
  gate, like gpxsheet.
- Frontend: tsc + eslint + Playwright (needs the stack or mocked API).
- Build + push the combined image; compose pulls it.

## Acceptance criteria

- `docker compose up` + `seed` from clean → upload a GPX → analyze → plan →
  share, fully offline of the public internet (self-hosted geo + keyless live).
- `/readyz` red until all deps up; green after `seed`.
- Region swap documented and works (re-seed → new area analyzes).
