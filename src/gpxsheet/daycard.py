"""Day cards: a per-day, read-ahead briefing for a touring rider.

Unlike the tank-bag *sheet* (:mod:`gpxsheet.pdf`) and *table*
(:mod:`gpxsheet.routetable`) -- which the rider glances at while riding -- a day
card is a *planning-time* summary read the night before: how long the day is, when
the sun sets and whether you'll be caught out after dark, the passes and scenic
stops, and any cautions (gravel, construction, wildlife, long no-services gaps).
One card per day (``Route.day_breaks``/``day_names``).

Most of the card is computed from the already-analyzed
:class:`~gpxsheet.models.Route` plus a best-effort OSM points-of-interest query
(passes / viewpoints / construction / wildlife) that degrades to empty when OSM is
unavailable. **Phase 2** adds keyless live conditions from :mod:`gpxsheet.live`
(Open-Meteo weather with crosswind, air-quality/smoke, an elevation DEM fallback,
NIFC wildfire) behind ``live=``; each source degrades to ``None`` independently.
Key-gated sources and cell coverage are Phase 3; see ``docs/day-cards-design.md``.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, tzinfo
from pathlib import Path
from typing import Any

from . import perf
from .geo import (
    KM_PER_MILE,
    M_TO_FT,
    METERS_PER_DEG_LAT,
    bearing,
    bearing_delta,
    haversine,
    meters_to_miles,
    miles_to_meters,
)
from .live import (
    AirInfo,
    ElevationProfile,
    Fire,
    SamplePoint,
    WeatherInfo,
    WeatherSample,
    fetch_air,
    fetch_elevation,
    fetch_fires,
    fetch_weather,
)
from .models import Route, RouteSpan, SpanKind
from .timing import SpeedProfile, observer
from .validate import INFO, WARNING, Finding

# Default cruising speed (mph) when OSM gave no speed profile and none was set.
DEFAULT_SPEED_MPH = 30.0
# Thresholds for the per-day cautions.
LONG_DAY_HOURS = 8.0
LONG_DAY_MILES = 400.0
BIG_CLIMB_FT = 6000.0
GRAVEL_WARN_MILES = 0.2
# A no-services gap longer than this (and longer than the rider's range, if given)
# is worth flagging.
SERVICE_GAP_MILES = 60.0

# Live-weather sampling + warning thresholds (imperial; see build_day_cards).
SAMPLE_SPACING_MILES = 27.5
HIGH_WIND_MPH = 25.0
HIGH_GUST_MPH = 35.0
HIGH_CROSSWIND_MPH = 20.0
HOT_F = 95.0
COLD_F = 40.0
WET_PROB_PCT = 50.0
# Max coordinates in one Open-Meteo elevation batch (matches the provider cap).
ELEV_SAMPLE_MAX = 100

# Output formats accepted by render_day_cards.
DAYCARD_FORMATS = ("markdown", "html", "json")


@dataclass(slots=True)
class Pass:
    """A mountain pass / summit the route crosses."""

    name: str
    mile: float
    elevation_ft: float | None = None


@dataclass(slots=True)
class POI:
    """A scenic/notable point near the route (viewpoint, peak, attraction)."""

    name: str
    mile: float
    kind: str  # "viewpoint" | "peak" | "attraction" | "wildlife" | ...


@dataclass(slots=True)
class ServiceGap:
    """A stretch with no fuel/services."""

    start_mile: float
    end_mile: float

    @property
    def miles(self) -> float:
        return round(self.end_mile - self.start_mile, 1)


@dataclass(slots=True)
class SunInfo:
    """Daylight summary for a day (all tz-aware, rendered in the display tz)."""

    sunrise: datetime | None = None
    sunset: datetime | None = None
    golden_morning_end: datetime | None = None
    golden_evening_start: datetime | None = None
    after_dark: bool = False
    dark_from_mile: float | None = None


@dataclass(slots=True)
class DayCard:
    """One day's read-ahead briefing."""

    index: int  # 0-based
    name: str
    date: datetime | None
    start_mile: float
    end_mile: float
    miles: float
    moving_time: timedelta | None
    arrive: datetime | None
    elevation_gain_ft: float | None = None
    elevation_max_ft: float | None = None
    passes: list[Pass] = field(default_factory=list)
    scenic: list[POI] = field(default_factory=list)
    construction: list[POI] = field(default_factory=list)
    wildlife: list[POI] = field(default_factory=list)
    gravel: list[RouteSpan] = field(default_factory=list)
    no_services: list[ServiceGap] = field(default_factory=list)
    sun: SunInfo | None = None
    # Phase 2 live data (None = not fetched / unavailable).
    weather: WeatherInfo | None = None
    air: AirInfo | None = None
    fire: list[Fire] = field(default_factory=list)
    elevation_profile: ElevationProfile | None = None
    warnings: list[Finding] = field(default_factory=list)
    attributions: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """A JSON-serializable view (datetimes -> ISO, timedelta -> minutes)."""

        def iso(dt: datetime | None) -> str | None:
            return dt.isoformat() if dt else None

        out = asdict(self)
        out["date"] = iso(self.date)
        out["arrive"] = iso(self.arrive)
        out["moving_minutes"] = (
            round(self.moving_time.total_seconds() / 60) if self.moving_time else None
        )
        out.pop("moving_time")
        if self.sun:
            out["sun"] = {
                "sunrise": iso(self.sun.sunrise),
                "sunset": iso(self.sun.sunset),
                "golden_morning_end": iso(self.sun.golden_morning_end),
                "golden_evening_start": iso(self.sun.golden_evening_start),
                "after_dark": self.sun.after_dark,
                "dark_from_mile": self.sun.dark_from_mile,
            }
        if self.weather:
            out["weather"] = {
                "source": self.weather.source,
                "as_of": iso(self.weather.as_of),
                "note": self.weather.note,
                "samples": [
                    {**asdict(s), "time": iso(s.time)} for s in self.weather.samples
                ],
            }
        if self.air:
            out["air"] = asdict(self.air)
            out["air"]["as_of"] = iso(self.air.as_of)
        out["warnings"] = [
            {"level": w.level, "code": w.code, "message": w.message} for w in self.warnings
        ]
        return out


