"""NIFC current wildfire perimeters near the route (keyless, Phase 2).

Queries the interagency (WFIGS) *current* perimeters ArcGIS feature service over
the route's bounding envelope, then intersects each returned polygon with the
route corridor (shapely) to report nearby fires with an approximate distance and
containment status. Perimeters are volatile and update on a delay -- this is a
planning hint, not a live operational feed.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..geo import METERS_PER_DEG_LAT, METERS_PER_MILE
from .base import Provider

# Only surface fires within this corridor distance (statute miles).
NEARBY_MILES = 50.0
# Rough statute miles per degree of latitude (good enough for a corridor hint).
_MILES_PER_DEG = METERS_PER_DEG_LAT / METERS_PER_MILE


@dataclass(slots=True)
class Fire:
    """A wildfire perimeter near the route."""

    name: str
    dist_mi: float
    status: str | None = None
    url: str | None = None


class FireProvider(Provider):
    """NIFC WFIGS current interagency perimeters (ArcGIS feature service)."""

    name = "nifc_fire"
    base_url_env = "GPXSHEET_NIFC_FIRE_BASE_URL"
    default_base_url = (
        "https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/"
        "WFIGS_Interagency_Perimeters_Current/FeatureServer/0/query"
    )


# Candidate attribute keys across NIFC schema revisions (first present wins).
_NAME_KEYS = ("poly_IncidentName", "attr_IncidentName", "IncidentName", "FireName")
_CONTAIN_KEYS = ("attr_PercentContained", "PercentContained")
_ACRES_KEYS = ("attr_IncidentSize", "poly_GISAcres", "GISAcres")


def _first(props: dict, keys: tuple[str, ...]) -> object | None:
    for k in keys:
        v = props.get(k)
        if v not in (None, ""):
            return v
    return None


def _status(props: dict) -> str | None:
    parts: list[str] = []
    acres = _first(props, _ACRES_KEYS)
    if isinstance(acres, (int, float)):
        parts.append(f"{round(acres):,} acres")
    contained = _first(props, _CONTAIN_KEYS)
    if isinstance(contained, (int, float)):
        parts.append(f"{round(contained)}% contained")
    return ", ".join(parts) if parts else None


def _bbox(
    coords: list[tuple[float, float]], pad_deg: float = 0.75
) -> tuple[float, float, float, float]:
    """``(xmin, ymin, xmax, ymax)`` envelope (lon/lat) around ``coords`` + padding."""
    lats = [lat for lat, _ in coords]
    lons = [lon for _, lon in coords]
    return (min(lons) - pad_deg, min(lats) - pad_deg, max(lons) + pad_deg, max(lats) + pad_deg)


def _distance_miles(line, poly) -> float:
    """Approximate route-to-perimeter distance in statute miles (0 if intersecting)."""
    return round(line.distance(poly) * _MILES_PER_DEG, 1)


def fetch_fires(coords: list[tuple[float, float]]) -> list[Fire] | None:
    """Current wildfire perimeters within :data:`NEARBY_MILES` of ``coords``.

    ``coords`` are the route's ``(lat, lon)`` points. Returns a distance-sorted
    list (possibly empty = "queried, none nearby"), or ``None`` when the lookup is
    unavailable (live disabled, no shapely, or the service failed).
    """
    prov = FireProvider()
    if not prov.available() or len(coords) < 2:
        return None
    try:
        import shapely.geometry as sg
    except ImportError:
        return None

    xmin, ymin, xmax, ymax = _bbox(coords)
    params = {
        "f": "geojson",
        "where": "1=1",
        "geometry": f"{xmin},{ymin},{xmax},{ymax}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "outFields": "*",
        "returnGeometry": "true",
    }
    payload = prov.get_json(params)
    if not isinstance(payload, dict):
        return None

    line = sg.LineString([(lon, lat) for lat, lon in coords])
    fires: list[Fire] = []
    for feat in payload.get("features") or []:
        if not isinstance(feat, dict):
            continue
        geom = feat.get("geometry")
        props = feat.get("properties") or {}
        if not geom:
            continue
        try:
            poly = sg.shape(geom)
        except (ValueError, TypeError, KeyError):
            continue
        dist = _distance_miles(line, poly)
        if dist > NEARBY_MILES:
            continue
        name = _first(props, _NAME_KEYS)
        fires.append(
            Fire(
                name=str(name).strip() if name else "Unnamed fire",
                dist_mi=dist,
                status=_status(props),
            )
        )
    fires.sort(key=lambda f: f.dist_mi)
    return fires
