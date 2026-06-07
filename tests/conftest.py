"""Shared test fixtures: synthetic GPX builders."""

from __future__ import annotations

from pathlib import Path

import pytest


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
