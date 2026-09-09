"""The boards command: generate boards, check them, and write the TC-14a evidence.

`sl-cli boards --check 1000` is the gate run of slice 6. It generates the boards, tests
each one against the geomorphic edge rules, joins each board to the next on the east and
on the south, and sets up scenario 1 on it. The run artifact holds the count, the seeds
that needed a retry, and the parameters of each board that failed.

`sl-cli boards --write <directory>` writes the board documents and the empty score sheet
of TC-14b, so the owner scores them. With the default count of 12 and the default type of
`all`, the directory holds three boards of each of the four types, which is what TC-14b
asks for. The owner fills the sheet in; the command scores nothing.
"""

from __future__ import annotations

import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any

from slboards import edges
from slboards.generator import BOARD_TYPES, GeneratorError, GeneratorParameters, generate
from slcore.engine import Engine
from slruns import artifact
from slruns.index import connect, upsert
from sldata.loaders import (
    board_and_parameters,
    load_all_counters,
    load_hexsides,
    load_scenario,
    load_tables,
    load_terrain,
)


def types_for(count: int, board_type: str) -> list[str]:
    """The type of each board in the run, in order.

    `all` spreads the count over the four types of FR-25 and cycles them, so board n and
    board n+1 are of different types. The join test then tests the harder case: a city
    board next to a rural board.
    """
    if board_type == "all":
        return [BOARD_TYPES[i % len(BOARD_TYPES)] for i in range(count)]
    if board_type not in BOARD_TYPES:
        raise ValueError(f"{board_type!r} is not a board type; the types are {BOARD_TYPES} or all")
    return [board_type] * count


def check_boards(count: int, first_seed: int, scenario_name: str, board_type: str = "all") -> artifact.RunArtifact:
    """TC-14a: each board satisfies the edge rules, joins another board, and holds the scenario."""
    terrain = load_terrain()
    base = load_scenario(scenario_name)
    hexsides, counters, tables = load_hexsides(), load_all_counters(), load_tables()
    art = artifact.RunArtifact(
        kind="boards",
        slug=f"tc14a-{scenario_name}",
        config={
            "scenario": scenario_name,
            "board": "generated",
            "board_type": board_type,
            "boards": count,
            "first_seed": first_seed,
            "criteria": ["TC-14a"],
        },
    )
    plan = types_for(count, board_type)
    edge_failures: list[dict[str, Any]] = []
    join_failures: list[dict[str, Any]] = []
    setup_failures: list[dict[str, Any]] = []
    retries: list[dict[str, int]] = []
    previous: dict | None = None
    started = time.perf_counter()
    for step in range(count):
        seed = first_seed + step
        art.seeds.append(seed)
        board = generate(GeneratorParameters(seed=seed, board_type=plan[step]), terrain)
        kinds = edges.kind_map(board)
        problems = edges.check_edges(kinds, board.cols, board.rows)
        if problems:
            edge_failures.append({"seed": seed, "type": plan[step], "problems": problems[:4]})
        if previous is not None:
            for side in ("east", "south"):
                joined = edges.check_join(previous, kinds, side, board.cols, board.rows)
                if joined:
                    join_failures.append({"seed": seed, "side": side, "problems": joined[:4]})
        previous = kinds
        if plan[step] != "city":
            # Scenario 1 asks for stone buildings in named zones (FR-21), and only a city
            # board holds that many. The set up half of TC-14a stays on the city boards.
            continue
        generator = dict(base.board_generator)
        generator["seed"] = seed
        scenario = replace(base, board_generator=tuple(sorted(generator.items())))
        try:
            play_board, params = board_and_parameters(scenario, terrain)
            Engine(scenario, play_board, terrain, hexsides, counters, tables)
            if params is not None and params.seed != seed:
                retries.append({"asked": seed, "used": params.seed})
        except (GeneratorError, ValueError) as exc:
            setup_failures.append({"seed": seed, "error": type(exc).__name__, "message": str(exc)[:300]})
    art.stats = {
        "boards": count,
        "types": sorted(set(plan)),
        "seconds": round(time.perf_counter() - started, 2),
        "edge_failures": edge_failures,
        "join_failures": join_failures,
        "setup_failures": setup_failures,
        "retries": retries,
        "retry_rate": round(len(retries) / count, 4) if count else 0.0,
        "passed": {"TC-14a": not edge_failures and not join_failures and not setup_failures},
    }
    return art


