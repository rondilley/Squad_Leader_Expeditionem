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
result. The two games of each side order share one seed (a paired design, L7): the same
dice and the same board decide the game with the agents on each side, so the difference
of the pair is the agents and not the seed. The Bradley-Terry fit has a side term for each
scenario (`slruns.elo.settled_ratings_by_side`), and the artifact reports it as the Elo
points the first side of the scenario gets from its side alone. The seeds are in the
gauntlet range of `slruns.seeds`, so a gauntlet does not replay the games a training run or
an evolution chose its candidate on. The seed is deterministic in the field order and the
scenario order, so a re-run of the same gauntlet reproduces every game (TR-02).

Sample size: a pair of 20 games gives a 95 percent interval about 40 points wide. A
baseline needs 200 games or more (`slruns.seeds.MINIMUM_BASELINE_GAMES`), and each rate
prints with its Wilson interval.

`--anchor-only` skips the panel-against-panel games and plays the candidate against each panel
member only. That is the fast loop for "is my new agent better than the field"; the default
full round-robin is the honest ladder for a periodic ranking.

`--workers N` plays the games in N processes. The list of games (the scenario, the seed, and
the two agents of each) is fixed before the first game, and the results come back in that
order, so a run with workers gives the same artifact as a run without them (TR-02). Each
pair row also counts the wins of each agent on each side, because a scenario that one side
wins from set up hides an agent that cannot attack behind an agent that can defend.

The side baseline (2026-10-14): a scenario can be one sided. On s04 an equal pair gives the
Axis attacker about 6 percent of the games, so "the candidate won 0 attacks against v7" says
little alone. For each scenario, each panel agent, and each side, the artifact gives the wins
of the candidate on that side against that agent, the wins of the other panel agents on that
side against it (from the round-robin, so it costs no game), and with `--mirror` the wins of
that side when the agent plays itself. The mirror games use a seed each, because the two
games of a paired seed are the same game when one agent plays the two sides. They are not in
the Elo fit or the leaderboard. A draw is not a win in the baseline.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from multiprocessing import Value
from pathlib import Path
from typing import Any

from slcli.play import build_engine, build_engine_with_record, make_agent, play_game
from slruns import artifact
from slruns.elo import Record, settled_ratings_by_side
from slruns.seeds import MINIMUM_BASELINE_GAMES, family_seed, rate_text, sample_warning
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
    # A farm host gets a variant as its document (a dict), and the document is the key.
    key = scenario if isinstance(scenario, str) else json.dumps(scenario, sort_keys=True)
    engine = _ENGINES.get(key)
    if engine is None:
        engine = build_engine(scenario, None)
        _ENGINES[key] = engine
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


def _play_all(
    jobs: list[tuple[str, int, str, str]],
    workers: int,
    progress: bool = False,
    play: Any = None,
    farm: Any = None,
) -> list[dict[str, Any]]:
    """The results of the jobs, in the order of the jobs. `play` is the function of one
    game, `_play_job` unless a test gives one that ends its worker process.

    With `farm` (an `slfarm.client.Farm`) the hosts of the farm play the games too, next
    to `workers` local processes, and the list comes back in the same order (TR-02).
    """
    play = play or _play_job
    started = time.perf_counter()
    outcomes: list[dict[str, Any]] = []
    from slcli.worker_limit import limit_workers

    workers = limit_workers(workers)
    if farm is not None:
        from slfarm import client as farm_client

        def report(done: int, total: int, job: tuple[str, int, str, str], outcome: dict[str, Any]) -> None:
            _progress(done, total, job, outcome, started)

        return farm_client.play_all(jobs, farm.addresses, farm.key, local_workers=workers, play=play, progress=report if progress else None)
    if workers <= 1 or len(jobs) < 2:
        for job in jobs:
            outcomes.append(play(job))
            if progress:
                _progress(len(outcomes), len(jobs), job, outcomes[-1], started)
        return outcomes
    # A worker process that dies (a native fault, not a Python exception) loses its game.
    # `multiprocessing.Pool` then waits for that result for ever; the 2026-10-12 s04
    # gauntlet stood 40 minutes with all workers idle. The executor marks the pool broken,
    # and the games with no result play again in a new pool while each pass gives a new
    # result. A game is its seed, so the second play gives the same result. After a pass
    # with no new result, each game left plays in a pool of its own, so that a game that
    # ends its worker each time does not stop the others.
    results: dict[int, dict[str, Any]] = {}
    while True:
        waiting = [index for index in range(len(jobs)) if index not in results]
        if not waiting:
            break
        before = len(results)
        _pool_pass(jobs, waiting, min(workers, len(waiting)), results, play, progress, started)
        if len(results) == before:
            break
    for index in [index for index in range(len(jobs)) if index not in results]:
        _pool_pass(jobs, [index], 1, results, play, progress, started)
        if index not in results:
            results[index] = {"winner": None, "error": "BrokenProcessPool", "message": "the worker process died while it played this game"}
    return [results[index] for index in range(len(jobs))]


