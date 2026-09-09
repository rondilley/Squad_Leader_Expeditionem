"""The tournament command (FR-58): N games between two agents with the sides balanced."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from slcli.play import build_engine_with_record, make_agent, play_game, trace_writer
from slruns import artifact
from slruns.elo import EloTable, Record
from slruns.index import connect, upsert


def run_tournament(
    scenario: str,
    board: str | None,
    agent_a: str,
    agent_b: str,
    games: int,
    seed: int,
    balance: bool = True,
    traces_root: str | Path | None = None,
) -> artifact.RunArtifact:
    """Play `games` games. With balance on, the agents change sides on each odd game."""
    engine, board_record = build_engine_with_record(scenario, board)
    art = artifact.RunArtifact(
        kind="tournament",
        slug=f"{scenario}-{agent_a}-vs-{agent_b}",
        config={
            "scenario": scenario,
            **board_record,
            "agent_a": agent_a,
            "agent_b": agent_b,
            "games": games,
            "first_seed": seed,
            "balance_sides": balance,
        },
    )
    sides = engine.scenario.players()
    records = {agent_a: Record(), agent_b: Record()}
    elo = EloTable()
    rows: list[dict[str, Any]] = []
    started = time.perf_counter()
    for i in range(games):
        game_seed = seed + i
        swap = balance and i % 2 == 1
        kind_for_player = (agent_b, agent_a) if swap else (agent_a, agent_b)
        agents = (make_agent(kind_for_player[0], engine, game_seed, 0), make_agent(kind_for_player[1], engine, game_seed, 1))
        writer = trace_writer(engine, game_seed, agents) if traces_root else None
        record = play_game(engine, game_seed, agents, traces=writer)
        if writer is not None:
            writer.write(traces_root, f"traces_{game_seed}.json")
        art.seeds.append(game_seed)
        art.commands.extend({"game": i, **c} for c in record.commands)
        art.events.extend({"game": i, **e} for e in record.events)
        winner_side = record.result
        rows.append(
            {
                "seed": game_seed,
                "agent_a": kind_for_player[0],
                "agent_b": kind_for_player[1],
                "side_a": sides[0],
                "result": winner_side,
                "turns": record.turns_played,
                "commands": len(record.commands),
            }
        )
        _score(records, elo, kind_for_player, sides, winner_side)
    art.stats = {
        "games": games,
        "seconds": round(time.perf_counter() - started, 1),
        "agents": {name: rec.to_dict() for name, rec in records.items()},
        "elo": elo.to_dict(),
        "results": rows,
        "sides": list(sides),
    }
    art.versions = {"agent_a": agent_a, "agent_b": agent_b}
    return art


def _score(records: dict[str, Record], elo: EloTable, kinds: tuple[str, str], sides: tuple[str, str], winner_side: str) -> None:
    a, b = kinds
    if winner_side == sides[0]:
        records[a].wins += 1
        records[b].losses += 1
        elo.update(a, b, 1.0)
    elif winner_side == sides[1]:
        records[b].wins += 1
        records[a].losses += 1
        elo.update(a, b, 0.0)
    else:
        records[a].draws += 1
        records[b].draws += 1
        elo.update(a, b, 0.5)


def run_families(args: Any) -> int:
    """FR-63 and TC-35: one table for each pair of the families the owner named."""
    names = [name for name in str(args.families).split(",") if name]
    if len(names) < 2:
        print("ERROR --families needs two agent names or more, as v1,v2,model:openai")
        return 2
    rows: list[dict[str, Any]] = []
    for i, first in enumerate(names):
        for second in names[i + 1 :]:
            art = run_tournament(
                args.scenario, args.board, first, second, args.games, args.seed, not args.no_balance, args.traces
            )
            directory = art.write(args.runs)
            conn = connect(Path(args.runs) / "runs.sqlite")
            try:
                upsert(conn, directory)
            finally:
                conn.close()
            for name, record in art.stats["agents"].items():
                rows.append(
                    {
                        "pair": f"{first} against {second}",
                        "agent": name,
                        "games": record["games"],
                        "win_rate": record["win_rate"],
                        "confidence_low": record["confidence_low"],
                        "confidence_high": record["confidence_high"],
                        "run": art.id,
                    }
                )
            print(f"{first} against {second}: {art.id}")
    print()
    print(f"{'pair':34s} {'agent':16s} {'games':>6s} {'win rate':>9s} {'95 percent interval':>22s}")
    for row in rows:
        low = row["confidence_low"] * 100
        high = row["confidence_high"] * 100
        print(
            f"{row['pair']:34s} {row['agent']:16s} {row['games']:6d} {row['win_rate'] * 100:8.1f}% "
            f"{low:9.1f} to {high:6.1f}"
        )
    return 0


def run(args: Any) -> int:
    if args.families:
        return run_families(args)
    art = run_tournament(
        args.scenario,
        args.board,
        args.agent_a,
        args.agent_b,
        args.games,
        args.seed,
        not args.no_balance,
        args.traces,
    )
    directory = art.write(args.runs)
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        upsert(conn, directory)
    finally:
        conn.close()
    print(f"run {art.id} in {directory}")
    for name, rec in art.stats["agents"].items():
        low = rec["confidence_low"] * 100
        high = rec["confidence_high"] * 100
        print(f"{name}: {rec['wins']} wins, {rec['losses']} losses, {rec['draws']} draws, win rate {rec['win_rate'] * 100:.1f} percent, 95 percent interval {low:.1f} to {high:.1f}")
    for name, entry in art.stats["elo"].items():
        print(f"elo {name}: {entry['rating']} after {entry['games']} games")
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("tournament", help="play N games between two agents and write a run artifact")
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--board", default=None)
    p.add_argument("--agent-a", default="v1", help="an agent name: random, v0, v1, v2, or model:<providers>")
    p.add_argument("--agent-b", default="v0", help="an agent name: random, v0, v1, v2, or model:<providers>")
    p.add_argument("--games", type=int, default=10)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--no-balance", action="store_true", help="keep each agent on one side")
    p.add_argument("--runs", default="runs", help="the run directory")
    p.add_argument("--traces", default=None, help="directory for the trace records of each game (FR-60)")
    p.add_argument(
        "--families",
        default=None,
        help="a list of agent names, as v1,v2,model:openai. One table for each pair (FR-63, TC-35).",
    )
    p.set_defaults(func=run)
