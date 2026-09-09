"""Rule 43, elevation, and the LOS parts that depend on it.

Rule 43 gives the board three levels of hills. A level is a height, and a height decides
what a unit can see over. Rule 43.15 says a hill hex with no other terrain feature is open
ground for movement and for combat, so the level lives in its own field of the hex and not
in the terrain kind.

The heights, from rules 43.11 to 43.13:

- A level one hill hex is as high as a small building or woods on ground level.
- A level two hill hex is as high as a large building or woods, or a small building on a
  level one hill hex.
- A level three hill hex is as high as woods on a level two hill hex.

So woods and a small building are one height unit above the hex they stand in, and a large
building of three hexes or more is two height units above it (rule 43.12 with rule 7.4).

How the module decides:

The thread from the firer to the target is a straight line between two hex centres. Rule
43.4 says a unit sees over an obstacle only with a height advantage over it, and rule 43.6
says the hex behind such an obstacle is blind. Both follow from one test: take the height
of the thread above each hex it goes through, and compare it with the top of that hex.

The height of the thread over the hex at step k of d steps is

    firer_height + (target_height - firer_height) * k / d

and the test multiplies both sides by d, so the rule path stays in integers (NFR-05).

Two comparisons, and the difference between them is rule 43.7:

- A hex whose crossed symbol blocks (woods, a building) stops the thread when its top
  reaches the height of the thread. A unit needs a height advantage to see over it.
- A bare hill hex stops the thread only when its level is above the height of the thread.
  Rule 43.7 says a unit sees anything on its own level, whatever the equal or lower crest
  lines between them do.

The thread test does not give the blind hexes of rule 43.6, because a thread that clears a
roof is already above the ground behind it. So the module counts them: one hex behind woods
or a small building (rule 7.4), two hexes behind a large building (rule 43.62), and a hex in
that zone is seen only when its own level reaches the top of the obstacle. A bare crest line
opens no blind zone, which is what rule 43.61 says.

When every hex of the thread is on ground level, this module says nothing, and rule 7
decides on its own. That keeps one reading of rule 7 for the city boards.
"""

from __future__ import annotations

from dataclasses import dataclass

from slcore.geometry import HexRef
from slcore.state import LOS_BLOCK, Board

RULE_43_3 = "43.3"
RULE_43_4 = "43.4"
RULE_43_6 = "43.6"
RULE_43_62 = "43.62"
RULE_43_7 = "43.7"

WOODS_HEIGHT = 1
SMALL_BUILDING_HEIGHT = 1
LARGE_BUILDING_HEIGHT = 2
LARGE_BUILDING_BLIND_HEXES = 2


@dataclass(frozen=True)
class Block:
    """The hex that stops the thread, and the rule that stopped it."""

    ref: HexRef
    rule_id: str


def level(board: Board, ref: HexRef) -> int:
    """Rule 43.14: the level of the hex is the level of its centre dot."""
    return board.hex(ref).elevation


def symbol_height(board: Board, ref: HexRef, kinds: frozenset[str]) -> int:
    """How far a crossed symbol stands above its hex (rules 43.11 to 43.13).

    `kinds` is what the thread crossed in this hex. A symbol the thread misses is not an
    obstacle for this thread, which is what rule 7.2 already says for ground level.
    """
    if not any(board.los_class(k) == LOS_BLOCK for k in kinds):
        return 0
    building = board.hex(ref).building
    if building is not None and any(board.is_building_kind(k) for k in kinds):
        return LARGE_BUILDING_HEIGHT if building.multi_story else SMALL_BUILDING_HEIGHT
    return WOODS_HEIGHT


def in_play(board: Board, path: list[HexRef]) -> bool:
    """Whether any hex of the thread is off ground level."""
    return any(level(board, ref) for ref in path)


def blocked(
    board: Board,
    firer: HexRef,
    target: HexRef,
    traced: list[tuple[HexRef, frozenset[str]]],
) -> Block | None:
    """The first hex that stops the thread, or None.

    `traced` holds the hexes between the firer and the target, in order, each with the
    terrain kinds the thread crossed inside it.
    """
    if level(board, target) > level(board, firer):
        # Rule 43.6 counts the blind hexes behind the obstacle as the unit with the height
        # advantage sees them, so the thread is read from its higher end. Rule 43.8 asks
        # for that: whatever A sees of B, B sees of A.
        firer, target = target, firer
        traced = list(reversed(traced))
    steps = len(traced) + 1
    low = level(board, firer)
    rise = level(board, target) - low
    blind_left = 0
    blind_top = 0
    blind_rule = RULE_43_6
    for k, (ref, kinds) in enumerate(traced, start=1):
        thread = low * steps + rise * k
        here = level(board, ref)
        height = symbol_height(board, ref, kinds)
        if height:
            if (here + height) * steps >= thread:
                return Block(ref, RULE_43_4)
            if height >= LARGE_BUILDING_HEIGHT:
                blind_left, blind_rule = LARGE_BUILDING_BLIND_HEXES, RULE_43_62
            else:
                blind_left, blind_rule = 1, RULE_43_6
            blind_top = here + height
            continue
        if here * steps > thread:
            return Block(ref, RULE_43_3)
        blind_left = max(0, blind_left - 1)
    if blind_left and level(board, target) < blind_top:
        return Block(target, blind_rule)
    return None
