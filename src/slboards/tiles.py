"""The tile set and the adjacency rules for the fill pass (ARCHITECTURE section 7, pass 3).

A tile is a terrain kind with a weight and a set of kinds it may sit next to. The rules
are written by hand and they are small, because the board type gives the large features
in pass 2 and the fill pass only closes the gaps.

Source of the look: docs/research/2026-09-07_RV-2_boards_scenarios.md section 1.4, which
records the terrain of each printed board from the scans.
"""

from __future__ import annotations

from dataclasses import dataclass

OPEN = "open"
WOODS = "woods"
WHEAT = "wheat"
SHELLHOLE = "shellhole"
STONE = "stone_building"
WOODEN = "wooden_building"


@dataclass(frozen=True)
class Tile:
    kind: str
    weight: int
    neighbors: frozenset[str]


BOARD_TYPES = ("city", "hills", "village", "rural")

# A wheatfield on a city board is a small patch, so it touches open ground only and cannot
# spread. On the country boards a field runs up to the woods and the shell holes, and that
# is what makes the large fields of rule 44.2.
FIELD_NEIGHBOURS = {
    "city": frozenset({OPEN, WHEAT}),
    "village": frozenset({OPEN, WHEAT}),
    "hills": frozenset({OPEN, WHEAT, WOODS}),
    "rural": frozenset({OPEN, WHEAT, WOODS, SHELLHOLE}),
}

DEFAULT_WEIGHTS = {"woods": 12, "grain": 4, "shellholes": 16}


def tile_set(board_type: str, weights: dict[str, int] | None = None) -> dict[str, Tile]:
    """The tiles of one board type. A kind that is not in the set never appears.

    The weights come from the style record of the board (FR-26), so two boards of the same
    type with different styles have the same adjacency rules and a different mix.
    """
    if board_type not in BOARD_TYPES:
        raise NotImplementedError(f"the tile set for the board type {board_type!r} waits for its own work")
    w = dict(DEFAULT_WEIGHTS)
    w.update(weights or {})
    field = FIELD_NEIGHBOURS[board_type]
    ground = frozenset({OPEN, WOODS, SHELLHOLE, STONE, WOODEN})
    with_field = ground | {WHEAT} if WHEAT in field else ground
    return {
        OPEN: Tile(OPEN, 62, ground | {WHEAT}),
        WOODS: Tile(WOODS, w["woods"], with_field if WOODS in field else ground),
        SHELLHOLE: Tile(SHELLHOLE, w["shellholes"], with_field if SHELLHOLE in field else ground),
        WHEAT: Tile(WHEAT, w["grain"], field),
        STONE: Tile(STONE, 0, ground | {WHEAT}),
        WOODEN: Tile(WOODEN, 0, ground | {WHEAT}),
    }


def allowed(tiles: dict[str, Tile], kind: str, other: str) -> bool:
    """The adjacency rule is symmetric: two kinds may touch when each allows the other."""
    a = tiles.get(kind)
    b = tiles.get(other)
    if a is None or b is None:
        return True
    return other in a.neighbors and kind in b.neighbors


def fillable(tiles: dict[str, Tile]) -> tuple[str, ...]:
    """The kinds the fill pass may place. A weight of zero belongs to pass 2."""
    return tuple(sorted(k for k, t in tiles.items() if t.weight > 0))
