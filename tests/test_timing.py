"""Tests for the route-table timing engine (src/gpxsheet/timing.py)."""

from __future__ import annotations

from datetime import datetime, timedelta

import dateutil.tz

from gpxsheet.timing import (
    StopInput,
    compute_timings,
    format_sun_line,
    sun_times,
    travel_time,
)

PACIFIC = dateutil.tz.gettz("US/Pacific")


def test_travel_time_one_hour_at_speed():
    # Exactly speed_kph kilometres take one hour.
    assert travel_time(48_280.0, 48.280) == timedelta(hours=1)


def test_travel_time_zero_speed_is_zero():
    assert travel_time(1000.0, 0.0) == timedelta()


def test_no_departure_gives_no_arrivals():
    stops = [StopInput(0.0), StopInput(1000.0)]
    timings = compute_timings(stops, departure=None, speed_kph=48.0)
    assert all(t.arrival is None for t in timings)


def test_arrivals_accumulate_distance_and_layover():
    depart = datetime(2023, 7, 30, 9, 0, tzinfo=PACIFIC)
    speed = 60.0  # km/h -> 1 km/min
    stops = [
        StopInput(0.0),
        StopInput(60_000.0, delay=timedelta(minutes=30)),  # +60 min ride
        StopInput(120_000.0),
    ]
    t = compute_timings(stops, departure=depart, speed_kph=speed)
    assert t[0].arrival == depart
    # 60 km at 1 km/min = 60 min after departure (no prior layover).
    assert t[1].arrival == depart + timedelta(minutes=60)
    assert t[1].layover == timedelta(minutes=30)
    # 120 km ride + the 30-min layover at stop 1.
    assert t[2].arrival == depart + timedelta(minutes=120 + 30)


def test_first_and_last_take_no_layover():
    stops = [
        StopInput(0.0, delay=timedelta(minutes=99)),
        StopInput(1000.0, delay=timedelta(minutes=20)),
        StopInput(2000.0, delay=timedelta(minutes=99)),
    ]
    t = compute_timings(stops, departure=None, speed_kph=48.0)
    assert t[0].layover == timedelta()
    assert t[1].layover == timedelta(minutes=20)
    assert t[2].layover == timedelta()


def test_since_gas_resets_after_fuel():
    stops = [
        StopInput(0.0),
        StopInput(50_000.0, fuel_reset=True),  # fill up here
        StopInput(80_000.0),
    ]
    t = compute_timings(stops, departure=None, speed_kph=48.0)
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
