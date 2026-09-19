"""The agents command: the scripted agent gate of TC-15 and FR-44.

TC-15 asks that each scripted agent complete 100 headless games in each of scenarios 1,
2, and 3A with zero unhandled errors. That is 900 games, and a game of scenario 3A is
about half a minute, so the run goes to worker processes in the same way as the
throughput benchmark.

`sl-cli agents --list` prints the agents with their names, their versions, and their
named parameters (FR-44). `sl-cli agents --games 100` runs the gate and writes a run
artifact with the result of each pair.
"""

from __future__ import annotations

import dataclasses
import json
import multiprocessing as mp
import queue as queue_module
import time
from pathlib import Path
from typing import Any

from slagents.scripted.v1 import Parameters as V1Parameters
from slagents.scripted.v2 import Parameters as V2Parameters
from slagents.scripted.v3 import Parameters as V3Parameters
from slagents.scripted.v4 import Parameters as V4Parameters
from slagents.scripted.v5 import Parameters as V5Parameters
from slagents.scripted.v6 import Parameters as V6Parameters
from slagents.scripted.v7 import Parameters as V7Parameters
from slcli.play import build_engine, make_agent, play_game
from slruns import artifact
from slruns.index import connect, upsert

AGENTS = ("v0", "v1", "v2", "v3", "v4", "v5", "v6", "v7")
SCENARIOS = ("s01_guards_counterattack", "s02_tractor_works", "s03a_streets_of_stalingrad", "s04_armor_probe")
JOIN_GRACE_SECONDS = 300.0
PARAMETERS = {"v0": None, "v1": V1Parameters, "v2": V2Parameters, "v3": V3Parameters, "v4": V4Parameters, "v5": V5Parameters, "v6": V6Parameters, "v7": V7Parameters}


def parameter_record() -> dict[str, Any]:
    """The named parameters of each agent, for the run artifact (FR-44)."""
    out: dict[str, Any] = {}
    for kind, record in PARAMETERS.items():
        if record is None:
            out[kind] = {}
            continue
        out[kind] = {f.name: getattr(record(), f.name) for f in dataclasses.fields(record)}
    return out


def worker(kind: str, scenario: str, first_seed: int, games: int, out: Any) -> None:
    """One pair of agent and scenario. The worker reports each error instead of stopping."""
    try:
        engine = build_engine(scenario)
        errors: list[dict[str, Any]] = []
        results: dict[str, int] = {}
        turns: list[int] = []
        commands = 0
        started = time.perf_counter()
        for step in range(games):
            seed = first_seed + step
            agents = (make_agent(kind, engine, seed, 0), make_agent(kind, engine, seed, 1))
            try:
                record = play_game(engine, seed, agents)
            except Exception as exc:  # TC-15 counts an unhandled error, it does not stop
                errors.append({"seed": seed, "error": type(exc).__name__, "message": str(exc)[:300]})
                continue
            results[record.result] = results.get(record.result, 0) + 1
            turns.append(record.turns_played)
            commands += len(record.commands)
        out.put(
            {
                "agent": kind,
                "scenario": scenario,
                "games": games,
                "played": sum(results.values()),
                "results": results,
                "commands": commands,
                "median_turns": sorted(turns)[len(turns) // 2] if turns else 0,
                "seconds": round(time.perf_counter() - started, 1),
                "errors": errors,
            }
        )
    except Exception as exc:
        out.put({"agent": kind, "scenario": scenario, "fatal": f"{type(exc).__name__}: {exc}"})


def run_gate(
    games: int, first_seed: int, workers: int, scenarios: tuple[str, ...] = SCENARIOS
) -> artifact.RunArtifact:
    """TC-15: each agent plays `games` games of each scenario."""
    pairs = [(kind, scenario) for kind in AGENTS for scenario in scenarios]
    art = artifact.RunArtifact(
        kind="agents",
        slug="tc15-scripted-agents",
        config={
            "scenario": ",".join(scenarios),
            "board": "generated",
            "agents": list(AGENTS),
            "games": games,
            "first_seed": first_seed,
            "workers": workers,
            "parameters": parameter_record(),
            "criteria": ["TC-15", "FR-44"],
        },
    )
    rows = run_pairs(pairs, games, first_seed, workers)
    errors = [e for row in rows for e in row.get("errors", [])]
    fatal = [row["fatal"] for row in rows if "fatal" in row]
    missing = [f"{k} on {s}" for k, s in pairs if not any(r.get("agent") == k and r.get("scenario") == s for r in rows)]
    art.seeds = list(range(first_seed, first_seed + games))
    art.stats = {
        "pairs": rows,
        "games_each": games,
        "unhandled_errors": errors,
        "fatal": fatal,
        "missing_pairs": missing,
        "passed": {"TC-15": not errors and not fatal and not missing},
    }
    return art


def run_pairs(pairs: list[tuple[str, str]], games: int, first_seed: int, workers: int) -> list[dict[str, Any]]:
    """Run the pairs over a pool of worker processes and gather what they report."""
    ctx = mp.get_context("spawn")
    results_queue: Any = ctx.Queue()
    rows: list[dict[str, Any]] = []
    waiting = list(pairs)
    running: list[Any] = []
    deadline = time.perf_counter() + JOIN_GRACE_SECONDS + games * len(pairs) * 60.0
    while (waiting or running) and time.perf_counter() < deadline:
        while waiting and len(running) < max(1, workers):
            kind, scenario = waiting.pop(0)
            p = ctx.Process(target=worker, args=(kind, scenario, first_seed, games, results_queue))
            p.start()
            running.append(p)
        try:
            rows.append(results_queue.get(timeout=5.0))
        except queue_module.Empty:
            pass
        running = [p for p in running if p.is_alive() or p.exitcode is None]
        if not running and not waiting:
            break
    while True:
        try:
            rows.append(results_queue.get_nowait())
        except queue_module.Empty:
            break
    for p in running:
        p.join(timeout=30)
        if p.is_alive():
            p.terminate()
            p.join(timeout=10)
    return rows


def print_list() -> int:
    for kind, values in sorted(parameter_record().items()):
        engine_free = ", ".join(f"{k}={v}" for k, v in sorted(values.items())) or "none"
        print(f"{kind}: parameters {engine_free}")
    return 0


def run(args: Any) -> int:
    if args.list:
        return print_list()
    art = run_gate(args.games, args.seed, args.workers)
    stats = art.stats
    for row in sorted(stats["pairs"], key=lambda r: (r.get("agent", ""), r.get("scenario", ""))):
        if "fatal" in row:
            print(f"{row['agent']} on {row['scenario']}: FATAL {row['fatal']}")
            continue
        print(
            f"{row['agent']} on {row['scenario']}: {row['played']} of {row['games']} games in {row['seconds']} s, "
            f"results {row['results']}, {len(row['errors'])} errors"
        )
    print(f"TC-15 {'holds' if stats['passed']['TC-15'] else 'fails'}")
    directory = art.write(args.runs)
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        upsert(conn, directory)
    finally:
        conn.close()
    print(f"run artifact {directory}")
    return 0 if stats["passed"]["TC-15"] else 1


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("agents", help="list the scripted agents or run the TC-15 gate")
    p.add_argument("--list", action="store_true", help="print each agent with its named parameters")
    p.add_argument("--games", type=int, default=100, help="games for each agent and scenario")
    p.add_argument("--seed", type=int, default=7000, help="the first seed")
    p.add_argument("--workers", type=int, default=9, help="how many pairs run at the same time")
    p.add_argument("--runs", default="runs")
    p.set_defaults(func=run)
