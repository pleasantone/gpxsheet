# Deploying GPXSheet

GPXSheet ships a single self-contained Docker image (the SPA is built inside the
image), so it runs anywhere that can build and run a `Dockerfile`. The reference
public deployment is a **Hugging Face Space**.

## Simple mode vs. full mode

The service picks its components from the environment in
`src/gpxsheet/service/app.py` (`default_components()`):

| Mode | Trigger | Job store | Storage | Runner |
|------|---------|-----------|---------|--------|
| **Simple** | `GPXSHEET_REDIS_URL` unset | in-memory | local disk (`GPXSHEET_RESULTS_DIR`, default `/tmp/gpxsheet-results`) | `EagerRunner` (renders synchronously in-request) |
| **Full** | `GPXSHEET_REDIS_URL` set | Redis | MinIO/S3 | Dramatiq worker (async) |

Simple mode needs no Redis, MinIO, or worker process — ideal for a single free
container. Renders happen in the request and the client downloads the result
immediately, so the ephemeral `/tmp` store is sufficient.

## Hugging Face Space (reference deployment)

The free CPU tier (2 vCPU / 16 GB RAM) handles the geo stack
(matplotlib + osmnx + geopandas + shapely) comfortably and has no per-request
timeout, so even slow dense-urban Overpass renders complete.

Deployment is automated: `.github/workflows/deploy-hf.yml` syncs `main` to the
Space on every push (via `hf upload`), and the Space rebuilds the image from the
repo's `Dockerfile`. The Space's root `README.md` (with the required HF
frontmatter) comes from `deploy/huggingface/README.md`.

Auth uses **Trusted Publishing (OIDC)** — there is **no `HF_TOKEN` secret** to
store or rotate. The job proves its identity with a GitHub OIDC token, which the
`hf` CLI exchanges for a short-lived (1h), Space-scoped Hugging Face token.

### One-time setup

1. Create a free [Hugging Face](https://huggingface.co/join) account.
2. Create a new **Space** → SDK **Docker** → e.g. `gpxsheet`. The first deploy
   overwrites its contents, so the starter files don't matter.
3. On the Space's **Settings → Trusted Publishers**, add a **GitHub Actions**
   publisher with these claims (all must match exactly):
   - `repository` = `<owner>/gpxsheet` (e.g. `pleasantone/gpxsheet`)
   - `branch` = `main`
   - `workflow` = `deploy-hf.yml`
4. In the GitHub repo (**Settings → Secrets and variables → Actions → Variables**),
   add **variable** `HF_SPACE` = `<user>/<space>` (e.g. `pleasantone/gpxsheet`).
5. Push to `main` (or run the **Deploy to Hugging Face Space** workflow manually).
   The workflow no-ops until `HF_SPACE` is set, so it's safe to merge beforehand.

The Space builds (a few minutes for the first build) and serves the UI at its
root URL, with the API docs at `/docs` and a liveness probe at `/healthz`.

### Access control

By default a deployment runs **open** (no API keys) with the built-in rate limit
(`GPXSHEET_RATE_LIMIT_PER_MIN`, default 60/min). Setting `GPXSHEET_API_KEYS`
(comma-separated) requires every request to present a key, via either
`X-API-Key: <key>` or `Authorization: Bearer <key>`.

#### First-party SPA + API-key escape hatch (the reference Space)

The reference Space locks the raw API behind a key **but lets its own bundled web
app work without one**. This is enabled with two env vars:

- `GPXSHEET_API_KEYS` — a strong random key, set as a **secret** (never committed).
- `GPXSHEET_TRUSTED_ORIGINS` — the Space's own origin, e.g.
  `https://<user>-<space>.hf.space`, set as a plain **variable**.

When `GPXSHEET_TRUSTED_ORIGINS` is set, a **same-origin browser request** (the
served SPA) is trusted without a key; everyone else must present a valid
`GPXSHEET_API_KEYS` key. First-party requests are recognised from browser-set
headers (`Sec-Fetch-Site: same-origin`, falling back to an `Origin`/`Referer`
origin in the trusted list).

> **Security note.** A browser SPA cannot hold a real secret, so this is a *soft*
> lock: it stops casual/anonymous direct API use and enables per-key rate limits
> and rotation, but a determined non-browser client can spoof those headers. The
> supported programmatic path is an API key. For true access control you'd need a
> server-side proxy that holds the secret, or per-user login — out of scope here.

This behaviour is **opt-in** and configured only on the deployment. Self-hosters
who leave `GPXSHEET_TRUSTED_ORIGINS` unset keep the standard behaviour: open if no
keys are set, key-required for everyone if `GPXSHEET_API_KEYS` is set.

Set both on the reference Space with the `hf` CLI (the key stays out of git):

```bash
KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
hf spaces secrets add <user>/<space> --secrets GPXSHEET_API_KEYS="$KEY"
hf spaces variables add <user>/<space> --env GPXSHEET_TRUSTED_ORIGINS="https://<user>-<space>.hf.space"
```

## Testing the image locally

Build and run exactly what the Space runs:

```bash
docker build -t gpxsheet .
docker run --rm -p 8000:8000 gpxsheet
```

Then verify:

```bash
curl -s localhost:8000/healthz        # -> {"status":"ok"}
open http://localhost:8000/           # SPA loads (not Swagger) => static baked in
```

Upload `examples/sample_route.gpx` through the UI and confirm a PDF renders. (That
route is offshore/synthetic, so it exercises the OSM-failure → geometry-only
fallback without any network dependency.)

## Other hosts

The same image runs on any container host (Google Cloud Run, Fly.io, a VPS,
etc.). For a host with scale-to-zero, expect a cold-start delay on the first
request while the image boots. Set `GPXSHEET_RESULTS_DIR` to a writable path; for
full mode, additionally set `GPXSHEET_REDIS_URL` and the `GPXSHEET_MINIO_*` vars
(see `docker-compose.yml`).
