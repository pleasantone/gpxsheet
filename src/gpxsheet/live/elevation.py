"""Open-Meteo Elevation fallback when the GPX has no usable ``ele`` (Phase 2).

Most GPX tracks carry elevation; this only fills the gap when they don't. One
batched ``/v1/elevation`` call (≤100 coords) over evenly-spaced route points
yields a coarse min/max/gain -- enough for the day card's "big climbing day"
read, explicitly marked as a (coarser) DEM-derived estimate.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geo import M_TO_FT
from .base import Provider

# Open-Meteo elevation accepts up to 100 coordinates per request.
MAX_COORDS = 100


@dataclass(slots=True)
class ElevationProfile:
    """Coarse elevation summary (feet) and where it came from."""

    min_ft: float | None = None
    max_ft: float | None = None
    gain_ft: float | None = None
    source: str = "gpx"  # "gpx" | "Open-Meteo (DEM, approx)"


class ElevationProvider(Provider):
    """Open-Meteo digital-elevation lookup (keyless, global)."""

    name = "openmeteo_elevation"
    base_url_env = "GPXSHEET_OPENMETEO_ELEVATION_BASE_URL"
    default_base_url = "https://api.open-meteo.com/v1/elevation"


def fetch_elevation(coords: list[tuple[float, float]]) -> ElevationProfile | None:
    """Min/max/gain (ft) over ``coords`` (lat, lon) from the DEM; ``None`` if down."""
    prov = ElevationProvider()
    if not prov.available() or len(coords) < 2:
        return None
    params = {
        "latitude": ",".join(f"{lat:.4f}" for lat, _ in coords),
        "longitude": ",".join(f"{lon:.4f}" for _, lon in coords),
    }
    payload = prov.get_json(params)
    if not isinstance(payload, dict):
        return None
    eles = payload.get("elevation")
    metres = (
        [float(e) for e in eles if isinstance(e, (int, float))] if isinstance(eles, list) else []
    )
    if len(metres) < 2:
        return None
    gain_m = sum(max(0.0, b - a) for a, b in zip(metres, metres[1:], strict=False))
    return ElevationProfile(
        min_ft=round(min(metres) * M_TO_FT),
        max_ft=round(max(metres) * M_TO_FT),
        gain_ft=round(gain_m * M_TO_FT),
        source="Open-Meteo (DEM, approx)",
    )
