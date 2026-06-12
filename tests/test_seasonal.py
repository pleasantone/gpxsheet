"""Tests for seasonal-closure detection (pure; no OSM/network)."""

from gpxsheet.seasonal import curated_closures, is_seasonal_edge


def test_curated_match_by_ref():
    labels = curated_closures(["CA 120"])
    assert labels == ["Tioga Pass (CA-120) — typically closed Nov–May"]


def test_curated_match_by_name_and_hyphenated_ref():
    # Hyphenated/spaced refs normalize the same; names also match.
    assert curated_closures(["CA-120"]) == curated_closures(["Tioga Pass Road"])
    assert curated_closures(["Tioga Pass Road"])


def test_curated_no_false_match_on_shorter_ref():
    # "CA 1" (Coast Highway) must not match "CA 120" / "CA 108" etc.
    assert curated_closures(["CA 1", "Cabrillo Highway"]) == []


def test_curated_dedupes_and_orders():
    labels = curated_closures(["Sonora Pass", "CA 108", "CA 120"])
    # Sonora appears once despite two matching tokens; CA-120 sorts in table order.
    assert labels == [
        "Tioga Pass (CA-120) — typically closed Nov–May",
        "Sonora Pass (CA-108) — typically closed in winter",
    ]


def test_seasonal_tag_yes():
    assert is_seasonal_edge(seasonal="yes")
    assert not is_seasonal_edge(seasonal="no")
    assert not is_seasonal_edge(seasonal=None)


def test_seasonal_conditional_with_month_is_seasonal():
    assert is_seasonal_edge(access_conditional="no @ (Nov-May)")
    assert is_seasonal_edge(motor_vehicle_conditional="destination @ (Dec-Apr)")


def test_time_of_day_conditional_is_not_seasonal():
    # A purely time-of-day restriction is not a seasonal closure.
    assert not is_seasonal_edge(access_conditional="no @ (22:00-06:00)")


def test_snowmobile_route_is_seasonal():
    assert is_seasonal_edge(snowmobile="designated")
    assert not is_seasonal_edge(snowmobile="no")
