"""Route-aware pagination.

Splits an analyzed route into pages for the PDF. Per docs/product.md, pages are *not*
split by mileage -- breaks fall only on decision points, so a page never cuts a
navigation moment in half and a long decision-free stretch stays on one page
(the strip compresses it; the progress bar conveys absolute distance). Each page
is returned as a ``(start_mile, end_mile)`` span; :func:`slice_route`
materializes the sub-route for one span (absolute miles).

:func:`plan_pages` is the single entry point for the dual-mode contract: 0 →
auto-fit (greedy analytic fit, :func:`fit_pages`); positive → fixed decision cap
(:func:`paginate`). All PDF rendering paths go through ``plan_pages``.
"""

from __future__ import annotations

import functools
from dataclasses import replace

from .geo import miles_to_meters
from .layout import TURN_STYLE_STYLIZED, StripLayout
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
    """Materialize the sub-route for ``[start, end]`` with absolute miles.

    Decisions are taken as those in ``(start, end]`` (the breaking decision
    belongs to the page that ends on it); fuel/reassurance/POIs use inclusive-start
    ``[start, end]`` because they can sit on a page boundary without belonging to
    the preceding page. The asymmetry is intentional: a decision at mile 40.0 is
    the *reason* a page break falls there, so it belongs to the page ending at 40.0,
    not the page starting at 40.0. A fuel stop at mile 40.0 should appear on
    whichever page the rider will read at that mile.
    Absolute miles are always preserved so strip labels read correctly across all
    layouts. Only the span length is needed from ``points``.
    """
    eps = 1e-9

    segments = []
    for s in route.segments:
        a = max(s.start_mile, start)
        b = min(s.end_mile, end)
        if b - a > 1e-6:
            segments.append(replace(s, start_mile=a, end_mile=b))

    decisions = [
        d
        for d in route.decision_points
        if start + eps < d.mile <= end + eps
    ]
    fuel = [
        f
        for f in route.fuel_stops
        if start - eps <= f.mile <= end + eps
    ]
    reassurance = [
        m
        for m in route.reassurance_markers
        if start - eps <= m.mile <= end + eps
    ]
    pois = [
        p
        for p in route.pois
        if start - eps <= p.mile <= end + eps
    ]
    spans = []
    for sp in route.spans:
        a = max(sp.start_mile, start)
        b = min(sp.end_mile, end)
        if b - a > 1e-6:
            spans.append(replace(sp, start_mile=a, end_mile=b))

    edge_points = [route.points[0], route.points[-1]] if route.points else []
    return Route(
        name=route.name,
        points=edge_points,
        distances_m=[0.0, miles_to_meters(end)],
        segments=segments,
        decision_points=decisions,
        fuel_stops=fuel,
        reassurance_markers=reassurance,
        pois=pois,
        spans=spans,
        fuel_report=route.fuel_report,
    )


# ---------------------------------------------------------------------------
# Auto-fit pagination (decisions_per_lane = 0)
# ---------------------------------------------------------------------------
# Pack as many decisions into a lane as fit without labels overlapping anything,
# with whitespace to keep objects distinct. This is an *analytic* estimate (no
# render/measure feedback loop): the strip is scaled into the fixed lane box the
# same way the renderer does, labels are measured once, and they're packed into
# two rows (above/below the ribbon). Best-effort and conservative (it breaks the
# lane early rather than risk an overlap). Markers may sit on the line; only the
# dots are allowed to touch the route.

_FIT_LABEL_PAD_IN = 0.06  # min horizontal whitespace between adjacent label boxes
_FIT_MARKER_GAP_IN = 0.10  # min spacing between adjacent marker dots
# Mirror draw_strip's xlim/ylim padding so the scale matches the rendered strip.
_FIT_WIDTH_PAD = 1.24  # xlim spans width * 1.24 (pad_x = 0.12*width per side)


@functools.lru_cache(maxsize=2048)
def _label_size_in(text: str, bold: bool) -> tuple[float, float]:
    """(width, height) of a label in inches at the strip's font size.

    Measured at 72 dpi so window-extent pixels equal points, i.e. inches*72 --
    a physical size independent of the eventual render dpi.
    """
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    from .strip import _use_bundled_fonts  # lazy: strip is a rendering dep

    _use_bundled_fonts()  # measure with the same font the renderer pins
    fig = plt.figure(dpi=72)
    t = fig.text(0, 0, text, fontsize=8, fontweight="bold" if bold else "normal")
    fig.canvas.draw()
    ext = t.get_window_extent(fig.canvas.get_renderer())  # type: ignore[attr-defined]
    plt.close(fig)
    return ext.width / 72.0, ext.height / 72.0


