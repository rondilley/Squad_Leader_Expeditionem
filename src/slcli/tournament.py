"""The tournament command (FR-58): N games between two agents with the sides balanced.

With the sides balanced, the two games of each side order share one seed (a paired
design, L7), so the same dice decide the game with each agent on each side. The seeds are
in the tournament range of `slruns.seeds`, so a tournament does not replay the seeds of a
training run, a gauntlet, or an evolution. A rate of 20 games has a 95 percent interval
about 40 points wide; a baseline needs 200 games or more, and each rate prints with its
Wilson interval.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from slcli.play import build_engine_with_record, make_agent, play_game, trace_writer
from slruns import artifact
from slruns.elo import EloTable, Record, settled_ratings_by_side
from slruns.seeds import MINIMUM_BASELINE_GAMES, family_seed, rate_text, sample_warning
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
    factory: Any = make_agent,
) -> artifact.RunArtifact:
    """Play `games` games. With balance on, the agents change sides on each odd game.

    `factory` builds an agent from its name, the engine, the seed, and the player, the
    way `make_agent` does. A test gives one that builds a model agent on a provider of
    its own, so the record of the harness is tested with no network.
    """
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
            "first_game_seed": family_seed("tournament", seed),
            "paired_seeds": balance,
            "balance_sides": balance,
        },
    )
    sides = engine.scenario.players()
    records = {agent_a: Record(), agent_b: Record()}
    elo = EloTable()
    rows: list[dict[str, Any]] = []
    # The four rates of TC-16 and the decision time of FR-59, from each model agent of
    # each game, so a run of the prompted family carries its own measurement (OR-02).
    harness: list[dict[str, Any]] = []
    started = time.perf_counter()
    sided: list[tuple[str, str, float, str]] = []
    for i in range(games):
        game_seed = family_seed("tournament", seed, i // 2 if balance else i)
        swap = balance and i % 2 == 1
        kind_for_player = (agent_b, agent_a) if swap else (agent_a, agent_b)
        agents = (factory(kind_for_player[0], engine, game_seed, 0), factory(kind_for_player[1], engine, game_seed, 1))
        writer = trace_writer(engine, game_seed, agents) if traces_root else None
        record = play_game(engine, game_seed, agents, traces=writer)
        if writer is not None:
            # Two games of a pair share a seed, so the file name holds the game index too.
            writer.write(traces_root, f"traces_{game_seed}_{i}.json")
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
        first_score = 1.0 if winner_side == sides[0] else (0.0 if winner_side == sides[1] else 0.5)
        sided.append((kind_for_player[0], kind_for_player[1], first_score, scenario))
        for player, agent in enumerate(agents):
            counters = getattr(agent, "counters", None)
            if counters is not None and hasattr(counters, "to_dict"):
                harness.append({"game": i, "seed": game_seed, "agent": kind_for_player[player], "side": sides[player], **counters.to_dict()})
    art.stats = {
        "games": games,
        "seconds": round(time.perf_counter() - started, 1),
        "agents": {name: rec.to_dict() for name, rec in records.items()},
        "elo": elo.to_dict(),
        # The Elo points the first side gets from its side alone, from the fit with the
        # side term (L7). It needs two distinct agents.
        "side_advantage": settled_ratings_by_side(sided).to_dict() if agent_a != agent_b else {},
        "results": rows,
        "sides": list(sides),
    }
    if harness:
        art.stats["harness"] = harness
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
        score = rec["wins"] + 0.5 * rec["draws"]
        print(f"{name}: {rec['wins']} wins, {rec['losses']} losses, {rec['draws']} draws, {rate_text(score, rec['games'])}")
    for name, entry in art.stats["elo"].items():
        print(f"elo {name}: {entry['rating']} after {entry['games']} games")
    for group, value in art.stats.get("side_advantage", {}).items():
        print(f"side term of {group}: {value:+.1f} Elo points for {art.stats['sides'][0]}")
    warning = sample_warning(art.stats["games"])
    if warning:
        print(warning)
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("tournament", help="play N games between two agents and write a run artifact")
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--board", default=None)
    p.add_argument("--agent-a", default="v1", help="an agent name: random, v0, v1, v2, v3, model:<providers>, or learned:<snapshot>")
    p.add_argument("--agent-b", default="v0", help="an agent name: random, v0, v1, v2, v3, model:<providers>, or learned:<snapshot>")
    p.add_argument(
        "--games",
        type=int,
        default=10,
        help=f"games of the pair, two for each seed when the sides are balanced; a baseline needs {MINIMUM_BASELINE_GAMES} or more",
    )
    p.add_argument("--seed", type=int, default=1, help="the first seed, inside the tournament range of seeds (slruns.seeds)")
    p.add_argument("--no-balance", action="store_true", help="keep each agent on one side")
    p.add_argument("--runs", default="runs", help="the run directory")
    p.add_argument("--traces", default=None, help="directory for the trace records of each game (FR-60)")
    p.add_argument(
        "--families",
        default=None,
        help="a list of agent names, as v1,v2,model:openai. One table for each pair (FR-63, TC-35).",
    )
    p.set_defaults(func=run)
