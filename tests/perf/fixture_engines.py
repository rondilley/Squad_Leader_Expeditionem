"""Engines on the board documents that `tests/perf/boards/` holds.

The recorded digests of the speed tests are of games on fixed boards. The board
generator of `slboards` changes in its own work, and a new generator version gives a new
board for the same scenario. So these tests read each board from its document and not
from the generator, and a change of the generator does not move a digest of the core.
"""

from __future__ import annotations

import json
from pathlib import Path

from slcore.engine import Engine
from slcore.state import Board
from sldata.loaders import load_all_counters, load_hexsides, load_scenario, load_tables, load_terrain

BOARDS = Path(__file__).parent / "boards"


def fixture_engine(scenario: str) -> Engine:
    terrain = load_terrain()
    document = json.loads((BOARDS / f"{scenario}.json").read_text(encoding="utf-8"))
    board = Board.from_dict(document, terrain)
    return Engine(load_scenario(scenario), board, terrain, load_hexsides(), load_all_counters(), load_tables())
