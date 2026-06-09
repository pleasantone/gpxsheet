"""FastAPI application factory for the GPXSheet web service."""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware

from . import settings
from .jobs import (
    DramatiqRunner,
    EagerRunner,
    InMemoryJobStore,
    JobStore,
    TaskRunner,
    prod_components,
)
from .models import GenerateParams, JobStatus
from .render import analyze_to_dict, render_preview_bytes
from .storage import LocalStorage, Storage

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
        recent = [t for t in self._hits[identity] if now - t < 60.0]
        if len(recent) >= self.limit:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        recent.append(now)
        self._hits[identity] = recent


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
        # API serves JSON/PDF/PNG, never HTML it controls; lock scripting down.
        response.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'"
        )
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=63072000; includeSubDomains"
            )
        return response


def _bearer_token(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None


def _cache_key(data: bytes, params: GenerateParams) -> str:
    return hashlib.sha256(data + params.model_dump_json().encode()).hexdigest()


def default_components() -> tuple[JobStore, Storage, TaskRunner]:
    """Prod path (Redis + MinIO + Dramatiq) if a Redis URL is set, else dev path."""
    if settings.redis_url():
        store, storage = prod_components()
        return store, storage, DramatiqRunner()
    store = InMemoryJobStore()
    storage = LocalStorage(settings.results_dir())
    return store, storage, EagerRunner(store, storage)


def create_app(
    store: JobStore | None = None,
    storage: Storage | None = None,
    runner: TaskRunner | None = None,
    *,
    max_upload_bytes: int | None = None,
    max_points: int | None = None,
    rate_limit_per_minute: int | None = None,
    api_keys: frozenset[str] | None = None,
    allow_osm: bool | None = None,
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
    osm_allowed = allow_osm if allow_osm is not None else settings.allow_osm()
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

    def vet_params(params: GenerateParams) -> GenerateParams:
        if params.use_osm and not osm_allowed:
            raise HTTPException(status_code=400, detail="OSM enrichment is disabled on this server")
        return params

    def to_status(rec) -> JobStatus:
        result_url = None
        if rec.status == "done" and rec.result_key:
            result_url = storage.url(rec.result_key) or f"/v1/jobs/{rec.id}/result"
        return JobStatus(id=rec.id, status=rec.status, error=rec.error, result_url=result_url)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.post(
        "/v1/jobs", status_code=202, response_model=JobStatus, dependencies=[Depends(rate_limited)]
    )
    def create_job(gpx: UploadFile, params: Annotated[GenerateParams, Query()]) -> JobStatus:
        vet_params(params)
        data = read_gpx(gpx)
        key = _cache_key(data, params)
        cached = store.get_cached(key)
        if cached is not None:  # identical GPX + params already rendered
            return to_status(cached)
        job_id = store.create(cache_key=key)
        runner.submit(job_id, data, params)
        return to_status(store.get(job_id))

    @app.get("/v1/jobs/{job_id}", response_model=JobStatus, dependencies=[Depends(client_identity)])
    def job_status(job_id: str) -> JobStatus:
        rec = store.get(job_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return to_status(rec)

    @app.get("/v1/jobs/{job_id}/result", dependencies=[Depends(client_identity)])
    def job_result(job_id: str):
        rec = store.get(job_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="unknown job")
        if rec.status != "done" or not rec.result_key:
            raise HTTPException(status_code=409, detail=f"job is {rec.status}")
        external = storage.url(rec.result_key)
        if external:
            return RedirectResponse(external, status_code=303)
        return Response(
            content=storage.load(rec.result_key),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{job_id}.pdf"'},
        )

    @app.post("/v1/analyze", dependencies=[Depends(rate_limited)])
    def analyze(gpx: UploadFile, params: Annotated[GenerateParams, Query()]) -> dict:
        vet_params(params)
        return analyze_to_dict(read_gpx(gpx), params)

    @app.post("/v1/preview", dependencies=[Depends(rate_limited)])
    def preview(gpx: UploadFile, params: Annotated[GenerateParams, Query()]) -> Response:
        # Synchronous: a fast, low-res whole-route thumbnail (no job/pagination).
        vet_params(params)
        png = render_preview_bytes(read_gpx(gpx), params)
        return Response(content=png, media_type="image/png")

    return app


def _guard_prod_secrets() -> None:
    """Refuse to boot the production path with default MinIO credentials."""
    cfg = settings.minio_config()
    if cfg["access_key"] == "minioadmin" or cfg["secret_key"] == "minioadmin":
        raise RuntimeError(
            "Refusing to start: default MinIO credentials (minioadmin) in use. "
            "Set GPXSHEET_MINIO_ACCESS_KEY / GPXSHEET_MINIO_SECRET_KEY."
        )
