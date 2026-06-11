"""PDF generation.

Composes the tank-bag document: a landscape or portrait pages
(see :mod:`gpxsheet.paginate`), with a header and a schematic map strip
(Map Zone).
Built with matplotlib (vector PDF via ``PdfPages``), reusing
:func:`gpxsheet.strip.draw_strip` for the map.
"""

from __future__ import annotations

from pathlib import Path

from . import colors, defaults
from .layout import TURN_STYLE_STYLIZED, build_strip_layout
from .models import Route
from .paginate import FIXED_DECISIONS_PER_LANE, fit_pages, paginate, plan_pages, slice_route
from .strip import _use_bundled_fonts, draw_strip

# Physical page sizes in inches, given as portrait (width, height). Landscape
# swaps the two. The layout math below works in figure fractions, so only the
# figure dims and the landscape aspect ratio depend on the paper choice.
PAGE_SIZES = {
    "letter": (8.5, 11.0),  # US Letter
    "a4": (8.27, 11.69),  # ISO A4, 210 x 297 mm
}


# Drawable map-box (inches) for a lane, mirroring the fractions in `_draw_lane`
# (portrait) and `_compose_page` (landscape) so auto-fit pagination scales the
# strip the same way the renderer will.
def _portrait_lane_box_in(paper: str, lanes_per_page: int) -> tuple[float, float]:
    pw, ph = PAGE_SIZES[paper.lower()]
    lane_h = (0.93 - 0.03) / max(1, lanes_per_page)  # figure fraction per lane
    return 0.90 * pw, (lane_h - 0.016) * 0.751 * ph


def _landscape_box_in(paper: str) -> tuple[float, float]:
    pw, ph = PAGE_SIZES[paper.lower()]  # landscape swaps the page dims
    return 0.92 * ph, 0.744 * pw


def iter_page_figures(
    route: Route,
    *,
    turn_style: str = TURN_STYLE_STYLIZED,
    orientation: str = "landscape",
    paper: str = defaults.PAPER,
    lanes_per_page: int = defaults.LANES_PER_PAGE,
    decisions_per_lane: int | None = FIXED_DECISIONS_PER_LANE,
    show_branches: bool = defaults.SHOW_BRANCHES,
):
    """Yield one matplotlib ``Figure`` per route-aware page (caller closes them).

    Shared by :func:`render_pdf` (PDF pages) and :func:`render_pages_png` (one
    stacked image). ``orientation`` is ``"landscape"`` (one strip per page, big
    map) or ``"portrait"`` (``lanes_per_page`` stacked strip lanes per page).
    A positive ``decisions_per_lane`` breaks pages every that-many decisions;
    ``0`` or ``None`` auto-fits as many decisions per page as fit (see
    :func:`gpxsheet.paginate.plan_pages`). ``show_branches`` toggles the ghosted
    "roads not taken" stubs (off by default).
    """
    if orientation not in ("landscape", "portrait"):
        raise ValueError(f"orientation must be 'landscape' or 'portrait', got {orientation!r}")
    paper = paper.lower()
    if paper not in PAGE_SIZES:
        raise ValueError(f"paper must be one of {sorted(PAGE_SIZES)}, got {paper!r}")
    page_w_in, page_h_in = PAGE_SIZES[paper]  # portrait (width, height) inches
    lanes_per_page = max(1, lanes_per_page)
    dpl = decisions_per_lane or 0  # normalise None → 0 for plan_pages
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _use_bundled_fonts()  # reproducible text/glyphs regardless of system fonts

    total = route.length_miles
    if orientation == "portrait":
        bw, bh = _portrait_lane_box_in(paper, lanes_per_page)
        lanes = plan_pages(
            route, dpl, box_w_in=bw, box_h_in=bh, turn_style=turn_style, show_start=True
        )
        page_groups = [
            lanes[i : i + lanes_per_page] for i in range(0, len(lanes), lanes_per_page)
        ]
        for i, group in enumerate(page_groups, start=1):
            fig = plt.figure(figsize=(page_w_in, page_h_in))  # portrait
            _compose_portrait_page(
                fig, route, group, i, len(page_groups), total, turn_style, lanes_per_page,
                show_branches,
            )
            yield fig
    else:
        bw, bh = _landscape_box_in(paper)
        pages = plan_pages(
            route, dpl, box_w_in=bw, box_h_in=bh, turn_style=turn_style, show_start=True
        )
        for i, (start, end) in enumerate(pages, start=1):
            fig = plt.figure(figsize=(page_h_in, page_w_in))  # landscape
            _compose_page(
                fig, route, start, end, i, len(pages), total, turn_style,
                page_h_in, page_w_in, show_branches,
            )
            yield fig


