"""Tests for the route analysis engine."""

import gpxsheet
from gpxsheet.analysis import analyze_route, detect_decision_points
from gpxsheet.gpx import load_route
from gpxsheet.models import DecisionKind
from gpxsheet.profiles import Profile
from gpxsheet.simplify import rdp


def test_load_route_parses_geometry(l_route_file):
    route = load_route(l_route_file)
    assert route.name == "Test Route"
    assert len(route.points) > 50
    assert route.length_miles > 4.0
    assert len(route.waypoints) == 1


def test_detects_single_left_turn(l_route_file):
    route = load_route(l_route_file)
    decisions = detect_decision_points(route.points)
    assert len(decisions) == 1
    turn = decisions[0]
    assert turn.kind == DecisionKind.CRITICAL_TURN
    assert turn.instruction == "Left"
    assert turn.turn_angle is not None and turn.turn_angle < -60
    # The corner is roughly halfway through the route.
    assert 1.5 < turn.mile < 3.5


def test_detects_consecutive_same_direction_turns():
    # Regression: two right turns separated by a long straight must NOT be merged
    # into one run and rejected. Path: north -> (right) east -> (right) south.
    from gpxsheet.models import GeoPoint

    pts: list[GeoPoint] = []
    lat, lon = 38.0, -123.0
    for _ in range(40):  # north
        pts.append(GeoPoint(lat, lon))
        lat += 0.001
    for _ in range(60):  # east (first right turn)
        pts.append(GeoPoint(lat, lon))
        lon += 0.001
    for _ in range(40):  # south (second right turn)
        pts.append(GeoPoint(lat, lon))
        lat -= 0.001

    decisions = detect_decision_points(pts)
    assert len(decisions) == 2
    assert all(d.instruction == "Right" for d in decisions)
    assert decisions[0].mile < decisions[1].mile


def test_sweeping_curve_is_not_a_decision():
    # A gradual 90-degree bend spread over a long arc should not register as a
    # junction-style turn.
    import math

    from gpxsheet.models import GeoPoint

    pts: list[GeoPoint] = []
    cx, cy = 38.0, -123.0
    radius_deg = 0.05  # ~5.5 km radius -> very gentle
    for k in range(60):
        theta = math.radians(90 * k / 59)  # 0..90 degrees
        pts.append(GeoPoint(cx + radius_deg * math.sin(theta), cy + radius_deg * math.cos(theta)))
    assert detect_decision_points(pts) == []


def test_straight_line_has_no_decisions():
    straight = [(38.0, -123.0 + i * 0.001) for i in range(40)]
    assert detect_decision_points(
        [type("P", (), {"lat": la, "lon": lo, "ele": None})() for la, lo in straight]
    ) == []


def test_rdp_reduces_collinear_points():
    from gpxsheet.models import GeoPoint

    pts = [GeoPoint(38.0, -123.0 + i * 0.001) for i in range(50)]
    simplified = rdp(pts, tolerance_m=5.0)
    # A straight line collapses to its two endpoints.
    assert simplified == [pts[0], pts[-1]]


def test_analyze_end_to_end_sport_touring(l_route_file):
    route = gpxsheet.analyze(str(l_route_file), profile="sport-touring", fuel_range=2.0)
    assert len(route.decision_points) == 1
    # Fuel waypoint near the corner should be detected.
    assert len(route.fuel_stops) == 1
    assert "Shell" in route.fuel_stops[0].name
    assert route.fuel_report is not None
    # Total ~5 mi with a fuel stop near the middle -> longest gap < full length.
    assert route.fuel_report.longest_gap_miles < route.length_miles
    # fuel_range of 2 mi is small -> should warn.
    assert route.fuel_report.exceeds_range is True
    # Segments split at the one decision point -> 2 legs.
    assert len(route.segments) == 2


def test_reassurance_markers_respect_interval(l_route_file):
    # Pass a Profile with a short interval so the 5-mile l_route gets markers.
    prof = Profile(
        name="test", decision_threshold=40, include_fuel=False,
        include_reassurance=True, reassurance_interval_miles=1.0,
    )
    route = load_route(str(l_route_file))
    analyze_route(route, profile=prof)
    assert len(route.reassurance_markers) >= 3
    miles = [m.mile for m in route.reassurance_markers]
    assert miles == sorted(miles)


def test_reassurance_marker_not_dropped_near_end(l_route_file):
    # Regression: a route between 1x and 1.5x the interval must still get its one
    # marker. The l-route is ~5 mi; with a 4 mi interval the single marker at
    # mile 4 (~1 mi from the end) must be kept, not suppressed by an end buffer.
    prof = Profile(
        name="test", decision_threshold=40, include_fuel=False,
        include_reassurance=True, reassurance_interval_miles=4.0,
    )
    route = load_route(str(l_route_file))
    analyze_route(route, profile=prof)
    assert len(route.reassurance_markers) == 1
    assert route.reassurance_markers[0].mile == 4.0


def test_minimalist_profile_suppresses_extras(l_route_file):
    route = gpxsheet.analyze(str(l_route_file), profile="minimalist")
    assert route.fuel_stops == []
    assert route.reassurance_markers == []
    assert route.fuel_report is None


