"""Tests for the web service (in-memory / eager path — no Redis/MinIO needed)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("dramatiq")

from fastapi.testclient import TestClient  # noqa: E402

from gpxsheet.service.app import create_app  # noqa: E402
from gpxsheet.service.jobs import EagerRunner, InMemoryJobStore  # noqa: E402
from gpxsheet.service.storage import LocalStorage  # noqa: E402


@pytest.fixture
def client(tmp_path):
    store = InMemoryJobStore()
    storage = LocalStorage(tmp_path / "results")
    return TestClient(create_app(store, storage, EagerRunner(store, storage)))


def _post(client, path, gpx_path):
    with open(gpx_path, "rb") as fh:
        return client.post(path, files={"gpx": ("route.gpx", fh, "application/gpx+xml")})


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_job_lifecycle(client, l_route_file):
    # Eager runner renders synchronously, so the job is already "done" on return.
    r = _post(client, "/v1/jobs?use_osm=false&orientation=landscape", l_route_file)
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
    r = _post(client, "/v1/jobs?use_osm=false&orientation=portrait&lanes_per_page=3", l_route_file)
    assert r.status_code == 202
    assert r.json()["status"] == "done"


def test_unknown_job_404(client):
    assert client.get("/v1/jobs/nope").status_code == 404
    assert client.get("/v1/jobs/nope/result").status_code == 404


def test_analyze(client, l_route_file):
    r = _post(client, "/v1/analyze?use_osm=false", l_route_file)
    assert r.status_code == 200
    data = r.json()
    assert data["length_miles"] > 0
    assert "decision_points" in data and "segments" in data


def test_empty_upload_rejected(client):
    r = client.post(
        "/v1/jobs?use_osm=false", files={"gpx": ("empty.gpx", b"", "application/gpx+xml")}
    )
    assert r.status_code == 400


def test_invalid_param_rejected(client, l_route_file):
    # orientation must match the model pattern
    r = _post(client, "/v1/jobs?orientation=diagonal&use_osm=false", l_route_file)
    assert r.status_code == 422
