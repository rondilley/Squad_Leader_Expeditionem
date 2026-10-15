"""`sl-cli evolve`: the parameter evolution of v7 with the games as the fitness (FR-44, FR-50).

The search is `slagents.scripted.evolve`, and this command gives it the fitness: each
candidate plays a panel of fixed agents on the seeds of the generation, and its score is
its share of the wins. The games of one generation go into one pool of workers, so a
generation of eleven candidates and 32 games each is about five minutes on sixteen
workers.

`--side` says which side the candidate plays. With `both` (the default) it plays each
side in turn, and the score mixes the two. The first run of 2026-09-20 showed what that
costs: on scenario 1 the German defence is the easy side, and a candidate that gains 5
German wins and loses 9 Russian wins still scores above the base. With `russian` or
`german` the candidate plays that side alone, so the search has one objective and the
other side is a run of its own.

The final stage. A search of 30 generations reads about 240 candidates, and the elite
of the last generation is the one whose scores went up, which is in part the noise of
the seeds it played. The second run of 2026-09-20 showed the size of that: the best of
the search had 32 percent across 200 games in the search and 29 percent across 180
games on seeds it had not played, against 23 percent for the base. So the command
plays the best candidates and the base again at the end, on seeds no generation used,
with `--final-games` games each. That table is the result of the run, and the best of
it is the candidate to keep.

The confirm stage (L7). The final table is also a selection: its best row is the best of
five noisy rates, so its rate is high by the same winner's curse. The command then plays
the row it chose, and the base, a third time on a third range of new seeds, and that
table (`stats["confirm"]`) is the estimate of the chosen candidate that no selection
read. The seeds of the generations, of the final stage, and of the confirm stage are in
three ranges of `slruns.seeds`, and none of them is a seed of a training run, a
gauntlet, or a tournament.

With `--side both` the two games of each side order share one seed (a paired design), so
the dice of a seed decide the game with the candidate on each side.

Sample size: a rate of 120 games has a 95 percent interval about 18 points wide. A
baseline needs 200 games or more (`slruns.seeds.MINIMUM_BASELINE_GAMES`), and each rate
prints with its Wilson interval.

The run artifact holds each candidate with its command line text, its genome, its score
in each generation, and its wins by opponent and by side. The best candidate is the
elite of the last generation with the best mean over its evaluations, and the artifact
names it as the text a person plays: `v7[name=value,...]`.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any, Sequence

from slagents.scripted import evolve as search
from slagents.scripted.v7 import Parameters, UnknownNation
from slcli.gauntlet import _play_all, add_farm_arguments, farm_of, split_agent_names
from slcli.play import build_engine_with_record
from slruns import artifact
from slruns.index import connect, upsert
from slruns.seeds import MINIMUM_BASELINE_GAMES, family_seed, rate_text, sample_warning

DEFAULT_PANEL = ("v7", "v6")


def base_of(text: str) -> Parameters:
    """The base record of a run: `v7`, `v7:<nation>`, `v7[...]`, or `v7:<nation>[...]`."""
    from slagents.scripted.v7 import parameters_of_name

    try:
        return parameters_of_name(text)
    except (ValueError, UnknownNation) as exc:
        raise search.EvolveError(f"the base is v7, v7:<nation>, or v7[name=value,...]: {exc}") from exc


def name_of(base_text: str, genome: Any, base: Parameters) -> str:
    """The agent name of a candidate, with the nation of the base when it has one.

    `search.text_of` gives the values that differ from the base, and a run on a profile
    has to name that profile, or the name plays the defaults with a few values on top.
    """
    text = search.text_of(genome, base)
    nation = base_text[3:].split("[")[0] if base_text.startswith("v7:") else ""
    if not nation:
        return text
    return f"v7:{nation}" if text == "v7" else f"v7:{nation}[{text[3:-1]}]"


SIDES = ("both", "first", "second")


def side_index(sides: tuple[str, str], side: str) -> int | None:
    """The player the candidate takes: 0, 1, or None for each side in turn.

    A side is a name of the scenario (`russian`), or `first` and `second` for the order
    of play, or `both`.
    """
    if side in ("both", ""):
        return None
    if side == "first":
        return 0
    if side == "second":
        return 1
    if side in sides:
        return sides.index(side)
    raise search.EvolveError(f"the side is both, first, second, {sides[0]}, or {sides[1]}, not {side!r}")


def generation_jobs(
    candidates: Sequence[search.Candidate],
    base: Parameters,
    panel: Sequence[str],
    scenario: str,
    games: int,
    first_seed: int,
    player: int | None = None,
    base_text: str = "v7",
) -> tuple[list[tuple[str, int, str, str]], list[tuple[int, int, str, bool]]]:
    """The games of one generation, and for each game the candidate index, the seed, the
    opponent, and whether the candidate is the first player.

    Each candidate plays the same seeds against the same panel. With no `player` it
    takes each side in turn, and the two games of a side pair share one seed (L7); with a
    player it takes that side in each game, one seed for each game.
    """
    jobs: list[tuple[str, int, str, str]] = []
    keys: list[tuple[int, int, str, bool]] = []
    for ci, cand in enumerate(candidates):
        text = name_of(base_text, cand.genome, base)
        for opponent in panel:
            for g in range(games):
                game_seed = first_seed + (g // 2 if player is None else g)
                first = (g % 2 == 0) if player is None else (player == 0)
                order = (text, opponent) if first else (opponent, text)
                jobs.append((scenario, game_seed, order[0], order[1]))
                keys.append((ci, game_seed, opponent, first))
    return jobs, keys


def score_generation(
    candidates: Sequence[search.Candidate],
    base: Parameters,
    panel: Sequence[str],
    scenario: str,
    sides: tuple[str, str],
    games: int,
    first_seed: int,
    workers: int,
    player: int | None = None,
    base_text: str = "v7",
    farm: Any = None,
) -> list[tuple[float, Any]]:
    """The share of the wins of each candidate, with its wins by opponent and by side."""
    jobs, keys = generation_jobs(candidates, base, panel, scenario, games, first_seed, player, base_text)
    outcomes = _play_all(jobs, workers, farm=farm)
    detail: list[dict[str, Any]] = [
        {"wins": 0, "games": 0, "errors": 0, "by_opponent": {name: [0, 0] for name in panel}, "by_side": {sides[0]: 0, sides[1]: 0}}
        for _ in candidates
    ]
    for (ci, game_seed, opponent, first), outcome in zip(keys, outcomes):
        record = detail[ci]
        record["games"] += 1
        if outcome["error"]:
            record["errors"] += 1
            continue
        side = sides[0] if first else sides[1]
        if outcome["winner"] == side:
            record["wins"] += 1
            record["by_opponent"][opponent][0] += 1
            record["by_side"][side] += 1
        record["by_opponent"][opponent][1] += 1
    return [(r["wins"] / r["games"] if r["games"] else 0.0, r) for r in detail]


def run_evolve(
    base_text: str,
    panel: Sequence[str],
    scenario: str,
    games: int,
    generations: int,
    population: int,
    parents: int,
    seed: int,
    workers: int,
    progress: bool = False,
    side: str = "both",
    final_games: int = 0,
    final_top: int = 4,
    only: Sequence[str] = (),
    farm: Any = None,
) -> artifact.RunArtifact:
    """Run the search and return its artifact."""
    base = base_of(base_text)
    engine, board_record = build_engine_with_record(scenario, None)
    sides = tuple(engine.scenario.players())
    player = side_index(sides, side)

    def seeds_of_games(first: int, count: int) -> list[int]:
        """The seeds `count` games of one candidate play: one for each side pair, or one for each game."""
        distinct = (count + 1) // 2 if player is None else count
        return [first + g for g in range(distinct)]

    art = artifact.RunArtifact(
        kind="evolve",
        slug=f"evolve-{base_text}",
        config={
            "base": base_text,
            "panel": list(panel),
            "scenario": scenario,
            "side": side,
            "player": player,
            **board_record,
            "games_per_opponent": games,
            "generations": generations,
            "population": population,
            "parents": parents,
            "seed": seed,
            "seed_ranges": {
                "generations": family_seed("evolve", seed),
                "final": family_seed("evolve_final", seed),
                "confirm": family_seed("evolve_confirm", seed),
            },
            "workers": workers,
            "farm": [str(a) for a in farm.addresses] if farm is not None else [],
            "final_games": final_games,
            "final_top": final_top,
            "only": list(only),
            "space": {name: list(rng) for name, rng in search.SPACE.items()},
            "flags": list(search.FLAGS),
        },
    )
    started = time.perf_counter()
    games_played = 0

    def fitness(candidates: Sequence[search.Candidate], index: int) -> list[tuple[float, Any]]:
        nonlocal games_played
        # New seeds for each generation, the same seeds for each candidate of it.
        first_seed = family_seed("evolve", seed, 1000 * (index + 1))
        art.seeds.extend(seeds_of_games(first_seed, games))
        scores = score_generation(candidates, base, panel, scenario, sides, games, first_seed, workers, player, base_text, farm)
        games_played += sum(r["games"] for _, r in scores)
        return scores

    def report(run: search.Evolution, gen: search.Generation) -> None:
        if not progress:
            return
        minutes = (time.perf_counter() - started) / 60.0
        best_id, best_score = gen.scored[0]
        text = name_of(base_text, run.candidate(best_id).genome, base)
        print(
            f"generation {gen.index}: best {best_score * 100:.0f}% {text} | elites {gen.elites} | {games_played} games, {minutes:.1f} min",
            file=sys.stderr,
            flush=True,
        )

    run = search.run_evolution(
        fitness,
        generations=generations,
        population=population,
        parents=parents,
        seed=seed,
        base=base,
        games=games * len(panel),
        only=list(only) or None,
        on_generation=report,
    )
    final: list[dict[str, Any]] = []
    confirm: list[dict[str, Any]] = []
    if final_games > 0:
        first_seed = family_seed("evolve_final", seed)
        art.seeds.extend(seeds_of_games(first_seed, final_games))
        final = final_stage(run, base, panel, scenario, sides, final_games, first_seed, workers, player, final_top, base_text, farm)
        games_played += sum(row["games"] for row in final)
        confirm_seed = family_seed("evolve_confirm", seed)
        art.seeds.extend(seeds_of_games(confirm_seed, final_games))
        confirm = confirm_stage(run, final[0]["id"], base, panel, scenario, sides, final_games, confirm_seed, workers, player, base_text, farm)
        games_played += sum(row["games"] for row in confirm)
        if progress:
            best = final[0]
            print(
                f"final stage: {best['wins']} of {best['games']} for candidate {best['id']}"
                f"{' (the base)' if best['is_base'] else ''}, {(time.perf_counter() - started) / 60.0:.1f} min",
                file=sys.stderr,
                flush=True,
            )
    art.stats = {
        "games": games_played,
        "seconds": round(time.perf_counter() - started, 1),
        **run.to_dict(),
        "final": final,
        "confirm": confirm,
    }
    return art


def confirm_stage(
    run: search.Evolution,
    chosen_id: int,
    base: Parameters,
    panel: Sequence[str],
    scenario: str,
    sides: tuple[str, str],
    games: int,
    first_seed: int,
    workers: int,
    player: int | None,
    base_text: str = "v7",
    farm: Any = None,
) -> list[dict[str, Any]]:
    """The candidate the final stage chose, and the base, on seeds no stage used (L7).

    The final table picks its best row from a few noisy rates, so that row's rate is high
    by the winner's curse. This table plays the pick again after the pick, so its rate is
    an estimate that no selection read. The chosen row comes first and the base second;
    when the base is the pick, the table has the one row.
    """
    chosen = [run.candidate(chosen_id)]
    if chosen_id != 0:
        chosen.append(run.candidates[0])
    scores = score_generation(chosen, base, panel, scenario, sides, games, first_seed, workers, player, base_text, farm)
    out = []
    for cand, (score, detail) in zip(chosen, scores):
        out.append(
            {
                "id": cand.id,
                "text": name_of(base_text, cand.genome, base),
                "confirm": round(score, 4),
                "wins": detail["wins"],
                "games": detail["games"],
                "by_opponent": detail["by_opponent"],
                "by_side": detail["by_side"],
                "is_base": cand.id == 0,
            }
        )
    return out


def final_stage(
    run: search.Evolution,
    base: Parameters,
    panel: Sequence[str],
    scenario: str,
    sides: tuple[str, str],
    games: int,
    first_seed: int,
    workers: int,
    player: int | None,
    top: int,
    base_text: str = "v7",
    farm: Any = None,
) -> list[dict[str, Any]]:
    """The best candidates and the base, played again on seeds no generation used.

    The candidates come in the order of their lower bound, and the base is always in
    the table, because the question of a search is whether it beat the base.
    """
    ranked = sorted((c for c in run.candidates if c.evaluations >= 2), key=lambda c: -c.lower_bound(run.games))
    chosen: list[search.Candidate] = []
    for cand in ranked:
        if len(chosen) >= top:
            break
        chosen.append(cand)
    if run.candidates[0] not in chosen:
        chosen.append(run.candidates[0])
    scores = score_generation(chosen, base, panel, scenario, sides, games, first_seed, workers, player, base_text, farm)
    out = []
    for cand, (score, detail) in zip(chosen, scores):
        out.append(
            {
                "id": cand.id,
                "text": name_of(base_text, cand.genome, base),
                "search_mean": round(cand.mean, 4),
                "search_games": cand.evaluations * run.games,
                "final": round(score, 4),
                "wins": detail["wins"],
                "games": detail["games"],
                "by_opponent": detail["by_opponent"],
                "by_side": detail["by_side"],
                "is_base": cand.id == 0,
            }
        )
    out.sort(key=lambda r: -r["final"])
    return out


def print_summary(art: artifact.RunArtifact) -> None:
    s = art.stats
    print(f"run {art.id} ({s['games']} games in {s['seconds']:.0f} s, the candidate as {art.config['side']})")
    print()
    print(f"{'gen':>4s}  {'best of the generation':>22s}  elites")
    for gen in s["generations"]:
        cid, score = gen["scored"][0]
        print(f"{gen['index']:4d}  {score * 100:21.0f}%  {gen['elites']}")
    best = s["best"]
    print()
    print(f"best: {best['text']}")
    print(
        f"  {best['mean'] * 100:.1f}% of {best['games']} games in {best['evaluations']} generations, "
        f"lower bound {best['lower_bound'] * 100:.1f}%, candidate {best['id']}"
    )
    base_scores = s["candidates"][0]["scores"]
    print(f"  the base scored {', '.join(f'{v * 100:.0f}%' for v in base_scores.values())} in the generations it played")
    for gen_index, detail in best["details"].items():
        by_side = ", ".join(f"{k} {v}" for k, v in detail["by_side"].items())
        by_opp = ", ".join(f"{k} {w} of {n}" for k, (w, n) in detail["by_opponent"].items())
        print(f"  generation {gen_index}: {detail['wins']} of {detail['games']} ({by_side}; {by_opp})")
    rows = s.get("final")
    if rows:
        print()
        print("the final stage, on seeds no generation played:")
        for row in rows:
            name = "the base" if row["is_base"] else row["text"][:60]
            print(f"  {row['id']:4d}  {rate_text(row['wins'], row['games'])}; in the search {row['search_mean'] * 100:5.1f}% of {row['search_games']:4d}  {name}")
    rows = s.get("confirm")
    if rows:
        print()
        print("the confirm stage, the pick of the final stage and the base on new seeds (no selection read these):")
        for row in rows:
            name = "the base" if row["is_base"] else row["text"][:60]
            print(f"  {row['id']:4d}  {rate_text(row['wins'], row['games'])}  {name}")
        warning = sample_warning(rows[0]["games"])
        if warning:
            print(f"  {warning}")


def run(args: Any) -> int:
    panel = split_agent_names(str(args.panel))
    art = run_evolve(
        args.base,
        panel,
        args.scenario,
        args.games,
        args.generations,
        args.population,
        args.parents,
        args.seed,
        args.workers,
        progress=bool(args.progress),
        side=str(args.side),
        final_games=args.final_games,
        final_top=args.final_top,
        only=[name.strip() for name in str(args.only).split(",") if name.strip()],
        farm=farm_of(args),
    )
    directory = art.write(args.runs)
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        upsert(conn, directory)
    finally:
        conn.close()
    print_summary(art)
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser(
        "evolve",
        help="evolve the parameters of v7 against a fixed panel, with the games as the fitness",
    )
    p.add_argument("--base", default="v7", help="the start record: v7, v7:<nation>, or v7[name=value,...]")
    p.add_argument("--panel", default=",".join(DEFAULT_PANEL), help="the fixed opponents, as v7,v6")
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--games", type=int, default=16, help="games against each opponent for each candidate in a generation, half as each side")
    p.add_argument("--generations", type=int, default=10)
    p.add_argument("--population", type=int, default=8, help="children in each generation (lambda)")
    p.add_argument("--parents", type=int, default=3, help="elites kept as parents (mu)")
    p.add_argument("--seed", type=int, default=1, help="the seed of the search, and the first seed of the evolve ranges of seeds (slruns.seeds)")
    p.add_argument("--side", default="both", help="the side the candidate plays: both, first, second, or a side name of the scenario")
    from slcli.worker_limit import workers_argument

    p.add_argument("--workers", type=workers_argument, default=1, help="processes that play the games")
    add_farm_arguments(p)
    p.add_argument("--runs", default="runs", help="the run directory")
    p.add_argument("--only", default="", help="the parameters the search moves, as smoke_floor,smoke_horizon; the rest keep the base (the default is each of them)")
    p.add_argument(
        "--final-games",
        type=int,
        default=120,
        help=f"games of the final stage for each of the best candidates and the base, on seeds no generation used, and of the confirm stage of the pick and the base, on new seeds again (0 is neither stage); a baseline needs {MINIMUM_BASELINE_GAMES} or more",
    )
    p.add_argument("--final-top", type=int, default=4, help="candidates of the final stage, by their lower bound")
    p.add_argument("--progress", action="store_true", help="print one line on the error stream for each generation")
    p.set_defaults(func=run)
