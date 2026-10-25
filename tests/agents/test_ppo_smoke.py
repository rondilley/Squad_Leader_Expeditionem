"""The training smoke test (TR-10) and the league (FR-52, TC-19).

TR-10 asks for 10,000 steps of PPO with a finite loss and a recorded step rate. That is
minutes on a processor, so the whole measurement carries the `gate` marker and a short
version of the same loop runs on each commit.
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

pytest.importorskip("torch")
pytest.importorskip("gymnasium")
pytest.importorskip("pettingzoo")

import torch

from slagents.learned import ppo
from slagents.learned.env import make_env
from slagents.learned.league import League, Member, load_snapshot
from slagents.learned.nets import NetConfig, Policy
from slcli.play import build_engine
from slcli.play import make_agent
from slcli.train import LEARNER, build_league, run_training, scripted_member

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


def test_a_run_shorter_than_the_snapshot_interval_keeps_its_last_net(tmp_path: Path):
    """A resume of 1,996,416 decisions with `--snapshot-every 2000000` kept no net, and the
    gate after it had nothing to play (2026-10-16). The run writes a snapshot at its end."""
    art = run_training(
        scenario=SCENARIO, steps=192, hours=0.0, seed=5, learner_player=0, snapshot_every=1000,
        config=ppo.PpoConfig(steps_per_update=64, minibatch=32, epochs=1), net=NetConfig(),
        out=tmp_path, log_dir=None,
    )
    done = art.stats["steps"]
    assert done < 1000
    assert [row["step"] for row in art.stats["snapshots"]] == [done]
    from slagents.learned.agent import load_policy

    path = Path(art.stats["snapshots"][0]["path"])
    assert path.is_file()
    assert isinstance(load_policy(str(path)), Policy)
    assert art.stats["stopped_because"] == "the step count is complete"


def test_a_run_that_stops_at_its_hours_says_so(tmp_path: Path):
    """The L08 and L09 chunks stopped at --hours 3 and said the step count was complete
    (2026-10-24)."""
    art = run_training(
        scenario=SCENARIO, steps=192, hours=1e-9, seed=5, learner_player=0, snapshot_every=0,
        config=ppo.PpoConfig(steps_per_update=64, minibatch=32, epochs=1), net=NetConfig(),
        out=tmp_path, log_dir=None,
    )
    assert art.stats["steps"] < 192
    assert art.stats["stopped_because"] == "the hours limit"


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
    config = ppo.PpoConfig()
    adv, returns = ppo.advantages(rollout, config)
    # The update reads the reward divided by the scale, so a win of one hundred is ten.
    assert adv[-1] == pytest.approx(1.0 / config.reward_scale)
    assert all(a > 0 for a in adv), "each decision of a won game has a positive advantage"
    assert returns[-1] == pytest.approx(1.0 / config.reward_scale)


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
    league = build_league(engine, seed=1)
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
        assert set(row["results"]) == {"win", "loss", "draw", "truncated", "repeated"}, "a truncated game and a cycle each have their own count"
        assert sum(row["results"].values()) == row["games"]
        assert set(row["by_side"]) == {"player_0", "player_1"}, "each side the learner held has its own counts"
        for side in row["by_side"].values():
            assert set(side) == set(row["results"])
        assert all(
            sum(side[key] for side in row["by_side"].values()) == row["results"][key] for key in row["results"]
        ), "the two sides sum to the whole"
    assert "TC-18" in art.stats["passed"]
    reward = art.config["reward"]
    assert reward["player_0"]["loss"] < 0 < reward["player_0"]["win"], "the artifact records the reward weights"
    assert reward["player_0"]["nation"] == "soviet" and reward["player_1"]["nation"] == "german", "each side has its army's weights"


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


def test_the_scripted_member_plays_the_side_of_the_frame():
    """A scripted opponent plans for the side the frame names, on each side.

    The evaluation of the third 1 million step run built the member for the opponent of
    the learner and then changed the sides, so the German plan moved the Russians in each
    odd game. The member now holds an agent for each side.
    """
    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=11)
    member = scripted_member(engine, "v1", 11)
    right = {player: make_agent("v1", engine, 11, player) for player in (0, 1)}
    wrong_side_choices = 0
    sides_seen = set()
    for _ in range(120):
        agent = env.agent_selection
        if env.terminations[agent] or env.truncations[agent]:
            break
        player = env.frame.player
        sides_seen.add(player)
        chosen = member.act(env, env.observe(agent))
        expected = env.frame.by_id(right[player].select(env.state_, env.frame))
        assert env.groups[chosen].id == expected.id, f"the member played a plan of the other side for player {player}"
        other = env.frame.by_id(right[1 - player].select(env.state_, env.frame))
        if other.id != env.groups[chosen].id:
            wrong_side_choices += 1
        env.step(chosen)
    assert sides_seen == {0, 1}, "the game reached a decision of each side"
    assert wrong_side_choices > 0, "an agent built for the other side gives a different command, so the side matters"


def test_the_learner_changes_sides_at_each_new_game():
    """`--player both`: one policy plays the attack and the defence in turn."""
    torch.manual_seed(0)
    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=4, max_commands=40)
    policy = Policy(env.spaces_record)
    generator = torch.Generator().manual_seed(0)
    games_ended = 0
    opponent_sides: list[set[int]] = [set()]

    def opponent(env, observation):
        opponent_sides[-1].add(env.frame.player)
        return ppo.random_opponent(env, observation)

    def on_game_end(_: float) -> None:
        nonlocal games_ended
        games_ended += 1
        opponent_sides.append(set())

    rollout = ppo.collect(env, policy, 0, opponent, 100, generator, on_game_end, alternate_sides=True)
    assert games_ended >= 3, "the short games gave several games in one collection"
    for game, sides in enumerate(opponent_sides[:games_ended]):
        assert sides == {1 - (game % 2)}, f"in game {game} the opponent held side {sides}, so the learner did not change sides"
    assert rollout.next_learner == games_ended % 2, "the next collection starts on the side after the last game"
    fixed = ppo.collect(make_env(engine, seed=4, max_commands=40), policy, 0, ppo.random_opponent, 100, generator)
    assert fixed.next_learner == 0, "without the switch the learner keeps its side"


def test_a_rollout_ends_at_the_learner_s_next_decision_and_drops_no_reward():
    """The rollout stops where the learner decides next, with the value of that state.

    Two short collections in a row: the environment waits at a decision of the learner
    after each one, the bootstrap is the policy's value of that state, and the rewards of
    the two rollouts add up to what the environment paid the learner. Before this the
    opponent's stretch between two rollouts was paid to no decision.
    """
    torch.manual_seed(0)
    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=6)
    policy = Policy(env.spaces_record)
    generator = torch.Generator().manual_seed(0)
    first = ppo.collect(env, policy, 0, ppo.random_opponent, 8, generator)
    assert len(first) == 8
    assert env.player_of(env.agent_selection) == 0, "the environment waits at the learner's decision"
    assert not any(env.terminations.values()) and not any(env.truncations.values())
    assert first.last_value == pytest.approx(ppo.value_of(policy, env.observe(env.agent_of(0))))
    assert first.done[-1] == 0.0
    second = ppo.collect(env, policy, 0, ppo.random_opponent, 8, generator)
    paid = float(env._cumulative_rewards[env.agent_of(0)])
    assert sum(first.reward) + sum(second.reward) == pytest.approx(paid, abs=1e-6), "no reward fell between the two rollouts"
    adv, returns = ppo.advantages(first, ppo.PpoConfig(), first.last_value)
    assert returns[-1] == pytest.approx(first.reward[-1] / ppo.PpoConfig.reward_scale + first.last_value)


def test_a_rollout_whose_game_ends_on_the_way_marks_the_end_and_bootstraps_on_zero():
    """A game that ends in the opponent's stretch after the last decision is a done step."""
    torch.manual_seed(0)
    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=8, max_commands=30)
    policy = Policy(env.spaces_record)
    generator = torch.Generator().manual_seed(0)
    ended: list[float] = []
    # Thirty commands is less than one turn, so a collection of many decisions holds
    # several game ends, each of which the callback sees once and marks as done.
    rollout = ppo.collect(env, policy, 0, ppo.random_opponent, 40, generator, ended.append)
    assert len(ended) >= 1
    assert sum(rollout.done) == len(ended) or sum(rollout.done) == len(ended) - 1
    assert rollout.last_value == 0.0 or env.player_of(env.agent_selection) == 0


