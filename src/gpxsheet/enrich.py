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
from dataclasses import replace

from .analysis import (
    CONTINUE_MAX_ANGLE_DEG,
    MIN_ROAD_RUN_MILES,
    MIN_SEGMENT_MILES,
    _turn_word,
    coord_at_meters,
    merge_close_decisions,
    turn_angle_at_mile,
)
from .geo import bearing, haversine, meters_to_miles, miles_to_meters
from .junctions import branches_not_taken, direction_word, relative_angle, roundabout_exit_number
from .models import Branch, DecisionKind, DecisionPoint, FuelStop, Route, Segment
from .profiles import SCORE_ROAD_NAME_CHANGE, SCORE_STATE_HWY_JUNCTION

_DEG_PER_M = 1.0 / 111_000.0  # crude latitude-degrees per meter, fine for buffering

# Names that read as a numbered/limited-access highway (higher significance).
_HIGHWAY_RE = re.compile(
    r"\b(?:freeway|expressway|highway|turnpike|(?:I|US|CA|SR|US-?\d|state route))\b|"
    r"\b[A-Z]{1,2}-\d+\b",
    re.IGNORECASE,
)


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


def _edge_value(edges_gdf, edge_key, attr: str) -> str | None:
    """Pull a single OSM tag value off an edges GeoDataFrame row.

    OSM values may be missing (NaN), a string, or a list (a way carrying several
    values); normalize all three to one string or None.
    """
    if attr not in edges_gdf.columns:
        return None
    try:
        value = edges_gdf.loc[edge_key, attr]
    except KeyError:
        return None
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None or isinstance(value, float):  # float == NaN here
        return None
    return str(value)


def _edge_name(edges_gdf, edge_key) -> str | None:
    """The road name for an edge (see :func:`_edge_value`)."""
    return _edge_value(edges_gdf, edge_key, "name")


# OSM `surface` values (and highway=track) that mean the road is not paved.
_UNPAVED_SURFACES = frozenset(
    {
        "unpaved", "gravel", "fine_gravel", "compacted", "dirt", "ground", "earth",
        "mud", "sand", "grass", "pebblestone", "rock", "woodchips",
    }
)


def _is_unpaved(surface: str | None, highway: str | None) -> bool:
    return (surface or "").lower() in _UNPAVED_SURFACES or (highway or "").lower() == "track"


# A ferry only counts as a crossing if the route actually rides along this much
# of it. Merely passing within the corridor buffer of a terminal (e.g. riding
# past a bay ferry pier) leaves only a sliver of the long ferry way overlapping.
FERRY_FOLLOW_FRACTION = 0.5


# A single OSM (graph/feature) query must stay tractable, so a long route is
# processed in chunks bounded by both point count and mileage.
MAX_CHUNK_POINTS = 4000
MAX_CHUNK_MILES = 120.0


