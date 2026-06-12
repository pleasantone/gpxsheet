"""ETA / layover / fuel-distance and sunrise-sunset math for the route table.

The temporal layer GPXsheet's analysis pipeline lacks. Pure functions over an
ordered list of stops (cumulative distance + layover + fuel-reset), producing per
-stop arrival times, distance-since-fuel and total distance. The model mirrors
GPXtable's (a single flat travel speed; the first and last stop take no layover)
so the native table matches GPXtable's ETAs.

Per-segment speed from OSM ``maxspeed``/road class is a deliberate later
enhancement -- :data:`compute_timings` takes one ``speed_kph`` for now.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo


def travel_time(distance_m: float, speed_kph: float) -> timedelta:
    """Time to cover ``distance_m`` metres at ``speed_kph`` (km/h)."""
    if speed_kph <= 0:
        return timedelta()
    return timedelta(minutes=distance_m / 1000.0 / speed_kph * 60.0)


@dataclass(frozen=True, slots=True)
class StopInput:
    """One ordered stop fed to :func:`compute_timings`.

    ``distance_m`` is cumulative metres from the route start; ``delay`` is the
    requested layover; ``fuel_reset`` zeroes the distance-since-fuel counter.
    """

    distance_m: float
    delay: timedelta = timedelta()
    fuel_reset: bool = False


@dataclass(frozen=True, slots=True)
class StopTiming:
    """Resolved timing for one stop.

    ``arrival`` is ``None`` when no departure was given. ``layover`` is what was
    actually applied (zero for the first and last stop). ``since_gas_m`` is the
    distance ridden since the last fuel reset; ``total_m`` echoes the cumulative
    distance.
    """

    arrival: datetime | None
    layover: timedelta
    since_gas_m: float
    total_m: float


def compute_timings(
    stops: list[StopInput],
    *,
    departure: datetime | None,
    speed_kph: float,
) -> list[StopTiming]:
    """Resolve arrival/layover/fuel-distance for an ordered list of stops.

    Arrival at stop *i* is ``departure + travel_time(total_i) + (sum of layovers
    of stops before i)``. The first and last stop take no layover (matching
    GPXtable). ``since_gas_m`` resets to 0 after a ``fuel_reset`` stop.
    """
    n = len(stops)
    cumulative_layover = timedelta()
    last_gas_m = 0.0
    out: list[StopTiming] = []
    for i, stop in enumerate(stops):
        is_edge = i == 0 or i == n - 1
        layover = timedelta() if is_edge else stop.delay
        arrival = (
            departure + travel_time(stop.distance_m, speed_kph) + cumulative_layover
            if departure is not None
            else None
        )
        out.append(
            StopTiming(
                arrival=arrival,
                layover=layover,
                since_gas_m=stop.distance_m - last_gas_m,
                total_m=stop.distance_m,
            )
        )
        cumulative_layover += layover
        if stop.fuel_reset:
            last_gas_m = stop.distance_m
    return out


def sun_times(
    start_lat: float,
    start_lon: float,
    start_time: datetime | None,
    end_lat: float,
    end_lon: float,
    end_time: datetime | None,
) -> dict[str, datetime] | None:
    """Sunrise (at the start), sunset (at the end) plus the start/end times.

    Returns a ``{"Sunrise", "Sunset", "Starts", "Ends"}`` mapping the caller can
    sort and format, or ``None`` if either endpoint has no time. Mirrors
    GPXtable's ``_sun_rise_set``.
    """
    if start_time is None or end_time is None:
        return None
    import astral
    import astral.sun

    def observer(lat: float, lon: float):
        return astral.LocationInfo("", "", "", lat, lon).observer

    sun_start = astral.sun.sun(observer(start_lat, start_lon), date=start_time)
    sun_end = astral.sun.sun(observer(end_lat, end_lon), date=end_time)
    return {
        "Sunrise": sun_start["sunrise"],
        "Sunset": sun_end["sunset"],
        "Starts": start_time,
        "Ends": end_time,
    }


def format_sun_line(times: dict[str, datetime], tz: tzinfo | None) -> str:
    """Render the sun/almanac line: ``MM/DD/YY: Sunrise: …, Starts: …`` (sorted)."""
    start = times["Starts"]
    parts = ", ".join(
        f"{name}: {when.astimezone(tz):%H:%M}"
        for name, when in sorted(times.items(), key=lambda kv: kv[1])
    )
    return f"{start.astimezone(tz):%x}: {parts}"
