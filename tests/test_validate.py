"""Tests for route validation (pure; no OSM/network)."""

from gpxsheet.models import FuelReport, FuelStop, GeoPoint, Route
from gpxsheet.validate import INFO, WARNING, validate_route


def _route(**kwargs) -> Route:
    return Route(
        name="t",
        points=[GeoPoint(0.0, 0.0), GeoPoint(0.0, 1.0)],
        distances_m=[0.0, 100 * 1609.344],
        **kwargs,
    )


def _warnings(findings):
    return {f.code for f in findings if f.level == WARNING}


def test_no_fuel_range_is_info_not_warning():
    findings = validate_route(_route())
    assert "fuel" not in _warnings(findings)
    assert any(f.code == "fuel" and f.level == INFO for f in findings)


def test_fuel_gap_exceeds_range_warns():
    route = _route(
        fuel_report=FuelReport(longest_gap_miles=120, exceeds_range=True, fuel_range_miles=100),
        fuel_stops=[FuelStop(50, "Gas", 0, 0)],
    )
    assert "fuel" in _warnings(validate_route(route, fuel_range=100))


def test_no_fuel_stops_warns():
    route = _route(
        fuel_report=FuelReport(longest_gap_miles=100, exceeds_range=True, fuel_range_miles=50),
        fuel_stops=[],
    )
    findings = validate_route(route, fuel_range=50)
    assert "fuel" in _warnings(findings)


def test_fuel_within_range_no_warning():
    route = _route(
        fuel_report=FuelReport(longest_gap_miles=40, exceeds_range=False, fuel_range_miles=100),
        fuel_stops=[FuelStop(40, "Gas", 0, 0)],
    )
    assert "fuel" not in _warnings(validate_route(route, fuel_range=100))


def test_no_fuel_stops_within_range_no_warning():
    # A short route within range legitimately has no fuel stops.
    route = _route(
        fuel_report=FuelReport(longest_gap_miles=75, exceeds_range=False, fuel_range_miles=500),
        fuel_stops=[],
    )
    assert "fuel" not in _warnings(validate_route(route, fuel_range=500))


def test_unpaved_skipped_without_osm():
    findings = validate_route(_route())  # unpaved_miles is None
    assert any(f.code == "unpaved" and f.level == INFO for f in findings)
    assert "unpaved" not in _warnings(findings)


def test_unpaved_warns_when_significant():
    assert "unpaved" in _warnings(validate_route(_route(unpaved_miles=3.0)))


def test_unpaved_paved_no_warning():
    findings = validate_route(_route(unpaved_miles=0.0))
    assert "unpaved" not in _warnings(findings)
    # 0.0 means assessed-and-paved, so not even an info note
    assert not any(f.code == "unpaved" for f in findings)


def test_ferry_warns():
    assert "ferry" in _warnings(validate_route(_route(ferry_crossings=["Coastal Ferry"])))


def test_ferry_none_present_no_warning():
    assert "ferry" not in _warnings(validate_route(_route(ferry_crossings=[])))


def test_seasonal_always_noted_as_info():
    assert any(f.code == "seasonal" and f.level == INFO for f in validate_route(_route()))
