"""OpenStreetMap enrichment.

This is the "OSM Enrichment" pipeline stage from docs/product.md. It derives navigation
structure from OSM topology rather than raw geometry, which is what docs/product.md's
significance scoring is actually about:

* decision points come from *durable* road-name changes (docs/product.md Rule Set 1):
  the route is sampled for road names, names that don't persist for
  :data:`~gpxsheet.analysis.MIN_ROAD_RUN_MILES` are discarded as nearest-edge
  flapping at junctions, and each surviving change becomes "Left/Right/Continue
  onto <road>" with the turn direction taken from the track geometry,
* segments become those durable named roads (the road ribbon),
* fuel stations (amenity=fuel) near the route are merged with GPX-waypoint fuel.

This avoids the core failure of geometry-only detection, which cannot tell a
curving road from a junction and so floods twisty sport-touring roads with false
decisions. Road/fuel queries hit the live Overpass API (via osmnx).
"""

from __future__ import annotations

import re
from dataclasses import replace

from .analysis import (
    CONTINUE_MAX_ANGLE_DEG,
    MIN_ROAD_RUN_MILES,
    MIN_SEGMENT_MILES,
    _significance_for_turn,
    _turn_word,
    coord_at_meters,
    merge_close_decisions,
    turn_angle_at_mile,
)
from .geo import bearing, haversine, meters_to_miles, miles_to_meters
from .junctions import branches_not_taken, direction_word, relative_angle, roundabout_exit_number
from .models import (
    Branch,
    DecisionKind,
    DecisionPoint,
    FuelStop,
    Route,
    RouteSpan,
    Segment,
    SpanKind,
)
from .profiles import (
    SCORE_CONTINUE_PENALTY,
    SCORE_ROAD_NAME_CHANGE,
    SCORE_STATE_HWY_JUNCTION,
)

_DEG_PER_M = 1.0 / 111_000.0  # crude latitude-degrees per meter, fine for buffering

# Names that read as a numbered/limited-access highway (higher significance).
_HIGHWAY_RE = re.compile(
    r"\b(?:freeway|expressway|highway|turnpike|(?:I|US|CA|SR|US-?\d|state route))\b|"
    r"\b[A-Z]{1,2}-\d+\b",
    re.IGNORECASE,
)


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

# Road network filters tried, in order, when building a chunk graph. "drive" is
# the clean default, but remote sport-touring roads (e.g. Mt Hamilton Rd, forest
# highways) sit on segments the strict "drive" filter drops, leaving the chunk
# with no graph nodes; "drive_service" reaches them without the path/track noise
# of "all". A wider buffer is tried last for genuinely thin clip polygons.
_NETWORK_FALLBACKS = ("drive", "drive_service")
_THIN_POLYGON_BUFFER_FACTOR = 4.0


def _chunk_graph(ox, sg, sub: list[tuple[float, float]], road_buffer_m: float):
    """Build the OSM graph for one chunk, with network/buffer fallbacks.

    Returns an osmnx graph (with edge bearings added) or ``None`` if no drivable
    network could be found. A missing chunk is then skipped so the rest of the
    route still enriches, rather than one bad chunk aborting all enrichment.
    """
    from osmnx._errors import InsufficientResponseError

    line = sg.LineString(sub)
    attempts = [(net, road_buffer_m) for net in _NETWORK_FALLBACKS]
    attempts.append(("drive_service", road_buffer_m * _THIN_POLYGON_BUFFER_FACTOR))
    for network_type, buffer_m in attempts:
        try:
            graph = ox.graph_from_polygon(
                line.buffer(buffer_m * _DEG_PER_M),
                network_type=network_type,
                retain_all=True,
                truncate_by_edge=True,
            )
        except (InsufficientResponseError, ValueError):
            continue  # no/empty network for this filter+buffer; try the next
        ox.bearing.add_edge_bearings(graph)  # 'bearing' per edge, for branch geometry
        return graph
    return None


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
    import osmnx as ox
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
        graph = _chunk_graph(ox, sg, sub, road_buffer_m)
        if graph is None:
            continue  # no drivable network here; other chunks still enrich
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
    route.spans = _unpaved_spans(sample_m, unpaved, spacing_m)

    if include_fuel:
        _add_fuel(route, ox, chunks, fuel_buffer_m)
    if include_hazards:
        ferry_spans = _detect_ferries(route, ox, sg, road_buffer_m)
        route.ferry_crossings = sorted({s.name for s in ferry_spans if s.name})
        route.spans = sorted([*route.spans, *ferry_spans], key=lambda s: s.start_mile)
    return route


# Runs shorter than this are dropped from the unpaved overlay as sampling noise.
MIN_UNPAVED_SPAN_MILES = 0.1


