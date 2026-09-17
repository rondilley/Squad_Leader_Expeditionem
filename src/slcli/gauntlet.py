"""The evaluation gauntlet: rank an agent against a fixed field across scenarios.

The tournament command (FR-58) answers one pair on one scenario. The strong-AI work needs a
different question: where does a new agent land on a ladder of opponents, across several
scenarios, with the sides balanced and a confidence interval on each result. Before this
command the only strength number in the tree was "v4 beats v1 at 66.7 percent on scenario 1",
which is one opponent and one scenario. You cannot steer an improvement with that.

The gauntlet plays a round-robin among the field (the candidate and the panel) on each
scenario, feeds every game into one shared Elo pool, and prints a leaderboard. So the field
self-calibrates and the candidate slots into a real rank, not a single win rate against one
opponent. The Elo table settles over the whole result list (`slruns.elo.settled_ratings`),
because one pass of the update rule ranks by the order of play: the first run of this
command put the agent with the best win rate fourth, because its pair played first. Each cell also keeps a Wilson interval, so the leaderboard shows when two agents are
too close to separate at the game count that ran.

Balance: each pair alternates sides, so a scenario that favors one side does not bias the
result. The seed is deterministic in the field order and the scenario order, so a re-run of
the same gauntlet reproduces every game (TR-02).

`--anchor-only` skips the panel-against-panel games and plays the candidate against each panel
member only. That is the fast loop for "is my new agent better than the field"; the default
full round-robin is the honest ladder for a periodic ranking.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from slcli.play import build_engine_with_record, make_agent, play_game
from slruns import artifact
from slruns.elo import Record, settled_ratings
from slruns.index import connect, upsert

# The default field. Random anchors the bottom, v0 and v1 are the early ladder, v4 is the
# current best scripted agent. A caller names a different panel with --panel.
DEFAULT_PANEL = ("random", "v0", "v1", "v4")
DEFAULT_SCENARIOS = ("s01_guards_counterattack",)


def _apply(record: Record, outcome: float) -> None:
    """outcome is 1.0 for a win, 0.5 for a draw, 0.0 for a loss."""
    if outcome == 1.0:
        record.wins += 1
    elif outcome == 0.0:
        record.losses += 1
    else:
        record.draws += 1


def _field(candidate: str, panel: list[str]) -> list[str]:
    field: list[str] = []
    for name in [candidate, *panel]:
        if name and name not in field:
            field.append(name)
    return field


def run_gauntlet(
    candidate: str,
    panel: list[str],
    scenarios: list[str],
    games: int,
    seed: int,
    anchor_only: bool = False,
    balance: bool = True,
) -> artifact.RunArtifact:
    """Play the gauntlet and return the run artifact with the leaderboard in its stats."""
    field = _field(candidate, panel)
    if len(field) < 2:
        raise ValueError("the gauntlet needs the candidate and one panel agent or more")

    results: list[tuple[str, str, float]] = []
    overall: dict[str, Record] = {name: Record() for name in field}
    per_scenario: dict[str, dict[str, Record]] = {name: {} for name in field}

    art = artifact.RunArtifact(
        kind="gauntlet",
        slug=f"gauntlet-{candidate}",
        config={
            "candidate": candidate,
            "panel": list(panel),
            "field": field,
            "scenarios": list(scenarios),
            "games_per_pair": games,
            "first_seed": seed,
            "anchor_only": anchor_only,
            "balance_sides": balance,
        },
    )

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    counter = 0
    started = time.perf_counter()

    for scenario in scenarios:
        engine, _board_record = build_engine_with_record(scenario, None)
        sides = engine.scenario.players()
        for i, first in enumerate(field):
            for second in field[i + 1 :]:
                if anchor_only and candidate not in (first, second):
                    continue
                wins = {first: 0, second: 0, "draw": 0}
                failed = 0
                for g in range(games):
                    game_seed = seed + counter
                    counter += 1
                    swap = balance and g % 2 == 1
                    order = (second, first) if swap else (first, second)
                    agents = (
                        make_agent(order[0], engine, game_seed, 0),
                        make_agent(order[1], engine, game_seed, 1),
                    )
                    try:
                        record = play_game(engine, game_seed, agents)
                    except Exception as exc:
                        # A game that does not reach a victory condition (an agent that
                        # cycles a phase without advancing the turn) must not abort the whole
                        # gauntlet. Record it and go on, the way the gate command does (TC-04).
                        failed += 1
                        errors.append(
                            {
                                "scenario": scenario,
                                "seed": game_seed,
                                "agent_a": order[0],
                                "agent_b": order[1],
                                "error": type(exc).__name__,
                                "message": str(exc)[:300],
                            }
                        )
                        continue
                    art.seeds.append(game_seed)
                    winner = record.result
                    if winner == sides[0]:
                        outcome_first_in_order = 1.0
                    elif winner == sides[1]:
                        outcome_first_in_order = 0.0
                    else:
                        outcome_first_in_order = 0.5
                    # order[0] plays side sides[0]. Map the outcome back to `first`.
                    outcome_first = outcome_first_in_order if order[0] == first else 1.0 - outcome_first_in_order
                    _apply(overall[first], outcome_first)
                    _apply(overall[second], 1.0 - outcome_first if outcome_first != 0.5 else 0.5)
                    _apply(per_scenario[first].setdefault(scenario, Record()), outcome_first)
                    _apply(
                        per_scenario[second].setdefault(scenario, Record()),
                        1.0 - outcome_first if outcome_first != 0.5 else 0.5,
                    )
                    results.append((first, second, outcome_first))
                    if outcome_first == 1.0:
                        wins[first] += 1
                    elif outcome_first == 0.0:
                        wins[second] += 1
                    else:
                        wins["draw"] += 1
                rows.append(
                    {
                        "scenario": scenario,
                        "agent_a": first,
                        "agent_b": second,
                        "a_wins": wins[first],
                        "b_wins": wins[second],
                        "draws": wins["draw"],
                        "games": games,
                        "completed": games - failed,
                        "errors": failed,
                    }
                )

    # The ratings come from the whole result list, so the order of the pairs does not set
    # the rank (see settled_ratings).
    elo = settled_ratings(results)
    leaderboard = [
        {
            "agent": name,
            "elo": elo.to_dict().get(name, {}).get("rating", 1500.0),
            **overall[name].to_dict(),
        }
        for name in field
    ]
    leaderboard.sort(key=lambda r: r["elo"], reverse=True)

    art.stats = {
        "games": counter,
        "completed": counter - len(errors),
        "errors": errors,
        "seconds": round(time.perf_counter() - started, 1),
        "leaderboard": leaderboard,
        "elo": elo.to_dict(),
        "pairs": rows,
        "per_scenario": {
            name: {sc: rec.to_dict() for sc, rec in by_sc.items()} for name, by_sc in per_scenario.items()
        },
    }
    art.versions = {"candidate": candidate, "panel": ",".join(panel)}
    return art


def _print_leaderboard(art: artifact.RunArtifact, candidate: str) -> None:
    board = art.stats["leaderboard"]
    print()
    print(f"{'rank':>4s}  {'agent':16s} {'elo':>6s} {'games':>6s} {'win rate':>9s} {'95 percent interval':>22s}")
    for rank, row in enumerate(board, start=1):
        mark = " *" if row["agent"] == candidate else "  "
        low = row["confidence_low"] * 100
        high = row["confidence_high"] * 100
        print(
            f"{rank:4d}{mark}{row['agent']:16s} {row['elo']:6.0f} {row['games']:6d} "
            f"{row['win_rate'] * 100:8.1f}% {low:9.1f} to {high:6.1f}"
        )
    print()
    print("per scenario, candidate win rate:")
    for scenario, rec in art.stats["per_scenario"].get(candidate, {}).items():
        low = rec["confidence_low"] * 100
        high = rec["confidence_high"] * 100
        print(f"  {scenario:34s} {rec['win_rate'] * 100:6.1f}%  ({low:.1f} to {high:.1f})")
    failed = art.stats.get("errors", [])
    if failed:
        # A game that did not finish is not in the win rates. Say so, so the number is honest
        # about what it covers, and name the first pair that failed.
        first = failed[0]
        print()
        print(
            f"WARNING {len(failed)} of {art.stats['games']} games did not finish and are not "
            f"in the rates. First: {first['agent_a']} against {first['agent_b']} "
            f"on {first['scenario']} ({first['error']})."
        )


def run(args: Any) -> int:
    panel = [name for name in str(args.panel).split(",") if name]
    scenarios = [name for name in str(args.scenarios).split(",") if name]
    art = run_gauntlet(
        args.candidate,
        panel,
        scenarios,
        args.games,
        args.seed,
        anchor_only=args.anchor_only,
        balance=not args.no_balance,
    )
    directory = art.write(args.runs)
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        upsert(conn, directory)
    finally:
        conn.close()
    print(f"run {art.id} in {directory}")
    _print_leaderboard(art, args.candidate)
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser(
        "gauntlet",
        help="rank an agent against a fixed panel across scenarios, with Elo and confidence intervals",
    )
    p.add_argument("--candidate", required=True, help="the agent to rank, as v5 or learned:<snapshot>")
    p.add_argument(
        "--panel",
        default=",".join(DEFAULT_PANEL),
        help="a comma list of opponent agents (default: %(default)s)",
    )
    p.add_argument(
        "--scenarios",
        default=",".join(DEFAULT_SCENARIOS),
        help="a comma list of scenario ids (default: %(default)s)",
    )
    p.add_argument("--games", type=int, default=20, help="games for each pair on each scenario")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument(
        "--anchor-only",
        action="store_true",
        help="play the candidate against each panel agent only, not the full round-robin",
    )
    p.add_argument("--no-balance", action="store_true", help="keep each agent on one side")
    p.add_argument("--runs", default="runs", help="the run directory")
    p.set_defaults(func=run)
