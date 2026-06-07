"""Optional OpenStreetMap enrichment.

This is the "OSM Enrichment" pipeline stage from PRODUCT.md. It is optional and
requires the heavy geo stack installed via the ``osm`` extra::

    pip install "gpxsheet[osm]"

When available it adds road names to decision points and segments and discovers
fuel stations near the route. The geometry-only analysis works without it, so
everything here degrades gracefully.

Marked experimental: it performs live Overpass/OSM queries and has no offline
test coverage yet.
"""

from __future__ import annotations

from .models import FuelStop, Route


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


def enrich_route(route: Route, *, search_dist_m: float = 60.0) -> Route:
    """Annotate ``route`` with OSM road names and fuel stations, in place.

    Args:
        route: The route to enrich.
        search_dist_m: How far off-route (meters) to look for fuel stations.
    """
    ox = _require_osm()

    lats = [p.lat for p in route.points]
    lons = [p.lon for p in route.points]
    north, south = max(lats), min(lats)
    east, west = max(lons), min(lons)
    pad = 0.02  # ~2 km bbox padding

    # --- Road names for decision points -------------------------------------
    try:
        graph = ox.graph_from_bbox(
            (west - pad, south - pad, east + pad, north + pad), network_type="drive"
        )
        if route.decision_points:
            dp_lats = [d.lat for d in route.decision_points]
            dp_lons = [d.lon for d in route.decision_points]
            edges = ox.distance.nearest_edges(graph, dp_lons, dp_lats)
            _, edge_data = ox.graph_to_gdfs(graph)
            renamed = []
            for dp, edge in zip(route.decision_points, edges, strict=True):
                name = _edge_name(edge_data, edge)
                instruction = f"{dp.instruction} onto {name}" if name else dp.instruction
                renamed.append(_replace(dp, instruction=instruction))
            route.decision_points = renamed
    except Exception:  # pragma: no cover - network/data dependent
        pass

    # --- Fuel stations near the route ---------------------------------------
    try:
        import shapely.geometry as sg

        line = sg.LineString([(p.lon, p.lat) for p in route.points])
        poly = line.buffer(search_dist_m / 111_000.0)  # crude deg-per-meter
        feats = ox.features_from_polygon(poly, tags={"amenity": "fuel"})
        from .geo import haversine, meters_to_miles

        stops: list[FuelStop] = []
        for _, row in feats.iterrows():
            geom = row.geometry.centroid
            nearest = min(
                range(len(route.points)),
                key=lambda i: haversine(route.points[i].lat, route.points[i].lon, geom.y, geom.x),
            )
            stops.append(
                FuelStop(
                    mile=round(meters_to_miles(route.distances_m[nearest]), 1),
                    name=str(row.get("name") or "Fuel"),
                    lat=geom.y,
                    lon=geom.x,
                )
            )
        if stops:
            stops.sort(key=lambda s: s.mile)
            route.fuel_stops = stops
    except Exception:  # pragma: no cover - network/data dependent
        pass

    return route


def _edge_name(edge_data, edge) -> str | None:  # pragma: no cover - osm dependent
    try:
        name = edge_data.loc[edge].get("name")
    except Exception:
        return None
    if isinstance(name, list):
        name = name[0] if name else None
    return str(name) if name else None


def _replace(dp, **changes):
    from dataclasses import replace

    return replace(dp, **changes)
