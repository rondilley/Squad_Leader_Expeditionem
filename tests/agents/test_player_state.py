"""S3 and S4: an agent decides from the state its player may know, and from nothing more.

The first tests read `slcore.player_state.for_player` on real states of scenarios 2, 3A, 4,
and 0C. The last test plays a full game of scenarios 2 and 3A with each scripted agent v1
to v7 through `play_game`. A wrapper around each agent examines each state it gets: no
enemy unit on the board below a concealment counter of the enemy, no enemy hidden unit,
and not the true generator. After the game a replay gives the true state of each decision,
and `player_state.leaks` compares the two.
"""

from __future__ import annotations

import pytest

from slagents.base import RandomAgent, decide
from slcli.play import build_engine, make_agent, play_game
from slcore import player_state, view
from slcore.engine import Engine
from slcore.frame import DecisionFrame
from slcore.game import State

SCENARIOS = ("s02_tractor_works", "s03a_streets_of_stalingrad", "s04_armor_probe", "s00c_two_board_advance")


def states_with_secrets(engine: Engine, seed: int, limit: int = 1500) -> list[State]:
    """States of a random game where one player or the other has a unit it may not see."""
    agents = (RandomAgent(seed, 0), RandomAgent(seed, 1))
    state = engine.new_game(seed)
    found: list[State] = []
    for _ in range(limit):
        if state.game_over:
            break
        if any(player_state.masked(state, u, p) for p in (0, 1) for u in state.units):
            found.append(state)
        frame = engine.legal_commands(state)
        chosen = frame.by_id(agents[frame.player].select(state, frame))
        state, _ = engine.apply(state, chosen.command, frame)
    return found


