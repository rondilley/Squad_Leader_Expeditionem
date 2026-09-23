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

`--workers N` plays the games in N processes. The list of games (the scenario, the seed, and
the two agents of each) is fixed before the first game, and the results come back in that
order, so a run with workers gives the same artifact as a run without them (TR-02). Each
pair row also counts the wins of each agent on each side, because a scenario that one side
wins from set up hides an agent that cannot attack behind an agent that can defend.
"""

from __future__ import annotations

import sys
import time
from multiprocessing import Pool, Value
from pathlib import Path
from typing import Any

from slcli.play import build_engine, build_engine_with_record, make_agent, play_game
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


# One engine for each scenario in each worker process, because a board takes time to build.
_ENGINES: dict[str, Any] = {}


def _play_job(job: tuple[str, int, str, str]) -> dict[str, Any]:
    """One game in a worker: the winner side name, or the error that stopped it."""
    scenario, game_seed, first, second = job
    engine = _ENGINES.get(scenario)
    if engine is None:
        engine = build_engine(scenario, None)
        _ENGINES[scenario] = engine
    agents = (make_agent(first, engine, game_seed, 0), make_agent(second, engine, game_seed, 1))
    try:
        record = play_game(engine, game_seed, agents)
    except Exception as exc:
        # A game that does not reach a victory condition (an agent that cycles a phase
        # without advancing the turn) must not abort the whole gauntlet. Record it and go
        # on, the way the gate command does (TC-04).
        return {"winner": None, "error": type(exc).__name__, "message": str(exc)[:300]}
    # The four rates of TC-16 and the decision time of FR-59 of each model agent (OR-02).
    harness = []
    for player, agent in enumerate(agents):
        counters = getattr(agent, "counters", None)
        if counters is not None and hasattr(counters, "to_dict"):
            harness.append({"player": player, "agent": (first, second)[player], **counters.to_dict()})
    return {"winner": record.result, "error": None, "harness": harness}


def _bind_worker(counter: Any) -> None:
    """Each worker takes the next index and binds itself to that host of a model pool.

    A worker bound to one host takes each game it gets to that host, and the pool hands
    a game to the next free worker. So a fast host plays more games than a slow one,
    which is the load sharing a mixed set of servers needs.
    """
    from slagents.prompted.providers import set_pool_offset

    with counter.get_lock():
        index = counter.value
        counter.value += 1
    set_pool_offset(index)


def _progress(done: int, total: int, job: tuple[str, int, str, str], outcome: dict[str, Any], started: float) -> None:
    """One line on the error stream for each game that ends, so a long gauntlet of a
    model agent shows how far it is. The table on the output stream stays as it was."""
    scenario, game_seed, first, second = job
    result = outcome["error"] or outcome["winner"] or "draw"
    minutes = (time.perf_counter() - started) / 60.0
    print(f"game {done} of {total}: {first} vs {second} seed {game_seed} -> {result} ({minutes:.1f} min)", file=sys.stderr, flush=True)


def _play_all(jobs: list[tuple[str, int, str, str]], workers: int, progress: bool = False) -> list[dict[str, Any]]:
    """The results of the jobs, in the order of the jobs."""
    started = time.perf_counter()
    outcomes: list[dict[str, Any]] = []
    if workers <= 1 or len(jobs) < 2:
        for job in jobs:
            outcomes.append(_play_job(job))
            if progress:
                _progress(len(outcomes), len(jobs), job, outcomes[-1], started)
        return outcomes
    counter = Value("i", 0)
    with Pool(processes=min(workers, len(jobs)), initializer=_bind_worker, initargs=(counter,)) as pool:
        for job, outcome in zip(jobs, pool.imap(_play_job, jobs, chunksize=1)):
            outcomes.append(outcome)
            if progress:
                _progress(len(outcomes), len(jobs), job, outcome, started)
    return outcomes


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
    workers: int = 1,
    progress: bool = False,
) -> artifact.RunArtifact:
    """Play the gauntlet and return the run artifact with the leaderboard in its stats.

    With `progress` each game that ends prints one line on the error stream.
    """
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
            "workers": workers,
        },
    )

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    harness_rows: list[dict[str, Any]] = []
    counter = 0
    started = time.perf_counter()

    # The list of games is fixed first, so the workers change nothing but the clock.
    jobs: list[tuple[str, int, str, str]] = []
    pairs: list[tuple[str, str, str, list[tuple[int, tuple[str, str]]]]] = []
    sides_of: dict[str, tuple[str, ...]] = {}
    for scenario in scenarios:
        engine, _board_record = build_engine_with_record(scenario, None)
        sides_of[scenario] = tuple(engine.scenario.players())
        for i, first in enumerate(field):
            for second in field[i + 1 :]:
                if anchor_only and candidate not in (first, second):
                    continue
                pair_jobs: list[tuple[int, tuple[str, str]]] = []
                for g in range(games):
                    game_seed = seed + counter
                    counter += 1
                    swap = balance and g % 2 == 1
                    order = (second, first) if swap else (first, second)
                    pair_jobs.append((len(jobs), order))
                    jobs.append((scenario, game_seed, order[0], order[1]))
                pairs.append((scenario, first, second, pair_jobs))
    outcomes = _play_all(jobs, workers, progress=progress)

    for scenario, first, second, pair_jobs in pairs:
        sides = sides_of[scenario]
        wins = {first: 0, second: 0, "draw": 0}
        # The wins of each agent as each side, so the row says who can attack and who can
        # only defend.
        by_side = {first: [0, 0], second: [0, 0]}
        failed = 0
        for index, order in pair_jobs:
            game_seed = jobs[index][1]
            outcome = outcomes[index]
            if outcome["error"] is not None:
                failed += 1
                errors.append(
                    {
                        "scenario": scenario,
                        "seed": game_seed,
                        "agent_a": order[0],
                        "agent_b": order[1],
                        "error": outcome["error"],
                        "message": outcome["message"],
                    }
                )
                continue
            art.seeds.append(game_seed)
            for row in outcome.get("harness", []):
                harness_rows.append({"scenario": scenario, "seed": game_seed, "side": sides[row["player"]], **row})
            winner = outcome["winner"]
            if winner == sides[0]:
                outcome_first_in_order = 1.0
                by_side[order[0]][0] += 1
            elif winner == sides[1]:
                outcome_first_in_order = 0.0
                by_side[order[1]][1] += 1
            else:
                outcome_first_in_order = 0.5
            # order[0] plays side sides[0]. Map the outcome back to `first`.
            outcome_first = outcome_first_in_order if order[0] == first else 1.0 - outcome_first_in_order
            outcome_second = 1.0 - outcome_first if outcome_first != 0.5 else 0.5
            _apply(overall[first], outcome_first)
            _apply(overall[second], outcome_second)
            _apply(per_scenario[first].setdefault(scenario, Record()), outcome_first)
            _apply(per_scenario[second].setdefault(scenario, Record()), outcome_second)
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
                "a_wins_by_side": {sides[0]: by_side[first][0], sides[1]: by_side[first][1]},
                "b_wins_by_side": {sides[0]: by_side[second][0], sides[1]: by_side[second][1]},
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
    if harness_rows:
        art.stats["harness"] = harness_rows
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
    print()
    print("the candidate against each opponent, wins by side:")
    for row in art.stats["pairs"]:
        if candidate not in (row["agent_a"], row["agent_b"]):
            continue
        mine, other = ("a", "b") if row["agent_a"] == candidate else ("b", "a")
        by_side = row[f"{mine}_wins_by_side"]
        sides = ", ".join(f"{n} as {side}" for side, n in by_side.items())
        print(
            f"  {row['scenario']:30s} against {row[f'agent_{other}']:8s} "
            f"{row[f'{mine}_wins']:3d} of {row['completed']:3d}  ({sides})"
        )
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


def split_agent_names(text: str) -> list[str]:
    """The agent names of a comma list. A comma inside the brackets of a parameter set,
    as in `v7[loss_scale=8,fire_floor=4]`, belongs to the set and not to the list."""
    out: list[str] = []
    depth = 0
    current = ""
    for ch in text:
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth = max(0, depth - 1)
        if ch == "," and depth == 0:
            if current.strip():
                out.append(current.strip())
            current = ""
            continue
        current += ch
    if current.strip():
        out.append(current.strip())
    return out


def run(args: Any) -> int:
    panel = split_agent_names(str(args.panel))
    scenarios = [name for name in str(args.scenarios).split(",") if name]
    art = run_gauntlet(
        args.candidate,
        panel,
        scenarios,
        args.games,
        args.seed,
        anchor_only=args.anchor_only,
        balance=not args.no_balance,
        workers=args.workers,
        progress=bool(args.progress),
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
    p.add_argument("--workers", type=int, default=1, help="processes that play the games; the results do not change")
    p.add_argument("--progress", action="store_true", help="print one line on the error stream for each game that ends")
    p.set_defaults(func=run)
