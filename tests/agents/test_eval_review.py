"""The evaluation corrections of the review of 2026-09-23 (L3, L4, L7).

L3: a league member plays one whole game. L4: the evaluation of a training run plays
seeds the training did not. L7: the two side orders of a pair share one seed, the
Bradley-Terry fit has a side term, and each command family plays its own range of seeds.
"""

from __future__ import annotations

import itertools

import pytest

pytest.importorskip("torch")
pytest.importorskip("gymnasium")
pytest.importorskip("pettingzoo")

import torch

from slagents.learned import ppo
from slagents.learned.env import make_env
from slagents.learned.nets import NetConfig, Policy
from slcli.gauntlet import run_gauntlet
from slcli.play import build_engine
from slcli.tournament import run_tournament
from slruns.elo import settled_ratings, settled_ratings_by_side
from slruns.seeds import FAMILY_BASE, FAMILY_STRIDE, UnknownFamily, family_seed, rate_text, sample_warning

SCENARIO = "s01_guards_counterattack"
SMALL = NetConfig(channels=4, hidden=16)


def test_a_new_game_takes_its_opponent_from_the_league_and_keeps_it_to_the_end():
    """L3: the opponent of a game is the one it started with, for each of its commands.
    Before this the one-process trainer sampled a member for each rollout, and a game
    that crossed two rollouts had two opponents and one record."""
    torch.manual_seed(0)
    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=4, max_commands=40)
    policy = Policy(env.spaces_record, SMALL)
    generator = torch.Generator().manual_seed(0)
    names = itertools.count()
    played: list[tuple[int, str]] = []
    ended: list[float] = []

    def member(name: str):
        def act(env, observation):
            played.append((env.seed_value, name))
            return ppo.random_opponent(env, observation)

        return act

    def next_opponent():
        return member(f"m{next(names)}")

    rollout = ppo.collect(env, policy, 0, member("first"), 120, generator, ended.append, next_opponent=next_opponent)
    assert len(rollout) == 120 and len(ended) >= 3, "the short games gave several games in one collection"
    by_game: dict[int, set[str]] = {}
    for seed, name in played:
        by_game.setdefault(seed, set()).add(name)
    assert all(len(opponents) == 1 for opponents in by_game.values()), by_game
    assert len({name for opponents in by_game.values() for name in opponents}) == len(by_game), "each game has its own draw"


def test_the_evaluation_plays_its_own_range_of_seeds_two_sides_on_each():
    """L4: the training plays the seeds from its first seed up, so the evaluation plays
    in the evaluation range, and the two games of a side pair share one seed (L7)."""
    from slcli.train import build_league, evaluate

    engine = build_engine(SCENARIO)
    env = make_env(engine, seed=70, max_commands=40)
    policy = Policy(env.spaces_record, SMALL)
    league = build_league(engine, 70)
    league.members = league.members[:1]
    rows = evaluate(env, policy, league, 0, 4, first_seed=70)
    row = rows[0]
    assert row["seeds"] == [family_seed("train_evaluation", 70, 1), family_seed("train_evaluation", 70, 2)]
    assert all(seed >= FAMILY_STRIDE for seed in row["seeds"]), "no evaluation seed is a training seed"
    assert sum(row["by_side"]["player_0"].values()) == 2 and sum(row["by_side"]["player_1"].values()) == 2


def test_the_side_term_takes_out_the_side_the_scenario_favours():
    """L7: two agents of the same strength on a scenario that gives the first side 200
    Elo points. Agent a held the first side five times more often. The fit with no side
    term ranks a far above b; the fit with the term finds them level and the 200 points."""
    results: list[tuple[str, str, float, str]] = []
    # P(first side wins) at 200 points is 0.76.
    results += [("a", "b", 1.0, "s")] * 76 + [("a", "b", 0.0, "s")] * 24
    results += [("b", "a", 1.0, "s")] * 15 + [("b", "a", 0.0, "s")] * 5
    plain = settled_ratings([(first, second, score) for first, second, score, _ in results]).to_dict()
    assert plain["a"]["rating"] - plain["b"]["rating"] > 100, "the plain fit credits the side to agent a"
    fit = settled_ratings_by_side(results)
    table = fit.table.to_dict()
    assert abs(table["a"]["rating"] - table["b"]["rating"]) < 25
    assert 170 < fit.side_advantage["s"] < 215
    assert table["a"]["games"] == table["b"]["games"] == 120
    reverse = settled_ratings_by_side(list(reversed(results)))
    assert reverse.to_dict() == fit.to_dict(), "the fit reads the results as a set"


def test_the_gauntlet_plays_both_side_orders_on_one_seed_and_reports_the_side_term():
    art = run_gauntlet(candidate="v1", panel=["v0"], scenarios=["s00_movement_drill"], games=4, seed=1, anchor_only=True)
    assert art.stats["games"] == 4
    assert art.seeds == [family_seed("gauntlet", 1, 0), family_seed("gauntlet", 1, 1)], "four games on two seeds"
    assert art.config["paired_seeds"] is True
    advantage = art.stats["side_advantage"]["s00_movement_drill"]
    assert advantage["first_side"] == "russian" and isinstance(advantage["elo"], float)


def test_the_tournament_plays_both_side_orders_on_one_seed():
    art = run_tournament("s00_movement_drill", None, "v1", "v0", 4, 1, balance=True)
    seeds = [row["seed"] for row in art.stats["results"]]
    first = family_seed("tournament", 1)
    assert seeds == [first, first, first + 1, first + 1]
    orders = [(row["agent_a"], row["agent_b"]) for row in art.stats["results"]]
    assert orders[0] == orders[1][::-1] and orders[2] == orders[3][::-1]
    assert "s00_movement_drill" in art.stats["side_advantage"]


def test_each_command_family_plays_its_own_range_of_seeds():
    """L7: the default --seed 1 of each command gave the same seeds to train, gauntlet,
    and evolve. A family's range is one stride wide, and no two ranges meet."""
    ranges = sorted((base, base + FAMILY_STRIDE) for base in FAMILY_BASE.values())
    assert all(high <= nxt for (_, high), (nxt, _) in zip(ranges, ranges[1:]))
    assert family_seed("train", 1, 5) == 6, "training keeps its seeds"
    assert family_seed("gauntlet", 1) != family_seed("evolve", 1) != family_seed("tournament", 1)
    with pytest.raises(UnknownFamily):
        family_seed("no_such_command", 1)
    assert rate_text(1, 20) == "1 of 20 (5.0 percent, 95 percent interval 0.9 to 23.6)"
    assert sample_warning(20) is not None and sample_warning(200) is None
