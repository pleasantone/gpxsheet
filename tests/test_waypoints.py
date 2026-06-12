"""Tests for the waypoint classifier (src/gpxsheet/waypoints.py)."""

from __future__ import annotations

from gpxsheet.waypoints import classify


def test_classify_by_symbol_gas():
    c = classify("76 Bodega Bay", "Gas Station")
    assert c.marker == "G"
    assert c.fuel_reset is True
    assert c.delay == 15
    assert c.symbol == "Gas Station"


def test_classify_by_symbol_restaurant():
    c = classify("Pat's Place", "Restaurant")
    assert c.marker == "L"
    assert c.fuel_reset is False
    assert c.delay == 60


def test_name_regex_adopts_symbol():
    # No symbol, but the name says "Lunch" -> Restaurant rule, symbol adopted.
    c = classify("Lunch at the Lake", None)
    assert c.symbol == "Restaurant"
    assert c.marker == "L"


def test_gas_and_lunch_combo_marker():
    c = classify("Gas and Lunch Stop", None)
    assert c.marker == "GL"
    assert c.fuel_reset is True
    assert c.delay == 75


def test_dinner_matches_but_winner_does_not():
    # Regression for the GPXtable \D bug: "Dinner" should classify as a meal,
    # but "winner"/"sinner" must NOT (\D matched any non-digit before "inner").
    assert classify("Dinner Spot", None).marker == "L"
    assert classify("Big Winner Saloon", None).marker == ""
    assert classify("The Sinner's Bar", None).marker == ""


def test_unmatched_keeps_symbol_no_marker():
    c = classify("Random Overlook", "Flag")
    assert c.symbol == "Flag"
    assert c.marker == ""
    assert c.delay == 0
    assert c.fuel_reset is False


def test_parenthetical_shorthand_inherits_gpxtable_quirk():
    # GPXtable's "(G)"/"(L)" shorthands use `\b\(G\)\b`; because "(" is not a word
    # char, the `\b` only fires when the token is glued to word chars on both
    # sides. We preserve that exact behavior so GPXtable stays a parity oracle.
    assert classify("stop(G)x", None).marker == "G"  # glued -> matches
    assert classify("Quick stop (G)", None).marker == ""  # spaced -> no match


def test_custom_classifier_overrides_default():
    custom = [{"symbol": "Coffee", "search": r"\bcoffee\b", "delay": 20, "marker": "C"}]
    c = classify("Morning Coffee", None, classifier=custom)
    assert c.symbol == "Coffee"
    assert c.marker == "C"
    assert c.delay == 20
    # A default-only match no longer fires under the custom classifier.
    assert classify("Gas Station Stop", "Gas Station", classifier=custom).marker == ""
