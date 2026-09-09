"""Scenarios 2 and 3A (FR-18, TC-04) with the rules that come in with them.

Scenario 2 brings rules 22 to 26. Scenario 3A joins scenarios 1 and 2 on the whole board
and brings rule 27. The tests here play real games and read the events, because a rule
that the conformance corpus proves in one state can still be unreachable in a game.

A whole game of scenario 2 is about two thousand commands, so the tests that only need to
see a rule appear play a bounded part of a game. The two tests that prove a scenario plays
to its end and replays play the whole game and carry the `slow` marker.
"""

from __future__ import annotations

import collections

import pytest

from slagents.base import RandomAgent
from slcli.play import build_engine, build_engine_with_record, make_agent, play_game
from slcore.engine import Engine
from slcore.rules import r22_flamethrower

SCENARIO_2 = "s02_tractor_works"
SCENARIO_3A = "s03a_streets_of_stalingrad"


def play_bounded(engine: Engine, seed: int, commands: int) -> collections.Counter:
    """The rule IDs that the first `commands` commands of one random game applied."""
    state = engine.new_game(seed)
    agents = (RandomAgent(seed, 0), RandomAgent(seed + 1, 1))
    seen: collections.Counter = collections.Counter()
    for _ in range(commands):
        if state.game_over:
            break
        frame = engine.legal_commands(state)
        if not frame.commands:
            break
        chosen = frame.by_id(agents[frame.player].select(state, frame))
        assert chosen is not None, "an agent selects a command of the frame"
        state, events = engine.apply(state, chosen.command, frame)
        seen.update(e.rule_id for e in events)
    return seen


@pytest.mark.slow
def test_scenario_two_plays_to_the_end_and_replays():
    engine = build_engine(SCENARIO_2)
    record = play_game(engine, 11, (make_agent("v1", engine, 11, 0), make_agent("v1", engine, 11, 1)))
    assert record.turns_played == 8
    assert record.result in ("german", "russian", "draw", "no_result")
    assert engine.replay(11, [c["payload"] for c in record.commands]) == record.hashes


@pytest.mark.slow
def test_scenario_three_a_plays_the_whole_board_and_replays():
    engine, board_record = build_engine_with_record(SCENARIO_3A)
    assert board_record["board_columns"] is None, "scenario 3A uses the whole board"
    assert engine.board.cols == 33
    record = play_game(engine, 3, (make_agent("v1", engine, 3, 0), make_agent("v1", engine, 3, 1)))
    assert record.turns_played == 7
    assert engine.replay(3, [c["payload"] for c in record.commands]) == record.hashes


def test_the_first_mover_comes_from_the_die():
    """Project ruling PR-12: the card says to roll, and the core generator rolls."""
    engine = build_engine(SCENARIO_2)
    phasings = set()
    for seed in range(1, 30):
        state = engine.new_game(seed)
        while state.phase == "setup":
            frame = engine.legal_commands(state)
            chosen = frame.by_id(RandomAgent(seed, frame.player).select(state, frame))
            state, _ = engine.apply(state, chosen.command, frame)
        phasings.add(state.phasing)
    assert phasings == {0, 1}, "the die gives the first player turn to each side over a set of seeds"


def test_the_new_rules_of_scenario_two_reach_a_game():
    """TC-04 with rules 22 to 26: the commands of the new rules are reachable."""
    engine = build_engine(SCENARIO_2)
    seen: collections.Counter = collections.Counter()
    for seed in (20, 21, 22):
        seen.update(play_bounded(engine, seed, 900))
    assert seen["25.6"] > 0, "the scenario gives concealment counters at set up"
    assert seen["25.3"] > 0, "counters grow at the end of a player turn"
    assert seen["25.4"] > 0, "and they come off when a unit acts"
    assert seen["24.3"] > 0, "the engineers make smoke"
    assert seen["24.8"] > 0, "and the smoke goes at the next Prep Fire Phase"
    assert seen["23.3"] > 0, "the engineers place demolition charges"