# ---------------------------------------------------------------------------
# Geometry / timing helpers (pure)
# ---------------------------------------------------------------------------


def _speed_profile(route: Route, speed: float) -> SpeedProfile:
    """A flat user speed, else the OSM speed-limit profile, else 30 mph."""
    if speed > 0:
        return SpeedProfile.flat(speed)
    if route.speed_samples_mph:
        return SpeedProfile.from_breakpoints_mph(route.speed_samples_mph)
    return SpeedProfile.flat(DEFAULT_SPEED_MPH)


def _point_bounds(route: Route) -> list[int]:
    """Point-index boundaries ``[0, break1, …, last]`` from ``route.day_breaks``."""
    return [0, *route.day_breaks, len(route.points) - 1]


def _mile_bounds(route: Route) -> list[float]:
    """Mile boundaries ``[0, break1, …, length]`` from ``route.day_breaks``."""
    breaks = [meters_to_miles(route.distances_m[i]) for i in route.day_breaks]
    return [0.0, *breaks, route.length_miles]


def _nearest_mile(route: Route, lat: float, lon: float) -> float:
    """Route mile of the vertex nearest ``(lat, lon)``."""
    i = min(
        range(len(route.points)),
        key=lambda k: haversine(route.points[k].lat, route.points[k].lon, lat, lon),
    )
    return round(meters_to_miles(route.distances_m[i]), 1)


def _elevation(route: Route, i0: int, i1: int) -> tuple[float | None, float | None]:
    """``(gain_ft, max_ft)`` over point indices ``[i0, i1]`` from GPX elevation.

    Returns ``(None, None)`` when the track carries no usable elevation.
    """
    eles = [p.ele for p in route.points[i0 : i1 + 1] if p.ele is not None]
    if len(eles) < 2:
        return None, None
    gain_m = sum(max(0.0, b - a) for a, b in zip(eles, eles[1:], strict=False))
    return round(gain_m * M_TO_FT), round(max(eles) * M_TO_FT)


def _service_gaps(
    route: Route, start_mi: float, end_mi: float, threshold: float
) -> list[ServiceGap]:
    """No-fuel stretches within ``[start_mi, end_mi]`` longer than ``threshold``."""
    stops = sorted(
        fs.mile for fs in route.fuel_stops if start_mi <= fs.mile <= end_mi
    )
    marks = [start_mi, *stops, end_mi]
    return [
        ServiceGap(round(a, 1), round(b, 1))
        for a, b in zip(marks, marks[1:], strict=False)
        if b - a > threshold
    ]


def _after_dark(
    profile: SpeedProfile, depart: datetime, sunset: datetime | None, day_miles: float
) -> tuple[bool, float | None]:
    """Whether the day's ride finishes after sunset, and from what mile it's dark.

    Scans the day in coarse steps and returns the first mile whose ETA is past
    ``sunset``. ``(False, None)`` if there's no sunset or the day ends in daylight.
    """
    if sunset is None:
        return False, None
    if depart + profile.time_to(day_miles) <= sunset:
        return False, None
    steps = max(2, int(day_miles))
    for s in range(steps + 1):
        mile = day_miles * s / steps
        if depart + profile.time_to(mile) >= sunset:
            return True, round(mile, 1)
    return True, None


