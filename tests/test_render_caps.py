"""Render-time safety caps for decision-flooded routes (paginate + pdf).

A long twisty route analyzed geometry-only floods with decisions/segments; these
caps keep pagination O(n) and the render bounded without affecting normal (OSM)
routes that stay well under the limits.
"""

from __future__ import annotations

from gpxsheet.geo import miles_to_meters
from gpxsheet.models import DecisionKind, DecisionPoint, GeoPoint, Route, Segment


def _flooded_route(n_decisions: int, length_mi: float = 200.0) -> Route:
    pts = [GeoPoint(38.0 + i * 0.001, -122.0) for i in range(50)]
    dists = [miles_to_meters(length_mi) * i / 49 for i in range(50)]
    decisions = [
        DecisionPoint(
            mile=round(length_mi * (k + 1) / (n_decisions + 1), 2),
            instruction="Left",
            significance=45 + (k % 3) * 15,  # 45 / 60 / 75
            lat=38.0, lon=-122.0,
            kind=DecisionKind.CRITICAL_TURN, turn_angle=40.0,
        )
        for k in range(n_decisions)
    ]
    segments = [
        Segment(name=f"Leg {i + 1}", start_mile=round(length_mi * i / n_decisions, 2),
                end_mile=round(length_mi * (i + 1) / n_decisions, 2))
        for i in range(n_decisions)
    ]
    return Route(
        name="flood", points=pts, distances_m=dists,
        decision_points=decisions, segments=segments,
    )


def test_plan_pages_caps_lanes_on_flood():
    from gpxsheet.paginate import MAX_AUTOFIT_LANES, plan_pages

    lanes = plan_pages(_flooded_route(400), 0, box_w_in=6.0, box_h_in=0.9)
    assert len(lanes) <= MAX_AUTOFIT_LANES


def test_plan_pages_autofit_unaffected_under_cap():
    # A handful of decisions still uses the greedy fit (one lane each fits here).
    from gpxsheet.paginate import plan_pages

    lanes = plan_pages(_flooded_route(5, length_mi=50.0), 0, box_w_in=6.0, box_h_in=0.9)
    assert len(lanes) >= 1


def test_cap_decisions_keeps_most_significant_and_rebuilds_segments():
    from gpxsheet.pdf import MAX_RENDER_DECISIONS, _cap_decisions

    route = _flooded_route(400)
    capped = _cap_decisions(route)
    assert len(capped.decision_points) == MAX_RENDER_DECISIONS
    # Kept the highest-significance ones (75s), then 60s -- never the 45s.
    assert all(d.significance >= 60 for d in capped.decision_points)
    # Restored to mile order, and segments rebuilt to match (not the original 400).
    miles = [d.mile for d in capped.decision_points]
    assert miles == sorted(miles)
    assert len(capped.segments) <= MAX_RENDER_DECISIONS + 1
    # The original route is untouched (shared analysis core must not mutate).
    assert len(route.decision_points) == 400
    assert len(route.segments) == 400


def test_cap_decisions_is_noop_under_cap():
    from gpxsheet.pdf import _cap_decisions

    route = _flooded_route(10)
    assert _cap_decisions(route) is route
