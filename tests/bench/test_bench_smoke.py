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
    code = main(["bench", "--workers", "1", "--seconds", "1", "--out", str(stats)])
    report = json.loads(stats.read_text(encoding="utf-8"))
    assert report["runs"][0]["steps"] > 0 and "hardware" in report
    assert code == (0 if report["passed"] else 1)


def test_the_workers_play_on_the_table_that_the_parent_filled(tmp_path: Path):
    from slcli.bench import warm_los

    los, seconds = warm_los("s00_movement_drill", None)
    assert seconds >= 0 and len(los.results) > 1000
    result = run_bench("s00_movement_drill", None, 1, 2.0, los)
    assert not result["worker_failures"] and result["steps"] > 100
    stats = tmp_path / "stats.json"
    main(["bench", "--workers", "1", "--seconds", "1", "--out", str(stats)])
    report = json.loads(stats.read_text(encoding="utf-8"))
    assert report["los_warm"] is True and "los_warm_seconds" in report
    main(["bench", "--workers", "1", "--seconds", "1", "--no-warm-los", "--out", str(stats)])
    report = json.loads(stats.read_text(encoding="utf-8"))
    assert report["los_warm"] is False and "los_warm_seconds" not in report