def enrich_route(
    route: Route,
    *,
    road_buffer_m: float = 50.0,
    fuel_buffer_m: float = 400.0,
    sample_spacing_m: float = 60.0,
    include_fuel: bool = True,
    include_hazards: bool = False,
) -> Route:
    """Replace decisions/segments with OSM-derived ones and add fuel, in place.

    Large routes are split into chunks (bounded points + mileage) so each OSM
    query stays tractable; the per-chunk road-name samples are stitched back
    together before durable-run detection. Small routes use a single chunk.

    ``unpaved_miles`` is always estimated from the sampled ``surface`` tags (it
    reuses the road-name nearest-edge lookups, so it's free). ``include_hazards``
    additionally runs a ferry query (an extra Overpass call) for :mod:`validate`.
    """
    ox = _require_osm()
    import shapely.geometry as sg

    total_m = route.length_m
    n = max(2, int(total_m / sample_spacing_m) + 1)
    sample_m = [total_m * i / (n - 1) for i in range(n)]
    coords = [coord_at_meters(route, m) for m in sample_m]
    names: list[str | None] = [None] * len(sample_m)
    unpaved: list[bool] = [False] * len(sample_m)
    node_seq: list[int | None] = [None] * len(sample_m)  # nearest OSM node per sample
    graphs: list[tuple[int, int, object]] = []  # (i0, i1, graph) for the topology pass

    chunks = _chunk_ranges(route)
    for i0, i1 in chunks:
        cs, ce = route.distances_m[i0], route.distances_m[i1]
        sub = [(route.points[k].lon, route.points[k].lat) for k in range(i0, i1 + 1)]
        if len(sub) < 2:
            continue
        graph = ox.graph_from_polygon(
            sg.LineString(sub).buffer(road_buffer_m * _DEG_PER_M),
            network_type="drive",
            retain_all=True,
            truncate_by_edge=True,
        )
        ox.bearing.add_edge_bearings(graph)  # 'bearing' per edge, for branch geometry
        graphs.append((i0, i1, graph))
        edges_gdf = ox.graph_to_gdfs(graph, nodes=False)
        idxs = [k for k, m in enumerate(sample_m) if cs - 1e-6 <= m <= ce + 1e-6]
        if not idxs:
            continue
        xs = [coords[k][1] for k in idxs]
        ys = [coords[k][0] for k in idxs]
        keys = ox.distance.nearest_edges(graph, xs, ys)
        for k, key in zip(idxs, keys, strict=True):
            edge = tuple(key)
            names[k] = _edge_name(edges_gdf, edge)
            unpaved[k] = _is_unpaved(
                _edge_value(edges_gdf, edge, "surface"),
                _edge_value(edges_gdf, edge, "highway"),
            )
            # Nearest node = the closer endpoint of the nearest edge. (Avoids
            # ox.distance.nearest_nodes, which needs the scikit-learn extra.)
            node_seq[k] = _closer_endpoint(graph, edge, coords[k])

    runs = _durable_runs(sample_m, names, miles_to_meters(MIN_ROAD_RUN_MILES))
    if runs:
        route.segments = _segments_from_runs(route, runs)
        route.decision_points = _decisions_from_runs(route, runs)
        try:  # roads-not-taken + roundabouts are best-effort; never break enrichment
            _apply_junction_topology(route, graphs, node_seq, sample_m, ox)
        except Exception:  # noqa: BLE001 - degrade to plain turns on any topology error
            pass

    spacing_m = total_m / (n - 1) if n > 1 else 0.0
    route.unpaved_miles = round(meters_to_miles(sum(unpaved) * spacing_m), 1)

    if include_fuel:
        _add_fuel(route, ox, chunks, fuel_buffer_m)
    if include_hazards:
        route.ferry_crossings = _detect_ferries(route, ox, sg, road_buffer_m)
    return route


def _detect_ferries(route: Route, ox, sg, buffer_m: float) -> list[str]:
    """Names/types of OSM ferry ways (route=ferry) crossing the route corridor."""
    from osmnx._errors import InsufficientResponseError

    line = sg.LineString([(p.lon, p.lat) for p in route.points])
    corridor = line.buffer(buffer_m * _DEG_PER_M)
    try:
        feats = ox.features_from_polygon(corridor, tags={"route": "ferry"})
    except InsufficientResponseError:
        return []
    if feats.empty:
        return []
    names = []
    for _, row in feats.iterrows():
        ferry_len = getattr(row.geometry, "length", 0.0)
        if not ferry_len:
            continue
        # Count only ferries the route rides along, not ones whose terminal we pass.
        overlap = row.geometry.intersection(corridor).length
        if overlap >= FERRY_FOLLOW_FRACTION * ferry_len:
            names.append(_clean_str(row.get("name")) or "ferry")
    return sorted(set(names))


