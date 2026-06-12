"""Tests for GPX loading, including Garmin BaseCamp route harvesting.

A BaseCamp route stores its real road geometry inside per-rtept
``gpxx:RoutePointExtension``/``gpxx:rpt`` children and marks announced stops with
``trp:ViaPoint`` (see docs/basecamp-routes.md). These tests cover both a synthetic
Garmin route (fully deterministic) and the committed ``gpxsamples`` sample when the
submodule is present.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from gpxsheet.analysis import looks_sparse
from gpxsheet.gpx import load_route

_GARMIN_HEADER = (
    '<?xml version="1.0"?>'
    '<gpx xmlns="http://www.topografix.com/GPX/1/1" '
    'xmlns:gpxx="http://www.garmin.com/xmlschemas/GpxExtensions/v3" '
    'xmlns:trp="http://www.garmin.com/xmlschemas/TripExtensions/v1" '
    'version="1.1" creator="Garmin Desktop App">'
)


def _rpt(lat: float, lon: float) -> str:
    return f'<gpxx:rpt lat="{lat:.6f}" lon="{lon:.6f}"/>'


def _rtept(
    lat: float,
    lon: float,
    name: str,
    rpts: list[tuple[float, float]],
    *,
    via: bool = False,
    arrival: str | None = None,
    departure: str | None = None,
) -> str:
    trp = ""
    if via:
        times = ""
        if departure is not None:
            times += f"<trp:DepartureTime>{departure}</trp:DepartureTime>"
        if arrival is not None:
            times += f"<trp:ArrivalTime>{arrival}</trp:ArrivalTime>"
        trp = f"<trp:ViaPoint>{times}</trp:ViaPoint>"
    rpt_xml = "".join(_rpt(la, lo) for la, lo in rpts)
    return (
        f'<rtept lat="{lat:.6f}" lon="{lon:.6f}"><name>{name}</name>'
        f"<extensions>{trp}"
        f"<gpxx:RoutePointExtension>{rpt_xml}</gpxx:RoutePointExtension>"
        "</extensions></rtept>"
    )


def _garmin_route(tmp_path: Path) -> Path:
    rtepts = (
        # First via: has both times; first-via arrival is schema-invalid (nulled).
        _rtept(
            38.000, -122.000, "Start Cafe", [(38.001, -122.001), (38.002, -122.002)],
            via=True, arrival="2023-07-27T16:00:00Z", departure="2023-07-27T16:30:00Z",
        )
        # Middle via: contradictory pair (departure < arrival) -> both dropped.
        + _rtept(
            38.010, -122.010, "Lunch Stop", [(38.011, -122.011)],
            via=True, arrival="2023-07-27T19:00:00Z", departure="2023-07-27T18:00:00Z",
        )
        # Shaping point: no ViaPoint -> excluded from waypoints.
        + _rtept(38.020, -122.020, "1716 Some Address Rd", [(38.021, -122.021)])
        # Last via: has departure; last-via departure is schema-invalid (nulled).
        + _rtept(
            38.030, -122.030, "End Diner", [],
            via=True, departure="2023-07-27T21:00:00Z",
        )
    )
    xml = _GARMIN_HEADER + f"<rte><name>Synthetic Garmin Route</name>{rtepts}</rte></gpx>"
    path = tmp_path / "garmin_route.gpx"
    path.write_text(xml, encoding="utf-8")
    return path


def test_garmin_route_reconstructs_dense_track(tmp_path: Path) -> None:
    route = load_route(_garmin_route(tmp_path))
    # 4 rtept + (2 + 1 + 1 + 0) rpt children, in document order.
    assert len(route.points) == 4 + 4
    assert route.points[0].lat == pytest.approx(38.000)
    assert route.points[1].lat == pytest.approx(38.001)  # first rpt of rtept0
    assert route.distances_m == sorted(route.distances_m)  # monotonic


def test_garmin_route_promotes_only_via_points(tmp_path: Path) -> None:
    route = load_route(_garmin_route(tmp_path))
    names = [w.name for w in route.waypoints]
    assert names == ["Start Cafe", "Lunch Stop", "End Diner"]  # shaping excluded


def test_garmin_via_times_are_schema_corrected(tmp_path: Path) -> None:
    route = load_route(_garmin_route(tmp_path))
    start, lunch, end = route.waypoints
    # First via: arrival invalid -> dropped; departure kept.
    assert start.arrival_time is None
    assert start.departure_time == datetime(2023, 7, 27, 16, 30, tzinfo=UTC)
    # Middle via: departure < arrival -> both dropped.
    assert lunch.arrival_time is None and lunch.departure_time is None
    # Last via: departure invalid -> dropped.
    assert end.departure_time is None


def test_plain_route_uses_sparse_fallback(tmp_path: Path) -> None:
    """A <rte> with no Garmin rpt extensions still loads from <rtept> directly."""
    xml = (
        '<?xml version="1.0"?>'
        '<gpx xmlns="http://www.topografix.com/GPX/1/1" version="1.1">'
        "<rte><name>Plain</name>"
        '<rtept lat="38.0" lon="-122.0"/><rtept lat="38.1" lon="-122.1"/>'
        "</rte></gpx>"
    )
    path = tmp_path / "plain.gpx"
    path.write_text(xml, encoding="utf-8")
    route = load_route(path)
    assert len(route.points) == 2
    assert route.waypoints == []


_BASECAMP_SAMPLE = (
    Path(__file__).parent.parent / "gpxsamples" / "basecamp-route.gpx"
)


@pytest.mark.skipif(
    not _BASECAMP_SAMPLE.exists(),
    reason="gpxsamples submodule not initialized",
)
def test_basecamp_sample_harvests_full_geometry() -> None:
    route = load_route(_BASECAMP_SAMPLE)
    # 23 <rtept> + 5197 <gpxx:rpt> = 5220 dense points; no longer sparse.
    assert len(route.points) == 5220
    assert not looks_sparse(route)
    # 8 announced via stops (15 shaping points are excluded).
    assert len(route.waypoints) == 8
    assert route.waypoints[0].name == "Peet's Coffee Northgate Mall"
