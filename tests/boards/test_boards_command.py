"""The boards command writes the TC-14a evidence and the documents for the scoring session."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from slcli.boards_cmd import check_boards, write_boards
from slcli.main import main
from slruns import artifact
from slruns.index import connect, list_runs, upsert


def test_the_check_run_holds_the_criterion_and_the_retry_rate():
    art = check_boards(12, 1, "s01_guards_counterattack")
    stats = art.stats
    assert stats["boards"] == 12
    assert stats["edge_failures"] == []
    assert stats["join_failures"] == []
    assert stats["setup_failures"] == []
    assert stats["passed"] == {"TC-14a": True}
    assert 0.0 <= stats["retry_rate"] <= 0.25
    for retry in stats["retries"]:
        assert retry["used"] > retry["asked"], "a retry moves to a later seed"
    assert art.config["criteria"] == ["TC-14a"]
    assert len(art.seeds) == 12


def test_the_run_artifact_reaches_the_index(tmp_path: Path):
    art = check_boards(4, 50, "s01_guards_counterattack")
    directory = art.write(tmp_path)
    assert artifact.complete(directory)
    conn = connect(tmp_path / "runs.sqlite")
    try:
        upsert(conn, directory)
        rows = list_runs(conn, kind="boards")
        assert len(rows) == 1 and rows[0]["id"] == art.id
    finally:
        conn.close()


def test_the_command_writes_board_documents_that_carry_their_parameters(tmp_path: Path):
    out = tmp_path / "boards"
    assert write_boards(3, 900, out) == 0
    files = sorted(out.glob("*.json"))
    assert len(files) == 3
    doc = json.loads(files[0].read_text(encoding="utf-8"))
    assert doc["generator"]["board_type"] == "city"
    assert doc["hexes"], "a board document holds its hexes"


def test_the_command_line_runs_the_check_and_reports_zero(tmp_path: Path):
    code = main(["boards", "--count", "3", "--seed", "77", "--runs", str(tmp_path)])
    assert code == 0
    runs = [p for p in tmp_path.iterdir() if p.is_dir()]
    assert len(runs) == 1
    stats = json.loads((runs[0] / artifact.STATS).read_text(encoding="utf-8"))
    assert stats["passed"]["TC-14a"] is True


def test_the_type_plan_spreads_the_count_over_the_four_types():
    from slboards.generator import BOARD_TYPES
    from slcli.boards_cmd import types_for

    plan = types_for(12, "all")
    assert len(plan) == 12
    assert sorted(set(plan)) == sorted(BOARD_TYPES)
    assert all(plan[i] != plan[i + 1] for i in range(len(plan) - 1))
    assert types_for(3, "hills") == ["hills"] * 3


def test_an_unknown_type_names_the_types_the_generator_makes():
    from slcli.boards_cmd import types_for

    with pytest.raises(ValueError) as exc:
        types_for(2, "tundra")
    assert "city" in str(exc.value)


def test_the_scoring_set_holds_three_boards_of_each_type_and_an_empty_sheet(tmp_path: Path):
    """TC-14b: 12 boards, 3 of each type, with a sheet the owner fills in."""
    from slcli.boards_cmd import write_boards

    assert write_boards(12, 5000, tmp_path) == 0
    documents = sorted(p.stem for p in tmp_path.glob("*.json"))
    assert len(documents) == 12
    for name in ("city", "hills", "village", "rural"):
        assert sum(1 for d in documents if d.startswith(name)) == 3
    sheet = (tmp_path / "scores.md").read_text(encoding="utf-8")
    assert "TC-14b" in sheet
    for name in documents:
        assert name in sheet
    # The command writes no score. A score in the sheet would be the developer scoring it.
    for line in sheet.splitlines():
        if any(line.startswith(f"| {name} ") for name in documents):
            assert not re.search(r"[1-5]", line.split("|", 2)[2])
