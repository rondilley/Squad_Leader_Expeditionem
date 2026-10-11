"""Rule 35.8: each agent answers the push out window of an overrun with a legal command.

The window is `defensive_fire/push_out`, and its commands have the action `push_out`. A
real game of scenario 4 (v6, v7, or the tanker v3 on each side) reaches it. Each scripted agent
v1 to v7 and the learned agent (an untrained policy of the real network) take the frame
and give an ID of the frame, and the encoding of the learner has the action.
"""

from __future__ import annotations

from importlib.util import find_spec

import pytest

from slagents.base import decide
from slagents.learned import encoding
from slcli.play import build_engine, make_agent

SCENARIO = "s04_armor_probe"


# The games that the fixture reads, in sequence, until one reaches the window. The agents
# change their play from slice to slice, so the fixture reads more than one game.
# Since the armor policy (2026-10-10) a tank overruns only a weak target, and the window
# comes in about one game in sixty; the first two games are ones that reach it.
GAMES = ((24, ("v6", "v6")), (30, ("v7", "v3"))) + tuple(
    (seed, pair) for seed in range(1, 13) for pair in (("v7", "v3"), ("v3", "v3"), ("v3", "v7"))
)


@pytest.fixture(scope="module")
def window():
    engine = build_engine(SCENARIO)
    for seed, (first, second) in GAMES:
        agents = (make_agent(first, engine, seed, 0), make_agent(second, engine, seed, 1))
        state = engine.new_game(seed)
        for _ in range(4000):
            if state.game_over:
                break
            frame = engine.legal_commands(state)
            if frame.sub_step == "push_out":
                return engine, state, frame
            chosen = frame.by_id(decide(agents[frame.player], state, frame))
            state, _ = engine.apply(state, chosen.command, frame)
    pytest.fail("no game of scenario 4 reached the push out window of rule 35.8")


def test_push_out_is_the_last_action_of_the_encoding(window):
    engine, _state, frame = window
    assert encoding.ACTIONS[-1] == "push_out"
    hexes = encoding.hex_slots(engine.board)
    for lc in frame.commands:
        _unit, action, _target = encoding.command_triple(lc.command, hexes)
        if lc.command.action == "push_out":
            assert action == encoding.ACTION_INDEX["push_out"]


@pytest.mark.parametrize("name", ("v1", "v2", "v3", "v4", "v5", "v6", "v7"))
def test_each_scripted_agent_answers_the_push_out_window(window, name):
    engine, state, frame = window
    agent = make_agent(name, engine, 1, frame.player)
    chosen = frame.by_id(decide(agent, state, frame))
    assert chosen is not None
    if any(lc.command.action == "push_out" for lc in frame.commands):
        assert chosen.command.action == "push_out"


@pytest.mark.skipif(find_spec("torch") is None, reason="the learned agent needs torch, the train extra")
def test_the_learned_agent_answers_the_push_out_window(window):
    import torch

    from slagents.learned.agent import LearnedAgent
    from slagents.learned.env import make_env
    from slagents.learned.nets import NetConfig, Policy

    engine, state, frame = window
    env = make_env(engine, seed=2)
    torch.manual_seed(0)
    policy = Policy(env.spaces_record, NetConfig(channels=4, board_width=16, unit_width=8, hidden=16))
    agent = LearnedAgent.from_policy(engine, policy)
    assert frame.by_id(decide(agent, state, frame)) is not None
