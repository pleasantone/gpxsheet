"""Schematic map-strip renderer.

Renders a :class:`~gpxsheet.layout.StripLayout` to an image (``route_strip.png``)
with matplotlib. Kept separate from the layout engine so the engine stays pure
and matplotlib is only imported when actually rendering.

Label placement uses a small measured-extent repulsion pass (a mini
"adjustText"): labels are nudged apart from each other and off the route line,
and a dashed leader connects a moved label back to its marker.
"""

from __future__ import annotations

import math
from pathlib import Path

from .layout import TURN_STYLE_STYLIZED, StripLayout, build_strip_layout
from .models import Route

# Marker styling by kind: (color, matplotlib marker, z-order).
_MARKER_STYLE = {
    "start": ("#1b7837", "o", 5),
    "end": ("#762a83", "s", 5),
    "decision": ("#d6312b", "o", 6),
    "roundabout": ("#d6312b", "o", 6),  # drawn as a ring glyph (see draw_strip)
    "fuel": ("#2166ac", "D", 6),
    "reassurance": ("#7f7f7f", "|", 4),
}

# Ghosted "road not taken" stubs at a junction.
_STUB_LEN = 1.6  # schematic units (~ MIN_SEGMENT_LEN); short, subordinate to the route
_STUB_COLOR = "#bbbbbb"

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
    ax.plot(xs, ys, color="#333333", linewidth=4, solid_capstyle="round", zorder=2)

    for m in layout.markers:
        if m.kind == "roundabout":  # open ring + centre dot
            ax.plot(m.x, m.y, marker="o", mfc="none", mec="#d6312b", ms=14, mew=2.0, zorder=6)
            ax.plot(m.x, m.y, marker="o", color="#d6312b", markersize=4, zorder=7)
            continue
        color, marker, z = _MARKER_STYLE.get(m.kind, ("#000000", "o", 5))
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
            ha="center", va="top", fontsize=8, color="#444444",
        )


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
            ax.plot([m.x, ex], [m.y, ey], color=_STUB_COLOR, lw=1.5,
                    ls=(0, (2, 2)), zorder=1, solid_capstyle="round")
            ax.plot([ex], [ey], marker="o", mfc="white", mec=_STUB_COLOR, ms=3, mew=1.0, zorder=1)


def _marker_label(m) -> str:
    if m.kind in ("decision", "roundabout"):
        # Wrap "<mile> <turn> onto / <road>" so labels are narrower (taller).
        text = f"{m.mile:.1f}  {m.label}"
        return text.replace(" onto ", " onto\n", 1)
    if m.kind == "fuel":
        return "Fuel" if m.label.strip().lower() == "fuel" else f"Fuel: {m.label}"
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
        color, _, _ = _MARKER_STYLE.get(m.kind, ("#000000", "o", 5))
        weight = "bold" if m.kind in ("decision", "roundabout") else "normal"
        t = ax.text(
            m.x, m.y, _marker_label(m), ha="center", va="center", fontsize=7,
            color=color, fontweight=weight, clip_on=False, zorder=10,
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

    cxs = sum(px for px, _ in nodes_px) / len(nodes_px)
    cys = sum(py for _, py in nodes_px) / len(nodes_px)

    def outward_normal(i):
        """Unit normal at marker i, pointing away from the route centroid."""
        mx, my = markers_px[i]
        # tangent from the nearest path segment
        best = min(segs, key=lambda s: _point_seg_dist((mx, my), s[0], s[1])[0])
        tx, ty = best[1][0] - best[0][0], best[1][1] - best[0][1]
        nlen = math.hypot(tx, ty) or 1.0
        nx, ny = -ty / nlen, tx / nlen
        if (mx - cxs) * nx + (my - cys) * ny < 0:  # point away from centroid
            nx, ny = -nx, -ny
        return nx, ny

    centers = []
    normals = []
    for i in range(len(markers)):
        mx, my = markers_px[i]
        nx, ny = outward_normal(i)
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
                linestyle=(0, (2, 2)), color="#999999", linewidth=0.6, zorder=3,
            )


def generate_strip(
    gpx_file: str,
    output_file: str = "route_strip.png",
    *,
    profile: str = "sport-touring",
    fuel_range: float | None = None,
    use_osm: bool = False,
    turn_style: str = TURN_STYLE_STYLIZED,
) -> str:
    """Load, analyze, and render a route to a schematic strip image."""
    from .analysis import analyze_route
    from .gpx import load_route

    route = analyze_route(
        load_route(gpx_file), profile=profile, fuel_range=fuel_range, use_osm=use_osm
    )
    render_route_strip(route, output_file, turn_style=turn_style)
    return str(output_file)
