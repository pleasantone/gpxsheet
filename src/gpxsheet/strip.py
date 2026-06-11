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
from .defaults import SHOW_BRANCHES
from .labels import place_labels
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


def render_route_strip(
    route: Route,
    output_path: str | Path,
    *,
    layout: StripLayout | None = None,
    turn_style: str = TURN_STYLE_STYLIZED,
    show_branches: bool = SHOW_BRANCHES,
    title: str | None = None,
    dpi: int = 150,
) -> Path:
    """Render ``route`` as a schematic strip PNG. Returns the output path.

    ``show_branches`` draws the ghosted "roads not taken" stubs at each junction
    (off by default); set it True to show them.
    """
    import matplotlib

    matplotlib.use("Agg")  # headless; no display needed
    import matplotlib.pyplot as plt

    _use_bundled_fonts()  # reproducible text/glyphs regardless of system fonts
    layout = layout or build_strip_layout(route, turn_style=turn_style)
    output_path = Path(output_path)

    aspect = (layout.width + 2) / (layout.height + 2)
    fig_w = min(max(aspect * 2.2, 7.0), 26.0)
    fig_h = min(max(fig_w / aspect, 3.5), 16.0)
    fig, ax = plt.subplots(figsize=(fig_w, fig_h))

    draw_strip(fig, ax, layout, show_branches=show_branches)

    header = title or route.name or "Route"
    fig.suptitle(header, fontsize=12, fontweight="bold", y=0.99)

    fig.savefig(output_path, dpi=dpi, bbox_inches="tight", pad_inches=0.4, facecolor="white")
    plt.close(fig)
    return output_path


def draw_strip(
    fig, ax, layout: StripLayout, *, draw_ribbon: bool = True, show_branches: bool = SHOW_BRANCHES
) -> None:
    """Draw a schematic strip (path, markers, collision-placed labels) into ``ax``.

    Shared by the standalone PNG renderer and the per-page PDF composition.
    ``show_branches`` toggles the ghosted "roads not taken" stubs (off by default).
    """
    xs = [p[0] for p in layout.path]
    ys = [p[1] for p in layout.path]
    if show_branches:
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


# Our vendored monochrome symbol font (subset of Google Noto Emoji, OFL): a tiny
# per-glyph fallback for the fuel/ferry/food symbols DejaVu Sans lacks. See
# ``fonts/README.md``. Listed AFTER DejaVu so it only supplies those glyphs.
_NOTO_SUBSET = Path(__file__).parent / "fonts" / "NotoEmoji-subset.ttf"


