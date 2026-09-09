"""The training smoke test (TR-10) and the league (FR-52, TC-19).

TR-10 asks for 10,000 steps of PPO with a finite loss and a recorded step rate. That is
minutes on a processor, so the whole measurement carries the `gate` marker and a short
version of the same loop runs on each commit.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest
import torch

from slagents.learned import ppo
from slagents.learned.env import make_env
from slagents.learned.league import League, Member, load_snapshot
from slagents.learned.nets import NetConfig, Policy
from slcli.play import build_engine
from slcli.train import LEARNER, build_league, run_training

SCENARIO = "s01_guards_counterattack"
SMOKE_STEPS = 10000
FAST_STEPS = 400


def smoke(steps: int, tmp_path: Path) -> dict:
    """The loop of TR-10: N steps, a finite loss, and a step rate."""
    art = run_training(
        scenario=SCENARIO,
        steps=steps,
        hours=0.0,
        seed=5,
        learner_player=0,
        snapshot_every=max(200, steps // 2),
        config=ppo.PpoConfig(steps_per_update=min(256, steps), minibatch=64, epochs=2),
        net=NetConfig(),
        out=tmp_path,
        log_dir=tmp_path / "tb",
    )
    return art.stats


def test_a_short_training_run_gives_a_finite_loss_and_a_rate(tmp_path: Path):
    stats = smoke(FAST_STEPS, tmp_path)
    assert stats["steps"] == FAST_STEPS
    assert stats["steps_per_second"] > 0.0
    assert stats["rate_reports"], "the run records its rate"
    assert stats["updates"] > 0


@pytest.mark.gate
def test_ten_thousand_steps_of_ppo(tmp_path: Path):
    """TR-10: 10,000 steps, a finite loss, and the steps per second recorded."""
    stats = smoke(SMOKE_STEPS, tmp_path)
    assert stats["steps"] == SMOKE_STEPS
    assert stats["steps_per_second"] > 0.0
    assert all(math.isfinite(r["steps_per_second"]) for r in stats["rate_reports"])
    assert stats["passed"]["TC-19"], "the Elo table holds each member"


def test_the_loss_of_one_update_is_finite():
    """A loss that is not finite is a defect, whatever the numbers of the run."""
    torch.manual_seed(0)
    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=3)
    policy = Policy(env.spaces_record)
    optimizer = torch.optim.Adam(policy.parameters(), lr=3e-4)
    generator = torch.Generator().manual_seed(0)
    config = ppo.PpoConfig(steps_per_update=96, minibatch=32, epochs=2)
    rollout = ppo.collect(env, policy, 0, ppo.random_opponent, config.steps_per_update, generator)
    stats = ppo.update(policy, optimizer, rollout, config, env.spaces_record)
    for name in ("loss", "policy_loss", "value_loss", "entropy"):
        assert math.isfinite(stats[name]), f"{name} is {stats[name]}"
    assert stats["minibatches"] > 0


def test_the_advantage_of_a_won_game_is_positive():
    """The reward reaches the decisions that came before it."""
    rollout = ppo.Rollout()
    for i in range(4):
        rollout.unit.append(0)
        rollout.action.append(0)
        rollout.target.append(0)
        rollout.log_prob.append(0.0)
        rollout.value.append(0.0)
        rollout.reward.append(0.0)
        rollout.done.append(0.0)
    rollout.reward[-1] = 1.0
    rollout.done[-1] = 1.0
    adv, returns = ppo.advantages(rollout, ppo.PpoConfig())
    assert adv[-1] == pytest.approx(1.0)
    assert all(a > 0 for a in adv), "each decision of a won game has a positive advantage"
    assert returns[-1] == pytest.approx(1.0)


def test_the_league_samples_the_opponent_that_wins_more_often():
    """FR-52: opponent sampling by loss rate."""
    league = League()
    weak = league.add(Member(name="weak", kind="test", act=lambda env, obs: (0, 0, 0)))
    strong = league.add(Member(name="strong", kind="test", act=lambda env, obs: (0, 0, 0)))
    for _ in range(10):
        league.record(weak, 1.0)
        league.record(strong, -1.0)
    assert weak.loss_rate == 0.0
    assert strong.loss_rate == 1.0
    generator = torch.Generator().manual_seed(0)
    picks = [league.sample(generator).name for _ in range(200)]
    assert picks.count("strong") > picks.count("weak") * 3


def test_the_elo_table_has_an_entry_for_each_member(tmp_path: Path):
    """TC-19: each member of the league and the learner are in the table."""
    engine = build_engine(SCENARIO)
    league = build_league(engine, seed=1, opponent_player=1)
    member = league.members[0]
    league.record(member, 1.0, LEARNER)
    table = league.table(LEARNER)
    assert LEARNER in table
    for other in league.members:
        assert other.name in table, other.name
        assert "rating" in table[other.name] and "games" in table[other.name]


def test_a_snapshot_saves_and_loads(tmp_path: Path):
    """FR-52: a snapshot is an opponent, so it must load into a policy of the same shape."""
    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=2)
    policy = Policy(env.spaces_record)
    league = League()
    path = league.take_snapshot(policy, tmp_path, 100, NetConfig())
    assert path.exists()
    other = Policy(env.spaces_record)
    load_snapshot(path, other)
    for a, b in zip(policy.state_dict().values(), other.state_dict().values()):
        assert torch.equal(a, b)
    assert league.snapshots == 1


def test_the_evaluation_gives_a_win_rate_with_an_interval(tmp_path: Path):
    """TC-18: the measurement of a ladder rung, on a run that is short enough to test."""
    art = run_training(
        scenario=SCENARIO,
        steps=200,
        hours=0.0,
        seed=9,
        learner_player=0,
        snapshot_every=0,
        config=ppo.PpoConfig(steps_per_update=200, minibatch=64, epochs=1),
        net=NetConfig(),
        out=tmp_path,
        log_dir=None,
        eval_games=2,
    )
    rows = art.stats["evaluation"]
    assert rows, "the run measured itself against the constant opponents"
    names = {row["opponent"] for row in rows}
    assert "random" in names
    assert any(name.startswith("scripted-") for name in names)
    for row in rows:
        assert row["games"] == 2
        assert 0.0 <= row["win_rate"] <= 1.0
        assert row["confidence_low"] <= row["win_rate"] <= row["confidence_high"]
        assert set(row["results"]) == {"win", "loss", "draw"}
    assert "TC-18" in art.stats["passed"]


def test_the_run_artifact_records_the_agent_versions_and_the_algorithm(tmp_path: Path):
    """TC-18 asks for the scripted agent version in the artifact, so a number compares."""
    art = run_training(
        scenario=SCENARIO,
        steps=200,
        hours=0.0,
        seed=4,
        learner_player=0,
        snapshot_every=0,
        config=ppo.PpoConfig(steps_per_update=200, minibatch=64, epochs=1),
        net=NetConfig(),
        out=tmp_path,
        log_dir=None,
    )
    config = art.config
    assert config["criteria"] == ["TC-13", "TC-18", "TC-19", "IR-07"]
    assert config["ppo"]["clip"] == ppo.PpoConfig().clip
    assert config["net"]["channels"] > 0
    assert config["parameters"] > 0
    assert any(name.startswith("scripted-scripted-v") for name in config["opponents"])
    assert any(name.startswith("scripted-engineer-v") for name in config["opponents"])
    assert config["board_source"] == "generated"