def _unpaved_spans(sample_m, unpaved, spacing_m) -> list[RouteSpan]:
    """Contiguous unpaved sample runs as :class:`RouteSpan` overlays.

    Each run is credited half a sample spacing at both ends so the drawn span
    covers the surface change rather than stopping at the sampled vertices.
    """
    spans: list[RouteSpan] = []
    half = 0.5 * spacing_m
    i, n = 0, len(unpaved)
    while i < n:
        if not unpaved[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and unpaved[j + 1]:
            j += 1
        start = meters_to_miles(max(0.0, sample_m[i] - half))
        end = meters_to_miles(sample_m[j] + half)
        if end - start >= MIN_UNPAVED_SPAN_MILES:
            spans.append(RouteSpan(round(start, 1), round(end, 1), SpanKind.UNPAVED))
        i = j + 1
    return spans


def _detect_ferries(route: Route, ox, sg, buffer_m: float) -> list[RouteSpan]:
    """Ferry crossings (route=ferry ways the route rides along) as spans.

    Each ferry the route follows becomes a :class:`RouteSpan` covering the route
    miles that run alongside the ferry way, so the renderer can draw the crossing
    as a styled ribbon stretch and label its boarding/landing ends.
    """
    from osmnx._errors import InsufficientResponseError

    line = sg.LineString([(p.lon, p.lat) for p in route.points])
    buf = buffer_m * _DEG_PER_M
    corridor = line.buffer(buf)
    try:
        feats = ox.features_from_polygon(corridor, tags={"route": "ferry"})
    except InsufficientResponseError:
        return []
    if feats.empty:
        return []
    spans: list[RouteSpan] = []
    for _, row in feats.iterrows():
        geom = row.geometry
        ferry_len = getattr(geom, "length", 0.0)
        if not ferry_len:
            continue
        # Count only ferries the route rides along, not ones whose terminal we pass.
        if geom.intersection(corridor).length < FERRY_FOLLOW_FRACTION * ferry_len:
            continue
        # Route miles that run alongside this ferry way -> the crossing span.
        miles = [
            meters_to_miles(route.distances_m[i])
            for i, p in enumerate(route.points)
            if geom.distance(sg.Point(p.lon, p.lat)) <= buf
        ]
        if not miles:
            continue
        name = _clean_str(row.get("name")) or "ferry"
        spans.append(RouteSpan(round(min(miles), 1), round(max(miles), 1), SpanKind.FERRY, name))
    spans.sort(key=lambda s: s.start_mile)
    return spans


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

    A run's measured extent is the span between its first and last sample, which
    undercounts the true on-road length by up to one sample spacing depending on
    where the samples fall relative to the junctions. That phase jitter makes a
    run sitting right on ``min_run_m`` flip in and out across runs of the live
    query. We pad each run's extent by one sample spacing (half at each end) so
    the keep/drop decision has a deterministic deadband and a borderline run is
    classified consistently.
    """
    spacing = (sample_m[1] - sample_m[0]) if len(sample_m) >= 2 else 0.0

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
        if (run[2] - run[0] + spacing) >= min_run_m or is_edge:
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


# Minor-road name suffixes (cul-de-sac / subdivision streets). A straight-through
# name change onto one of these is residential-grid noise, not a navigation
# moment. Arterials (Road / Avenue / Boulevard / Highway) are deliberately
# excluded so a straight "Continue onto Sand Hill Road" keeps full weight.
# Restricted to unambiguous cul-de-sac types: live validation flagged that
# "Way" / "Loop" / "Row" are also used for real arterials, so penalizing them
# risked dropping genuine roads.
_MINOR_ROAD_SUFFIXES = frozenset(
    {
        "court", "ct", "lane", "ln", "place", "pl", "circle", "cir",
        "terrace", "ter", "close", "cove", "alley", "cul-de-sac",
    }
)


def _is_minor_residential(name: str) -> bool:
    last = name.strip().rsplit(" ", 1)[-1].rstrip(".").lower() if name.strip() else ""
    return last in _MINOR_ROAD_SUFFIXES


def _road_change_significance(name: str, angle: float) -> int:
    sig = SCORE_ROAD_NAME_CHANGE
    if _is_highway(name):
        sig = max(sig, SCORE_STATE_HWY_JUNCTION)
    if abs(angle) >= 60.0:
        sig += 10
    # A straight-through name change onto a minor residential road is grid noise;
    # down-weight it (below the sport-touring threshold) so profiles filter it.
    elif abs(angle) < CONTINUE_MAX_ANGLE_DEG and _is_minor_residential(name):
        sig = max(0, sig - SCORE_CONTINUE_PENALTY)
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

# Promoting a nameless fork into a decision: the route must clearly turn off an
# obvious through-road at a real junction. Gated tightly (a meaningful turn AND a
# straight-ahead road the route does not take) so ordinary side streets the route
# rides straight past are not flagged.
PROMOTE_FORK_MIN_ANGLE_DEG = 30.0
FORK_DEDUP_MILES = 0.2


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


# Highway classes that are not a navigation choice when the route stays on the
# main road: a driveway / track / path branching off is not a fork the rider can
# mistakenly take. Used to gate nameless-fork promotion so a twisty road with
# service-road stubs at every switchback isn't flooded with false "forks".
_MINOR_HIGHWAYS = frozenset(
    {
        "service", "track", "path", "footway", "cycleway", "bridleway", "steps",
        "pedestrian", "construction", "raceway", "busway", "corridor",
    }
)


def _named_road_branches(graph, node) -> list[tuple[str, float]]:
    """(name, bearing) for each *named, drivable* edge leaving ``node``.

    Minor service/track/path edges and unnamed stubs are excluded, so only roads
    a rider could genuinely take are considered when judging whether a junction
    is a real fork.
    """
    out: list[tuple[str, float]] = []
    for _, _v, data in graph.out_edges(node, data=True):
        b = data.get("bearing")
        if b is None:
            continue
        name = _clean_str(_first(data.get("name")))
        highway = _first(data.get("highway"))
        if name and highway not in _MINOR_HIGHWAYS:
            out.append((name, float(b)))
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
    """Per ring node, whether it has an *exit* spur (a road leaving the circle).

    Only outgoing spurs count: an edge leaving the ring is an exit you can take,
    while a road that only feeds *into* the roundabout (incoming-only spur) is an
    entrance, not an exit. Counting entrances would inflate the "take the Nth
    exit" number (observed live: a one-way feeder made a 2nd exit read as 3rd).
    """
    ringset = set(ring)
    return [any(v not in ringset for v in graph.successors(nid)) for nid in ring]


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
    # 3. Nameless forks: a high-degree node where the route leaves a through-road
    #    with no road-name change to flag it.
    _promote_fork_decisions(route, graphs, node_seq, sample_m)


def _promote_fork_decisions(route, graphs, node_seq, sample_m) -> None:
    """Add decisions at nameless forks the route turns off (no name change).

    A high-degree OSM node carries no road-name change when the road keeps its
    name through the junction, so :func:`_decisions_from_runs` never flags it --
    yet if the route turns off an obvious straight-ahead road there, the rider
    needs to be told. Promote such a node to a decision when the route turns by
    at least :data:`PROMOTE_FORK_MIN_ANGLE_DEG` and a *named, non-minor* road is
    left going straight ahead; the branches render as ghosted stubs. Deliberately
    conservative -- service-road / driveway stubs (common at switchbacks) and
    side streets ridden straight through are not flagged.
    """
    existing = [d.mile for d in route.decision_points]
    added: list[DecisionPoint] = []
    seen: set = set()
    for k, node in enumerate(node_seq):
        if node is None or node in seen:
            continue
        mile = meters_to_miles(sample_m[k])
        if any(abs(mile - em) <= FORK_DEDUP_MILES for em in existing):
            continue
        if any(abs(mile - a.mile) <= FORK_DEDUP_MILES for a in added):
            continue
        graph = _graph_for_mile(graphs, route, mile)
        if graph is None or node not in graph or _junction_degree(graph, node) < 3:
            continue
        angle = turn_angle_at_mile(route, mile)
        if abs(angle) < PROMOTE_FORK_MIN_ANGLE_DEG:
            continue  # rode basically straight through -> a side street, not a fork
        arrival, taken = _route_bearings_at(route, mile)
        # Drop the road the rider stays on (same name): at a switchback the far
        # limb of the same road runs "straight ahead", which is a bend, not a fork.
        taken_name = _road_after(route, mile)
        branches = branches_not_taken(
            arrival, taken, _named_road_branches(graph, node), taken_name=taken_name
        )
        if not any(b.direction == "straight" for b in branches):
            continue  # no *differently named* through-road was left -> not a fork
        lat, lon = coord_at_meters(route, miles_to_meters(mile))
        added.append(
            DecisionPoint(
                mile=round(mile, 1),
                instruction=f"{_turn_word(angle)} at the fork",
                significance=_significance_for_turn(angle),
                lat=lat,
                lon=lon,
                kind=DecisionKind.CRITICAL_TURN,
                turn_angle=round(angle, 1),
                branches=branches,
            )
        )
        seen.add(node)
    if added:
        route.decision_points = sorted([*route.decision_points, *added], key=lambda d: d.mile)


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