def _chunk_ranges(
    route: Route, max_points: int = MAX_CHUNK_POINTS, max_miles: float = MAX_CHUNK_MILES
) -> list[tuple[int, int]]:
    """Inclusive point-index ranges tiling the route; consecutive chunks share a
    boundary point so road-name sampling has no gap between them."""
    n = len(route.points)
    if n < 2:
        return [(0, n - 1)] if n else []
    max_m = miles_to_meters(max_miles)
    dist = route.distances_m
    ranges: list[tuple[int, int]] = []
    i0 = 0
    while i0 < n - 1:
        i1 = i0
        while i1 + 1 < n and (i1 + 1 - i0) < max_points and (dist[i1 + 1] - dist[i0]) <= max_m:
            i1 += 1
        if i1 == i0:  # always make progress, even across one very long segment
            i1 = i0 + 1
        ranges.append((i0, i1))
        i0 = i1
    return ranges


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
        lat, lon = coord_at_meters(route, miles_to_meters(start_mile))
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


# ---------------------------------------------------------------------------
# Junction topology: roads-not-taken (ghosted stubs) and roundabout exits.
# These read the osmnx networkx graph (node degree, edge bearings, junction
# tags) and feed the pure helpers in gpxsheet.junctions. All best-effort: if the
# graph is ambiguous the decision keeps its plain "turn onto <road>" form.
# ---------------------------------------------------------------------------

ROUNDABOUT_JUNCTION_TAGS = frozenset({"roundabout", "circular"})
_BEARING_WINDOW_M = 30.0  # geometry sampled either side of a decision for headings


def _first(value):
    """First element of an OSM list-valued tag, else the value (or None)."""
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _closer_endpoint(graph, edge, latlon):
    """The nearer of an edge's two endpoints to ``(lat, lon)`` -- the route's node
    at that sample, without ``ox.distance.nearest_nodes`` (which needs sklearn)."""
    lat, lon = latlon
    u, v = edge[0], edge[1]
    du = haversine(lat, lon, graph.nodes[u]["y"], graph.nodes[u]["x"])
    dv = haversine(lat, lon, graph.nodes[v]["y"], graph.nodes[v]["x"])
    return u if du <= dv else v


def _nearest_graph_node(graph, lat: float, lon: float, ox=None):
    """Graph node nearest ``(lat, lon)`` by haversine (no sklearn dependency)."""
    best, best_d = None, float("inf")
    for nid, data in graph.nodes(data=True):
        d = haversine(lat, lon, data["y"], data["x"])
        if d < best_d:
            best, best_d = nid, d
    return best


def _junction_degree(graph, node) -> int:
    """Distinct roads meeting at ``node`` (a fork needs >= 3)."""
    return len(set(graph.successors(node)) | set(graph.predecessors(node)))


def _outgoing_branches(graph, node) -> list[tuple[str | None, float]]:
    """(name, compass bearing) for each edge leaving ``node``."""
    out: list[tuple[str | None, float]] = []
    for _, _v, data in graph.out_edges(node, data=True):
        b = data.get("bearing")
        if b is None:
            continue
        out.append((_clean_str(_first(data.get("name"))), float(b)))
    return out


def _route_bearings_at(route: Route, mile: float) -> tuple[float, float]:
    """(arrival, departure) compass bearings of the track through ``mile``."""
    center = miles_to_meters(mile)
    before = coord_at_meters(route, max(0.0, center - _BEARING_WINDOW_M))
    at = coord_at_meters(route, center)
    after = coord_at_meters(route, min(route.length_m, center + _BEARING_WINDOW_M))
    return (
        bearing(before[0], before[1], at[0], at[1]),
        bearing(at[0], at[1], after[0], after[1]),
    )


def _graph_for_mile(graphs, route: Route, mile: float):
    target = miles_to_meters(mile)
    for i0, i1, g in graphs:
        if route.distances_m[i0] - 1.0 <= target <= route.distances_m[i1] + 1.0:
            return g
    return graphs[0][2] if graphs else None


