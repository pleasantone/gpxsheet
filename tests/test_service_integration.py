"""Integration tests against real Redis + MinIO.

Skipped unless ``GPXSHEET_SERVICE_IT=1`` and the services are reachable (set
``GPXSHEET_REDIS_URL`` and the ``GPXSHEET_MINIO_*`` env vars, e.g. via
``docker compose up``). These exercise the production components (RedisJobStore,
MinioStorage) that the unit tests stub out.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("dramatiq")

pytestmark = pytest.mark.skipif(
    os.environ.get("GPXSHEET_SERVICE_IT") != "1",
    reason="integration: set GPXSHEET_SERVICE_IT=1 with Redis+MinIO running",
)


def test_redis_job_store_roundtrip():
    from gpxsheet.service import settings
    from gpxsheet.service.jobs import RedisJobStore

    store = RedisJobStore(settings.redis_url())
    job_id = store.create()
    assert store.get(job_id).status == "queued"
    store.update(job_id, status="done", result_key=f"{job_id}.pdf")
    rec = store.get(job_id)
    assert rec.status == "done" and rec.result_key == f"{job_id}.pdf"
    assert store.get("missing") is None


def test_prod_path_end_to_end(l_route_file):
    # Real Redis store + MinIO storage, but EagerRunner so no separate worker is
    # needed: render runs inline, the PDF lands in MinIO, result_url is presigned.
    from fastapi.testclient import TestClient

    from gpxsheet.service import settings
    from gpxsheet.service.app import create_app
    from gpxsheet.service.jobs import EagerRunner, RedisJobStore
    from gpxsheet.service.storage import MinioStorage

    store = RedisJobStore(settings.redis_url())
    storage = MinioStorage(**settings.minio_config())
    client = TestClient(create_app(store, storage, EagerRunner(store, storage)))

    with open(l_route_file, "rb") as fh:
        r = client.post(
            "/v1/jobs?orientation=landscape",
            files={"gpx": ("route.gpx", fh, "application/gpx+xml")},
        )
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "done"
    assert body["result_url"] and body["result_url"].startswith("http")  # presigned MinIO URL
