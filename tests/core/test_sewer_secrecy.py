"""S11 and PR-35: a sewer move leaves no track and arrives below a counter.

Rule 27.4 makes the stack immune to fire in each hex but the one it comes up in, so no
hex of its route is a target hex of rule 16.1. Rule 27.5 covers the stack with a counter
when no enemy is next to it in the building, and the counter goes on at the arrival.
"""

from __future__ import annotations

from slcore import view

from conformance.harness import build_case


def _sewer_case() -> dict:
    return {
        "phase": "movement",
        "sub_step": "move_window",
        "phasing": "german",
        "dice": [3],
        "single_dice": True,
        "units": [
            {"ref": "s", "side": "german", "type": "4-6-7", "hex": "C5"},
            {"ref": "l", "side": "german", "type": "9-1", "hex": "C5"},
            {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "H3"},
        ],
    }


def _arrive(cs):
    sewer = [lc.command for lc in cs.engine.legal_commands(cs.state).commands if lc.command.action == "sewer_move"]
    assert sewer
    cs.state, events = cs.engine.apply(cs.state, sewer[0])
    return events


def test_the_stack_arrives_below_a_counter_at_once():
    cs = build_case(_sewer_case())
    _arrive(cs)
    assert cs.unit("s").hex is not None and cs.unit("s").hex != cs.unit("r").hex
    russian = cs.engine.scenario.side_index("russian")
    assert not view.visible_to(cs.state, cs.unit("s"), russian), "the arrival is not in full view"
    assert not view.visible_to(cs.state, cs.unit("l"), russian)
    assert len(cs.state.concealment) == 1


def test_the_sewer_move_leaves_no_track():
    cs = build_case(_sewer_case())
    _arrive(cs)
    assert cs.unit("s").track == ()
    assert cs.unit("l").track == ()


def test_the_defender_gets_no_return_that_names_the_stack():
    cs = build_case(_sewer_case())
    _arrive(cs)
    cs.state, _ = cs.engine.apply(cs.state, cs.command({"action": "end_phase"}))
    assert cs.state.phase == "defensive_fire"
    for lc in cs.engine.legal_commands(cs.state).commands:
        assert lc.command.action != "track_return"


def test_no_counter_covers_a_unit_that_came_into_the_hex_in_view():
    """Rule 25.41: a unit that moved into the arrival hex in view stays in view.

    A counter covers each unit of its hex, so the arrival hex of such a unit gets no
    counter, and the track of that unit never names a unit the defender cannot see.
    """
    case = _sewer_case()
    case["units"].append({"ref": "w", "side": "german", "type": "4-6-7", "hex": "E4"})
    cs = build_case(case)
    cs.state, _ = cs.engine.apply(cs.state, cs.command({"action": "move", "units": ["w"], "hex": "E5"}))
    cs.state, _ = cs.engine.apply(cs.state, cs.command({"action": "sewer_move", "units": ["l", "s"], "hex": "E5"}))
    assert cs.unit("s").hex == cs.unit("w").hex
    assert cs.state.concealment == ()
    russian = cs.engine.scenario.side_index("russian")
    assert view.visible_to(cs.state, cs.unit("w"), russian)


def test_a_unit_that_made_a_sewer_move_makes_no_other_move():
    cs = build_case(_sewer_case())
    _arrive(cs)
    for lc in cs.engine.legal_commands(cs.state).commands:
        if lc.command.action in ("move", "stack_move", "sewer_move"):
            assert cs.ids["s"] not in lc.command.units and cs.ids["l"] not in lc.command.units
