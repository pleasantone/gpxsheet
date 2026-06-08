"""FastAPI application factory for the GPXSheet web service."""

from __future__ import annotations

from typing import Annotated

from fastapi import FastAPI, HTTPException, Query, UploadFile
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
) -> FastAPI:
    """Build the API. Pass components explicitly (tests) or let env decide."""
    if store is None or storage is None or runner is None:
        store, storage, runner = default_components()

    app = FastAPI(title="GPXSheet", version="0.1.0", summary="GPX → tank-bag navigation PDFs")

    def to_status(rec) -> JobStatus:
        result_url = None
        if rec.status == "done" and rec.result_key:
            result_url = storage.url(rec.result_key) or f"/v1/jobs/{rec.id}/result"
        return JobStatus(id=rec.id, status=rec.status, error=rec.error, result_url=result_url)

    @app.get("/healthz")
    def healthz() -> dict:
        return {"status": "ok"}

    @app.post("/v1/jobs", status_code=202, response_model=JobStatus)
    def create_job(gpx: UploadFile, params: Annotated[GenerateParams, Query()]) -> JobStatus:
        data = gpx.file.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty GPX upload")
        job_id = store.create()
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

    @app.post("/v1/analyze")
    def analyze(gpx: UploadFile, params: Annotated[GenerateParams, Query()]) -> dict:
        data = gpx.file.read()
        if not data:
            raise HTTPException(status_code=400, detail="empty GPX upload")
        return analyze_to_dict(data, params)

    return app
