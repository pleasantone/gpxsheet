"""GPXSheet — motorcycle sport-touring route awareness generator.

Public library API. See ``PRODUCT.md`` for the full design specification.
"""

from __future__ import annotations

__version__ = "0.1.0"

__all__ = ["__version__", "generate_pdf", "analyze"]

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


def analyze(gpx_file: str, *, profile: str = DEFAULT_PROFILE) -> dict:
    """Run the route analysis engine and return a structured summary.

    Returns a dict with decision points, fuel stops, reassurance markers and
    road segments. See the ``analyze`` output mode in ``PRODUCT.md``.
    """
    raise NotImplementedError(
        "Route analysis engine is not implemented yet (see Milestone 1 in PRODUCT.md)."
    )
