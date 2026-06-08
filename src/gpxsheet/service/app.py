"""FastAPI application factory for the GPXSheet web service."""

from __future__ import annotations

import hashlib
import time
from collections import defaultdict
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, UploadFile
from fastapi.responses import RedirectResponse, Response

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
from .render import analyze_to_dict
from .storage import LocalStorage, Storage


class _RateLimiter:
    """In-memory fixed-window per-client limiter (per API process)."""

    def __init__(self, per_minute: int) -> None:
        self.limit = per_minute
        self._hits: dict[str, list[float]] = defaultdict(list)

    def check(self, request: Request) -> None:
        if self.limit <= 0:
            return
        now = time.monotonic()
        client = request.client.host if request.client else "?"
        recent = [t for t in self._hits[client] if now - t < 60.0]
        if len(recent) >= self.limit:
            raise HTTPException(status_code=429, detail="rate limit exceeded")
        recent.append(now)
        self._hits[client] = recent


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
    rate_limit_per_minute: int | None = None,
) -> FastAPI:
    """Build the API. Pass components explicitly (tests) or let env decide."""
    if store is None or storage is None or runner is None:
        store, storage, runner = default_components()
    max_bytes = max_upload_bytes if max_upload_bytes is not None else settings.max_upload_bytes()
    limiter = _RateLimiter(
        rate_limit_per_minute if rate_limit_per_minute is not None
        else settings.rate_limit_per_minute()
    )

    app = FastAPI(title="GPXSheet", version="0.1.0", summary="GPX → tank-bag navigation PDFs")

    def rate_limit(request: Request) -> None:
        limiter.check(request)

    def read_gpx(gpx: UploadFile) -> bytes:
        # Read at most max_bytes+1 to detect oversize without buffering huge files.
        data = gpx.file.read(max_bytes + 1)
        if len(data) > max_bytes:
            raise HTTPException(status_code=413, detail=f"GPX exceeds {max_bytes} bytes")
        if not data:
            raise HTTPException(status_code=400, detail="empty GPX upload")
        return data

    def to_status(rec) -> JobStatus:
        result_url = None
        if rec.status == "done" and rec.result_key:
            result_url = storage.url(rec.result_key) or f"/v1/jobs/{rec.id}/result"
        return JobStatus(id=rec.id, status=rec.status, error=rec.error, result_url=result_url)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.post(
        "/v1/jobs", status_code=202, response_model=JobStatus, dependencies=[Depends(rate_limit)]
    )
    def create_job(gpx: UploadFile, params: Annotated[GenerateParams, Query()]) -> JobStatus:
        data = read_gpx(gpx)
        key = _cache_key(data, params)
        cached = store.get_cached(key)
        if cached is not None:  # identical GPX + params already rendered
            return to_status(cached)
        job_id = store.create(cache_key=key)
        runner.submit(job_id, data, params)
        return to_status(store.get(job_id))

    @app.get("/v1/jobs/{job_id}", response_model=JobStatus)
    def job_status(job_id: str) -> JobStatus:
        rec = store.get(job_id)
        if rec is None:
            raise HTTPException(status_code=404, detail="unknown job")
        return to_status(rec)

    @app.get("/v1/jobs/{job_id}/result")
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

    @app.post("/v1/analyze", dependencies=[Depends(rate_limit)])
    def analyze(gpx: UploadFile, params: Annotated[GenerateParams, Query()]) -> dict:
        return analyze_to_dict(read_gpx(gpx), params)

    return app
