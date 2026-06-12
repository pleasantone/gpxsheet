"""Open-Meteo Air-Quality at each day's sampled points (keyless, Phase 2).

Reports the day's worst US AQI and PM2.5 along the route and a coarse ``smoke``
flag (elevated fine particulate -- the usual wildfire-smoke signature). AirNow
(key-gated, US-only, often fresher for active smoke) is Phase 3.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from .base import Provider, SamplePoint
from .weather import _as_locations, _nearest_index, _parse_times, _val

# PM2.5 (µg/m³) at/above which we flag likely smoke; ~"unhealthy for sensitive".
SMOKE_PM25 = 35.0
SMOKE_AQI = 100


@dataclass(slots=True)
class AirInfo:
    """A day's air-quality summary (worst point along the route)."""

    max_aqi: int | None = None
    max_pm25: float | None = None
    smoke: bool = False
    source: str = "Open-Meteo Air-Quality"
    as_of: datetime | None = None
    note: str | None = None


class AirProvider(Provider):
    """Open-Meteo air-quality (keyless, global)."""

    name = "openmeteo_air"
    base_url_env = "GPXSHEET_OPENMETEO_AIR_BASE_URL"
    default_base_url = "https://air-quality-api.open-meteo.com/v1/air-quality"


def fetch_air(points: list[SamplePoint], *, now: datetime | None = None) -> AirInfo | None:
    """Fetch air quality for the day's ``points``; ``None`` when unavailable."""
    prov = AirProvider()
    timed = [p for p in points if p.time is not None]
    if not prov.available() or not timed:
        return None

    params = {
        "latitude": ",".join(f"{p.lat:.2f}" for p in timed),
        "longitude": ",".join(f"{p.lon:.2f}" for p in timed),
        "hourly": "us_aqi,pm2_5",
        "timezone": "UTC",
    }
    payload = prov.get_json(params)
    locations = _as_locations(payload)
    if not locations:
        return None

    aqis: list[float] = []
    pms: list[float] = []
    for p, loc in zip(timed, locations, strict=False):
        hourly = loc.get("hourly") or {}
        times = _parse_times(hourly.get("time") or [])
        idx = _nearest_index(times, p.time.astimezone(UTC))  # type: ignore[union-attr]
        if idx is None:
            continue
        aqi = _val(hourly.get("us_aqi"), idx)
        pm = _val(hourly.get("pm2_5"), idx)
        if aqi is not None:
            aqis.append(aqi)
        if pm is not None:
            pms.append(pm)
    if not aqis and not pms:
        return None

    max_aqi = int(max(aqis)) if aqis else None
    max_pm = round(max(pms), 1) if pms else None
    smoke = (max_pm is not None and max_pm >= SMOKE_PM25) or (
        max_aqi is not None and max_aqi >= SMOKE_AQI
    )
    return AirInfo(
        max_aqi=max_aqi,
        max_pm25=max_pm,
        smoke=smoke,
        as_of=now or datetime.now(UTC),
    )
