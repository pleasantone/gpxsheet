"""Junction-topology wiring tested against hand-built networkx graphs (no Overpass).

Exercises the real graph-reading code in gpxsheet.enrich (node degree, edge
bearings, junction=roundabout) without hitting the live OSM API.
"""

from __future__ import annotations


def _straight_north_route(miles: float = 1.4):
    """A route running due north through (0, 0) at its midpoint."""
    from gpxsheet.geo import cumulative_distances
    from gpxsheet.models import GeoPoint, Route, Segment

    pts = [GeoPoint(-0.01, 0.0), GeoPoint(0.0, 0.0), GeoPoint(0.01, 0.0)]
    route = Route(
        name="t",
        points=pts,
        distances_m=cumulative_distances([(p.lat, p.lon) for p in pts]),
        segments=[Segment("Main St", 0.0, miles)],
    )
    return route


class _FakeOx:
    """Force _nearest_graph_node onto its haversine fallback (no scipy/CRS)."""

    class distance:  # noqa: N801
        @staticmethod
        def nearest_nodes(*a, **k):
            raise RuntimeError("use fallback")


def _four_way_graph():
    import networkx as nx

    g = nx.MultiDiGraph()
    g.add_node("J", x=0.0, y=0.0)
    coords = {"N": (0.0, 0.01), "E": (0.01, 0.0), "S": (0.0, -0.01), "W": (-0.01, 0.0)}
    for nid, (x, y) in coords.items():
        g.add_node(nid, x=x, y=y)
    # name + outgoing compass bearing per directed edge
    edges = [
        ("J", "N", "Main St", 0.0), ("N", "J", "Main St", 180.0),
        ("J", "E", "East Ave", 90.0), ("E", "J", "East Ave", 270.0),
        ("J", "S", "Main St", 180.0), ("S", "J", "Main St", 0.0),
        ("J", "W", "West Ave", 270.0), ("W", "J", "West Ave", 90.0),
    ]
    for u, v, name, brg in edges:
        g.add_edge(u, v, name=name, bearing=brg)
    return g


def test_branches_at_four_way():
    from gpxsheet.enrich import _branches_for
    from gpxsheet.models import DecisionPoint

    g = _four_way_graph()
    route = _straight_north_route()
    # Decision at the junction; route goes straight through (S -> N).
    mid = route.length_miles / 2
    d = DecisionPoint(mile=mid, instruction="x", significance=0, lat=0.0, lon=0.0)
    branches = _branches_for(g, route, d, _FakeOx())
    assert [(b.direction, b.name) for b in branches] == [
        ("left", "West Ave"),
        ("right", "East Ave"),
    ]


def test_no_branches_when_degree_two():
    import networkx as nx

    from gpxsheet.enrich import _branches_for
    from gpxsheet.models import DecisionPoint

    g = nx.MultiDiGraph()
    for nid, (x, y) in {"J": (0, 0), "N": (0, 0.01), "S": (0, -0.01)}.items():
        g.add_node(nid, x=x, y=y)
    g.add_edge("J", "N", name="Main St", bearing=0.0)
    g.add_edge("J", "S", name="Main St", bearing=180.0)
    route = _straight_north_route()
    d = DecisionPoint(mile=route.length_miles / 2, instruction="x", significance=0, lat=0, lon=0)
    assert _branches_for(g, route, d, _FakeOx()) == ()  # not a fork


def _roundabout_graph():
    import networkx as nx

    g = nx.MultiDiGraph()
    ring = {"R0": (0, 0.001), "R1": (0.001, 0), "R2": (0, -0.001), "R3": (-0.001, 0)}
    for nid, (x, y) in ring.items():
        g.add_node(nid, x=x, y=y)
    for i in range(4):
        g.add_edge(f"R{i}", f"R{(i + 1) % 4}", junction="roundabout", bearing=0.0, name=None)
    # approach into R0, exit spurs off R1/R2/R3 (ring_node, coord, spur bearing)
    g.add_node("A", x=0, y=0.01)
    g.add_edge("A", "R0", name="Approach", bearing=180.0)
    spurs = {
        "X1": ("R1", (0.01, 0), 90.0),
        "X2": ("R2", (0, -0.01), 180.0),
        "X3": ("R3", (-0.01, 0), 270.0),
    }
    for sid, (ring_node, (x, y), brg) in spurs.items():
        g.add_node(sid, x=x, y=y)
        g.add_edge(ring_node, sid, name=f"{sid} Rd", bearing=brg)
    return g


