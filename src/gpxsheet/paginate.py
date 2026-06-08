"""Route-aware pagination (Milestone 3).

Splits an analyzed route into pages for the PDF. Per PRODUCT.md, pages are *not*
split by mileage -- breaks fall only on decision points, so a page never cuts a
navigation moment in half and a long decision-free stretch stays on one page
(the strip compresses it; the progress bar conveys absolute distance). Each page
is returned as a ``(start_mile, end_mile)`` span; :func:`slice_route`
materializes the sub-route for one span (mile-rebased to 0).
"""

from __future__ import annotations

from dataclasses import replace

from .models import Route

# A page holds at most this many decisions; the last page absorbs the run-out.
MAX_DECISIONS_PER_PAGE = 5


def paginate(
    route: Route,
    *,
    max_decisions: int = MAX_DECISIONS_PER_PAGE,
) -> list[tuple[float, float]]:
    """Return ``(start_mile, end_mile)`` spans, breaking only at decision points."""
    length = route.length_miles
    decisions = sorted(d.mile for d in route.decision_points if 0.0 < d.mile < length)
    if not decisions:
        return [(0.0, length)]

    pages: list[tuple[float, float]] = []
    start = 0.0
    i = 0
    while i < len(decisions):
        group = decisions[i : i + max_decisions]
        i += len(group)
        # Break at the group's last decision; the final group runs to the end.
        end = length if i >= len(decisions) else group[-1]
        pages.append((start, end))
        start = end
    return pages


def slice_route(route: Route, start: float, end: float) -> Route:
    """Materialize the sub-route for ``[start, end]``, rebased so it begins at 0.

    Decisions are taken as those in ``(start, end]`` (the breaking decision
    belongs to the page that ends on it); segments are clipped; fuel/reassurance
    within the span are kept. Only the page length is needed from ``points``.
    """
    span = max(end - start, 0.0)
    eps = 1e-9

    segments = []
    for s in route.segments:
        a = max(s.start_mile, start)
        b = min(s.end_mile, end)
        if b - a > 1e-6:
            segments.append(replace(s, start_mile=a - start, end_mile=b - start))

    decisions = [
        replace(d, mile=d.mile - start)
        for d in route.decision_points
        if start + eps < d.mile <= end + eps
    ]
    fuel = [
        replace(f, mile=f.mile - start)
        for f in route.fuel_stops
        if start - eps <= f.mile <= end + eps
    ]
    reassurance = [
        replace(m, mile=m.mile - start)
        for m in route.reassurance_markers
        if start - eps <= m.mile <= end + eps
    ]

    edge_points = [route.points[0], route.points[-1]] if route.points else []
    return Route(
        name=route.name,
        points=edge_points,
        distances_m=[0.0, span * 1609.344],
        segments=segments,
        decision_points=decisions,
        fuel_stops=fuel,
        reassurance_markers=reassurance,
        fuel_report=route.fuel_report,
    )
