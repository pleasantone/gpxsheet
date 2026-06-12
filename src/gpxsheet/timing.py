"""ETA / layover / fuel-distance and sunrise-sunset math for the route table.

The temporal layer GPXsheet's analysis pipeline lacks. Pure functions over an
ordered list of stops (cumulative distance + layover + fuel-reset), producing per
-stop arrival times, distance-since-fuel and total distance. The first and last
stop take no layover (matching GPXtable).

Travel time comes from a :class:`SpeedProfile`: either a single flat speed
(GPXtable's model, or a user-supplied ``--speed``) or a piecewise-constant
profile built from OSM speed limits (:data:`Route.speed_samples_mph`), giving
variable ETAs across a mixed interstate/backroad route.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo

from .geo import meters_to_miles


def travel_time(distance_m: float, speed_kph: float) -> timedelta:
    """Time to cover ``distance_m`` metres at ``speed_kph`` (km/h)."""
    if speed_kph <= 0:
        return timedelta()
    return timedelta(minutes=distance_m / 1000.0 / speed_kph * 60.0)


@dataclass(frozen=True, slots=True)
class SpeedProfile:
    """Piecewise-constant travel speed along the route, in **mph** over miles.

    ``breakpoints`` are ``(start_mile, mph)`` sorted ascending, the first at mile
    0; each holds until the next. A flat profile is a single breakpoint.
    """

    breakpoints: tuple[tuple[float, float], ...]

    @classmethod
    def flat(cls, mph: float) -> SpeedProfile:
        return cls(((0.0, max(mph, 0.0)),))

    @classmethod
    def from_breakpoints_mph(cls, bps: list[tuple[float, float]]) -> SpeedProfile:
        """Build a profile from ``(mile, mph)`` pairs, ensuring mile-0 coverage."""
        pts = sorted((float(m), float(s)) for m, s in bps if s and s > 0)
        if not pts:
            return cls.flat(0.0)
        if pts[0][0] > 0.0:
            pts = [(0.0, pts[0][1]), *pts]
        return cls(tuple(pts))

    def time_to(self, mile: float) -> timedelta:
        """Travel time from the start to ``mile`` (integrating 1/speed)."""
        if mile <= 0:
            return timedelta()
        hours = 0.0
        bps = self.breakpoints
        for i, (start, mph) in enumerate(bps):
            end = bps[i + 1][0] if i + 1 < len(bps) else float("inf")
            lo, hi = max(start, 0.0), min(end, mile)
            if hi > lo and mph > 0:
                hours += (hi - lo) / mph
        return timedelta(hours=hours)

    def average_mph(self, length_miles: float) -> float:
        """Overall average mph across ``length_miles`` (0 if it takes no time)."""
        hours = self.time_to(length_miles).total_seconds() / 3600.0
        return length_miles / hours if hours > 0 else 0.0

    def slice(self, start_mile: float, end_mile: float) -> SpeedProfile:
        """The sub-profile over ``[start_mile, end_mile]`` rebased to mile 0.

        Used to give a per-day route slice its own day-relative speed profile.
        """
        out: list[tuple[float, float]] = []
        bps = self.breakpoints
        for i, (start, mph) in enumerate(bps):
            seg_end = bps[i + 1][0] if i + 1 < len(bps) else float("inf")
            if seg_end <= start_mile or start >= end_mile:
                continue
            out.append((max(start - start_mile, 0.0), mph))
        return SpeedProfile.from_breakpoints_mph(out) if out else SpeedProfile.flat(0.0)


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
    speed: SpeedProfile,
) -> list[StopTiming]:
    """Resolve arrival/layover/fuel-distance for an ordered list of stops.

    Arrival at stop *i* is ``departure + speed.time_to(total_i) + (sum of layovers
    of stops before i)``. The first and last stop take no layover (matching
    GPXtable). ``since_gas_m`` resets to 0 after a ``fuel_reset`` stop. Distances
    are measured from the start of ``stops`` (a per-day slice rebases its own
    distances + speed profile to 0).
    """
    n = len(stops)
    cumulative_layover = timedelta()
    last_gas_m = 0.0
    out: list[StopTiming] = []
    for i, stop in enumerate(stops):
        is_edge = i == 0 or i == n - 1
        layover = timedelta() if is_edge else stop.delay
        ride = speed.time_to(meters_to_miles(stop.distance_m))
        arrival = (
            departure + ride + cumulative_layover if departure is not None else None
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
