"""Rule 44, the rural terrain types (FR-16 in the part that needs no armor table).

Game Set II adds three terrain types to the ones that the city board has. Two of them were
already in the terrain data, and this module gives them the effects the rule names.

- 44.1, cliffs. A hill hexside in black is impassable. The movement rule already refuses
  it, because the hexside table marks a cliff as not passable. What this module adds is
  the second half: fire across a cliff hexside between two adjacent hexes triples the Point
  Blank Fire of the higher unit, and the lower unit keeps the doubling of rule 9.1.
- 44.2, wheatfields. A unit sees into a wheatfield hex and not through it. A unit fires into
  a wheatfield hex at full strength, and fire that goes through a wheatfield hex is half
  strength as Area Fire, because it crosses more than one wheatfield hexside. A unit with a
  height advantage over the wheatfield is not affected at all (44.21, 44.22).
- 44.23: a unit that moved in a wheatfield hex does not take the minus two of rule 16.5.
  The terrain rule already gives that, because a wheatfield is not open ground.
- 44.24: wheatfields are seasonal. They are on the board from June to October, and a
  scenario outside those months plays them as open ground.
- 44.3, shellholes. A shellhole gives the plus one of the terrain table, which the data
  file already holds. What this module adds is 44.32: a unit fired on while it moved
  through a shellhole hex takes minus one and not the minus two of rule 16.5.

Why the halving counts hexes and not hexsides. A thread that goes through a wheatfield hex
crosses two of its hexsides, one to go in and one to come out. A thread that stops in the
hex crosses one. So "more than one wheatfield hexside" is the same statement as "the thread
passes through a wheatfield hex", and the hexes between the firer and the target are the
ones the LOS evaluator already gives.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from slcore.geometry import HexRef
from slcore.rules import r43_elevation
from slcore.state import Board

RULE_44_1 = "44.1"
RULE_44_21 = "44.21"
RULE_44_24 = "44.24"
RULE_44_32 = "44.32"

WHEAT = "wheat"
# PR-56: an orchard has the effects of a wheatfield in each season.
ORCHARD = "orchard"
RULE_PR_56 = "PR-56"
SHELLHOLE = "shellhole"
CLIFF = "cliff"

# Rule 44.24: the months that have a standing crop.
IN_SEASON_MONTHS = (6, 7, 8, 9, 10)
SWITCH_SEASON = "wheat_season"
SEASON_IN = "in"
SEASON_OUT = "out"

# Rule 16.5 gives minus two against a unit that moved in open ground. Rule 44.32 makes it
# minus one when the hex is a shellhole.
MOVED_IN_SHELLHOLE = -1

# Rule 9.1 doubles Point Blank Fire. Rule 44.1 triples it for the higher unit across a
# cliff hexside. The firepower is in half factors (NFR-05), so the numbers are the count of
# halves that one factor becomes.
POINT_BLANK_HALVES = 4
CLIFF_POINT_BLANK_HALVES = 6


def wheat_in_season(switches) -> bool:
    """Rule 44.24: whether the scenario has a standing crop.

    A scenario says `wheat_season` as `in` or `out`. With no switch the crop is standing,
    because the three scenarios of year one are in October.
    """
    value = dict(switches or {}).get(SWITCH_SEASON, SEASON_IN)
    return str(value) != SEASON_OUT


def month_in_season(month: int) -> bool:
    """Rule 44.24 by the month of the scenario."""
    return month in IN_SEASON_MONTHS


def is_wheat(board: Board, ref: HexRef, in_season: bool = True) -> bool:
    """A wheatfield hex, when the crop is standing. Out of season it is open ground."""
    return in_season and board.hex(ref).terrain == WHEAT


def is_orchard(board: Board, ref: HexRef) -> bool:
    """PR-56: an orchard hex. It has no season."""
    return board.hex(ref).terrain == ORCHARD


def crop_hexes(board: Board, traced: Iterable[HexRef], in_season: bool = True) -> tuple[HexRef, ...]:
    """The wheatfield and orchard hexes that the thread goes through, between the two ends."""
    return tuple(ref for ref in traced if is_wheat(board, ref, in_season) or is_orchard(board, ref))


def crop_rules(board: Board, crop: Sequence[HexRef]) -> tuple[str, ...]:
    """The rule IDs of the halving: 44.21 for a wheatfield, PR-56 for an orchard."""
    kinds = {board.hex(ref).terrain for ref in crop}
    return tuple(rule for kind, rule in ((WHEAT, RULE_44_21), (ORCHARD, RULE_PR_56)) if kind in kinds)


def height_over(board: Board, firer: HexRef, target: HexRef, crop: Sequence[HexRef]) -> bool:
    """Rule 44.21: a unit above the wheatfield sees over it, and the crop does nothing.

    A wheatfield is as high as the ground it stands in, so one level of rule 43 is enough.
    """
    if not crop:
        return False
    highest = max(r43_elevation.level(board, ref) for ref in crop)
    return max(r43_elevation.level(board, firer), r43_elevation.level(board, target)) > highest


def halves_through_crop(
    board: Board,
    firer: HexRef,
    target: HexRef,
    traced: Sequence[HexRef],
    halves: int,
    in_season: bool = True,
) -> int:
    """Rule 44.21: fire that goes through a wheatfield hex is half strength.

    Fire into a wheatfield hex is full strength, because it crosses one hexside of the
    crop and rule 44.21 halves the fire that crosses more than one.
    """
    crop = crop_hexes(board, traced, in_season)
    if not crop or height_over(board, firer, target, crop):
        return halves
    return halves // 2


def moved_modifier(board: Board, target: HexRef) -> int | None:
    """Rule 44.32: the modifier of rule 16.5 in a shellhole hex, or None for no change."""
    if board.hex(target).terrain == SHELLHOLE:
        return MOVED_IN_SHELLHOLE
    return None


def cliff_between(board: Board, firer: HexRef, target: HexRef) -> bool:
    """Whether a cliff hexside separates two adjacent hexes (rule 44.1)."""
    from slcore.geometry import direction_to

    direction = direction_to(firer, target)
    if direction is None:
        return False
    return board.hexside(firer, direction) == CLIFF


def point_blank_halves(board: Board, firer: HexRef, target: HexRef) -> int:
    """Rule 9.1 with rule 44.1: how many half factors one firepower factor becomes.

    Point Blank Fire doubles the firepower. Across a cliff hexside the higher unit triples
    it instead, and the lower unit keeps the doubling.
    """
    if not cliff_between(board, firer, target):
        return POINT_BLANK_HALVES
    if r43_elevation.level(board, firer) > r43_elevation.level(board, target):
        return CLIFF_POINT_BLANK_HALVES
    return POINT_BLANK_HALVES
