"""Tests for the web service (in-memory / eager path — no Redis/MinIO needed)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("dramatiq")

from fastapi.testclient import TestClient  # noqa: E402

from gpxsheet.service.app import create_app  # noqa: E402
from gpxsheet.service.jobs import EagerRunner, InMemoryJobStore, ThreadedRunner  # noqa: E402
from gpxsheet.service.models import RenderParams  # noqa: E402
from gpxsheet.service.storage import LocalStorage  # noqa: E402

PDF_MAGIC = b"%PDF"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def test_render_params_default_auto_fit():
    assert RenderParams().decisions_per_lane == 0  # default = auto-fit


def test_render_params_show_branches_default_off():
    assert RenderParams().show_branches is False  # roads-not-taken stubs off by default


def _make_client(tmp_path, **kwargs):
    store = InMemoryJobStore()
    storage = LocalStorage(tmp_path / "results")
    return TestClient(create_app(store, storage, EagerRunner(store, storage), **kwargs))


@pytest.fixture
def client(tmp_path):
    return _make_client(tmp_path)


def _post(client, path, gpx_path, **params):
    """POST a job: GPX as the file, knobs as multipart form fields."""
    with open(gpx_path, "rb") as fh:
        return client.post(
            path, files={"gpx": ("route.gpx", fh, "application/gpx+xml")}, data=params
        )


def test_healthz(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_readyz(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_job_lifecycle(client, l_route_file):
    # Eager runner renders synchronously, so the job comes back already "done"
    # (-> 200, not 202) with a Location header pointing at the job.
    r = _post(client, "/v1/render", l_route_file, layout="landscape")
    assert r.status_code == 200
    assert r.headers["location"] == f"/v1/jobs/{r.json()['id']}"
    body = r.json()
    assert body["status"] == "done"
    assert body["result_url"]
    assert body["content_type"] == "application/pdf"
    job_id = body["id"]

    assert client.get(f"/v1/jobs/{job_id}").json()["status"] == "done"

    res = client.get(f"/v1/jobs/{job_id}/result")
    assert res.status_code == 200
    assert res.headers["content-type"] == "application/pdf"
    assert res.content[:4] == PDF_MAGIC


# Every layout works in both formats; the artifact carries the right content type.
@pytest.mark.parametrize("layout", ["portrait", "landscape", "preview", "strip"])
@pytest.mark.parametrize(
    "fmt,content_type,magic",
    [("pdf", "application/pdf", PDF_MAGIC), ("png", "image/png", PNG_MAGIC)],
)
def test_render_layout_format_matrix(client, l_route_file, layout, fmt, content_type, magic):
    r = _post(client, "/v1/render", l_route_file, layout=layout, format=fmt)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    assert body["content_type"] == content_type
    res = client.get(f"/v1/jobs/{body['id']}/result")
    assert res.status_code == 200
    assert res.headers["content-type"] == content_type
    assert res.content[: len(magic)] == magic


def test_queued_job_returns_202_then_425(tmp_path, l_route_file):
    # A runner that never completes the job: POST -> 202 (Location + Retry-After),
    # and the result is 425 (too early) until it's done.
    class _NoopRunner:
        def submit(self, *args, **kwargs):
            pass

    store = InMemoryJobStore()
    client = TestClient(create_app(store, LocalStorage(tmp_path / "r"), _NoopRunner()))
    r = _post(client, "/v1/render", l_route_file)
    assert r.status_code == 202
    assert r.json()["status"] == "queued"
    assert r.headers["location"] == f"/v1/jobs/{r.json()['id']}"
    assert r.headers["retry-after"]
    res = client.get(f"/v1/jobs/{r.json()['id']}/result")
    assert res.status_code == 425
    assert res.headers["retry-after"]


def test_background_runner_renders_off_request_path(tmp_path, l_route_file):
    # ThreadedRunner returns from submit immediately, so the POST comes back 202
    # (queued/running) rather than a synchronous 200; polling then reaches done.
    import time

    store = InMemoryJobStore()
    storage = LocalStorage(tmp_path / "results")
    runner = ThreadedRunner(store, storage, concurrency=1)
    client = TestClient(create_app(store, storage, runner))
    try:
        r = _post(client, "/v1/render", l_route_file, layout="landscape")
        assert r.status_code == 202, r.text
        body = r.json()
        assert body["status"] in ("queued", "running")
        assert r.headers["location"] == f"/v1/jobs/{body['id']}"
        job_id = body["id"]

        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            status = client.get(f"/v1/jobs/{job_id}").json()["status"]
            if status in ("done", "error"):
                break
            time.sleep(0.05)
        assert status == "done"

        res = client.get(f"/v1/jobs/{job_id}/result")
        assert res.status_code == 200
        assert res.headers["content-type"] == "application/pdf"
        assert res.content[:4] == PDF_MAGIC
    finally:
        runner.shutdown()


def test_queue_position_reports_jobs_ahead(tmp_path, l_route_file):
    # With a runner that never drains the queue, successive jobs report how many
    # pending jobs sit ahead of them (0, 1, 2 …).
    class _NoopRunner:
        def submit(self, *args, **kwargs):
            pass

    store = InMemoryJobStore()
    client = TestClient(create_app(store, LocalStorage(tmp_path / "r"), _NoopRunner()))
    ids = []
    for layout in ("portrait", "landscape", "preview"):
        r = _post(client, "/v1/render", l_route_file, layout=layout)
        assert r.status_code == 202
        ids.append(r.json()["id"])
    for expected, job_id in enumerate(ids):
        assert client.get(f"/v1/jobs/{job_id}").json()["queue_position"] == expected


def test_done_job_has_no_queue_position(client, l_route_file):
    # The eager path completes in-request, so a finished job carries no position.
    r = _post(client, "/v1/render", l_route_file)
    assert r.json()["status"] == "done"
    assert r.json()["queue_position"] is None


def test_render_auto_fit_accepted(client, l_route_file):
    # decisions_per_lane=0 (auto-fit) is accepted over the wire (ge=0).
    r = _post(client, "/v1/render", l_route_file, decisions_per_lane=0)
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_render_no_branches_accepted(client, l_route_file):
    # show_branches is a plain form field; disabling the stubs still renders.
    r = _post(client, "/v1/render", l_route_file, show_branches=False)
    assert r.status_code == 200
    assert r.json()["status"] == "done"


def test_unknown_job_404(client):
    assert client.get("/v1/jobs/nope").status_code == 404
    assert client.get("/v1/jobs/nope/result").status_code == 404


def test_analyze_job(client, l_route_file):
    r = _post(client, "/v1/analyze", l_route_file)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "done"
    assert body["content_type"] == "application/json"
    res = client.get(f"/v1/jobs/{body['id']}/result")
    assert res.headers["content-type"] == "application/json"
    # JSON reports are served inline, not as a download.
    assert "content-disposition" not in res.headers
    data = res.json()
    assert data["length_miles"] > 0
    assert "decision_points" in data and "segments" in data


def test_validate_job(client, l_route_file):
    r = _post(client, "/v1/validate", l_route_file)
    assert r.status_code == 200
    body = r.json()
    res = client.get(f"/v1/jobs/{body['id']}/result")
    data = res.json()
    assert "findings" in data
    assert all({"level", "code", "message"} <= f.keys() for f in data["findings"])


@pytest.mark.parametrize(
    "fmt,content_type,ext,needle",
    [
        ("html", "text/html", "html", b'<table class="gpxtable">'),
        ("markdown", "text/markdown", "md", b"## Route:"),
    ],
)
def test_table_job(client, table_route_file, fmt, content_type, ext, needle):
    r = _post(client, "/v1/table", table_route_file, format=fmt, departure="9:00 AM")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    assert body["content_type"] == content_type
    res = client.get(f"/v1/jobs/{body['id']}/result")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith(content_type)
    assert res.headers["content-disposition"] == f'attachment; filename="Table Test Route.{ext}"'
    assert needle in res.content


def test_table_json_job(client, table_route_file):
    r = _post(client, "/v1/table", table_route_file, format="json", departure="9:00 AM")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    assert body["content_type"] == "application/json"
    res = client.get(f"/v1/jobs/{body['id']}/result")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    doc = res.json()
    assert doc["name"] == "Table Test Route"
    assert doc["units"] == "imperial"
    assert doc["sections"][0]["rows"]


def test_table_invalid_format_rejected(client, l_route_file):
    assert _post(client, "/v1/table", l_route_file, format="pdf").status_code == 422


@pytest.mark.parametrize(
    ("fmt", "content_type", "needle"),
    [
        ("markdown", "text/markdown", b"## Day"),
        ("html", "text/html", b"<h2"),
        ("json", "application/json", b'"warnings"'),
    ],
)
def test_daycard_job(client, l_route_file, fmt, content_type, needle):
    r = _post(client, "/v1/daycard", l_route_file, format=fmt, departure="8:00 AM")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "done"
    assert body["content_type"] == content_type
    res = client.get(f"/v1/jobs/{body['id']}/result")
    assert res.status_code == 200
    assert needle in res.content


def test_daycard_invalid_format_rejected(client, l_route_file):
    assert _post(client, "/v1/daycard", l_route_file, format="pdf").status_code == 422


def test_daycard_accepts_live_toggle(client, l_route_file):
    # The live providers degrade to nothing offline; the job still succeeds.
    r = _post(client, "/v1/daycard", l_route_file, departure="8:00 AM", live="false")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"


def test_table_bad_gpx_errors_job(client):
    bad = b'<gpx version="1.1"><trk><trkseg></trk></gpx>'  # mismatched tag
    r = client.post("/v1/table", files={"gpx": ("bad.gpx", bad, "application/gpx+xml")})
    assert r.status_code == 200  # eager job completes, as an error
    assert r.json()["status"] == "error"


def test_result_caching_headers(client, l_route_file):
    # Results are immutable: ETag + immutable Cache-Control, and a conditional
    # re-fetch returns 304.
    body = _post(client, "/v1/render", l_route_file).json()
    res = client.get(f"/v1/jobs/{body['id']}/result")
    assert "immutable" in res.headers["cache-control"]
    etag = res.headers["etag"]
    again = client.get(f"/v1/jobs/{body['id']}/result", headers={"If-None-Match": etag})
    assert again.status_code == 304


def test_download_filename_uses_route_name(client, l_route_file):
    body = _post(client, "/v1/render", l_route_file).json()
    res = client.get(f"/v1/jobs/{body['id']}/result")
    # l_route_file is named "Test Route" (see conftest.write_gpx default).
    assert res.headers["content-disposition"] == 'attachment; filename="Test Route.pdf"'


def test_empty_upload_rejected(client):
    r = client.post("/v1/render", files={"gpx": ("empty.gpx", b"", "application/gpx+xml")})
    assert r.status_code == 400


def test_invalid_param_rejected(client, l_route_file):
    assert _post(client, "/v1/render", l_route_file, layout="diagonal").status_code == 422
    assert _post(client, "/v1/render", l_route_file, format="svg").status_code == 422


def test_result_cache_hit_reuses_job(client, l_route_file):
    # Identical GPX + endpoint + params -> the second request returns the first job.
    first = _post(client, "/v1/render", l_route_file, layout="landscape")
    second = _post(client, "/v1/render", l_route_file, layout="landscape")
    first_id = first.json()["id"]
    assert first_id == second.json()["id"]
    # A different layout, format, or endpoint -> a different job.
    other_layout = _post(client, "/v1/render", l_route_file, layout="portrait")
    other_format = _post(client, "/v1/render", l_route_file, layout="landscape", format="png")
    other_op = _post(client, "/v1/analyze", l_route_file)
    assert other_layout.json()["id"] != first_id
    assert other_format.json()["id"] != first_id
    assert other_op.json()["id"] != first_id


def test_upload_size_cap(tmp_path, l_route_file):
    client = _make_client(tmp_path, max_upload_bytes=10)
    assert _post(client, "/v1/render", l_route_file).status_code == 413


def test_rate_limit(tmp_path, l_route_file):
    client = _make_client(tmp_path, rate_limit_per_minute=2)
    results = [_post(client, "/v1/render", l_route_file) for _ in range(3)]
    assert [r.status_code for r in results[:2]] == [200, 200]  # eager -> done -> 200
    assert results[2].status_code == 429
    assert results[2].headers["retry-after"]


def test_generic_jobs_post_gone(client, l_route_file):
    # The generic POST /v1/jobs was replaced by typed endpoints.
    assert _post(client, "/v1/jobs", l_route_file).status_code in (404, 405)
    assert _post(client, "/v1/preview", l_route_file).status_code in (404, 405)


def test_json_result_roundtrip_is_valid_json(client, l_route_file):
    body = _post(client, "/v1/analyze", l_route_file).json()
    raw = client.get(f"/v1/jobs/{body['id']}/result").content
    json.loads(raw)  # must parse
