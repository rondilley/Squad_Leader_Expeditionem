"""Rule 7, basic line of sight, plus the LOS parts of rules 11.5 and 17.7.

The functions here take a traced thread: the hexes the segment goes through
after the firer's hexside choices are applied, each with the terrain kinds
the segment crosses in it. The static geometry lives in `los_cache`, and the
choice logic lives in `los_eval`.

Rule readings that the text leaves open are listed in tasks/lessons.md.
"""

from __future__ import annotations

from dataclasses import dataclass

from slcore.geometry import HexRef, direction_to
from slcore.rules import r43_elevation
from slcore.state import LOS_BLOCK, LOS_HINDER, Board

RULE_7_2 = "7.2"
RULE_7_3 = "7.3"
RULE_7_4 = "7.4"
RULE_7_5 = "7.5"
RULE_7_6 = "7.6"
RULE_7_7 = "7.7"
RULE_7_8 = "7.8"
RULE_11_51 = "11.51"
RULE_17_7 = "17.7"

HEXSIDE_BLOCKERS = frozenset({"wall", "hedge"})


@dataclass(frozen=True)
class TracedHex:
    ref: HexRef
    kinds: frozenset[str]


@dataclass(frozen=True)
class LosVerdict:
    clear: bool
    rule_id: str
    blocking_hex: HexRef | None = None
    blocking_hexside: tuple[HexRef, int] | None = None


def rule_7_8_adjacent(board: Board, firer: HexRef, target: HexRef) -> bool:
    """Rule 7.8: units may always fire into an adjacent hex."""
    return board.adjacent(firer, target)


def rule_7_4_multi_story(board: Board, ref: HexRef) -> bool:
    """Rule 7.4: a building of three or more hexes is a multi-story structure."""
    b = board.hex(ref).building
    return b is not None and b.multi_story


def crossed_obstacle(board: Board, kinds: frozenset[str]) -> bool:
    """Rule 7.2: a woods or building symbol that the segment goes through."""
    return any(board.los_class(k) == LOS_BLOCK for k in kinds)


def crossed_building(board: Board, kinds: frozenset[str]) -> bool:
    return any(board.is_building_kind(k) for k in kinds)


def crossed_multi_story_building(board: Board, ref: HexRef, kinds: frozenset[str]) -> bool:
    """Rule 7.5: a multi-story building symbol that the segment goes through."""
    return crossed_building(board, kinds) and rule_7_4_multi_story(board, ref)


def hindrance_count(board: Board, traced: list[TracedHex]) -> int:
    count = 0
    for t in traced:
        if any(board.los_class(k) == LOS_HINDER for k in t.kinds):
            count += 1
    return count


def rule_11_51_hexside_block(
    board: Board,
    firer: HexRef,
    target: HexRef,
    path: list[HexRef],
    height_advantage: bool,
) -> tuple[HexRef, int] | None:
    """Rule 11.51: a wall or hedge hexside stops the LOS unless the LOS ends or
    originates in the hex the hexside forms, or a height advantage exists.

    path is firer, the traced hexes, target. Gives the hexside (hex, direction)
    that stops the LOS, or None.
    """
    if height_advantage:
        return None
    for i in range(len(path) - 1):
        a = path[i]
        b = path[i + 1]
        d = direction_to(a, b)
        if d is None:
            continue
        feature = board.hexside(a, d)
        if feature in HEXSIDE_BLOCKERS and a != firer and b != target:
            return (a, d)
    return None


def evaluate_traced(board: Board, firer: HexRef, target: HexRef, traced: list[TracedHex]) -> LosVerdict:
    """Apply rules 7.2 to 7.8 and 11.51 to one traced thread."""
    if rule_7_8_adjacent(board, firer, target):
        return LosVerdict(True, RULE_7_8)
    firer_ms = rule_7_4_multi_story(board, firer)
    target_ms = rule_7_4_multi_story(board, target)
    height_advantage = firer_ms or target_ms

    hexside = rule_11_51_hexside_block(board, firer, target, [firer] + [t.ref for t in traced] + [target], height_advantage)
    if hexside is not None:
        return LosVerdict(False, RULE_11_51, blocking_hexside=hexside)

    fb = board.hex(firer).building
    tb = board.hex(target).building
    if fb is not None and tb is not None and fb.id == tb.id:
        for t in traced:
            if crossed_building(board, t.kinds):
                return LosVerdict(False, RULE_7_7, blocking_hex=t.ref)

    path = [firer] + [t.ref for t in traced] + [target]
    if r43_elevation.in_play(board, path):
        # Rule 43 reads rules 7.2 to 7.6 again with the levels of the hexes. It decides on
        # its own thread, because a height advantage over an obstacle is a number there and
        # not the multi-story flag of rule 7.4.
        block = r43_elevation.blocked(board, firer, target, [(t.ref, t.kinds) for t in traced])
        if block is not None:
            return LosVerdict(False, block.rule_id, blocking_hex=block.ref)
        return LosVerdict(True, r43_elevation.RULE_43_7)

    for t in traced:
        if crossed_multi_story_building(board, t.ref, t.kinds):
            return LosVerdict(False, RULE_7_5, blocking_hex=t.ref)

    if not height_advantage:
        for t in traced:
            if crossed_obstacle(board, t.kinds):
                return LosVerdict(False, RULE_7_3, blocking_hex=t.ref)
        return LosVerdict(True, RULE_7_2)

    if traced:
        check_firer_side = (not firer_ms) or target_ms
        check_target_side = (not target_ms) or firer_ms
        if check_target_side and crossed_obstacle(board, traced[-1].kinds):
            return LosVerdict(False, RULE_7_4, blocking_hex=traced[-1].ref)
        if check_firer_side and crossed_obstacle(board, traced[0].kinds):
            return LosVerdict(False, RULE_7_6 if not firer_ms else RULE_7_4, blocking_hex=traced[0].ref)
    return LosVerdict(True, RULE_7_4)
