"""Tests for the web service (in-memory / eager path — no Redis/MinIO needed)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("dramatiq")

from fastapi.testclient import TestClient  # noqa: E402

from gpxsheet.service.app import create_app  # noqa: E402
from gpxsheet.service.jobs import EagerRunner, InMemoryJobStore  # noqa: E402
from gpxsheet.service.storage import LocalStorage  # noqa: E402


def _make_client(tmp_path, **kwargs):
    store = InMemoryJobStore()
    storage = LocalStorage(tmp_path / "results")
    return TestClient(create_app(store, storage, EagerRunner(store, storage), **kwargs))


@pytest.fixture
def client(tmp_path):
    return _make_client(tmp_path)


def _post(client, path, gpx_path):
    with open(gpx_path, "rb") as fh:
        return client.post(path, files={"gpx": ("route.gpx", fh, "application/gpx+xml")})


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_job_lifecycle(client, l_route_file):
    # Eager runner renders synchronously, so the job is already "done" on return.
    r = _post(client, "/v1/jobs?orientation=landscape", l_route_file)
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "done"
    assert body["result_url"]
    job_id = body["id"]

    assert client.get(f"/v1/jobs/{job_id}").json()["status"] == "done"

    res = client.get(f"/v1/jobs/{job_id}/result")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:4] == b"%PDF"


def test_portrait_job(client, l_route_file):
    r = _post(client, "/v1/jobs?orientation=portrait&lanes_per_page=3", l_route_file)
    assert r.status_code == 202
    assert r.json()["status"] == "done"


def test_unknown_job_404(client):
    assert client.get("/v1/jobs/nope").status_code == 404
    assert client.get("/v1/jobs/nope/result").status_code == 404


def test_analyze(client, l_route_file):
    r = _post(client, "/v1/analyze", l_route_file)
    assert r.status_code == 200
    data = r.json()
    assert data["length_miles"] > 0
    assert "decision_points" in data and "segments" in data


def test_preview_returns_png(client, l_route_file):
    r = _post(client, "/v1/preview", l_route_file)
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"  # valid PNG header


def test_empty_upload_rejected(client):
    r = client.post(
        "/v1/jobs", files={"gpx": ("empty.gpx", b"", "application/gpx+xml")}
    )
    assert r.status_code == 400


def test_invalid_param_rejected(client, l_route_file):
    # orientation must match the model pattern
    r = _post(client, "/v1/jobs?orientation=diagonal", l_route_file)
    assert r.status_code == 422


def test_result_cache_hit_reuses_job(client, l_route_file):
    # Identical GPX + params -> the second request returns the first job.
    first = _post(client, "/v1/jobs?orientation=landscape", l_route_file)
    second = _post(client, "/v1/jobs?orientation=landscape", l_route_file)
    assert first.json()["id"] == second.json()["id"]
    # Different params -> a different job.
    third = _post(client, "/v1/jobs?orientation=portrait", l_route_file)
    assert third.json()["id"] != first.json()["id"]


def test_upload_size_cap(tmp_path, l_route_file):
    client = _make_client(tmp_path, max_upload_bytes=10)
    r = _post(client, "/v1/jobs", l_route_file)
    assert r.status_code == 413


def test_rate_limit(tmp_path, l_route_file):
    client = _make_client(tmp_path, rate_limit_per_minute=2)
    codes = [
        _post(client, "/v1/jobs?orientation=landscape", l_route_file).status_code
        for _ in range(3)
    ]
    assert codes[:2] == [202, 202]
    assert codes[2] == 429
