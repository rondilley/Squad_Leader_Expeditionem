"""Rule 25.3 with the counter of a whole hex: a unit that does not qualify stays in view.

The core keeps one counter for each side in a hex, and the counter covers each unit of
that side there (rule 25.2). Rule 25.3 gives a counter only to a unit that did not move,
fire, make smoke, or take a morale check. So a hex that holds a unit that moved gets no
counter at the end of the player turn, and that unit is not hidden from a player that saw
it move.
"""

from __future__ import annotations

from slcore.rules import r25_concealment

from conformance.harness import build_case


def _case(moved: bool) -> dict:
    return {
        "phase": "close_combat",
        "sub_step": "cc_declare",
        "actor": "phasing",
        "phasing": "russian",
        "units": [
            {"ref": "quiet", "side": "german", "type": "4-6-7", "hex": "E3"},
            {"ref": "mover", "side": "german", "type": "4-6-7", "hex": "E3", "moved": moved},
            {"ref": "r", "side": "russian", "type": "4-4-7", "hex": "J9"},
        ],
    }


def test_a_hex_of_quiet_units_gets_a_counter():
    cs = build_case(_case(moved=False))
    state, events = r25_concealment.grow(cs.state, cs.engine.board)
    assert len(state.concealment) == 1 and events


def test_a_hex_with_a_unit_that_moved_gets_no_counter():
    cs = build_case(_case(moved=True))
    state, events = r25_concealment.grow(cs.state, cs.engine.board)
    assert state.concealment == () and events == []
