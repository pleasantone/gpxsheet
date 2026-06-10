"""Schematic map-strip renderer.

Renders a :class:`~gpxsheet.layout.StripLayout` to an image (``route_strip.png``)
with matplotlib. Kept separate from the layout engine so the engine stays pure
and matplotlib is only imported when actually rendering.

Label placement uses a small measured-extent repulsion pass (a mini
"adjustText"): labels are nudged apart from each other and off the route line,
and a dashed leader connects a moved label back to its marker.
"""

from __future__ import annotations

import functools
import math
from pathlib import Path

from . import colors
from .layout import TURN_STYLE_STYLIZED, StripLayout, build_strip_layout
from .models import Route

# Marker styling by kind: (color, matplotlib marker, z-order).
_MARKER_STYLE = {
    "start": (colors.START, "o", 5),
    "end": (colors.END, "s", 5),
    "decision": (colors.DECISION, "o", 6),
    "roundabout": (colors.DECISION, "o", 6),  # drawn as a ring glyph (see draw_strip)
    "fuel": (colors.FUEL, "D", 6),
    "food": (colors.FOOD, "P", 6),
    "waypoint": (colors.WAYPOINT, "^", 5),
    "ferry": (colors.FERRY_RIBBON, "v", 6),
    "unpaved": (colors.UNPAVED_RIBBON, "v", 6),
    "reassurance": (colors.REASSURANCE, "|", 4),
}

# Styled ribbon overlays (unpaved / ferry): (color, linestyle) drawn over the
# base route line for that stretch.
_OVERLAY_STYLE = {
    "unpaved": (colors.UNPAVED_RIBBON, (0, (4, 3))),
    "ferry": (colors.FERRY_RIBBON, (0, (1, 2))),
}

# Ghosted "road not taken" stubs at a junction.
_STUB_LEN = 1.6  # schematic units (~ MIN_SEGMENT_LEN); short, subordinate to the route

# Label-placement tuning (display pixels at figure dpi).
_OFFSET = 30.0  # initial label offset from its marker, along the outward normal
_PAD = 5.0  # min gap between label boxes
_LINE_CLEAR = 11.0  # min gap from a label to the route line
_ANCHOR = 0.04  # spring keeping a label near its marker's outward offset
_REPEL = 0.85  # label-label separation strength
_LINE_REPEL = 1.3  # push off the route line
_MARKER_CLEAR = 9.0  # min gap from a label to any marker dot (incl. its own)
_MARKER_REPEL = 1.2
_STEP = 0.5
_ITERS = 400
_LEADER_MIN = 12.0  # draw a leader once a label is at least this far from marker