def test_the_anchor_holds_the_policy_and_the_same_policy_has_no_divergence():
    """The KL term reads zero against a copy, and an update with a heavy anchor stays put."""
    import copy

    torch.manual_seed(0)
    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=9)
    policy = Policy(env.spaces_record, NetConfig(channels=4, board_width=32, unit_width=16, hidden=32))
    generator = torch.Generator().manual_seed(0)
    rollout = ppo.collect(env, policy, 0, ppo.random_opponent, 32, generator)
    anchor = copy.deepcopy(policy)
    for parameter in anchor.parameters():
        parameter.requires_grad_(False)
    with pytest.raises(ValueError):
        ppo.update(policy, torch.optim.Adam(policy.parameters()), rollout, ppo.PpoConfig(anchor_kl=1.0, epochs=1, minibatch=32), env.spaces_record)
    free = copy.deepcopy(policy)
    ppo.update(free, torch.optim.Adam(free.parameters(), lr=1e-2), rollout, ppo.PpoConfig(epochs=4, minibatch=16), env.spaces_record)
    held = copy.deepcopy(policy)
    stats = ppo.update(held, torch.optim.Adam(held.parameters(), lr=1e-2), rollout, ppo.PpoConfig(epochs=4, minibatch=16, anchor_kl=50.0), env.spaces_record, anchor)
    assert stats["anchor_kl"] >= 0.0 and math.isfinite(stats["anchor_kl"])

    def divergence(other: Policy) -> float:
        spaces = env.spaces_record
        import numpy as np

        parts = (
            torch.from_numpy(np.stack(rollout.board)),
            torch.from_numpy(np.stack(rollout.units)),
            torch.from_numpy(np.stack(rollout.scalars)),
            torch.from_numpy(np.stack(rollout.unit_mask).astype(np.float32)),
            torch.from_numpy(np.stack(rollout.action_mask).astype(np.float32).reshape(-1, spaces.units, spaces.actions)),
            torch.from_numpy(np.stack(rollout.target_mask).astype(np.float32)),
            torch.from_numpy(np.stack(rollout.option_mask).astype(np.float32)),
            torch.tensor(rollout.unit),
            torch.tensor(rollout.action),
            torch.tensor(rollout.target),
        )
        with torch.no_grad():
            mine = other.head_logits(*parts)
            theirs = anchor.head_logits(*parts)
            return float(ppo.anchor_divergence(*mine[:4], *theirs[:4]).mean().item())

    assert divergence(anchor) == pytest.approx(0.0, abs=1e-6), "a policy has no divergence from its own copy"
    assert divergence(held) < divergence(free), "the anchor kept the policy nearer the start"


