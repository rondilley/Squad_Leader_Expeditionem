"""TC-08: each run artifact has its four files, and the SQLite index lists it."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from slcli.tournament import run_tournament
from slruns import artifact
from slruns.elo import EloTable, Record, expected, wilson_interval
from slruns.index import IndexError_, connect, elo_history, list_runs, rebuild, upsert, win_counts


def sample(slug: str = "test-run") -> artifact.RunArtifact:
    art = artifact.RunArtifact(
        kind="tournament",
        slug=slug,
        config={"scenario": "s00_movement_drill", "board": "fixture", "games": 2},
        seeds=[1, 2],
        started=datetime(2026, 9, 7, 12, 0, 0, tzinfo=timezone.utc),
    )
    art.commands = [{"game": 0, "seq": 1, "payload": {"action": "end_phase"}, "hash": "a" * 64}]
    art.events = [{"game": 0, "rule_id": "4.9", "kind": "player_turn_end", "data": {}}]
    art.stats = {
        "games": 2,
        "agents": {"v1": Record(wins=2).to_dict(), "v0": Record(losses=2).to_dict()},
        "elo": {"v1": {"rating": 1516.0, "games": 2}, "v0": {"rating": 1484.0, "games": 2}},
        "results": [
            {"seed": 1, "agent_a": "v1", "agent_b": "v0", "side_a": "russian", "result": "russian", "turns": 3, "commands": 40},
            {"seed": 2, "agent_a": "v0", "agent_b": "v1", "side_a": "russian", "result": "german", "turns": 3, "commands": 44},
        ],
    }
    return art


def test_a_run_has_its_four_files(tmp_path: Path):
    directory = sample().write(tmp_path)
    assert directory.name == "20260907T120000Z-test-run"
    for name in artifact.FILES:
        assert (directory / name).is_file(), name
    assert artifact.complete(directory)
    doc = artifact.read(directory)
    assert doc["manifest"]["kind"] == "tournament"
    assert doc["manifest"]["versions"]["slcore"]
    assert doc["manifest"]["hardware"]["cpu_count"]
    assert doc["commands"]["commands"][0]["payload"]["action"] == "end_phase"
    assert doc["log"]["events"][0]["rule_id"] == "4.9"
    assert doc["stats"]["games"] == 2


def test_an_incomplete_run_is_not_read(tmp_path: Path):
    directory = sample().write(tmp_path)
    (directory / artifact.STATS).unlink()
    assert not artifact.complete(directory)
    with pytest.raises(artifact.ArtifactError):
        artifact.read(directory)
    assert list(artifact.find_runs(tmp_path)) == []


def test_the_index_round_trips_and_an_upsert_is_idempotent(tmp_path: Path):
    directory = sample().write(tmp_path)
    conn = connect(tmp_path / "runs.sqlite")
    try:
        run_id = upsert(conn, directory)
        assert run_id == directory.name
        rows = list_runs(conn)
        assert len(rows) == 1 and rows[0]["scenario"] == "s00_movement_drill"
        assert json.loads(rows[0]["stats"])["games"] == 2
        assert win_counts(conn, run_id) == {"russian": 1, "german": 1}
        upsert(conn, directory)
        upsert(conn, directory)
        assert len(list_runs(conn)) == 1
        assert conn.execute("SELECT COUNT(*) FROM results").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM elo").fetchone()[0] == 2
        history = elo_history(conn, "v1")
        assert len(history) == 1 and history[0]["rating"] == 1516.0
    finally:
        conn.close()


def test_a_failed_rebuild_keeps_the_rows_it_already_had(tmp_path: Path):
    """The delete and the new rows commit together. A bad artifact does not empty the index."""
    kept = sample("kept").write(tmp_path)
    broken = sample("broken")
    broken.started = datetime(2026, 9, 7, 12, 5, 0, tzinfo=timezone.utc)
    broken_dir = broken.write(tmp_path)
    (broken_dir / artifact.STATS).write_text("{not json", encoding="utf-8")
    conn = connect(tmp_path / "runs.sqlite")
    try:
        upsert(conn, kept)
        assert len(list_runs(conn)) == 1
        with pytest.raises(artifact.ArtifactError):
            rebuild(conn, tmp_path)
        rows = list_runs(conn)
        assert len(rows) == 1 and rows[0]["id"] == kept.name
    finally:
        conn.close()


def test_a_rebuild_reads_every_run(tmp_path: Path):
    for i in range(3):
        art = sample(f"run-{i}")
        art.started = datetime(2026, 9, 7, 12, i, 0, tzinfo=timezone.utc)
        art.write(tmp_path)
    conn = connect(tmp_path / "runs.sqlite")
    try:
        assert rebuild(conn, tmp_path) == 3
        assert len(list_runs(conn)) == 3
        assert rebuild(conn, tmp_path) == 3, "a second rebuild gives the same count"
    finally:
        conn.close()


def test_a_broken_artifact_gives_a_typed_error(tmp_path: Path):
    directory = sample().write(tmp_path)
    (directory / artifact.STATS).write_text("{not json", encoding="utf-8")
    conn = connect(tmp_path / "runs.sqlite")
    try:
        with pytest.raises(artifact.ArtifactError):
            upsert(conn, directory)
    finally:
        conn.close()


def test_elo_moves_the_two_ratings():
    table = EloTable()
    assert expected(1500.0, 1500.0) == pytest.approx(0.5)
    a, b = table.update("winner", "loser", 1.0)
    assert a == pytest.approx(1516.0)
    assert b == pytest.approx(1484.0)
    assert table.games == {"winner": 1, "loser": 1}
    table.update("winner", "loser", 0.5)
    assert table.rating("winner") < 1516.0, "a draw against a weaker agent costs rating"
    with pytest.raises(ValueError):
        table.update("winner", "loser", 2.0)


def test_the_win_rate_interval_holds_the_ends():
    low, high = wilson_interval(0, 10)
    assert low == 0.0 and 0.0 < high < 0.4
    low, high = wilson_interval(10, 10)
    assert 0.6 < low < 1.0 and high == pytest.approx(1.0)
    low, high = wilson_interval(5, 10)
    assert low < 0.5 < high
    assert wilson_interval(0, 0) == (0.0, 1.0)
    record = Record(wins=7, losses=3)
    d = record.to_dict()
    assert d["games"] == 10 and d["win_rate"] == 0.7
    assert d["confidence_low"] < 0.7 < d["confidence_high"]


def test_a_tournament_writes_a_run_that_the_index_lists(tmp_path: Path):
    art = run_tournament("s00_movement_drill", None, "v1", "v0", 2, 1, balance=True)
    assert art.stats["games"] == 2
    assert art.stats["results"][0]["agent_a"] == "v1"
    assert art.stats["results"][1]["agent_a"] == "v0", "the sides change on the second game"
    directory = art.write(tmp_path)
    conn = connect(tmp_path / "runs.sqlite")
    try:
        upsert(conn, directory)
        rows = list_runs(conn, kind="tournament")
        assert len(rows) == 1 and rows[0]["games"] == 2
    finally:
        conn.close()
    assert len(art.commands) > 20
    assert all("game" in c for c in art.commands)


def test_settled_ratings_do_not_depend_on_the_order_of_the_games():
    """The first gauntlet ranked the best win rate fourth because its pair played first."""
    from slruns.elo import settled_ratings

    results = [("a", "b", 1.0)] * 6 + [("a", "b", 0.0)] * 2 + [("b", "c", 1.0)] * 5 + [("b", "c", 0.0)] * 3 + [("a", "c", 1.0)] * 7 + [("a", "c", 0.0)]
    forward = settled_ratings(results).to_dict()
    backward = settled_ratings(list(reversed(results))).to_dict()
    for agent in ("a", "b", "c"):
        assert abs(forward[agent]["rating"] - backward[agent]["rating"]) < 2.0, agent
        assert forward[agent]["games"] == sum(1 for r in results if agent in r[:2])
    assert forward["a"]["rating"] > forward["b"]["rating"] > forward["c"]["rating"]
    one_pass = EloTable()
    for first, second, score in results:
        one_pass.update(first, second, score)
    # The one pass rates the pair that played first by the games at the end of the list
    # as much as by its own, so the two tables differ. The settled one is the record.
    assert one_pass.to_dict() != forward


def test_a_long_slug_is_cut_with_a_hash_of_the_whole():
    """A v7 parameter text can be 300 characters, and a Windows path has 260. The slug
    keeps its head and a hash of the whole, so two long texts give two run directories
    and the same text gives the same one."""
    from slruns.artifact import SLUG_LIMIT, slugify

    long_a = "gauntlet-v7[" + ",".join(f"parameter_{i}={i}" for i in range(40)) + "]"
    long_b = long_a.replace("parameter_39=39", "parameter_39=40")
    a, b = slugify(long_a), slugify(long_b)
    assert len(a) <= SLUG_LIMIT and len(b) <= SLUG_LIMIT
    assert a != b and a == slugify(long_a)
    assert a.startswith("gauntlet-v7-parameter-0-0")
    assert slugify("gauntlet-v7") == "gauntlet-v7"
