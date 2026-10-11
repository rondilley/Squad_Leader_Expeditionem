"""Save a game on the host and resume it later.

A game is its seed, its switches, and its command log (CLAUDE.md, DR-04). So a save file
holds the scenario, the board, the seed, the computer opponents, and the command log of
the host: each command's ID, its canonical payload, and the state hash after it. Resume
builds a new game from the seed and plays the log again through the core, one legal
command at a time, and it compares each hash. A hash that does not agree is a replay
defect, and resume stops with the command number; it does not give a game that is not the
saved one.

The file is JSON. It holds no view and no state, so it holds nothing that a player could
read to see the other side's hidden units that the log does not already name. A save file
is for the person who owns the host; it is not a public replay (SR-09 covers those).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

SAVE_FORMAT = "sl-save-1"


class SaveError(Exception):
    """A save file that cannot be written, read, or played again."""


def save_document(host: Any, scenario: str, board: str | None, seed: int, opponents: dict[int, str]) -> dict[str, Any]:
    """The save document of a running host."""
    return {
        "format": SAVE_FORMAT,
        "scenario": scenario,
        "board": board,
        "seed": int(seed),
        "opponents": {str(seat): name for seat, name in sorted(opponents.items())},
        "commands": [
            {"command_id": c["command_id"], "payload": c["payload"], "hash": c["hash"]}
            for c in host.game.commands
        ],
        "game_over": bool(host.game.state.game_over),
    }


def write_save(path: Path, document: dict[str, Any]) -> Path:
    """Write the document to a temporary file and move it over the old one, so a crash in
    the middle of a write does not leave half a save."""
    path = Path(path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        partial.write_text(json.dumps(document, separators=(",", ":")), encoding="utf-8")
        os.replace(partial, path)
    except OSError as exc:
        raise SaveError(f"cannot write the save file {path}: {exc}") from exc
    return path


def read_save(path: Path) -> dict[str, Any]:
    path = Path(path)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SaveError(f"cannot read the save file {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise SaveError(f"the save file {path} is not JSON: {exc}") from exc
    if not isinstance(document, dict) or document.get("format") != SAVE_FORMAT:
        raise SaveError(f"the save file {path} is not in the format {SAVE_FORMAT}")
    for key in ("scenario", "seed", "commands"):
        if key not in document:
            raise SaveError(f"the save file {path} has no {key!r}")
    return document


def replay_into(host: Any, document: dict[str, Any]) -> int:
    """Play the saved command log again on a new host, and check each hash.

    The host must be new: built from the same scenario, board, and seed, with no command
    applied. Return the number of commands played.
    """
    game = host.game
    if game.commands:
        raise SaveError("resume needs a new game, and this host already applied commands")
    for number, entry in enumerate(document["commands"], start=1):
        if game.state.game_over:
            raise SaveError(f"the game ended before saved command {number}")
        frame = game.engine.legal_commands(game.state)
        legal = frame.by_id(str(entry["command_id"]))
        if legal is None:
            raise SaveError(
                f"saved command {number} ({entry.get('payload')}) is not legal in the game the seed builds"
            )
        game.apply(frame.frame_id, legal.id)
        expected = entry.get("hash")
        actual = game.commands[-1]["hash"]
        if expected is not None and actual != expected:
            raise SaveError(f"the state hash after saved command {number} does not agree; the replay is a defect")
    return len(document["commands"])