def test_the_anchor_divergence_is_finite_where_the_anchor_underflows():
    """A legal command the anchor holds at a probability below float32 gives a finite term."""
    mine = torch.tensor([[0.0, 0.0, -1e9]])
    theirs = torch.tensor([[0.0, -200.0, -1e9]])
    kl = ppo.anchor_divergence(mine, mine, mine, mine, theirs, theirs, theirs, theirs)
    assert torch.isfinite(kl).all()
    # Four heads, each with the same divergence: half of 200 nats less the entropy gain.
    # p is a half on each legal entry, q is one and e to the minus 200: the divergence is
    # half of 200 nats less the log of two, on each of the four heads.
    assert float(kl[0]) == pytest.approx(4 * (100.0 - math.log(2.0)), rel=1e-3)
    same = ppo.anchor_divergence(mine, mine, mine, mine, mine, mine, mine, mine)
    assert float(same[0]) == pytest.approx(0.0, abs=1e-6)


def test_the_share_cap_holds_no_member_above_it():
    """The loss-rate rule with a cap: the shares add to one and no member is above the cap."""
    from slagents.learned.league import capped_shares

    shares = capped_shares([0.68, 0.60, 0.60, 0.40, 0.05, 0.05], 0.25)
    assert sum(shares) == pytest.approx(1.0)
    assert max(shares) == pytest.approx(0.25)
    assert shares[0] == shares[1] == shares[2] == pytest.approx(0.25)
    # The excess went to the others in proportion to their weight.
    assert shares[3] > shares[4] == shares[5]
    assert capped_shares([0.9, 0.1], 0.5) == pytest.approx([0.5, 0.5])
    assert capped_shares([3.0, 1.0, 1.0], 0.2) == pytest.approx([1 / 3, 1 / 3, 1 / 3]), "a cap below one over the count gives equal shares"
    assert capped_shares([], 0.5) == []
    league = League()
    for name, losses in (("strong", 9), ("weak", 1)):
        member = league.add(Member(name=name, kind="scripted", act=lambda e, o: (0, 0, 0)))
        member.games = 10
        member.losses = losses
    assert league.weights() == [0.9, 0.1]
    league.share_cap = 0.6
    assert league.weights() == pytest.approx([0.6, 0.4])
    generator = torch.Generator().manual_seed(1)
    drawn = [league.sample(generator).name for _ in range(400)]
    assert 0.5 < drawn.count("strong") / 400 < 0.7, "the sample follows the capped shares"


