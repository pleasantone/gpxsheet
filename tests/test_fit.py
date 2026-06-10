"""Tests for auto-fit pagination (decisions_per_lane = 0/None)."""

from __future__ import annotations

from gpxsheet.models import DecisionPoint, GeoPoint, Route, Segment
from gpxsheet.strip import fit_pages

# A roomy portrait-ish lane box (inches), like _portrait_lane_box_in default.
BOX = {"box_w_in": 7.65, "box_h_in": 1.73, "turn_style": "stylized"}


def _route(labels):
    decs = [
        DecisionPoint(float(i + 1), lbl, 60, 0, 0, turn_angle=40)
        for i, lbl in enumerate(labels)
    ]
    n = len(labels)
    return Route(
        name="R",
        points=[GeoPoint(0, 0), GeoPoint(1, 1)],
        distances_m=[0.0, (n + 1) * 1609.344],
        decision_points=decs,
        segments=[Segment("Rd", 0.0, float(n + 1))],
    )


def test_no_decisions_is_one_lane():
    route = Route(
        name="R", points=[GeoPoint(0, 0), GeoPoint(0, 1)], distances_m=[0.0, 1609.344]
    )
    assert fit_pages(route, **BOX) == [(0.0, route.length_miles)]


def test_long_labels_need_more_lanes_than_short():
    short = _route([f"R{i}" for i in range(8)])
    long = _route([f"Turn left onto Very Long Road Name {i}" for i in range(8)])
    # Same geometry, wider labels -> at least as many lanes (usually more).
    assert len(fit_pages(long, **BOX)) >= len(fit_pages(short, **BOX))
    assert len(fit_pages(long, **BOX)) > 1  # the long ones can't all share a lane


def test_min_one_decision_per_lane():
    # A single oversized label still gets its own lane (never zero).
    huge = _route(["X" * 200])
    assert fit_pages(huge, **BOX) == [(0.0, huge.length_miles)]


def test_more_decisions_more_lanes():
    few = _route([f"Main St {i}" for i in range(6)])
    many = _route([f"Main St {i}" for i in range(24)])
    assert len(fit_pages(many, **BOX)) > len(fit_pages(few, **BOX))


def test_lanes_cover_route_in_order():
    route = _route([f"Cross Rd {i}" for i in range(15)])
    lanes = fit_pages(route, **BOX)
    assert lanes[0][0] == 0.0
    assert lanes[-1][1] == route.length_miles
    for (_, end), (start2, _) in zip(lanes, lanes[1:], strict=False):
        assert end == start2  # contiguous, no gaps/overlaps
    assert all(b > a for a, b in lanes)  # every lane is non-empty
