"""The geomorphic edge constants that all four printed boards share (FR-24).

Source: docs/research/2026-09-07_RV-2_boards_scenarios.md section 1.2. These are hex
positions, not art. Any board that satisfies them joins any other board along an edge.

Which hexes a seam touches. RV-2 section 1.2 records half hexes on all four edges. Two
boards that touch along their long edges join their north and south half hexes, which are
the odd-index columns at row 0 and at the last row. Two boards that touch along their short
edges join the whole first column of one to the whole last column of the other, because
those two columns are the half-hex columns of rule 3.7.

So a seam hex has to be the same on every board, and not only the woods half hexes and the
road entries. Each seam hex that no constant names is open ground. That is the smallest
rule that makes any board join any other board, which is what FR-24 asks for.
"""

from __future__ import annotations

from slcore import geometry
from slcore.geometry import HexRef

COLS = 33
ROWS = 10

WOODS_EDGE_COLUMNS = ("F", "H", "J", "L", "V", "X", "Z", "BB")
ROAD_TOP = ("I1", "Q1", "Y1")
ROAD_BOTTOM = ("I10", "Q10", "Y10")
ROAD_WEST = ("A5", "A6")
ROAD_EAST = ("GG5", "GG6")

ROAD_COLUMNS = ("I", "Q", "Y")

# Each seam hex that no other constant names is open ground.
EDGE_KIND = "open"
ROAD_KIND = "road"
WOODS_KIND = "woods"


def woods_half_hexes(cols: int = COLS, rows: int = ROWS) -> tuple[HexRef, ...]:
    out: list[HexRef] = []
    for label in WOODS_EDGE_COLUMNS:
        col = geometry.column_index(label)
        if col >= cols:
            continue
        out.append((col, 0))
        out.append((col, rows))
    return tuple(sorted(out))


def road_edge_hexes(cols: int = COLS, rows: int = ROWS) -> tuple[HexRef, ...]:
    names = list(ROAD_TOP) + list(ROAD_BOTTOM) + list(ROAD_WEST)
    if cols == COLS:
        names += list(ROAD_EAST)
    else:
        last = geometry.column_label(cols - 1)
        names += [f"{last}5", f"{last}6"]
    out = []
    for name in names:
        ref = geometry.parse_hex_id(name)
        if ref[0] < cols and ref[1] <= rows:
            out.append(ref)
    return tuple(sorted(set(out)))


def road_column_indexes(cols: int = COLS) -> tuple[int, ...]:
    return tuple(geometry.column_index(c) for c in ROAD_COLUMNS if geometry.column_index(c) < cols)


def long_edge_hexes(cols: int = COLS, rows: int = ROWS) -> tuple[HexRef, ...]:
    """The half hexes of the north edge and the south edge: the odd columns at row 0 and row `rows`."""
    return tuple(sorted((col, row) for col in range(1, cols, 2) for row in (0, rows)))


def short_edge_hexes(cols: int = COLS, rows: int = ROWS) -> tuple[HexRef, ...]:
    """The half-hex columns of the west edge and the east edge: the first and the last column."""
    out = []
    for col in (0, cols - 1):
        first = 0 if col & 1 else 1
        out.extend((col, row) for row in range(first, rows + 1))
    return tuple(sorted(set(out)))


def seam_hexes(cols: int = COLS, rows: int = ROWS) -> tuple[HexRef, ...]:
    """Each hex that a join can put against a hex of another board."""
    return tuple(sorted(set(long_edge_hexes(cols, rows)) | set(short_edge_hexes(cols, rows))))


def seam_kind(ref: HexRef, cols: int = COLS, rows: int = ROWS) -> str:
    """What a seam hex has to be, as `kind_map` reads it."""
    if ref in set(woods_half_hexes(cols, rows)):
        return WOODS_KIND
    if ref in set(road_edge_hexes(cols, rows)):
        return ROAD_KIND
    return EDGE_KIND


def check_edges(board_hexes: dict[HexRef, str], cols: int = COLS, rows: int = ROWS) -> list[str]:
    """The edge rules that the board does not satisfy, as messages (TC-14a)."""
    problems: list[str] = []
    for ref in seam_hexes(cols, rows):
        wanted = seam_kind(ref, cols, rows)
        found = board_hexes.get(ref)
        if found != wanted:
            problems.append(f"{geometry.hex_id(*ref)} must be {wanted} on a seam, and it is {found}")
    return problems


def kind_map(board) -> dict[HexRef, str]:
    """The board as the map that the edge checks read: a road hex reads as `road`."""
    return {h.ref: ("road" if h.road else h.terrain) for h in board}


def check_join(first: dict[HexRef, str], second: dict[HexRef, str], side: str, cols: int = COLS, rows: int = ROWS) -> list[str]:
    """The join rules that a pair of boards does not satisfy, as messages (TC-14a).

    `side` is where the second board sits: `east` of the first, or `south` of it. A join
    holds when the roads continue across the seam and the half hexes pair into whole
    hexes of the same terrain.
    """
    problems: list[str] = []
    if side == "east":
        # The last column of the first board and the first column of the second are the two
        # halves of one column of hexes, so each row of them has to agree.
        first_last = 0 if (cols - 1) & 1 else 1
        for row in range(first_last, rows + 1):
            left = first.get((cols - 1, row))
            right = second.get((0, row))
            if left != right:
                problems.append(
                    f"row {row} of the seam pairs {left} with {right}, and a pair is one hex"
                )
        return problems
    if side == "south":
        # Only the half hexes pair. An even column of the first board sits next to an even
        # column of the second and stays its own hex.
        for col in range(1, cols, 2):
            top = first.get((col, rows))
            bottom = second.get((col, 0))
            if top != bottom:
                problems.append(
                    f"the half hexes of column {geometry.column_label(col)} pair {top} with {bottom}"
                )
        return problems
    raise ValueError(f"a board joins on the east or the south, and not on {side!r}")
