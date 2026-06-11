"""GPXSheet — motorcycle sport-touring route awareness generator.

Public library API. The three entry points mirror the web service:
:func:`render` (a map), :func:`analyze` and :func:`validate` (reports). See
``docs/product.md`` for the full design specification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .validate import Finding, ValidationReport

if TYPE_CHECKING:
    from .models import Route

__version__ = "0.2.1"  # x-release-please-version

__all__ = [
    "__version__",
    "render",
    "analyze",
    "validate",
    "analyze_route",
    "load_route",
    "Finding",
    "ValidationReport",
]

DEFAULT_PROFILE = "sport-touring"


def render(
    gpx_file: str,
    output_file: str | None = None,
    *,
    profile: str = DEFAULT_PROFILE,
    fuel_range: float | None = None,
    layout: str = "portrait",
    format: str = "pdf",
    turn_style: str = "stylized",
    paper: str = "letter",
    lanes_per_page: int = 4,
    decisions_per_lane: int | None = None,
    show_branches: bool = False,
) -> str:
    """Render a GPX route to a tank-bag navigation map.

    Args:
        gpx_file: Path to the input ``.gpx`` route or track.
        output_file: Output path; defaults to ``route.<format>``. Its extension
            should match ``format``.
        profile: One of ``minimalist``, ``sport-touring``, ``rally``.
        fuel_range: Rider fuel range in miles, used for fuel-gap analysis.
        layout: ``"portrait"`` (stacked roadbook lanes, the default),
            ``"landscape"`` (one big strip per page), ``"preview"`` (the whole
            route as one continuous image), or ``"strip"`` (a single schematic
            strip).
        format: ``"pdf"`` or ``"png"``. Paginated layouts (``portrait`` /
            ``landscape``) become a multi-page PDF or one tall stacked PNG.
        turn_style: Strip bend style, ``"stylized"`` or ``"faithful"``.
        paper: Page size for paginated PDF layouts, ``"letter"`` or ``"a4"``.
        lanes_per_page: ``portrait`` only -- strip lanes per page.
        decisions_per_lane: max decisions per page/lane for the paginated layouts
            (``portrait`` / ``landscape`` / ``preview``). The default (``None``;
            also ``0``) auto-fits as many as fit each lane without overlap; pass a
            positive number to force a fixed cap.
        show_branches: draw the ghosted "roads not taken" stubs at each junction
            (on by default); set False to hide them.

    Returns:
        The path to the written file.
    """
    from .pdf import render_layout

    if output_file is None:
        output_file = f"route.{format}"
    route = analyze(gpx_file, profile=profile, fuel_range=fuel_range)
    render_layout(
        route,
        output_file,
        layout=layout,
        fmt=format,
        turn_style=turn_style,
        paper=paper,
        lanes_per_page=lanes_per_page,
        decisions_per_lane=decisions_per_lane,
        show_branches=show_branches,
    )
    return str(output_file)


def analyze(
    gpx_file: str,
    *,
    profile: str = DEFAULT_PROFILE,
    fuel_range: float | None = None,
    reassurance_interval: float | None = None,
    include_hazards: bool = False,
) -> Route:
    """Run the route analysis engine on a GPX file.

    Loads the GPX, runs decision-point detection, reassurance-marker placement,
    fuel analysis and segmentation, and returns the populated :class:`Route`.
    ``include_hazards`` adds OSM hazard data for validation. See the ``analyze``
    output mode in ``docs/product.md``.
    """
    from .analysis import analyze_route as _analyze_route
    from .gpx import load_route as _load_route

    route = _load_route(gpx_file)
    return _analyze_route(
        route,
        profile=profile,
        fuel_range=fuel_range,
        reassurance_interval=reassurance_interval,
        include_hazards=include_hazards,
    )


def validate(
    gpx_file: str,
    *,
    profile: str = DEFAULT_PROFILE,
    fuel_range: float | None = None,
) -> ValidationReport:
    """Validate a route for fuel gaps, unpaved stretches and ferry crossings.

    Analyzes the route (with OSM hazard data) and returns a
    :class:`ValidationReport` holding the analyzed :class:`Route` and the list of
    :class:`Finding` results.
    """
    from .validate import validate_route

    route = analyze(gpx_file, profile=profile, fuel_range=fuel_range, include_hazards=True)
    return ValidationReport(route=route, findings=validate_route(route, fuel_range=fuel_range))


def load_route(gpx_file: str, *, name: str | None = None) -> Route:
    """Load a GPX file into a :class:`Route` without running analysis."""
    from .gpx import load_route as _load_route

    return _load_route(gpx_file, name=name)


def analyze_route(route: Route, **kwargs) -> Route:
    """Run analysis on an already-loaded :class:`Route` (see :mod:`gpxsheet.analysis`)."""
    from .analysis import analyze_route as _analyze_route

    return _analyze_route(route, **kwargs)