def test_the_named_opponents_are_the_only_league_members(tmp_path: Path):
    """`--opponents v7`: the league holds v7 alone, and no snapshot of the learner joins it."""
    engine = build_engine(SCENARIO)
    league = build_league(engine, 1, ["v7"])
    assert [m.spec for m in league.members] == ["v7"]
    assert [m.name for m in build_league(engine, 1, ["random", "v1"]).members][0] == "random"
    art = run_training(
        scenario=SCENARIO,
        steps=200,
        hours=0.0,
        seed=5,
        learner_player=0,
        snapshot_every=100,
        config=ppo.PpoConfig(steps_per_update=100, minibatch=64, epochs=1),
        net=NetConfig(),
        out=tmp_path,
        log_dir=None,
        opponents=["v1"],
    )
    assert art.config["opponents"] == [m.name for m in build_league(engine, 5, ["v1"]).members]
    assert art.config["fixed_opponents"] is True
    assert art.stats["snapshots"], "the run still writes its snapshots"
    assert [row["name"] for row in art.stats["league"]] == art.config["opponents"], "no snapshot joined the league"


def test_the_value_warm_up_changes_the_value_head_alone():
    """The warm-up fits the value head to the policy's own returns (PIRLNav). The trunk is
    shared with the policy heads, so it and each policy head keep their weights, and the
    policy gives the same distribution as before."""
    import copy

    torch.manual_seed(0)
    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=9)
    policy = Policy(env.spaces_record, NetConfig(channels=4, board_width=32, unit_width=16, hidden=32))
    generator = torch.Generator().manual_seed(0)
    rollout = ppo.collect(env, policy, 0, ppo.random_opponent, 64, generator)
    before = copy.deepcopy(policy.state_dict())
    config = ppo.PpoConfig(epochs=4, minibatch=16)
    optimizer = torch.optim.Adam(policy.parameters(), lr=1e-2)
    first = ppo.update(policy, optimizer, rollout, config, env.spaces_record, value_only=True)
    for _ in range(5):
        last = ppo.update(policy, optimizer, rollout, config, env.spaces_record, value_only=True)
    assert first["value_only"] == 1.0
    assert last["value_loss"] < first["value_loss"], "the value head fits the returns"
    after = policy.state_dict()
    for name, weights in before.items():
        if name.startswith("value_head."):
            continue
        assert torch.equal(weights, after[name]), f"{name} changed in the warm-up"
    assert any(not torch.equal(before[n], after[n]) for n in before if n.startswith("value_head."))
    # The full update changes the policy heads.
    full = ppo.update(policy, optimizer, rollout, config, env.spaces_record)
    assert full["value_only"] == 0.0
    assert any(not torch.equal(before[n], policy.state_dict()[n]) for n in before if n.startswith("unit_head."))


def test_the_run_trains_the_value_head_alone_in_the_warm_up(tmp_path: Path):
    art = run_training(
        scenario=SCENARIO,
        steps=256,
        hours=0.0,
        seed=5,
        learner_player=0,
        snapshot_every=0,
        config=ppo.PpoConfig(steps_per_update=128, minibatch=64, epochs=1, value_warmup_steps=128),
        net=NetConfig(channels=4, board_width=32, unit_width=16, hidden=32),
        out=tmp_path,
        log_dir=None,
    )
    assert art.config["ppo"]["value_warmup_steps"] == 128
    assert art.stats["updates"] == 2
    assert art.stats["value_warmup_updates"] == 1, "the first update of 128 steps is the warm-up"
