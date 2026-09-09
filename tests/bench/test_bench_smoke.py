import json
from pathlib import Path

from slcli.bench import hardware_manifest, run_bench
from slcli.main import main


def test_bench_one_worker_two_seconds(tmp_path: Path):
    result = run_bench("s00_movement_drill", None, 1, 2.0)
    assert result["steps"] > 100
    assert result["steps_per_second"] > 50
    manifest = hardware_manifest()
    assert manifest["cpu_count"] and manifest["python"]


def test_cli_play_and_bench_write_files(tmp_path: Path):
    out = tmp_path / "games"
    assert main(["play", "--seed", "3", "--games", "2", "--verify", "--out", str(out), "--agent-a", "random", "--agent-b", "v0"]) == 0
    files = sorted(out.glob("game_*.json"))
    assert len(files) == 2
    doc = json.loads(files[0].read_text(encoding="utf-8"))
    assert doc["commands"][0]["payload"]["action"] in ("place", "place_weapon")
    stats = tmp_path / "stats.json"
    assert main(["bench", "--workers", "1", "--seconds", "1", "--out", str(stats)]) == 0
    report = json.loads(stats.read_text(encoding="utf-8"))
    assert report["runs"][0]["steps"] > 0 and "hardware" in report
