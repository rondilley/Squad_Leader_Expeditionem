"""S2 and PR-31: the legal list is the same for a dummy counter and a real concealed stack.

Rule 25.2 treats a stack below a concealment counter as an opposing squad until proven
otherwise, and rule 25.7 lets a counter stand on an empty hex. Each test builds two
states that differ in one thing only: in the real state a German squad is below the
counter, and in the dummy state that squad is off the board. The Russian legal list must
be the same in the two states, command for command.
"""

from __future__ import annotations

import copy
from typing import Any

from conformance.harness import CaseState, build_case


def pair(case: dict[str, Any], hidden_refs: tuple[str, ...]) -> tuple[CaseState, CaseState]:
    """The real state and the dummy state of one case.

    In the dummy state each unit of `hidden_refs` has no hex, so the counter over its hex
    has nothing below it (rule 25.7). The unit list keeps its length and its identities.
    """
    real = build_case(copy.deepcopy(case))
    dummy_case = copy.deepcopy(case)
    for spec in dummy_case["units"]:
        if spec["ref"] in hidden_refs:
            spec["hex"] = None
    dummy = build_case(dummy_case)
    return real, dummy


def payloads(cs: CaseState) -> list[dict]:
    return [lc.payload for lc in cs.engine.legal_commands(cs.state).commands]


def assert_same_list(real: CaseState, dummy: CaseState) -> list[dict]:
    got_real = payloads(real)
    got_dummy = payloads(dummy)
    assert got_real == got_dummy, f"the lists differ: real {got_real} dummy {got_dummy}"
    return got_real


def test_movement_refuses_the_counter_hex_for_a_dummy_and_a_real_stack():
    """Rules 5.6 and 25.2: no move into the hex of a counter, whatever is below it."""
    case = {
        "phase": "movement",
        "sub_step": "move_window",
        "phasing": "russian",
        "units": [
            {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "D2"},
            {"ref": "lead", "side": "russian", "type": "8-1", "hex": "D2"},
            {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3"},
        ],
        "concealment": [{"side": "german", "hex": "E3"}],
    }
    real, dummy = pair(case, ("g",))
    listed = assert_same_list(real, dummy)
    assert not any(p.get("hex") == "E3" and p["action"] in ("move", "stack_move") for p in listed)
    assert any(p.get("hex") == "D3" and p["action"] == "move" for p in listed), "the other hexes stay open"


def test_the_counter_hex_is_a_fire_target_for_a_dummy_and_a_real_stack():
    """Rule 25.2 and 25.8: the hex of a counter is a target in each fire phase."""
    case = {
        "phase": "prep_fire",
        "sub_step": "fire_window",
        "phasing": "russian",
        "units": [
            {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "D3"},
            {"ref": "lmg", "side": "russian", "type": "LMG", "carrier": "r"},
            {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3"},
        ],
        "concealment": [{"side": "german", "hex": "E3"}],
    }
    real, dummy = pair(case, ("g",))
    listed = assert_same_list(real, dummy)
    assert {"action": "group_add", "units": [real.ids["r"]], "hex": "E3"} in listed


def test_the_main_gun_and_the_vehicle_mg_aim_at_a_dummy_as_at_a_real_stack():
    """Rules 25.2, 34.1, and 34.2: the infantry aim of a main gun and the vehicle machine gun."""
    case = {
        "phase": "prep_fire",
        "sub_step": "fire_window",
        "phasing": "russian",
        "units": [
            {"ref": "tank", "side": "russian", "type": "T34", "hex": "C2", "facing": 1},
            {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3"},
        ],
        "concealment": [{"side": "german", "hex": "E3"}],
    }
    real, dummy = pair(case, ("g",))
    listed = assert_same_list(real, dummy)
    aims = [p for p in listed if p["action"] in ("afv_fire", "afv_mg") and p.get("hex") == "E3"]
    assert aims, "the counter hex is a target of the tank"


def test_rout_is_the_same_next_to_a_dummy_and_next_to_a_real_stack():
    """QA-13.41 and PR-31: a counter is not a known enemy position, and its hex is closed."""
    case = {
        "phase": "rout",
        "sub_step": "rout_window",
        "actor": "phasing",
        "phasing": "russian",
        "units": [
            {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "D2", "broken": True},
            {"ref": "far", "side": "german", "type": "4-6-7", "hex": "J9"},
            {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3"},
        ],
        "concealment": [{"side": "german", "hex": "E3"}],
    }
    real, dummy = pair(case, ("g",))
    listed = assert_same_list(real, dummy)
    assert not any(p.get("hex") == "E3" for p in listed), "no rout ends in the counter hex"


def test_advance_into_the_counter_hex_is_legal_for_a_dummy_and_a_real_stack():
    """Rules 4.7 and 5.6: an advance may enter an enemy hex, so it may enter a counter hex."""
    case = {
        "phase": "advance",
        "sub_step": "advance_window",
        "phasing": "russian",
        "units": [
            {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "D3"},
            {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3"},
        ],
        "concealment": [{"side": "german", "hex": "E3"}],
    }
    real, dummy = pair(case, ("g",))
    listed = assert_same_list(real, dummy)
    assert {"action": "advance", "units": [real.ids["r"]], "hex": "E3"} in listed


def _fire_at_counter(cs: CaseState) -> None:
    for payload in (
        {"action": "group_add", "units": ["r"], "hex": "E3"},
        {"action": "group_fire"},
    ):
        cs.state, _ = cs.engine.apply(cs.state, cs.command(payload))


def _fire_case(dice: list[int]) -> dict[str, Any]:
    return {
        "phase": "prep_fire",
        "sub_step": "fire_window",
        "phasing": "russian",
        "dice": dice,
        "units": [
            {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "D3"},
            {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3"},
        ],
        "concealment": [{"side": "german", "hex": "E3"}],
    }


def test_fire_with_a_result_removes_a_dummy_as_it_removes_a_real_counter():
    """Rule 25.9: the counters of the hex go on a result that is not No Effect."""
    real, dummy = pair(_fire_case([1, 1]), ("g",))
    _fire_at_counter(real)
    _fire_at_counter(dummy)
    assert real.state.concealment == ()
    assert dummy.state.concealment == ()


def test_fire_with_no_effect_keeps_a_dummy_as_it_keeps_a_real_counter():
    """Rule 25.9: a No Effect result leaves each counter, so a counter that stays proves nothing."""
    real, dummy = pair(_fire_case([6, 6]), ("g",))
    _fire_at_counter(real)
    _fire_at_counter(dummy)
    assert len(real.state.concealment) == 1
    assert len(dummy.state.concealment) == 1


def test_fire_at_a_dummy_has_no_other_effect():
    """PR-31: the roll reads the table for the counter, and no unit takes a result."""
    real, dummy = pair(_fire_case([1, 1]), ("g",))
    before = [u for u in dummy.state.units]
    _fire_at_counter(dummy)
    after = dummy.state.units
    assert [u.eliminated for u in after] == [u.eliminated for u in before]
    assert not any(u.broken for u in after)
