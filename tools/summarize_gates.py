"""Write a small summary of each gate run into `gates/` (B10, Slice 9 item 7).

The run artifacts are in `runs/`, and git does not record that directory: it is large and
it stays on the owner's machine. The success-claim guardrail of CLAUDE.md asks for a run
artifact for each gate. This tool reads the newest artifact of each gate kind and writes
one JSON file for it in `gates/`, which git can record. It only reads `runs/`.

Each summary has the run ID, the date, the kind, the measured numbers, the status of each
criterion against the bar of `docs/SUCCESS_CRITERIA.md`, the pass or fail that the run
itself recorded, and a SHA-256 hash of the artifact files. The tool calculates each status
again from the numbers, because a run can record a pass on a sample that is smaller than
the bar.

A status is one of these words:

- `pass`: the numbers satisfy the bar.
- `fail`: the numbers show a failure.
- `short`: no failure, but the sample or the time is less than the bar asks for.
- `measurement`: the criterion has no bar; the summary records the numbers only.

Usage:

    python tools/summarize_gates.py                    # runs/ to gates/
    python tools/summarize_gates.py --runs R --out G
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from slruns import artifact  # noqa: E402

PASS = "pass"
FAIL = "fail"
SHORT = "short"
MEASUREMENT = "measurement"

SOURCE = "docs/SUCCESS_CRITERIA.md"

# The bars of docs/SUCCESS_CRITERIA.md, section "Technical criteria".
TC04_GAMES = 100
TC05_GAMES = 1000
TC10_MEDIAN_SECONDS = 15.0
TC38_GAMES = 100
TC09_STEPS_PER_SECOND = 3500
TC09_SECONDS = 600.0
TC09_WORKERS = (8, 16)
TC14A_BOARDS = 1000
TC15_GAMES = 100
TC15_SCENARIOS = ("s01_guards_counterattack", "s02_tractor_works", "s03a_streets_of_stalingrad")
TC18_GAMES = 200
TC16_RATES = ("invalid_rate", "retry_rate", "fallback_rate", "timeout_rate")


class SummaryError(Exception):
    """A run artifact cannot be read for its summary."""


def criterion(bar: str, status: str, self_reported: bool | None, note: str = "") -> dict[str, Any]:
    out: dict[str, Any] = {"bar": bar, "status": status, "self_reported": self_reported}
    if note:
        out["note"] = note
    return out


def sample_status(failures: int, sample: int, needed: int) -> str:
    if failures:
        return FAIL
    return PASS if sample >= needed else SHORT


def files_hash(paths: list[Path]) -> str:
    """SHA-256 of the files, with the name of each file before its bytes."""
    digest = hashlib.sha256()
    for path in paths:
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise SummaryError(f"cannot read {path}: {exc}") from exc
        digest.update(path.name.encode("utf-8") + b"\0")
        digest.update(data + b"\0")
    return digest.hexdigest()


# ------------------------------------------------------------------ summaries


def summarize_gate(manifest: dict[str, Any], stats: dict[str, Any]) -> tuple[dict, dict]:
    """`sl-cli gate`: TC-04, TC-05, TC-10, TC-38."""
    games = int(stats.get("games", 0))
    errors = len(stats.get("unhandled_errors", []))
    replay = len(stats.get("replay_mismatches", []))
    shuffled = len(stats.get("shuffle_mismatches", []))
    shuffle_games = int(manifest.get("config", {}).get("shuffle_games", 0))
    median = stats.get("median_seconds")
    reported = stats.get("passed", {})
    measured = {
        "scenario": manifest.get("config", {}).get("scenario"),
        "games": games,
        "unhandled_errors": errors,
        "replay_mismatches": replay,
        "shuffle_games": shuffle_games,
        "shuffle_mismatches": shuffled,
        "median_seconds": median,
        "max_seconds": stats.get("max_seconds"),
    }
    median_ok = median is not None and median < TC10_MEDIAN_SECONDS
    criteria = {
        "TC-04": criterion(
            f"{TC04_GAMES} games, 0 unhandled errors, replay hashes agree",
            sample_status(errors + replay, games, TC04_GAMES),
            reported.get("TC-04"),
        ),
        "TC-05": criterion(
            f"{TC05_GAMES} random games, 0 mismatches",
            sample_status(replay, games, TC05_GAMES),
            reported.get("TC-05"),
        ),
        "TC-10": criterion(
            f"median of {TC04_GAMES} games below {TC10_MEDIAN_SECONDS:g} s",
            (PASS if games >= TC04_GAMES else SHORT) if median_ok else FAIL,
            reported.get("TC-10"),
        ),
        "TC-38": criterion(
            f"{TC38_GAMES} random games, 0 mismatches after the shuffle",
            sample_status(shuffled, shuffle_games, TC38_GAMES),
            reported.get("TC-38"),
        ),
    }
    return measured, criteria


def summarize_boards(manifest: dict[str, Any], stats: dict[str, Any]) -> tuple[dict, dict]:
    """`sl-cli boards --count 1000`: TC-14a."""
    boards = int(stats.get("boards", 0))
    failures = sum(len(stats.get(key, [])) for key in ("edge_failures", "join_failures", "setup_failures"))
    measured = {
        "boards": boards,
        "types": stats.get("types", []),
        "edge_failures": len(stats.get("edge_failures", [])),
        "join_failures": len(stats.get("join_failures", [])),
        "setup_failures": len(stats.get("setup_failures", [])),
        "retry_rate": stats.get("retry_rate"),
        "seconds": stats.get("seconds"),
    }
    criteria = {
        "TC-14a": criterion(
            f"100 percent of {TC14A_BOARDS} seeds",
            sample_status(failures, boards, TC14A_BOARDS),
            stats.get("passed", {}).get("TC-14a"),
        )
    }
    return measured, criteria


def summarize_agents(manifest: dict[str, Any], stats: dict[str, Any]) -> tuple[dict, dict]:
    """`sl-cli agents --games 100`: TC-15."""
    pairs = stats.get("pairs", [])
    errors = len(stats.get("unhandled_errors", [])) + len(stats.get("fatal", [])) + len(stats.get("missing_pairs", []))
    played = [int(row.get("played", 0)) for row in pairs]
    scenarios = sorted({row.get("scenario") for row in pairs})
    agents = sorted({row.get("agent") for row in pairs})
    fewest = min(played) if played else 0
    measured = {
        "agents": agents,
        "scenarios": scenarios,
        "pairs": len(pairs),
        "fewest_games_in_a_pair": fewest,
        "games": sum(played),
        "unhandled_errors": len(stats.get("unhandled_errors", [])),
        "fatal": len(stats.get("fatal", [])),
        "missing_pairs": len(stats.get("missing_pairs", [])),
    }
    status = sample_status(errors, fewest, TC15_GAMES)
    missing_scenarios = [s for s in TC15_SCENARIOS if s not in scenarios]
    note = ""
    if status == PASS and missing_scenarios:
        status = SHORT
        note = f"no games of {', '.join(missing_scenarios)}"
    criteria = {
        "TC-15": criterion(
            f"{TC15_GAMES} games of each agent in scenarios 1, 2, and 3A, 0 unhandled errors",
            status,
            stats.get("passed", {}).get("TC-15"),
            note,
        )
    }
    return measured, criteria


def summarize_bench(manifest: dict[str, Any], stats: dict[str, Any]) -> tuple[dict, dict]:
    """`sl-cli bench`: TC-09 (NFR-01)."""
    runs = stats.get("runs", [])
    rows = [
        {"workers": r.get("workers"), "seconds": r.get("seconds"), "steps_per_second": round(float(r.get("steps_per_second", 0.0)), 1)}
        for r in runs
    ]
    gate_rows = [r for r in rows if r["workers"] in TC09_WORKERS]
    best = max((r["steps_per_second"] for r in gate_rows), default=0.0)
    longest = max((float(r["seconds"] or 0.0) for r in gate_rows if r["steps_per_second"] >= TC09_STEPS_PER_SECOND), default=0.0)
    failed = not stats.get("measurement_complete", True)
    measured = {
        "scenario": stats.get("scenario"),
        "hardware": stats.get("hardware", {}).get("platform"),
        "cpu_count": stats.get("hardware", {}).get("cpu_count"),
        "runs": rows,
        "best_steps_per_second_at_8_or_16_workers": best,
    }
    if failed or best < TC09_STEPS_PER_SECOND or stats.get("scenario") != "s01_guards_counterattack":
        status = FAIL
    elif longest < TC09_SECONDS:
        status = SHORT
    else:
        status = PASS
    note = ""
    if status == SHORT:
        note = f"the rate is above the bar, but each worker count ran {longest:g} s of the {TC09_SECONDS:g} s the bar asks for"
    criteria = {
        "TC-09": criterion(
            f"{TC09_STEPS_PER_SECOND} steps/s at 8 or 16 workers, sustained {TC09_SECONDS / 60:g} minutes, scenario 1",
            status,
            stats.get("passed"),
            note,
        )
    }
    return measured, criteria


def summarize_train(manifest: dict[str, Any], stats: dict[str, Any]) -> tuple[dict, dict]:
    """`sl-cli train`: TC-18 at the step count of the run."""
    rows = stats.get("evaluation", [])
    evaluation = []
    status = FAIL
    for row in rows:
        by_side = row.get("by_side", {})
        side_games = sorted(sum(int(v) for v in side.values()) for side in by_side.values())
        balanced = len(side_games) == 2 and side_games[0] == side_games[1]
        entry = {
            "opponent": row.get("opponent"),
            "games": row.get("games"),
            "win_rate": row.get("win_rate"),
            "confidence_low": row.get("confidence_low"),
            "sides_balanced": balanced,
        }
        evaluation.append(entry)
        if str(row.get("opponent", "")).startswith("random"):
            continue
        beats = float(row.get("confidence_low") or 0.0) > 0.5 and float(row.get("win_rate") or 0.0) > 0.5
        if beats and balanced and int(row.get("games") or 0) >= TC18_GAMES:
            status = PASS
        elif beats and status == FAIL:
            status = SHORT
    measured = {
        "steps": stats.get("steps"),
        "steps_per_second": stats.get("steps_per_second"),
        "stopped_because": stats.get("stopped_because"),
        "evaluation": evaluation,
    }
    criteria = {
        "TC-18": criterion(
            f"{TC18_GAMES} games with sides balanced against a versioned scripted agent, win rate and its 95 percent interval above 50 percent",
            status,
            stats.get("passed", {}).get("TC-18"),
            "the ladder rung is the step count of the run",
        )
    }
    return measured, criteria


def summarize_tournament(manifest: dict[str, Any], stats: dict[str, Any]) -> tuple[dict, dict]:
    """`sl-cli tournament`: TC-16 when a model agent played."""
    agents = stats.get("agents", {})
    models = sorted(name for name in agents if name.startswith("model:"))
    harness = stats.get("harness", {})
    measured = {
        "games": stats.get("games"),
        "agents": {name: {k: row.get(k) for k in ("wins", "losses", "draws", "games")} for name, row in agents.items()},
        "harness": {name: {k: harness.get(name, {}).get(k) for k in TC16_RATES} for name in models},
    }
    criteria: dict[str, Any] = {}
    if models:
        recorded = all(name in harness and all(k in harness[name] for k in TC16_RATES) for name in models)
        criteria["TC-16"] = criterion(
            "the four rates of the harness recorded for each model agent",
            PASS if recorded else FAIL,
            None,
            "" if recorded else "the run has no harness counters",
        )
    return measured, criteria


def summarize_gauntlet(manifest: dict[str, Any], stats: dict[str, Any]) -> tuple[dict, dict]:
    """`sl-cli gauntlet`: a measurement with no bar."""
    measured = {
        "games": stats.get("games"),
        "completed": stats.get("completed"),
        "errors": len(stats.get("errors", [])),
        "leaderboard": [
            {k: row.get(k) for k in ("agent", "elo", "wins", "losses", "draws", "games", "confidence_low", "confidence_high")}
            for row in stats.get("leaderboard", [])
        ],
    }
    criteria = {
        "gauntlet": criterion("no bar; the Elo table of the candidate and the panel", MEASUREMENT, None),
    }
    return measured, criteria


SUMMARIZERS: dict[str, Callable[[dict[str, Any], dict[str, Any]], tuple[dict, dict]]] = {
    "gate": summarize_gate,
    "boards": summarize_boards,
    "agents": summarize_agents,
    "bench": summarize_bench,
    "train": summarize_train,
    "tournament": summarize_tournament,
    "gauntlet": summarize_gauntlet,
}


# -------------------------------------------------------------- the run tree


def newest_artifacts(runs: Path) -> dict[str, Path]:
    """The newest complete run artifact of each kind that has a summarizer."""
    newest: dict[str, tuple[str, Path]] = {}
    for directory in artifact.find_runs(runs):
        try:
            manifest = json.loads((directory / artifact.MANIFEST).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SummaryError(f"cannot read the manifest of {directory}: {exc}") from exc
        kind = manifest.get("kind")
        if kind not in SUMMARIZERS or kind == "bench":
            continue
        key = str(manifest.get("started", "")) + directory.name
        if kind not in newest or key > newest[kind][0]:
            newest[kind] = (key, directory)
    return {kind: path for kind, (_, path) in newest.items()}


def bench_reports(runs: Path) -> list[Path]:
    """The stats files that `sl-cli bench --out` wrote for TC-09. They have no manifest."""
    candidates = list(runs.glob("*.json")) + list(runs.glob("*/stats.json"))
    out = []
    for path in candidates:
        if path.name == "stats.json" and (path.parent / artifact.MANIFEST).exists():
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue  # another file of the run tree, not a bench report
        if isinstance(doc, dict) and doc.get("criterion") == "TC-09" and "runs" in doc:
            out.append(path)
    return out


def summarize_artifact(directory: Path, runs: Path) -> dict[str, Any]:
    try:
        doc = artifact.read(directory)
    except artifact.ArtifactError as exc:
        raise SummaryError(str(exc)) from exc
    manifest, stats = doc["manifest"], doc["stats"]
    kind = manifest["kind"]
    measured, criteria = SUMMARIZERS[kind](manifest, stats)
    return {
        "gate": kind,
        "run_id": manifest.get("id", directory.name),
        "date": manifest.get("started"),
        "kind": kind,
        "artifact": directory.relative_to(runs).as_posix(),
        "artifact_sha256": files_hash([directory / name for name in artifact.FILES]),
        "slcore_version": manifest.get("versions", {}).get("slcore"),
        "config_criteria": manifest.get("config", {}).get("criteria", []),
        "measured": measured,
        "criteria": criteria,
        "status": overall(criteria),
        "source": SOURCE,
    }


def summarize_bench_report(path: Path, runs: Path) -> dict[str, Any]:
    try:
        stats = json.loads(path.read_text(encoding="utf-8"))
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except (OSError, json.JSONDecodeError) as exc:
        raise SummaryError(f"cannot read {path}: {exc}") from exc
    measured, criteria = summarize_bench({}, stats)
    return {
        "gate": "bench",
        "run_id": path.relative_to(runs).as_posix(),
        "date": stamp.isoformat().replace("+00:00", "Z"),
        "date_source": "file modification time; a bench report has no manifest",
        "kind": "bench",
        "artifact": path.relative_to(runs).as_posix(),
        "artifact_sha256": files_hash([path]),
        "config_criteria": [stats.get("criterion")],
        "measured": measured,
        "criteria": criteria,
        "status": overall(criteria),
        "source": SOURCE,
    }


def overall(criteria: dict[str, Any]) -> str:
    statuses = [c["status"] for c in criteria.values()]
    if not statuses:
        return MEASUREMENT
    for word in (FAIL, SHORT, PASS):
        if word in statuses:
            return word
    return MEASUREMENT


def summaries(runs: Path) -> dict[str, dict[str, Any]]:
    """The summary of each gate kind, keyed by the kind."""
    out = {kind: summarize_artifact(path, runs) for kind, path in newest_artifacts(runs).items()}
    reports = bench_reports(runs)
    if reports:
        newest = max(reports, key=lambda p: (p.stat().st_mtime, p.as_posix()))
        out["bench"] = summarize_bench_report(newest, runs)
    return out


def write(out_dir: Path, docs: dict[str, dict[str, Any]]) -> list[Path]:
    written = []
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        for kind in sorted(docs):
            path = out_dir / f"{kind}.json"
            path.write_text(json.dumps(docs[kind], indent=1) + "\n", encoding="utf-8")
            written.append(path)
    except OSError as exc:
        raise SummaryError(f"cannot write in {out_dir}: {exc}") from exc
    return written


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize the newest run artifact of each gate kind into gates/.")
    parser.add_argument("--runs", default=str(ROOT / "runs"), help="the run tree to read (read only)")
    parser.add_argument("--out", default=str(ROOT / "gates"), help="the directory for the summaries")
    args = parser.parse_args(argv)
    runs = Path(args.runs)
    if not runs.is_dir():
        print(f"ERROR there is no run tree at {runs}", file=sys.stderr)
        return 2
    try:
        docs = summaries(runs)
        paths = write(Path(args.out), docs)
    except SummaryError as exc:
        print(f"ERROR {exc}", file=sys.stderr)
        return 1
    for path in paths:
        doc = docs[path.stem]
        states = ", ".join(f"{name} {c['status']}" for name, c in doc["criteria"].items())
        print(f"{path.name}: {doc['run_id']}: {states}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
