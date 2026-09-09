"""The gate command writes the evidence that TC-04, TC-05, TC-10, and TC-38 ask for."""

from __future__ import annotations

import json
from pathlib import Path

from slboards.generator import GENERATOR_VERSION, GeneratorParameters, generate
from slcli.gates import replay_with_shuffle, run_gate
from slcli.play import build_engine, play_game
from slagents.base import RandomAgent
from slruns import artifact
from slruns.index import connect, list_runs, upsert
from sldata.loaders import load_terrain


def test_the_gate_run_records_each_criterion(tmp_path: Path):
    art = run_gate("s00_movement_drill", None, "v1", "v0", 3, 1, shuffle_games=3)
    stats = art.stats
    assert stats["games"] == 3
    assert stats["unhandled_errors"] == []
    assert stats["replay_mismatches"] == []
    assert stats["shuffle_mismatches"] == []
    assert stats["median_seconds"] is not None and stats["median_seconds"] < 15.0
    assert stats["passed"] == {"TC-04": True, "TC-05": True, "TC-10": True, "TC-38": True}
    assert "5.5" in stats["rule_ids_applied"], "the games applied the movement rule"
    assert art.config["criteria"] == ["TC-04", "TC-05", "TC-10", "TC-38"]
    assert art.commands and art.events, "the first game is kept in full"

    directory = art.write(tmp_path)
    doc = artifact.read(directory)
    assert doc["manifest"]["kind"] == "gate"
    assert json.loads((directory / artifact.STATS).read_text(encoding="utf-8"))["games"] == 3
    conn = connect(tmp_path / "runs.sqlite")
    try:
        upsert(conn, directory)
        rows = list_runs(conn, kind="gate")
        assert len(rows) == 1 and rows[0]["games"] == 3
    finally:
        conn.close()


def test_the_shuffled_replay_uses_the_command_id_not_a_position():
    engine = build_engine("s00_movement_drill")
    record = play_game(engine, 5, (RandomAgent(5, 0), RandomAgent(5, 1)))
    assert replay_with_shuffle(engine, record)
    broken = type(record)(**{**record.__dict__})
    broken.commands = [dict(c) for c in record.commands]
    broken.commands[3]["command_id"] = "0" * 16
    assert not replay_with_shuffle(engine, broken), "an ID that is not in the frame must fail the check"


def test_the_manifest_of_a_generated_board_carries_the_parameters_that_built_it(tmp_path: Path):
    """FR-25: a later session builds the same board from the run artifact alone."""
    art = run_gate("s01_guards_counterattack", None, "v1", "v1", 1, 900, shuffle_games=0)
    config = art.manifest()["config"]
    assert config["board_source"] == "generated"
    assert config["board_columns"] == [0, 15]
    generator = config["generator"]
    assert generator["board_type"] == "city"
    assert generator["version"] == GENERATOR_VERSION
    assert generator["zones"] == [
        {"count": 5, "min_hexes": 2, "max_hexes": 6, "min_col": 0, "max_col": 7},
        {"count": 1, "min_hexes": 4, "max_hexes": 6, "min_col": 0, "max_col": 7},
        {"count": 5, "min_hexes": 2, "max_hexes": 6, "min_col": 8, "max_col": 15},
    ]

    directory = art.write(tmp_path)
    stored = artifact.read(directory)["manifest"]["config"]["generator"]
    board = generate(GeneratorParameters.from_dict(stored), load_terrain())
    assert board.subset_columns(0, 15).name == config["board"]