def render_route_strip(
    route: Route,
    output_path: str | Path,
    *,
    layout: StripLayout | None = None,
    turn_style: str = TURN_STYLE_STYLIZED,
    title: str | None = None,
    dpi: int = 150,
) -> Path:
    """Render ``route`` as a schematic strip PNG. Returns the output path."""
    import matplotlib

    matplotlib.use("Agg")  # headless; no display needed
    import matplotlib.pyplot as plt

    layout = layout or build_strip_layout(route, turn_style=turn_style)
    output_path = Path(output_path)

    aspect = (layout.width + 2) / (layout.height + 2)
    fig_w = min(max(aspect * 2.2, 7.0), 26.0)
    fig_h = min(max(fig_w / aspect, 3.5), 16.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    draw_strip(fig, ax, layout)

    header = title or route.name or "Route"
    fig.suptitle(header, fontsize=12, fontweight="bold", y=0.99)

    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", pad_inches=0.4, facecolor="white")
    plt.close(fig)
    return output_path


def draw_strip(fig, ax, layout: StripLayout, *, draw_ribbon: bool = True) -> None:
    """Draw a schematic strip (path, markers, collision-placed labels) into ``ax``.

    Shared by the standalone PNG renderer and the per-page PDF composition.
    """
    xs = [p[0] for p in layout.path]
    ys = [p[1] for p in layout.path]
    _draw_branch_stubs(ax, layout)  # ghosted, behind the route line
    ax.plot(xs, ys, color=colors.ROUTE_LINE, linewidth=4, solid_capstyle="round", zorder=2)
    _draw_overlays(ax, layout)  # recolor unpaved/ferry stretches over the base line

    for m in layout.markers:
        if m.kind == "roundabout":  # open ring + centre dot
            ax.plot(m.x, m.y, marker="o", mfc="none", mec=colors.DECISION, ms=14, mew=2.0, zorder=6)
            ax.plot(m.x, m.y, marker="o", color=colors.DECISION, markersize=4, zorder=7)
            continue
        color, marker, z = _MARKER_STYLE.get(m.kind, (colors.MARKER_FALLBACK, "o", 5))
        size = 11 if m.kind in ("start", "end") else (9 if m.kind == "decision" else 7)
        ax.plot(m.x, m.y, marker=marker, color=color, markersize=size, zorder=z)

    # Fix the view so transforms are stable during label placement.
    pad_x = 0.12 * (layout.width or 1)
    pad_y = 0.30 * (layout.height or 1) + 1
    ax.set_xlim(-pad_x, layout.width + pad_x)
    ax.set_ylim(-pad_y, layout.height + pad_y)
    ax.set_aspect("equal")
    ax.axis("off")

    labeled = [m for m in sorted(layout.markers, key=lambda mk: mk.mile) if _marker_label(m)]
    obstacles = [(m.x, m.y) for m in layout.markers]  # all dots, for label avoidance
    _place_labels_with_leaders(fig, ax, layout.path, labeled, obstacles)

    if draw_ribbon and layout.ribbon:
        ax.text(
            0.5, -0.02, "  ›  ".join(layout.ribbon), transform=ax.transAxes,
            ha="center", va="top", fontsize=8, color=colors.TEXT_LABEL,
        )


def _draw_overlays(ax, layout: StripLayout) -> None:
    """Redraw unpaved/ferry stretches in their own colour + dash over the ribbon."""
    for ov in layout.overlays:
        if len(ov.points) < 2:
            continue
        color, dash = _OVERLAY_STYLE.get(ov.kind, (colors.ROUTE_LINE, (0, (4, 3))))
        oxs = [p[0] for p in ov.points]
        oys = [p[1] for p in ov.points]
        ax.plot(oxs, oys, color=color, linewidth=4, linestyle=dash,
                solid_capstyle="round", zorder=3)


def _draw_branch_stubs(ax, layout: StripLayout) -> None:
    """Ghosted stubs for the road(s) NOT taken at each junction.

    Each stub is drawn off the marker at its branch's angle relative to the
    rider's *arrival* heading (the incoming ribbon segment), so a fork/multi-way
    reads at a glance: the route continues on the dark line, the gray stub is the
    branch to ignore.
    """
    path = layout.path
    if len(path) < 2:
        return
    for m in layout.markers:
        if not m.branches:
            continue
        # incoming ribbon direction at this marker == the rider's arrival heading
        i = min(range(len(path)), key=lambda k: (path[k][0] - m.x) ** 2 + (path[k][1] - m.y) ** 2)
        j = i - 1 if i > 0 else i + 1
        tx, ty = path[i][0] - path[j][0], path[i][1] - path[j][1]
        if i == 0:  # used the next node; flip to point forward
            tx, ty = -tx, -ty
        base = math.atan2(ty, tx)
        for b in m.branches:
            # +relative_angle is a right turn (clockwise) == negative in math coords
            ang = base - math.radians(b.relative_angle)
            ex, ey = m.x + _STUB_LEN * math.cos(ang), m.y + _STUB_LEN * math.sin(ang)
            ax.plot([m.x, ex], [m.y, ey], color=colors.BRANCH_STUB, lw=1.5,
                    ls=(0, (2, 2)), zorder=1, solid_capstyle="round")
            ax.plot([ex], [ey], marker="o", mfc="white", mec=colors.BRANCH_STUB,
                    ms=3, mew=1.0, zorder=1)


# Preferred symbol glyphs per marker kind, most-expressive first. Many of these
# (the fuel pump, ferry, fork-and-knife) are absent from the default DejaVu Sans
# and would render as a tofu box, so each kind falls back through covered glyphs
# and finally to no glyph (the label's word carries the meaning). Resolved
# against the *active* font, so a richer system font shows the nicer symbol.
_GLYPH_CANDIDATES = {
    "fuel": (0x26FD,),  # ⛽ fuel pump
    "food": (0x1F374, 0x2615),  # 🍴 fork+knife -> ☕ hot beverage
    "ferry": (0x26F4, 0x2693),  # ⛴ ferry -> ⚓ anchor
}


@functools.lru_cache(maxsize=256)
def _font_covers(codepoint: int) -> bool:
    """Whether the active default font has a glyph for ``codepoint``."""
    from matplotlib.font_manager import FontProperties, findfont, get_font

    return bool(get_font(findfont(FontProperties())).get_char_index(codepoint))


@functools.lru_cache(maxsize=8)
def _kind_glyph(kind: str) -> str:
    """A trailing-spaced symbol prefix for ``kind`` (or "" if none is renderable)."""
    for cp in _GLYPH_CANDIDATES.get(kind, ()):
        if _font_covers(cp):
            return chr(cp) + " "
    return ""


def _marker_label(m) -> str:
    if m.kind in ("decision", "roundabout"):
        # Wrap "<mile> <turn> onto / <road>" so labels are narrower (taller).
        text = f"{m.mile:.1f}  {m.label}"
        return text.replace(" onto ", " onto\n", 1)
    if m.kind == "fuel":
        base = "Fuel" if m.label.strip().lower() == "fuel" else f"Fuel: {m.label}"
        return f"{_kind_glyph('fuel')}{base}  ({m.mile:.1f} mi)"
    if m.kind == "food":
        return f"{_kind_glyph('food')}{m.label}  ({m.mile:.1f} mi)"
    if m.kind == "ferry":
        return f"{_kind_glyph('ferry')}{m.label}  ({m.mile:.1f} mi)"
    if m.kind in ("waypoint", "unpaved"):
        return f"{m.label}  ({m.mile:.1f} mi)"
    if m.kind == "reassurance":
        # Generic mileage markers ("15 mi") get a tick but no text; only named
        # places (towns/landmarks) are worth the label clutter.
        stripped = m.label.removesuffix(" mi").strip()
        return "" if stripped.isdigit() else m.label
    if m.kind in ("start", "end"):
        return m.label
    return ""


def _point_seg_dist(p, a, b):
    """(distance, nearest point) from point p to segment a-b, in 2D."""
    px, py = p
    ax_, ay = a
    bx, by = b
    dx, dy = bx - ax_, by - ay
    seg2 = dx * dx + dy * dy
    if seg2 == 0.0:
        return math.hypot(px - ax_, py - ay), (ax_, ay)
    t = max(0.0, min(1.0, ((px - ax_) * dx + (py - ay) * dy) / seg2))
    nx, ny = ax_ + t * dx, ay + t * dy
    return math.hypot(px - nx, py - ny), (nx, ny)


def _place_labels_with_leaders(fig, ax, path_nodes, markers, obstacles=()) -> None:
    """Place each label near its marker, offset to the outside of the route.

    Labels start offset along the route's local outward normal (so they sit on
    the outside of bends), then a repulsion pass separates them from each other,
    off the route line, and clear of every marker dot in ``obstacles`` (so a
    label never covers its own or a neighbour's dot). A dashed leader connects
    any moved label to its dot.
    """
    if not markers:
        return

    texts = []
    for m in markers:
        color, _, _ = _MARKER_STYLE.get(m.kind, (colors.MARKER_FALLBACK, "o", 5))
        weight = "bold" if m.kind in ("decision", "roundabout") else "normal"
        style = "normal"
        size = 7
        if m.kind == "reassurance":
            # Named towns/landmarks earn a darker, italic, slightly larger label
            # so they stand out from the muted interval ticks (which carry no
            # text); the tick dot itself stays grey.
            color, style, size = colors.REASSURANCE_TOWN, "italic", 7.5
        t = ax.text(
            m.x, m.y, _marker_label(m), ha="center", va="center", fontsize=size,
            color=color, fontweight=weight, fontstyle=style, clip_on=False, zorder=10,
        )
        texts.append(t)

    # Capture the transforms only AFTER drawing: set_aspect("equal") finalizes
    # the data<->pixel mapping during the draw, so transforms taken earlier would
    # be stale (which previously left leader lines disconnected from their dots).
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    trans = ax.transData.transform
    inv = ax.transData.inverted().transform
    obstacles_px = [trans(o) for o in obstacles]

    markers_px = [trans((m.x, m.y)) for m in markers]
    nodes_px = [trans(p) for p in path_nodes]
    segs = list(zip(nodes_px, nodes_px[1:], strict=False))
    sizes = [(e.width, e.height) for e in (t.get_window_extent(r) for t in texts)]

    def side_normal(i, above):
        """Unit normal off the route at marker i, on the chosen side (above/below).

        Perpendicular to the nearest ribbon segment so labels sit square to the
        line; the ``above`` flag selects the upper or lower side. ``markers`` is
        mile-sorted, so alternating the side spreads dense labels into two rows
        instead of bunching them all above the line.
        """
        mx, my = markers_px[i]
        best = min(segs, key=lambda s: _point_seg_dist((mx, my), s[0], s[1])[0])
        tx, ty = best[1][0] - best[0][0], best[1][1] - best[0][1]
        nlen = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / nlen, tx / nlen
        if (ny >= 0) != above:  # orient to the requested side of the ribbon
            nx, ny = -nx, -ny
        return nx, ny

    centers = []
    normals = []
    for i in range(len(markers)):
        mx, my = markers_px[i]
        nx, ny = side_normal(i, above=(i % 2 == 0))  # alternate rows along the route
        normals.append((nx, ny))
        off = _OFFSET + sizes[i][1] * 0.5
        centers.append([mx + nx * off, my + ny * off])

    n = len(centers)
    for _ in range(_ITERS):
        for i in range(n):
            cx, cy = centers[i]
            w, h = sizes[i]
            mx, my = markers_px[i]
            nx, ny = normals[i]
            off = _OFFSET + h * 0.5
            fx = (mx + nx * off - cx) * _ANCHOR
            fy = (my + ny * off - cy) * _ANCHOR

            for j in range(n):
                if i == j:
                    continue
                ox, oy = centers[j]
                ow, oh = sizes[j]
                penx = (w + ow) / 2 + _PAD - abs(cx - ox)
                peny = (h + oh) / 2 + _PAD - abs(cy - oy)
                if penx > 0 and peny > 0:
                    if peny <= penx:
                        fy += math.copysign(peny, cy - oy or 1.0) * _REPEL
                    else:
                        fx += math.copysign(penx, cx - ox or 1.0) * _REPEL

            for a, b in segs:
                d, (px, py) = _point_seg_dist((cx, cy), a, b)
                d = max(d, 1e-6)
                ux, uy = (cx - px) / d, (cy - py) / d
                # clearance must account for the box extent along the push
                # direction, so a wide label clears a vertical line by its width.
                clear = abs(ux) * w / 2 + abs(uy) * h / 2 + _LINE_CLEAR
                if d < clear:
                    fx += ux * (clear - d) * _LINE_REPEL
                    fy += uy * (clear - d) * _LINE_REPEL

            for omx, omy in obstacles_px:
                dx, dy = cx - omx, cy - omy
                dd = math.hypot(dx, dy) or 1e-6
                ux, uy = dx / dd, dy / dd
                clear = abs(ux) * w / 2 + abs(uy) * h / 2 + _MARKER_CLEAR
                if dd < clear:
                    fx += ux * (clear - dd) * _MARKER_REPEL
                    fy += uy * (clear - dd) * _MARKER_REPEL

            centers[i][0] = cx + fx * _STEP
            centers[i][1] = cy + fy * _STEP

    for i, t in enumerate(texts):
        cx, cy = centers[i]
        t.set_position(inv((cx, cy)))
        mx, my = markers_px[i]
        if math.hypot(cx - mx, cy - my) > _LEADER_MIN:
            # leader from marker toward the label box edge (not its center)
            w, h = sizes[i]
            dx, dy = cx - mx, cy - my
            dist = math.hypot(dx, dy) or 1.0
            ex = cx - dx / dist * (w / 2)
            ey = cy - dy / dist * (h / 2)
            (mdx, mdy), (edx, edy) = inv((mx, my)), inv((ex, ey))
            ax.plot(
                [mdx, edx], [mdy, edy],
                linestyle=(0, (2, 2)), color=colors.LEADER_LINE, linewidth=0.6, zorder=3,
            )


# --- Auto-fit pagination (decisions_per_lane = 0/None) ----------------------
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

    fig = plt.figure(dpi=72)
    t = fig.text(0, 0, text, fontsize=8, fontweight="bold" if bold else "normal")
    fig.canvas.draw()
    ext = t.get_window_extent(fig.canvas.get_renderer())
    plt.close(fig)
    return ext.width / 72.0, ext.height / 72.0


def _lane_fits(layout: StripLayout, box_w_in: float, box_h_in: float) -> bool:
    """Whether ``layout`` renders into a ``box_w_in`` x ``box_h_in`` lane with no
    label overlaps (two-row packing) and distinguishable marker dots."""
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
    from .paginate import slice_route

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
            sub = slice_route(route, start, end, rebase=False)
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
