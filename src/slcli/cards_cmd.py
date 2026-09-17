"""The cards command: render printable scenario cards.

`sl-cli cards --scenario s01_guards_counterattack --out <dir>` writes `card_<id>.png` for one
scenario. `sl-cli cards --all --out <dir>` writes a card for every scenario in the data.

The card evokes the 1977 scenario card, but every word comes from the scenario JSON (FR-22)
and every shape is the project's own drawing (SR-07, DR-01). The renderer runs offscreen, so
the command needs no display.
"""

from __future__ import annotations

import json
from importlib import resources
from pathlib import Path
from typing import Any

from sldata.loaders import DataError


def _scenario_names() -> list[str]:
    """The ids of every scenario JSON in the data package."""
    names = []
    for entry in resources.files("sldata").joinpath("scenarios").iterdir():
        if entry.name.endswith(".json"):
            names.append(entry.name[:-5])
    return sorted(names)


def _load(name: str) -> dict[str, Any]:
    ref = resources.files("sldata").joinpath(f"scenarios/{name}.json")
    try:
        with ref.open("r", encoding="utf-8") as fh:
            text = fh.read()
    except (FileNotFoundError, OSError) as exc:
        raise DataError(f"scenario {name!r} is not in the data: {exc}") from exc
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataError(f"scenario {name!r} is not valid JSON: {exc}") from exc
    return data


def run(args: Any) -> int:
    from slcards.card import save_card  # imported here so pygame loads only for this command

    out = Path(args.out)
    if args.all:
        names = _scenario_names()
    else:
        names = [args.scenario]
    for name in names:
        scenario = _load(name)
        path = out / f"card_{scenario.get('id', name)}.png"
        save_card(scenario, path)
        print(f"wrote {path}")
    print(f"{len(names)} card(s) in {out}")
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("cards", help="render a printable scenario card")
    p.add_argument("--scenario", default="s01_guards_counterattack", help="the scenario id")
    p.add_argument("--all", action="store_true", help="render every scenario")
    p.add_argument("--out", default="cards", help="the output directory")
    p.set_defaults(func=run)