def test_roundabout_rings_and_exit_decision():
    from gpxsheet.enrich import _roundabout_decision, _roundabout_rings
    from gpxsheet.models import GeoPoint, Route, Segment

    g = _roundabout_graph()
    rings = _roundabout_rings(g)
    assert len(rings) == 1 and len(rings[0]) == 4

    # Route enters at R0 and leaves at R2 -> the 2nd exit.
    pts = [GeoPoint(0.001 * i, 0.0) for i in range(6)]
    from gpxsheet.geo import cumulative_distances

    route = Route(
        name="t", points=pts,
        distances_m=cumulative_distances([(p.lat, p.lon) for p in pts]),
        segments=[Segment("X2 Rd", 0.0, 1.0)],
    )
    node_seq = ["A", "R0", "R1", "R2", "X2", "X2"]
    sample_m = [route.distances_m[i] for i in range(6)]
    rd = _roundabout_decision(g, rings[0], route, node_seq, sample_m)
    assert rd is not None
    assert rd.kind == "roundabout"
    assert rd.roundabout_exit == 2
    # No "At the roundabout" prefix -- the ring glyph already conveys that.
    assert rd.instruction == "Take the 2nd exit onto X2 Rd"
    # The exits NOT taken (X1, X3) become branches; the taken exit (X2) does not.
    assert {b.name for b in rd.branches} == {"X1 Rd", "X3 Rd"}
    by_name = {b.name: b for b in rd.branches}
    assert by_name["X1 Rd"].direction == "right"  # spur bearing 90 vs entry heading N
    assert by_name["X3 Rd"].direction == "left"  # spur bearing 270


def _fork_route():
    """Route heading north, then bearing right (NE) at (0, 0)."""
    from gpxsheet.geo import cumulative_distances
    from gpxsheet.models import GeoPoint, Route, Segment

    pts = [
        GeoPoint(-0.02, 0.0), GeoPoint(-0.01, 0.0), GeoPoint(0.0, 0.0),
        GeoPoint(0.007, 0.007), GeoPoint(0.014, 0.014),
    ]
    route = Route(
        name="fork", points=pts,
        distances_m=cumulative_distances([(p.lat, p.lon) for p in pts]),
        segments=[Segment("County Road", 0.0, 5.0)],  # one name through the fork
    )
    return route


def _fork_graph():
    """Junction J (deg 3): arrive from S, through-road N (not taken), bear NE."""
    import networkx as nx

    g = nx.MultiDiGraph()
    for nid, (x, y) in {
        "J": (0.0, 0.0), "S": (0.0, -0.01), "N": (0.0, 0.01), "E": (0.007, 0.007)
    }.items():
        g.add_node(nid, x=x, y=y)
    g.add_edge("J", "S", name="County Road", bearing=180.0)
    g.add_edge("J", "N", name="County Road", bearing=0.0)  # straight ahead, not taken
    g.add_edge("J", "E", name="County Road", bearing=45.0)  # the route bears right
    return g


def test_promote_nameless_fork_emits_decision():
    from gpxsheet.enrich import _promote_fork_decisions

    route = _fork_route()
    g = _fork_graph()
    j_idx = 2  # the junction sample
    node_seq = ["S", "S", "J", "E", "E"]
    sample_m = list(route.distances_m)
    graphs = [(0, len(route.points) - 1, g)]
    _promote_fork_decisions(route, graphs, node_seq, sample_m)

    assert len(route.decision_points) == 1
    d = route.decision_points[0]
    assert d.instruction == "Right at the fork"
    assert d.turn_angle > 0  # bore right
    # the straight-ahead road the route did not take becomes a ghosted branch
    assert any(b.direction == "straight" for b in d.branches)
    assert abs(d.mile - route.length_miles * j_idx / 4) < 1.0


def test_no_fork_decision_when_route_runs_straight_through():
    from gpxsheet.enrich import _promote_fork_decisions
    from gpxsheet.geo import cumulative_distances
    from gpxsheet.models import GeoPoint, Route, Segment

    # Same junction, but the route continues straight north past the side road.
    pts = [GeoPoint(0.01 * i, 0.0) for i in range(-2, 3)]
    route = Route(
        name="thru", points=pts,
        distances_m=cumulative_distances([(p.lat, p.lon) for p in pts]),
        segments=[Segment("County Road", 0.0, 5.0)],
    )
    g = _fork_graph()
    node_seq = ["S", "S", "J", "N", "N"]
    _promote_fork_decisions(route, g and [(0, 4, g)], node_seq, list(route.distances_m))
    assert route.decision_points == []  # straight through -> not a fork


def test_roundabout_not_traversed_returns_none():
    from gpxsheet.enrich import _roundabout_decision, _roundabout_rings
    from gpxsheet.models import GeoPoint, Route

    g = _roundabout_graph()
    ring = _roundabout_rings(g)[0]
    route = Route(name="t", points=[GeoPoint(0, 0), GeoPoint(0, 1)], distances_m=[0.0, 1000.0])
    node_seq = ["A", "X1", "X2"]  # never on the ring
    assert _roundabout_decision(g, ring, route, node_seq, [0.0, 500.0, 1000.0]) is None
