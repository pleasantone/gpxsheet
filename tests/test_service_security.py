"""Security-hardening tests for the web service and the GPX parser."""

from __future__ import annotations

import pytest

from gpxsheet.gpx import load_route

pytest.importorskip("fastapi")
pytest.importorskip("dramatiq")

from fastapi.testclient import TestClient  # noqa: E402

from gpxsheet.service import settings  # noqa: E402
from gpxsheet.service.app import _guard_prod_secrets, create_app  # noqa: E402
from gpxsheet.service.jobs import EagerRunner, InMemoryJobStore  # noqa: E402
from gpxsheet.service.storage import LocalStorage  # noqa: E402


def _client(tmp_path, **kwargs):
    store = InMemoryJobStore()
    storage = LocalStorage(tmp_path / "results")
    return TestClient(create_app(store, storage, EagerRunner(store, storage), **kwargs))


def _post(client, path, gpx_path, **kwargs):
    with open(gpx_path, "rb") as fh:
        return client.post(path, files={"gpx": ("route.gpx", fh, "application/gpx+xml")}, **kwargs)


# --- GPX parser: XXE / entity-expansion ------------------------------------


def test_load_route_rejects_doctype(tmp_path):
    """A GPX carrying a DTD/entity declaration (XXE vector) is refused."""
    evil = tmp_path / "xxe.gpx"
    evil.write_text(
        '<?xml version="1.0"?>\n'
        '<!DOCTYPE gpx [<!ENTITY xxe SYSTEM "file:///etc/hostname">]>\n'
        '<gpx version="1.1"><wpt lat="1" lon="2"><name>&xxe;</name></wpt>'
        '<rte><rtept lat="1" lon="2"/><rtept lat="3" lon="4"/></rte></gpx>',
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="DTD/entity"):
        load_route(evil)


def test_doctype_upload_fails_job(tmp_path):
    """The rejection surfaces as a failed job (not a worker crash) via the API."""
    client = _client(tmp_path)
    gpx = tmp_path / "xxe.gpx"
    gpx.write_text(
        '<!DOCTYPE gpx [<!ENTITY a "b">]>'
        '<gpx><rte><rtept lat="1" lon="2"/><rtept lat="3" lon="4"/></rte></gpx>',
        encoding="utf-8",
    )
    body = _post(client, "/v1/jobs?use_osm=false", gpx).json()
    assert body["status"] == "error"
    assert "DTD/entity" in body["error"]


# --- upload validation ------------------------------------------------------


def test_non_gpx_upload_rejected(tmp_path):
    client = _client(tmp_path)
    r = client.post(
        "/v1/jobs?use_osm=false",
        files={"gpx": ("note.txt", b"just some text, not xml", "text/plain")},
    )
    assert r.status_code == 400


def test_point_cap_rejects_monster_route(tmp_path, l_route_file):
    client = _client(tmp_path, max_points=5)  # l_route_file has many more
    assert _post(client, "/v1/jobs?use_osm=false", l_route_file).status_code == 413


# --- OSM egress gate --------------------------------------------------------


def test_osm_disabled_rejects_osm_request(tmp_path, l_route_file):
    client = _client(tmp_path, allow_osm=False)
    assert _post(client, "/v1/jobs?use_osm=true", l_route_file).status_code == 400
    # ...but offline rendering still works.
    assert _post(client, "/v1/jobs?use_osm=false", l_route_file).status_code == 202


# --- authentication & per-key rate limiting ---------------------------------


def test_api_key_required_when_configured(tmp_path, l_route_file):
    client = _client(tmp_path, api_keys=frozenset({"s3cret"}))
    assert _post(client, "/v1/jobs?use_osm=false", l_route_file).status_code == 401
    ok = _post(
        client, "/v1/jobs?use_osm=false", l_route_file, headers={"X-API-Key": "s3cret"}
    )
    assert ok.status_code == 202


def test_bearer_token_accepted(tmp_path, l_route_file):
    client = _client(tmp_path, api_keys=frozenset({"s3cret"}))
    ok = _post(
        client, "/v1/jobs?use_osm=false", l_route_file, headers={"Authorization": "Bearer s3cret"}
    )
    assert ok.status_code == 202


def test_result_requires_api_key(tmp_path, l_route_file):
    client = _client(tmp_path, api_keys=frozenset({"s3cret"}))
    hdr = {"X-API-Key": "s3cret"}
    job_id = _post(client, "/v1/jobs?use_osm=false", l_route_file, headers=hdr).json()["id"]
    assert client.get(f"/v1/jobs/{job_id}/result").status_code == 401
    assert client.get(f"/v1/jobs/{job_id}/result", headers=hdr).status_code == 200


def test_rate_limit_is_per_key(tmp_path, l_route_file):
    client = _client(
        tmp_path, api_keys=frozenset({"a", "b"}), rate_limit_per_minute=1
    )
    assert _post(
        client, "/v1/jobs?use_osm=false", l_route_file, headers={"X-API-Key": "a"}
    ).status_code == 202
    assert _post(
        client, "/v1/jobs?use_osm=false", l_route_file, headers={"X-API-Key": "a"}
    ).status_code == 429
    # A different key has its own budget.
    assert _post(
        client, "/v1/jobs?use_osm=false", l_route_file, headers={"X-API-Key": "b"}
    ).status_code == 202


# --- security headers -------------------------------------------------------


def test_security_headers_present(tmp_path):
    client = _client(tmp_path)
    h = client.get("/healthz").headers
    assert h["X-Content-Type-Options"] == "nosniff"
    assert h["X-Frame-Options"] == "DENY"
    assert "default-src 'none'" in h["Content-Security-Policy"]
    assert "Strict-Transport-Security" not in h  # off unless enabled


def test_hsts_when_enabled(tmp_path):
    client = _client(tmp_path, enable_hsts=True)
    assert "max-age=" in client.get("/healthz").headers["Strict-Transport-Security"]


# --- production secret guard ------------------------------------------------


def test_prod_guard_rejects_default_minio_creds(monkeypatch):
    monkeypatch.delenv("GPXSHEET_MINIO_ACCESS_KEY", raising=False)
    monkeypatch.delenv("GPXSHEET_MINIO_SECRET_KEY", raising=False)
    assert settings.minio_config()["access_key"] == "minioadmin"
    with pytest.raises(RuntimeError, match="default MinIO credentials"):
        _guard_prod_secrets()


def test_prod_guard_passes_with_real_creds(monkeypatch):
    monkeypatch.setenv("GPXSHEET_MINIO_ACCESS_KEY", "real-access")
    monkeypatch.setenv("GPXSHEET_MINIO_SECRET_KEY", "real-secret")
    _guard_prod_secrets()  # no raise
