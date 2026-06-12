"""Geometry helpers: distances and bearings on the WGS-84 sphere.

Distances are computed with the haversine formula and kept internally in
meters. Miles are the user-facing unit (see :data:`METERS_PER_MILE`).
"""

from __future__ import annotations

import math
from collections.abc import Sequence

EARTH_RADIUS_M = 6_371_008.8  # mean Earth radius (IUGG)
METERS_PER_MILE = 1609.344
M_TO_FT = 3.280839895  # metres -> feet (elevation display)

# Equirectangular flat-earth constant for short-range projections and geographic
# buffering. One canonical value avoids the 0.5 % lat/lon discrepancy between the
# more precise 110 540 (lat) / 111 320 (lon) pair — the difference is well inside
# GPS noise and OSM buffer tolerances. Value chosen to match the legacy enrich.py
# buffer value (1 / 111 000) so OSM query-cache keys remain stable across refactors.
METERS_PER_DEG_LAT: float = 111_000.0   # m per ° (equirectangular approx, ±0.5 %)


def meters_to_miles(meters: float) -> float:
    return meters / METERS_PER_MILE


def miles_to_meters(miles: float) -> float:
    return miles * METERS_PER_MILE


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two points, in meters."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_M * math.asin(min(1.0, math.sqrt(a)))


def bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial compass bearing from point 1 to point 2, in degrees [0, 360)."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlambda = math.radians(lon2 - lon1)
    x = math.sin(dlambda) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dlambda)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def bearing_delta(b1: float, b2: float) -> float:
    """Signed smallest turn from bearing b1 to b2, in degrees (-180, 180].

    Positive = turn to the right (clockwise), negative = turn to the left.
    """
    d = (b2 - b1 + 180.0) % 360.0 - 180.0
    return 180.0 if d == -180.0 else d


def cumulative_distances(points: Sequence[tuple[float, float]]) -> list[float]:
    """Cumulative along-track distance (meters) for each point; first is 0."""
    out = [0.0]
    for (lat1, lon1), (lat2, lon2) in zip(points, points[1:], strict=False):
        out.append(out[-1] + haversine(lat1, lon1, lat2, lon2))
    return out


def project_to_segment(
    lat: float,
    lon: float,
    a: tuple[float, float],
    b: tuple[float, float],
) -> tuple[float, float]:
    """(distance_m, t) from ``(lat, lon)`` to geographic segment ``a``–``b``.

    ``a`` and ``b`` are ``(lat, lon)`` pairs. Uses a local equirectangular frame
    centered on the query point — accurate to < 0.5 % for road-scale offsets.
    ``t ∈ [0, 1]`` is the interpolation fraction along the segment.
    """
    coslat = math.cos(math.radians(lat))
    ax = (a[1] - lon) * coslat * METERS_PER_DEG_LAT
    ay = (a[0] - lat) * METERS_PER_DEG_LAT
    bx = (b[1] - lon) * coslat * METERS_PER_DEG_LAT
    by = (b[0] - lat) * METERS_PER_DEG_LAT
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 == 0.0:
        return math.hypot(ax, ay), 0.0
    t = max(0.0, min(1.0, (-ax * dx + -ay * dy) / seg2))
    nx, ny = ax + t * dx, ay + t * dy
    return math.hypot(nx, ny), t
