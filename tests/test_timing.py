"""Tests for the route-table timing engine (src/gpxsheet/timing.py)."""

from __future__ import annotations

from datetime import datetime, timedelta

import dateutil.tz

from gpxsheet.geo import miles_to_meters
from gpxsheet.timing import (
    SpeedProfile,
    StopInput,
    compute_timings,
    format_sun_line,
    sun_times,
    travel_time,
)

PACIFIC = dateutil.tz.gettz("US/Pacific")
FLAT60 = SpeedProfile.flat(60.0)  # 60 mph -> 1 mile/min


def test_travel_time_one_hour_at_speed():
    # Exactly speed_kph kilometres take one hour.
    assert travel_time(48_280.0, 48.280) == timedelta(hours=1)


def test_travel_time_zero_speed_is_zero():
    assert travel_time(1000.0, 0.0) == timedelta()


def test_flat_profile_time_to():
    assert SpeedProfile.flat(60.0).time_to(30.0) == timedelta(minutes=30)


def test_variable_profile_integrates_segments():
    # 0-10 mi @ 60 mph (10 min), 10-20 mi @ 30 mph (20 min).
    profile = SpeedProfile.from_breakpoints_mph([(0.0, 60.0), (10.0, 30.0)])
    assert profile.time_to(10.0) == timedelta(minutes=10)
    assert profile.time_to(20.0) == timedelta(minutes=30)
    assert round(profile.average_mph(20.0), 1) == 40.0


def test_profile_slice_rebases_to_zero():
    profile = SpeedProfile.from_breakpoints_mph([(0.0, 60.0), (10.0, 30.0)])
    day2 = profile.slice(10.0, 20.0)  # the 30 mph stretch, rebased to mile 0
    assert day2.time_to(10.0) == timedelta(minutes=20)


def test_no_departure_gives_no_arrivals():
    stops = [StopInput(0.0), StopInput(miles_to_meters(10))]
    timings = compute_timings(stops, departure=None, speed=FLAT60)
    assert all(t.arrival is None for t in timings)


def test_arrivals_accumulate_distance_and_layover():
    depart = datetime(2023, 7, 30, 9, 0, tzinfo=PACIFIC)
    stops = [
        StopInput(0.0),
        StopInput(miles_to_meters(60), delay=timedelta(minutes=30)),  # +60 min ride
        StopInput(miles_to_meters(120)),
    ]
    t = compute_timings(stops, departure=depart, speed=FLAT60)
    assert t[0].arrival == depart
    # 60 mi at 1 mi/min = 60 min after departure (no prior layover).
    assert t[1].arrival == depart + timedelta(minutes=60)
    assert t[1].layover == timedelta(minutes=30)
    # 120 mi ride + the 30-min layover at stop 1.
    assert t[2].arrival == depart + timedelta(minutes=120 + 30)


def test_user_speed_overrides_via_flat_profile():
    # A flat profile (what a user --speed produces) ignores any variable data.
    depart = datetime(2023, 7, 30, 9, 0, tzinfo=PACIFIC)
    t = compute_timings(
        [StopInput(0.0), StopInput(miles_to_meters(30))],
        departure=depart,
        speed=SpeedProfile.flat(30.0),  # 30 mph -> 30 mi in 60 min
    )
    assert t[1].arrival == depart + timedelta(minutes=60)


def test_first_and_last_take_no_layover():
    stops = [
        StopInput(0.0, delay=timedelta(minutes=99)),
        StopInput(miles_to_meters(1), delay=timedelta(minutes=20)),
        StopInput(miles_to_meters(2), delay=timedelta(minutes=99)),
    ]
    t = compute_timings(stops, departure=None, speed=FLAT60)
    assert t[0].layover == timedelta()
    assert t[1].layover == timedelta(minutes=20)
    assert t[2].layover == timedelta()


def test_since_gas_resets_after_fuel():
    stops = [
        StopInput(0.0),
        StopInput(50_000.0, fuel_reset=True),  # fill up here
        StopInput(80_000.0),
    ]
    t = compute_timings(stops, departure=None, speed=FLAT60)
    assert t[1].since_gas_m == 50_000.0  # distance to the fuel stop
    assert t[2].since_gas_m == 30_000.0  # since the fill-up
    assert t[2].total_m == 80_000.0


def test_sun_times_none_without_times():
    assert sun_times(38.0, -122.0, None, 38.5, -122.5, None) is None


def test_sun_times_and_format():
    start = datetime(2023, 7, 30, 9, 15, tzinfo=PACIFIC)
    end = datetime(2023, 7, 30, 17, 41, tzinfo=PACIFIC)
    times = sun_times(37.99, -122.55, start, 38.43, -123.0, end)
    assert times is not None
    assert set(times) == {"Sunrise", "Sunset", "Starts", "Ends"}
    line = format_sun_line(times, PACIFIC)
    assert line.startswith("07/30/23:")
    assert "Sunrise:" in line and "Sunset:" in line
    # Sorted chronologically: sunrise precedes the 09:15 start.
    assert line.index("Sunrise") < line.index("Starts")
