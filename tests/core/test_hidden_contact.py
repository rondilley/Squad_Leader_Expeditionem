"""S5 and PR-32: a stack move, an advance, and a rout that meet a hidden unit.

Rule 42.5 stops a unit that moves into the hex of a hidden unit in the hex it came from.
A stack move is the move of each unit of the stack. An advance may enter an enemy hex, so
the hidden unit comes on the board at once, and the close combat list then names a unit
the other player sees.
"""

from __future__ import annotations

from slcore import geometry, view
from slcore.rules import r42_hidden

from conformance.harness import build_case


def test_a_stack_move_into_a_hidden_unit_stops_each_unit_of_the_stack():
    cs = build_case(
        {
            "phase": "movement",
            "sub_step": "move_window",
            "phasing": "russian",
            "units": [
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "D2"},
                {"ref": "lead", "side": "russian", "type": "8-1", "hex": "D2"},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3", "hidden": True},
            ],
        }
    )
    events = []
    cs.state, ev = cs.engine.apply(cs.state, cs.command({"action": "stack_move", "units": ["r", "lead"], "hex": "E3"}))
    events.extend(e.to_dict() for e in ev)
    for ref in ("r", "lead"):
        assert geometry.hex_id(*cs.unit(ref).hex) == "D2", f"unit {ref} stops in the hex it came from"
    stopped = [e for e in events if e["kind"] == "stopped" and e["rule_id"] == "42.5"]
    assert len(stopped) == 2
    assert cs.unit("g").hidden, "rule 42.5 does not put the unit on the board"
    ids = [lc.payload for lc in cs.engine.legal_commands(cs.state).commands]
    assert not any(p["action"] in ("move", "stack_move") and cs.ids["r"] in p.get("units", []) for p in ids)


def test_an_advance_into_a_hidden_unit_puts_it_on_the_board():
    cs = build_case(
        {
            "phase": "advance",
            "sub_step": "advance_window",
            "phasing": "russian",
            "units": [
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "D3"},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3", "hidden": True},
            ],
        }
    )
    cs.state, ev = cs.engine.apply(cs.state, cs.command({"action": "advance", "units": ["r"], "hex": "E3"}))
    assert not cs.unit("g").hidden
    assert any(e.kind == "revealed" and e.data["unit"] == cs.ids["g"] for e in ev)
    russian = cs.engine.scenario.side_index("russian")
    assert view.visible_to(cs.state, cs.unit("g"), russian)


def test_the_close_combat_list_never_names_a_hidden_unit_after_an_advance():
    cs = build_case(
        {
            "phase": "advance",
            "sub_step": "advance_window",
            "phasing": "russian",
            "units": [
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "D3"},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3", "hidden": True},
            ],
        }
    )
    cs.state, _ = cs.engine.apply(cs.state, cs.command({"action": "advance", "units": ["r"], "hex": "E3"}))
    cs.state, _ = cs.engine.apply(cs.state, cs.command({"action": "end_phase"}))
    assert cs.state.phase == "close_combat"
    russian = cs.engine.scenario.side_index("russian")
    for lc in cs.engine.legal_commands(cs.state).commands:
        for target in lc.payload.get("targets", []):
            assert view.visible_to(cs.state, cs.state.units[target], russian)


def test_the_adjacency_test_of_rule_42_2_reads_the_hex_of_the_hidden_unit():
    cs = build_case(
        {
            "phase": "advance",
            "sub_step": "advance_window",
            "phasing": "russian",
            "units": [
                {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "E3"},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3", "hidden": True},
            ],
        }
    )
    state, events = r42_hidden.refresh_adjacency(cs.state, cs.engine.board)
    assert not state.units[cs.ids["g"]].hidden
    assert events and events[0].rule_id == "42.2"


def test_a_rout_stops_before_the_hex_of_a_hidden_unit():
    cs = build_case(
        {
            "phase": "rout",
            "sub_step": "rout_window",
            "actor": "phasing",
            "phasing": "russian",
            "units": [
                {"ref": "b", "side": "russian", "type": "4-4-7", "hex": "D2", "broken": True},
                {"ref": "g", "side": "german", "type": "4-6-7", "hex": "E3", "hidden": True},
            ],
        }
    )
    frame = [lc.payload for lc in cs.engine.legal_commands(cs.state).commands]
    into = [p for p in frame if p["action"] == "rout" and p["hex"] == "E3"]
    assert into, "the hidden unit does not close the hex in the list, so the list tells nothing"
    cs.state, ev = cs.engine.apply(cs.state, cs.command(into[0]))
    assert geometry.hex_id(*cs.unit("b").hex) == "D2"
    assert any(e.rule_id == "42.5" and e.kind == "stopped" for e in ev)
    assert cs.unit("g").hidden