def _lane_fits(layout: StripLayout, box_w_in: float, box_h_in: float) -> bool:
    """Whether ``layout`` renders into a ``box_w_in`` x ``box_h_in`` lane with no
    label overlaps (two-row packing) and distinguishable marker dots."""
    from .strip import _marker_label  # lazy: avoid import cycle; strip imports paginate

    sw = layout.width or 1e-6
    sh = layout.height or 0.0
    # Scale the strip (with the renderer's padding) into the box, aspect-preserving.
    scale = min(box_w_in / (_FIT_WIDTH_PAD * sw), box_h_in / (1.6 * sh + 2.0))
    if scale <= 0.0:
        return True  # degenerate; don't block progress

    pts = sorted(((m.x * scale, m) for m in layout.markers), key=lambda t: t[0])

    # 1. Every adjacent marker dot needs whitespace to read as a separate object.
    xs = [x for x, _ in pts]
    if any(b - a < _FIT_MARKER_GAP_IN for a, b in zip(xs, xs[1:], strict=False)):
        return False

    # 2. Labels pack into two rows (above / below the ribbon) without overlap.
    row_right = [-1e18, -1e18]  # right edge (inches) of the last label in each row
    for x, m in pts:
        text = _marker_label(m)
        if not text:
            continue
        w, h = _label_size_in(text, m.kind in ("decision", "roundabout"))
        if h > box_h_in / 2.0:  # too tall for the half-lane band
            return False
        left = x - w / 2.0
        # Place in the row with the most room (smallest right edge) that fits.
        for r in sorted((0, 1), key=lambda i: row_right[i]):
            if left >= row_right[r] + _FIT_LABEL_PAD_IN:
                row_right[r] = x + w / 2.0
                break
        else:
            return False
    return True


def fit_pages(
    route: Route,
    *,
    box_w_in: float,
    box_h_in: float,
    turn_style: str = TURN_STYLE_STYLIZED,
    show_start: bool = False,
) -> list[tuple[float, float]]:
    """Greedy auto-fit pagination: ``(start, end)`` spans that each pack as many
    decisions as fit a ``box_w_in`` x ``box_h_in`` lane (always >= 1 decision)."""
    from .layout import build_strip_layout

    eps = 1e-9
    length = route.length_miles
    miles = sorted(d.mile for d in route.decision_points if eps < d.mile < length - eps)
    if not miles:
        return [(0.0, length)]

    pages: list[tuple[float, float]] = []
    start = 0.0
    i = 0
    n = len(miles)
    while i < n:
        accepted = i  # at least one decision per lane, even if it "doesn't fit"
        for k in range(i, n):
            end = length if k == n - 1 else miles[k]
            sub = slice_route(route, start, end)
            layout = build_strip_layout(
                sub, turn_style=turn_style,
                show_start=(show_start and start <= eps), show_end=(end >= length - eps),
            )
            if _lane_fits(layout, box_w_in, box_h_in):
                accepted = k
            else:
                break
        end = length if accepted == n - 1 else miles[accepted]
        pages.append((start, end))
        start = end
        i = accepted + 1
    return pages


def plan_pages(
    route: Route,
    decisions_per_lane: int = 0,
    *,
    box_w_in: float = 0.0,
    box_h_in: float = 0.0,
    turn_style: str = TURN_STYLE_STYLIZED,
    show_start: bool = False,
) -> list[tuple[float, float]]:
    """Return page spans for ``route``, encoding the dual-mode contract.

    ``decisions_per_lane = 0`` → auto-fit (greedy :func:`fit_pages`; requires
    ``box_w_in``/``box_h_in``); a positive value → fixed cap (:func:`paginate`).
    This is the single documented home for the ``0 ⇒ auto-fit`` semantics so
    callers don't need to branch.
    """
    if decisions_per_lane:
        return paginate(route, max_decisions=max(1, decisions_per_lane))
    return fit_pages(
        route, box_w_in=box_w_in, box_h_in=box_h_in,
        turn_style=turn_style, show_start=show_start,
    )
