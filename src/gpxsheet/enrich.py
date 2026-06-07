"""Optional OpenStreetMap enrichment.

This is the "OSM Enrichment" pipeline stage from PRODUCT.md. It is optional and
requires the heavy geo stack installed via the ``osm`` extra::

    pip install "gpxsheet[osm]"

When available it derives navigation structure from OSM topology rather than raw
geometry, which is what PRODUCT.md's significance scoring is actually about:

* decision points come from *durable* road-name changes (PRODUCT.md Rule Set 1):
  the route is sampled for road names, names that don't persist for
  :data:`~gpxsheet.analysis.MIN_ROAD_RUN_MILES` are discarded as nearest-edge
  flapping at junctions, and each surviving change becomes "Left/Right/Continue
  onto <road>" with the turn direction taken from the track geometry,
* segments become those durable named roads (the road ribbon),
* fuel stations (amenity=fuel) near the route are merged with GPX-waypoint fuel.

This avoids the core failure of geometry-only detection, which cannot tell a
curving road from a junction and so floods twisty sport-touring roads with false
decisions. The geometry-only analysis still works without the extra (it just
over-detects on twisty roads). Road/fuel queries hit the live Overpass API.
"""

from __future__ import annotations

import re

from .analysis import (
    CONTINUE_MAX_ANGLE_DEG,
    MIN_ROAD_RUN_MILES,
    MIN_SEGMENT_MILES,
    _turn_word,
    coord_at_meters,
    merge_close_decisions,
    turn_angle_at_mile,
)
from .geo import haversine, meters_to_miles
from .models import DecisionKind, DecisionPoint, FuelStop, Route, Segment
from .profiles import SCORE_ROAD_NAME_CHANGE, SCORE_STATE_HWY_JUNCTION

_DEG_PER_M = 1.0 / 111_000.0  # crude latitude-degrees per meter, fine for buffering

# Names that read as a numbered/limited-access highway (higher significance).
_HIGHWAY_RE = re.compile(
    r"\b(?:freeway|expressway|highway|turnpike|(?:I|US|CA|SR|US-?\d|state route))\b|"
    r"\b[A-Z]{1,2}-\d+\b",
    re.IGNORECASE,
)

_DEG_PER_M = 1.0 / 111_000.0  # crude latitude-degrees per meter, fine for buffering


def osm_available() -> bool:
    """True if the optional OSM dependency (osmnx) is importable."""
    try:
        import osmnx  # noqa: F401
    except ImportError:
        return False
    return True


def _require_osm():
    try:
        import osmnx as ox
    except ImportError as exc:  # pragma: no cover - exercised only without extra
        raise ImportError(
            'OSM enrichment requires the optional "osm" extra: pip install "gpxsheet[osm]"'
        ) from exc
    return ox


def _route_line(route: Route):
    import shapely.geometry as sg

    return sg.LineString([(p.lon, p.lat) for p in route.points])


def _edge_name(edges_gdf, edge_key) -> str | None:
    """Pull a single road name out of an edges GeoDataFrame row.

    OSM edge names may be missing (NaN), a string, or a list (a way carrying
    several names); normalize all three to one string or None.
    """
    if "name" not in edges_gdf.columns:
        return None
    try:
        name = edges_gdf.loc[edge_key, "name"]
    except KeyError:
        return None
    if isinstance(name, list):
        name = name[0] if name else None
    if name is None or (isinstance(name, float)):  # float == NaN here
        return None
    return str(name)


def enrich_route(
    route: Route,
    *,
    road_buffer_m: float = 50.0,
    fuel_buffer_m: float = 400.0,
    sample_spacing_m: float = 60.0,
    include_fuel: bool = True,
) -> Route:
    """Replace decisions/segments with OSM-derived ones and add fuel, in place."""
    ox = _require_osm()

    line = _route_line(route)
    graph = ox.graph_from_polygon(
        line.buffer(road_buffer_m * _DEG_PER_M),
        network_type="drive",
        retain_all=True,
        truncate_by_edge=True,
    )
    edges_gdf = ox.graph_to_gdfs(graph, nodes=False)

    sample_m, names = _sample_road_names(route, ox, graph, edges_gdf, sample_spacing_m)
    runs = _durable_runs(sample_m, names, MIN_ROAD_RUN_MILES * 1609.344)
    if runs:
        route.segments = _segments_from_runs(route, runs)
        route.decision_points = _decisions_from_runs(route, runs)

    if include_fuel:
        _add_fuel(route, ox, line, fuel_buffer_m)
    return route


def _sample_road_names(route, ox, graph, edges_gdf, spacing_m: float):
    """Sample the OSM road name at evenly spaced points along the route."""
    total_m = route.length_m
    n = max(2, int(total_m / spacing_m) + 1)
    sample_m = [total_m * i / (n - 1) for i in range(n)]
    coords = [coord_at_meters(route, m) for m in sample_m]
    edge_keys = ox.distance.nearest_edges(graph, [c[1] for c in coords], [c[0] for c in coords])
    names = [_edge_name(edges_gdf, tuple(k)) for k in edge_keys]
    return sample_m, names