def _pool_pass(
    jobs: list[tuple[str, int, str, str]],
    indexes: list[int],
    workers: int,
    results: dict[int, dict[str, Any]],
    play: Any,
    progress: bool,
    started: float,
) -> None:
    """Play the jobs of `indexes` in one pool and put each result that comes back in `results`."""
    counter = Value("i", 0)
    with ProcessPoolExecutor(max_workers=workers, initializer=_bind_worker, initargs=(counter,)) as executor:
        futures = {executor.submit(play, jobs[index]): index for index in indexes}
        for future in as_completed(futures):
            try:
                outcome = future.result()
            except BrokenProcessPool:
                continue
            index = futures[future]
            results[index] = outcome
            if progress:
                _progress(len(results), len(jobs), jobs[index], outcome, started)


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
    mirror: bool = False,
    farm: Any = None,
) -> artifact.RunArtifact:
    """Play the gauntlet and return the run artifact with the leaderboard in its stats.

    With `progress` each game that ends prints one line on the error stream. With `mirror`
    each panel agent also plays itself `games` times on each scenario, for the side baseline.
    """
    field = _field(candidate, panel)
    if len(field) < 2:
        raise ValueError("the gauntlet needs the candidate and one panel agent or more")

    # Each result as the agent of the first side, the agent of the second side, the score
    # of the first side, and the scenario, for the fit with the side term.
    results: list[tuple[str, str, float, str]] = []
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
            "first_game_seed": family_seed("gauntlet", seed),
            "paired_seeds": balance,
            "anchor_only": anchor_only,
            "balance_sides": balance,
            "workers": workers,
            "mirror": mirror,
            "farm": [str(a) for a in farm.addresses] if farm is not None else [],
        },
    )

    rows: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    harness_rows: list[dict[str, Any]] = []
    counter = 0
    seeds_used = 0
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
                    # With balance on, game g and game g + 1 play one seed with the sides
                    # changed. An odd count leaves the last game with a seed of its own.
                    if not balance or g % 2 == 0:
                        game_seed = family_seed("gauntlet", seed, seeds_used)
                        seeds_used += 1
                    counter += 1
                    swap = balance and g % 2 == 1
                    order = (second, first) if swap else (first, second)
                    pair_jobs.append((len(jobs), order))
                    jobs.append((scenario, game_seed, order[0], order[1]))
                pairs.append((scenario, first, second, pair_jobs))
    # The mirror games go after the round-robin, so their seeds do not change its seeds.
    mirrors: list[tuple[str, str, list[int]]] = []
    if mirror:
        for scenario in scenarios:
            for name in field:
                if name == candidate:
                    continue
                indexes = []
                for _g in range(games):
                    indexes.append(len(jobs))
                    jobs.append((scenario, family_seed("gauntlet", seed, seeds_used), name, name))
                    seeds_used += 1
                mirrors.append((scenario, name, indexes))
    outcomes = _play_all(jobs, workers, progress=progress, farm=farm)

    for scenario, first, second, pair_jobs in pairs:
        sides = sides_of[scenario]
        wins = {first: 0, second: 0, "draw": 0}
        # The wins of each agent as each side, so the row says who can attack and who can
        # only defend.
        by_side = {first: [0, 0], second: [0, 0]}
        played = {first: [0, 0], second: [0, 0]}
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
            if game_seed not in art.seeds:
                art.seeds.append(game_seed)
            for row in outcome.get("harness", []):
                harness_rows.append({"scenario": scenario, "seed": game_seed, "side": sides[row["player"]], **row})
            played[order[0]][0] += 1
            played[order[1]][1] += 1
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
            results.append((order[0], order[1], outcome_first_in_order, scenario))
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
                "a_games_by_side": {sides[0]: played[first][0], sides[1]: played[first][1]},
                "b_games_by_side": {sides[0]: played[second][0], sides[1]: played[second][1]},
                "games": games,
                "completed": games - failed,
                "errors": failed,
            }
        )

    mirror_rows: list[dict[str, Any]] = []
    for scenario, name, indexes in mirrors:
        sides = sides_of[scenario]
        side_wins = {sides[0]: 0, sides[1]: 0}
        failed = 0
        for index in indexes:
            outcome = outcomes[index]
            if outcome["error"] is not None:
                failed += 1
                continue
            if outcome["winner"] in side_wins:
                side_wins[outcome["winner"]] += 1
        mirror_rows.append(
            {
                "scenario": scenario,
                "agent": name,
                "games": len(indexes),
                "completed": len(indexes) - failed,
                "errors": failed,
                "wins_by_side": side_wins,
            }
        )

    # The ratings come from the whole result list, so the order of the pairs does not set
    # the rank, and the side term takes out the side each scenario favours (L7).
    fit = settled_ratings_by_side(results)
    elo = fit.table
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
        # The Elo points the first side of each scenario gets from its side alone.
        "side_advantage": {
            scenario: {"first_side": sides_of[scenario][0], "elo": value}
            for scenario, value in fit.to_dict().items()
        },
        "pairs": rows,
        "side_baseline": side_baseline(rows, mirror_rows, candidate, sides_of),
        "per_scenario": {
            name: {sc: rec.to_dict() for sc, rec in by_sc.items()} for name, by_sc in per_scenario.items()
        },
    }
    if mirror_rows:
        art.stats["mirror"] = mirror_rows
    if harness_rows:
        art.stats["harness"] = harness_rows
    art.versions = {"candidate": candidate, "panel": ",".join(panel)}
    return art


