"""Shared test fixtures: synthetic GPX builders and the OSM cache harness.

The suite is deterministic and offline. We point osmnx at a committed response
cache (``tests/fixtures/osm_cache``) and, unless recording, replace osmnx's
Overpass request with a cache-only stand-in that raises on a miss -- so a
forgotten/stale fixture fails loudly instead of silently hitting the network.
Re-record with::

    GPXSHEET_RECORD_OSM=1 .venv/bin/pytest tests/test_enrich.py

(see ``tests/fixtures/README.md``).
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"
OSM_CACHE_DIR = FIXTURES_DIR / "osm_cache"
LIVE_CACHE_DIR = FIXTURES_DIR / "live_cache"
RECORDING_OSM = os.environ.get("GPXSHEET_RECORD_OSM") == "1"


def _offline_overpass_request(data):
    """Cache-only replacement for ``osmnx._overpass._overpass_request``.

    Computes the same cache key osmnx would and returns the committed response;
    a miss raises rather than touching the network, keeping CI deterministic.
    """
    import requests
    from osmnx import _http, settings

    url = settings.overpass_url.rstrip("/") + "/interpreter"
    prepared_url = str(requests.Request("GET", url, params=data).prepare().url)
    cached = _http._retrieve_from_cache(prepared_url)
    if isinstance(cached, dict):
        return cached
    raise RuntimeError(
        "OSM Overpass cache miss in offline test mode. Re-record fixtures with "
        f"GPXSHEET_RECORD_OSM=1. query={str(data.get('data', ''))[:200]!r}"
    )


@pytest.fixture(scope="session", autouse=True)
def _osm_cache():
    """Wire osmnx to the committed response cache for the whole session.

    No-op when osmnx isn't installed (core-only runs skip OSM entirely). When
    recording, network is allowed and responses land in the committed cache dir;
    otherwise Overpass is served strictly from the cache.
    """
    try:
        import osmnx as ox
        from osmnx import _overpass
    except ImportError:
        yield
        return

    OSM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ox.settings.use_cache = True
    ox.settings.cache_folder = str(OSM_CACHE_DIR)

    original = _overpass._overpass_request
    if RECORDING_OSM:
        ox.settings.overpass_rate_limit = False  # skip inter-request pauses
    else:
        _overpass._overpass_request = _offline_overpass_request
    try:
        yield
    finally:
        _overpass._overpass_request = original


@pytest.fixture(scope="session", autouse=True)
def _live_cache():
    """Wire the day-card live providers to the committed cache (cache-only).

    Mirrors ``_osm_cache``: point the live providers' on-disk cache at a committed
    fixture dir and, unless recording, replace the single network seam
    (``live.base._http_get_json``) with a cache-only stand-in that returns
    ``None`` on a miss -- so the suite is deterministic and offline (a missing
    fixture just omits that section). Record with ``GPXSHEET_RECORD_LIVE=1``.
    Also clears ``GPXSHEET_DISABLE_LIVE`` / ``GPXSHEET_OFFLINE`` so the committed
    cache is consulted (the disable switches are exercised in their own tests).
    """
    from gpxsheet.live import base
    from gpxsheet.sources import recording_live

    LIVE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    prev_dir = os.environ.get("GPXSHEET_LIVE_CACHE_DIR")
    prev_disable = os.environ.pop("GPXSHEET_DISABLE_LIVE", None)
    prev_offline = os.environ.pop("GPXSHEET_OFFLINE", None)
    os.environ["GPXSHEET_LIVE_CACHE_DIR"] = str(LIVE_CACHE_DIR)

    original = base._http_get_json
    if not recording_live():
        base._http_get_json = lambda url, params: None  # cache-only; miss -> skip
    try:
        yield
    finally:
        base._http_get_json = original
        if prev_dir is None:
            os.environ.pop("GPXSHEET_LIVE_CACHE_DIR", None)
        else:
            os.environ["GPXSHEET_LIVE_CACHE_DIR"] = prev_dir
        if prev_disable is not None:
            os.environ["GPXSHEET_DISABLE_LIVE"] = prev_disable
        if prev_offline is not None:
            os.environ["GPXSHEET_OFFLINE"] = prev_offline


@pytest.fixture
def enrich_route_file() -> Path:
    """A real onshore route (15 mi clip) with committed OSM cache, for enrichment."""
    return FIXTURES_DIR / "enrich_route.gpx"


@pytest.fixture
def table_route_file() -> Path:
    """A small ``<rte>`` with named points + symbols, for the native route table."""
    return FIXTURES_DIR / "table_route.gpx"


@pytest.fixture
def roundabout_route_file() -> Path:
    """A real clip through a La Loma Ave roundabout (Riverbank, CA).

    Regression fixture for roundabout exit-counting: the route goes straight
    through, which is the 2nd exit. A one-way feeder at the ring previously made
    it read as the 3rd exit (see _ring_exit_flags).
    """
    return FIXTURES_DIR / "roundabout_route.gpx"


@pytest.fixture
def mthamilton_route_file() -> Path:
    """A remote Mt Hamilton clip whose roads the strict "drive" filter drops.

    Regression fixture for the ``drive`` -> ``drive_service`` enrichment fallback:
    plain ``drive`` returns no graph nodes here, so without the fallback the route
    silently degrades to the geometry baseline.
    """
    return FIXTURES_DIR / "mthamilton_route.gpx"


def _trkpt(lat: float, lon: float) -> str:
    return f'<trkpt lat="{lat:.6f}" lon="{lon:.6f}"></trkpt>'


def write_gpx(
    path: Path,
    track: list[tuple[float, float]],
    waypoints: list[tuple[float, float, str]] | None = None,
    name: str = "Test Route",
) -> Path:
    wpts = "".join(
        f'<wpt lat="{lat:.6f}" lon="{lon:.6f}"><name>{nm}</name></wpt>'
        for lat, lon, nm in (waypoints or [])
    )
    trkpts = "".join(_trkpt(lat, lon) for lat, lon in track)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gpx version="1.1" creator="gpxsheet-tests">'
        f"{wpts}"
        f"<trk><name>{name}</name><trkseg>{trkpts}</trkseg></trk>"
        "</gpx>"
    )
    path.write_text(xml, encoding="utf-8")
    return path


def l_shaped_track(
    start_lat: float = 38.0,
    start_lon: float = -123.0,
    east_steps: int = 46,
    north_steps: int = 36,
    step: float = 0.001,
) -> list[tuple[float, float]]:
    """A track heading due east, then turning ~90° left to head due north."""
    pts: list[tuple[float, float]] = []
    lat, lon = start_lat, start_lon
    for _ in range(east_steps):
        pts.append((lat, lon))
        lon += step
    for _ in range(north_steps + 1):
        pts.append((lat, lon))
        lat += step
    return pts


@pytest.fixture
def l_route_file(tmp_path: Path) -> Path:
    track = l_shaped_track()
    # Put a fuel waypoint near the corner of the L.
    corner = track[46]
    return write_gpx(
        tmp_path / "route.gpx",
        track,
        waypoints=[(corner[0], corner[1], "Shell Gas Station")],
    )
