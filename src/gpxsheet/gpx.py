"""GPX loading: turn a ``.gpx`` file into a :class:`Route` geometry.

Supports the inputs listed in docs/product.md: GPX tracks (``<trk>``), routes
(``<rte>``) and waypoints (``<wpt>``). Track segments and multiple tracks are
concatenated in document order; waypoints are kept separately for fuel/marker
enrichment.

Garmin BaseCamp routes are a special case: their real road-snapped geometry lives
inside per-rtept ``gpxx:RoutePointExtension``/``gpxx:rpt`` extensions rather than the
sparse ``<rtept>`` list, and announced stops are tagged ``trp:ViaPoint``. We harvest
the dense geometry as a track and lift via points to waypoints -- see
docs/basecamp-routes.md.
"""

from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import gpxpy

from .geo import cumulative_distances
from .models import GeoPoint, Route, Waypoint

# Garmin extension namespaces used by BaseCamp / Garmin Desktop App route exports.
# A BaseCamp route stores its real road-snapped geometry inside
# ``gpxx:RoutePointExtension``/``gpxx:rpt`` children of each ``<rtept>`` (not in the
# sparse ``<rtept>`` list itself), and marks announced stops with ``trp:ViaPoint``.
# See docs/basecamp-routes.md for the full structure.
_GPXX = "{http://www.garmin.com/xmlschemas/GpxExtensions/v3}"
_TRP = "{http://www.garmin.com/xmlschemas/TripExtensions/v1}"

# Reject any DTD/entity declarations before handing the XML to gpxpy. Real GPX
# never carries a DOCTYPE; rejecting one neutralises XXE and entity-expansion
# ("billion laughs") attacks regardless of which XML backend gpxpy selects
# (the stdlib parser blocks both, but gpxpy prefers lxml when installed, whose
# default parser resolves entities). See docs/security-audit.md.
_DOCTYPE_RE = re.compile(r"<!(?:DOCTYPE|ENTITY)\b", re.IGNORECASE)


def _reject_unsafe_xml(text: str, source: str) -> None:
    if _DOCTYPE_RE.search(text):
        raise ValueError(f"{source}: GPX with a DTD/entity declaration is not allowed")


def _point_tuples(points: list[GeoPoint]) -> list[tuple[float, float]]:
    return [(p.lat, p.lon) for p in points]


def _parse_garmin_time(text: str | None) -> datetime | None:
    """Parse a Garmin ``trp:`` ISO-8601 timestamp, tolerating a trailing ``Z``."""
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.strip().replace("Z", "+00:00"))
    except ValueError:
        return None


def _garmin_route_dense_points(route: object) -> list[GeoPoint] | None:
    """Reconstruct the road-snapped track from a BaseCamp/Garmin ``<rte>``.

    Each ``<rtept>`` carries a ``gpxx:RoutePointExtension`` whose ``gpxx:rpt``
    children are the calculated path from that rtept toward the *next* one. In
    document order we emit each rtept's own coordinate followed by its ``rpt``
    children, yielding a dense track equivalent to a recorded ``<trk>``.

    Returns ``None`` when no rtept carries a ``RoutePointExtension`` (i.e. a plain
    route that should use the caller's sparse fallback).
    """
    dense: list[GeoPoint] = []
    saw_extension = False
    for rtept in route.points:  # type: ignore[attr-defined]
        dense.append(GeoPoint(rtept.latitude, rtept.longitude, rtept.elevation))
        for ext in rtept.extensions:
            if ext.tag != _GPXX + "RoutePointExtension":
                continue
            saw_extension = True
            for rpt in ext:
                if rpt.tag != _GPXX + "rpt":
                    continue
                try:
                    lat = float(rpt.get("lat"))
                    lon = float(rpt.get("lon"))
                except (TypeError, ValueError):
                    continue  # best-effort: skip a malformed rpt child
                dense.append(GeoPoint(lat, lon))
    return dense if saw_extension else None


def _is_shaping_point(name: str | None, extensions: list) -> bool:
    """True for a route point that should not appear as a named stop.

    Mirrors GPXtable's ``shaping_point()``: an unnamed point, a Garmin shaping
    point (``...ShapingPoint`` extension), or a name flagged as a via/shaping
    point (``"Via …"`` prefix or ``"(V)"`` suffix).
    """
    if not name:
        return True
    if name.startswith("Via ") or name.endswith("(V)"):
        return True
    return any("ShapingPoint" in getattr(ext, "tag", "") for ext in extensions)