def _durable_runs(sample_m, names, min_run_m: float) -> list[tuple[float, str]]:
    """Collapse sampled names into runs of road, dropping transient flaps.

    A run shorter than ``min_run_m`` is discarded as nearest-edge snapping at a
    junction (unless it's the first/last run); the surrounding road then joins
    up. Returns ``(start_mile, name)`` for each surviving road in order.
    """
    # Forward-fill gaps (None) with the previous known name.
    filled: list[str | None] = []
    prev: str | None = None
    for nm in names:
        prev = nm or prev
        filled.append(prev)

    # Run-length encode into [start_m, name, end_m].
    runs: list[list] = []
    for m, nm in zip(sample_m, filled, strict=True):
        if runs and runs[-1][1] == nm:
            runs[-1][2] = m
        else:
            runs.append([m, nm, m])

    # Drop short interior runs and None runs, then merge now-adjacent same names.
    kept: list[list] = []
    for i, run in enumerate(runs):
        if run[1] is None:
            continue
        is_edge = i == 0 or i == len(runs) - 1
        if (run[2] - run[0]) >= min_run_m or is_edge:
            if kept and kept[-1][1] == run[1]:
                kept[-1][2] = run[2]
            else:
                kept.append(run)

    return [(meters_to_miles(r[0]), r[1]) for r in kept]


def _segments_from_runs(route: Route, runs: list[tuple[float, str]]) -> list[Segment]:
    segments: list[Segment] = []
    for i, (start, name) in enumerate(runs):
        end = runs[i + 1][0] if i + 1 < len(runs) else route.length_miles
        if segments and end - start < MIN_SEGMENT_MILES:
            segments[-1] = Segment(segments[-1].name, segments[-1].start_mile, round(end, 1))
            continue
        segments.append(Segment(name=name, start_mile=round(start, 1), end_mile=round(end, 1)))
    return segments


def _is_highway(name: str) -> bool:
    return bool(_HIGHWAY_RE.search(name))


def _road_change_significance(name: str, angle: float) -> int:
    sig = SCORE_ROAD_NAME_CHANGE
    if _is_highway(name):
        sig = max(sig, SCORE_STATE_HWY_JUNCTION)
    if abs(angle) >= 60.0:
        sig += 10
    return sig


def _decisions_from_runs(route: Route, runs: list[tuple[float, str]]) -> list[DecisionPoint]:
    """Each durable road-name change is a decision: turn direction from geometry."""
    decisions: list[DecisionPoint] = []
    for start_mile, name in runs[1:]:  # the first road is where you start, not a decision
        angle = turn_angle_at_mile(route, start_mile)
        lat, lon = coord_at_meters(route, start_mile * 1609.344)
        if abs(angle) < CONTINUE_MAX_ANGLE_DEG:
            instruction = f"Continue onto {name}"
        else:
            instruction = f"{_turn_word(angle)} onto {name}"
        decisions.append(
            DecisionPoint(
                mile=round(start_mile, 1),
                instruction=instruction,
                significance=_road_change_significance(name, angle),
                lat=lat,
                lon=lon,
                kind=DecisionKind.CRITICAL_TURN,
                turn_angle=round(angle, 1),
            )
        )
    return merge_close_decisions(decisions)


def _clean_str(value) -> str | None:
    """A non-empty string, or None for NaN/None/blank (OSM cells are often NaN)."""
    if value is None:
        return None
    if isinstance(value, float):  # NaN
        return None
    text = str(value).strip()
    return text or None


def _add_fuel(route, ox, line, fuel_buffer_m: float) -> None:
    """Merge OSM amenity=fuel stations near the route into route.fuel_stops."""
    from osmnx._errors import InsufficientResponseError

    try:
        feats = ox.features_from_polygon(
            line.buffer(fuel_buffer_m * _DEG_PER_M), tags={"amenity": "fuel"}
        )
    except InsufficientResponseError:
        return  # no fuel stations anywhere near the route
    if feats.empty:
        return

    osm_stops: list[FuelStop] = []
    for _, row in feats.iterrows():
        geom = row.geometry
        pt = geom.centroid if geom.geom_type != "Point" else geom
        nearest = min(
            range(len(route.points)),
            key=lambda i: haversine(route.points[i].lat, route.points[i].lon, pt.y, pt.x),
        )
        name = _clean_str(row.get("name")) or _clean_str(row.get("brand")) or "Fuel"
        osm_stops.append(
            FuelStop(
                mile=round(meters_to_miles(route.distances_m[nearest]), 1),
                name=str(name),
                lat=pt.y,
                lon=pt.x,
            )
        )

    # Merge with existing (waypoint) stops, dropping near-duplicates by mileage.
    merged = list(route.fuel_stops)
    for stop in osm_stops:
        if not any(abs(stop.mile - e.mile) < 0.3 for e in merged):
            merged.append(stop)
    merged.sort(key=lambda s: s.mile)
    route.fuel_stops = merged