def test_a_flamethrower_is_offered_when_a_target_is_in_range():
    """Rule 22: the command exists in the fire window of a real scenario 2 state."""
    engine = build_engine(SCENARIO_2)
    state = engine.new_game(5)
    engineer = next(u for u in state.player_units(0) if engine.types[u.type_key].assault_engineer)
    weapon = next(u for u in state.player_units(0) if r22_flamethrower.is_flamethrower(engine.types, u))
    target = next(u for u in state.player_units(1) if u.is_infantry)
    here, there = (10, 5), (10, 4)
    assert here in engine.board and there in engine.board
    state = state.with_units(
        {
            engineer.id: engineer.with_(hex=here),
            weapon.id: weapon.with_(hex=here, carrier=engineer.id),
            target.id: target.with_(hex=there),
        }
    )
    state = state.with_(phase="prep_fire", sub_step=2, setup_index=3, phasing=0, active=0)
    actions = {c.command.action for c in engine.legal_commands(state).commands}
    assert "ft_fire" in actions, "the flamethrower of an engineer squad can fire at an adjacent hex"


def test_scenario_three_a_reaches_the_sewers():
    """Rule 27: over a set of seeds the random agent goes down a sewer entrance."""
    engine = build_engine(SCENARIO_3A)
    seen: collections.Counter = collections.Counter()
    for seed in range(30, 36):
        seen.update(play_bounded(engine, seed, 1200))
    assert seen["27.22"] > 0, "a stack used sewer movement"


def test_the_scenarios_name_the_rules_they_introduce():
    for name, wanted in ((SCENARIO_2, "26"), (SCENARIO_3A, "27")):
        engine = build_engine(name)
        assert wanted in engine.scenario.rules_used, f"{name} names rule {wanted}"


def test_every_concealment_counter_of_the_scenario_reaches_the_board():
    """Rule 25.6 with project ruling PR-17: the side cannot end set up while it holds one."""
    engine = build_engine(SCENARIO_2)
    allowance = engine.concealment_allowance()
    assert allowance == {0: 12, 1: 18}, allowance
    for seed in (4, 9):
        state = engine.new_game(seed)
        while state.phase == "setup":
            frame = engine.legal_commands(state)
            chosen = frame.by_id(RandomAgent(seed, frame.player).select(state, frame))
            state, _ = engine.apply(state, chosen.command, frame)
        placed = collections.Counter(c.player for c in state.concealment)
        assert dict(placed) == allowance, f"seed {seed} placed {dict(placed)}"


def test_a_counter_can_go_on_a_hex_with_no_unit_below_it():
    """Rule 25.7: a dummy is a counter with nothing below it, and it needs room to exist."""
    engine = build_engine(SCENARIO_2)
    seed = 4
    state = engine.new_game(seed)
    while state.phase == "setup":
        frame = engine.legal_commands(state)
        chosen = frame.by_id(RandomAgent(seed, frame.player).select(state, frame))
        state, _ = engine.apply(state, chosen.command, frame)
    occupied = {(u.hex, u.player) for u in state.units if u.hex is not None and u.carrier is None}
    dummies = [c for c in state.concealment if (c.hex, c.player) not in occupied]
    assert dummies, "no counter went on an empty hex, so rule 25.7 has no dummy"


def test_a_counter_may_not_go_in_the_set_up_area_of_the_other_side():
    """Project ruling PR-17: the one place a counter cannot go."""
    engine = build_engine(SCENARIO_2)
    state = engine.new_game(4)
    enemy_hexes = set()
    for group in engine.scenario.side_spec("russian").groups:
        enemy_hexes.update(group.area.resolve(engine.board))
    assert state.active == engine.scenario.side_index("russian"), "the Russians set up first"
    german = engine.scenario.side_index("german")
    allowed = set(engine._concealment_hexes(state, german))
    assert allowed, "the German side has hexes for its counters"
    assert not (allowed & enemy_hexes), "and none of them is in a Russian set up area"
