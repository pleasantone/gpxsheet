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

osmnx caches Overpass responses to `./cache` by default, which fails when the
container runs as a non-root user with a non-writable working dir (enrichment then
silently degrades to geometry-only). The image sets `GPXSHEET_OSM_CACHE_DIR=/tmp/
gpxsheet-osm-cache` so the cache lands somewhere writable; point it elsewhere if you
mount a persistent volume. When that var is set, `/readyz` verifies the dir is
writable (503 otherwise) and startup logs an error if not — so a misconfigured cache
fails loudly instead of silently degrading every render to geometry-only.

`overpass-api.de` round-robins across several mirrors, and osmnx pins one IP per
process; if that mirror is down, every Overpass query fails and enrichment silently
degrades to geometry-only (which floods twisty roads with false turns). Set
`GPXSHEET_OVERPASS_URL` to point osmnx at a healthy endpoint — another public mirror
(e.g. `https://overpass.kumi.systems/api`) or a self-hosted instance — when the
default is flaky. It governs all Overpass traffic (the road graph and the fuel/feature
queries); unset, osmnx's default `https://overpass-api.de/api` stands.

## Hugging Face Space (reference deployment)

The free CPU tier (2 vCPU / 16 GB RAM) handles the geo stack
(matplotlib + osmnx + geopandas + shapely) comfortably and has no per-request
timeout, so even slow dense-urban Overpass renders complete.

Deployment is automated: `.github/workflows/deploy-hf.yml` syncs `main` to the
Space (via `hf upload`) **after the CI workflow passes** on that commit, and the
Space rebuilds the image from the repo's `Dockerfile`. (It runs via `workflow_run`
on CI completion; a failed CI run skips the deploy. `workflow_dispatch` is a manual
override.) The Space's root `README.md` (with the required HF
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
app work without one**. Enabled with:

- `GPXSHEET_API_KEYS` — a strong random key, set as a **secret** (never committed).
- `GPXSHEET_TRUST_FIRST_PARTY=1` — set as a plain **variable**, turns the feature on.
- `GPXSHEET_SESSION_SECRET` — *optional* HMAC secret for signing first-party tokens.
  If unset, a random per-process secret is used (fine for a single replica; set it
  to share trust across replicas).

How it works: when enabled, the backend serves `index.html` with a **server-signed,
expiring first-party token** injected as a `<meta name="gpxsheet-fp">` tag (a meta
tag, not an inline script, so the page's `default-src 'self'` CSP doesn't block it).
The SPA reads it and sends it back as the `X-First-Party` header, and the backend
accepts a valid token in lieu of an API key. Everyone else must present a `GPXSHEET_API_KEYS` key
(`X-API-Key` or `Authorization: Bearer`). A token is delivered via the rendered
page (not a bare API endpoint), so obtaining one requires loading the app, and it
cannot be forged without the server secret.

We use an injected token (a request header set by JS) rather than a cookie on
purpose: HF serves the Space inside a cross-site iframe at
`huggingface.co/spaces/…`, where `SameSite` cookies are not sent — a cookie would
break the embedded view, whereas a same-origin request header works everywhere.

> **Security note.** This is still a *soft* lock, not a true boundary: anyone who
> loads the page can read the token and replay it until it expires. It stops casual
> direct API use, enables per-key rate limits + rotation, and is no longer a
> single-header bypass — but a determined scraper can refresh a token. The
> supported programmatic path is an API key. True access control would need a
> server-side proxy or per-user login — out of scope here. CSRF is not a concern:
> state-changing routes only render an uploaded GPX (no per-user data to act on).

**Opt-in**, configured only on the deployment. Self-hosters who leave
`GPXSHEET_TRUST_FIRST_PARTY` unset keep the standard behaviour: open if no keys are
set, key-required for everyone if `GPXSHEET_API_KEYS` is set.

Set on the reference Space with the `hf` CLI (the key stays out of git):

```bash
KEY=$(python -c "import secrets; print(secrets.token_urlsafe(32))")
hf spaces secrets add <user>/<space> --secrets GPXSHEET_API_KEYS="$KEY"
hf spaces variables add <user>/<space> --env GPXSHEET_TRUST_FIRST_PARTY=1
```

#### Embedding (HF Spaces iframe)

By default the app denies all framing (`X-Frame-Options: DENY` + CSP
`frame-ancestors 'none'`) — good clickjacking protection for a self-hosted
deployment. The HF Spaces page (`huggingface.co/spaces/…`) renders the app in an
**iframe**, so the Space must allow `huggingface.co` to frame it, via
`GPXSHEET_FRAME_ANCESTORS` (comma/space-separated origins). When set, the app drops
`X-Frame-Options` (which can't allowlist an origin) and lets CSP govern:

```bash
hf spaces variables add <user>/<space> \
  --env GPXSHEET_FRAME_ANCESTORS="https://huggingface.co https://*.hf.space"
```

Leaving it unset keeps the deny-all default. (Clickjacking risk is negligible here
— the app is a stateless GPX renderer with no per-user accounts or sensitive
actions — but the allowlist keeps framing scoped to HF.)

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
route is offshore/synthetic: OSM enrichment queries Overpass for its bbox, gets no
results, and falls back to geometry-only. To skip the Overpass round-trip entirely
— e.g. air-gapped, rate-limited, or for a fast offline check — set
`GPXSHEET_DISABLE_OSM=1`, which forces geometry-only analysis with no network call.
The CI smoke test uses this.)

## Other hosts

The same image runs on any container host (Google Cloud Run, Fly.io, a VPS,
etc.). For a host with scale-to-zero, expect a cold-start delay on the first
request while the image boots. Set `GPXSHEET_RESULTS_DIR` to a writable path; for
full mode, additionally set `GPXSHEET_REDIS_URL` and the `GPXSHEET_MINIO_*` vars
(see `docker-compose.yml`).
