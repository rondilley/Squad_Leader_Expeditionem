"""The save file of a host game, and the resume (slice 4).

A game is its seed, its switches, and its command log. The host writes one JSON line for
the game and one line for each command it applies, as it applies it, to
`runs/games/<game_id>.jsonl`. So a host that stops leaves a file that holds the game up to
its last command.

The first line is the header: the format, the seed, the scenario, the switches, the board
parameters, and the seats of the computer opponents. Each other line is one command: its
canonical payload, its command ID, the player that sent it, and the state hash after it.
The host writes the hash to its own disk and never to a client (S1).

`sl-cli host --resume FILE` reads the file, applies each payload to a new game with the
same seed, and compares each hash. A hash that is not the same is a defect, and the
resume stops with `SaveFileError`.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

FORMAT = "sl-host-game"
VERSION = 1
DEFAULT_DIRECTORY = Path("runs") / "games"


class SaveFileError(Exception):
    """A save file cannot be read, or its commands do not give the recorded hashes."""


@dataclass
class SaveFile:
    """The file of one game. Each write goes to the disk before the host goes on."""

    path: Path
    header: dict[str, Any]
    lines: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def create(cls, directory: Path, header: dict[str, Any]) -> "SaveFile":
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{header['game_id']}.jsonl"
        record = cls(path, {"format": FORMAT, "version": VERSION, **header})
        record.rewrite([])
        return record

    def append(self, line: dict[str, Any]) -> None:
        self.lines.append(line)
        try:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
        except OSError as exc:
            raise SaveFileError(f"cannot write the save file {self.path}: {exc}") from exc

    def rewrite(self, lines: list[dict[str, Any]]) -> None:
        """Write the file again with these command lines. An undo uses this."""
        self.lines = list(lines)
        text = json.dumps(self.header, sort_keys=True, separators=(",", ":")) + "\n"
        text += "".join(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n" for line in self.lines)
        temporary = self.path.with_suffix(".jsonl.tmp")
        try:
            temporary.write_text(text, encoding="utf-8")
            os.replace(temporary, self.path)
        except OSError as exc:
            raise SaveFileError(f"cannot write the save file {self.path}: {exc}") from exc


def load(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The header and the command lines of a save file. Every error is typed."""
    source = Path(path)
    try:
        text = source.read_text(encoding="utf-8")
    except OSError as exc:
        raise SaveFileError(f"cannot read the save file {source}: {exc}") from exc
    rows = [row for row in text.splitlines() if row.strip()]
    if not rows:
        raise SaveFileError(f"the save file {source} is empty")
    try:
        parsed = [json.loads(row) for row in rows]
    except json.JSONDecodeError as exc:
        raise SaveFileError(f"the save file {source} has a line that is not JSON: {exc}") from exc
    return check_lines(parsed, f"the save file {source}")


def check_lines(parsed: list[Any], label: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """The header and the command lines of parsed save file lines. Every error is typed.

    `load` reads a file with it, and the collector (`slcollect.verify`) reads an upload.
    """
    if not parsed:
        raise SaveFileError(f"{label} is empty")
    header = parsed[0]
    if not isinstance(header, dict) or header.get("format") != FORMAT:
        raise SaveFileError(f"{label} does not start with a {FORMAT} header")
    if header.get("version") != VERSION:
        raise SaveFileError(f"{label} has version {header.get('version')}, and this host reads {VERSION}")
    for key in ("seed", "scenario", "game_id"):
        if key not in header:
            raise SaveFileError(f"the header of {label} has no {key}")
    lines = parsed[1:]
    for index, line in enumerate(lines, start=1):
        if not isinstance(line, dict) or not isinstance(line.get("payload"), dict) or not isinstance(line.get("hash"), str):
            raise SaveFileError(f"line {index + 1} of {label} is not a command line")
    return header, lines
