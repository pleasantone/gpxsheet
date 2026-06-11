"""Tests for route-aware pagination and route slicing."""

import pytest

from gpxsheet.models import (
    POI,
    DecisionPoint,
    FuelStop,
    GeoPoint,
    ReassuranceMarker,
    Route,
    Segment,
)
from gpxsheet.paginate import paginate, slice_route


def _route(n_decisions=8, length=200.0):
    step = length / (n_decisions + 1)
    decisions = [
        DecisionPoint((i + 1) * step, f"Turn {i}", 60, 0, 0, turn_angle=45)
        for i in range(n_decisions)
    ]
    return Route(
        name="R",
        points=[GeoPoint(0, 0), GeoPoint(1, 1)],
        distances_m=[0.0, length * 1609.344],
        decision_points=decisions,
        segments=[Segment("Road", 0, length)],
        fuel_stops=[FuelStop(length / 2, "Mid Gas", 0, 0)],
        reassurance_markers=[ReassuranceMarker(length / 4, "Town", 0, 0, "landmark")],
    )


def test_paginate_breaks_on_decisions():
    route = _route(n_decisions=8, length=200.0)
    pages = paginate(route, max_decisions=3)
    # 8 decisions, 3 per page -> breaks after the 3rd and 6th decision, then tail.
    assert len(pages) == 3
    # every interior boundary is a decision mile
    decision_miles = {round(d.mile, 6) for d in route.decision_points}
    for _start, end in pages[:-1]:
        assert round(end, 6) in decision_miles
    # pages are contiguous and cover the whole route
    assert pages[0][0] == 0.0
    assert pages[-1][1] == route.length_miles
    for (_, e), (s2, _) in zip(pages, pages[1:], strict=False):
        assert e == s2
    # at most max_decisions per page
    for start, end in pages:
        on_page = [d for d in route.decision_points if start < d.mile <= end + 1e-9]
        assert len(on_page) <= 3


def test_long_decision_free_route_is_one_page():
    # Decision-cap only: a sparse route is NOT split by mileage.
    route = _route(n_decisions=1, length=300.0)  # one decision at 150
    assert paginate(route, max_decisions=5) == [(0.0, 300.0)]


def test_no_decisions_single_page():
    route = _route(n_decisions=0, length=120.0)
    assert paginate(route) == [(0.0, 120.0)]


def test_single_page_when_few_decisions():
    route = _route(n_decisions=2, length=40.0)
    assert paginate(route, max_decisions=5) == [(0.0, 40.0)]


def test_slice_route_no_rebase_keeps_absolute_miles():
    route = _route(n_decisions=8, length=200.0)
    page = slice_route(route, 40.0, 90.0, rebase=False)
    # absolute miles preserved (portrait lanes need this for correct labels)
    assert all(40.0 < d.mile <= 90.0 + 1e-9 for d in page.decision_points)
    assert page.length_miles == pytest.approx(90.0)  # absolute end, not the 50 mi span
    assert page.segments[0].start_mile == 40.0


def test_slice_poi_on_exact_page_boundary():
    """A POI sitting exactly on a page boundary (mile 40.0) must appear on the
    page that *starts* at that mile, not be dropped — inclusive-start [start, end]
    for POIs vs exclusive-start (start, end] for decisions."""
    route = Route(
        name="R",
        points=[GeoPoint(0, 0), GeoPoint(1, 1)],
        distances_m=[0.0, 200.0 * 1609.344],
        decision_points=[DecisionPoint(40.0, "Left onto Main", 60, 0, 0)],
        pois=[POI(mile=40.0, name="Fuel Stop", lat=0, lon=0)],
    )
    # Page ending at 40.0: the decision is included (exclusive-start), POI included
    page_end = slice_route(route, 0.0, 40.0)
    assert len(page_end.decision_points) == 1
    assert len(page_end.pois) == 1
    # Page starting at 40.0: decision is excluded (it ends the previous page),
    # but POI is included (inclusive-start for non-decisions)
    page_start = slice_route(route, 40.0, 200.0)
    assert len(page_start.decision_points) == 0
    assert len(page_start.pois) == 1


def test_slice_route_rebases_and_filters():
    route = _route(n_decisions=8, length=200.0)  # decisions at 22.2, 44.4, ...
    page = slice_route(route, 40.0, 90.0)
    # all decisions fall inside (40, 90], rebased to start at 0
    assert page.length_miles == 50.0
    assert all(0 < d.mile <= 50.0 + 1e-6 for d in page.decision_points)
    expected = [d for d in route.decision_points if 40.0 < d.mile <= 90.0 + 1e-9]
    assert len(page.decision_points) == len(expected)
    # segment clipped to the page span
    assert page.segments[0].start_mile == 0.0
    assert page.segments[0].end_mile == 50.0