def side_baseline(
    rows: list[dict[str, Any]],
    mirror_rows: list[dict[str, Any]],
    candidate: str,
    sides_of: dict[str, tuple[str, ...]],
) -> list[dict[str, Any]]:
    """For each scenario, opponent, and side: the wins and the games of the candidate, of
    the other panel agents, and of the opponent against itself, on that side against that
    opponent. A rate is the wins over the games; `mirror` is absent with no mirror games."""
    out: list[dict[str, Any]] = []
    for scenario, sides in sides_of.items():
        opponents: list[str] = []
        for row in rows:
            if row["scenario"] != scenario:
                continue
            for name in (row["agent_a"], row["agent_b"]):
                if name != candidate and name not in opponents:
                    opponents.append(name)
        for opponent in opponents:
            for side in sides:
                entry: dict[str, Any] = {
                    "scenario": scenario,
                    "opponent": opponent,
                    "side": side,
                    "candidate": {"wins": 0, "games": 0},
                    "panel": {"wins": 0, "games": 0},
                }
                for row in rows:
                    if row["scenario"] != scenario or opponent not in (row["agent_a"], row["agent_b"]):
                        continue
                    mine = "b" if row["agent_a"] == opponent else "a"
                    key = "candidate" if row[f"agent_{mine}"] == candidate else "panel"
                    entry[key]["wins"] += row[f"{mine}_wins_by_side"][side]
                    entry[key]["games"] += row[f"{mine}_games_by_side"][side]
                for row in mirror_rows:
                    if row["scenario"] == scenario and row["agent"] == opponent:
                        entry["mirror"] = {"wins": row["wins_by_side"][side], "games": row["completed"]}
                out.append(entry)
    return out