def render_pdf(
    route: Route,
    output_path: str | Path,
    *,
    turn_style: str = TURN_STYLE_STYLIZED,
    orientation: str = "landscape",
    paper: str = defaults.PAPER,
    lanes_per_page: int = defaults.LANES_PER_PAGE,
    decisions_per_lane: int | None = FIXED_DECISIONS_PER_LANE,
    show_branches: bool = defaults.SHOW_BRANCHES,
) -> Path:
    """Render an already-analyzed ``route`` to a multi-page PDF.

    ``orientation`` is ``"landscape"`` (one strip per page, big map) or
    ``"portrait"`` (``lanes_per_page`` stacked strip lanes per page,
    roadbook-style). Both break a page every ``decisions_per_lane`` decisions;
    ``lanes_per_page`` is portrait-only. ``paper`` is one of :data:`PAGE_SIZES`
    (``"letter"`` or ``"a4"``). ``show_branches`` toggles the ghosted "roads not
    taken" stubs (off by default).
    """
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    output_path = Path(output_path)
    with PdfPages(output_path) as pdf:
        for fig in iter_page_figures(
            route, turn_style=turn_style, orientation=orientation, paper=paper,
            lanes_per_page=lanes_per_page, decisions_per_lane=decisions_per_lane,
            show_branches=show_branches,
        ):
            pdf.savefig(fig, facecolor="white")
            plt.close(fig)
    return output_path


def render_pages_png(
    route: Route,
    output_path: str | Path,
    *,
    turn_style: str = TURN_STYLE_STYLIZED,
    orientation: str = "landscape",
    paper: str = defaults.PAPER,
    lanes_per_page: int = defaults.LANES_PER_PAGE,
    decisions_per_lane: int | None = FIXED_DECISIONS_PER_LANE,
    show_branches: bool = defaults.SHOW_BRANCHES,
    dpi: int | None = None,
) -> Path:
    """Render a paginated layout to a single tall PNG: every page stacked top to
    bottom (a contact sheet), so the whole route is one image."""
    import matplotlib.pyplot as plt
    import numpy as np

    dpi = PREVIEW_DPI if dpi is None else dpi
    output_path = Path(output_path)
    rows: list = []
    for fig in iter_page_figures(
        route, turn_style=turn_style, orientation=orientation, paper=paper,
        lanes_per_page=lanes_per_page, decisions_per_lane=decisions_per_lane,
        show_branches=show_branches,
    ):
        fig.set_dpi(dpi)
        fig.set_facecolor("white")
        fig.canvas.draw()
        w, h = fig.canvas.get_width_height()
        rows.append(np.asarray(fig.canvas.buffer_rgba()).reshape(h, w, 4).copy())
        plt.close(fig)

    if not rows:  # empty route -> a small blank canvas, still a valid PNG
        rows = [np.full((1, 1, 4), 255, dtype=np.uint8)]
    width = max(r.shape[1] for r in rows)
    padded = [
        r if r.shape[1] == width
        else np.pad(r, ((0, 0), (0, width - r.shape[1]), (0, 0)), constant_values=255)
        for r in rows
    ]
    plt.imsave(output_path, np.vstack(padded))
    return output_path