def _sun_event(lat: float, lon: float, date: datetime, event: str) -> datetime | None:
    """``sunrise``/``sunset`` (etc.) for ``date`` at ``(lat, lon)``, best-effort."""
    try:
        import astral.sun

        return astral.sun.sun(observer(lat, lon), date=date)[event]
    except Exception:  # noqa: BLE001 - almanac is decorative; never break the card
        return None


def _golden_hours(
    lat: float, lon: float, date: datetime
) -> tuple[datetime | None, datetime | None]:
    """``(morning_golden_end, evening_golden_start)`` for the day, best-effort."""
    try:
        import astral.sun

        obs = observer(lat, lon)
        morning = astral.sun.golden_hour(obs, date=date, direction=astral.sun.SunDirection.RISING)
        evening = astral.sun.golden_hour(obs, date=date, direction=astral.sun.SunDirection.SETTING)
        return morning[1], evening[0]
    except Exception:  # noqa: BLE001 - almanac is decorative; never break the card
        return None, None


# ---------------------------------------------------------------------------
# Live-data sampling (Phase 2): weather / air / elevation / fire
# ---------------------------------------------------------------------------


def _interp_latlon(route: Route, target_m: float) -> tuple[float, float]:
    """Interpolated ``(lat, lon)`` at cumulative distance ``target_m`` along route."""
    dists = route.distances_m
    pts = route.points
    if target_m <= 0 or len(pts) < 2:
        return pts[0].lat, pts[0].lon
    if target_m >= dists[-1]:
        return pts[-1].lat, pts[-1].lon
    # Linear scan is fine: a handful of samples per day.
    j = next(k for k in range(len(dists) - 1) if dists[k + 1] >= target_m)
    span = dists[j + 1] - dists[j]
    t = (target_m - dists[j]) / span if span > 0 else 0.0
    a, b = pts[j], pts[j + 1]
    return a.lat + t * (b.lat - a.lat), a.lon + t * (b.lon - a.lon)


def _heading_at(route: Route, target_m: float) -> float | None:
    """Route bearing (deg) through the point at cumulative distance ``target_m``."""
    pts = route.points
    if len(pts) < 2:
        return None
    dists = route.distances_m
    j = next((k for k in range(len(dists) - 1) if dists[k + 1] >= target_m), len(pts) - 2)
    a, b = pts[j], pts[j + 1]
    return bearing(a.lat, a.lon, b.lat, b.lon)


def _crosswind(
    heading: float | None, wind_from_deg: float | None, wind_mph: float | None
) -> float | None:
    """Crosswind component (mph): ``|wind * sin(Δ)|`` between heading and wind-from."""
    if heading is None or wind_from_deg is None or wind_mph is None:
        return None
    delta = math.radians(bearing_delta(heading, wind_from_deg))
    return round(abs(wind_mph * math.sin(delta)), 1)


def _day_samples(
    route: Route,
    start_mi: float,
    end_mi: float,
    depart_day: datetime | None,
    day_profile: SpeedProfile,
) -> list[SamplePoint]:
    """Sample points every ~:data:`SAMPLE_SPACING_MILES` across the day, with ETAs."""
    day_miles = end_mi - start_mi
    n = max(1, round(day_miles / SAMPLE_SPACING_MILES))
    miles = [start_mi + day_miles * i / n for i in range(n + 1)]
    out: list[SamplePoint] = []
    for m in miles:
        lat, lon = _interp_latlon(route, miles_to_meters(m))
        time = depart_day + day_profile.time_to(m - start_mi) if depart_day else None
        out.append(SamplePoint(round(m, 1), lat, lon, time, _heading_at(route, miles_to_meters(m))))
    return out


