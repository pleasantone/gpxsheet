"""Optional OpenStreetMap enrichment.

This is the "OSM Enrichment" pipeline stage from PRODUCT.md. It is optional and
requires the heavy geo stack installed via the ``osm`` extra::

    pip install "gpxsheet[osm]"

When available it:

* annotates geometry-detected decision points with the road being turned onto
  ("Left" -> "Left onto Skaggs Springs Rd"),
* names route segments by the dominant road along each leg (the road ribbon),
* discovers fuel stations near the route and merges them with any GPX-waypoint
  fuel stops.

The geometry-only analysis works without it, so absence of the extra degrades
gracefully. Road/fuel queries hit the live Overpass API.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import replace

from .geo import haversine, meters_to_miles
from .models import DecisionPoint, FuelStop, Route, Segment

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


def _coord_at_meters(route: Route, meters: float) -> tuple[float, float]:
    """(lat, lon) of the route point nearest a given along-track distance."""
    dist = route.distances_m
    lo, hi = 0, len(dist) - 1
    target = max(0.0, min(meters, dist[-1]))
    while lo < hi:
        mid = (lo + hi) // 2
        if dist[mid] < target:
            lo = mid + 1
        else:
            hi = mid
    p = route.points[lo]
    return p.lat, p.lon


def enrich_route(
    route: Route,
    *,
    road_buffer_m: float = 50.0,
    fuel_buffer_m: float = 400.0,
    decision_lookahead_m: float = 60.0,
    sample_spacing_m: float = 150.0,
    include_fuel: bool = True,
) -> Route:
    """Annotate ``route`` with OSM road names and fuel stations, in place."""
    ox = _require_osm()

    line = _route_line(route)
    graph = ox.graph_from_polygon(
        line.buffer(road_buffer_m * _DEG_PER_M),
        network_type="drive",
        retain_all=True,
        truncate_by_edge=True,
    )
    edges_gdf = ox.graph_to_gdfs(graph, nodes=False)

    _name_decision_points(route, ox, graph, edges_gdf, decision_lookahead_m)
    _name_segments(route, ox, graph, edges_gdf, sample_spacing_m)
    if include_fuel:
        _add_fuel(route, ox, line, fuel_buffer_m)
    return route


def _name_decision_points(route, ox, graph, edges_gdf, lookahead_m: float) -> None:
    """Replace each turn's instruction with "<turn> onto <road>" when known.

    The road named is the one *just past* the turn (the road you end up on).
    """
    if not route.decision_points:
        return
    targets = []
    for dp in route.decision_points:
        meters = dp.mile * 1609.344 + lookahead_m
        targets.append(_coord_at_meters(route, meters))
    xs = [lon for _, lon in targets]
    ys = [lat for lat, _ in targets]
    edge_keys = ox.distance.nearest_edges(graph, xs, ys)

    renamed: list[DecisionPoint] = []
    for dp, key in zip(route.decision_points, edge_keys, strict=True):
        name = _edge_name(edges_gdf, tuple(key))
        instruction = f"{dp.instruction} onto {name}" if name else dp.instruction
        renamed.append(replace(dp, instruction=instruction))
    route.decision_points = renamed


def _name_segments(route, ox, graph, edges_gdf, spacing_m: float) -> None:
    """Rename each segment to the most common road name along its mileage."""
    if not route.segments:
        return
    total_m = route.length_m
    n = max(2, int(total_m / spacing_m) + 1)
    sample_m = [total_m * i / (n - 1) for i in range(n)]
    coords = [_coord_at_meters(route, m) for m in sample_m]
    xs = [lon for _, lon in coords]
    ys = [lat for lat, _ in coords]
    edge_keys = ox.distance.nearest_edges(graph, xs, ys)
    sample_names = [_edge_name(edges_gdf, tuple(k)) for k in edge_keys]

    renamed: list[Segment] = []
    for seg in route.segments:
        names = [
            sample_names[i]
            for i, m in enumerate(sample_m)
            if seg.start_mile <= meters_to_miles(m) <= seg.end_mile and sample_names[i]
        ]
        if names:
            best = Counter(names).most_common(1)[0][0]
            renamed.append(replace(seg, name=best))
        else:
            renamed.append(seg)
    route.segments = renamed


def _add_fuel(route, ox, line, fuel_buffer_m: float) -> None:
    """Merge OSM amenity=fuel stations near the route into route.fuel_stops."""
    feats = ox.features_from_polygon(
        line.buffer(fuel_buffer_m * _DEG_PER_M), tags={"amenity": "fuel"}
    )
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
        name = row.get("name") or row.get("brand") or "Fuel"
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
