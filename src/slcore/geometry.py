"""Hex geometry on the exact lattice.

A lattice point is a pair of integers (x, y). The real coordinates are
(x, y * sqrt(3)). Every hex center and every hex vertex is a lattice point,
so a cross product of two lattice vectors is an integer times sqrt(3) and its
sign is exact. No float is used in this module (NFR-05).

The board (rule 3) has columns of flat-topped hexes. Columns are lettered
A to GG along the long edge, rows are numbered along the short edge. A hex
has side 2 units. Column c has its centers at x = 3 * c. Odd-index columns
(B, D, F, ...) are shifted down by half a hex, so their rows run 0 to `rows`
with half hexes at row 0 and row `rows` (the VASL names F0, F10, ...). Even-
index columns (A, C, E, ...) have rows 1 to `rows`. Column A and the last
column are half-hex columns on the left and right edges (rule 3.7).

Design source: docs/ARCHITECTURE.md section 5 and RV-2 section 1.2.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from typing import Iterable, Sequence

Point = tuple[int, int]
HexRef = tuple[int, int]

COL_STEP = 3
HEX_SIDE = 2

# Vertex offsets from a hex center, in the order that gives a positive
# signed area (counter-clockwise in the mathematical sense).
VERTEX_OFFSETS: tuple[Point, ...] = ((2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1), (1, -1))

# Direction index to neighbor center offset. 0 is north (row - 1), then
# clockwise on a screen where y grows downward: 1 northeast, 2 southeast,
# 3 south, 4 southwest, 5 northwest.
DIRECTIONS: tuple[Point, ...] = ((0, -2), (3, -1), (3, 1), (0, 2), (-3, 1), (-3, -1))

# The two vertices (as offsets) that bound the hexside in each direction.
HEXSIDE_VERTICES: tuple[tuple[Point, Point], ...] = (
    ((-1, -1), (1, -1)),
    ((1, -1), (2, 0)),
    ((2, 0), (1, 1)),
    ((1, 1), (-1, 1)),
    ((-1, 1), (-2, 0)),
    ((-2, 0), (-1, -1)),
)


LETTERS = 26


def column_label(col: int) -> str:
    """0 -> A, 25 -> Z, 26 -> AA, 32 -> GG, 52 -> AAA.

    The 1977 board has 33 columns and stops at GG, so one board never needs more than two
    letters. A composition of two to four boards (FR-29) is wider than that, and it goes on
    with the same rule: the letter is the index inside the block of twenty-six, and the
    count of letters is the block number.
    """
    if col < 0:
        raise ValueError(f"column index must be non-negative, got {col}")
    return chr(65 + col % LETTERS) * (1 + col // LETTERS)


def column_index(label: str) -> int:
    """A -> 0, Z -> 25, AA -> 26, GG -> 32, AAA -> 52."""
    if not label or not all("A" <= c <= "Z" for c in label) or any(c != label[0] for c in label):
        raise ValueError(f"not a column label: {label!r}")
    return LETTERS * (len(label) - 1) + ord(label[0]) - 65


def hex_id(col: int, row: int) -> str:
    return f"{column_label(col)}{row}"


def parse_hex_id(text: str) -> HexRef:
    letters = text.rstrip("0123456789")
    digits = text[len(letters):]
    if not letters or not digits:
        raise ValueError(f"not a hex id: {text!r}")
    return column_index(letters), int(digits)


@lru_cache(maxsize=1 << 14)
def center(col: int, row: int) -> Point:
    return (COL_STEP * col, 2 * row + (col & 1))


def hex_from_center(x: int, y: int) -> HexRef | None:
    """The hex whose center is the lattice point, or None."""
    if x % COL_STEP:
        return None
    col = x // COL_STEP
    y2 = y - (col & 1)
    if y2 % 2:
        return None
    return (col, y2 // 2)


def vertices(col: int, row: int) -> tuple[Point, ...]:
    cx, cy = center(col, row)
    return tuple((cx + dx, cy + dy) for dx, dy in VERTEX_OFFSETS)


def neighbor(col: int, row: int, direction: int) -> HexRef:
    cx, cy = center(col, row)
    dx, dy = DIRECTIONS[direction]
    found = hex_from_center(cx + dx, cy + dy)
    if found is None:
        raise ValueError(f"no hex in direction {direction} from {hex_id(col, row)}")
    return found


def neighbors(col: int, row: int) -> tuple[HexRef, ...]:
    """The six neighbors in direction order. The caller filters by the board."""
    return tuple(neighbor(col, row, d) for d in range(6))


def direction_to(a: HexRef, b: HexRef) -> int | None:
    """The direction index from a to b when the two are adjacent, else None."""
    ax, ay = center(*a)
    bx, by = center(*b)
    delta = (bx - ax, by - ay)
    for d, offset in enumerate(DIRECTIONS):
        if offset == delta:
            return d
    return None


def distance(a: HexRef, b: HexRef) -> int:
    """Hex distance (rule 5, range in hexes)."""
    ax, ay = center(*a)
    bx, by = center(*b)
    dcol = abs(bx - ax) // COL_STEP
    dy = abs(by - ay)
    if dy <= dcol:
        return dcol
    return dcol + (dy - dcol) // 2


def cross(ax: int, ay: int, bx: int, by: int) -> int:
    """The integer part of the cross product of two lattice vectors."""
    return ax * by - ay * bx


def signed_area2(points: Sequence[Point]) -> int:
    """Twice the signed area of a polygon, in lattice units."""
    total = 0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]
        total += x1 * y2 - x2 * y1
    return total


def normalize_polygon(points: Iterable[Point]) -> tuple[Point, ...]:
    """Give the polygon with positive orientation. Reject degenerate or non-convex input."""
    pts = tuple((int(x), int(y)) for x, y in points)
    if len(pts) < 3:
        raise ValueError("a polygon needs three or more points")
    area = signed_area2(pts)
    if area == 0:
        raise ValueError("degenerate polygon")
    if area < 0:
        pts = tuple(reversed(pts))
    n = len(pts)
    for i in range(n):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % n]
        x2, y2 = pts[(i + 2) % n]
        if cross(x1 - x0, y1 - y0, x2 - x1, y2 - y1) < 0:
            raise ValueError("polygon is not convex")
    return pts


def hex_polygon(col: int, row: int) -> tuple[Point, ...]:
    return vertices(col, row)


@dataclass(frozen=True)
class Clip:
    """The parameter interval where a segment meets a convex polygon.

    t0 and t1 are parameters along the segment from p (t=0) to q (t=1).
    collinear_edge is the index of a polygon edge that the segment's line
    contains, or None.
    """

    t0: Fraction
    t1: Fraction
    collinear_edge: int | None

    @property
    def length_positive(self) -> bool:
        return self.t1 > self.t0


def clip_segment(p: Point, q: Point, polygon: Sequence[Point]) -> Clip | None:
    """Cyrus-Beck clip of the segment p-q against a convex polygon with positive orientation.

    Gives None when the segment does not meet the closed polygon. Gives a Clip with
    t0 == t1 when the segment touches the polygon at one point only.

    The parameters stay as integer pairs inside the loop and become fractions one time
    at the end, because a fraction object for each edge costs more than the clip itself.
    """
    dx = q[0] - p[0]
    dy = q[1] - p[1]
    low_num, low_den = 0, 1
    high_num, high_den = 1, 1
    collinear: int | None = None
    n = len(polygon)
    for i in range(n):
        vx, vy = polygon[i]
        wx, wy = polygon[(i + 1) % n]
        ex = wx - vx
        ey = wy - vy
        a = ex * (p[1] - vy) - ey * (p[0] - vx)
        b = ex * dy - ey * dx
        if b == 0:
            if a < 0:
                return None
            if a == 0:
                collinear = i
            continue
        num, den = -a, b
        if den < 0:
            num, den = -num, -den
        if b > 0:
            if num * low_den > low_num * den:
                low_num, low_den = num, den
        elif num * high_den < high_num * den:
            high_num, high_den = num, den
    if low_num * high_den > high_num * low_den:
        return None
    return Clip(Fraction(low_num, low_den), Fraction(high_num, high_den), collinear)


class Crossing:
    """How a segment relates to a convex polygon."""

    NONE = "none"
    INTERIOR = "interior"
    EDGE = "edge"


def classify_crossing(p: Point, q: Point, polygon: Sequence[Point]) -> tuple[str, Clip | None]:
    clip = clip_segment(p, q, polygon)
    if clip is None or not clip.length_positive:
        return Crossing.NONE, clip
    if clip.collinear_edge is not None:
        return Crossing.EDGE, clip
    return Crossing.INTERIOR, clip


def line_y_at(p: Point, q: Point, x: int) -> Fraction:
    """The y of the line p-q at x. The line must not be vertical."""
    dx = q[0] - p[0]
    if dx == 0:
        raise ValueError("vertical line")
    return Fraction(p[1]) + Fraction((x - p[0]) * (q[1] - p[1]), dx)
