"""PDF generation.

Composes the tank-bag document: one landscape page (US Letter or A4) per route-aware
page (see :mod:`gpxsheet.paginate`), each with a header, the schematic map strip
(Map Zone), a large-text cue zone (NEXT / AFTER / FUEL / TOTAL), and a progress
indicator. Built with matplotlib (vector PDF via ``PdfPages``), reusing
:func:`gpxsheet.strip.draw_strip` for the map.
"""

from __future__ import annotations

from pathlib import Path

from .layout import TURN_STYLE_STYLIZED, build_strip_layout
from .models import Route
from .paginate import paginate, slice_route
from .strip import draw_strip

_RED = "#d6312b"
_GREEN = "#1b7837"
_GREY = "#666666"


# Portrait mode: each page stacks several route "lanes" (strips), each covering
# a few decisions, clearly separated -- a roadbook / TripTik layout.
LANES_PER_PAGE = 4
DECISIONS_PER_LANE = 4


# Physical page sizes in inches, given as portrait (width, height). Landscape
# swaps the two. The layout math below works in figure fractions, so only the
# figure dims and the landscape aspect ratio depend on the paper choice.
PAGE_SIZES = {
    "letter": (8.5, 11.0),  # US Letter
    "a4": (8.27, 11.69),  # ISO A4, 210 x 297 mm
}
DEFAULT_PAPER = "letter"


def render_pdf(
    route: Route,
    output_path: str | Path,
    *,
    turn_style: str = TURN_STYLE_STYLIZED,
    orientation: str = "landscape",
    paper: str = DEFAULT_PAPER,
    lanes_per_page: int = LANES_PER_PAGE,
    decisions_per_lane: int = DECISIONS_PER_LANE,
) -> Path:
    """Render an already-analyzed ``route`` to a multi-page PDF.

    ``orientation`` is ``"landscape"`` (one strip per page, big map) or
    ``"portrait"`` (``lanes_per_page`` stacked strip lanes per page, each holding
    up to ``decisions_per_lane`` decisions, roadbook-style). ``paper`` is one of
    :data:`PAGE_SIZES` (``"letter"`` or ``"a4"``).
    """
    if orientation not in ("landscape", "portrait"):
        raise ValueError(f"orientation must be 'landscape' or 'portrait', got {orientation!r}")
    paper = paper.lower()
    if paper not in PAGE_SIZES:
        raise ValueError(f"paper must be one of {sorted(PAGE_SIZES)}, got {paper!r}")
    page_w_in, page_h_in = PAGE_SIZES[paper]  # portrait (width, height) inches
    lanes_per_page = max(1, lanes_per_page)
    decisions_per_lane = max(1, decisions_per_lane)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    output_path = Path(output_path)
    total = route.length_miles

    with PdfPages(output_path) as pdf:
        if orientation == "portrait":
            lanes = paginate(route, max_decisions=decisions_per_lane)
            page_groups = [
                lanes[i : i + lanes_per_page] for i in range(0, len(lanes), lanes_per_page)
            ]
            for i, group in enumerate(page_groups, start=1):
                fig = plt.figure(figsize=(page_w_in, page_h_in))  # portrait
                _compose_portrait_page(
                    fig, route, group, i, len(page_groups), total, turn_style, lanes_per_page
                )
                pdf.savefig(fig, facecolor="white")
                plt.close(fig)
        else:
            pages = paginate(route)
            for i, (start, end) in enumerate(pages, start=1):
                fig = plt.figure(figsize=(page_h_in, page_w_in))  # landscape
                _compose_page(
                    fig, route, start, end, i, len(pages), total, turn_style,
                    page_h_in, page_w_in,
                )
                pdf.savefig(fig, facecolor="white")
                plt.close(fig)
    return output_path


