"""Board composition (FR-29).

A scenario of Game Set II or later plays on two to four boards. The boards touch along
their long edges, which stacks them from north to south, or along their short edges, which
puts them end to end from west to east. A board can be turned one hundred and eighty
degrees before it goes down. RV-2 section 6 records the diagrams that the cards give.

How the boards meet:

- The half hexes of an edge combine with the half hexes of the edge they touch, and the
  pair becomes one whole hex (rule 3.5). So a join costs one row or one column, and two
  boards of 33 by 10 give 65 by 10 side by side, or 33 by 20 stacked.
- The terrain of the two half hexes must agree, because they are now one hex. The edge
  constants of FR-24 make that true for any two generated boards, and `check` says so when
  it is not.

Why the offsets are what they are. The lattice puts the centre of the hex in column c at
x = 3c, and it shifts an odd column down by one unit. So a column offset must be even, or
the columns of the board that moves land with the wrong shift and the board is not a hex
grid any more. The width of a printed board is 33 columns, and the join removes one, so
the offset is 32 and it is even. A row offset has no such rule, because the shift is a
property of the column.

The turn. One hundred and eighty degrees about the centre of the board negates both
lattice coordinates. In the coordinates of a hex that is

    col  ->  cols - 1 - col
    row  ->  rows + 1 - row  for an even column, and rows - row for an odd column

and the two forms are one form on the lattice: `y -> 2 * (rows + 1) - y`. The count of
columns must be odd, so that a turn keeps the shift of each column. A printed board has 33
columns, which is odd.

A hexside feature turns with the board: direction d becomes direction d plus three, and
so does each road hexside of PR-50. Where two half hexes become one hex, the road of that
hex crosses the road hexsides of the two halves. A
polygon turns on the lattice, point by point, so a woods hex keeps the shape it had and
the line of sight through it does not change.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Iterable, Mapping, Sequence

from slcore import geometry
from slcore.geometry import HexRef, Point
from slcore.state import Board, Building, Hex, Polygon, TerrainType

EAST = "east"
SOUTH = "south"
SIDES = (EAST, SOUTH)
HALF_TURN = 3


class CompositionError(Exception):
    """The boards cannot make one playing surface."""


@dataclass(frozen=True)
class Placement:
    """One board of a composition: which board, and whether it is turned."""

    board: Board
    turned: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"board": self.board.name, "turned": self.turned}


def turn(board: Board) -> Board:
    """The board, one hundred and eighty degrees about its centre."""
    if board.cols % 2 == 0:
        raise CompositionError(
            f"a turn needs an odd column count, and {board.name or 'the board'} has {board.cols}"
        )
    dx = geometry.COL_STEP * (board.cols - 1)
    dy = 2 * (board.rows + 1)

    def move(p: Point) -> Point:
        return (dx - p[0], dy - p[1])

    hexes = []
    for h in board:
        col = board.cols - 1 - h.col
        row = board.rows + 1 - h.row - (h.col & 1)
        sides = tuple(h.hexsides[(d + HALF_TURN) % 6] for d in range(6))
        road_sides = tuple(sorted((d + HALF_TURN) % 6 for d in h.road_sides))
        polygons = tuple(Polygon.make(p.kind, [move(v) for v in p.points]) for p in h.polygons)
        hexes.append(
            Hex(
                col=col,
                row=row,
                terrain=h.terrain,
                elevation=h.elevation,
                road=h.road,
                building=h.building,
                hexsides=sides,
                sewer=h.sewer,
                stairs=h.stairs,
                polygons=polygons,
                road_sides=road_sides,
            )
        )
    return Board(board.cols, board.rows, hexes, board.terrain, name=f"{board.name}-turned")


def offsets(placements: Sequence[Placement], side: str) -> list[tuple[int, int]]:
    """Where each board goes on the shared lattice, in columns and rows.

    A join removes the column or the row that the two edges share, so board n starts one
    short of the end of board n minus one.
    """
    if side not in SIDES:
        raise CompositionError(f"boards join on {SIDES}, and not on {side!r}")
    out = [(0, 0)]
    for index in range(1, len(placements)):
        before = placements[index - 1].board
        col, row = out[-1]
        if side == EAST:
            step = before.cols - 1
            if step % 2:
                raise CompositionError(
                    f"a board of {before.cols} columns joins on the east with an odd offset, "
                    "and an odd offset breaks the shift of each column"
                )
            out.append((col + step, row))
        else:
            out.append((col, row + before.rows))
    return out


def size(placements: Sequence[Placement], side: str) -> tuple[int, int]:
    """The columns and the rows of the composition."""
    spots = offsets(placements, side)
    cols = max(spot[0] + p.board.cols for spot, p in zip(spots, placements))
    rows = max(spot[1] + p.board.rows for spot, p in zip(spots, placements))
    return cols, rows


def moved(h: Hex, dcol: int, drow: int, tag: str = "") -> Hex:
    """One hex at its place in the composition, with its polygons on the new lattice.

    `tag` goes in front of the building identity. Two boards each name their buildings B1,
    B2, and so on, and a victory condition names one building, so the identities have to be
    different once the two boards are one surface.
    """
    dx = geometry.COL_STEP * dcol
    dy = 2 * drow
    building = h.building
    if building is not None and tag:
        building = Building(f"{tag}{building.id}", building.kind, building.size)
    return Hex(
        col=h.col + dcol,
        row=h.row + drow,
        terrain=h.terrain,
        elevation=h.elevation,
        road=h.road,
        building=building,
        hexsides=h.hexsides,
        sewer=h.sewer,
        stairs=h.stairs,
        polygons=tuple(Polygon.make(p.kind, [(x + dx, y + dy) for x, y in p.points]) for p in h.polygons),
        road_sides=h.road_sides,
    )


def check_seam(first: Hex, second: Hex) -> list[str]:
    """What two half hexes of a seam disagree about. They are one hex now (rule 3.5)."""
    problems = []
    if first.terrain != second.terrain:
        problems.append(f"{first.id}: terrain {first.terrain} against {second.terrain}")
    if first.road != second.road:
        problems.append(f"{first.id}: road {first.road} against {second.road}")
    if first.elevation != second.elevation:
        problems.append(f"{first.id}: level {first.elevation} against {second.elevation}")
    return problems


def compose(
    placements: Sequence[Placement],
    side: str,
    terrain: Mapping[str, TerrainType] | None = None,
    name: str = "",
) -> Board:
    """One playing surface from two to four boards (FR-29).

    The boards go down in order: west to east for a join on the east, north to south for a
    join on the south. A placement that is turned is turned before it goes down.
    """
    if not 2 <= len(placements) <= 4:
        raise CompositionError(f"a composition is two to four boards, and not {len(placements)}")
    spots = offsets(placements, side)
    cols, rows = size(placements, side)
    named = [p.board.named_road_sides for p in placements]
    # PR-50: a board that names no road hexside reads each pair of adjacent road hexes as
    # joined, but only while no hex of the surface names one. So where the surface mixes
    # the two, the hexes of such a board get that reading written out.
    unnamed: set[HexRef] = set()
    table = dict(terrain or placements[0].board.terrain)
    seen: dict[HexRef, Hex] = {}
    problems: list[str] = []
    ids: dict[str, str] = {}
    for index, (placement, (dcol, drow)) in enumerate(zip(placements, spots), start=1):
        board = turn(placement.board) if placement.turned else placement.board
        if board.rows != placements[0].board.rows and side == EAST:
            raise CompositionError("boards that join on the east must have the same row count")
        tag = f"{index}-"
        for h in board:
            here = moved(h, dcol, drow, tag)
            found = seen.get(here.ref)
            if not placement.board.named_road_sides and any(named):
                unnamed.add(here.ref)
            if found is None:
                seen[here.ref] = here
                ids[here.id] = f"{placement.board.name}:{h.id}"
                continue
            problems.extend(check_seam(found, here))
            if here.road_sides:
                # PR-50: the two half hexes are one hex now, and the road of that hex
                # crosses each hexside that the road of either half crosses.
                seen[here.ref] = replace(found, road_sides=tuple(sorted(set(found.road_sides) | set(here.road_sides))))
    if problems:
        raise CompositionError("the boards do not agree at a seam: " + "; ".join(problems[:6]))
    composed = Board(cols, rows, joined_roads(adjacent_roads(seen, unnamed)), table, name=name or composed_name(placements, side))
    composed.source_ids = ids  # type: ignore[attr-defined]
    return composed


def adjacent_roads(hexes: Mapping[HexRef, Hex], unnamed: set[HexRef]) -> dict[HexRef, Hex]:
    """PR-50: the road hexsides of the hexes of a board that names none.

    Such a board reads each pair of adjacent road hexes as joined. The surface names the
    road hexsides of its other boards, so this writes that reading out: a hexside between
    a road hex of such a board and any adjacent road hex is a road hexside, from both sides.
    """
    if not unnamed:
        return dict(hexes)
    sides: dict[HexRef, set[int]] = {ref: set(h.road_sides) for ref, h in hexes.items()}
    for ref in sorted(unnamed):
        if not hexes[ref].road:
            continue
        for d in range(6):
            other = hexes.get(geometry.neighbor(ref[0], ref[1], d))
            if other is not None and other.road:
                sides[ref].add(d)
                sides[other.ref].add((d + HALF_TURN) % 6)
    return {
        ref: h if sides[ref] == set(h.road_sides) else replace(h, road_sides=tuple(sorted(sides[ref])))
        for ref, h in hexes.items()
    }


def joined_roads(hexes: Mapping[HexRef, Hex]) -> list[Hex]:
    """PR-50: a road hexside on a seam stays only when the road goes on across it.

    A board names the road hexside on its north or south edge where it has a road entry.
    The road continues across the join only when the board on the other side has a road
    entry there too. A board with fewer road columns has no road in that hex, and the road
    then ends at the edge of the first board.
    """
    out = []
    for ref, h in hexes.items():
        kept = tuple(
            d
            for d in h.road_sides
            if (other := hexes.get(geometry.neighbor(ref[0], ref[1], d))) is None
            or (d + HALF_TURN) % 6 in other.road_sides
        )
        out.append(h if kept == h.road_sides else replace(h, road_sides=kept))
    return out


def composed_name(placements: Sequence[Placement], side: str) -> str:
    parts = [p.board.name + ("-turned" if p.turned else "") for p in placements]
    return f"{side}[{'+'.join(parts)}]"


def board_coordinate(board: Board, ref: HexRef) -> str:
    """The coordinate of rule 3.5: the board the hex came from, and its name there.

    A composition keeps its own hex names, because the core reads a hex by its place on
    the lattice. This is the name the player reads, and it is what a scenario card gives.
    """
    ids = getattr(board, "source_ids", None)
    here = geometry.hex_id(*ref)
    if not ids:
        return here
    return ids.get(here, here)