def _plain_route_named_waypoints(route: object) -> list[Waypoint]:
    """Lift named, non-shaping ``<rtept>``s of a plain route to waypoints.

    A non-Garmin ``<rte>`` (no ``RoutePointExtension``) carries its stops as named
    route points rather than ``<wpt>``s. Surface them so they drive POIs / the
    route table, skipping shaping/via points (see :func:`_is_shaping_point`).
    """
    out: list[Waypoint] = []
    for rtept in route.points:  # type: ignore[attr-defined]
        if _is_shaping_point(rtept.name, rtept.extensions):
            continue
        out.append(Waypoint(rtept.latitude, rtept.longitude, rtept.name, rtept.symbol))
    return out


def _garmin_route_via_waypoints(route: object) -> list[Waypoint]:
    """Promote a Garmin route's announced stops (``trp:ViaPoint``) to waypoints.

    Shaping points (no ``trp:ViaPoint``) are intentionally excluded: their names
    are reverse-geocoded street addresses, not rider-meaningful labels. Optional
    arrival/departure times are attached when present, with two corrections from
    the Garmin schema: the first via's ``ArrivalTime`` and the last via's
    ``DepartureTime`` are semantically invalid (BaseCamp writes placeholders), and
    a self-contradictory pair (departure before arrival) is dropped entirely.
    """
    vias: list[Waypoint] = []
    for rtept in route.points:  # type: ignore[attr-defined]
        for ext in rtept.extensions:
            if ext.tag != _TRP + "ViaPoint":
                continue
            arr = _parse_garmin_time(
                getattr(ext.find(_TRP + "ArrivalTime"), "text", None)
            )
            dep = _parse_garmin_time(
                getattr(ext.find(_TRP + "DepartureTime"), "text", None)
            )
            if arr is not None and dep is not None and dep < arr:
                arr = dep = None
            vias.append(
                Waypoint(
                    rtept.latitude,
                    rtept.longitude,
                    rtept.name,
                    rtept.symbol,
                    arrival_time=arr,
                    departure_time=dep,
                )
            )
            break
    # Schema: arrival on the first via and departure on the last via are invalid.
    if vias:
        vias[0] = replace(vias[0], arrival_time=None)
        vias[-1] = replace(vias[-1], departure_time=None)
    return vias


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
    text = path.read_text(encoding="utf-8")
    _reject_unsafe_xml(text, str(path))
    gpx = gpxpy.parse(text)

    points: list[GeoPoint] = []
    gpx_name: str | None = None
    # Point index where each track after the first begins (≈ one day per track).
    day_breaks: list[int] = []

    # Prefer tracks; fall back to routes.
    for track in gpx.tracks:
        gpx_name = gpx_name or track.name
        start_index = len(points)
        for seg in track.segments:
            for pt in seg.points:
                points.append(GeoPoint(pt.latitude, pt.longitude, pt.elevation))
        if start_index > 0 and len(points) > start_index:
            day_breaks.append(start_index)

    # Garmin BaseCamp routes hide their real road geometry inside per-rtept
    # extensions; harvest it as a dense track and lift announced stops to
    # waypoints. Plain routes fall through to the sparse <rtept> list.
    via_waypoints: list[Waypoint] = []
    if not points:
        for route in gpx.routes:
            gpx_name = gpx_name or route.name
            dense = _garmin_route_dense_points(route)
            if dense is not None:
                points.extend(dense)
                via_waypoints.extend(_garmin_route_via_waypoints(route))
            else:
                for rpt in route.points:
                    points.append(
                        GeoPoint(rpt.latitude, rpt.longitude, rpt.elevation)
                    )
                via_waypoints.extend(_plain_route_named_waypoints(route))

    if len(points) < 2:
        found = len(points)
        raise ValueError(
            f"{path}: no usable track or route geometry "
            f"(need >= 2 points, found {found})"
        )

    waypoints = [
        Waypoint(w.latitude, w.longitude, w.name, w.symbol) for w in gpx.waypoints
    ]
    waypoints.extend(via_waypoints)

    resolved_name = name or gpx_name or (gpx.name if gpx.name else None) or path.stem
    distances = cumulative_distances(_point_tuples(points))

    return Route(
        name=resolved_name,
        points=points,
        distances_m=distances,
        waypoints=waypoints,
        day_breaks=day_breaks,
    )
