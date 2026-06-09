# GPXSheet security audit

Scope: the GPXSheet library, CLI, and especially the FastAPI web service
(`src/gpxsheet/service/`), reviewed against the Phase 2 audit checklist in
[TODO.md](https://github.com/pleasantone/gpxsheet/blob/main/TODO.md) ahead of
public-internet exposure.

Date: 2026-06-08. Audited at version 0.1.0.

Legend: **Fixed** = remediated in code; **Mitigated** = bounded but residual
risk remains; **Deployment** = must be handled by the operator (documented, not
enforceable in code).

---

## Summary of changes made

| Area | Finding | Severity | Status |
| --- | --- | --- | --- |
| XML safety | XXE / entity-expansion if lxml backend is present | High | **Fixed** |
| AuthN | No authentication on any endpoint | High | **Fixed** (optional) |
| Upload validation | Only a byte cap; no content sniff or point cap | Medium | **Fixed** |
| SSRF / egress | Client-triggered outbound Overpass calls | Medium | **Mitigated** |
| Info leak | Worker exception text returned to clients | Medium | **Fixed** |
| Secrets | Default `minioadmin` creds could reach prod | High | **Fixed** |
| Headers / CORS | No security headers; CORS undefined | Medium | **Fixed** |
| DoS | Synchronous endpoints; unbounded route size | Medium | **Mitigated** |
| Dependencies | No CVE gate in CI | Low | **Fixed** |
| Least privilege | Worker already runs non-root | — | OK |

---

## 1. XML upload safety (XXE / billion-laughs) — **Fixed**

`gpxpy` selects an XML backend at import time: **lxml if installed, otherwise the
stdlib `xml.etree`/expat parser**. Tested empirically:

- Stdlib backend (current default — lxml is not a dependency): external entities
  raise `undefined entity`, and Python 3.13+ expat enforces an input-amplification
  limit, so both XXE and billion-laughs are already blocked.
- **lxml backend**: lxml's default parser sets `resolve_entities=True`, so a
  malicious `<!DOCTYPE>`/`<!ENTITY>` would be a live XXE / entity-expansion
  vector. lxml can arrive transitively, so relying on "we don't install it" is
  fragile.

**Fix:** `gpx.load_route()` now rejects any document containing a `<!DOCTYPE` or
`<!ENTITY` declaration *before* parsing (`gpx._reject_unsafe_xml`). Legitimate
GPX never carries a DTD, so this is backend-independent defense in depth and
protects the CLI as well as the service. Covered by
`tests/test_service_security.py::test_load_route_rejects_doctype`.

## 2. Authentication & per-key quotas — **Fixed (opt-in)**

Previously every endpoint was unauthenticated. Added optional API-key auth:
set `GPXSHEET_API_KEYS` (comma-separated). When set, all `/v1/*` endpoints
require a matching `X-API-Key` or `Authorization: Bearer <key>`; the rate limiter
then keys on the API key instead of the client IP, giving per-key quotas. When
unset, the service stays open (single-process dev convenience).

Result downloads (`/v1/jobs/{id}/result`) require auth when keys are configured,
so rendered PDFs aren't world-readable by job ID. Job IDs remain unguessable
(`uuid4`), acting as a capability when auth is disabled.

**Object-level authorization (BOLA):** when keys are configured, a job records the
identity that created it and `GET /v1/jobs/{id}` and `.../result` return `404`
(not `403`, so IDs aren't confirmable) to any other key. The result cache is also
keyed by identity, so identical inputs from different keys never share a job.

> **Deployment:** for a public deployment, set `GPXSHEET_API_KEYS`. Distributed
> (Redis-backed) quotas are still future work — the limiter is per-process, so
> behind multiple API replicas the effective limit is `replicas × limit`.

## 3. Upload validation beyond size — **Fixed**

`read_gpx()` previously enforced only `GPXSHEET_MAX_UPLOAD_BYTES` (25 MiB). Added:

- **Content sniff:** the payload must contain a `<gpx` root marker, else `400`.
- **Point cap:** counts `<trkpt>`/`<rtept>` tags and rejects routes above
  `GPXSHEET_MAX_POINTS` (default 500 000) with `413`, *before* parsing/rendering,
  so a monster route can't tie up a worker for minutes.

## 4. SSRF & egress from OSM/Overpass — **Mitigated**

OSM enrichment (`enrich.py` via osmnx) issues outbound HTTP to a fixed Overpass
endpoint; the client cannot inject the URL, so there is no classic SSRF
surface. The residual risk is *amplification*: enrichment runs on every request
and a large/dense route triggers slow outbound work.

**Mitigations:** rate limiting + the async job queue + a 20-minute Dramatiq
`time_limit` + the upload size/point caps bound it. Operators that must prevent
outbound OSM should restrict egress at the network layer.

> **Deployment:** restrict the container's egress (network policy / firewall) to
> the Overpass and OSM tile/Nominatim hosts you actually use.

## 5. Information leakage in job errors — **Fixed**

`process_job` previously stored `f"{type(exc).__name__}: {exc}"` on the job,
which is returned to clients in `JobStatus.error` — that could leak temp paths,
Overpass URLs, or library internals. Now only `ValueError` (intentional
input-validation messages such as the DTD rejection) is echoed; any other
exception is logged server-side and reported to the client as a generic
`"internal render error"`.

## 6. MinIO credentials & bucket policy — **Fixed + Deployment**

The compose file and `settings.minio_config()` default to `minioadmin` /
`minioadmin`. The production path (`create_app` when `GPXSHEET_REDIS_URL` is set)
now **refuses to boot** if either MinIO credential is still the default
(`_guard_prod_secrets`). Downloads use short-lived presigned GET URLs
(`url_expiry_seconds=3600`); the bucket is created without a public policy, so
objects are reachable only via those signed URLs.

> **Deployment:** supply real `GPXSHEET_MINIO_ACCESS_KEY`/`_SECRET_KEY` from a
> secret store; keep the bucket private; serve MinIO over TLS
> (`GPXSHEET_MINIO_SECURE=1`). Tighten presign expiry if download links are
> shared.

## 7. CORS & security headers — **Fixed**

Added a response-header middleware applying `X-Content-Type-Options: nosniff`,
`X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and a strict
`Content-Security-Policy: default-src 'none'; frame-ancestors 'none'` (the API
serves only JSON/PDF/PNG). `Strict-Transport-Security` is sent when
`GPXSHEET_ENABLE_HSTS=1` (enable only behind TLS). CORS is **deny by default**
(same-origin); set `GPXSHEET_CORS_ORIGINS` to an explicit allow-list for the
future browser front end — never `*` with credentials.

## 8. DoS / resource limits — **Mitigated**

- Render jobs run off the request path (Dramatiq) with a 20-minute `time_limit`
  and `max_retries=0`.
- The point cap (§3) rejects oversized routes early.
- Every operation (render, analyze, validate) is now a queued job, so no request
  worker is held for the slow work on the prod path.
- **Residual:** the dev/eager path still runs jobs inline — a slow route can
  occupy a request worker there. The byte + point caps bound this; for heavy
  public use, set per-container memory limits (e.g. compose `mem_limit`) plus a
  bounded queue.

> **Deployment:** cap worker memory at the container level; run multiple workers
> behind a bounded queue; put a reverse-proxy request-body limit in front as a
> second line of defense for the byte cap.

## 9. Dependency CVEs — **Fixed**

`pip-audit` reports no known vulnerabilities at audit time. Added an `audit` job
to CI (`.github/workflows/ci.yml`) that installs the full extras and runs
`pip-audit`, so a newly disclosed CVE in a runtime dependency fails the build.

## 10. Least privilege — **OK**

The Docker image already creates and runs as a non-root `app` user. The worker
needs only Redis + MinIO; no extra capabilities are granted.

---

## Operator checklist (public deployment)

- [ ] Set `GPXSHEET_API_KEYS`; distribute keys out-of-band.
- [ ] Set real MinIO credentials (boot guard enforces this on the prod path).
- [ ] Serve behind TLS; set `GPXSHEET_ENABLE_HSTS=1` and
      `GPXSHEET_MINIO_SECURE=1`.
- [ ] Set `GPXSHEET_CORS_ORIGINS` only if a browser front end needs it.
- [ ] Restrict container egress to the Overpass/OSM hosts you use.
- [ ] Set a reverse-proxy body-size limit and per-container memory limits.
- [ ] Tune `GPXSHEET_RATE_LIMIT_PER_MIN`, `GPXSHEET_MAX_UPLOAD_BYTES`,
      `GPXSHEET_MAX_POINTS` for your traffic.
