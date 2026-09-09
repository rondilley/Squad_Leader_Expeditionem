"""The static per-board thread table (FR-28, ARCHITECTURE section 5).

For each unordered pair of hexes the table holds the thread: the sequence of
hexes that the center-to-center segment goes through, with the terrain
polygons it crosses in each. Where the segment runs along a hexside, the step
holds the two adjoining hexes, and the rule evaluator applies the firer's
choice of rule 17.7 at play time.

The table is symmetric. It is built lazily and memoized, and `build_all`
fills it for a whole board.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import ceil, floor

from slcore import geometry
from slcore.geometry import Crossing, HexRef
from slcore.state import Board


@dataclass(frozen=True)
class Step:
    """One position along a thread.

    hexes has one hex when the segment goes through its interior. It has two
    hexes when the segment runs along the hexside between them (rule 17.7),
    or one hex when that hexside is on the board edge. kinds[i] holds the
    terrain kinds of the polygons in hexes[i] that the segment crosses.
    """

    hexes: tuple[HexRef, ...]
    kinds: tuple[frozenset[str], ...]

    @property
    def choice(self) -> bool:
        return len(self.hexes) > 1


@dataclass(frozen=True)
class Thread:
    firer: HexRef
    target: HexRef
    steps: tuple[Step, ...]

    def reversed(self) -> "Thread":
        return Thread(self.target, self.firer, tuple(reversed(self.steps)))

    def hexes(self) -> tuple[HexRef, ...]:
        out: list[HexRef] = []
        for s in self.steps:
            out.extend(s.hexes)
        return tuple(out)


class LosTable:
    def __init__(self, board: Board) -> None:
        self.board = board
        self._cache: dict[tuple[HexRef, HexRef], Thread] = {}
        self._rays: dict[tuple[HexRef, HexRef], tuple[HexRef, ...]] = {}
        self.static_results: dict[tuple[HexRef, HexRef], object] = {}

    def thread(self, firer: HexRef, target: HexRef) -> Thread:
        if firer not in self.board or target not in self.board:
            raise KeyError(f"hex not on board: {firer} or {target}")
        if firer == target:
            return Thread(firer, target, ())
        key = (firer, target) if firer <= target else (target, firer)
        found = self._cache.get(key)
        if found is None:
            found = build_thread(self.board, key[0], key[1])
            self._cache[key] = found
        return found if key[0] == firer else found.reversed()

    def ray(self, firer: HexRef, target: HexRef) -> tuple[HexRef, ...]:
        """The hexes beyond the target on the same line, in sequence (rules 17.5 and 17.6).

        Where the line runs along a hexside, the ray gives the hex with the lower
        reference. Rule 17.7 gives the firer the choice, and the core does not offer
        it beyond the target hex. The lesson file records this.
        """
        key = (firer, target)
        found = self._rays.get(key)
        if found is None:
            found = build_ray(self.board, firer, target)
            self._rays[key] = found
        return found

    def build_all(self) -> int:
        refs = self.board.order
        for i, a in enumerate(refs):
            for b in refs[i + 1:]:
                self.thread(a, b)
        return len(self._cache)

    def __len__(self) -> int:
        return len(self._cache)


def _crossed_kinds(board: Board, ref: HexRef, p: geometry.Point, q: geometry.Point, mode: str) -> frozenset[str]:
    """The terrain kinds the segment crosses in the hex.

    mode INTERIOR: a polygon counts when the segment goes through its interior.
    mode EDGE: the segment runs along the hexside of this hex, so a polygon
    counts when it has an edge along that hexside with positive overlap
    (rule 7.1: the obstacle is then on that side of the string).
    """
    kinds: set[str] = set()
    for poly in board.hex(ref).polygons:
        crossing, _ = geometry.classify_crossing(p, q, poly.points)
        if crossing == mode:
            kinds.add(poly.kind)
    return frozenset(kinds)


def build_thread(board: Board, firer: HexRef, target: HexRef) -> Thread:
    p = geometry.center(*firer)
    q = geometry.center(*target)
    dx = q[0] - p[0]
    entries: list[tuple[Fraction, Fraction, str, HexRef]] = []
    col_lo = min(firer[0], target[0])
    col_hi = max(firer[0], target[0])
    x_lo = min(p[0], q[0])
    x_hi = max(p[0], q[0])
    for col in range(col_lo, col_hi + 1):
        span_lo = max(geometry.COL_STEP * col - 2, x_lo)
        span_hi = min(geometry.COL_STEP * col + 2, x_hi)
        if span_lo > span_hi:
            continue
        if dx == 0:
            y_lo = Fraction(min(p[1], q[1]))
            y_hi = Fraction(max(p[1], q[1]))
        else:
            ya = geometry.line_y_at(p, q, span_lo)
            yb = geometry.line_y_at(p, q, span_hi)
            y_lo = min(ya, yb)
            y_hi = max(ya, yb)
        parity = col & 1
        row_lo = ceil((y_lo - 1 - parity) / 2)
        row_hi = floor((y_hi + 1 - parity) / 2)
        for row in range(row_lo, row_hi + 1):
            ref = (col, row)
            if ref == firer or ref == target or ref not in board:
                continue
            crossing, clip = geometry.classify_crossing(p, q, geometry.hex_polygon(col, row))
            if crossing == Crossing.NONE or clip is None:
                continue
            entries.append((clip.t0, clip.t1, crossing, ref))
    entries.sort(key=lambda e: (e[0], e[1], e[3]))
    steps: list[Step] = []
    i = 0
    while i < len(entries):
        t0, t1, crossing, ref = entries[i]
        if crossing == Crossing.INTERIOR:
            steps.append(Step((ref,), (_crossed_kinds(board, ref, p, q, Crossing.INTERIOR),)))
            i += 1
            continue
        group = [ref]
        j = i + 1
        while j < len(entries) and entries[j][0] == t0 and entries[j][1] == t1 and entries[j][2] == Crossing.EDGE:
            group.append(entries[j][3])
            j += 1
        group.sort()
        steps.append(
            Step(
                tuple(group),
                tuple(_crossed_kinds(board, g, p, q, Crossing.EDGE) for g in group),
            )
        )
        i = j
    return Thread(firer, target, tuple(steps))


def build_ray(board: Board, firer: HexRef, target: HexRef) -> tuple[HexRef, ...]:
    """The board hexes that the line from firer through target meets after the target."""
    p = geometry.center(*firer)
    q = geometry.center(*target)
    dx = q[0] - p[0]
    dy = q[1] - p[1]
    far = (p[0] + dx * 200, p[1] + dy * 200)
    found: list[tuple[Fraction, HexRef]] = []
    for ref in board.order:
        if ref in (firer, target):
            continue
        crossing, clip = geometry.classify_crossing(p, far, geometry.hex_polygon(*ref))
        if crossing == Crossing.NONE or clip is None or not clip.length_positive:
            continue
        if clip.t0 * 200 <= 1:
            continue
        found.append((clip.t0, ref))
    found.sort()
    out: list[HexRef] = []
    seen_t: Fraction | None = None
    for t0, ref in found:
        if seen_t is not None and t0 == seen_t:
            continue
        seen_t = t0
        out.append(ref)
    return tuple(out)