@functools.lru_cache(maxsize=1)
def _bundled_sans_path() -> str:
    """Path to matplotlib's vendored DejaVu Sans TTF (always shipped with mpl)."""
    from matplotlib import get_data_path

    return str(Path(get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf")


@functools.lru_cache(maxsize=1)
def _render_font_paths() -> tuple[str, ...]:
    """The font files the renderer pins, in fallback order (text, then symbols)."""
    paths = [_bundled_sans_path()]
    if _NOTO_SUBSET.exists():  # vendored; guard so a stripped install still renders
        paths.append(str(_NOTO_SUBSET))
    return tuple(paths)


@functools.lru_cache(maxsize=1)
def _register_bundled_fonts() -> list[str]:
    """Register the pinned font files by path; return their family names in order."""
    from matplotlib import font_manager

    names = []
    for path in _render_font_paths():
        font_manager.fontManager.addfont(path)
        names.append(font_manager.FontProperties(fname=path).get_name())
    return names


def _use_bundled_fonts() -> None:
    """Pin matplotlib to bundled fonts for *reproducible* output.

    Without this, ``findfont`` resolves through whatever fonts the machine has
    installed, so the same route renders different text (and selects different
    symbol glyphs) on different machines. We register matplotlib's own DejaVu
    Sans plus our vendored Noto Emoji subset (the fuel/ferry/food glyphs DejaVu
    lacks) by path and pin them as a ``font.sans-serif`` fallback chain, so
    rendering depends only on these files -- not on system font config.
    Idempotent; call before each render.
    """
    from matplotlib import rcParams

    names = _register_bundled_fonts()
    # Pin the *explicit* family list (not the generic "sans-serif" alias, which
    # collapses to a single font): matplotlib's per-glyph fallback only walks the
    # families named directly in font.family, so this is what lets the fuel/ferry/
    # food glyphs fall through from DejaVu Sans to the Noto Emoji subset.
    rcParams["font.family"] = names  # DejaVu first; Noto Emoji per-glyph fallback
    rcParams["font.sans-serif"] = names
    rcParams["mathtext.fontset"] = "dejavusans"


@functools.lru_cache(maxsize=256)
def _font_covers(codepoint: int) -> bool:
    """Whether any pinned render font has a glyph for ``codepoint``.

    Probes the same files :func:`_use_bundled_fonts` pins (DejaVu Sans + the Noto
    Emoji subset), so glyph selection matches what matplotlib actually draws --
    not whatever ``findfont`` would have resolved from system fonts.
    """
    from matplotlib.font_manager import get_font

    return any(get_font(p).get_char_index(codepoint) for p in _render_font_paths())


@functools.lru_cache(maxsize=8)
def _kind_glyph(kind: str) -> str:
    """A trailing-spaced symbol prefix for ``kind`` (or "" if none is renderable)."""
    for cp in _GLYPH_CANDIDATES.get(kind, ()):
        if _font_covers(cp):
            return chr(cp) + " "
    return ""


# Map GPX <sym> strings (lowercase) to preferred Unicode codepoints.
# Covers common Garmin/GaiaGPS symbols; anything not listed falls back to ★.
# Symbols known to carry no useful visual meaning get no glyph at all.
_WAYPOINT_SYMBOL_GLYPHS: dict[str, tuple[int, ...]] = {
    "summit": (0x25B2,),          # ▲
    "scenic area": (0x2605,),     # ★
    "scenic": (0x2605,),          # ★
    "campground": (0x26FA,),      # ⛺
    "flag, blue": (0x25B6,),      # ▶ (blue flag → directional marker)
    "flag, green": (0x25B6,),     # ▶
    "flag, red": (0x25B6,),       # ▶
    "circle, green": (0x25CF,),   # ●
    "circle, red": (0x25CF,),     # ●
    "circle, blue": (0x25CF,),    # ●
}
# Generic symbols that add no visual meaning — suppress the glyph.
_WAYPOINT_SYMBOL_NO_GLYPH = {"waypoint", "flag, white", ""}


def _waypoint_glyph(symbol: str | None) -> str:
    """Trailing-spaced glyph for a GPX waypoint symbol, or "" if none applies."""
    if not symbol:
        return ""
    key = symbol.lower().strip()
    if key in _WAYPOINT_SYMBOL_NO_GLYPH:
        return ""
    candidates = _WAYPOINT_SYMBOL_GLYPHS.get(key, (0x2605,))  # default ★
    for cp in candidates:
        if _font_covers(cp):
            return chr(cp) + " "
    return ""


def _mil(m) -> str:
    """Formatted mileage prefix: ``(12.3) ``."""
    return f"({m.mile:.1f}) "


def _marker_label(m) -> str:
    if m.kind in ("decision", "roundabout"):
        # Wrap so labels are narrower (taller).
        text = f"{_mil(m)}{m.label}"
        return text.replace(" onto ", " onto\n", 1)
    if m.kind == "fuel":
        return f"{_mil(m)}{_kind_glyph('fuel')}{m.label}"
    if m.kind == "food":
        return f"{_mil(m)}{_kind_glyph('food')}{m.label}"
    if m.kind == "ferry":
        return f"{_mil(m)}{_kind_glyph('ferry')}{m.label}"
    if m.kind == "waypoint":
        return f"{_mil(m)}{_waypoint_glyph(getattr(m, 'symbol', None))}{m.label}"
    if m.kind == "unpaved":
        return f"{_mil(m)}{m.label}"
    if m.kind == "reassurance":
        # Generic interval ticks ("15 mi") get no text; named towns get mileage.
        stripped = m.label.removesuffix(" mi").strip()
        return "" if stripped.isdigit() else f"{_mil(m)}{m.label}"
    if m.kind in ("start", "end"):
        return f"{_mil(m)}{m.label}"
    return ""


def _place_labels_with_leaders(fig, ax, path_nodes, markers, obstacles=()) -> None:
    """Draw each marker's label, placed by the pure solver in :mod:`gpxsheet.labels`.

    Builds the text objects, measures them in display pixels, hands the geometry
    to :func:`gpxsheet.labels.place_labels`, then sets the solved positions and
    draws a dashed leader for any label the solver moved off its dot.
    """
    if not markers:
        return

    texts = []
    for m in markers:
        color, _, _ = _MARKER_STYLE.get(m.kind, (colors.MARKER_FALLBACK, "o", 5))
        weight = "bold" if m.kind in ("decision", "roundabout", "waypoint") else "normal"
        style = "normal"
        size: float = 7
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
    r = fig.canvas.get_renderer()  # type: ignore[attr-defined]
    trans = ax.transData.transform
    inv = ax.transData.inverted().transform

    def _px(p) -> tuple[float, float]:
        x, y = trans(p)
        return float(x), float(y)

    anchors = [_px((m.x, m.y)) for m in markers]
    sizes = [(float(e.width), float(e.height)) for e in (t.get_window_extent(r) for t in texts)]
    nodes_px = [_px(p) for p in path_nodes]
    segments = list(zip(nodes_px, nodes_px[1:], strict=False))
    obstacle_px = [_px(o) for o in obstacles]

    placements = place_labels(anchors, sizes, segments, obstacle_px)
    for t, pl in zip(texts, placements, strict=True):
        t.set_position(inv(pl.center))
        if pl.leader is not None:
            start, edge = pl.leader
            (sx, sy), (ex, ey) = inv(start), inv(edge)
            ax.plot(
                [sx, ex], [sy, ey],
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
