"""Tests for the schematic layout engine (pure, no matplotlib)."""

import pytest

from gpxsheet.layout import build_strip_layout
from gpxsheet.models import (
    POI,
    Branch,
    DecisionKind,
    DecisionPoint,
    FuelStop,
    GeoPoint,
    POIKind,
    ReassuranceMarker,
    Route,
    Segment,
)


def _route_with_segments() -> Route:
    return Route(
        name="Test",
        points=[GeoPoint(38.0, -123.0), GeoPoint(38.2, -123.0)],
        distances_m=[0.0, 30 * 1609.344],
        decision_points=[
            DecisionPoint(10.0, "Left onto B Rd", 60, 0, 0, turn_angle=-70),
            DecisionPoint(20.0, "Right onto C Rd", 60, 0, 0, turn_angle=80),
        ],
        fuel_stops=[FuelStop(15.0, "Shell", 0, 0)],
        reassurance_markers=[ReassuranceMarker(5.0, "Townville", 0, 0)],
        segments=[
            Segment("A Rd", 0.0, 10.0),
            Segment("B Rd", 10.0, 20.0),
            Segment("C Rd", 20.0, 30.0),
        ],
    )


def test_layout_path_has_node_per_boundary():
    layout = build_strip_layout(_route_with_segments())
    # 3 segments -> 4 boundary nodes.
    assert len(layout.path) == 4
    assert layout.ribbon == ["A Rd", "B Rd", "C Rd"]


def test_layout_is_normalized_to_origin():
    layout = build_strip_layout(_route_with_segments())
    xs = [p[0] for p in layout.path]
    ys = [p[1] for p in layout.path]
    assert min(xs) == 0.0 and min(ys) == 0.0
    assert layout.width > 0
    assert layout.height >= 0


def test_layout_places_all_markers():
    layout = build_strip_layout(_route_with_segments())
    kinds = [m.kind for m in layout.markers]
    assert kinds.count("start") == 1
    assert kinds.count("end") == 1
    assert kinds.count("decision") == 2
    assert kinds.count("fuel") == 1
    assert kinds.count("reassurance") == 1


def test_markers_lie_on_or_near_the_path_bounds():
    layout = build_strip_layout(_route_with_segments())
    for m in layout.markers:
        assert -0.01 <= m.x <= layout.width + 0.01
        assert -0.01 <= m.y <= layout.height + 0.01


def test_turn_direction_affects_geometry():
    # A route that only ever turns left should bend differently than one that
    # only turns right -- i.e. the stylized turn sign is actually applied.
    base = _route_with_segments()
    left = Route(
        name="L", points=base.points, distances_m=base.distances_m,
        decision_points=[DecisionPoint(10.0, "Left", 60, 0, 0, turn_angle=-70),
                         DecisionPoint(20.0, "Left", 60, 0, 0, turn_angle=-70)],
        segments=base.segments,
    )
    right = Route(
        name="R", points=base.points, distances_m=base.distances_m,
        decision_points=[DecisionPoint(10.0, "Right", 60, 0, 0, turn_angle=70),
                         DecisionPoint(20.0, "Right", 60, 0, 0, turn_angle=70)],
        segments=base.segments,
    )
    assert build_strip_layout(left).path[-1] != build_strip_layout(right).path[-1]


def test_turn_style_default_is_stylized_and_differs_from_faithful():
    # A sharp 130-degree turn: faithful bends much more than the quantized
    # stylized bend, so the two layouts must differ.
    r = Route(
        name="x",
        points=[GeoPoint(0, 0), GeoPoint(0, 1)],
        distances_m=[0.0, 20 * 1609.344],
        decision_points=[DecisionPoint(10.0, "Right", 80, 0, 0, turn_angle=130)],
        segments=[Segment("A", 0, 10), Segment("B", 10, 20)],
    )
    stylized = build_strip_layout(r)  # default
    faithful = build_strip_layout(r, turn_style="faithful")
    assert build_strip_layout(r, turn_style="stylized").path == stylized.path
    assert stylized.path[-1] != faithful.path[-1]


def test_turn_style_invalid_raises():
    r = Route(name="x", points=[GeoPoint(0, 0), GeoPoint(0, 1)], distances_m=[0.0, 1609.344])
    with pytest.raises(ValueError):
        build_strip_layout(r, turn_style="bogus")


def test_layout_handles_route_without_segments():
    route = Route(
        name="Bare",
        points=[GeoPoint(0, 0), GeoPoint(0, 1)],
        distances_m=[0.0, 5 * 1609.344],
    )
    layout = build_strip_layout(route)
    assert len(layout.path) == 2  # single default segment -> 2 nodes
    assert layout.ribbon == ["Bare"]


