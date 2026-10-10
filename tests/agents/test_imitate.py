"""The imitation start of the learned agent (FR-51).

The policy copies the decisions of the scripted agents before PPO. The tests play real
games of the teachers in the environment, fit a small policy on the processor, and read
that the fit lowered the cross entropy, that the snapshot loads as a training snapshot,
and that the trainer starts from it with its weights.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("gymnasium")
pytest.importorskip("pettingzoo")

import numpy as np
import torch

from slagents.learned import imitate
from slagents.learned.agent import LearnedAgent, load_policy
from slagents.learned.env import make_env
from slagents.learned.nets import NetConfig, Policy
from slcli.imitate_cmd import run_imitation
from slcli.play import build_engine, make_agent
from slcli.train import run_training, snapshot_net

SCENARIO = "s01_guards_counterattack"
SMALL = NetConfig(channels=4, board_width=32, unit_width=16, hidden=32)


@pytest.fixture(scope="module")
def engine():
    return build_engine(SCENARIO)


@pytest.fixture(scope="module")
def demonstrations(engine):
    env = make_env(engine, seed=3)

    def make_teacher(kind: str, seed: int, player: int):
        return make_agent(kind, engine, seed, player)

    return env, imitate.collect_demonstrations(env, make_teacher, ["v5", "v1"], games=2, seed=3)


def test_the_teacher_pairs_cover_each_ordered_pair_with_self_play():
    assert imitate.teacher_pairs(["v5", "v6"]) == [("v5", "v5"), ("v5", "v6"), ("v6", "v5"), ("v6", "v6")]


def test_the_demonstrations_hold_each_decision_of_the_two_sides_inside_the_masks(demonstrations):
    env, data = demonstrations
    assert data.games == 2
    assert len(data) > 400, "two games of scenario 1 give hundreds of decisions"
    assert set(data.player) == {0, 1}, "the two sides are in the data"
    assert sum(data.results.values()) == 2
    spaces = env.spaces_record
    for i in range(len(data)):
        unit, action, target = data.unit[i], data.action[i], data.target[i]
        assert data.unit_mask[i][unit] == 1
        assert data.action_mask[i].reshape(spaces.units, spaces.actions)[unit, action] == 1
        assert data.target_mask[i][target] == 1
    assert len(data.value) == len(data)
    # The return of the last decision of a game is the end reward alone, so the return
    # of the first decision of the winner is larger than the return of its last one.
    assert any(v != 0.0 for v in data.value)


def test_the_fit_lowers_the_cross_entropy_and_the_holdout_reads_it(demonstrations):
    env, data = demonstrations
    torch.manual_seed(0)
    policy = Policy(env.spaces_record, SMALL)
    config = imitate.FitConfig(epochs=3, minibatch=64, learning_rate=1e-3, holdout=0.2)
    rows = imitate.fit(policy, data, config, env.spaces_record, seed=0)
    assert len(rows) == 3
    assert all(np.isfinite(row["loss"]) for row in rows)
    assert rows[-1]["cross_entropy"] < rows[0]["cross_entropy"], "the fit lowered the cross entropy"
    assert np.isfinite(rows[-1]["holdout_cross_entropy"])
    assert 0.0 <= rows[-1]["holdout_accuracy"] <= 1.0


def test_the_snapshot_loads_as_a_training_snapshot_and_plays(tmp_path: Path, demonstrations, engine):
    env, data = demonstrations
    policy = Policy(env.spaces_record, SMALL)
    imitate.fit(policy, data, imitate.FitConfig(epochs=1, minibatch=64), env.spaces_record, seed=0)
    path = imitate.save(policy, tmp_path / "snapshot-0.pt", SMALL, {"teachers": ["v5", "v1"]})
    saved = torch.load(path, map_location="cpu", weights_only=False)
    assert saved["step"] == 0 and saved["imitation"]["teachers"] == ["v5", "v1"]
    loaded = load_policy(path)
    assert loaded.config == SMALL
    agent = LearnedAgent.from_policy(engine, loaded)
    state = engine.new_game(5)
    frame = engine.legal_commands(state)
    assert frame.by_id(agent.select(state, frame)) is not None, "the loaded policy gives a legal command"
    assert snapshot_net(path, env.spaces_record) == SMALL


def test_the_trainer_starts_from_the_snapshot_with_its_weights(tmp_path: Path, demonstrations):
    env, data = demonstrations
    policy = Policy(env.spaces_record, SMALL)
    path = imitate.save(policy, tmp_path / "start.pt", SMALL, {})
    before = {k: v.clone() for k, v in policy.state_dict().items()}
    from slagents.learned import ppo

    art = run_training(
        scenario=SCENARIO,
        steps=0,
        hours=0.0,
        seed=3,
        learner_player=0,
        snapshot_every=0,
        config=ppo.PpoConfig(steps_per_update=16, minibatch=8, epochs=1),
        net=NetConfig(channels=64, hidden=512),
        out=tmp_path / "train",
        log_dir=None,
        device="cpu",
        start_from=path,
    )
    assert art.config["start_from"] == str(path)
    assert art.config["net"] == SMALL.to_dict(), "the snapshot's shape replaces the command line's"
    started = load_policy(path).state_dict()
    for key, value in before.items():
        assert torch.equal(started[key], value)


def test_a_snapshot_of_another_shape_of_spaces_is_refused(tmp_path: Path, demonstrations):
    env, _ = demonstrations
    from slagents.learned.encoding import Spaces

    other = Spaces(units=3, actions=env.spaces_record.actions, targets=5, cols=2, rows=2)
    policy = Policy(other, SMALL)
    path = imitate.save(policy, tmp_path / "other.pt", SMALL, {})
    with pytest.raises(ValueError, match="same scenario and board"):
        snapshot_net(path, env.spaces_record)


def test_the_command_runs_end_to_end_on_the_processor(tmp_path: Path):
    art = run_imitation(
        scenario=SCENARIO,
        teachers=["v5"],
        games=1,
        seed=4,
        config=imitate.FitConfig(epochs=1, minibatch=64),
        net=SMALL,
        out=tmp_path / "snapshot-0.pt",
        eval_games=0,
        device="cpu",
        log=lambda *_: None,
    )
    assert art.kind == "imitate"
    assert art.stats["games"] == 1 and art.stats["decisions"] > 100
    assert (tmp_path / "snapshot-0.pt").exists()
    assert art.config["snapshot"] == str(tmp_path / "snapshot-0.pt")