def _day_coords(route: Route, i0: int, i1: int, max_n: int) -> list[tuple[float, float]]:
    """Up to ``max_n`` evenly-spaced ``(lat, lon)`` over point indices ``[i0, i1]``."""
    span = i1 - i0
    if span <= 0:
        return []
    step = max(1, span // max_n)
    idxs = list(range(i0, i1 + 1, step))
    if idxs[-1] != i1:
        idxs.append(i1)
    return [(route.points[k].lat, route.points[k].lon) for k in idxs]


def _day_weather(samples: list[SamplePoint]) -> WeatherInfo | None:
    """Fetch weather for the day's samples and fill each one's crosswind."""
    info = fetch_weather(samples)
    if info is None:
        return None
    by_mile = {round(s.mile, 1): s for s in samples}
    for ws in info.samples:
        sp = by_mile.get(round(ws.mile, 1))
        heading = sp.heading if sp else None
        ws.crosswind_mph = _crosswind(heading, ws.wind_dir_deg, ws.wind_mph)
    return info


def _live_elevation(
    route: Route, i0: int, i1: int, gpx_gain_ft: float | None
) -> ElevationProfile | None:
    """Open-Meteo elevation fallback, only when the GPX carried no usable ``ele``."""
    if gpx_gain_ft is not None:
        return None
    coords = _day_coords(route, i0, i1, ELEV_SAMPLE_MAX)
    return fetch_elevation(coords)


# ---------------------------------------------------------------------------
# OSM points of interest (best-effort; degrades to empty without OSM)
# ---------------------------------------------------------------------------

# One combined Overpass features query for everything the card marks.
_POI_TAGS: dict[str, Any] = {
    "mountain_pass": "yes",
    "tourism": ["viewpoint", "attraction"],
    "natural": "peak",
    "highway": "construction",
    "hazard": "animal_crossing",
}


def _classify_pois(rows: list[dict[str, Any]], route: Route) -> dict[str, list]:
    """Sort raw OSM feature rows into passes / scenic / construction / wildlife.

    ``rows`` are plain dicts (``name``, ``lat``, ``lon``, ``ele`` plus the matched
    OSM tag keys) so this stays pure and unit-testable without geopandas.
    """
    passes: list[Pass] = []
    scenic: list[POI] = []
    construction: list[POI] = []
    wildlife: list[POI] = []
    for r in rows:
        name = (r.get("name") or "").strip()
        mile = _nearest_mile(route, r["lat"], r["lon"])
        is_scenic = r.get("tourism") in ("viewpoint", "attraction") or r.get("natural") == "peak"
        if r.get("mountain_pass") == "yes":
            passes.append(Pass(name or "pass", mile, _ele_to_ft(r.get("ele"))))
        elif r.get("highway") == "construction":
            construction.append(POI(name or "construction", mile, "construction"))
        elif r.get("hazard") == "animal_crossing":
            wildlife.append(POI(name or "wildlife crossing", mile, "wildlife"))
        elif name and is_scenic:
            kind = "peak" if r.get("natural") == "peak" else str(r.get("tourism"))
            scenic.append(POI(name, mile, kind))
    passes.sort(key=lambda p: p.mile)
    for lst in (scenic, construction, wildlife):
        lst.sort(key=lambda p: p.mile)
    return {"passes": passes, "scenic": scenic, "construction": construction, "wildlife": wildlife}


def _ele_to_ft(ele: Any) -> float | None:
    """OSM ``ele`` (metres, possibly missing/non-numeric) as feet, or None."""
    try:
        return round(float(ele) * M_TO_FT)
    except (TypeError, ValueError):
        return None


def _collect_pois(route: Route, road_buffer_m: float = 200.0) -> dict[str, list]:
    """Query OSM for card POIs along the route corridor; ``{}`` if unavailable.

    Best-effort: a single ``features_from_polygon`` call (like
    ``enrich._detect_ferries``), normalized to plain dicts and classified by
    :func:`_classify_pois`. Any failure (osmnx missing, Overpass down, offline
    cache miss) degrades to empty so the rest of the card still renders.
    """
    try:
        import osmnx as ox
        import shapely.geometry as sg

        line = sg.LineString([(p.lon, p.lat) for p in route.points])
        corridor = line.buffer(road_buffer_m / METERS_PER_DEG_LAT)  # ~deg per metre
        feats = ox.features_from_polygon(corridor, tags=_POI_TAGS)
        if feats.empty:
            return {}
        rows: list[dict[str, Any]] = []
        for _, row in feats.iterrows():
            geom = row.geometry
            c = geom.centroid
            rows.append(
                {
                    "name": row.get("name"),
                    "lat": c.y,
                    "lon": c.x,
                    "ele": row.get("ele"),
                    "mountain_pass": row.get("mountain_pass"),
                    "tourism": row.get("tourism"),
                    "natural": row.get("natural"),
                    "highway": row.get("highway"),
                    "hazard": row.get("hazard"),
                }
            )
        return _classify_pois(rows, route)
    except Exception:  # noqa: BLE001 - POIs are additive; never break the card
        return {}


# ---------------------------------------------------------------------------
# Card builder
# ---------------------------------------------------------------------------


def build_day_cards(
    route: Route,
    *,
    departure: datetime | None = None,
    tz: tzinfo | None = None,
    imperial: bool = True,
    speed: float = 0.0,
    fuel_range: float | None = None,
    osm: bool = True,
    live: bool = True,
) -> list[DayCard]:
    """Build one :class:`DayCard` per day of ``route``.

    ``departure`` (with the day rolling +24h, like the route table) enables the
    sun / golden-hour / after-dark sections and the weather/air-quality lookups
    (which need an ETA); without it those are skipped. ``osm`` gates the best-
    effort POI query; ``live`` gates the keyless live providers (Open-Meteo
    weather/air/elevation + NIFC wildfire), which also honor
    ``GPXSHEET_DISABLE_LIVE`` and degrade gracefully when offline. ``imperial``
    only affects rendering, not the stored values (which are imperial-ish: miles,
    feet, °F, mph).
    """
    profile = _speed_profile(route, speed)
    pbounds = _point_bounds(route)
    mbounds = _mile_bounds(route)
    multiday = len(route.day_breaks) > 0
    gap_threshold = min(SERVICE_GAP_MILES, fuel_range) if fuel_range else SERVICE_GAP_MILES

    with perf.span("daycard.pois"):
        pois = _collect_pois(route) if osm else {}

    cards: list[DayCard] = []
    for d in range(len(mbounds) - 1):
        start_mi, end_mi = mbounds[d], mbounds[d + 1]
        i0, i1 = pbounds[d], pbounds[d + 1]
        day_miles = round(end_mi - start_mi, 1)
        day_profile = profile.slice(start_mi, end_mi) if multiday else profile
        moving = day_profile.time_to(day_miles)
        depart_day = departure + timedelta(days=d) if departure else None
        arrive = depart_day + moving if depart_day else None

        gain_ft, max_ft = _elevation(route, i0, i1)
        gravel = [
            s for s in route.spans
            if s.kind == SpanKind.UNPAVED and s.start_mile < end_mi and s.end_mile > start_mi
        ]
        services = _service_gaps(route, start_mi, end_mi, gap_threshold)
        sun = _day_sun(route, i0, i1, depart_day, day_profile, day_miles)

        weather = air = elevation = None
        fires: list[Fire] = []
        if live:
            samples = _day_samples(route, start_mi, end_mi, depart_day, day_profile)
            # Each provider is a network round-trip; instrument so the perf line
            # shows which source costs the time (spans repeat per day on a
            # multi-day route, and are ~free outside a perf.track).
            with perf.span("daycard.weather"):
                weather = _day_weather(samples)
            with perf.span("daycard.air"):
                air = fetch_air(samples)
            with perf.span("daycard.elevation"):
                elevation = _live_elevation(route, i0, i1, gain_ft)
            with perf.span("daycard.fire"):
                fires = fetch_fires(_day_coords(route, i0, i1, ELEV_SAMPLE_MAX)) or []

        if elevation is not None:  # GPX had no usable elevation; use the DEM fallback
            gain_ft, max_ft = elevation.gain_ft, elevation.max_ft

        card = DayCard(
            index=d,
            name=route.day_names[d] if d < len(route.day_names) else "",
            date=depart_day,
            start_mile=round(start_mi, 1),
            end_mile=round(end_mi, 1),
            miles=day_miles,
            moving_time=moving,
            arrive=arrive,
            elevation_gain_ft=gain_ft,
            elevation_max_ft=max_ft,
            passes=[p for p in pois.get("passes", []) if start_mi <= p.mile <= end_mi],
            scenic=[p for p in pois.get("scenic", []) if start_mi <= p.mile <= end_mi],
            construction=[p for p in pois.get("construction", []) if start_mi <= p.mile <= end_mi],
            wildlife=[p for p in pois.get("wildlife", []) if start_mi <= p.mile <= end_mi],
            gravel=gravel,
            no_services=services,
            sun=sun,
            weather=weather,
            air=air,
            fire=fires,
            elevation_profile=elevation,
            attributions=_attributions(weather, air, elevation, fires),
        )
        card.warnings = _warnings(card)
        cards.append(card)
    return cards


def _attributions(
    weather: WeatherInfo | None,
    air: AirInfo | None,
    elevation: ElevationProfile | None,
    fires: list[Fire],
) -> list[str]:
    """Data-source credits for whatever the card actually used."""
    out = ["Map data © OpenStreetMap contributors"]
    if weather or air or elevation:
        out.append("Weather/air/elevation © Open-Meteo.com (CC BY 4.0)")
    if fires:
        out.append("Wildfire perimeters: NIFC / WFIGS")
    return out


def _day_sun(
    route: Route,
    i0: int,
    i1: int,
    depart_day: datetime | None,
    day_profile: SpeedProfile,
    day_miles: float,
) -> SunInfo | None:
    """Sunrise/sunset + golden-hour + after-dark for one day (needs a departure).

    Sunrise (at the start) and sunset (at the end) are both taken for the
    *departure* day, so a long ride that runs past midnight still compares against
    that evening's sunset rather than the next day's.
    """
    if depart_day is None:
        return None
    s_lat, s_lon = route.points[i0].lat, route.points[i0].lon
    e_lat, e_lon = route.points[i1].lat, route.points[i1].lon
    sunrise = _sun_event(s_lat, s_lon, depart_day, "sunrise")
    sunset = _sun_event(e_lat, e_lon, depart_day, "sunset")
    gm_end, ge_start = _golden_hours(s_lat, s_lon, depart_day)
    after_dark, dark_from = _after_dark(day_profile, depart_day, sunset, day_miles)
    return SunInfo(
        sunrise=sunrise,
        sunset=sunset,
        golden_morning_end=gm_end,
        golden_evening_start=ge_start,
        after_dark=after_dark,
        dark_from_mile=dark_from,
    )


def _warnings(card: DayCard) -> list[Finding]:
    """Aggregate the day's cautions into validation findings."""
    out: list[Finding] = []
    if card.sun and card.sun.after_dark:
        m = card.sun.dark_from_mile
        where = f" (~{m} mi in)" if m is not None else ""
        out.append(
            Finding(
                WARNING,
                "dark",
                f"You'll be riding after sunset{where} — plan for night riding "
                "or an earlier start.",
            )
        )
    hours = card.moving_time.total_seconds() / 3600.0 if card.moving_time else 0.0
    if hours >= LONG_DAY_HOURS or card.miles >= LONG_DAY_MILES:
        out.append(
            Finding(INFO, "long_day", f"Long day: {card.miles:.0f} mi, ~{hours:.1f} h moving.")
        )
    if card.elevation_gain_ft and card.elevation_gain_ft >= BIG_CLIMB_FT:
        out.append(
            Finding(INFO, "climb", f"Big climbing day: ~{card.elevation_gain_ft:.0f} ft of gain.")
        )
    gravel_mi = sum(s.length_miles for s in card.gravel)
    if gravel_mi >= GRAVEL_WARN_MILES:
        out.append(Finding(WARNING, "unpaved", f"~{gravel_mi:.1f} mi of unpaved/gravel surface."))
    if card.construction:
        out.append(
            Finding(INFO, "construction", f"{len(card.construction)} construction zone(s) tagged "
                    "in OSM (may be stale — check current conditions).")
        )
    if card.wildlife:
        out.append(
            Finding(INFO, "wildlife", f"{len(card.wildlife)} marked wildlife-crossing zone(s).")
        )
    for g in card.no_services:
        out.append(
            Finding(WARNING, "services", f"No fuel for {g.miles:.0f} mi "
                    f"(mile {g.start_mile:.0f}–{g.end_mile:.0f}) — top off and tell someone.")
        )
    out += _live_warnings(card)
    return out


def _live_warnings(card: DayCard) -> list[Finding]:
    """Warnings from the Phase-2 live data (weather / air / fire)."""
    out: list[Finding] = []
    if card.weather and card.weather.samples:
        out += _weather_warnings(card.weather.samples)
    if card.air and card.air.smoke:
        bits = []
        if card.air.max_aqi is not None:
            bits.append(f"AQI {card.air.max_aqi}")
        if card.air.max_pm25 is not None:
            bits.append(f"PM2.5 {card.air.max_pm25:.0f}")
        detail = f" ({', '.join(bits)})" if bits else ""
        out.append(
            Finding(WARNING, "smoke", f"Likely wildfire smoke / poor air{detail} — "
                    "carry a respirator-rated mask and watch visibility.")
        )
    for f in card.fire:
        where = "on the route corridor" if f.dist_mi <= 0 else f"~{f.dist_mi:.0f} mi away"
        status = f" ({f.status})" if f.status else ""
        out.append(
            Finding(WARNING, "fire", f"Active fire: {f.name} {where}{status} — "
                    "check closures before you go (perimeters update on a delay).")
        )
    return out


def _weather_warnings(samples: list[WeatherSample]) -> list[Finding]:
    """Heat / cold / wind / crosswind / precip warnings from the day's samples."""
    out: list[Finding] = []

    def peak(attr: str) -> float | None:
        vals = [getattr(s, attr) for s in samples if getattr(s, attr) is not None]
        return max(vals) if vals else None

    hi = peak("temp_f")
    if hi is not None and hi >= HOT_F:
        out.append(Finding(WARNING, "heat", f"Hot: up to ~{hi:.0f}°F — hydrate and pace stops."))
    lo = min((s.temp_f for s in samples if s.temp_f is not None), default=None)
    if lo is not None and lo <= COLD_F:
        out.append(Finding(WARNING, "cold", f"Cold: down to ~{lo:.0f}°F — pack layers."))
    gust = peak("gust_mph")
    wind = peak("wind_mph")
    if (gust is not None and gust >= HIGH_GUST_MPH) or (wind is not None and wind >= HIGH_WIND_MPH):
        g = f", gusting {gust:.0f}" if gust is not None else ""
        out.append(Finding(WARNING, "wind", f"Strong wind: up to ~{wind or 0:.0f} mph{g}."))
    cross = peak("crosswind_mph")
    if cross is not None and cross >= HIGH_CROSSWIND_MPH:
        out.append(
            Finding(WARNING, "wind", f"High crosswind: up to ~{cross:.0f} mph — "
                    "expect to be pushed across the lane.")
        )
    prob = peak("precip_prob")
    if prob is not None and prob >= WET_PROB_PCT:
        out.append(
            Finding(WARNING, "precip", f"Wet: up to ~{prob:.0f}% chance of precip; pack rain gear.")
        )
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _fmt_dist(miles: float, imperial: bool) -> str:
    return f"{miles:.0f} mi" if imperial else f"{miles * KM_PER_MILE:.0f} km"


def _fmt_elev(feet: float, imperial: bool) -> str:
    return f"{feet:,.0f} ft" if imperial else f"{feet / M_TO_FT:,.0f} m"


def _fmt_dur(td: timedelta | None) -> str:
    if not td:
        return "—"
    mins = round(td.total_seconds() / 60)
    return f"{mins // 60}h{mins % 60:02d}"


def _fmt_clock(dt: datetime | None, tz: tzinfo | None) -> str:
    return dt.astimezone(tz).strftime("%H:%M") if dt else "—"


def _fmt_temp(f: float, imperial: bool) -> str:
    return f"{f:.0f}°F" if imperial else f"{(f - 32) * 5 / 9:.0f}°C"


def _fmt_speed(mph: float, imperial: bool) -> str:
    return f"{mph:.0f} mph" if imperial else f"{mph * KM_PER_MILE:.0f} km/h"


def _weather_line(w: WeatherInfo, imperial: bool) -> str | None:
    """A one-line weather summary (range of temp / wind / crosswind / precip)."""
    if not w.samples:
        note = w.note or "unavailable"
        return f"* Weather: {note}"
    temps = [s.temp_f for s in w.samples if s.temp_f is not None]
    winds = [s.wind_mph for s in w.samples if s.wind_mph is not None]
    cross = [s.crosswind_mph for s in w.samples if s.crosswind_mph is not None]
    probs = [s.precip_prob for s in w.samples if s.precip_prob is not None]
    parts: list[str] = []
    if temps:
        lo, hi = min(temps), max(temps)
        parts.append(f"{_fmt_temp(lo, imperial)}–{_fmt_temp(hi, imperial)}")
    if winds:
        w_str = f"wind ≤{_fmt_speed(max(winds), imperial)}"
        if cross and max(cross) >= 1:
            w_str += f" (crosswind ≤{_fmt_speed(max(cross), imperial)})"
        parts.append(w_str)
    if probs and max(probs) >= 1:
        parts.append(f"precip ≤{max(probs):.0f}%")
    return "* Weather: " + ", ".join(parts) if parts else None


def _range_line(spans: list[tuple[float, float]], imperial: bool, *, lengths: bool) -> str:
    """Format mile ranges as ``12 mi–18 mi`` (optionally ``… (6 mi)``)."""
    parts = []
    for a, b in spans:
        s = f"{_fmt_dist(a, imperial)}–{_fmt_dist(b, imperial)}"
        if lengths:
            s += f" ({_fmt_dist(b - a, imperial)})"
        parts.append(s)
    return ", ".join(parts)


def _sun_line(sun: SunInfo, imperial: bool, tz: tzinfo | None) -> str | None:
    """``Sun: ↑ … ↓ …`` plus an after-dark note, or None when empty."""
    parts = []
    if sun.sunrise:
        parts.append(f"↑ {_fmt_clock(sun.sunrise, tz)}")
    if sun.sunset:
        parts.append(f"↓ {_fmt_clock(sun.sunset, tz)}")
    if not parts and not sun.after_dark:
        return None
    line = "* Sun: " + "  ".join(parts)
    if sun.after_dark:
        line += (
            f" — riding after dark from {_fmt_dist(sun.dark_from_mile, imperial)}"
            if sun.dark_from_mile is not None
            else " — finishes after dark"
        )
    return line


def build_day_cards_markdown(
    cards: list[DayCard], *, imperial: bool = True, tz: tzinfo | None = None
) -> str:
    """Render day cards as markdown (one ``## Day N`` section per card).

    Mirrors the structured card: stats, climb (noting a DEM-elevation fallback),
    sun + after-dark + golden hour, passes/scenic, live weather/air/fire, the
    cautions (gravel, construction, wildlife, no-services gaps), warnings, and a
    data-source attribution line.
    """
    sections: list[str] = []
    for c in cards:
        title = f"## Day {c.index + 1}: {c.name}" if c.name else f"## Day {c.index + 1}"
        lines = [title]
        if c.date:
            lines.append(f"* {c.date.astimezone(tz):%a %b %-d}")
        lines.append(
            f"* Distance: {_fmt_dist(c.miles, imperial)}  ·  Moving: {_fmt_dur(c.moving_time)}"
            + (f"  ·  Arrive ~{_fmt_clock(c.arrive, tz)}" if c.arrive else "")
        )
        if c.elevation_gain_ft is not None:
            approx = (
                " (approx, via DEM)"
                if c.elevation_profile and c.elevation_profile.source != "gpx"
                else ""
            )
            lines.append(
                f"* Climb: {_fmt_elev(c.elevation_gain_ft, imperial)} gain"
                + (f", max {_fmt_elev(c.elevation_max_ft, imperial)}" if c.elevation_max_ft else "")
                + approx
            )
        if c.sun and (sl := _sun_line(c.sun, imperial, tz)):
            lines.append(sl)
            if c.sun.golden_morning_end or c.sun.golden_evening_start:
                gparts = []
                if c.sun.golden_morning_end:
                    gparts.append(f"morning to {_fmt_clock(c.sun.golden_morning_end, tz)}")
                if c.sun.golden_evening_start:
                    gparts.append(f"evening from {_fmt_clock(c.sun.golden_evening_start, tz)}")
                lines.append("* Golden hour: " + ", ".join(gparts))
        if c.passes:
            parts = [
                f"{p.name} ({_fmt_elev(p.elevation_ft, imperial)})" if p.elevation_ft else p.name
                for p in c.passes
            ]
            lines.append("* Passes: " + ", ".join(parts))
        if c.scenic:
            lines.append("* Scenic: " + ", ".join(f"{p.name} (mi {p.mile:.0f})" for p in c.scenic))
        if c.weather and (wl := _weather_line(c.weather, imperial)):
            lines.append(wl)
        if c.air and (c.air.max_aqi is not None or c.air.max_pm25 is not None):
            bits = []
            if c.air.max_aqi is not None:
                bits.append(f"AQI {c.air.max_aqi}")
            if c.air.max_pm25 is not None:
                bits.append(f"PM2.5 {c.air.max_pm25:.0f}")
            smoke = " — possible smoke" if c.air.smoke else ""
            lines.append(f"* Air: {', '.join(bits)}{smoke}")
        if c.fire:
            lines.append("* Fires: " + ", ".join(
                f"{f.name} (~{f.dist_mi:.0f} mi)" if f.dist_mi > 0 else f"{f.name} (on route)"
                for f in c.fire
            ))
        if c.gravel:
            spans = [(g.start_mile, g.end_mile) for g in c.gravel]
            lines.append("* Gravel/unpaved: " + _range_line(spans, imperial, lengths=False))
        if c.construction:
            lines.append("* Construction: " + ", ".join(p.name for p in c.construction))
        if c.wildlife:
            lines.append("* Wildlife: " + ", ".join(p.name for p in c.wildlife))
        if c.no_services:
            lines.append(
                "* No services: "
                + _range_line(
                    [(g.start_mile, g.end_mile) for g in c.no_services], imperial, lengths=True
                )
            )
        if c.warnings:
            lines.append("")
            lines.append("### Warnings")
            lines += [
                f"- {'⚠' if w.level == WARNING else '·'} {w.message}" for w in c.warnings
            ]
        if c.attributions:
            lines.append("")
            lines.append("*Sources: " + "; ".join(c.attributions) + "*")
        sections.append("\n".join(lines))
    return "\n\n".join(sections) + "\n"


def build_day_cards_json(cards: list[DayCard]) -> str:
    """Render day cards as a JSON array."""
    import json

    return json.dumps([c.to_dict() for c in cards])


def render_day_cards(
    gpx_source: str | Path,
    output_path: str | Path,
    *,
    fmt: str = "markdown",
    imperial: bool = True,
    speed: float = 0.0,
    departure: datetime | None = None,
    tz: tzinfo | None = None,
    fuel_range: float | None = None,
    osm: bool = True,
    live: bool = True,
) -> Path:
    """Analyze ``gpx_source`` and write per-day cards to ``output_path``.

    ``fmt`` is ``markdown`` | ``html`` | ``json``. Runs the full analysis (OSM on by
    default, with hazards) so gravel/fuel are populated; ``osm=False`` is fast and
    fully offline (no passes/scenic POIs). ``live`` gates the keyless live
    providers (Open-Meteo weather/air/elevation + NIFC wildfire); weather/air also
    need ``departure`` for ETAs, and everything honors ``GPXSHEET_DISABLE_LIVE``.
    """
    if fmt not in DAYCARD_FORMATS:
        raise ValueError(f"fmt must be one of {DAYCARD_FORMATS}, got {fmt!r}")
    from . import analyze

    route = analyze(str(gpx_source), include_hazards=True, osm=osm)
    cards = build_day_cards(
        route, departure=departure, tz=tz, imperial=imperial, speed=speed,
        fuel_range=fuel_range, osm=osm, live=live,
    )
    if fmt == "json":
        text = build_day_cards_json(cards)
    else:
        md = build_day_cards_markdown(cards, imperial=imperial, tz=tz)
        from .routetable import markdown_to_html

        text = markdown_to_html(md) if fmt == "html" else md
    out = Path(output_path)
    out.write_text(text, encoding="utf-8")
    return out
