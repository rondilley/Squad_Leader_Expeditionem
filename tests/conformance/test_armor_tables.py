"""The armor combat tables of rules 33.3, 33.31, 33.4, and 33.41 (FR-16).

The numbers come off page 13 of the owner's rulebook, where the four tables are printed as
graphics. A transcription is only as good as its check, so this file states each row of
each table, and a mistake in one cell fails one test.
"""

from __future__ import annotations

import pytest

from sldata.loaders import load_armor

ARMOR = load_armor()

# Rule 33.3. Each row is the four range columns: 1-6, 7-12, 13-24, and 25 or more.
TO_HIT_DEFAULT = {
    "infantry_in_building": [8, 7, 6, 5],
    "infantry_in_woods": [8, 6, 5, 4],
    "infantry_in_other": [9, 8, 7, 6],
    "vehicle_hull_down": [7, 5, 4, 3],
    "vehicle_in_woods_or_building": [9, 8, 7, 6],
    "vehicle_in_other": [10, 9, 8, 7],
    "at_gun": [6, 5, 4, 2],
}
TO_HIT_RUSSIAN = {
    "infantry_in_building": [8, 6, 5, 2],
    "infantry_in_woods": [8, 6, 4, 2],
    "infantry_in_other": [9, 7, 6, 3],
    "vehicle_hull_down": [6, 4, 3, 2],
    "vehicle_in_woods_or_building": [9, 7, 6, 3],
    "vehicle_in_other": [10, 8, 7, 4],
    "at_gun": [5, 4, 3, None],
}

# Rule 33.4, in the column order of the table.
WEAPONS = [
    "mmg_hmg",
    "cal50_20mm",
    "ap37",
    "ap50",
    "ap75_76",
    "he37",
    "he50",
    "he75_76",
    "he105",
    "he120",
    "he150",
    "h6",
    "panzerfaust",
    "bazooka",
    "flamethrower",
    "demolition_charge",
]
KILL = {
    "afv_front": [-3, -3, 2, 3, 6, -1, 0, 2, 4, 6, 8, 8, 7, 3, 3, 9],
    "afv_side": [-3, -2, 3, 6, 8, 1, 2, 3, 6, 7, 10, 10, 8, 4, 4, 10],
    "afv_rear": [-2, -1, 4, 8, 10, 2, 3, 4, 8, 9, 12, 11, 10, 6, 6, 11],
    "truck_or_jeep": [None, None, 8, 10, 10, 10, 11, 12, 12, 12, 12, 11, 10, 10, 10, 12],
}

# Rule 33.31.
CASES = {"A": 2, "B": 2, "C": 4, "D": 2, "E": 1, "F": 5, "G": 3, "H": 2, "I": 4, "J": -2, "K": -2}

# Rule 33.41.
KILL_MODIFIERS = {
    "halftrack": -5,
    "priest": -2,
    "m10": -1,
    "m4a4": 0,
    "t34": 0,
    "mkiv": 0,
    "m4m52": 1,
    "su122": 1,
    "stg3": 1,
    "su152": 2,
    "brumbar": 2,
}

MIDDLE_OF_EACH_RANGE = (3, 9, 18, 30)


# ------------------------------------------------------------------- 33.3, the to hit


def test_the_ranges_are_the_four_columns_of_the_table():
    assert ARMOR.ranges == ((1, 6), (7, 12), (13, 24), (25, None))


@pytest.mark.parametrize("target", sorted(TO_HIT_DEFAULT))
def test_the_to_hit_row_of_each_target(target: str):
    """Rule 33.3: the black number, which each firing unit that is not Russian reads."""
    found = [ARMOR.to_hit(target, distance) for distance in MIDDLE_OF_EACH_RANGE]
    assert found == TO_HIT_DEFAULT[target]


@pytest.mark.parametrize("target", sorted(TO_HIT_RUSSIAN))
def test_the_russian_to_hit_row_of_each_target(target: str):
    """Rule 33.3: the red number, which a Russian firing unit reads."""
    found = [ARMOR.to_hit(target, distance, "russian") for distance in MIDDLE_OF_EACH_RANGE]
    assert found == TO_HIT_RUSSIAN[target]