def test_build_segments_no_degenerate_legs():
    # Clustered decision points (3.0 and 3.05 mi apart) must not create a
    # zero-length leg; legs stay sequentially numbered.
    from gpxsheet.analysis import build_segments
    from gpxsheet.models import DecisionPoint, GeoPoint, Route

    route = Route(
        name="x",
        points=[GeoPoint(38.0, -123.0), GeoPoint(38.1, -123.0)],
        distances_m=[0.0, 10 * 1609.344],
        decision_points=[
            DecisionPoint(3.0, "Right", 60, 38.0, -123.0),
            DecisionPoint(3.05, "Left", 60, 38.0, -123.0),
            DecisionPoint(7.0, "Right", 60, 38.0, -123.0),
        ],
    )
    segs = build_segments(route)
    assert all(s.length_miles >= 0.1 for s in segs)
    assert [s.name for s in segs] == [f"Leg {i}" for i in range(1, len(segs) + 1)]
    # Final leg reaches the route end.
    assert segs[-1].end_mile == 10.0


def test_merge_close_decisions_collapses_clusters():
    from gpxsheet.analysis import merge_close_decisions
    from gpxsheet.models import DecisionPoint

    dps = [
        DecisionPoint(5.00, "Right", 45, 0, 0, turn_angle=40),
        DecisionPoint(5.05, "Sharp right", 80, 0, 0, turn_angle=120),  # most significant
        DecisionPoint(5.08, "Right", 60, 0, 0, turn_angle=70),
        DecisionPoint(9.00, "Left", 60, 0, 0, turn_angle=-70),  # separate
    ]
    merged = merge_close_decisions(dps, min_separation_miles=0.2)
    assert len(merged) == 2
    assert merged[0].significance == 80  # representative is the sharpest/most significant
    assert merged[1].mile == 9.0


def test_coord_at_meters():
    from gpxsheet.analysis import coord_at_meters
    from gpxsheet.models import GeoPoint, Route

    pts = [GeoPoint(0.0, float(i)) for i in range(5)]
    route = Route(name="x", points=pts, distances_m=[0.0, 100.0, 200.0, 300.0, 400.0])
    assert coord_at_meters(route, 0.0) == (0.0, 0.0)
    assert coord_at_meters(route, 250.0) == (0.0, 2.5)  # interpolated between vertices
    assert coord_at_meters(route, 10_000.0) == (0.0, 4.0)  # clamped to end


def test_turn_angle_at_mile_detects_left_turn(l_route_file):
    from gpxsheet.analysis import turn_angle_at_mile
    from gpxsheet.gpx import load_route

    route = load_route(l_route_file)
    # The L-route turns left (east -> north) at its midpoint (~2.5 mi).
    angle = turn_angle_at_mile(route, route.length_miles / 2)
    assert angle < -45  # left = negative


def test_looks_sparse_detection():
    from gpxsheet.analysis import looks_sparse
    from gpxsheet.models import GeoPoint, Route

    # 4 points over 60 mi -> sparse (a waypoint-only route).
    sparse = Route(
        name="s",
        points=[GeoPoint(0, 0), GeoPoint(0, 1), GeoPoint(0, 2), GeoPoint(0, 3)],
        distances_m=[0.0, 20 * 1609.344, 40 * 1609.344, 60 * 1609.344],
    )
    assert looks_sparse(sparse)


def test_dense_route_not_sparse(l_route_file):
    from gpxsheet.analysis import looks_sparse
    from gpxsheet.gpx import load_route

    assert not looks_sparse(load_route(l_route_file))


def test_analyze_skips_osm_for_sparse_route():
    import pytest

    from gpxsheet.analysis import analyze_route
    from gpxsheet.models import GeoPoint, Route

    # Straight sparse route; analysis must warn and NOT hit the network
    # (looks_sparse short-circuits before calling enrich).
    sparse = Route(
        name="s",
        points=[GeoPoint(0, 0.0), GeoPoint(0, 0.5), GeoPoint(0, 1.0)],
        distances_m=[0.0, 30 * 1609.344, 60 * 1609.344],
    )
    with pytest.warns(UserWarning, match="sparse"):
        analyze_route(sparse, profile="sport-touring")
    # falls back to geometry-only: a straight line has no decisions
    assert sparse.decision_points == []


def test_analyze_falls_back_when_osm_query_fails(l_route_file, monkeypatch):
    import pytest

    import gpxsheet
    import gpxsheet.enrich as enrich

    def boom(*args, **kwargs):
        raise RuntimeError("overpass unreachable")

    monkeypatch.setattr(enrich, "enrich_route", boom)
    with pytest.warns(UserWarning, match="OSM enrichment failed"):
        route = gpxsheet.analyze(str(l_route_file))
    assert all(s.name.startswith("Leg ") for s in route.segments)


def test_analyze_report_renders(l_route_file):
    from gpxsheet.report import format_analysis

    route = gpxsheet.analyze(str(l_route_file))
    text = format_analysis(route)
    assert "Route Length:" in text
    assert "Decision Points:" in text
    assert "Road Segments:" in text
