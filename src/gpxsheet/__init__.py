"""GPXSheet — motorcycle sport-touring route awareness generator.

Public library API. See ``PRODUCT.md`` for the full design specification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Route

__version__ = "0.1.0"  # x-release-please-version

__all__ = [
    "__version__",
    "generate_pdf",
    "generate_strip",
    "analyze",
    "analyze_route",
    "load_route",
]

DEFAULT_PROFILE = "sport-touring"


def generate_pdf(
    gpx_file: str,
    output_file: str = "route.pdf",
    *,
    profile: str = DEFAULT_PROFILE,
    fuel_range: float | None = None,
    use_osm: bool = False,
    turn_style: str = "stylized",
    orientation: str = "landscape",
    paper: str = "letter",
    lanes_per_page: int = 4,
    decisions_per_lane: int = 4,
) -> str:
    """Generate a tank-bag navigation PDF from a GPX file.

    Args:
        gpx_file: Path to the input ``.gpx`` route or track.
        output_file: Path to write the rendered PDF to.
        profile: One of ``minimalist``, ``sport-touring``, ``rally``.
        fuel_range: Rider fuel range in miles, used for fuel-gap analysis.
        use_osm: Enrich with OpenStreetMap road names/fuel (needs the osm extra).
        turn_style: Strip bend style, ``"stylized"`` or ``"faithful"``.
        orientation: ``"landscape"`` (one big strip per page) or ``"portrait"``
            (several stacked strip lanes per page, roadbook-style).
        paper: Page size, ``"letter"`` or ``"a4"``.
        lanes_per_page: Portrait only -- number of strip lanes per page.
        decisions_per_lane: Portrait only -- max decisions per lane.

    Returns:
        The path to the written PDF.
    """
    from .pdf import generate_pdf as _generate_pdf

    return _generate_pdf(
        gpx_file,
        output_file,
        profile=profile,
        fuel_range=fuel_range,
        use_osm=use_osm,
        turn_style=turn_style,
        orientation=orientation,
        paper=paper,
        lanes_per_page=lanes_per_page,
        decisions_per_lane=decisions_per_lane,
    )


def analyze(
    gpx_file: str,
    *,
    profile: str = DEFAULT_PROFILE,
    fuel_range: float | None = None,
    reassurance_interval: float | None = None,
    use_osm: bool = False,
    include_hazards: bool = False,
) -> Route:
    """Run the route analysis engine on a GPX file.

    Loads the GPX, runs decision-point detection, reassurance-marker placement,
    fuel analysis and segmentation, and returns the populated :class:`Route`.
    ``include_hazards`` adds OSM hazard data for validation. See the ``analyze``
    output mode in ``PRODUCT.md``.
    """
    from .analysis import analyze_route as _analyze_route
    from .gpx import load_route as _load_route

    route = _load_route(gpx_file)
    return _analyze_route(
        route,
        profile=profile,
        fuel_range=fuel_range,
        reassurance_interval=reassurance_interval,
        use_osm=use_osm,
        include_hazards=include_hazards,
    )


def load_route(gpx_file: str, *, name: str | None = None) -> Route:
    """Load a GPX file into a :class:`Route` without running analysis."""
    from .gpx import load_route as _load_route

    return _load_route(gpx_file, name=name)


def analyze_route(route: Route, **kwargs) -> Route:
    """Run analysis on an already-loaded :class:`Route` (see :mod:`gpxsheet.analysis`)."""
    from .analysis import analyze_route as _analyze_route

    return _analyze_route(route, **kwargs)


def generate_strip(
    gpx_file: str,
    output_file: str = "route_strip.png",
    *,
    profile: str = DEFAULT_PROFILE,
    fuel_range: float | None = None,
    use_osm: bool = False,
    turn_style: str = "stylized",
) -> str:
    """Render a route to a schematic map-strip image."""
    from .strip import generate_strip as _generate_strip

    return _generate_strip(
        gpx_file,
        output_file,
        profile=profile,
        fuel_range=fuel_range,
        use_osm=use_osm,
        turn_style=turn_style,
    )
