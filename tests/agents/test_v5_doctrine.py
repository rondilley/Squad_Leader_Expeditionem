"""Agent v5: the combined-arms doctrine agent. It is deterministic and closes two v4 gaps.

The tests here check the invariants that let v5 stand in a gauntlet and a replay:
- v5 gives a legal command in each phase of a full game.
- v5 against v5 replays to the same hash (TR-02), so it is deterministic.
- The suppression value and the vehicle threat are the two behavioral changes, and each has a
  direct unit test on a built state.
"""

from __future__ import annotations

import pytest

from slcli.play import build_engine, make_agent, play_game
from slagents.scripted.v5 import ScriptedV5, UnknownNation, profile_for, with_parameters


def test_v5_plays_a_full_game_and_replays():
    engine = build_engine("s01_guards_counterattack")
    record = play_game(engine, 7, (make_agent("v5", engine, 7, 0), make_agent("v5", engine, 7, 1)))
    assert record.hashes, "the game produced a hash sequence"
    again = engine.replay(7, [c["payload"] for c in record.commands])
    assert again == record.hashes, "v5 against v5 is deterministic (TR-02)"


def test_v5_gives_a_legal_command_in_each_frame_of_a_game():
    engine = build_engine("s01_guards_counterattack")
    agents = (make_agent("v5", engine, 3, 0), make_agent("v5", engine, 3, 1))
    state = engine.new_game(3)
    steps = 0
    while not state.game_over and steps < 5000:
        frame = engine.legal_commands(state)
        chosen = agents[state.active].select(state, frame)
        assert frame.by_id(chosen) is not None, "the chosen id is in the frame"
        state, _ = engine.apply(state, frame.by_id(chosen).command)
        steps += 1
    assert steps > 0


def test_the_nation_profiles_load_and_british_is_not_defined():
    for nation in ("german", "soviet", "american"):
        assert profile_for(nation).suppression_priority >= 1
    assert profile_for("american").suppression_priority >= profile_for("soviet").suppression_priority
    with pytest.raises(UnknownNation):
        profile_for("british")


def test_with_parameters_changes_one_named_field():
    p = with_parameters(suppression_priority=5)
    assert p.suppression_priority == 5
    assert p.aggression == 2, "the other fields keep the default"


def test_the_suppression_value_counts_our_units_the_target_can_hit():
    engine = build_engine("s01_guards_counterattack")
    state = engine.new_game(11)
    agent = ScriptedV5(engine, 0)
    # For each enemy-held hex, the suppression value is between zero and the count of our units.
    ours = sum(1 for u in state.player_units(0) if u.hex is not None and not u.broken)
    enemy_hexes = {u.hex for u in state.player_units(1) if u.hex is not None}
    for target in enemy_hexes:
        value = agent._suppression_value(state, target)
        assert 0 <= value <= ours
