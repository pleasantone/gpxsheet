"""Geometry cleanup via Ramer-Douglas-Peucker simplification.

Used as the "Geometry Cleanup" pipeline stage in docs/product.md: it strips GPS
noise and redundant points before bearing/turn analysis, which makes
decision-point detection far more robust on recorded tracks. docs/product.md targets
95%+ point reduction for recorded tracks.

This is a planar RDP using the equirectangular approximation, which is more than
accurate enough at the small tolerances (~10 m) used for cleanup.
"""

from __future__ import annotations

from .geo import project_to_segment
from .models import GeoPoint


def _perp_distance_m(p: GeoPoint, a: GeoPoint, b: GeoPoint) -> float:
    """Perpendicular distance (m) from point p to segment a–b, equirectangular."""
    return project_to_segment(p.lat, p.lon, (a.lat, a.lon), (b.lat, b.lon))[0]


def rdp(points: list[GeoPoint], tolerance_m: float) -> list[GeoPoint]:
    """Ramer-Douglas-Peucker simplification keeping points > tolerance_m.

    Returns a new list; endpoints are always preserved. An iterative stack is
    used to avoid recursion limits on long recorded tracks.
    """
    n = len(points)
    if n < 3 or tolerance_m <= 0:
        return list(points)

    keep = [False] * n
    keep[0] = keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        start, end = stack.pop()
        if end <= start + 1:
            continue
        dmax, idx = 0.0, start
        for i in range(start + 1, end):
            d = _perp_distance_m(points[i], points[start], points[end])
            if d > dmax:
                dmax, idx = d, i
        if dmax > tolerance_m:
            keep[idx] = True
            stack.append((start, idx))
            stack.append((idx, end))

    return [p for p, k in zip(points, keep, strict=True) if k]
