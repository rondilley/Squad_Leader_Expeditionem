"""`sl-cli launch`: the launcher of the packaged game (`slwindow.launcher`).

The packaged program starts it when it has no arguments (`slcli.frozen_main`). It asks for
the consent at the first start, and it starts each game window as a second process.
"""

from __future__ import annotations

from typing import Any


def run(args: Any) -> int:
    from slcli.window_cmd import load_window

    load_window()  # the typed error of a missing pygame
    from slwindow.launcher import Launcher

    return Launcher().run()


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("launch", help="the game launcher: the choice of a game, and the consent to send the played games")
    p.set_defaults(func=run)
