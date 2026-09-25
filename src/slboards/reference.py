"""The reference-mode loader (FR-27, DR-06, SR-07).

The four printed board layouts are a creative selection, and the project does not ship
them. A layout that the owner transcribed lives in `background/reference/`, which
`.gitignore` lists, so git does not record it. This module reads from there and from
nowhere else.

Three guards keep the layouts out of the build:

- The loader refuses a path that is not inside the reference directory.
- A board it loads carries `board_source = "reference_private"`, which the trace writer
  and the fine-tune guard read (SR-10).
- The default test run does not call this module. `tests/boards/test_reference.py`
  checks that the guard works and skips when the directory is absent.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Mapping

from slcore.state import Board, TerrainType

REFERENCE_ROOT = Path("background") / "reference"
LAYOUT_DIRECTORY = "layouts"
SOURCE_GENERATED = "generated"
SOURCE_REFERENCE = "reference_private"
ENVIRONMENT_OVERRIDE = "SQUAD_LEADER_REFERENCE_ROOT"
NAME_PREFIX = "reference-"


class ReferenceUnavailable(Exception):
    """The reference material is not on this machine, or the path is not allowed."""


def reference_root() -> Path:
    """The directory the loader reads. The environment variable moves it for the owner."""
    override = os.environ.get(ENVIRONMENT_OVERRIDE)
    return Path(override) if override else REFERENCE_ROOT


def available() -> bool:
    return (reference_root() / LAYOUT_DIRECTORY).is_dir()


def layout_path(name: str) -> Path:
    """The path of one layout, checked to be a file inside the layouts directory.

    A name that climbs out of that directory can sit next to it and still be inside
    the reference root. The check is the layouts directory, not the root.
    """
    if name != Path(name).name or name in (".", ".."):
        raise ReferenceUnavailable(f"the layout name {name!r} points outside the layouts directory")
    root = reference_root().resolve()
    layout_dir = (root / LAYOUT_DIRECTORY).resolve()
    target = (layout_dir / f"{name}.json").resolve()
    try:
        target.relative_to(layout_dir)
    except ValueError as exc:
        raise ReferenceUnavailable(f"the layout name {name!r} points outside the layouts directory") from exc
    return target


def load_layout(name: str, terrain: Mapping[str, TerrainType]) -> tuple[Board, dict[str, Any]]:
    """One printed layout as a board, with a record that marks it private.

    The record travels with the board so that a trace from a reference-mode game carries
    `board_source = "reference_private"` (SR-10).
    """
    if not available():
        raise ReferenceUnavailable(
            f"no reference layouts on this machine. Put them in {reference_root() / LAYOUT_DIRECTORY}, "
            f"which git does not record, or play in generated mode."
        )
    path = layout_path(name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReferenceUnavailable(f"the reference layout {name!r} is not in {path.parent}") from exc
    except OSError as exc:
        raise ReferenceUnavailable(f"cannot read the reference layout {name!r}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ReferenceUnavailable(f"the reference layout {name!r} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ReferenceUnavailable(f"the reference layout {name!r} is not a board record")
    payload = dict(data)
    payload["name"] = f"{NAME_PREFIX}{name}"
    # The data loader holds the closed key set of a board. It imports this package, so the
    # import is here and not at the top.
    from sldata.loaders import BOARD_KEYS, DataKeyError, check_keys

    try:
        check_keys(payload, BOARD_KEYS, f"the reference layout {name!r}")
        board = Board.from_dict(payload, terrain)
    except DataKeyError as exc:
        raise ReferenceUnavailable(f"the reference layout {name!r} has a key this build does not read: {exc}") from exc
    except (KeyError, TypeError, ValueError) as exc:
        raise ReferenceUnavailable(f"the reference layout {name!r} is not a board this build reads: {exc}") from exc
    return board, {"board_source": SOURCE_REFERENCE, "layout": name}


def source_of(board: Board) -> str:
    """The tag a trace record carries for this board (SR-10, DR-08)."""
    return SOURCE_REFERENCE if board.name.startswith(NAME_PREFIX) else SOURCE_GENERATED
