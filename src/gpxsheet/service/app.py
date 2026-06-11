"""FastAPI application factory for the GPXSheet web service."""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from typing import Annotated, Any

from fastapi import Depends, FastAPI, Form, Header, HTTPException, Request, Response, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware

from . import settings
from .jobs import (
    DramatiqRunner,
    EagerRunner,
    InMemoryJobStore,
    JobRecord,
    JobStore,
    TaskRunner,
    prod_components,
)
from .models import JobState, JobStatus, RenderForm, RenderParams, ReportForm, ReportParams
from .storage import LocalStorage, Storage

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

    def __init__(self, app, *, hsts: bool) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        # API routes stay locked down; SPA HTML needs script execution + blob: images.
        is_api = request.url.path.startswith("/v1/") or request.url.path in ("/healthz", "/readyz")
        csp = (
            "default-src 'none'; frame-ancestors 'none'"
            if is_api
            else "default-src 'self'; img-src 'self' blob: data:; frame-ancestors 'none'"
        )
        response.headers.setdefault("Content-Security-Policy", csp)
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _cache_key(data: bytes, op: str, params: ReportParams, identity: str) -> str:
    # Identity is part of the key so cross-tenant requests never share a job
    # (each owner gets their own), which keeps per-job ownership consistent.
    return hashlib.sha256(
        data + b"\0" + op.encode() + b"\0" + identity.encode() + b"\0"
        + params.model_dump_json().encode()
    ).hexdigest()


def _to_params(form: ReportParams, model: type[ReportParams]) -> ReportParams:
    """Extract the plain (queue-serializable) params from a multipart form body."""
    return model(**{k: getattr(form, k) for k in model.model_fields})


def default_components() -> tuple[JobStore, Storage, TaskRunner]:
    """Prod path (Redis + MinIO + Dramatiq) if a Redis URL is set, else dev path."""
    if settings.redis_url():
        store, storage = prod_components()
        return store, storage, DramatiqRunner()
    mem = InMemoryJobStore()
    local = LocalStorage(settings.results_dir())
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
    hsts = enable_hsts if enable_hsts is not None else settings.enable_hsts()

    app = FastAPI(title="GPXSheet", version="0.1.0", summary="GPX → tank-bag navigation PDFs")
    app.add_middleware(_SecurityHeadersMiddleware, hsts=hsts)
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
    ) -> str:
        """Authenticate (when keys are configured) and return a rate-limit identity."""
        presented = x_api_key or _bearer_token(authorization)
        if keys:
            if presented is None or presented not in keys:
                raise HTTPException(status_code=401, detail="invalid or missing API key")
            return f"key:{presented}"
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
        return JobStatus(
            id=rec.id,
            status=JobState(rec.status),
            error=rec.error,
            result_url=result_url,
            content_type=rec.content_type,
        )

    def submit_job(
        op: str, gpx: UploadFile, params: ReportParams, identity: str, response: Response
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
        """Readiness: the job store and result storage are reachable."""
        if not (store.ready() and storage.ready()):
            raise HTTPException(status_code=503, detail="not ready")
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

    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    _static = Path(__file__).parent / "static"
    if _static.is_dir():
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