def _branches_for(graph, route: Route, decision: DecisionPoint, ox):
    node = _nearest_graph_node(graph, decision.lat, decision.lon, ox)
    if node is None or _junction_degree(graph, node) < 3:  # not a fork
        return ()
    arrival, taken = _route_bearings_at(route, decision.mile)
    instr = decision.instruction
    taken_name = instr.rsplit(" onto ", 1)[-1] if " onto " in instr else None
    return branches_not_taken(
        arrival, taken, _outgoing_branches(graph, node), taken_name=taken_name
    )


def _roundabout_rings(graph) -> list[list]:
    """Ordered node rings for each one-way roundabout/circular way in the graph."""
    radj: dict = {}
    nodes: set = set()
    for u, v, data in graph.edges(data=True):
        if _first(data.get("junction")) in ROUNDABOUT_JUNCTION_TAGS:
            radj.setdefault(u, []).append(v)
            nodes.update((u, v))
    rings, seen = [], set()
    for start in nodes:
        if start in seen:
            continue
        ring, cur = [], start
        while cur is not None and cur not in seen:
            seen.add(cur)
            ring.append(cur)
            nxt = radj.get(cur)
            cur = nxt[0] if nxt else None
        if len(ring) >= 3:
            rings.append(ring)
    return rings


def _ring_exit_flags(graph, ring: list) -> list[bool]:
    """Per ring node, whether it has a spur leaving the circle (an exit)."""
    ringset = set(ring)
    flags = []
    for nid in ring:
        spur = any(v not in ringset for v in graph.successors(nid)) or any(
            u not in ringset for u in graph.predecessors(nid)
        )
        flags.append(spur)
    return flags


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"


def _road_after(route: Route, mile: float) -> str | None:
    """Segment name covering ``mile`` (the road you leave a roundabout onto)."""
    for seg in route.segments:
        if seg.start_mile <= mile <= seg.end_mile:
            return seg.name
    return None


def _roundabout_spur_branches(graph, ring, entry_node, exit_node, arrival_bearing):
    """Exits the route does NOT take, as branches off the rider's entry heading.

    Each non-taken spur (a road leaving the circle, excluding the approach you
    arrived on and the exit you take) becomes a :class:`Branch`, so a roundabout's
    other exits render as ghosted stubs just like a normal junction's branches.
    """
    ringset = set(ring)
    branches: list[Branch] = []
    for r in ring:
        if r in (entry_node, exit_node):  # approach in / exit taken
            continue
        for _, v, data in graph.out_edges(r, data=True):
            if v in ringset:  # the circulating edge, not a spur
                continue
            b = data.get("bearing")
            if b is None:
                continue
            rel = relative_angle(arrival_bearing, float(b))
            branches.append(
                Branch(direction_word(rel), round(rel, 1), _clean_str(_first(data.get("name"))))
            )
    branches.sort(key=lambda br: br.relative_angle)
    return tuple(branches)


def _roundabout_decision(graph, ring, route, node_seq, sample_m) -> DecisionPoint | None:
    """A ROUNDABOUT decision if the route traverses ``ring``, else None."""
    idx_of = {nid: i for i, nid in enumerate(ring)}
    on = [k for k, nd in enumerate(node_seq) if nd in idx_of]
    if not on:
        return None
    first_k, last_k = on[0], on[-1]
    entry_node, exit_node = node_seq[first_k], node_seq[last_k]
    num = roundabout_exit_number(
        _ring_exit_flags(graph, ring), idx_of[entry_node], idx_of[exit_node]
    )
    if num <= 0:
        return None
    exit_mile = meters_to_miles(sample_m[min(last_k + 1, len(sample_m) - 1)])
    lat, lon = coord_at_meters(route, miles_to_meters(exit_mile))
    arrival_bearing, _ = _route_bearings_at(route, meters_to_miles(sample_m[first_k]))
    onto = _road_after(route, exit_mile)
    instr = f"Take the {_ordinal(num)} exit"
    if onto:
        instr += f" onto {onto}"
    return DecisionPoint(
        mile=round(exit_mile, 1),
        instruction=instr,
        significance=SCORE_STATE_HWY_JUNCTION,
        lat=lat,
        lon=lon,
        kind=DecisionKind.ROUNDABOUT,
        roundabout_exit=num,
        branches=_roundabout_spur_branches(graph, ring, entry_node, exit_node, arrival_bearing),
    )


