"""Scripted agent v3, the tanker: a computer opponent that plays rules 28 to 41.

Agent v1 and agent v2 have no policy for a vehicle. They see `vehicle_move` and `afv_fire`
as commands they do not know, so they end the window and the tanks stand still. These tests
measure the difference, because "the agent handles armour" is a claim that only a count of
the commands it played can support.
"""

from __future__ import annotations

import collections

import pytest

from slagents.scripted.v3 import Parameters, ScriptedV3, with_parameters
from slcli.play import build_engine, make_agent, play_game
from slcore.engine import Engine

SCENARIO = "s04_armor_probe"
ARMOR_ACTIONS = ("vehicle_move", "vehicle_pivot", "afv_fire", "afv_mg", "at_fire", "afv_attack", "cc_afv")


def play_and_count(engine: Engine, kind: str, seed: int, commands: int) -> collections.Counter:
    """The actions that two agents of one kind played in the first `commands` commands."""
    state = engine.new_game(seed)
    agents = (make_agent(kind, engine, seed, 0), make_agent(kind, engine, seed, 1))
    seen: collections.Counter = collections.Counter()
    for _ in range(commands):
        if state.game_over:
            break
        frame = engine.legal_commands(state)
        if not frame.commands:
            break
        chosen = frame.by_id(agents[frame.player].select(state, frame))
        assert chosen is not None, f"{kind} gave an ID that is not in the frame"
        seen[chosen.command.action] += 1
        state, _ = engine.apply(state, chosen.command, frame)
    return seen


def test_the_tanker_is_a_named_agent():
    engine = build_engine(SCENARIO)
    agent = make_agent("v3", engine, 3, 0)
    assert isinstance(agent, ScriptedV3)
    assert agent.name == "tanker" and agent.version == "3.2"


def test_the_engineer_leaves_the_tanks_where_they_stand():
    """The measurement that agent v3 exists to change."""
    engine = build_engine(SCENARIO)
    seen = collections.Counter()
    for seed in (3, 7, 11):
        seen.update(play_and_count(engine, "v2", seed, 700))
    assert seen["vehicle_move"] == 0, "agent v2 is not supposed to know how to drive"
    assert seen["afv_fire"] == 0, "agent v2 is not supposed to know how to fire a gun"


def test_the_tanker_drives_and_fires():
    engine = build_engine(SCENARIO)
    seen = collections.Counter()
    for seed in (3, 7, 11):
        seen.update(play_and_count(engine, "v3", seed, 700))
    assert seen["vehicle_move"] > 0, f"the tanker drove nothing: {dict(seen)}"
    used = sum(seen[a] for a in ARMOR_ACTIONS)
    assert used > 20, f"the tanker played {used} armor commands: {dict(seen)}"


def test_the_tanker_keeps_the_infantry_policy_of_the_engineer():
    engine = build_engine(SCENARIO)
    seen = play_and_count(engine, "v3", 7, 700)
    assert seen["move"] > 0, f"the tanker stopped moving its infantry: {dict(seen)}"
    assert seen["place"] > 0, "the tanker did not set up"


def test_a_game_between_two_tankers_plays_and_replays():
    engine = build_engine(SCENARIO)
    record = play_game(engine, 9, (make_agent("v3", engine, 9, 0), make_agent("v3", engine, 9, 1)))
    assert record.result in tuple(engine.scenario.players()) + ("draw", "no_result")
    assert engine.replay(9, [c["payload"] for c in record.commands]) == record.hashes


def test_the_named_parameters_change_what_the_tanker_does():
    """FR-44: a parameter with a name is a parameter a sweep can turn."""
    engine = build_engine(SCENARIO)
    careful = ScriptedV3(engine, 0, with_parameters(overrun=False, pivot_to_aim=False))
    assert careful.params.overrun is False
    assert careful.params.pivot_to_aim is False
    assert Parameters().overrun is True
    state = engine.new_game(5)
    frame = engine.legal_commands(state)
    assert frame.by_id(careful.select(state, frame)) is not None


def test_the_tanker_plays_a_game_with_no_vehicle_in_it():
    """A scenario of the infantry game must not break the agent that knows about armour."""
    engine = build_engine("s01_guards_counterattack")
    seen = play_and_count(engine, "v3", 4, 400)
    assert sum(seen[a] for a in ARMOR_ACTIONS) == 0
    assert seen["move"] > 0 or seen["place"] > 0
