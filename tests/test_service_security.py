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
    resp = _post(client, "/v1/render", gpx)
    body = resp.json()
    assert body["status"] == "error"
    assert "DTD/entity" in body["error"]
    # Fetching a failed job's result is a 409 (not a "still processing" signal).
    assert client.get(f"/v1/jobs/{body['id']}/result").status_code == 409


# --- upload validation ------------------------------------------------------


def test_non_gpx_upload_rejected(tmp_path):
    client = _client(tmp_path)
    r = client.post(
        "/v1/render",
        files={"gpx": ("note.txt", b"just some text, not xml", "text/plain")},
    )
    assert r.status_code == 400


def test_point_cap_rejects_monster_route(tmp_path, l_route_file):
    client = _client(tmp_path, max_points=5)  # l_route_file has many more
    assert _post(client, "/v1/render", l_route_file).status_code == 413


# --- authentication & per-key rate limiting ---------------------------------


def test_api_key_required_when_configured(tmp_path, l_route_file):
    client = _client(tmp_path, api_keys=frozenset({"s3cret"}))
    assert _post(client, "/v1/render", l_route_file).status_code == 401
    ok = _post(
        client, "/v1/render", l_route_file, headers={"X-API-Key": "s3cret"}
    )
    assert ok.status_code in (200, 202)  # 200 eager (done) / 202 queued


def test_bearer_token_accepted(tmp_path, l_route_file):
    client = _client(tmp_path, api_keys=frozenset({"s3cret"}))
    ok = _post(
        client, "/v1/render", l_route_file, headers={"Authorization": "Bearer s3cret"}
    )
    assert ok.status_code in (200, 202)


def test_job_not_visible_to_other_key(tmp_path, l_route_file):
    """Object-level authz: a job is only visible to the key that created it."""
    client = _client(tmp_path, api_keys=frozenset({"a", "b"}))
    job_id = _post(client, "/v1/render", l_route_file, headers={"X-API-Key": "a"}).json()["id"]
    assert client.get(f"/v1/jobs/{job_id}", headers={"X-API-Key": "a"}).status_code == 200
    # A different key gets 404 (not 403), so job IDs aren't confirmable.
    assert client.get(f"/v1/jobs/{job_id}", headers={"X-API-Key": "b"}).status_code == 404
    assert client.get(f"/v1/jobs/{job_id}/result", headers={"X-API-Key": "b"}).status_code == 404


def test_result_requires_api_key(tmp_path, l_route_file):
    client = _client(tmp_path, api_keys=frozenset({"s3cret"}))
    hdr = {"X-API-Key": "s3cret"}
    job_id = _post(client, "/v1/render", l_route_file, headers=hdr).json()["id"]
    assert client.get(f"/v1/jobs/{job_id}/result").status_code == 401
    assert client.get(f"/v1/jobs/{job_id}/result", headers=hdr).status_code == 200


# --- first-party signed-token trust, with API-key escape hatch --------------


def test_fp_token_roundtrip_and_expiry():
    from gpxsheet.service.app import _issue_fp_token, _valid_fp_token

    secret = b"unit-secret"
    assert _valid_fp_token(secret, _issue_fp_token(secret))
    # Wrong secret, garbage, empty, and expired tokens all fail.
    assert not _valid_fp_token(b"other", _issue_fp_token(secret))
    assert not _valid_fp_token(secret, "not-a-token")
    assert not _valid_fp_token(secret, None)
    assert not _valid_fp_token(secret, _issue_fp_token(secret, ttl=-1))


def test_first_party_token_allows_keyless_spa(tmp_path, l_route_file):
    """With trust enabled, a valid signed first-party token is accepted in lieu of
    an API key; everyone else still needs the key."""
    from gpxsheet.service.app import _issue_fp_token

    client = _client(
        tmp_path,
        api_keys=frozenset({"s3cret"}),
        trust_first_party=True,
        session_secret="sign-me",
    )
    # No key, no token -> rejected.
    assert _post(client, "/v1/render", l_route_file).status_code == 401
    # Valid signed token -> trusted, no key needed.
    token = _issue_fp_token(b"sign-me")
    assert _post(
        client, "/v1/render", l_route_file, headers={"X-First-Party": token}
    ).status_code in (200, 202)
    # A forged token (wrong secret) is rejected.
    assert _post(
        client, "/v1/render", l_route_file,
        headers={"X-First-Party": _issue_fp_token(b"wrong")},
    ).status_code == 401


def test_first_party_disabled_by_default_still_requires_key(tmp_path, l_route_file):
    """Self-hoster default: keys set but trust off -> a (would-be) token is ignored
    and the key is required for everyone."""
    from gpxsheet.service.app import _issue_fp_token

    client = _client(tmp_path, api_keys=frozenset({"s3cret"}), session_secret="sign-me")
    assert _post(
        client, "/v1/render", l_route_file,
        headers={"X-First-Party": _issue_fp_token(b"sign-me")},
    ).status_code == 401


def test_rate_limit_is_per_key(tmp_path, l_route_file):
    client = _client(
        tmp_path, api_keys=frozenset({"a", "b"}), rate_limit_per_minute=1
    )
    assert _post(
        client, "/v1/render", l_route_file, headers={"X-API-Key": "a"}
    ).status_code in (200, 202)
    assert _post(
        client, "/v1/render", l_route_file, headers={"X-API-Key": "a"}
    ).status_code == 429
    # A different key has its own budget.
    assert _post(
        client, "/v1/render", l_route_file, headers={"X-API-Key": "b"}
    ).status_code in (200, 202)


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


# --- path-traversal guard on LocalStorage -----------------------------------


def test_local_storage_rejects_traversal_key(tmp_path):
    from gpxsheet.service.storage import LocalStorage

    s = LocalStorage(tmp_path / "results")
    with pytest.raises(ValueError, match="escapes root"):
        s.save("../secret.txt", b"data")


def test_local_storage_accepts_normal_key(tmp_path):
    from gpxsheet.service.storage import LocalStorage

    s = LocalStorage(tmp_path / "results")
    s.save("abc123.pdf", b"data")
    assert s.load("abc123.pdf") == b"data"


# --- InMemoryJobStore TTL / pruning -----------------------------------------


def test_in_memory_job_store_prunes_expired_jobs():
    import time

    from gpxsheet.service.jobs import InMemoryJobStore

    store = InMemoryJobStore(ttl_seconds=0)  # expire immediately
    jid = store.create()
    time.sleep(0.01)
    store.create()  # triggers prune
    assert store.get(jid) is None  # should have been pruned


def test_in_memory_job_store_keeps_fresh_jobs():
    from gpxsheet.service.jobs import InMemoryJobStore

    store = InMemoryJobStore(ttl_seconds=3600)
    jid = store.create()
    store.create()  # triggers prune, but jid is not expired
    assert store.get(jid) is not None
