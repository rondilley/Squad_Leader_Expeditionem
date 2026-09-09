"""The v0.1 gate command: play N games, verify the replay, and write one run artifact.

One run answers TC-04 (games play to the end with no unhandled error), TC-05 (a replay
gives the same hash sequence), TC-10 (the median game time), and TC-38 (a replay after
a shuffle of the legal list). The artifact is the evidence the gate asks for.
"""

from __future__ import annotations

import random
import statistics
import time
from pathlib import Path
from typing import Any

from slcore.frame import DecisionFrame
from slcli.play import build_engine_with_record, make_agent, play_game
from slruns import artifact
from slruns.index import connect, upsert


def shuffled(frame: DecisionFrame, rng: random.Random) -> DecisionFrame:
    commands = list(frame.commands)
    rng.shuffle(commands)
    return DecisionFrame(frame.frame_id, frame.player, frame.phase, frame.sub_step, frame.turn, tuple(commands))


def replay_with_shuffle(engine, record) -> bool:
    """TC-38: the command ID finds the command whatever the sequence of the legal list."""
    rng = random.Random(record.seed)
    state = engine.new_game(record.seed)
    for logged in record.commands:
        frame = shuffled(engine.legal_commands(state), rng)
        legal = frame.by_id(logged["command_id"])
        if legal is None or legal.payload != logged["payload"]:
            return False
        state, _ = engine.apply(state, legal.command)
        if engine.hash_state(state) != logged["hash"]:
            return False
    return True


def run_gate(scenario: str, board: str | None, agent_a: str, agent_b: str, games: int, seed: int, shuffle_games: int) -> artifact.RunArtifact:
    engine, board_record = build_engine_with_record(scenario, board)
    art = artifact.RunArtifact(
        kind="gate",
        slug=f"v01-{scenario}",
        config={
            "scenario": scenario,
            **board_record,
            "agent_a": agent_a,
            "agent_b": agent_b,
            "games": games,
            "first_seed": seed,
            "shuffle_games": shuffle_games,
            "criteria": ["TC-04", "TC-05", "TC-10", "TC-38"],
        },
    )
    errors: list[dict[str, Any]] = []
    replay_mismatches: list[int] = []
    shuffle_mismatches: list[int] = []
    durations: list[float] = []
    results: list[dict[str, Any]] = []
    rules: set[str] = set()
    sides = engine.scenario.players()
    for i in range(games):
        game_seed = seed + i
        agents = (make_agent(agent_a, engine, game_seed, 0), make_agent(agent_b, engine, game_seed, 1))
        started = time.perf_counter()
        try:
            record = play_game(engine, game_seed, agents)
        except Exception as exc:  # the gate records every unhandled error (TC-04)
            errors.append({"seed": game_seed, "error": type(exc).__name__, "message": str(exc)[:400]})
            continue
        durations.append(time.perf_counter() - started)
        art.seeds.append(game_seed)
        for event in record.events:
            rules.add(event["rule_id"])
        if engine.replay(game_seed, [c["payload"] for c in record.commands]) != record.hashes:
            replay_mismatches.append(game_seed)
        if i < shuffle_games and not replay_with_shuffle(engine, record):
            shuffle_mismatches.append(game_seed)
        results.append(
            {
                "seed": game_seed,
                "agent_a": agent_a,
                "agent_b": agent_b,
                "side_a": sides[0],
                "result": record.result,
                "turns": record.turns_played,
                "commands": len(record.commands),
            }
        )
        if i == 0:
            art.commands = [{"game": 0, **c} for c in record.commands]
            art.events = [{"game": 0, **e} for e in record.events]
    art.stats = {
        "games": games,
        "unhandled_errors": errors,
        "replay_mismatches": replay_mismatches,
        "shuffle_mismatches": shuffle_mismatches,
        "median_seconds": round(statistics.median(durations), 3) if durations else None,
        "max_seconds": round(max(durations), 3) if durations else None,
        "rule_ids_applied": sorted(rules),
        "results": results,
        "passed": {
            "TC-04": not errors and not replay_mismatches,
            "TC-05": not replay_mismatches,
            "TC-10": bool(durations) and statistics.median(durations) < 15.0,
            "TC-38": not shuffle_mismatches,
        },
    }
    art.versions = {"agent_a": agent_a, "agent_b": agent_b}
    return art


def run(args: Any) -> int:
    art = run_gate(args.scenario, args.board, args.agent_a, args.agent_b, args.games, args.seed, args.shuffle_games)
    directory = art.write(args.runs)
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        upsert(conn, directory)
    finally:
        conn.close()
    stats = art.stats
    print(f"run {art.id} in {directory}")
    print(f"games {stats['games']}, unhandled errors {len(stats['unhandled_errors'])}, replay mismatches {len(stats['replay_mismatches'])}, shuffle mismatches {len(stats['shuffle_mismatches'])}")
    print(f"median game {stats['median_seconds']} s, longest {stats['max_seconds']} s")
    for name, ok in stats["passed"].items():
        print(f"{name}: {'satisfied' if ok else 'NOT SATISFIED'}")
    return 0 if all(stats["passed"].values()) else 1


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("gate", help="play N games, verify the replay, and write the v0.1 gate artifact")
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--board", default=None)
    p.add_argument("--agent-a", default="v1", choices=("random", "v0", "v1", "v2", "v3"))
    p.add_argument("--agent-b", default="v1", choices=("random", "v0", "v1", "v2", "v3"))
    p.add_argument("--games", type=int, default=100)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--shuffle-games", type=int, default=10, help="how many games also replay with a shuffled legal list")
    p.add_argument("--runs", default="runs")
    p.set_defaults(func=run)
