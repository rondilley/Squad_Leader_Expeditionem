"""The worker pool of the parallel collection (FR-51, NFR-01).

The workers hold the environments in their own processes, and the trainer answers them in
one batch. The tests start a small pool, collect a rollout through it, and read that the
steps of each worker are in the rollout with their rewards, their game ends, and their
bootstrap values, and that the league saw each game that ended.
"""

from __future__ import annotations

import math

import pytest

pytest.importorskip("torch")
pytest.importorskip("gymnasium")
pytest.importorskip("pettingzoo")

import numpy as np
import torch

from slagents.learned import ppo
from slagents.learned.env import make_env
from slagents.learned.league import Member
from slagents.learned.nets import NetConfig, Policy
from slagents.learned.workers import WorkerPool, member_spec
from slcli.play import build_engine
from slcli.train import build_league

SCENARIO = "s01_guards_counterattack"
SMALL = NetConfig(channels=4, board_width=32, unit_width=16, hidden=32)


def test_a_pool_collects_the_steps_of_each_worker_with_their_rewards_and_ends():
    torch.manual_seed(0)
    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=3)
    policy = Policy(env.spaces_record, SMALL)
    generator = torch.Generator().manual_seed(0)
    league = build_league(engine, 3)
    ended: list[tuple[str, float]] = []
    seeds = iter(range(100, 200))
    # Forty commands is less than one turn, so each worker ends several games.
    with WorkerPool(SCENARIO, 2, 3, 40, env.spaces_record) as pool:
        pool.workers[1].learner = 1
        rollout = ppo.collect_parallel(
            pool,
            policy,
            60,
            generator,
            lambda: (member_spec(league.members[0]), league.members[0].name),
            lambda: next(seeds),
            lambda name, result: ended.append((name, result)),
            alternate_sides=True,
        )
        assert len(rollout) == 60
        assert set(rollout.worker) == {0, 1}, "the two workers are in the rollout"
        assert set(rollout.last_values) == {0, 1} and all(math.isfinite(v) for v in rollout.last_values.values())
        assert ended, "the short games ended in the collection"
        assert all(name == "random" for name, _ in ended)
        assert sum(rollout.done) >= len(ended) - 2, "each game end marks the worker's last step"
        assert any(r != 0.0 for r in rollout.reward), "the rewards came back from the workers"
        # A truncation costs the loss on each side, so a step before a game end is paid it.
        losses = [rollout.reward[i] for i in range(len(rollout)) if rollout.done[i] == 1.0]
        assert losses and min(losses) <= -100.0 + 5.0
        for i in range(len(rollout)):
            assert rollout.unit_mask[i][rollout.unit[i]] == 1
            assert rollout.target_mask[i][rollout.target[i]] == 1
        # A second collection continues from where the workers wait, with no reset.
        again = ppo.collect_parallel(
            pool, policy, 20, generator,
            lambda: (member_spec(league.members[0]), league.members[0].name),
            lambda: next(seeds), None, alternate_sides=True,
        )
        assert len(again) == 20 and set(again.last_values) == {0, 1}
        adv, returns = ppo.advantages(again, ppo.PpoConfig())
        assert adv.shape == (20,) and np.all(np.isfinite(adv))


def test_the_advantage_runs_along_each_worker_s_own_steps():
    """Interleaved steps of two workers give the same estimate as the two sequences apart."""
    config = ppo.PpoConfig(gae_lambda=1.0, discount=1.0)
    joined = ppo.Rollout()
    apart = {0: ppo.Rollout(), 1: ppo.Rollout()}
    values = {0: [1.0, 2.0, 3.0], 1: [0.5, 0.25, 0.125]}
    rewards = {0: [0.0, 10.0, -10.0], 1: [1.0, 1.0, 1.0]}
    for k in range(3):
        for w in (0, 1):
            for rollout in (joined, apart[w]):
                rollout.unit.append(0)
                rollout.value.append(values[w][k])
                rollout.reward.append(rewards[w][k])
                rollout.done.append(1.0 if (w == 0 and k == 1) else 0.0)
            joined.worker.append(w)
    joined.last_values = {0: 7.0, 1: -3.0}
    apart[0].last_value = 7.0
    apart[1].last_value = -3.0
    adv_joined, _ = ppo.advantages(joined, config)
    adv_0, _ = ppo.advantages(apart[0], config)
    adv_1, _ = ppo.advantages(apart[1], config)
    assert adv_joined[0::2] == pytest.approx(adv_0)
    assert adv_joined[1::2] == pytest.approx(adv_1)


def test_the_member_spec_names_what_a_worker_builds():
    engine = build_engine(SCENARIO)
    league = build_league(engine, 1)
    assert member_spec(league.by_name("random")) == ("random",)
    assert member_spec(league.by_name("scripted-scripted-v5")) == ("scripted", "v5")
    assert member_spec(Member(name="snapshot-5", kind="snapshot", act=lambda e, o: (0, 0, 0), spec="x.pt")) == ("snapshot", "x.pt")
    with pytest.raises(ValueError):
        member_spec(Member(name="snapshot-5", kind="snapshot", act=lambda e, o: (0, 0, 0)))


def test_the_imitation_pool_gives_the_same_games_as_one_process():
    """The parallel demonstrations are the one-process demonstrations, game for game."""
    from slagents.learned import imitate
    from slagents.learned.workers import corrections_parallel, demonstrations_parallel
    from slcli.play import make_agent

    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=1, max_commands=60)

    def make_teacher(kind: str, seed: int, player: int):
        return make_agent(kind, engine, seed, player)

    labels = {0: "v5", 1: "v1"}
    alone = imitate.collect_demonstrations(env, make_teacher, ["v1"], games=2, seed=50, labels=labels)
    seen: list[tuple[int, str, str, float]] = []
    pooled = demonstrations_parallel(SCENARIO, ["v1"], 2, 50, 2, 60, labels, lambda *a: seen.append(a))
    assert len(pooled) == len(alone) and pooled.games == 2
    assert np.array_equal(pooled.unit, alone.unit) and np.array_equal(pooled.action, alone.action)
    assert np.array_equal(pooled.target, alone.target)
    assert pooled.value == pytest.approx(alone.value)
    assert [row[0] for row in seen] == [0, 1]
    policy = Policy(env.spaces_record, SMALL)
    corrected = corrections_parallel(SCENARIO, policy, labels, ["v1"], 2, 60, 2, 60)
    assert corrected.games == 2 and len(corrected) > 4 and set(corrected.player) == {0, 1}


def test_the_parallel_evaluation_gives_the_rows_of_the_one_process_evaluation():
    """TC-18 through the pool: the same members, the same sides, the same counts shape."""
    from slcli.train import evaluate

    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=70, max_commands=50)
    policy = Policy(env.spaces_record, SMALL)
    league = build_league(engine, 70)
    league.members = league.members[:2]
    rows = evaluate(env, policy, league, 0, 2, workers=2, scenario=SCENARIO)
    assert [row["opponent"] for row in rows] == ["random", "scripted-scripted-v0"]
    for row in rows:
        assert row["games"] == 2
        assert sum(row["results"].values()) == 2
        assert sum(row["by_side"]["player_0"].values()) == 1 and sum(row["by_side"]["player_1"].values()) == 1
        # Fifty commands is less than a game, so each game is a truncation or a repeat.
        assert row["results"]["truncated"] + row["results"]["repeated"] == 2
    with pytest.raises(ValueError, match="scenario"):
        evaluate(env, policy, league, 0, 2, workers=2)
