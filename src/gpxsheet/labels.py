"""Pure label placement for the schematic strip.

A small "adjustText"-style solver, extracted from the matplotlib renderer so it
is backend-agnostic and unit-testable: it operates on plain 2-D coordinates
(anchors, label sizes, route segments, obstacle dots) in a single space — the
caller supplies measured pixels and converts the results back.

Each label starts offset along the route's local normal (alternating
above/below for mile-sorted markers, so dense labels spread into two rows), then
a force-directed pass separates labels from each other, off the route line, and
clear of every marker dot. A label that ends far enough from its anchor gets a
leader (anchor -> label-box edge).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Point = tuple[float, float]
Segment = tuple[Point, Point]


@dataclass(frozen=True)
class LabelTuning:
    """Force-directed placement constants (in the caller's coordinate units)."""

    offset: float = 30.0  # initial label offset from its anchor, along the normal
    pad: float = 5.0  # min gap between label boxes
    line_clear: float = 11.0  # min gap from a label to the route line
    anchor: float = 0.04  # spring keeping a label near its offset position
    repel: float = 0.85  # label-label separation strength
    line_repel: float = 1.3  # push off the route line
    marker_clear: float = 9.0  # min gap from a label to any marker dot
    marker_repel: float = 1.2
    step: float = 0.5  # integration step per iteration
    iters: int = 400
    leader_min: float = 12.0  # draw a leader once a label is this far from its anchor


DEFAULT_TUNING = LabelTuning()


@dataclass(frozen=True)
class Placement:
    """Solved label position and optional leader, in the input coordinate space."""

    center: Point
    leader: Segment | None  # (anchor, label-edge) or None if the label sits put


def point_segment_distance(p: Point, a: Point, b: Point) -> tuple[float, Point]:
    """(distance, nearest point) from point ``p`` to segment ``a``–``b``, in 2-D.

    Operates in the schematic layout coordinate space (rendered units), not
    geographic degrees — distinct from :func:`gpxsheet.geo.project_to_segment`.
    """
    px, py = p
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 == 0.0:
        return math.hypot(px - ax, py - ay), (ax, ay)
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / seg2))
    nx, ny = ax + t * dx, ay + t * dy
    return math.hypot(px - nx, py - ny), (nx, ny)


def _side_normal(anchor: Point, segments: list[Segment], above: bool) -> Point:
    """Unit normal off the route at ``anchor``, on the requested side.

    Perpendicular to the nearest route segment (so labels sit square to the
    line); ``above`` selects the upper/lower side. Alternating ``above`` across
    mile-sorted anchors spreads dense labels into two rows rather than bunching
    them on one side.
    """
    if not segments:
        return (0.0, 1.0) if above else (0.0, -1.0)
    best = min(segments, key=lambda s: point_segment_distance(anchor, s[0], s[1])[0])
    tx, ty = best[1][0] - best[0][0], best[1][1] - best[0][1]
    nlen = math.hypot(tx, ty) or 1.0
    nx, ny = -ty / nlen, tx / nlen
    if (ny >= 0) != above:  # orient to the requested side of the ribbon
        nx, ny = -nx, -ny
    return nx, ny


def place_labels(
    anchors: list[Point],
    sizes: list[Point],
    segments: list[Segment],
    obstacles: list[Point] | tuple[Point, ...] = (),
    *,
    tuning: LabelTuning = DEFAULT_TUNING,
) -> list[Placement]:
    """Place each label near its anchor without overlapping labels/line/markers.

    ``anchors`` are where labels attach (one per label), ``sizes`` the ``(w, h)``
    of each label box, ``segments`` the route polyline (for line clearance), and
    ``obstacles`` the marker dots to avoid. All coordinates share one space.
    Returns one :class:`Placement` per anchor, in order.
    """
    n = len(anchors)
    if n == 0:
        return []

    normals = [_side_normal(anchors[i], segments, above=(i % 2 == 0)) for i in range(n)]
    centers = [
        [anchors[i][0] + normals[i][0] * (tuning.offset + sizes[i][1] * 0.5),
         anchors[i][1] + normals[i][1] * (tuning.offset + sizes[i][1] * 0.5)]
        for i in range(n)
    ]

    for _ in range(tuning.iters):
        for i in range(n):
            cx, cy = centers[i]
            w, h = sizes[i]
            mx, my = anchors[i]
            nx, ny = normals[i]
            off = tuning.offset + h * 0.5
            fx = (mx + nx * off - cx) * tuning.anchor
            fy = (my + ny * off - cy) * tuning.anchor

            for j in range(n):
                if i == j:
                    continue
                ox, oy = centers[j]
                ow, oh = sizes[j]
                penx = (w + ow) / 2 + tuning.pad - abs(cx - ox)
                peny = (h + oh) / 2 + tuning.pad - abs(cy - oy)
                if penx > 0 and peny > 0:
                    if peny <= penx:
                        fy += math.copysign(peny, cy - oy or 1.0) * tuning.repel
                    else:
                        fx += math.copysign(penx, cx - ox or 1.0) * tuning.repel

            for a, b in segments:
                d, (px, py) = point_segment_distance((cx, cy), a, b)
                d = max(d, 1e-6)
                ux, uy = (cx - px) / d, (cy - py) / d
                # clearance accounts for the box extent along the push direction,
                # so a wide label clears a vertical line by its width.
                clear = abs(ux) * w / 2 + abs(uy) * h / 2 + tuning.line_clear
                if d < clear:
                    fx += ux * (clear - d) * tuning.line_repel
                    fy += uy * (clear - d) * tuning.line_repel

            for omx, omy in obstacles:
                dx, dy = cx - omx, cy - omy
                dd = math.hypot(dx, dy) or 1e-6
                ux, uy = dx / dd, dy / dd
                clear = abs(ux) * w / 2 + abs(uy) * h / 2 + tuning.marker_clear
                if dd < clear:
                    fx += ux * (clear - dd) * tuning.marker_repel
                    fy += uy * (clear - dd) * tuning.marker_repel

            centers[i][0] = cx + fx * tuning.step
            centers[i][1] = cy + fy * tuning.step

    placements: list[Placement] = []
    for i in range(n):
        cx, cy = centers[i]
        mx, my = anchors[i]
        leader: Segment | None = None
        if math.hypot(cx - mx, cy - my) > tuning.leader_min:
            # leader from anchor toward the label-box edge (not its center)
            w, h = sizes[i]
            dx, dy = cx - mx, cy - my
            dist = math.hypot(dx, dy) or 1.0
            edge = (cx - dx / dist * (w / 2), cy - dy / dist * (h / 2))
            leader = ((mx, my), edge)
        placements.append(Placement(center=(cx, cy), leader=leader))
    return placements
