"""The gauntlet ranks a candidate against a field and writes one run artifact."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slcli.gauntlet import run_gauntlet
from slruns import artifact
from slruns.index import connect, list_runs, upsert


def test_a_small_gauntlet_ranks_the_field_and_writes_an_artifact(tmp_path: Path):
    art = run_gauntlet(
        candidate="v1",
        panel=["random", "v0"],
        scenarios=["s00_movement_drill"],
        games=2,
        seed=1,
    )
    stats = art.stats
    board = stats["leaderboard"]
    names = {row["agent"] for row in board}
    assert names == {"v1", "random", "v0"}, "every field agent is on the board"
    # Full round-robin of three agents on one scenario, two games each pair: 3 pairs * 2 = 6.
    assert stats["games"] == 6
    # The board is sorted by Elo, highest first.
    elos = [row["elo"] for row in board]
    assert elos == sorted(elos, reverse=True)
    # Each agent played two pairs of two games, so four games each.
    for row in board:
        assert row["games"] == 4
    # Every game has a Wilson interval that brackets the win rate.
    for row in board:
        assert row["confidence_low"] <= row["win_rate"] <= row["confidence_high"]

    directory = art.write(tmp_path)
    doc = artifact.read(directory)
    assert doc["manifest"]["kind"] == "gauntlet"
    saved = json.loads((directory / artifact.STATS).read_text(encoding="utf-8"))
    assert saved["leaderboard"][0]["agent"] in names
    conn = connect(tmp_path / "runs.sqlite")
    try:
        upsert(conn, directory)
        rows = list_runs(conn, kind="gauntlet")
        assert len(rows) == 1
    finally:
        conn.close()


def test_anchor_only_skips_panel_against_panel(tmp_path: Path):
    art = run_gauntlet(
        candidate="v1",
        panel=["random", "v0"],
        scenarios=["s00_movement_drill"],
        games=2,
        seed=1,
        anchor_only=True,
    )
    # Candidate against each of two panel agents, two games each: 2 pairs * 2 = 4.
    assert art.stats["games"] == 4
    pairs = art.stats["pairs"]
    for row in pairs:
        assert "v1" in (row["agent_a"], row["agent_b"]), "anchor-only plays the candidate in every pair"


def test_the_gauntlet_needs_a_field_of_two_or_more():
    with pytest.raises(ValueError):
        run_gauntlet(candidate="v1", panel=[], scenarios=["s00_movement_drill"], games=1, seed=1)


def test_workers_give_the_same_result_as_one_process():
    """The list of games is fixed before the first game, so a pool changes only the clock."""
    alone = run_gauntlet(candidate="v1", panel=["random", "v0"], scenarios=["s00_movement_drill"], games=2, seed=3)
    pooled = run_gauntlet(
        candidate="v1", panel=["random", "v0"], scenarios=["s00_movement_drill"], games=2, seed=3, workers=2
    )
    assert pooled.seeds == alone.seeds
    assert pooled.stats["pairs"] == alone.stats["pairs"]
    assert pooled.stats["leaderboard"] == alone.stats["leaderboard"]
    assert pooled.config["workers"] == 2
    # Each pair row says how many games each agent won on each side of the scenario.
    for row in pooled.stats["pairs"]:
        assert sum(row["a_wins_by_side"].values()) == row["a_wins"]
        assert sum(row["b_wins_by_side"].values()) == row["b_wins"]


def test_the_panel_keeps_a_comma_inside_a_parameter_set():
    from slcli.gauntlet import split_agent_names

    assert split_agent_names("v1,v7[loss_scale=8,fire_floor=4],v6") == ["v1", "v7[loss_scale=8,fire_floor=4]", "v6"]
    assert split_agent_names("random, v0 ,") == ["random", "v0"]
