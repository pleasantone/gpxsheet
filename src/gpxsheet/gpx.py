"""GPX loading: turn a ``.gpx`` file into a :class:`Route` geometry.

Supports the inputs listed in PRODUCT.md: GPX tracks (``<trk>``), routes
(``<rte>``) and waypoints (``<wpt>``). Track segments and multiple tracks are
concatenated in document order; waypoints are kept separately for fuel/marker
enrichment.
"""

from __future__ import annotations

from pathlib import Path

import gpxpy

from .geo import cumulative_distances
from .models import GeoPoint, Route, Waypoint


def _point_tuples(points: list[GeoPoint]) -> list[tuple[float, float]]:
    return [(p.lat, p.lon) for p in points]


def load_route(path: str | Path, *, name: str | None = None) -> Route:
    """Parse a GPX file into a :class:`Route`.

    Args:
        path: Path to the ``.gpx`` file.
        name: Optional route name override; otherwise taken from the GPX
            metadata / first track / first route, falling back to the filename.

    Raises:
        ValueError: if the file contains no usable track or route geometry.
    """
    path = Path(path)
    with path.open(encoding="utf-8") as fh:
        gpx = gpxpy.parse(fh)

    points: list[GeoPoint] = []
    gpx_name: str | None = None

    # Prefer tracks; fall back to routes.
    for track in gpx.tracks:
        gpx_name = gpx_name or track.name
        for seg in track.segments:
            for pt in seg.points:
                points.append(GeoPoint(pt.latitude, pt.longitude, pt.elevation))

    if not points:
        for route in gpx.routes:
            gpx_name = gpx_name or route.name
            for pt in route.points:
                points.append(GeoPoint(pt.latitude, pt.longitude, pt.elevation))

    if len(points) < 2:
        raise ValueError(f"{path}: no usable track or route geometry (need >= 2 points)")

    waypoints = [
        Waypoint(w.latitude, w.longitude, w.name, w.symbol) for w in gpx.waypoints
    ]

    resolved_name = name or gpx_name or (gpx.name if gpx.name else None) or path.stem
    distances = cumulative_distances(_point_tuples(points))

    return Route(name=resolved_name, points=points, distances_m=distances, waypoints=waypoints)
