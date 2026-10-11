"""A guard for the Panda3D tests: they do not run while a live 3D game window is open.

Each test here makes an offscreen Panda3D window. A second OpenGL process on the display of a
live `sl-cli window3d` crashed that window before (2026-09-10), and a session ran these tests
beside the owner's open game twice on 2026-10-10. So the session stops with a message when it
finds that process. The check reads `/proc`; a system with no `/proc` is not checked.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest


def _live_windows() -> list[str]:
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    found = []
    me = os.getpid()
    for entry in proc.iterdir():
        if not entry.name.isdigit() or int(entry.name) == me:
            continue
        try:
            args = (entry / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        words = [a.decode("utf-8", "replace") for a in args if a]
        if any(w.endswith("sl-cli") for w in words) and "window3d" in words and "--screenshot" not in words:
            found.append(entry.name)
    return found


@pytest.fixture(scope="session", autouse=True)
def no_live_game_window():
    live = _live_windows()
    if live:
        pytest.exit(
            f"a live `sl-cli window3d` is open (process {', '.join(live)}); close it before the "
            "Panda3D tests, because a second OpenGL process on its display can crash it",
            returncode=3,
        )
    yield
