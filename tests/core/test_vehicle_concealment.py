"""S6 and S7: only infantry is concealed, and each firing or moving act unconceals its unit.

Rule 25.3 puts a counter on a squad or a leader (PR-33). Rules 25.4 and 42.2 remove the
counter and the hidden status of a unit that fires, moves, or makes smoke, whatever the
weapon: an anti-tank weapon and a vehicle gun as well (PR-34).
"""

from __future__ import annotations

import pytest

from slcore import view
from slcore.actions import ACTION_SPECS, UNCONCEALING
from slcore.commands import ACTIONS

from conformance.harness import build_case


def test_each_action_has_one_property():
    assert set(ACTION_SPECS) == set(ACTIONS)


@pytest.mark.parametrize(
    "action",
    ["at_fire", "afv_fire", "afv_mg", "afv_attack", "cc_afv", "afv_smoke", "afv_dischargers", "vehicle_move", "vehicle_pivot"],
)
def test_the_armour_acts_unconceal(action):
    assert action in UNCONCEALING


def test_a_vehicle_below_a_counter_of_its_side_stays_in_view():
    cs = build_case(
        {
            "phase": "movement",
            "sub_step": "move_window",
            "phasing": "russian",
            "units": [
                {"ref": "t", "side": "russian", "type": "T34", "hex": "D3", "facing": 0},
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "E3"},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "H3"},
            ],
            "concealment": [{"side": "russian", "hex": "E3"}],
        }
    )
    moves = [lc.command for lc in cs.engine.legal_commands(cs.state).commands if lc.command.action == "vehicle_move"]
    into = [c for c in moves if c.hex is not None and c.units == (cs.ids["t"],) and c.hex == cs.unit("r").hex]
    assert into, "the tank may drive into the hex of its own infantry"
    cs.state, _ = cs.engine.apply(cs.state, into[0])
    german = cs.engine.scenario.side_index("german")
    assert view.visible_to(cs.state, cs.unit("t"), german), "a vehicle is never below a counter"
    assert not cs.state.concealed(cs.unit("t"))
    assert len(cs.state.concealment) == 1, "the counter stays over the squad"
    assert not view.visible_to(cs.state, cs.unit("r"), german)


def test_a_panzerfaust_shot_removes_the_counter_of_the_firer():
    cs = build_case(
        {
            "phase": "defensive_fire",
            "sub_step": "fire_window",
            "phasing": "russian",
            "units": [
                {"ref": "t", "side": "russian", "type": "T34", "hex": "D3", "facing": 1},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3"},
                {"ref": "pf", "side": "german", "type": "PF", "carrier": "g"},
            ],
            "concealment": [{"side": "german", "hex": "E3"}],
        }
    )
    shots = [lc.command for lc in cs.engine.legal_commands(cs.state).commands if lc.command.action == "at_fire"]
    assert shots
    cs.state, events = cs.engine.apply(cs.state, shots[0])
    assert cs.state.concealment == (), "rule 25.4: the firer loses its counter"
    assert any(e.kind == "unconcealed" and e.rule_id == "25.4" for e in events)


def test_a_hidden_panzerfaust_team_comes_on_the_board_when_it_fires():
    cs = build_case(
        {
            "phase": "defensive_fire",
            "sub_step": "fire_window",
            "phasing": "russian",
            "units": [
                {"ref": "t", "side": "russian", "type": "T34", "hex": "D3", "facing": 1},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3", "hidden": True},
                {"ref": "pf", "side": "german", "type": "PF", "carrier": "g"},
            ],
        }
    )
    shots = [lc.command for lc in cs.engine.legal_commands(cs.state).commands if lc.command.action == "at_fire"]
    assert shots
    cs.state, events = cs.engine.apply(cs.state, shots[0])
    assert not cs.unit("g").hidden, "rule 42.2: the unit fired"


def test_a_hidden_tank_comes_on_the_board_when_its_gun_fires():
    cs = build_case(
        {
            "phase": "prep_fire",
            "sub_step": "fire_window",
            "phasing": "german",
            "units": [
                {"ref": "t", "side": "german", "type": "MkIVF2", "hex": "E3", "facing": 4, "hidden": True},
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "C2"},
            ],
        }
    )
    shots = [lc.command for lc in cs.engine.legal_commands(cs.state).commands if lc.command.action in ("afv_fire", "afv_mg")]
    assert shots
    cs.state, _ = cs.engine.apply(cs.state, shots[0])
    assert not cs.unit("t").hidden, "rule 42.2: the vehicle fired"
