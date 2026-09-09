"""The runs command: rebuild the index and list what is in it (FR-57)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from slruns.index import connect, elo_history, list_runs, rebuild


def run(args: Any) -> int:
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        if args.rebuild:
            count = rebuild(conn, args.runs)
            print(f"indexed {count} runs from {args.runs}")
        if args.elo:
            history = elo_history(conn, args.elo)
            if not history:
                print(f"no run holds an Elo entry for {args.elo}")
            for row in history:
                print(f"{row['started']} {row['id']}: {row['rating']} after {row['games']} games")
            return 0
        for row in list_runs(conn, args.kind, args.limit):
            print(f"{row['started']} {row['id']} kind={row['kind']} scenario={row['scenario']} games={row['games']}")
    finally:
        conn.close()
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("runs", help="list the run index or build it again")
    p.add_argument("--runs", default="runs")
    p.add_argument("--rebuild", action="store_true")
    p.add_argument("--kind", default=None)
    p.add_argument("--limit", type=int, default=50)
    p.add_argument("--elo", default=None, help="show the Elo history of one agent")
    p.set_defaults(func=run)
