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


def test_the_side_baseline_counts_the_panel_and_the_mirror_games_on_each_side(capsys):
    """A one-sided scenario hides the skill of an attacker. The baseline puts the wins of
    the candidate on each side next to the wins of the other panel agents and of the
    opponent against itself, on that side against that opponent."""
    from slcli.gauntlet import _print_leaderboard

    plain = run_gauntlet(candidate="v1", panel=["random", "v0"], scenarios=["s00_movement_drill"], games=4, seed=7)
    art = run_gauntlet(candidate="v1", panel=["random", "v0"], scenarios=["s00_movement_drill"], games=4, seed=7, mirror=True)
    # The mirror games come after the round-robin and are not in its seeds, Elo, or rows.
    assert art.stats["pairs"] == plain.stats["pairs"]
    assert art.stats["leaderboard"] == plain.stats["leaderboard"]
    assert art.stats["games"] == plain.stats["games"] == 12
    assert [(m["agent"], m["games"]) for m in art.stats["mirror"]] == [("random", 4), ("v0", 4)]
    for row in art.stats["pairs"]:
        assert sum(row["a_games_by_side"].values()) == sum(row["b_games_by_side"].values()) == row["completed"]
    baseline = art.stats["side_baseline"]
    # Two opponents and two sides.
    assert len(baseline) == 4
    for entry in baseline:
        # The candidate plays 4 games against each opponent, 2 on each side; the one other
        # panel agent plays it the same way.
        assert entry["candidate"]["games"] == 2 and entry["panel"]["games"] == 2
        assert 0 <= entry["candidate"]["wins"] <= 2 and 0 <= entry["panel"]["wins"] <= 2
        assert entry["mirror"]["games"] == 4
    for opponent in ("random", "v0"):
        mirror_wins = sum(e["mirror"]["wins"] for e in baseline if e["opponent"] == opponent)
        row = next(m for m in art.stats["mirror"] if m["agent"] == opponent)
        assert mirror_wins == sum(row["wins_by_side"].values()) <= 4
    assert "mirror" not in plain.stats and all("mirror" not in e for e in plain.stats["side_baseline"])
    _print_leaderboard(art, "v1")
    out = capsys.readouterr().out
    assert "the side baseline" in out and out.count(" against random ") >= 2


def test_the_panel_keeps_a_comma_inside_a_parameter_set():
    from slcli.gauntlet import split_agent_names

    assert split_agent_names("v1,v7[loss_scale=8,fire_floor=4],v6") == ["v1", "v7[loss_scale=8,fire_floor=4]", "v6"]
    assert split_agent_names("random, v0 ,") == ["random", "v0"]


def test_a_gauntlet_records_the_rates_of_a_model_agent(monkeypatch):
    """TC-16 and OR-02 in the gauntlet: the artifact holds the rates and the decision time
    of each model agent of each game. The test gives the worker a model agent on a provider
    with no answer, through the factory the workers use, so no network is touched."""
    from slagents.prompted.harness import PromptedAgent
    from slagents.prompted.providers import Answer, ProviderUnavailable, load_config
    from slagents.prompted.providers.base import Provider, ProviderConfig
    from slcli import gauntlet as module
    from slcli.play import make_agent

    class Silent(Provider):
        """A provider that never answers, so each decision is a timeout and a fallback."""

        def health(self) -> bool:
            return False

        def complete(self, system, user, max_tokens=700, temperature=0.2, json_schema=None) -> Answer:
            raise ProviderUnavailable("the test provider does not answer")

    config = load_config()
    row = ProviderConfig(name="silent", kind="openai_compatible", endpoint=config.allowlist[-1] + "/v1", model="silent-1")

    def factory(kind, engine, seed, player):
        if kind == "model:silent":
            return PromptedAgent(engine, player, Silent(row, config.allowlist), make_agent("v1", engine, seed, player), retries=0)
        return make_agent(kind, engine, seed, player)

    monkeypatch.setattr(module, "make_agent", factory)
    art = run_gauntlet(candidate="model:silent", panel=["v0"], scenarios=["s00_movement_drill"], games=2, seed=3, anchor_only=True)
    rows = art.stats["harness"]
    assert len(rows) == 2 and {row["side"] for row in rows} == {"russian", "german"}
    for row in rows:
        assert row["agent"] == "model:silent"
        assert row["fallbacks"] == row["timeouts"] > 0
        for field in ("invalid_rate", "retry_rate", "fallback_rate", "timeout_rate", "median_seconds"):
            assert field in row, field


def test_the_progress_line_names_each_game_that_ends(capsys):
    """A long gauntlet of a model agent shows how far it is: one line on the error stream
    for each game, with the pair, the seed, and the result. The output stream keeps the
    table alone, so a caller that reads the table reads nothing else."""
    art = run_gauntlet(candidate="v1", panel=["v0"], scenarios=["s00_movement_drill"], games=2, seed=5, anchor_only=True, progress=True)
    captured = capsys.readouterr()
    lines = [line for line in captured.err.splitlines() if line.startswith("game ")]
    assert len(lines) == art.stats["games"] == 2
    assert lines[0].startswith("game 1 of 2: ") and lines[1].startswith("game 2 of 2: ")
    assert all(" seed " in line and " -> " in line and " min)" in line for line in lines)
    assert "game 1 of 2" not in captured.out


def _end_the_worker_on_the_first_try(job):
    """One game of the dead worker test. A job named `die` ends its worker process the
    first time (a marker file in the job's directory records the try), and `always` ends
    it each time. The others give their name as the winner."""
    import os

    directory, seed, first, _second = job
    marker = Path(directory) / f"tried-{seed}"
    if first == "always" or (first == "die" and not marker.exists()):
        marker.write_text("1")
        os._exit(3)
    return {"winner": first, "error": None}


def test_a_dead_worker_process_does_not_stop_the_games(tmp_path: Path):
    """multiprocessing.Pool waited for ever for the game of a dead worker (s04, 2026-10-12)."""
    from slcli.gauntlet import _play_all

    jobs = [(str(tmp_path), seed, name, "x") for seed, name in enumerate(["a", "die", "b", "c", "always", "d", "e"])]
    outcomes = _play_all(jobs, workers=3, play=_end_the_worker_on_the_first_try)
    assert [o["winner"] for o in outcomes] == ["a", "die", "b", "c", None, "d", "e"]
    assert outcomes[4]["error"] == "BrokenProcessPool"
    assert all(o["error"] is None for i, o in enumerate(outcomes) if i != 4)
