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


def test_the_labels_parse_as_one_teacher_for_each_side():
    assert imitate.parse_labels("0=v5,1=v6") == {0: "v5", 1: "v6"}
    assert imitate.parse_labels(" 1=v6 , 0=v4 ") == {0: "v4", 1: "v6"}
    with pytest.raises(ValueError):
        imitate.parse_labels("0=v5")
    with pytest.raises(ValueError):
        imitate.parse_labels("2=v5,1=v6")


def test_the_label_teacher_of_a_side_names_the_command_and_the_actor_plays(engine):
    """With labels the pool plays the game, and the label teacher of each side gives the record.

    The label of a decision is legal in the state, the label teacher of side 0 is built for
    each game, and on some decisions it disagrees with the actor, which is what the labels
    are for.
    """
    env = make_env(engine, seed=31)
    built: list[tuple[str, int]] = []
    actors_chose: list[tuple[int, int, int]] = []

    def make_teacher(kind: str, seed: int, player: int):
        built.append((kind, player))
        agent = make_agent(kind, engine, seed, player)
        if kind == "v1" and player == 0:
            original = agent.select

            def select(state, frame):
                chosen = original(state, frame)
                actors_chose.append(imitate.command_triple(frame.by_id(chosen).command, env.hexes))
                return chosen

            agent.select = select
        return agent

    data = imitate.collect_demonstrations(env, make_teacher, ["v1"], games=1, seed=31, labels={0: "v5", 1: "v1"})
    assert ("v5", 0) in built, "the label teacher of side 0 was built"
    assert ("v5", 1) not in built, "side 1 is labelled by its own actor"
    assert data.games == 1 and len(data) > 100
    spaces = env.spaces_record
    for i in range(len(data)):
        assert data.unit_mask[i][data.unit[i]] == 1
        assert data.action_mask[i].reshape(spaces.units, spaces.actions)[data.unit[i], data.action[i]] == 1
        assert data.target_mask[i][data.target[i]] == 1
    side_0 = [(data.unit[i], data.action[i], data.target[i]) for i in range(len(data)) if data.player[i] == 0]
    assert len(side_0) == len(actors_chose)
    assert any(label != chosen for label, chosen in zip(side_0, actors_chose)), "v5 and v1 differ in some state"


def test_a_dagger_round_records_the_policy_s_states_with_the_teacher_s_labels(engine):
    """The policy plays each side in turn, and each state has the label teacher's command."""
    torch.manual_seed(0)
    env = make_env(engine, seed=37, max_commands=120)
    policy = Policy(env.spaces_record, SMALL)
    generator = torch.Generator().manual_seed(0)
    sides: list[int] = []

    def make_teacher(kind: str, seed: int, player: int):
        return make_agent(kind, engine, seed, player)

    data = imitate.collect_corrections(
        env, policy, make_teacher, {0: "v5", 1: "v1"}, ["v1"], games=2, seed=37, generator=generator,
        on_game=lambda game, side, kind, result: sides.append(side),
    )
    assert sides == [0, 1], "the policy held side 0 and then side 1"
    assert data.games == 2 and len(data) > 20
    assert set(data.player) == {0, 1}
    spaces = env.spaces_record
    for i in range(len(data)):
        assert data.unit_mask[i][data.unit[i]] == 1
        assert data.action_mask[i].reshape(spaces.units, spaces.actions)[data.unit[i], data.action[i]] == 1
        assert data.target_mask[i][data.target[i]] == 1
    assert len(data.value) == len(data)
    before = len(data)
    more = imitate.Demonstrations()
    more.extend(data)
    more.extend(data)
    assert len(more) == 2 * before and more.games == 4


def test_the_command_runs_a_dagger_round_on_the_processor(tmp_path: Path):
    art = run_imitation(
        scenario=SCENARIO,
        teachers=["v1"],
        games=1,
        seed=41,
        config=imitate.FitConfig(epochs=1, minibatch=64),
        net=SMALL,
        out=tmp_path / "snapshot-0.pt",
        eval_games=0,
        device="cpu",
        log=lambda *_: None,
        labels={0: "v5", 1: "v1"},
        dagger_rounds=1,
        dagger_games=1,
        dagger_epochs=1,
    )
    assert art.stats["dagger"][0]["games"] == 1 and art.stats["dagger"][0]["decisions"] > 20
    assert art.stats["games"] == 2, "the teachers' game and the round's game"
    assert art.config["labels"] == {"0": "v5", "1": "v1"}
    with pytest.raises(ValueError, match="need --labels"):
        run_imitation(
            scenario=SCENARIO, teachers=["v1"], games=1, seed=41, config=imitate.FitConfig(epochs=1),
            net=SMALL, out=tmp_path / "x.pt", device="cpu", log=lambda *_: None, dagger_rounds=1, dagger_games=1,
        )


def test_the_stop_weight_weighs_the_decisions_of_no_unit(demonstrations):
    """A heavier stop weight raises the share of the loss that the slot 0 decisions carry."""
    env, data = demonstrations
    torch.manual_seed(0)
    policy = Policy(env.spaces_record, SMALL)
    tensors = imitate.Tensors(data, env.spaces_record, torch.device("cpu"), 10.0)
    index = torch.arange(0, min(256, len(tensors)))
    units = tensors.unit[index]
    assert (units == 0).any() and (units != 0).any(), "the batch holds stop decisions and unit decisions"
    with torch.no_grad():
        equal, _, _ = tensors.losses(policy, index, 0.1, 1.0)
        heavy, _, _ = tensors.losses(policy, index, 0.1, 5.0)
        # The stop decisions alone, and the others alone.
        stops, _, _ = tensors.losses(policy, index[units == 0], 0.1, 1.0)
        others, _, _ = tensors.losses(policy, index[units != 0], 0.1, 1.0)
    n_stop = int((units == 0).sum())
    n_other = int((units != 0).sum())
    assert float(equal) == pytest.approx((float(stops) * n_stop + float(others) * n_other) / (n_stop + n_other), rel=1e-4)
    assert float(heavy) == pytest.approx((float(stops) * 5 * n_stop + float(others) * n_other) / (5 * n_stop + n_other), rel=1e-4)
    assert imitate.FitConfig(stop_weight=3.0).to_dict()["stop_weight"] == 3.0
