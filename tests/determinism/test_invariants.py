"""Core invariants that must hold in every state of a game.

The first one is the reason the throughput run stopped on 2026-09-07: a state with no
legal command leaves a player with nothing to do and no way to end the game.
"""

from __future__ import annotations

import pytest

from slagents.base import RandomAgent
from slcore.rules import r06_stacking
from slcli.play import build_engine

SEEDS = [1, 2, 3, 4010, 5001, 6002, 7003, 8004]


@pytest.fixture(scope="module")
def engine():
    return build_engine("s01_guards_counterattack")


@pytest.mark.slow
@pytest.mark.parametrize("seed", SEEDS)
def test_a_state_that_is_not_over_always_has_a_legal_command(engine, seed):
    agents = (RandomAgent(seed, 0), RandomAgent(seed, 1))
    state = engine.new_game(seed)
    steps = 0
    while not state.game_over:
        frame = engine.legal_commands(state)
        assert frame.commands, f"no legal command in {state.phase}/{frame.sub_step} for player {state.active} at step {steps}"
        legal = frame.by_id(agents[state.active].select(state, frame))
        state, _ = engine.apply(state, legal.command, frame)
        steps += 1
    assert steps > 100


@pytest.mark.slow
def test_no_player_ends_a_phase_over_a_stacking_limit(engine):
    """Rule 6.1 holds for each player except during the Movement Phase (rule 6.3)."""
    seed = 12
    agents = (RandomAgent(seed, 0), RandomAgent(seed, 1))
    state = engine.new_game(seed)
    while not state.game_over:
        frame = engine.legal_commands(state)
        if state.phase not in ("movement", "setup", "defensive_fire"):
            for player in (0, 1):
                over = r06_stacking.overstacked_hexes(state, engine.types, player)
                assert not over, f"player {player} is over a limit in {over} during {state.phase}"
        legal = frame.by_id(agents[state.active].select(state, frame))
        state, _ = engine.apply(state, legal.command, frame)


def test_the_stacking_limit_counts_one_player(engine):
    """Rule 6.1 gives the limit to each player, and rule 6.2 lets both sides share a hex."""
    state = engine.new_game(1)
    german = [u for u in state.units if u.player == 1 and u.kind == "squad"][:3]
    russian = [u for u in state.units if u.player == 0 and u.kind == "squad"][:3]
    hex_ref = engine.board.order[20]
    changed = {u.id: u.with_(hex=hex_ref) for u in german + russian}
    state = state.with_units(changed)
    assert r06_stacking.hex_load(state, engine.types, hex_ref, 1) == (3, 3, 0)
    assert r06_stacking.hex_load(state, engine.types, hex_ref, 0) == (3, 3, 0)
    assert not r06_stacking.rule_6_1_overstacked(state, engine.types, hex_ref, 0)
    assert not r06_stacking.rule_6_1_overstacked(state, engine.types, hex_ref, 1)
