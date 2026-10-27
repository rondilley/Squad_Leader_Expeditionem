"""The fire group in the windows: the side resolves it from the list or the board.

The entries are the two that the host gave the owner in a real game (lib01, the Defensive
Fire Phase, a 9-1 with its LMG aimed at Z6): one names the 9-1, and one names no unit.
"""

from __future__ import annotations

import dataclasses

from slcli.play import build_engine
from slcore.game import FireGroup
from slhost import annotate
from slhost.server import Host
from slwindow.choice import Chooser
from slwindow.overlay import next_focus

LEGAL = [
    {"id": "a", "action": "group_leader", "label": "9-1 #1 (O7) directs the fire group", "units": [{"id": 6, "name": "9-1 #1 (O7)"}], "hexes": ["O7"], "payload": {"action": "group_leader", "units": [6]}},
    {"id": "b", "action": "group_fire", "label": "resolve the fire group at Z6", "units": [], "hexes": ["Z6"], "payload": {"action": "group_fire"}},
]
VIEW = {
    "units": [
        {"id": 6, "kind": "leader", "hex": "O7", "carrier": None, "own": True},
        {"id": 13, "kind": "leader", "hex": "Z6", "carrier": None, "own": False},
    ]
}


def test_a_unit_in_focus_does_not_hide_the_entry_that_resolves_the_fire_group():
    chooser = Chooser()
    chooser.sync("f1", LEGAL)
    chooser.unit = 6
    assert [i for i, _ in chooser.visible(LEGAL, VIEW)] == [0, 1]


def test_a_click_on_the_target_of_the_fire_group_resolves_it():
    chooser = Chooser()
    chooser.sync("f1", LEGAL)
    picked = chooser.board_click(VIEW, LEGAL, "Z6", 6, next_focus)
    assert picked.send == 1
    # A click on another hex does not fire.
    assert chooser.board_click(VIEW, LEGAL, "O7", None, next_focus).send is None


def test_the_side_that_builds_a_fire_group_is_told_how_to_fire_it():
    game = Host(build_engine("lib01_grain_office"), seed=1).game
    assert annotate.fire_group_text(game.state) is None
    state = dataclasses.replace(game.state, fire_group=FireGroup((25, 6), ((6, 7),), None))
    text = annotate.fire_group_text(state)
    assert text is not None and "Z6" in text and "resolve the fire group" in text
