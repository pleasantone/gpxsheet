"""GPXSheet — motorcycle sport-touring route awareness generator.

Public library API. See ``PRODUCT.md`` for the full design specification.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .models import Route

__version__ = "0.1.0"

__all__ = ["__version__", "generate_pdf", "analyze", "analyze_route", "load_route"]

DEFAULT_PROFILE = "sport-touring"


def generate_pdf(
    gpx_file: str,
    output_file: str = "route.pdf",
    *,
    profile: str = DEFAULT_PROFILE,
    fuel_range: float | None = None,
    reassurance_interval: float = 15.0,
) -> str:
    """Generate a tank-bag navigation PDF from a GPX file.

    Args:
        gpx_file: Path to the input ``.gpx`` route or track.
        output_file: Path to write the rendered PDF to.
        profile: One of ``minimalist``, ``sport-touring``, ``rally``.
        fuel_range: Rider fuel range in miles, used for fuel-gap analysis.
        reassurance_interval: Distance (miles) between reassurance markers.

    Returns:
        The path to the written PDF.
    """
    raise NotImplementedError(
        "PDF rendering pipeline is not implemented yet (see Milestone 3 in PRODUCT.md)."
    )


def analyze(
    gpx_file: str,
    *,
    profile: str = DEFAULT_PROFILE,
    fuel_range: float | None = None,
    reassurance_interval: float | None = None,
    use_osm: bool = False,
) -> Route:
    """Run the route analysis engine on a GPX file.

    Loads the GPX, runs decision-point detection, reassurance-marker placement,
    fuel analysis and segmentation, and returns the populated :class:`Route`.
    See the ``analyze`` output mode in ``PRODUCT.md``.
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
    )


def load_route(gpx_file: str, *, name: str | None = None) -> Route:
    """Load a GPX file into a :class:`Route` without running analysis."""
    from .gpx import load_route as _load_route

    return _load_route(gpx_file, name=name)


def analyze_route(route: Route, **kwargs) -> Route:
    """Run analysis on an already-loaded :class:`Route` (see :mod:`gpxsheet.analysis`)."""
    from .analysis import analyze_route as _analyze_route

    return _analyze_route(route, **kwargs)