def _merge_roundabout(decisions: list[DecisionPoint], rd: DecisionPoint, tol: float = 0.25):
    """Drop any plain decision within ``tol`` miles of the roundabout, add ``rd``."""
    kept = [d for d in decisions if abs(d.mile - rd.mile) > tol]
    kept.append(rd)
    return sorted(kept, key=lambda d: d.mile)


def _apply_junction_topology(route, graphs, node_seq, sample_m, ox) -> None:
    if not graphs:
        return
    # 1. Roundabouts: replace the plain exit decision with a ROUNDABOUT one.
    decisions = list(route.decision_points)
    for _, _, graph in graphs:
        for ring in _roundabout_rings(graph):
            rd = _roundabout_decision(graph, ring, route, node_seq, sample_m)
            if rd is not None:
                decisions = _merge_roundabout(decisions, rd)
    # 2. Roads-not-taken on every remaining plain decision.
    out: list[DecisionPoint] = []
    for d in decisions:
        if d.kind == DecisionKind.ROUNDABOUT or d.branches:
            out.append(d)
            continue
        graph = _graph_for_mile(graphs, route, d.mile)
        branches = _branches_for(graph, route, d, ox) if graph is not None else ()
        out.append(replace(d, branches=branches) if branches else d)
    route.decision_points = out


def _clean_str(value) -> str | None:
    """A non-empty string, or None for NaN/None/blank (OSM cells are often NaN)."""
    if value is None:
        return None
    if isinstance(value, float):  # NaN
        return None
    text = str(value).strip()
    return text or None


def _add_fuel(route, ox, chunks, fuel_buffer_m: float) -> None:
    """Merge OSM amenity=fuel stations near the route into route.fuel_stops.

    Queried per chunk so a long route's fuel search stays tractable; duplicates
    (incl. those near chunk boundaries) are dropped by mileage.
    """
    import shapely.geometry as sg
    from osmnx._errors import InsufficientResponseError

    def nearest_mile(lat, lon):
        i = min(
            range(len(route.points)),
            key=lambda k: haversine(route.points[k].lat, route.points[k].lon, lat, lon),
        )
        return round(meters_to_miles(route.distances_m[i]), 1)

    osm_stops: list[FuelStop] = []
    for i0, i1 in chunks:
        sub = [(route.points[k].lon, route.points[k].lat) for k in range(i0, i1 + 1)]
        if len(sub) < 2:
            continue
        try:
            feats = ox.features_from_polygon(
                sg.LineString(sub).buffer(fuel_buffer_m * _DEG_PER_M), tags={"amenity": "fuel"}
            )
        except InsufficientResponseError:
            continue
        if feats.empty:
            continue
        for _, row in feats.iterrows():
            geom = row.geometry
            pt = geom.centroid if geom.geom_type != "Point" else geom
            name = _clean_str(row.get("name")) or _clean_str(row.get("brand")) or "Fuel"
            osm_stops.append(FuelStop(nearest_mile(pt.y, pt.x), str(name), pt.y, pt.x))

    osm_stops.sort(key=lambda s: s.mile)
    merged = list(route.fuel_stops)
    for stop in osm_stops:
        if not any(abs(stop.mile - e.mile) < 0.3 for e in merged):
            merged.append(stop)
    merged.sort(key=lambda s: s.mile)
    route.fuel_stops = merged
