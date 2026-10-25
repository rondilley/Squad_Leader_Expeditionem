"""The library command: the 12 project scenarios of the library (owner directive, 2026-10-16).

    sl-cli library slots
    sl-cli library draw --slot L01 --seed 1 --board-seed 1
    sl-cli library check --slot L01 --seed 1 --board-seed 1 --agents v3,v6,v7
    sl-cli library search --slot L01 --seed 1 --board-seeds 1-20 --remote tars,case,kipp,plex
    sl-cli library search --slot L01 --seeds 1-10 --board-seeds 1-10 --screen 100 --remote tars,case,kipp,plex

`draw` writes the scenario document of one candidate of a slot (`slcampaign.library`).
`check` is item 3 of the gate of a library scenario: each agent plays the candidate
against itself on the two sides, and each game must end. `search` is item 4: the balance
by the board seed first, with the forces fixed. It screens each board seed with games of
v7 against v7, then confirms the seed nearest to an even result with more games, and it
writes a run artifact with the rate of each seed. The owner's measure is 1,600 games and
45 to 55 percent for the first side. When no board seed gives the balance, `--seeds`
screens other draw seeds too, which is a change of the forces inside the slot bands.

A candidate is a file under `--out` (default `runs/library/<slot>`), and the games play it
as `file:<path>`, so the game farm gets it as a document (`slfarm.client`).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from slcampaign import library
from slcampaign.generator import ScenarioError
from slcampaign.run import counter_types, point_values
from slruns import artifact
from slruns.index import connect, upsert

DEFAULT_AGENTS = "v3,v6,v7"
CHECK_GAMES = 2
SCREEN_GAMES = 200
CONFIRM_GAMES = 1600
# The search confirms this many of the best pairs of the screen.
CONFIRM_TOP = 3
BALANCE_LOW = 45
BALANCE_HIGH = 55
# The game seeds of the confirmation start here, so they are not the seeds of the screen.
CONFIRM_SEED_BASE = 1_000_000


def parse_seeds(text: str) -> list[int]:
    """`1-20` or `3,7,11` or a mix of the two."""
    out: list[int] = []
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            low, high = part.split("-", 1)
            out.extend(range(int(low), int(high) + 1))
        else:
            out.append(int(part))
    if not out:
        raise ValueError(f"no seed in {text!r}")
    return out


def write_candidate(slot_id: str, seed: int, board_seed: int, out: Path) -> tuple[Path, dict[str, Any], library.LibraryDraw]:
    slot, vehicles = library.slot_by_id(slot_id)
    types = counter_types()
    document, d = library.candidate(slot, seed, board_seed, types, point_values(types), vehicles)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{document['id']}_s{seed}_b{board_seed}.json"
    path.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    return path, document, d


def _out(args: Any) -> Path:
    return Path(args.out) if args.out else Path(args.runs) / "library" / args.slot.upper()


def _slots(args: Any) -> int:
    slots, _ = library.load_slots()
    for s in slots:
        boards = " and ".join(s.boards)
        print(
            f"{s.id} {s.title}: {s.attacker} attacks {s.defender}"
            + (f" and {s.defender_second}" if s.defender_second else "")
            + f", {boards}, rules 1 to {s.rules}, {s.turns[0]} to {s.turns[1]} turns, "
            f"{s.points[0]} to {s.points[1]} points"
        )
    return 0


def _draw(args: Any) -> int:
    path, document, d = write_candidate(args.slot, args.seed, args.board_seed, _out(args))
    print(f"{document['id']}: {document['title']}, draw seed {args.seed}, board seed {args.board_seed}")
    print(f"  {d.turns} turns, victory {d.victory_kind}, share {d.attack_share[0]} to {d.attack_share[1]}")
    for name, force in (("attack", d.attacker), ("defence", d.defender), ("second defence", d.defender_second)):
        if force is None:
            continue
        print(
            f"  {name}: {force.nationality}, {force.points} points, {force.squad_count()} squads, "
            f"{force.leader_count()} leaders, {force.vehicle_count()} vehicles, weapons {dict(force.weapons)}"
        )
    print(f"  card: {document['situation']}")
    print(f"wrote {path}")
    return 0


def _first_side_wins(document: dict[str, Any], outcomes: list[dict[str, Any]]) -> tuple[int, int, int]:
    """The wins of the first side, the games with a winner or not, and the games that failed."""
    first = document["first_mover"]
    wins = sum(1 for o in outcomes if o.get("winner") == first)
    errors = sum(1 for o in outcomes if o.get("error"))
    return wins, len(outcomes), errors


def _check(args: Any) -> int:
    from slcli.gauntlet import _play_all, farm_of

    path, document, _ = write_candidate(args.slot, args.seed, args.board_seed, _out(args))
    agents = [a.strip() for a in args.agents.split(",") if a.strip()]
    jobs = [(f"file:{path}", game, agent, agent) for agent in agents for game in range(1, args.games + 1)]
    outcomes = _play_all(jobs, args.workers, progress=args.progress, farm=farm_of(args))
    failed = 0
    for job, outcome in zip(jobs, outcomes):
        _, game, agent, _ = job
        if outcome.get("error"):
            failed += 1
            print(f"  {agent} game {game}: FAILED {outcome['error']}: {outcome.get('message', '')}")
        else:
            print(f"  {agent} game {game}: {outcome.get('winner') or 'no winner'}")
    print(f"{document['id']}: {len(jobs) - failed} of {len(jobs)} games ended")
    return 1 if failed else 0


def _rate(wins: int, games: int) -> float:
    return 100.0 * wins / games if games else 0.0


def make_candidates(
    slot_id: str, seeds: list[int], board_seeds: list[int], out: Path
) -> tuple[dict[tuple[int, int], tuple[Path, dict[str, Any]]], list[tuple[int, str]]]:
    """The candidate file of each pair, and each draw seed that gives no candidate.

    A low point total of a slot with vehicles can buy fewer than three squads after the
    vehicles (2026-10-17: L05, L06, L07, and L12 have such seeds). That draw seed is out of
    the search with its reason, and the other seeds go on.
    """
    candidates: dict[tuple[int, int], tuple[Path, dict[str, Any]]] = {}
    skipped: list[tuple[int, str]] = []
    for seed in seeds:
        try:
            for board_seed in board_seeds:
                path, document, _ = write_candidate(slot_id, seed, board_seed, out)
                candidates[(seed, board_seed)] = (path, document)
        except ScenarioError as exc:
            skipped.append((seed, str(exc)))
            for board_seed in board_seeds:
                candidates.pop((seed, board_seed), None)
    return candidates, skipped


def rank_screen(
    pairs: list[tuple[int, int]],
    candidates: dict[tuple[int, int], tuple[Path, dict[str, Any]]],
    outcomes: list[dict[str, Any]],
    screen: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """The row of each candidate of the screen, and the candidates from the best: those with
    no failed game, nearest to 50 percent first. The outcomes come in the order of `pairs`,
    `screen` of them for each pair."""
    rows = []
    for index, (seed, board_seed) in enumerate(pairs):
        path, document = candidates[(seed, board_seed)]
        part = outcomes[index * screen : (index + 1) * screen]
        wins, games, errors = _first_side_wins(document, part)
        rows.append(
            {
                "draw_seed": seed,
                "board_seed": board_seed,
                "file": str(path),
                "wins": wins,
                "games": games,
                "errors": errors,
                "rate": round(_rate(wins, games), 1),
            }
        )
    usable = [r for r in rows if r["errors"] == 0] or rows
    ranked = sorted(usable, key=lambda r: (abs(r["rate"] - 50.0), r["draw_seed"], r["board_seed"]))
    return rows, ranked


def best_confirmation(confirmations: list[dict[str, Any]]) -> dict[str, Any]:
    """The confirmed pair with no failed game nearest to 50 percent, or nothing."""
    usable = [c for c in confirmations if c["errors"] == 0] or confirmations
    if not usable:
        return {}
    return min(usable, key=lambda c: (abs(c["rate"] - 50.0), c["draw_seed"], c["board_seed"]))


def search(
    slot_id: str,
    seeds: list[int],
    board_seeds: list[int],
    out: Path,
    screen: int,
    confirm: int,
    agent: str,
    workers: int,
    farm: Any = None,
    progress: bool = False,
    confirm_top: int = CONFIRM_TOP,
) -> artifact.RunArtifact:
    """Item 4 of the gate: the candidate that gives the first side 45 to 55 percent.

    Each pair of a draw seed and a board seed plays `screen` games of `agent` against
    itself. The `confirm_top` pairs nearest to 50 percent then play `confirm` games each on
    other game seeds, because a screen of 100 games varies by approximately 10 points
    (2026-10-17). The confirmed pair nearest to 50 percent is the result, and the artifact
    says if it is in the band. With one draw seed the forces do not
    change, which is the board seed first of the owner's rule. More draw seeds give other
    forces, turns, and victory conditions inside the bands of the slot (2026-10-17).
    """
    from slcli.gauntlet import _play_all

    seed_text = f"s{seeds[0]}" if len(seeds) == 1 else f"s{seeds[0]}-{seeds[-1]}"
    art = artifact.RunArtifact(
        kind="library-search",
        slug=f"library-{slot_id.lower()}-{seed_text}",
        config={
            "slot": slot_id.upper(),
            "draw_seeds": seeds,
            "board_seeds": board_seeds,
            "screen_games": screen,
            "confirm_games": confirm,
            "confirm_top": confirm_top,
            "agent": agent,
            "band": [BALANCE_LOW, BALANCE_HIGH],
            "farm": [str(a) for a in farm.addresses] if farm is not None else [],
        },
    )
    candidates, skipped = make_candidates(slot_id, seeds, board_seeds, out)
    for seed, reason in skipped:
        print(f"  draw seed {seed}: no candidate, {reason}")
    if not candidates:
        raise ScenarioError(f"slot {slot_id}: no draw seed of {seeds} gives a candidate")
    pairs = list(candidates)
    jobs: list[tuple[str, int, str, str]] = []
    for pair in pairs:
        path, _ = candidates[pair]
        jobs.extend((f"file:{path}", game, agent, agent) for game in range(1, screen + 1))
    outcomes = _play_all(jobs, workers, progress=progress, farm=farm)
    rows, ranked = rank_screen(pairs, candidates, outcomes, screen)
    for row in rows:
        print(
            f"  draw seed {row['draw_seed']} board seed {row['board_seed']}: first side {row['wins']} of "
            f"{row['games']} ({row['rate']:.1f} percent), {row['errors']} failed"
        )
    confirmations: list[dict[str, Any]] = []
    if confirm:
        chosen = ranked[: max(1, confirm_top)]
        jobs = []
        for row in chosen:
            path, _ = candidates[(row["draw_seed"], row["board_seed"])]
            jobs.extend((f"file:{path}", CONFIRM_SEED_BASE + game, agent, agent) for game in range(1, confirm + 1))
        played = _play_all(jobs, workers, progress=progress, farm=farm)
        for index, row in enumerate(chosen):
            path, document = candidates[(row["draw_seed"], row["board_seed"])]
            wins, games, errors = _first_side_wins(document, played[index * confirm : (index + 1) * confirm])
            rate = _rate(wins, games)
            confirmations.append(
                {
                    "draw_seed": row["draw_seed"],
                    "board_seed": row["board_seed"],
                    "file": str(path),
                    "wins": wins,
                    "games": games,
                    "errors": errors,
                    "rate": round(rate, 1),
                    "balanced": errors == 0 and BALANCE_LOW <= rate <= BALANCE_HIGH,
                }
            )
            print(
                f"confirm draw seed {row['draw_seed']} board seed {row['board_seed']}: first side {wins} of {games} "
                f"({rate:.1f} percent), {errors} failed: {'balanced' if confirmations[-1]['balanced'] else 'not balanced'}"
            )
    confirmation = best_confirmation(confirmations)
    if confirmation:
        print(
            f"result: draw seed {confirmation['draw_seed']} board seed {confirmation['board_seed']}, "
            f"{confirmation['rate']:.1f} percent, {'balanced' if confirmation['balanced'] else 'not balanced'}"
        )
    art.stats = {
        "screen": rows,
        "skipped_draw_seeds": [{"draw_seed": seed, "reason": reason} for seed, reason in skipped],
        "best": ranked[0],
        "confirmations": confirmations,
        "confirmation": confirmation,
    }
    return art


def _search(args: Any) -> int:
    from slcli.gauntlet import farm_of

    seeds = parse_seeds(args.seeds) if args.seeds else [args.seed]
    art = search(
        args.slot,
        seeds,
        parse_seeds(args.board_seeds),
        _out(args),
        args.screen,
        args.confirm,
        args.agent,
        args.workers,
        farm=farm_of(args),
        progress=args.progress,
        confirm_top=args.confirm_top,
    )
    directory = art.write(args.runs)
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        upsert(conn, directory)
    finally:
        conn.close()
    print(f"run artifact {directory}")
    confirmation = art.stats["confirmation"]
    return 0 if not confirmation or confirmation["balanced"] else 2


def add_parser(subparsers: Any) -> None:
    from slcli.gauntlet import add_farm_arguments

    p = subparsers.add_parser("library", help="the 12 project scenarios of the library")
    actions = p.add_subparsers(dest="action", required=True)

    a = actions.add_parser("slots", help="list the 12 slots")
    a.set_defaults(func=_slots)

    def common(q: Any) -> None:
        q.add_argument("--slot", required=True, help="the slot, L01 to L12")
        q.add_argument("--seed", type=int, default=1, help="the draw seed: the forces, the turns, the victory")
        q.add_argument("--out", default=None, help="the directory of the candidate files (default runs/library/<slot>)")
        q.add_argument("--runs", default="runs")

    def players(q: Any) -> None:
        q.add_argument("--workers", type=int, default=8)
        q.add_argument("--progress", action="store_true")
        add_farm_arguments(q)

    a = actions.add_parser("draw", help="write one candidate of a slot")
    common(a)
    a.add_argument("--board-seed", type=int, default=1)
    a.set_defaults(func=_draw)

    a = actions.add_parser("check", help="gate item 3: each agent plays the candidate to the end on the two sides")
    common(a)
    a.add_argument("--board-seed", type=int, default=1)
    a.add_argument("--agents", default=DEFAULT_AGENTS)
    a.add_argument("--games", type=int, default=CHECK_GAMES, help="games of each agent against itself")
    players(a)
    a.set_defaults(func=_check)

    a = actions.add_parser("search", help="gate item 4: the board seed that balances the slot")
    common(a)
    a.add_argument("--seeds", default="", help="draw seeds to screen too, as 1-10; each one with each board seed")
    a.add_argument("--board-seeds", default="1-20", help="the board seeds to screen, as 1-20 or 3,7,11")
    a.add_argument("--screen", type=int, default=SCREEN_GAMES, help="games of each board seed")
    a.add_argument("--confirm", type=int, default=CONFIRM_GAMES, help="games of each confirmed pair")
    a.add_argument("--confirm-top", type=int, default=CONFIRM_TOP, help="how many of the best pairs of the screen to confirm")
    a.add_argument("--agent", default="v7")
    players(a)
    a.set_defaults(func=_search)
