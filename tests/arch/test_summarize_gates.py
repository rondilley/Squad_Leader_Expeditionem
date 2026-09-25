"""The gate summaries of `tools/summarize_gates.py` (B10).

The run tree of each test is in tmp. The artifacts in it are real: `sl-cli gate`,
`sl-cli boards`, and `sl-cli bench` wrote them with their own writers on short runs.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from slcli import bench, boards_cmd, gates

ROOT = Path(__file__).resolve().parents[2]


def load_tool():
    spec = importlib.util.spec_from_file_location("summarize_gates", ROOT / "tools" / "summarize_gates.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def run_tree(tmp_path_factory):
    runs = tmp_path_factory.mktemp("runs")
    older = gates.run_gate("s00_movement_drill", None, "v1", "v1", 2, 1, 1)
    older.started = datetime(2026, 9, 1, tzinfo=timezone.utc)
    older.write(runs)
    newer = gates.run_gate("s00_movement_drill", None, "v1", "v1", 3, 5, 2)
    newer.started = older.started + timedelta(days=1)
    newer.write(runs)
    boards_cmd.check_boards(2, 1, "s01_guards_counterattack").write(runs)
    args = argparse.Namespace(
        workers="1", minutes=0.0, seconds=0.5, scenario="s01_guards_counterattack", board=None, out=str(runs / "bench_tc09.json")
    )
    bench.run(args)
    return runs, newer


def test_newest_artifact_of_each_kind(run_tree):
    tool = load_tool()
    runs, newer = run_tree
    docs = tool.summaries(runs)
    assert sorted(docs) == ["bench", "boards", "gate"]
    gate = docs["gate"]
    assert gate["run_id"] == newer.id
    assert gate["date"] == newer.manifest()["started"]
    assert gate["measured"]["games"] == 3
    assert gate["measured"]["unhandled_errors"] == 0


def test_gate_status_against_the_bar(run_tree):
    tool = load_tool()
    runs, _ = run_tree
    gate = tool.summaries(runs)["gate"]
    criteria = gate["criteria"]
    # Three games with no error satisfy the run itself, but not the sample of the bar.
    assert criteria["TC-04"]["self_reported"] is True
    assert criteria["TC-04"]["status"] == "short"
    assert criteria["TC-05"]["status"] == "short"
    assert criteria["TC-38"]["status"] == "short"
    assert criteria["TC-10"]["status"] == "short"
    assert gate["status"] == "short"
    boards = tool.summaries(runs)["boards"]
    assert boards["measured"]["boards"] == 2
    assert boards["criteria"]["TC-14a"]["status"] == "short"


def test_bench_with_one_worker_fails(run_tree):
    tool = load_tool()
    runs, _ = run_tree
    doc = tool.summaries(runs)["bench"]
    assert doc["artifact"] == "bench_tc09.json"
    assert doc["measured"]["runs"][0]["workers"] == 1
    assert doc["criteria"]["TC-09"]["status"] == "fail"
    assert doc["criteria"]["TC-09"]["self_reported"] is False


def test_hash_is_of_the_artifact_files(run_tree):
    tool = load_tool()
    runs, newer = run_tree
    doc = tool.summaries(runs)["gate"]
    directory = runs / newer.id
    assert doc["artifact_sha256"] == tool.files_hash([directory / n for n in ("manifest.json", "commands.json", "log.json", "stats.json")])
    assert len(doc["artifact_sha256"]) == 64
    assert doc["artifact_sha256"] != tool.summaries(runs)["boards"]["artifact_sha256"]


def test_main_writes_one_file_per_kind_and_reads_only(run_tree, tmp_path):
    tool = load_tool()
    runs, _ = run_tree
    before = sorted((p.as_posix(), p.stat().st_mtime_ns) for p in runs.rglob("*"))
    out = tmp_path / "gates"
    assert tool.main(["--runs", str(runs), "--out", str(out)]) == 0
    assert sorted(p.name for p in out.iterdir()) == ["bench.json", "boards.json", "gate.json"]
    doc = json.loads((out / "gate.json").read_text(encoding="utf-8"))
    for key in ("run_id", "date", "kind", "measured", "criteria", "status", "artifact_sha256", "source"):
        assert key in doc
    after = sorted((p.as_posix(), p.stat().st_mtime_ns) for p in runs.rglob("*"))
    assert before == after
    # A second run gives the same bytes, so git sees no change without a new run.
    first = (out / "gate.json").read_text(encoding="utf-8")
    assert tool.main(["--runs", str(runs), "--out", str(out)]) == 0
    assert (out / "gate.json").read_text(encoding="utf-8") == first


def test_missing_run_tree_is_an_error(tmp_path):
    tool = load_tool()
    assert tool.main(["--runs", str(tmp_path / "none"), "--out", str(tmp_path / "gates")]) == 2