def _share(cell: dict[str, Any] | None) -> str:
    if not cell or not cell["games"]:
        return "no games"
    return f"{cell['wins']} of {cell['games']} ({cell['wins'] * 100.0 / cell['games']:.1f} percent)"


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
        score = row[f"{mine}_wins"] + 0.5 * row["draws"]
        print(
            f"  {row['scenario']:30s} against {row[f'agent_{other}']:8s} "
            f"{rate_text(score, row['completed'])}  ({sides})"
        )
    baseline = art.stats.get("side_baseline", [])
    if baseline:
        print()
        print("the side baseline, wins on each side against each opponent (candidate; other panel agents; the opponent against itself):")
        for entry in baseline:
            print(
                f"  {entry['scenario']:30s} against {entry['opponent']:8s} as {entry['side']:8s} "
                f"{_share(entry['candidate'])}; {_share(entry['panel'])}; {_share(entry.get('mirror'))}"
            )
    advantage = art.stats.get("side_advantage", {})
    if advantage:
        print()
        print("the side term of the fit, in Elo points for the first side of each scenario:")
        for scenario, entry in advantage.items():
            print(f"  {scenario:34s} {entry['first_side']:10s} {entry['elo']:+7.1f}")
    games = next((r["games"] for r in board if r["agent"] == candidate), 0)
    warning = sample_warning(games)
    if warning:
        print()
        print(warning)
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


def farm_of(args: Any) -> Any:
    """The farm of `--remote` and `--remote-key`, or None."""
    text = getattr(args, "remote", "") or ""
    if not text:
        return None
    from slfarm import protocol as farm_protocol
    from slfarm.client import Farm, parse_addresses

    try:
        key = farm_protocol.read_key(args.remote_key)
    except farm_protocol.FarmKeyError as exc:
        raise RuntimeError(str(exc)) from exc
    return Farm(tuple(parse_addresses(text)), key)


def add_farm_arguments(p: Any) -> None:
    p.add_argument(
        "--remote",
        default="",
        help="farm hosts that play games too, as tars,case:5160 (sl-cli farm serve on each); the scripted agents only",
    )
    p.add_argument("--remote-key", default="farm.key.txt", help="the file with the farm key (sl-cli farm key)")


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
        mirror=bool(args.mirror),
        farm=farm_of(args),
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
    p.add_argument(
        "--games",
        type=int,
        default=20,
        help=f"games for each pair on each scenario, two for each seed; a baseline needs {MINIMUM_BASELINE_GAMES} or more games of the candidate, and each rate prints with its 95 percent Wilson interval",
    )
    p.add_argument("--seed", type=int, default=1, help="the first seed, inside the gauntlet range of seeds (slruns.seeds)")
    p.add_argument(
        "--anchor-only",
        action="store_true",
        help="play the candidate against each panel agent only, not the full round-robin",
    )
    p.add_argument("--no-balance", action="store_true", help="keep each agent on one side")
    p.add_argument("--runs", default="runs", help="the run directory")
    from slcli.worker_limit import workers_argument

    p.add_argument("--workers", type=workers_argument, default=1, help="processes that play the games; the results do not change")
    p.add_argument("--progress", action="store_true", help="print one line on the error stream for each game that ends")
    add_farm_arguments(p)
    p.add_argument(
        "--mirror",
        action="store_true",
        help="also play each panel agent against itself for the side baseline; not in the Elo",
    )
    p.set_defaults(func=run)
