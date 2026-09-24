"""The throughput test (NFR-01, TR-04, TC-09).

One environment step is: one `legal_commands` call, one agent choice, one `apply`, and
one `hash_state`. Random legal games run from new seeds in W worker processes for a
fixed time, and the numbers go to a stats file with the hardware manifest.

The runner writes the stats file after each worker count, so a long run leaves its
numbers on disk even when a later phase does not finish. The exit code says whether the
measurement ran, and the `passed` field of the artifact says whether it met NFR-01.
"""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import platform
import queue as queue_module
import sys
import time
from pathlib import Path
from typing import Any

from slagents.base import RandomAgent
from slcli.play import build_engine
from sldata.loaders import DataError

JOIN_GRACE_SECONDS = 120.0


def hardware_manifest() -> dict[str, Any]:
    return {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python": sys.version.split()[0],
        "implementation": platform.python_implementation(),
    }


def worker(scenario: str, board: str | None, seed_start: int, seconds: float, out: Any) -> None:
    """One worker: play random legal games until the deadline and report its counts."""
    try:
        engine = build_engine(scenario, board)
        steps = 0
        games = 0
        seed = seed_start
        deadline = time.perf_counter() + seconds
        while time.perf_counter() < deadline:
            agents = (RandomAgent(seed, 0), RandomAgent(seed, 1))
            state = engine.new_game(seed)
            while not state.game_over and time.perf_counter() < deadline:
                frame = engine.legal_commands(state)
                chosen = agents[state.active].select(state, frame)
                legal = frame.by_id(chosen)
                if legal is None:
                    raise RuntimeError("the random agent gave an ID that is not in the frame")
                state, _ = engine.apply(state, legal.command, frame)
                engine.hash_state(state)
                steps += 1
            if state.game_over:
                games += 1
            seed += 1
        out.put({"steps": steps, "games": games, "seed_start": seed_start, "seconds": seconds})
    except Exception as exc:  # a worker reports its failure instead of a silent exit
        out.put({"error": f"{type(exc).__name__}: {exc}", "seed_start": seed_start})


def run_bench(scenario: str, board: str | None, workers: int, seconds: float) -> dict[str, Any]:
    from slcli.worker_limit import limit_workers

    workers = limit_workers(workers)
    ctx = mp.get_context("spawn")
    results_queue: Any = ctx.Queue()
    procs = []
    started = time.perf_counter()
    for w in range(workers):
        p = ctx.Process(target=worker, args=(scenario, board, 1000 * (w + 1), seconds, results_queue))
        p.start()
        procs.append(p)
    results: list[dict[str, Any]] = []
    deadline = started + seconds + JOIN_GRACE_SECONDS
    while len(results) < workers and time.perf_counter() < deadline:
        try:
            results.append(results_queue.get(timeout=5.0))
        except queue_module.Empty:
            if all(p.exitcode is not None for p in procs):
                break
    for p in procs:
        p.join(timeout=30)
        if p.is_alive():
            p.terminate()
            p.join(timeout=10)
    failures = [r["error"] for r in results if "error" in r]
    missing = workers - len(results)
    elapsed = time.perf_counter() - started
    good = [r for r in results if "error" not in r]
    steps = sum(r["steps"] for r in good)
    return {
        "workers": workers,
        "seconds": seconds,
        "elapsed_seconds": round(elapsed, 1),
        "steps": steps,
        "games": sum(r["games"] for r in good),
        "steps_per_second": steps / seconds if seconds > 0 else 0.0,
        "workers_reporting": len(good),
        "worker_failures": failures,
        "workers_missing": missing,
        "per_worker": good,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, indent=1), encoding="utf-8")
    except OSError as exc:
        raise DataError(f"cannot write {path}: {exc}") from exc


def run(args: Any) -> int:
    worker_counts = [int(x) for x in str(args.workers).split(",")]
    seconds = args.minutes * 60.0 if args.minutes else args.seconds
    report: dict[str, Any] = {
        "benchmark": "NFR-01 environment steps per second",
        "criterion": "TC-09",
        "scenario": args.scenario,
        "board": args.board,
        "threshold_steps_per_second": 3500,
        "hardware": hardware_manifest(),
        "runs": [],
    }
    path = Path(args.out) if args.out else None
    failed = False
    for w in worker_counts:
        result = run_bench(args.scenario, args.board, w, seconds)
        report["runs"].append(result)
        note = ""
        if result["worker_failures"] or result["workers_missing"]:
            note = f" WARNING {result['workers_missing']} workers gave no result, {len(result['worker_failures'])} failed"
            failed = True
        print(f"workers {w}: {result['steps']} steps in {seconds:.0f} s = {result['steps_per_second']:.0f} steps/s ({result['games']} games){note}", flush=True)
        if path is not None:
            write_report(path, report)
    best = max((r["steps_per_second"] for r in report["runs"]), default=0.0)
    report["best_steps_per_second"] = round(best, 1)
    report["measurement_complete"] = not failed
    report["passed"] = best >= report["threshold_steps_per_second"] and not failed
    if path is not None:
        write_report(path, report)
        print(f"wrote {path}", flush=True)
    print(f"best {best:.0f} steps/s against the threshold of 3,500: {'satisfied' if report['passed'] else 'NOT SATISFIED'}", flush=True)
    return 0 if report["passed"] else 1


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("bench", help="measure environment steps per second")
    p.add_argument("--scenario", default="s00_movement_drill")
    p.add_argument("--board", default=None)
    from slcli.worker_limit import worker_list_argument

    p.add_argument("--workers", type=worker_list_argument, default="1")
    p.add_argument("--minutes", type=float, default=0.0)
    p.add_argument("--seconds", type=float, default=10.0)
    p.add_argument("--out", default=None, help="stats file path")
    p.set_defaults(func=run)
