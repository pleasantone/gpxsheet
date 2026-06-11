# Development Workflow

GPXSheet has two backend dev modes and one frontend dev server. Mix and match
depending on what you're working on.

---

## Quick reference

| Goal | Commands |
|---|---|
| Edit frontend only | `make dev-api` + `make dev-ui` |
| Edit frontend + backend | `make infra` + `make dev-api-full` + `make dev-worker` + `make dev-ui` |
| Edit backend only (no UI) | `make dev-api` (or `dev-api-full` for real queue) |
| Verify the full built product | `make frontend` then `make dev-api` or `docker compose up --build` |

---

## Mode 1 — Simple (EagerRunner, no deps)

```bash
make dev-api    # uvicorn --reload on :8000
make dev-ui     # Vite on :5173, proxies /v1/ to :8000
```

**How it works:** The API runs in "dev path" — no Redis or MinIO. Jobs execute
synchronously in the same process (`EagerRunner`) and results are stored on the
local filesystem under `/tmp/gpxsheet-results`. The `POST /v1/render` response
comes back with `status: done` immediately (no polling needed).

**What it's good for:**
- Frontend iteration — form interactions, layout, polling UI
- Python logic changes (analysis, strip renderer, PDF layout)
- Running the test suite

**What it doesn't test:**
- Real async job queue behavior (Dramatiq worker picking up jobs)
- MinIO result storage and presigned URL redirects (303 responses)
- Multi-process separation (API and worker are one process here)

**Prerequisites:** just Python + `.venv`.

---

## Mode 2 — Full stack (Redis + MinIO in Docker, Python on host)

```bash
# One-time: start infrastructure containers
make infra

# Three terminals:
make dev-api-full   # uvicorn --reload on :8000, prod path
make dev-worker     # Dramatiq worker
make dev-ui         # Vite on :5173
```

**How it works:** `make infra` starts Redis and MinIO in Docker
(`docker-compose.infra.yml`). `dev-api-full` and `dev-worker` source `.env.dev`
which points them at the containers, activating the prod code path (Dramatiq job
queue, MinIO result storage). Python processes run on the host for `--reload` and
debugger access.

**What it's good for:**
- Testing the full async flow: submit → queued → worker picks up → done
- Testing MinIO presigned URL redirects (the `GET …/result` 303 response)
- Verifying job deduplication / caching
- Frontend polish with realistic latency

**What changes without rebuild:**
- Python source (`--reload` on the API; restart `dev-worker` manually)
- Frontend source (Vite HMR, instant)

**Prerequisites:** Docker Desktop running.

```bash
make infra-down     # stop containers when done
```

**Ports (all loopback-only):**
- API: http://localhost:8000 (and http://localhost:5173 via Vite proxy)
- MinIO S3: localhost:9000
- MinIO console: http://localhost:9001 (devkey / devsecret1)
- Redis: localhost:6379

---

## Mode 3 — Full prod stack in Docker

```bash
docker compose up --build
```

Runs api + worker + redis + minio all in containers (`docker-compose.yml`).
Used to verify the complete built product, including the compiled frontend. The
frontend must be built first (`make frontend`) to appear at `/`; otherwise the
API serves Swagger at `/docs`.

This is the closest to a production deployment. Python changes require
`docker compose up --build` (no hot reload).

---

## Frontend build

The SPA in `frontend/` is **gitignored when built** — `src/gpxsheet/service/static/`
is excluded from version control. Build it explicitly:

```bash
make frontend       # npm ci && npm run build → service/static/
```

The FastAPI app serves the built files at `/` via a `StaticFiles` mount. Without
the build, `GET /` falls through to Swagger UI at `/docs`. The `make dev-ui`
workflow (Vite dev server) does **not** need a build — it serves the SPA
directly from source with HMR.

---

## Environment files

`.env.dev` — committed, dev-only throwaway credentials for `docker-compose.infra.yml`.
Used automatically by `make dev-api-full` and `make dev-worker` (sourced in a
subshell, not exported to your shell session).

The prod `docker-compose.yml` uses separate `minioadmin` defaults which are
blocked by `_guard_prod_secrets()` in `app.py` — those credentials are only
valid inside the Docker network where you know what you're doing.

---

## Switching between modes

Modes 1 and 2 share port 8000. You can't run both at once. Stop one before
starting the other. Mode 3 (`docker compose up`) also uses port 8000; stop
`dev-api-full` first.

The Vite dev server (`make dev-ui`) works with any mode — it just proxies
`/v1/` to whatever is on port 8000.