def test_pois_are_placed_and_labeled():
    route = Route(
        name="P",
        points=[GeoPoint(0, 0), GeoPoint(0, 1)],
        distances_m=[0.0, 20 * 1609.344],
        segments=[Segment("A Rd", 0.0, 20.0)],
        pois=[
            POI(5.0, "Vista Point", 0, 0, POIKind.WAYPOINT),
            POI(8.0, "Joe's Diner", 0, 0, POIKind.FOOD),
        ],
    )
    layout = build_strip_layout(route)
    by_kind = {m.kind: m for m in layout.markers}
    assert by_kind["waypoint"].label == "Vista Point"
    assert by_kind["food"].label == "Joe's Diner"


def test_spans_become_overlays_and_endpoint_markers():
    from gpxsheet.models import RouteSpan, SpanKind

    route = Route(
        name="S",
        points=[GeoPoint(0, 0), GeoPoint(0, 1)],
        distances_m=[0.0, 30 * 1609.344],
        segments=[Segment("A Rd", 0.0, 30.0)],
        spans=[
            RouteSpan(5.0, 9.0, SpanKind.UNPAVED),
            RouteSpan(18.0, 22.0, SpanKind.FERRY, "Bay Ferry"),
        ],
    )
    layout = build_strip_layout(route)
    assert {o.kind for o in layout.overlays} == {"unpaved", "ferry"}
    assert all(len(o.points) >= 2 for o in layout.overlays)
    kinds = [m.kind for m in layout.markers]
    assert kinds.count("unpaved") == 2  # start + end labeled
    assert kinds.count("ferry") == 2
    ferry_start = next(m for m in layout.markers if m.kind == "ferry")
    assert "Bay Ferry" in ferry_start.label


def test_same_direction_turns_do_not_spiral():
    # A long run of same-direction turns must not curl the ribbon back on itself;
    # heading relaxation keeps it flowing left-to-right (x strictly increasing).
    n = 9
    pts = [GeoPoint(0, 0), GeoPoint(0, 1)]
    segs = [Segment(f"R{i}", float(i * 4), float((i + 1) * 4)) for i in range(n)]
    decisions = [
        DecisionPoint(float(i * 4), "Right", 60, 0, 0, turn_angle=70)
        for i in range(1, n)
    ]
    route = Route(
        name="spiral", points=pts, distances_m=[0.0, n * 4 * 1609.344],
        segments=segs, decision_points=decisions,
    )
    xs = [p[0] for p in build_strip_layout(route).path]
    assert all(b > a for a, b in zip(xs, xs[1:], strict=False))


def test_fuel_at_mile_zero_is_nudged_off_start():
    # A fuel stop at mile 0 must not draw on top of the START marker.
    route = Route(
        name="Z",
        points=[GeoPoint(0, 0), GeoPoint(0, 1)],
        distances_m=[0.0, 20 * 1609.344],
        segments=[Segment("A Rd", 0.0, 20.0)],
        fuel_stops=[FuelStop(0.0, "Shell", 0, 0)],
    )
    layout = build_strip_layout(route)
    start = next(m for m in layout.markers if m.kind == "start")
    fuel = next(m for m in layout.markers if m.kind == "fuel")
    assert (fuel.x, fuel.y) != (start.x, start.y)
    assert abs(fuel.x - start.x) >= 1.0  # pushed clearly along the ribbon
    assert fuel.mile == 0.0  # label still reads the true mileage


def test_branches_and_roundabout_carry_into_markers():
    route = Route(
        name="Topo",
        points=[GeoPoint(0, 0), GeoPoint(0, 1)],
        distances_m=[0.0, 20 * 1609.344],
        segments=[Segment("A Rd", 0, 8), Segment("B Rd", 8, 14), Segment("C Rd", 14, 20)],
        decision_points=[
            DecisionPoint(
                8.0, "Right onto B Rd", 60, 0, 0, turn_angle=80,
                branches=(Branch("left", -85, "Side St"),),
            ),
            DecisionPoint(
                14.0, "At the roundabout, take the 2nd exit onto C Rd", 60, 0, 0,
                kind=DecisionKind.ROUNDABOUT, roundabout_exit=2,
            ),
        ],
    )
    layout = build_strip_layout(route)
    decision = next(m for m in layout.markers if m.kind == "decision")
    assert decision.branches and decision.branches[0].name == "Side St"
    rb = next(m for m in layout.markers if m.kind == "roundabout")
    assert rb.roundabout_exit == 2
