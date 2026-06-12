"""Open-Meteo weather at each day's sampled points (keyless, Phase 2).

One batched ``/v1/forecast`` call covers all of a day's sample points; for each
point we pick the forecast hour nearest its ETA. Values are stored imperial-ish
(°F, mph, inches, statute-mile visibility) and converted at render time, matching
the rest of the day card. Crosswind is *not* computed here -- the day card layer
combines ``wind_dir_deg`` with the route heading (see ``daycard._crosswind``).

Past Open-Meteo's ~16-day horizon the forecast is unavailable; the result then
carries an empty sample list and an explanatory ``note``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from ..geo import METERS_PER_MILE
from .base import HTTP_TIMEOUT_S, Provider, SamplePoint  # noqa: F401 - HTTP_TIMEOUT_S re-export

# Open-Meteo offers up to 16 days of hourly forecast.
FORECAST_HORIZON_DAYS = 16
_HOURLY_VARS = (
    "temperature_2m",
    "apparent_temperature",
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "precipitation_probability",
    "precipitation",
    "visibility",
    "weather_code",
)


@dataclass(slots=True)
class WeatherSample:
    """Forecast at one sampled point (imperial units; ``None`` where missing)."""

    mile: float
    time: datetime | None
    temp_f: float | None = None
    feels_f: float | None = None
    wind_mph: float | None = None
    gust_mph: float | None = None
    wind_dir_deg: float | None = None
    crosswind_mph: float | None = None  # filled by the day-card layer
    precip_prob: float | None = None  # percent
    precip_in: float | None = None
    visibility_mi: float | None = None
    code: int | None = None  # WMO weather code


@dataclass(slots=True)
class WeatherInfo:
    """A day's weather: per-point samples plus provenance / availability note."""

    samples: list[WeatherSample] = field(default_factory=list)
    source: str = "Open-Meteo"
    as_of: datetime | None = None
    note: str | None = None


class WeatherProvider(Provider):
    """Open-Meteo hourly forecast (keyless, global)."""

    name = "openmeteo_weather"
    base_url_env = "GPXSHEET_OPENMETEO_BASE_URL"
    default_base_url = "https://api.open-meteo.com/v1/forecast"


def _nearest_index(times: list[datetime], target: datetime) -> int | None:
    """Index of the forecast hour closest to ``target`` (both tz-aware UTC)."""
    if not times:
        return None
    return min(range(len(times)), key=lambda i: abs((times[i] - target).total_seconds()))


def _parse_times(raw: list[str]) -> list[datetime]:
    """Parse Open-Meteo ``hourly.time`` (UTC, no offset) to tz-aware datetimes."""
    out: list[datetime] = []
    for s in raw:
        try:
            out.append(datetime.fromisoformat(s).replace(tzinfo=UTC))
        except ValueError:
            continue
    return out


def _as_locations(payload: object) -> list[dict]:
    """Open-Meteo returns a list for multi-coord requests, an object for one."""
    if isinstance(payload, list):
        return [p for p in payload if isinstance(p, dict)]
    if isinstance(payload, dict):
        return [payload]
    return []


def _val(arr: object, i: int) -> float | None:
    if isinstance(arr, list) and 0 <= i < len(arr) and isinstance(arr[i], (int, float)):
        return float(arr[i])
    return None


def fetch_weather(points: list[SamplePoint], *, now: datetime | None = None) -> WeatherInfo | None:
    """Fetch hourly weather for the day's ``points`` (all tz-aware ETAs).

    Returns ``None`` when unavailable (live disabled, no ETAs, or fetch failed)
    so the card omits the section; a populated :class:`WeatherInfo` with a
    ``note`` and no samples when the day is beyond the forecast horizon.
    """
    prov = WeatherProvider()
    timed = [p for p in points if p.time is not None]
    if not prov.available() or not timed:
        return None

    now = now or datetime.now(UTC)
    horizon = now.timestamp() + FORECAST_HORIZON_DAYS * 86400
    if all(p.time.timestamp() > horizon for p in timed):  # type: ignore[union-attr]
        return WeatherInfo(
            note=f"beyond Open-Meteo's ~{FORECAST_HORIZON_DAYS}-day forecast horizon"
        )

    params = {
        "latitude": ",".join(f"{p.lat:.2f}" for p in timed),
        "longitude": ",".join(f"{p.lon:.2f}" for p in timed),
        "hourly": ",".join(_HOURLY_VARS),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "precipitation_unit": "inch",
        "timezone": "UTC",
        "forecast_days": FORECAST_HORIZON_DAYS,
    }
    payload = prov.get_json(params)
    locations = _as_locations(payload)
    if not locations:
        return None

    samples: list[WeatherSample] = []
    for p, loc in zip(timed, locations, strict=False):
        hourly = loc.get("hourly") or {}
        times = _parse_times(hourly.get("time") or [])
        target = p.time.astimezone(UTC)  # type: ignore[union-attr]
        idx = _nearest_index(times, target)
        if idx is None:
            continue
        vis_m = _val(hourly.get("visibility"), idx)
        code = _val(hourly.get("weather_code"), idx)
        samples.append(
            WeatherSample(
                mile=p.mile,
                time=p.time,
                temp_f=_val(hourly.get("temperature_2m"), idx),
                feels_f=_val(hourly.get("apparent_temperature"), idx),
                wind_mph=_val(hourly.get("wind_speed_10m"), idx),
                gust_mph=_val(hourly.get("wind_gusts_10m"), idx),
                wind_dir_deg=_val(hourly.get("wind_direction_10m"), idx),
                precip_prob=_val(hourly.get("precipitation_probability"), idx),
                precip_in=_val(hourly.get("precipitation"), idx),
                visibility_mi=(vis_m / METERS_PER_MILE if vis_m is not None else None),
                code=int(code) if code is not None else None,
            )
        )
    if not samples:
        return None
    return WeatherInfo(samples=samples, as_of=now)
