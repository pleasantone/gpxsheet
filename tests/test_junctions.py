"""Tests for the pure junction topology helpers (no OSM/network)."""

from gpxsheet.junctions import (
    branches_not_taken,
    direction_word,
    relative_angle,
    roundabout_exit_number,
)


def test_relative_angle_sign_and_wrap():
    assert relative_angle(0, 90) == 90  # due east of north -> right
    assert relative_angle(0, 270) == -90  # west -> left
    assert relative_angle(350, 10) == 20  # wraps across 0
    assert relative_angle(10, 350) == -20


def test_direction_word_bands():
    assert direction_word(0) == "straight"
    assert direction_word(20) == "straight"
    assert direction_word(45) == "right"
    assert direction_word(-45) == "left"
    assert direction_word(170) == "back"
    assert direction_word(-160) == "back"


def test_branches_excludes_arrival_and_taken():
    # Heading north into a 4-way: go straight (N), with side roads E and W and
    # the road you came from (S). Branches not taken = the E and W side roads.
    incident = [
        ("Main St", 0.0),  # straight ahead -> taken
        ("East Ave", 90.0),  # right
        ("West Ave", 270.0),  # left
        ("Main St", 180.0),  # back where you came from -> excluded
    ]
    branches = branches_not_taken(arrival_bearing=0.0, taken_bearing=0.0, incident=incident)
    assert [(b.direction, b.name) for b in branches] == [
        ("left", "West Ave"),
        ("right", "East Ave"),
    ]
    # sorted left (negative) -> right (positive)
    assert branches[0].relative_angle < branches[1].relative_angle


def test_branches_fork_disambiguation():
    # Y-fork: arrive heading north, bear right onto the NE branch; the NW branch
    # is the road not taken.
    incident = [
        ("NE Branch", 30.0),  # taken (bear right)
        ("NW Branch", 330.0),  # not taken (bears left)
        ("Stem Rd", 180.0),  # arrived on this
    ]
    branches = branches_not_taken(arrival_bearing=0.0, taken_bearing=30.0, incident=incident)
    assert len(branches) == 1
    assert branches[0].name == "NW Branch"
    assert branches[0].direction == "left"


def test_branches_drops_same_name_as_taken():
    # The continuing road / other carriageway (same name) is noise, not a fork.
    incident = [
        ("Farm Hill Blvd", 0.0),  # taken (straight)
        ("Farm Hill Blvd", 30.0),  # other carriageway, same name -> dropped
        ("Glennan Dr", 300.0),  # real side road -> kept
    ]
    branches = branches_not_taken(0.0, 0.0, incident, taken_name="Farm Hill Blvd")
    assert [b.name for b in branches] == ["Glennan Dr"]


def test_branches_tolerance_merges_near_taken():
    # A branch a few degrees off the taken road is treated as the taken road.
    incident = [("Hwy", 88.0), ("Hwy", 92.0), ("Side", 270.0)]
    branches = branches_not_taken(arrival_bearing=0.0, taken_bearing=90.0, incident=incident)
    assert [b.name for b in branches] == ["Side"]


def test_roundabout_exit_counts_spurs():
    # 4-node ring, exit spurs at indices 1, 2, 3. Enter at 0.
    ring = [False, True, True, True]
    assert roundabout_exit_number(ring, entry_idx=0, exit_idx=1) == 1  # first exit
    assert roundabout_exit_number(ring, entry_idx=0, exit_idx=2) == 2  # second exit
    assert roundabout_exit_number(ring, entry_idx=0, exit_idx=3) == 3  # third exit


def test_roundabout_exit_wraps_and_skips_non_exits():
    # Non-exit nodes between spurs are not counted; circulation wraps the ring.
    ring = [False, False, True, False, True]  # exits at 2 and 4
    assert roundabout_exit_number(ring, entry_idx=4, exit_idx=2) == 1  # wrap 4->0->1->2
    assert roundabout_exit_number(ring, entry_idx=0, exit_idx=4) == 2


def test_roundabout_degenerate():
    assert roundabout_exit_number([], 0, 0) == 0
    assert roundabout_exit_number([True, True], 1, 1) == 0  # entry == exit