@pytest.mark.slow
@pytest.mark.parametrize("scenario", SCENARIOS)
def test_the_player_state_has_no_unit_the_view_hides(scenario: str):
    engine = build_engine(scenario)
    states = states_with_secrets(engine, 3)
    assert states, f"{scenario}: the random game gave no state with a secret unit"
    for state in states[:: max(1, len(states) // 40)]:
        for player in (0, 1):
            known = player_state.for_player(state, player)
            assert player_state.leaks(state, known, player) == []
            assert known.rng != state.rng and known.seed == player_state.MASKED_SEED
            assert known.concealment == state.concealment, "a concealment counter is public (rule 25.2)"
            for u in state.units:
                if u.player == player:
                    assert known.units[u.id] == u, "the player's own units are the true units"
                elif view.visible_to(state, u, player):
                    assert known.units[u.id] == u, "an enemy unit in view stays as it is"
                else:
                    assert known.units[u.id].hex is None and not view.visible_to(known, known.units[u.id], player)
            # The view of the player is the same from the two states.
            assert view.build(known, engine.types, player) == view.build(state, engine.types, player)


def test_the_player_state_is_a_fixed_point():
    engine = build_engine("s02_tractor_works")
    state = states_with_secrets(engine, 5, limit=500)[-1]
    once = player_state.for_player(state, 0)
    assert player_state.for_player(once, 0) == once


@pytest.mark.slow
def test_the_core_applies_a_command_on_the_player_state():
    """A lookahead with the core `apply` on the player state does not fail on a missing unit."""
    engine = build_engine("s03a_streets_of_stalingrad")
    for state in states_with_secrets(engine, 7)[::25]:
        known = player_state.for_player(state, state.active)
        frame = engine.legal_commands(known)
        for lc in frame.commands[:30]:
            after, _ = engine.apply(known, lc.command, frame)
            assert after.seq == known.seq + 1


class Watched:
    """An agent wrapper that examines each state its agent gets."""

    def __init__(self, inner, player: int) -> None:
        self.inner = inner
        self.player = player
        self.name = inner.name
        self.version = getattr(inner, "version", "0")
        self.seen: list[State] = []

    def select(self, state: State, frame: DecisionFrame) -> str:
        assert frame.player == self.player
        assert state.rng == player_state.MASKED_RNG, "the agent got the true generator"
        assert state.seed == player_state.MASKED_SEED, "the agent got the true seed"
        for u in state.units:
            if u.player == self.player or u.eliminated:
                continue
            assert not u.hidden, f"the agent got the hidden unit {u.id}"
            if u.hex is not None or u.carrier is not None:
                assert view.visible_to(state, u, self.player), f"the agent got the unit {u.id} below a counter"
        self.seen.append(state)
        return self.inner.select(state, frame)


@pytest.mark.slow
@pytest.mark.parametrize("scenario", ("s02_tractor_works", "s03a_streets_of_stalingrad"))
@pytest.mark.parametrize("name", ("v1", "v2", "v3", "v4", "v5", "v6", "v7"))
def test_each_scripted_agent_plays_a_full_game_from_the_player_state(scenario: str, name: str):
    engine = build_engine(scenario)
    seed = 11
    watched = (Watched(make_agent(name, engine, seed, 0), 0), Watched(make_agent(name, engine, seed, 1), 1))
    record = play_game(engine, seed, watched)
    # The replay gives the true state of each decision. The seq of a state counts its
    # commands, so it names the decision.
    truth: dict[int, State] = {}
    state = engine.new_game(seed)
    truth[state.seq] = state
    for c in record.commands:
        frame = engine.legal_commands(state)
        state, _ = engine.apply(state, frame.by_id(c["command_id"]).command, frame)
        truth[state.seq] = state
    secrets = 0
    for agent in watched:
        assert agent.seen, "each side decided at least once"
        for known in agent.seen:
            true_state = truth[known.seq]
            assert player_state.leaks(true_state, known, agent.player) == []
            secrets += sum(1 for u in true_state.units if player_state.masked(true_state, u, agent.player))
    assert secrets > 0, "the game had a secret unit, so the test examined the masking"


def test_decide_gives_the_agent_the_player_state():
    engine = build_engine("s02_tractor_works")
    state = states_with_secrets(engine, 5, limit=500)[-1]
    frame = engine.legal_commands(state)
    watched = Watched(RandomAgent(5, frame.player), frame.player)
    chosen = decide(watched, state, frame)
    assert frame.by_id(chosen) is not None
    assert watched.seen == [player_state.for_player(state, frame.player)]


@pytest.mark.slow
def test_the_odds_of_a_shot_do_not_count_the_units_below_a_counter():
    """S4, the second guard: `odds.shot` counts only the units the viewer sees."""
    from slcore import geometry
    from slcore.game import FireGroup
    from slcore.game import PHASE_PREP_FIRE
    from slagents.scripted import odds

    engine = build_engine("s02_tractor_works")
    checked = 0
    for state in states_with_secrets(engine, 3):
        if checked >= 3:
            break
        for counter in state.concealment:
            below = [u for u in state.infantry_in(counter.hex) if u.player == counter.player]
            if not below:
                continue
            firer = 1 - counter.player
            for own in state.player_units(firer):
                if own.hex is None or not own.is_infantry or own.broken or geometry.distance(own.hex, counter.hex) > 6:
                    continue
                group = FireGroup(counter.hex, ((own.id, None),), None)
                full = odds.shot(engine, state, group, PHASE_PREP_FIRE, viewer=counter.player)
                if not full.breaks:
                    continue
                seen = odds.shot(engine, state, group, PHASE_PREP_FIRE)
                assert seen.breaks == {} and seen.value == 0, "the odds read a unit below a concealment counter"
                checked += 1
                break
    assert checked > 0, "the game gave a concealed stack in the range of a squad"


@pytest.mark.slow
def test_the_repeat_guard_of_the_learned_agent_keys_on_the_view():
    """S13 for the learned agent: two states that differ only in what the player cannot
    see, and in the generator, give one key."""
    pytest.importorskip("torch")
    from dataclasses import replace

    from slagents.learned.agent import LearnedAgent

    engine = build_engine("s02_tractor_works")
    state = states_with_secrets(engine, 3)[-1]
    player = next(p for p in (0, 1) if any(player_state.masked(state, u, p) for u in state.units))
    secret = next(u for u in state.units if player_state.masked(state, u, player) and u.hex is not None)
    moved = state.with_unit(replace(secret, broken=not secret.broken))
    rolled = replace(moved, rng=(9, 9, 9, 9))
    assert LearnedAgent._view_key(state, player) == LearnedAgent._view_key(rolled, player)
    assert LearnedAgent._view_key(state, player) != LearnedAgent._view_key(moved, 1 - player), "the owner sees the change"