RUBRIC = (
    "Hex grid, center dots, and grid labels are readable at the default zoom.",
    "Terrain types are identifiable at a glance without a legend.",
    "The color palette is in the 1977 family: flat greens, browns, grays, and yellows.",
    "Woods and hill edges look hand-drawn, not procedural.",
    "Buildings have the shapes and dimensions of the 1977 boards.",
    "The board satisfies the geomorphic edge rules and joins a second board with no visible seam.",
    "Counters are readable at the default zoom.",
    "The board type is identifiable: a city looks like a city, a hills board like hills.",
)


def score_sheet(names: list[str]) -> str:
    """The empty TC-14b sheet. The command writes the rows; the owner writes the scores."""
    lines = [
        "# The board look rubric, TC-14b",
        "",
        "Score each item 1 to 5 for each board. TC-14b holds when the mean is 4 or more and no",
        "board is below 3. Open each board in the client, at the default zoom, before scoring.",
        "",
        "The items:",
        "",
    ]
    lines += [f"{i}. {text}" for i, text in enumerate(RUBRIC, start=1)]
    lines += ["", "| Board | " + " | ".join(str(i) for i in range(1, len(RUBRIC) + 1)) + " | Mean |"]
    lines.append("|---" * (len(RUBRIC) + 2) + "|")
    for name in names:
        lines.append(f"| {name} | " + " | ".join(" " for _ in RUBRIC) + " |  |")
    lines += ["", "Owner:", "Date:", ""]
    return "\n".join(lines)


def write_boards(count: int, first_seed: int, directory: Path, board_type: str = "all") -> int:
    """The board documents and the empty score sheet for the owner (TC-14b)."""
    terrain = load_terrain()
    directory.mkdir(parents=True, exist_ok=True)
    plan = types_for(count, board_type)
    names = []
    for step in range(count):
        seed = first_seed + step
        params = GeneratorParameters(seed=seed, board_type=plan[step])
        board = generate(params, terrain)
        doc = board.to_dict()
        doc["generator"] = params.to_dict()
        (directory / f"{board.name}.json").write_text(json.dumps(doc, indent=1), encoding="utf-8")
        names.append(board.name)
    (directory / "scores.md").write_text(score_sheet(names), encoding="utf-8")
    print(f"wrote {count} board documents and an empty score sheet in {directory}")
    for name in names:
        print(f"  {name}")
    return 0


def run(args: Any) -> int:
    if args.write:
        return write_boards(args.count, args.seed, Path(args.write), args.type)
    art = check_boards(args.count, args.seed, args.scenario, args.type)
    stats = art.stats
    print(f"{stats['boards']} boards of {', '.join(stats['types'])} from seed {args.seed} in {stats['seconds']} s")
    print(f"edge failures {len(stats['edge_failures'])}, join failures {len(stats['join_failures'])}, "
          f"set up failures {len(stats['setup_failures'])}")
    print(f"seeds that needed a retry: {len(stats['retries'])} ({100.0 * stats['retry_rate']:.1f} percent)")
    print(f"TC-14a {'holds' if stats['passed']['TC-14a'] else 'fails'}")
    directory = art.write(args.runs)
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        upsert(conn, directory)
    finally:
        conn.close()
    print(f"run artifact {directory}")
    return 0 if stats["passed"]["TC-14a"] else 1


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("boards", help="generate boards, check them (TC-14a), or write them for scoring")
    p.add_argument("--count", type=int, default=1000, help="how many boards")
    p.add_argument(
        "--type",
        default="all",
        help="one board type, or all to spread the count over the four types of FR-25",
    )
    p.add_argument("--seed", type=int, default=1, help="the first seed")
    p.add_argument("--scenario", default="s01_guards_counterattack", help="the scenario to set up on each board")
    p.add_argument(
        "--write",
        default=None,
        help="write the board documents and the empty TC-14b score sheet in this directory",
    )
    p.add_argument("--runs", default="runs")
    p.set_defaults(func=run)
