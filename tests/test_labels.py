"""Tests for the pure label-placement solver (no matplotlib)."""

from __future__ import annotations

import math

from gpxsheet.labels import (
    DEFAULT_TUNING,
    LabelTuning,
    Placement,
    place_labels,
    point_segment_distance,
)

# A horizontal route segment through the origin (tangent +x, normals ±y).
_ROUTE = [((-100.0, 0.0), (100.0, 0.0))]


def test_empty_input_returns_empty():
    assert place_labels([], [], _ROUTE) == []


def test_point_segment_distance():
    d, near = point_segment_distance((0.0, 5.0), (-10.0, 0.0), (10.0, 0.0))
    assert d == 5.0 and near == (0.0, 0.0)
    # beyond the segment end -> clamps to the endpoint
    d2, near2 = point_segment_distance((20.0, 0.0), (-10.0, 0.0), (10.0, 0.0))
    assert near2 == (10.0, 0.0) and d2 == 10.0


def test_alternating_sides_split_above_and_below():
    # Four anchors on the line; even indices go above (+y), odd below (-y).
    anchors = [(float(x), 0.0) for x in (0, 40, 80, 120)]
    sizes = [(30.0, 10.0)] * 4
    out = place_labels(anchors, sizes, _ROUTE)
    ys = [p.center[1] for p in out]
    assert ys[0] > 0 and ys[2] > 0  # above
    assert ys[1] < 0 and ys[3] < 0  # below


def test_overlapping_labels_get_separated():
    # Two wide labels on anchors close together would overlap if stacked; the
    # solver must push them apart (in x or y) by at least their half-widths/pad.
    anchors = [(0.0, 0.0), (10.0, 0.0)]
    sizes = [(60.0, 12.0), (60.0, 12.0)]
    a, b = place_labels(anchors, sizes, _ROUTE)
    (ax, ay), (bx, by) = a.center, b.center
    # boxes must not overlap: gap on at least one axis exceeds the half-extents.
    sep_x = abs(ax - bx) >= 60.0 + DEFAULT_TUNING.pad - 1.0
    sep_y = abs(ay - by) >= 12.0 + DEFAULT_TUNING.pad - 1.0
    assert sep_x or sep_y


def test_label_pushed_clear_of_route_line():
    # A single label's box must clear the route line by ~line_clear + half height.
    [p] = place_labels([(0.0, 0.0)], [(40.0, 12.0)], _ROUTE)
    assert abs(p.center[1]) >= DEFAULT_TUNING.line_clear


def test_leader_emitted_when_moved_and_starts_at_anchor():
    [p] = place_labels([(0.0, 0.0)], [(40.0, 12.0)], _ROUTE)
    assert p.leader is not None
    start, edge = p.leader
    assert start == (0.0, 0.0)  # leader begins at the anchor/dot
    # the edge point lies between the anchor and the label centre
    assert math.hypot(*[c - s for c, s in zip(p.center, start)]) > math.hypot(
        *[e - s for e, s in zip(edge, start)]
    )


def test_no_leader_when_label_stays_near_anchor():
    # offset=0 + a lone label with no repulsion -> it sits within leader_min of
    # the anchor (only nudged by half its height), so no leader is drawn.
    tuning = LabelTuning(offset=0.0, iters=5)
    [p] = place_labels([(0.0, 0.0)], [(40.0, 12.0)], [], tuning=tuning)
    assert p.leader is None
    assert math.hypot(*p.center) <= tuning.leader_min


def test_deterministic():
    anchors = [(0.0, 0.0), (25.0, 0.0), (50.0, 0.0)]
    sizes = [(40.0, 12.0)] * 3
    first = place_labels(anchors, sizes, _ROUTE)
    second = place_labels(anchors, sizes, _ROUTE)
    assert first == second
    assert all(isinstance(p, Placement) for p in first)
