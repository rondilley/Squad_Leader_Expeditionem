"""The doctrine agent v4 (fire and maneuver, do not move under fire).

These tests prove v4 exists as version 4, that it plays each scenario to the end, that it is
deterministic, that it is a different policy from v1 (not v1 with a new name), that its nation
profiles build, and that its threat map runs and never returns a negative value. The proof
that the doctrine helps is the tournament artifact (v4 beats v1), not a unit test; a unit test
cannot measure win rate in the time a commit can afford.
"""

from __future__ import annotations

import pytest

from slcore.game import PHASE_MOVEMENT
from slagents.scripted.v1 import ScriptedV1
from slagents.scripted.v4 import (
    NATION_PROFILES,
    Parameters,
    ScriptedV4,
    UnknownNation,
    profile_for,
)
from slcli.play import build_engine, make_agent, play_game

SCENARIOS = ("s01_guards_counterattack", "s02_tractor_works")


def test_v4_is_the_doctrine_agent_version_4():
    engine = build_engine("s01_guards_counterattack")
    agent = make_agent("v4", engine, 1, 0)
    assert isinstance(agent, ScriptedV4)
    assert (agent.name, agent.version) == ("scripted", "4")


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_v4_plays_each_scenario_to_the_end(scenario):
    engine = build_engine(scenario)
    a = make_agent("v4", engine, 7, 0)
    b = make_agent("v1", engine, 7, 1)
    record = play_game(engine, 7, (a, b))  # raises if the game does not end
    assert record.result in ("russian", "german", "american", "draw")


def test_v4_is_deterministic():
    engine = build_engine("s01_guards_counterattack")
    agent = make_agent("v4", engine, 1, 0)
    state = engine.new_game(1)
    frame = engine.legal_commands(state)
    assert agent.select(state, frame) == agent.select(state, frame)


def test_v4_is_a_different_policy_from_v1():
    """The doctrine changes decisions, so the command log is not the v1 command log."""
    engine = build_engine("s01_guards_counterattack")
    v4_vs_v1 = play_game(engine, 5, (make_agent("v4", engine, 5, 0), make_agent("v1", engine, 5, 1)))
    v1_vs_v1 = play_game(engine, 5, (make_agent("v1", engine, 5, 0), make_agent("v1", engine, 5, 1)))
    ids_a = [c["command_id"] for c in v4_vs_v1.commands]
    ids_b = [c["command_id"] for c in v1_vs_v1.commands]
    assert ids_a != ids_b


def test_nation_profiles_build_and_differ():
    engine = build_engine("s01_guards_counterattack")
    for nation in NATION_PROFILES:
        agent = make_agent(f"v4:{nation}", engine, 1, 0)
        assert isinstance(agent, ScriptedV4)
    # The American profile is more cautious than the German one (higher threat aversion).
    assert profile_for("american").threat_aversion > profile_for("german").threat_aversion


def test_british_profile_is_not_defined_yet():
    with pytest.raises(UnknownNation):
        profile_for("british")


def test_the_threat_map_runs_and_is_never_negative():
    """The threat of a hex is a sum of enemy firepower, so it is a non-negative integer."""
    engine = build_engine("s01_guards_counterattack")
    agent = ScriptedV4(engine, 0)
    other = make_agent("v1", engine, 3, 1)
    state = engine.new_game(3)
    # Step with real agents until a movement frame of our player, or the game ends.
    steps = 0
    while not state.game_over and steps < 4000:
        frame = engine.legal_commands(state)
        if frame.phase == PHASE_MOVEMENT and state.active == 0 and any(
            lc.command.action in ("move", "stack_move") for lc in frame.commands
        ):
            cache: dict = {}
            saw_move = False
            for lc in frame.commands:
                if lc.command.action in ("move", "stack_move") and lc.command.hex is not None:
                    threat = agent._threat(state, lc.command.hex, cache)
                    assert isinstance(threat, int) and threat >= 0
                    saw_move = True
            assert saw_move
            return
        chooser = agent if state.active == 0 else other
        chosen = chooser.select(state, frame)
        state, _ = engine.apply(state, frame.by_id(chosen).command, frame)
        steps += 1
    pytest.skip("no movement frame with a move option was reached in this game")


def test_v4_parameters_are_a_superset_of_v1():
    p = Parameters()
    for name in ("aggression", "cover_preference", "fire_priority", "group_size", "advance_into_close_combat"):
        assert hasattr(p, name)
    for name in ("threat_aversion", "superiority_tenths"):
        assert hasattr(p, name)
