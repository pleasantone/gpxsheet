"""Pure junction topology helpers (roads-not-taken + roundabout exits).

These operate on plain bearings/rings, with no OSM or matplotlib dependency, so
they are fully unit-testable. :mod:`gpxsheet.enrich` feeds them topology pulled
from the OSM graph; :mod:`gpxsheet.strip` renders what they return.

All bearings are compass degrees (0 = N, 90 = E, clockwise), matching osmnx
edge bearings. A *relative angle* is signed degrees off the rider's heading,
``+`` to the right (clockwise) and ``-`` to the left -- the same convention as
:attr:`gpxsheet.models.DecisionPoint.turn_angle`.
"""

from __future__ import annotations

from collections.abc import Iterable

from .geo import bearing_delta
from .models import Branch

# A branch within this many degrees of the road taken (or of the road arrived on)
# is treated as that road, not a separate fork.
BRANCH_MATCH_TOL_DEG = 20.0
# Relative-angle bands for the direction word shown on a ghosted stub.
STRAIGHT_MAX_DEG = 25.0  # |angle| <= this reads as "straight" (cf. CONTINUE_MAX_ANGLE_DEG)
BACK_MIN_DEG = 150.0  # |angle| >= this reads as "back" (a road behind you)


def relative_angle(heading: float, bearing: float) -> float:
    """Signed angle (deg, +right/-left) of ``bearing`` relative to ``heading``."""
    a = (bearing - heading) % 360.0
    return a - 360.0 if a > 180.0 else a


def direction_word(angle: float) -> str:
    """Classify a relative angle into left | right | straight | back."""
    mag = abs(angle)
    if mag <= STRAIGHT_MAX_DEG:
        return "straight"
    if mag >= BACK_MIN_DEG:
        return "back"
    return "right" if angle > 0 else "left"


def _angular_close(b1: float, b2: float, tol: float) -> bool:
    return abs(bearing_delta(b1, b2)) <= tol


def branches_not_taken(
    arrival_bearing: float,
    taken_bearing: float,
    incident: Iterable[tuple[str | None, float]],
    *,
    tol: float = BRANCH_MATCH_TOL_DEG,
    taken_name: str | None = None,
) -> tuple[Branch, ...]:
    """Roads at a junction the route does *not* take, left-to-right.

    ``incident`` is ``(name, out_bearing)`` for every edge leaving the junction
    node (``out_bearing`` = compass bearing from the node toward the neighbour).
    The edge the rider arrived on (pointing back at ``arrival_bearing`` + 180) and
    the edge actually taken (``taken_bearing``) are excluded; the rest become
    :class:`~gpxsheet.models.Branch` entries with a relative angle and direction.
    A branch sharing ``taken_name`` (the road you continue on, e.g. the other
    carriageway of a divided road) is dropped as noise, not a real alternative.
    """
    came_from = (arrival_bearing + 180.0) % 360.0
    taken_key = taken_name.strip().casefold() if taken_name else None
    branches: list[Branch] = []
    for name, out_bearing in incident:
        if _angular_close(out_bearing, came_from, tol):  # the road you arrived on
            continue
        if _angular_close(out_bearing, taken_bearing, tol):  # the road you take
            continue
        if taken_key and name and name.strip().casefold() == taken_key:  # same road
            continue
        rel = relative_angle(arrival_bearing, out_bearing)
        branches.append(
            Branch(direction=direction_word(rel), relative_angle=round(rel, 1), name=name)
        )
    branches.sort(key=lambda b: b.relative_angle)
    return tuple(branches)


def roundabout_exit_number(ring_exits: list[bool], entry_idx: int, exit_idx: int) -> int:
    """1-based exit number for leaving a roundabout at ``exit_idx``.

    ``ring_exits[i]`` is True when ring node ``i`` has an exit spur, listed in
    circulation order. Counts spurs from just after the entry node up to and
    including the exit node -- i.e. the "take the Nth exit" count. Returns 0 if
    the entry and exit coincide or the exit is unreachable.
    """
    n = len(ring_exits)
    if n == 0 or entry_idx == exit_idx:
        return 0
    count = 0
    i = entry_idx
    for _ in range(n):
        i = (i + 1) % n
        if ring_exits[i]:
            count += 1
        if i == exit_idx:
            return count
    return 0
