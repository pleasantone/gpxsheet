"""FastAPI application factory for the GPXSheet web service."""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import time
from collections import defaultdict
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import BaseModel
from starlette.middleware.base import BaseHTTPMiddleware

from . import settings
from .jobs import (
    DramatiqRunner,
    EagerRunner,
    InMemoryJobStore,
    JobRecord,
    JobStore,
    TaskRunner,
    ThreadedRunner,
    prod_components,
)
from .models import (
    JobState,
    JobStatus,
    RenderForm,
    RenderParams,
    ReportForm,
    ReportParams,
    TableForm,
    TableParams,
)
from .storage import LocalStorage, Storage

log = logging.getLogger(__name__)

# Error responses we declare on endpoints so they show up in the OpenAPI schema.
_UPLOAD_ERRORS: dict[int | str, dict[str, Any]] = {
    400: {"description": "Empty or non-GPX upload"},
    413: {"description": "Upload or route too large"},
    429: {"description": "Rate limit exceeded"},
}
_JOB_RESPONSES: dict[int | str, dict[str, Any]] = {
    200: {"model": JobStatus, "description": "Job already complete (returned as-is)"},
    202: {"model": JobStatus, "description": "Job accepted and queued"},
    **_UPLOAD_ERRORS,
}

# A real GPX document must contain a <gpx ...> root element. Cheap content sniff
# so we reject non-GPX uploads before doing any parsing/rendering work.
_GPX_MARKER = b"<gpx"
# Counting these point tags is a cheap proxy for route size; lets us reject a
# monster route up front rather than after a multi-minute render.
_POINT_TAGS = (b"<trkpt", b"<rtept")


class _RateLimiter:
    """In-memory fixed-window per-identity limiter (per API process)."""

    def __init__(self, per_minute: int) -> None:
        self.limit = per_minute
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, identity: str) -> None:
        if self.limit <= 0:
            return
        now = time.monotonic()
        recent = [t for t in self._hits.get(identity, []) if now - t < 60.0]
        if len(recent) >= self.limit:
            # Fixed 60s window: the oldest hit clears in (60 - its age) seconds.
            retry_after = max(1, int(60.0 - (now - recent[0])))
            raise HTTPException(
                status_code=429,
                detail="rate limit exceeded",
                headers={
                    "Retry-After": str(retry_after),
                    "RateLimit-Limit": str(self.limit),
                    "RateLimit-Remaining": "0",
                    "RateLimit-Reset": str(retry_after),
                },
            )
        recent.append(now)
        self._hits[identity] = recent
        # Prune identities whose window has fully expired to prevent unbounded growth.
        self._hits = {k: v for k, v in self._hits.items() if v}


