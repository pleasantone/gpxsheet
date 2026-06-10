"""Rider profiles control which route events are shown and at what threshold.

See the "User Profiles" and "Significance Scoring" sections of PRODUCT.md.
Profile settings determine display thresholds rather than what gets detected;
detection always runs, profiles filter the output.
"""

from __future__ import annotations

from dataclasses import dataclass

# Significance contributions from PRODUCT.md's scoring table.
SCORE_ROAD_NAME_CHANGE = 40
SCORE_STATE_HWY_JUNCTION = 50
SCORE_COUNTY_ROAD_JUNCTION = 30
SCORE_Y_INTERSECTION = 60
SCORE_T_INTERSECTION = 60
SCORE_FUEL = 20
SCORE_TOWN_CENTER = 20
# A straight-through road-name change ("Continue onto ...") with no real heading
# change is usually residential-grid noise, not a navigation moment. Penalize it
# (below the sport-touring threshold) unless it is onto a numbered highway, where
# the name change is genuinely worth flagging.
SCORE_CONTINUE_PENALTY = 18


@dataclass(frozen=True, slots=True)
class Profile:
    name: str
    # Minimum significance for a decision point to be displayed.
    decision_threshold: int
    include_fuel: bool
    include_reassurance: bool
    include_confirmation: bool
    reassurance_interval_miles: float


PROFILES: dict[str, Profile] = {
    "minimalist": Profile(
        name="minimalist",
        decision_threshold=55,
        include_fuel=False,
        include_reassurance=False,
        include_confirmation=False,
        reassurance_interval_miles=15.0,
    ),
    "sport-touring": Profile(
        name="sport-touring",
        decision_threshold=40,
        include_fuel=True,
        include_reassurance=True,
        include_confirmation=False,
        reassurance_interval_miles=15.0,
    ),
    "rally": Profile(
        name="rally",
        decision_threshold=30,
        include_fuel=True,
        include_reassurance=True,
        include_confirmation=True,
        reassurance_interval_miles=10.0,
    ),
}


def get_profile(name: str) -> Profile:
    try:
        return PROFILES[name]
    except KeyError:
        valid = ", ".join(sorted(PROFILES))
        raise ValueError(f"unknown profile {name!r}; choose one of: {valid}") from None