def test_a_russian_gun_hits_no_anti_tank_gun_past_twenty_four_hexes():
    """The one empty cell of the table."""
    assert ARMOR.to_hit("at_gun", 30, "russian") is None
    assert ARMOR.to_hit("at_gun", 30) == 2


def test_the_edges_of_each_range_band_read_the_same_column():
    for target in TO_HIT_DEFAULT:
        assert ARMOR.to_hit(target, 1) == ARMOR.to_hit(target, 6)
        assert ARMOR.to_hit(target, 7) == ARMOR.to_hit(target, 12)
        assert ARMOR.to_hit(target, 13) == ARMOR.to_hit(target, 24)
        assert ARMOR.to_hit(target, 25) == ARMOR.to_hit(target, 100)


def test_a_distance_of_zero_is_not_on_the_table():
    assert ARMOR.range_index(0) is None
    assert ARMOR.to_hit("infantry_in_other", 0) is None


def test_a_target_the_table_does_not_name_says_so():
    with pytest.raises(KeyError) as exc:
        ARMOR.to_hit("aircraft", 5)
    assert "aircraft" in str(exc.value)


def test_a_shot_is_harder_as_the_range_grows():
    """A to-hit number is a roll-or-less number, so a smaller number is a harder shot."""
    for target, row in TO_HIT_DEFAULT.items():
        assert row == sorted(row, reverse=True), target


def test_a_vehicle_that_is_hull_down_is_the_hardest_vehicle_to_hit():
    for i, distance in enumerate(MIDDLE_OF_EACH_RANGE):
        assert ARMOR.to_hit("vehicle_hull_down", distance) < ARMOR.to_hit("vehicle_in_other", distance)


# --------------------------------------------------------------- 33.31, the modifiers


def test_each_case_of_the_hit_modifiers():
    assert ARMOR.hit_modifiers == CASES


def test_the_modifiers_of_several_cases_add_up():
    """Rule 33.32: the modifiers are cumulative."""
    assert ARMOR.hit_modifier(["A", "D"]) == CASES["A"] + CASES["D"]
    assert ARMOR.hit_modifier(["F", "H", "J"]) == CASES["F"] + CASES["H"] + CASES["J"]
    assert ARMOR.hit_modifier([]) == 0


def test_a_case_the_rule_does_not_name_says_so():
    with pytest.raises(KeyError) as exc:
        ARMOR.hit_modifier(["Z"])
    assert "33.31" in str(exc.value)


def test_the_two_cases_that_help_the_firer_are_the_close_ones():
    """A negative modifier is a better chance, and the two are adjacent and same hex."""
    assert sorted(c for c, v in CASES.items() if v < 0) == ["J", "K"]


# ------------------------------------------------------------------- 33.4, the kill


def test_the_weapon_columns_are_in_the_order_of_the_table():
    assert list(ARMOR.weapons) == WEAPONS


@pytest.mark.parametrize("target", sorted(KILL))
def test_the_kill_row_of_each_target(target: str):
    found = [ARMOR.kill_number(target, weapon) for weapon in WEAPONS]
    assert found == KILL[target]


def test_a_machine_gun_has_no_kill_number_against_a_truck():
    """Rule 51.4 sends that attack to the Infantry Fire Table instead."""
    assert ARMOR.kill_number("truck_or_jeep", "mmg_hmg") is None
    assert ARMOR.kill_number("truck_or_jeep", "cal50_20mm") is None


def test_the_rear_of_a_vehicle_is_the_easiest_face_to_kill():
    for weapon in WEAPONS:
        front = ARMOR.kill_number("afv_front", weapon)
        side = ARMOR.kill_number("afv_side", weapon)
        rear = ARMOR.kill_number("afv_rear", weapon)
        assert front <= side <= rear, weapon