def _compose_page(
    fig, route, start, end, page_no, page_count, total, turn_style,
    page_w_in, page_h_in,
) -> None:
    """Lay out a single page (header, map strip, cue zone, progress) into ``fig``.

    ``page_w_in``/``page_h_in`` are the physical page width/height in inches for
    the rendered (landscape) orientation, used to keep the strip's aspect ratio.
    """
    page = slice_route(route, start, end)
    layout = build_strip_layout(
        page,
        turn_style=turn_style,
        show_start=(page_no == 1),  # interior page edges are marked by a decision
        show_end=(page_no == page_count),
    )

    _draw_header(fig, route.name, page_no, page_count, start, total)
    _draw_progress(fig, start, end, total)

    # Map zone (option b): the framed panel HUGS the strip (height = the strip's
    # natural aspect-preserving height + the ribbon + a small margin) and the whole
    # panel is centered in the area below the header/progress bar -- so there's no
    # big empty box around a flat strip. Panel size/position varies per page.
    from matplotlib.patches import Rectangle

    avail_lo, avail_hi = 0.05, 0.86  # vertical area below the progress bar
    panel_x, panel_w = 0.03, 0.94
    margin, ribbon_band = 0.018, 0.030  # inner pad; room for the ribbon at bottom

    span_x = 1.24 * (layout.width or 1.0)
    span_y = 1.6 * (layout.height or 0.0) + 2.0
    aspect = span_x / span_y
    map_w = panel_w - 0.02
    map_h = (map_w * page_w_in / aspect) / page_h_in
    map_h = max(0.12, min(map_h, (avail_hi - avail_lo) - 2 * margin - ribbon_band))

    panel_h = map_h + 2 * margin + ribbon_band
    panel_bottom = (avail_lo + avail_hi) / 2 - panel_h / 2  # center the panel
    map_y = panel_bottom + margin + ribbon_band

    fig.patches.append(
        Rectangle(
            (panel_x, panel_bottom), panel_w, panel_h, transform=fig.transFigure,
            facecolor="#fafafa", edgecolor="#dddddd", linewidth=1.0, zorder=-10,
        )
    )
    map_ax = fig.add_axes([panel_x + 0.01, map_y, map_w, map_h])
    draw_strip(fig, map_ax, layout, draw_ribbon=False)
    ribbon = "  ›  ".join(layout.ribbon)
    if ribbon:
        fig.text(
            0.5, panel_bottom + 0.012, ribbon, ha="center", va="bottom",
            fontsize=8, color="#444444",
        )


def _draw_header(
    fig, name: str, page_no: int, page_count: int, start: float, total: float, name_max: int = 48
) -> None:
    # Truncate long route names (GPX often auto-names "<start> to <end>") so the
    # title never runs into the mileage / page counter.
    display = name if len(name) <= name_max else name[: name_max - 1].rstrip() + "…"
    fig.text(0.03, 0.955, display, ha="left", va="center", fontsize=13, fontweight="bold")
    fig.text(
        0.84, 0.955, f"{start:.0f} / {total:.0f} mi",
        ha="right", va="center", fontsize=11, color=_GREEN, fontweight="bold",
    )
    fig.text(
        0.97, 0.955, f"Page {page_no} of {page_count}",
        ha="right", va="center", fontsize=11, color=_GREY,
    )


def _compose_portrait_page(
    fig, route, lanes, page_no, page_count, total, turn_style, lanes_per_page
) -> None:
    """Stack several route lanes (strips) down a portrait page, clearly separated."""
    _draw_header(fig, route.name, page_no, page_count, lanes[0][0], total, name_max=38)

    eps = 1e-6
    top, bottom, gap = 0.93, 0.03, 0.016
    # Fixed lane height (sized for a full page) so lanes look consistent across
    # pages; partial pages are top-aligned (empty space falls at the bottom).
    lane_h = (top - bottom) / lanes_per_page
    for j, (start, end) in enumerate(lanes):
        y1 = top - j * lane_h
        rect = (0.04, y1 - lane_h + gap / 2, 0.92, lane_h - gap)
        _draw_lane(
            fig, route, start, end, rect,
            show_start=(start <= eps),
            show_end=(end >= total - eps),
            turn_style=turn_style,
        )


def _draw_lane(fig, route, start, end, rect, *, show_start, show_end, turn_style) -> None:
    """Draw one route lane (a framed strip covering [start, end]) into ``rect``."""
    from matplotlib.patches import Rectangle

    x, y, w, h = rect
    page = slice_route(route, start, end, rebase=False)  # keep absolute miles
    layout = build_strip_layout(
        page, turn_style=turn_style, show_start=show_start, show_end=show_end
    )

    fig.patches.append(
        Rectangle(
            (x, y), w, h, transform=fig.transFigure,
            facecolor="#fafafa", edgecolor="#dddddd", linewidth=1.0, zorder=-10,
        )
    )
    # Absolute mile range for this lane (green), top-left of the frame.
    fig.text(
        x + 0.008, y + h - 0.006, f"{start:.0f}–{end:.0f} mi",
        ha="left", va="top", fontsize=8, color=_GREEN, fontweight="bold",
    )
    # Strip fills the frame, leaving room for the mile label (top) and a clear
    # band for the ribbon (bottom) so the lowest decision labels don't touch it.
    # Bands scale with the lane height so lanes look the same on a portrait page
    # and in the (variable-height) preview column. The fractions reproduce the
    # original 0.016 / 0.040 figure-fractions at the default 4 lanes/page.
    label_h, ribbon_h = 0.071 * h, 0.178 * h
    map_ax = fig.add_axes([x + 0.01, y + ribbon_h, w - 0.02, h - label_h - ribbon_h])
    draw_strip(fig, map_ax, layout, draw_ribbon=False)
    ribbon = "  ›  ".join(layout.ribbon)
    if ribbon:
        fig.text(
            x + w / 2, y + 0.008, ribbon, ha="center", va="bottom", fontsize=7, color="#444444"
        )


