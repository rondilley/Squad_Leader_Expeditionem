"""The fire preview: the odds of a fire group before its dice (rules 10.3 and 10.5).

The states are real: two v1 agents play scenario 1, and the test reads the preview at each
frame where the acting player builds a fire group. When that player fires the group, the
fire event of the core must give the same firepower and column as the preview, and the same
modifier total when no modifier of the hidden kinds applies.
"""

from __future__ import annotations

import pytest

from slagents.scripted.v1 import ScriptedV1
from slcli.play import build_engine
from slhost.server import Host
from slwindow3d.selection import preview_text

SCENARIO = "s01_guards_counterattack"
HIDDEN_RULES = {"22.7", "24.6", "24.7"}


def _fires(seed: int, limit: int = 4000):
    """Each (preview, fire event) of a game: the preview just before the group fires."""
    engine = build_engine(SCENARIO)
    state = engine.new_game(seed)
    agents = {seat: ScriptedV1(engine, seat) for seat in (0, 1)}
    count = 0
    while not state.game_over and count < limit:
        frame = engine.legal_commands(state)
        chosen = agents[state.active].select(state, frame)
        legal = frame.by_id(chosen)
        preview = engine.fire_preview(state)
        before = engine.hash_state(state)
        if preview is not None:
            again = engine.fire_preview(state)
            assert again == preview
            assert engine.hash_state(state) == before, "the preview changed the state"
        state, events = engine.apply(state, legal.command, frame)
        if legal.payload["action"] == "group_fire":
            fire = next(e for e in events if e.kind == "fire")
            yield preview, fire.data
        count += 1


def test_the_preview_agrees_with_the_fire_that_follows_it():
    checked = 0
    exact = 0
    for preview, fire in _fires(seed=3):
        assert preview is not None, "a group fired with no preview"
        assert preview["target"] == fire["target"]
        assert preview["firepower"] == fire["firepower"]
        assert preview["column"] == fire["column"]
        assert sum(preview["rolls_of_36"].values()) == 36
        fired_rules = {str(part["rule"]) for part in fire["modifiers"]}
        if not fired_rules & HIDDEN_RULES:
            # With no hidden modifier, the modifier total of the fire is the preview's.
            assert fire["adjusted"] - sum(fire["dice"]) == preview["drm"]
            exact += 1
        checked += 1
    assert checked >= 10
    assert exact >= 5


def test_the_host_gives_the_preview_only_to_the_player_who_acts():
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=3, agents={1: ScriptedV1(engine, 1)})
    person = ScriptedV1(engine, 0)
    host.run_agents()
    seen = False
    for _ in range(3000):
        state = host.game.state
        if state.game_over:
            break
        if state.fire_group is not None and state.fire_group.members and state.active == 0:
            assert host.preview_for(0) is not None
            assert host.preview_for(1) is None
            seen = True
            break
        frame = engine.legal_commands(state)
        host.game.apply(frame.frame_id, person.select(state, frame))
        host.run_agents()
    assert seen, "the person never built a fire group"


def test_the_window_line_names_the_column_the_modifiers_and_the_odds():
    preview, _ = next(iter(_fires(seed=3)))
    text = preview_text(preview)
    assert text.startswith(f"Fire at {preview['target']}: {preview['firepower']} FP (column {preview['column']})")
    assert "Of 36 rolls:" in text
    for part in preview["modifiers"]:
        assert str(part["rule"]) in text
    assert preview_text(None) == ""


@pytest.mark.parametrize("name,words", [("KIA", "KIA"), ("M", "MC"), ("2", "MC+2"), ("-", "no effect")])
def test_result_names(name, words):
    from slwindow3d.selection import result_name

    assert result_name(name) == words
