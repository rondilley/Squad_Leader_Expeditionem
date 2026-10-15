"""Jump-Start RL: a guide plays the first turns of the learner's side (2026-10-13).

The horizon rule needs no torch. The worker test starts a real pool and reads the turn of
the learner's first decision from the observation.
"""

from __future__ import annotations

import itertools

import pytest

from slagents.learned.jumpstart import JumpStart


def test_the_horizon_goes_down_one_turn_when_the_learner_wins_enough():
    js = JumpStart("v7", 3, threshold=0.75, window=4)
    assert js.next() == ("v7", 3)
    for result in (-1.0, 1.0, 1.0):
        js.record(3, result)
    assert js.turns == 3, "three games are fewer than the window"
    js.record(3, -1.0)
    assert js.turns == 3, "two wins of four are under the threshold"
    js.record(3, 1.0)
    assert js.turns == 2, "three wins in the last four games reach the threshold"
    assert js.changes == [{"games": 5, "from_turns": 3, "to_turns": 2, "win_rate": 0.75}]


def test_a_game_of_the_old_horizon_does_not_count_for_the_new_one():
    js = JumpStart("v7", 2, threshold=0.5, window=2)
    js.record(2, 1.0)
    js.record(2, 1.0)
    assert js.turns == 1
    for _ in range(5):
        js.record(2, 1.0)
    assert js.turns == 1, "the games that started at two turns are not evidence for one"
    assert js.games == 7


def test_at_a_horizon_of_zero_the_learner_plays_the_whole_game():
    js = JumpStart("v7", 1, threshold=0.5, window=1)
    js.record(1, 1.0)
    assert js.turns == 0
    assert js.next() is None
    js.record(0, 1.0)
    assert js.turns == 0, "the horizon does not go below zero"


def test_the_jump_start_values_are_checked():
    with pytest.raises(ValueError):
        JumpStart("v7", -1)
    with pytest.raises(ValueError):
        JumpStart("v7", 2, threshold=0.0)
    with pytest.raises(ValueError):
        JumpStart("v7", 2, window=0)


def test_the_guide_plays_the_learner_side_in_the_first_turns():
    """With a guide for one turn, the learner's first decision is in turn 2. Without a
    guide it is in turn 1. The collection records each game that ended for the rule."""
    pytest.importorskip("torch")
    pytest.importorskip("gymnasium")
    pytest.importorskip("pettingzoo")
    import torch

    from slagents.learned import encoding, ppo
    from slagents.learned.env import make_env
    from slagents.learned.nets import NetConfig, Policy
    from slagents.learned.workers import WorkerPool
    from slcli.play import build_engine

    scenario = "s01_guards_counterattack"
    engine = build_engine(scenario)
    env = make_env(engine, seed=3)
    turn_index = len(encoding.PLAYER_TURN_PHASES) + 1
    limit = engine.new_game(1).turn_limit

    def first_turn(pool, worker, guide) -> int:
        pool.reset(worker, ("random",), "random", 0, 11, guide)
        decision = pool.receive(worker)
        assert not decision.ended
        return round(float(decision.observation["scalars"][turn_index]) * limit)

    with WorkerPool(scenario, 2, 3, 5000, env.spaces_record) as pool:
        worker = pool.workers[0]
        assert first_turn(pool, worker, None) == 1
        assert first_turn(pool, worker, ("v1", 1)) == 2
        assert worker.guide_turns == 1
        # A horizon past the end leaves the last turn to the learner.
        assert first_turn(pool, worker, ("v1", limit + 5)) == limit

    torch.manual_seed(0)
    policy = Policy(env.spaces_record, NetConfig(channels=4, board_width=32, unit_width=16, hidden=32))
    js = JumpStart("v1", 1, threshold=1.0, window=50)
    seeds = itertools.count(100)
    # A limit of 400 commands ends each game early, after the guide's turn.
    with WorkerPool(scenario, 2, 3, 400, env.spaces_record) as pool:
        ppo.collect_parallel(
            pool, policy, 200, torch.Generator().manual_seed(0),
            lambda: (("random",), "random"), lambda: next(seeds), None, jump_start=js,
        )
    assert js.games > 0, "the collection records each game that ended"
