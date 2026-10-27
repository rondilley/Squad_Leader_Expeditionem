"""The entry point of the packaged program (`tools/package.py`).

With no arguments the program is the launcher. With arguments it is `sl-cli`, so the
launcher starts each game window as `<program> window3d --scenario ...`.

A packaged program for Windows has no console, so `sys.stdout` and `sys.stderr` are None,
and a write to them would stop the game. They go to `logs/<command>.log` in the data
directory of the player.
"""

from __future__ import annotations

import multiprocessing
import sys


def _redirect(command: str) -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    from slcollect.settings import data_dir

    folder = data_dir() / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    handle = open(folder / f"{command}.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115 - open for the life of the process
    if sys.stdout is None:
        sys.stdout = handle
    if sys.stderr is None:
        sys.stderr = handle


def main() -> int:
    multiprocessing.freeze_support()
    argv = sys.argv[1:] or ["launch"]
    _redirect(argv[0])
    from slcli.main import main as cli_main

    return cli_main(argv)


if __name__ == "__main__":
    sys.exit(main())