def test_a_bigger_gun_kills_more_easily():
    """Within the armour-piercing columns and within the high explosive columns."""
    for target in ("afv_front", "afv_side", "afv_rear"):
        armour_piercing = [ARMOR.kill_number(target, w) for w in ("ap37", "ap50", "ap75_76")]
        explosive = [ARMOR.kill_number(target, w) for w in ("he37", "he50", "he75_76", "he105", "he120", "he150")]
        assert armour_piercing == sorted(armour_piercing), target
        assert explosive == sorted(explosive), target


def test_a_weapon_the_table_does_not_name_says_so():
    with pytest.raises(KeyError) as exc:
        ARMOR.kill_number("afv_front", "railgun")
    assert "railgun" in str(exc.value)


# ------------------------------------------------------- 33.41, the vehicle modifiers


def test_each_vehicle_modifier():
    assert ARMOR.kill_number_modifiers == KILL_MODIFIERS


def test_a_halftrack_is_the_easiest_vehicle_to_kill():
    """Rule 33.41: a minus five on the roll of the attacker is the largest help there is."""
    assert min(KILL_MODIFIERS.values()) == KILL_MODIFIERS["halftrack"]


def test_the_vehicle_modifier_goes_on_the_attacker_dice():
    """Rule 33.41: a negative modifier helps the attacker. The base number does not move.

    A halftrack is minus 5, so a raw roll above the base number can still kill it.
    An SU-152 is plus 2, so a raw roll at the base number does not kill it.
    """
    from conformance.harness import build_case
    from slcore.rules.r33_afv_combat import roll_kill

    base = ARMOR.kill_number("afv_front", "ap75_76")
    assert ARMOR.kill_number("afv_front", "ap75_76", "halftrack") == base
    assert ARMOR.kill_number("afv_front", "ap75_76", "su152") == base

    def rolled(vehicle: str, dice: list[int]):
        case = build_case({
            "phase": "prep_fire",
            "sub_step": "fire_window",
            "phasing": "german",
            "active": "german",
            "dice": dice,
            "units": [
                {"ref": "gun", "side": "german", "type": "MkIVF2", "hex": "A1", "facing": 0},
                {"ref": "v", "side": "german" if vehicle == "SdKfz251" else "russian", "type": vehicle, "hex": "B1", "facing": 0},
            ],
        })
        state, result = roll_kill(case.engine.armor_ctx, case.state, case.unit("gun").hex, case.unit("v"), "ap75_76")
        return result

    halftrack = rolled("SdKfz251", [5, 6])
    assert halftrack.raw == 11
    assert halftrack.modifier == -5
    assert halftrack.adjusted == 6
    assert halftrack.needed == ARMOR.kill_number(halftrack.face, "ap75_76")
    assert halftrack.raw > halftrack.needed
    assert halftrack.killed

    survives = rolled("SU152", [6, 6])
    assert survives.raw == 12
    assert survives.modifier == 2
    assert survives.adjusted == 14
    assert survives.needed == ARMOR.kill_number(survives.face, "ap75_76")
    assert not survives.killed

    dies = rolled("SU152", [1, 3])
    assert dies.raw == 4
    assert dies.adjusted == 6
    assert dies.raw < dies.needed
    assert dies.killed


def test_a_vehicle_that_no_row_names_takes_no_modifier():
    base = ARMOR.kill_number("afv_side", "ap50")
    assert ARMOR.kill_number("afv_side", "ap50", "a_vehicle_of_a_later_set") == base


def test_a_kill_number_with_no_base_stays_without_one():
    assert ARMOR.kill_number("truck_or_jeep", "mmg_hmg", "halftrack") is None


# ------------------------------------------------------------------- the provenance


def test_the_data_file_names_where_the_numbers_came_from():
    """DR-01: a rules table is a project data file with a provenance note."""
    from sldata.loaders import _read_json

    document = _read_json("tables/armor.json")
    provenance = " ".join(document["provenance"])
    assert "page 13" in provenance
    assert "SR-07" in provenance and "DR-01" in provenance