class _SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add baseline security response headers to every response."""

    def __init__(self, app, *, hsts: bool, frame_ancestors: list[str]) -> None:
        super().__init__(app)
        self._hsts = hsts
        self._frame_ancestors = frame_ancestors

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # Framing: deny by default. When an allowlist is configured (e.g. to embed
        # in the HF Spaces iframe), drop X-Frame-Options — it can't allowlist an
        # origin — and let CSP frame-ancestors govern.
        if self._frame_ancestors:
            ancestors = " ".join(self._frame_ancestors)
        else:
            ancestors = "'none'"
            response.headers.setdefault("X-Frame-Options", "DENY")
        # API routes stay locked down; SPA HTML needs script execution + blob: images.
        # style-src allows 'unsafe-inline' so the inline-rendered Table view can keep
        # the route table's `text-align` cell styles (sanitized via DOMPurify before injection);
        # script-src/default-src stay strict, so this is style-only.
        is_api = request.url.path.startswith("/v1/") or request.url.path in ("/healthz", "/readyz")
        base = (
            "default-src 'none'"
            if is_api
            else "default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'"
        )
        csp = f"{base}; frame-ancestors {ancestors}"
        response.headers.setdefault("Content-Security-Policy", csp)
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response


def _osm_cache_problem() -> str | None:
    """If GPXSHEET_OSM_CACHE_DIR is set but not creatable/writable, return why.

    Guards against the silent failure where osmnx can't write its cache and every
    render degrades to geometry-only. Only enforced when the dir is configured, so
    self-hosters who don't set it are unaffected.
    """
    cache_dir = settings.osm_cache_dir()
    if not cache_dir:
        return None
    try:
        path = Path(cache_dir)
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write-probe"
        probe.write_bytes(b"")
        probe.unlink()
    except OSError as e:
        return f"OSM cache dir {cache_dir!r} is not writable: {e}"
    return None


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


_FP_TTL_SECONDS = 12 * 3600
# Delivered as a <meta> tag (not an inline <script>): the SPA's CSP is
# default-src 'self' with no 'unsafe-inline', so an inline script would be blocked.
_FP_META = "gpxsheet-fp"


def _issue_fp_token(secret: bytes, ttl: int = _FP_TTL_SECONDS) -> str:
    """A signed, expiring first-party token: 'exp.hmac'. Issued only into the
    served SPA page, so obtaining one requires loading the app (not a bare API
    call). Unforgeable without the server secret."""
    exp = str(int(time.time()) + ttl)
    sig = hmac.new(secret, exp.encode(), hashlib.sha256).hexdigest()
    return f"{exp}.{sig}"


def _valid_fp_token(secret: bytes, token: str | None) -> bool:
    if not token:
        return False
    try:
        exp_s, sig = token.split(".", 1)
        exp = int(exp_s)
    except ValueError:
        return False
    expected = hmac.new(secret, exp_s.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expected) and time.time() < exp


def _cache_key(data: bytes, op: str, params: BaseModel, identity: str) -> str:
    # Identity is part of the key so cross-tenant requests never share a job
    # (each owner gets their own), which keeps per-job ownership consistent.
    return hashlib.sha256(
        data + b"\0" + op.encode() + b"\0" + identity.encode() + b"\0"
        + params.model_dump_json().encode()
    ).hexdigest()


def _to_params(form: BaseModel, model: type[BaseModel]) -> BaseModel:
    """Extract the plain (queue-serializable) params from a multipart form body."""
    return model(**{k: getattr(form, k) for k in model.model_fields})


def default_components() -> tuple[JobStore, Storage, TaskRunner]:
    """Prod path (Redis + MinIO + Dramatiq) if a Redis URL is set; else a single-
    process path that renders either in-request (EagerRunner) or off the request
    path on a thread pool (ThreadedRunner) when GPXSHEET_BACKGROUND_RENDER is set."""
    if settings.redis_url():
        store, storage = prod_components()
        return store, storage, DramatiqRunner()
    mem = InMemoryJobStore()
    local = LocalStorage(settings.results_dir())
    if settings.background_render():
        return mem, local, ThreadedRunner(mem, local, settings.render_concurrency())
    return mem, local, EagerRunner(mem, local)


def create_app(
    store: JobStore | None = None,
    storage: Storage | None = None,
    runner: TaskRunner | None = None,
    *,
    max_upload_bytes: int | None = None,
    max_points: int | None = None,
    rate_limit_per_minute: int | None = None,
    api_keys: frozenset[str] | None = None,
    cors_origins: list[str] | None = None,
    trust_first_party: bool | None = None,
    session_secret: str | None = None,
    frame_ancestors: list[str] | None = None,
    enable_hsts: bool | None = None,
) -> FastAPI:
    """Build the API. Pass components explicitly (tests) or let env decide."""
    prod = store is None and storage is None and runner is None and settings.redis_url()
    if store is None or storage is None or runner is None:
        store, storage, runner = default_components()
    if prod:
        _guard_prod_secrets()

    max_bytes = max_upload_bytes if max_upload_bytes is not None else settings.max_upload_bytes()
    point_cap = max_points if max_points is not None else settings.max_points()
    limiter = _RateLimiter(
        rate_limit_per_minute if rate_limit_per_minute is not None
        else settings.rate_limit_per_minute()
    )
    keys = api_keys if api_keys is not None else settings.api_keys()
    origins = cors_origins if cors_origins is not None else settings.cors_origins()
    trust_fp = trust_first_party if trust_first_party is not None else settings.trust_first_party()
    secret_str = session_secret if session_secret is not None else settings.session_secret()
    fp_secret = secret_str.encode() if secret_str else secrets.token_bytes(32)
    frames = frame_ancestors if frame_ancestors is not None else settings.frame_ancestors()
    hsts = enable_hsts if enable_hsts is not None else settings.enable_hsts()

    # Fail loudly at startup if the OSM cache dir is misconfigured — otherwise
    # enrichment silently degrades to geometry-only on every render.
    cache_problem = _osm_cache_problem()
    if cache_problem:
        log.error("%s — OSM enrichment will degrade to geometry-only", cache_problem)

    # Let an in-process runner (ThreadedRunner) drain its thread pool on shutdown
    # so a reload/stop doesn't hang on an in-flight render.
    @asynccontextmanager
    async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            shutdown = getattr(runner, "shutdown", None)
            if callable(shutdown):
                shutdown()

    app = FastAPI(
        title="GPXSheet",
        version="0.1.0",
        summary="GPX → tank-bag navigation PDFs",
        lifespan=_lifespan,
    )
    app.add_middleware(_SecurityHeadersMiddleware, hsts=hsts, frame_ancestors=frames)
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_methods=["GET", "POST"],
            allow_headers=["X-API-Key", "Authorization", "Content-Type"],
        )

    def client_identity(
        request: Request,
        x_api_key: Annotated[str | None, Header()] = None,
        authorization: Annotated[str | None, Header()] = None,
        x_first_party: Annotated[str | None, Header()] = None,
    ) -> str:
        """Authenticate (when keys are configured) and return a rate-limit identity."""
        presented = x_api_key or _bearer_token(authorization)
        if keys:
            if presented is not None and presented in keys:
                return f"key:{presented}"
            # The bundled SPA carries a server-signed first-party token (injected
            # into its page), accepted in lieu of a key when enabled.
            if trust_fp and _valid_fp_token(fp_secret, x_first_party):
                return f"ip:{request.client.host if request.client else '?'}"
            raise HTTPException(status_code=401, detail="invalid or missing API key")
        return f"ip:{request.client.host if request.client else '?'}"

    # Default-value form (not Annotated): `from __future__ import annotations`
    # stringifies annotations, and FastAPI can't resolve the locally-defined
    # client_identity from inside an Annotated string.
    def rate_limited(identity: str = Depends(client_identity)) -> None:
        limiter.check(identity)

    def read_gpx(gpx: UploadFile) -> bytes:
        # Read at most max_bytes+1 to detect oversize without buffering huge files.
        data = gpx.file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(status_code=413, detail=f"GPX exceeds {max_bytes} bytes")
        if not data:
            raise HTTPException(status_code=400, detail="empty GPX upload")
        if _GPX_MARKER not in data[:4096].lower():
            raise HTTPException(status_code=400, detail="not a GPX document")
        n_points = sum(data.count(tag) for tag in _POINT_TAGS)
        if n_points > point_cap:
            raise HTTPException(
                status_code=413, detail=f"route exceeds {point_cap} points"
            )
        return data

    def to_status(rec: JobRecord) -> JobStatus:
        result_url = None
        if rec.status == "done" and rec.result_key:
            result_url = storage.url(rec.result_key) or f"/v1/jobs/{rec.id}/result"
        # While the job is still waiting/working, tell the client how many jobs are
        # ahead of it in the (single-worker) queue, so a backlog is visible.
        queue_position = store.jobs_ahead(rec.id) if rec.status in ("queued", "running") else None
        return JobStatus(
            id=rec.id,
            status=JobState(rec.status),
            error=rec.error,
            result_url=result_url,
            content_type=rec.content_type,
            queue_position=queue_position,
        )

    def submit_job(
        op: str, gpx: UploadFile, params: BaseModel, identity: str, response: Response
    ) -> JobStatus:
        """Shared create-a-job path for every POST endpoint.

        Deduplicates by (GPX + op + params + identity); sets a ``Location`` header
        to the job, and a status code of 200 for an already-finished job (e.g. a
        cache hit or a synchronous dev render) or 202 for newly queued work.
        """
        data = read_gpx(gpx)
        key = _cache_key(data, op, params, identity)
        cached = store.get_cached(key)
        if cached is not None:  # identical GPX + op + params already produced
            rec = cached
        else:
            job_id = store.create(cache_key=key, owner=identity)
            runner.submit(job_id, op, data, params)
            fresh = store.get(job_id)
            assert fresh is not None  # just created -> always present
            rec = fresh
        status = to_status(rec)
        response.headers["Location"] = f"/v1/jobs/{status.id}"
        if status.status in (JobState.done, JobState.error):
            response.status_code = 200
        else:
            response.status_code = 202
            response.headers["Retry-After"] = "2"  # hint: poll the job in ~2s
        return status

    def require_visible(job_id: str, identity: str):
        """Fetch a job, 404 if missing or (when auth is on) not owned by caller."""
        rec = store.get(job_id)
        # Hide others' jobs behind 404 (not 403) so IDs aren't confirmable.
        if rec is None or (keys and rec.owner is not None and rec.owner != identity):
            raise HTTPException(status_code=404, detail="unknown job")
        return rec

    @app.get("/healthz")
    def healthz() -> dict:
        """Liveness: the process is up."""
        return {"status": "ok"}

    @app.get("/readyz", responses={503: {"description": "A backend is unreachable"}})
    def readyz() -> dict:
        """Readiness: job store + result storage reachable, and (if configured) the
        OSM cache dir is writable so enrichment won't silently degrade."""
        if not (store.ready() and storage.ready()):
            raise HTTPException(status_code=503, detail="not ready")
        problem = _osm_cache_problem()
        if problem:
            raise HTTPException(status_code=503, detail=problem)
        return {"status": "ready"}

    @app.post(
        "/v1/render", status_code=202, response_model=JobStatus,
        responses=_JOB_RESPONSES, dependencies=[Depends(rate_limited)],
    )
    def render(
        body: Annotated[RenderForm, Form()],
        response: Response,
        identity: str = Depends(client_identity),
    ) -> JobStatus:
        """Render a map (layout x format) as a job."""
        return submit_job("render", body.gpx, _to_params(body, RenderParams), identity, response)

    @app.post(
        "/v1/table", status_code=202, response_model=JobStatus,
        responses=_JOB_RESPONSES, dependencies=[Depends(rate_limited)],
    )
    def table(
        body: Annotated[TableForm, Form()],
        response: Response,
        identity: str = Depends(client_identity),
    ) -> JobStatus:
        """Render a route table (HTML or markdown) as a job."""
        return submit_job("table", body.gpx, _to_params(body, TableParams), identity, response)

    @app.post(
        "/v1/analyze", status_code=202, response_model=JobStatus,
        responses=_JOB_RESPONSES, dependencies=[Depends(rate_limited)],
    )
    def analyze(
        body: Annotated[ReportForm, Form()],
        response: Response,
        identity: str = Depends(client_identity),
    ) -> JobStatus:
        """Analyze a route into a JSON report as a job."""
        return submit_job("analyze", body.gpx, _to_params(body, ReportParams), identity, response)

    @app.post(
        "/v1/validate", status_code=202, response_model=JobStatus,
        responses=_JOB_RESPONSES, dependencies=[Depends(rate_limited)],
    )
    def validate(
        body: Annotated[ReportForm, Form()],
        response: Response,
        identity: str = Depends(client_identity),
    ) -> JobStatus:
        """Validate a route (fuel/unpaved/ferry) into a JSON report as a job."""
        return submit_job("validate", body.gpx, _to_params(body, ReportParams), identity, response)

    @app.get(
        "/v1/jobs/{job_id}", response_model=JobStatus,
        responses={404: {"description": "Unknown job"}},
    )
    def job_status(job_id: str, identity: str = Depends(client_identity)) -> JobStatus:
        return to_status(require_visible(job_id, identity))

    @app.get(
        "/v1/jobs/{job_id}/result",
        responses={
            200: {"description": "The rendered artifact (PDF/PNG) or JSON report"},
            303: {"description": "Redirect to a presigned download URL"},
            304: {"description": "Not modified (matching If-None-Match)"},
            404: {"description": "Unknown job"},
            409: {"description": "Job failed"},
            425: {"description": "Job not finished yet; poll the status URL"},
        },
    )
    def job_result(
        job_id: str,
        request: Request,
        identity: str = Depends(client_identity),
    ):
        rec = require_visible(job_id, identity)
        if rec.status == "error":
            raise HTTPException(status_code=409, detail=rec.error or "job failed")
        if rec.status != "done" or not rec.result_key:
            # Not ready: tell the client to keep polling the status resource.
            raise HTTPException(
                status_code=425,
                detail=f"job is {rec.status}",
                headers={"Retry-After": "2", "Location": f"/v1/jobs/{rec.id}"},
            )

        external = storage.url(rec.result_key)
        if external:
            return RedirectResponse(external, status_code=303)

        # Results are immutable (content-addressed), so they cache forever; the
        # job id is a stable ETag for conditional requests.
        etag = f'"{rec.id}"'
        if request.headers.get("if-none-match") == etag:
            return Response(status_code=304, headers={"ETag": etag})
        content_type = rec.content_type or "application/octet-stream"
        headers = {"ETag": etag, "Cache-Control": "public, max-age=31536000, immutable"}
        # Stream maps as a download; serve JSON reports inline.
        if content_type != "application/json":
            filename = rec.download_name or rec.result_key
            headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        return Response(
            content=storage.load(rec.result_key), media_type=content_type, headers=headers
        )

    from fastapi.staticfiles import StaticFiles

    _static = Path(__file__).parent / "static"
    if _static.is_dir():
        # When first-party trust is on, serve index.html through a handler that
        # injects a fresh signed token, so the SPA can authenticate without a key.
        # Registered before the catch-all mount so it wins for "/". Other routes
        # (assets, SPA fallback) are served by StaticFiles as usual.
        if trust_fp and keys:
            _index_html = (_static / "index.html").read_text(encoding="utf-8")

            @app.get("/", include_in_schema=False)
            def index() -> HTMLResponse:
                token = _issue_fp_token(fp_secret)  # token chars are [0-9a-f.] — attr-safe
                tag = f'<meta name="{_FP_META}" content="{token}">'
                html = _index_html.replace("</head>", f"{tag}</head>", 1)
                return HTMLResponse(html, headers={"Cache-Control": "no-store"})

        app.mount("/", StaticFiles(directory=_static, html=True), name="static")

    return app


def _guard_prod_secrets() -> None:
    """Refuse to boot the production path with default MinIO credentials."""
    cfg = settings.minio_config()
    if cfg["access_key"] == "minioadmin" or cfg["secret_key"] == "minioadmin":
        raise RuntimeError(
            "Refusing to start: default MinIO credentials (minioadmin) in use. "
            "Set GPXSHEET_MINIO_ACCESS_KEY / GPXSHEET_MINIO_SECRET_KEY."
        )