def _draw_progress(fig, start: float, end: float, total: float) -> None:
    ax = fig.add_axes([0.06, 0.90, 0.88, 0.02])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(-1, 1)
    frac0 = start / total if total else 0.0
    frac1 = end / total if total else 1.0
    ax.plot([0, 1], [0, 0], color="#cccccc", lw=3, solid_capstyle="round")
    ax.plot([frac0, frac1], [0, 0], color=_RED, lw=6, solid_capstyle="round")  # this page
    ax.plot([frac0], [0], marker="o", color=_RED, markersize=8)
    ax.text(0, 0.9, "START", ha="left", va="bottom", fontsize=7, color=_GREY)
    ax.text(1, 0.9, "END", ha="right", va="bottom", fontsize=7, color=_GREY)
    ax.annotate(
        f"YOU  {start:.0f} mi", (frac0, 0), (frac0, -0.9),
        ha="center", va="top", fontsize=7, color=_RED, fontweight="bold",
    )


def generate_pdf(
    gpx_file: str,
    output_file: str = "route.pdf",
    *,
    profile: str = "sport-touring",
    fuel_range: float | None = None,
    turn_style: str = TURN_STYLE_STYLIZED,
    orientation: str = "landscape",
    paper: str = DEFAULT_PAPER,
    lanes_per_page: int = LANES_PER_PAGE,
    decisions_per_lane: int = DECISIONS_PER_LANE,
) -> str:
    """Load, analyze, and render a route to a tank-bag PDF."""
    from .analysis import analyze_route
    from .gpx import load_route

    route = analyze_route(load_route(gpx_file), profile=profile, fuel_range=fuel_range)
    render_pdf(
        route,
        output_file,
        turn_style=turn_style,
        orientation=orientation,
        paper=paper,
        lanes_per_page=lanes_per_page,
        decisions_per_lane=decisions_per_lane,
    )
    return str(output_file)


# Preview: the whole route as one un-paginated column of strip lanes (a single
# image, not a multi-page PDF) so the user can eyeball the entire route at once.
PREVIEW_WIDTH_IN = 8.5
PREVIEW_LANE_HEIGHT_IN = 1.7  # per stacked lane; good on-screen size at PREVIEW_DPI
PREVIEW_HEADER_IN = 0.5
# Raster resolution for the preview PNG -- the same value the strip renderer uses,
# so the preview matches the rest of the product's output (not a separate knob).
PREVIEW_DPI = 150


def render_preview(
    route: Route,
    output_path: str | Path,
    *,
    turn_style: str = TURN_STYLE_STYLIZED,
    decisions_per_lane: int = DECISIONS_PER_LANE,
) -> Path:
    """Render the whole route as a single image of stacked strip lanes.

    Like the portrait roadbook but with no page breaks: every lane (a strip
    covering up to ``decisions_per_lane`` decisions, in absolute miles) is stacked
    into one tall figure that grows with the route -- a scrollable on-screen
    overview. The image format follows ``output_path``'s extension.
    """
    decisions_per_lane = max(1, decisions_per_lane)
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    output_path = Path(output_path)
    total = route.length_miles
    lanes = paginate(route, max_decisions=decisions_per_lane)
    n = max(1, len(lanes))

    fig_h = PREVIEW_HEADER_IN + n * PREVIEW_LANE_HEIGHT_IN
    fig = plt.figure(figsize=(PREVIEW_WIDTH_IN, fig_h))

    header_frac = PREVIEW_HEADER_IN / fig_h
    lane_frac = PREVIEW_LANE_HEIGHT_IN / fig_h
    gap = 0.18 * lane_frac

    name = route.name or "Route"
    display = name if len(name) <= 60 else name[:59].rstrip() + "…"
    header_y = 1 - header_frac / 2
    fig.text(0.04, header_y, display, ha="left", va="center", fontsize=13, fontweight="bold")
    fig.text(
        0.96, header_y, f"{total:.0f} mi",
        ha="right", va="center", fontsize=11, color=_GREEN, fontweight="bold",
    )

    eps = 1e-6
    for j, (start, end) in enumerate(lanes):
        y_top = (1 - header_frac) - j * lane_frac
        rect = (0.04, y_top - lane_frac + gap / 2, 0.92, lane_frac - gap)
        _draw_lane(
            fig, route, start, end, rect,
            show_start=(start <= eps),
            show_end=(end >= total - eps),
            turn_style=turn_style,
        )

    fig.savefig(output_path, dpi=PREVIEW_DPI, facecolor="white")
    plt.close(fig)
    return output_path


def generate_preview(
    gpx_file: str,
    output_file: str = "route_preview.png",
    *,
    profile: str = "sport-touring",
    fuel_range: float | None = None,
    turn_style: str = TURN_STYLE_STYLIZED,
    decisions_per_lane: int = DECISIONS_PER_LANE,
) -> str:
    """Load, analyze, and render a route to a non-paginated multi-strip preview image."""
    from .analysis import analyze_route
    from .gpx import load_route

    route = analyze_route(load_route(gpx_file), profile=profile, fuel_range=fuel_range)
    render_preview(
        route, output_file, turn_style=turn_style, decisions_per_lane=decisions_per_lane
    )
    return str(output_file)