def _compose_page(
    fig, route, start, end, page_no, page_count, total, turn_style,
    page_w_in, page_h_in, show_branches=defaults.SHOW_BRANCHES,
) -> None:
    """Lay out a single page (header, map strip) into ``fig``.

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
            facecolor=colors.PANEL_FILL, edgecolor=colors.PANEL_EDGE, linewidth=1.0, zorder=-10,
        )
    )
    map_ax = fig.add_axes([panel_x + 0.01, map_y, map_w, map_h])
    draw_strip(fig, map_ax, layout, draw_ribbon=False, show_branches=show_branches)
    ribbon = "  ›  ".join(layout.ribbon)
    if ribbon:
        fig.text(
            0.5, panel_bottom + 0.012, ribbon, ha="center", va="bottom",
            fontsize=8, color=colors.TEXT_LABEL,
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
        ha="right", va="center", fontsize=11, color=colors.START, fontweight="bold",
    )
    fig.text(
        0.97, 0.955, f"Page {page_no} of {page_count}",
        ha="right", va="center", fontsize=11, color=colors.TEXT_MUTED,
    )


def _compose_portrait_page(
    fig, route, lanes, page_no, page_count, total, turn_style, lanes_per_page,
    show_branches=defaults.SHOW_BRANCHES,
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
            show_branches=show_branches,
        )


def _draw_lane(
    fig, route, start, end, rect, *, show_start, show_end, turn_style,
    show_branches=defaults.SHOW_BRANCHES,
) -> None:
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
            facecolor=colors.PANEL_FILL, edgecolor=colors.PANEL_EDGE, linewidth=1.0, zorder=-10,
        )
    )
    # Absolute mile range for this lane (green), top-left of the frame.
    fig.text(
        x + 0.008, y + h - 0.006, f"{start:.0f}–{end:.0f} mi",
        ha="left", va="top", fontsize=8, color=colors.START, fontweight="bold",
    )
    # Strip fills the frame, leaving room for the mile label (top) and a clear
    # band for the ribbon (bottom) so the lowest decision labels don't touch it.
    # Bands scale with the lane height so lanes look the same on a portrait page
    # and in the (variable-height) preview column. The fractions reproduce the
    # original 0.016 / 0.040 figure-fractions at the default 4 lanes/page.
    label_h, ribbon_h = 0.071 * h, 0.178 * h
    map_ax = fig.add_axes([x + 0.01, y + ribbon_h, w - 0.02, h - label_h - ribbon_h])
    draw_strip(fig, map_ax, layout, draw_ribbon=False, show_branches=show_branches)
    ribbon = "  ›  ".join(layout.ribbon)
    if ribbon:
        fig.text(
            x + w / 2, y + 0.008, ribbon,
            ha="center", va="bottom", fontsize=7, color=colors.TEXT_LABEL,
        )


def _draw_progress(fig, start: float, end: float, total: float) -> None:
    ax = fig.add_axes([0.06, 0.90, 0.88, 0.02])
    ax.axis("off")
    ax.set_xlim(0, 1)
    ax.set_ylim(-1, 1)
    frac0 = start / total if total else 0.0
    frac1 = end / total if total else 1.0
    ax.plot([0, 1], [0, 0], color=colors.PROGRESS_TRACK, lw=3, solid_capstyle="round")
    # the current page's span, highlighted on the full-route track
    ax.plot([frac0, frac1], [0, 0], color=colors.DECISION, lw=6, solid_capstyle="round")
    ax.plot([frac0], [0], marker="o", color=colors.DECISION, markersize=8)
    ax.text(0, 0.9, "START", ha="left", va="bottom", fontsize=7, color=colors.TEXT_MUTED)
    ax.text(1, 0.9, "END", ha="right", va="bottom", fontsize=7, color=colors.TEXT_MUTED)
    ax.annotate(
        f"YOU  {start:.0f} mi", (frac0, 0), (frac0, -0.9),
        ha="center", va="top", fontsize=7, color=colors.DECISION, fontweight="bold",
    )


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
    decisions_per_lane: int | None = FIXED_DECISIONS_PER_LANE,
    show_branches: bool = defaults.SHOW_BRANCHES,
) -> Path:
    """Render the whole route as a single image of stacked strip lanes.

    Like the portrait roadbook but with no page breaks: every lane (a strip
    covering up to ``decisions_per_lane`` decisions, in absolute miles) is stacked
    into one tall figure that grows with the route -- a scrollable on-screen
    overview. The image format follows ``output_path``'s extension.
    """
    auto = not decisions_per_lane  # 0 or None -> auto-fit
    cap = max(1, decisions_per_lane) if decisions_per_lane else 1  # fixed-cap value
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    _use_bundled_fonts()  # reproducible text/glyphs regardless of system fonts
    output_path = Path(output_path)
    total = route.length_miles
    if auto:
        # Preview lane box: the map axes inside one stacked lane (see _draw_lane).
        box_w = 0.90 * PREVIEW_WIDTH_IN
        box_h = 0.751 * (PREVIEW_LANE_HEIGHT_IN * 0.82)
        lanes = fit_pages(
            route, box_w_in=box_w, box_h_in=box_h, turn_style=turn_style, show_start=True
        )
    else:
        lanes = paginate(route, max_decisions=cap)
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
        ha="right", va="center", fontsize=11, color=colors.START, fontweight="bold",
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
            show_branches=show_branches,
        )

    fig.savefig(output_path, dpi=PREVIEW_DPI, facecolor="white")
    plt.close(fig)
    return output_path


# Layouts the service exposes, and the output formats each supports. ``portrait``
# and ``landscape`` are paginated (multi-page PDF / one stacked PNG); ``preview``
# is the whole route as one image; ``strip`` is a single schematic strip.
LAYOUTS = ("portrait", "landscape", "preview", "strip")
FORMATS = ("pdf", "png")


def render_layout(
    route: Route,
    output_path: str | Path,
    *,
    layout: str = "portrait",
    fmt: str = "pdf",
    turn_style: str = TURN_STYLE_STYLIZED,
    paper: str = defaults.PAPER,
    lanes_per_page: int = defaults.LANES_PER_PAGE,
    decisions_per_lane: int | None = FIXED_DECISIONS_PER_LANE,
    show_branches: bool = defaults.SHOW_BRANCHES,
) -> Path:
    """Render an already-analyzed ``route`` to ``output_path`` in any layout/format.

    ``layout`` is one of :data:`LAYOUTS`, ``fmt`` one of :data:`FORMATS`.
    ``output_path``'s extension must match ``fmt`` (the ``preview``/``strip``
    renderers infer their format from it). ``show_branches`` toggles the ghosted
    "roads not taken" stubs (off by default).
    """
    if layout not in LAYOUTS:
        raise ValueError(f"layout must be one of {LAYOUTS}, got {layout!r}")
    if fmt not in FORMATS:
        raise ValueError(f"fmt must be one of {FORMATS}, got {fmt!r}")
    output_path = Path(output_path)

    if layout in ("portrait", "landscape"):
        render = render_pdf if fmt == "pdf" else render_pages_png
        return render(
            route, output_path, turn_style=turn_style, orientation=layout, paper=paper,
            lanes_per_page=lanes_per_page, decisions_per_lane=decisions_per_lane,
            show_branches=show_branches,
        )
    if layout == "preview":
        return render_preview(
            route, output_path, turn_style=turn_style, decisions_per_lane=decisions_per_lane,
            show_branches=show_branches,
        )
    from .strip import render_route_strip

    return render_route_strip(
        route, output_path, turn_style=turn_style, show_branches=show_branches
    )
