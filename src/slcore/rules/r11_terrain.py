"""Rule 11, terrain effects modifiers on the fire combat dice roll."""

from __future__ import annotations

from typing import Mapping, Sequence

from slcore import geometry
from slcore.geometry import HexRef
from slcore.rules import r44_rural
from slcore.state import Board, HexsideRule

RULE_11_1 = "11.1"
RULE_11_2 = "11.2"
RULE_11_4 = "11.4"
RULE_11_53 = "11.53"
RULE_11_6 = "11.6"
RULE_16_5 = "16.5"

HEXSIDE_MODIFIERS = ("wall", "hedge")
OPEN_GROUND = ("open",)


def target_hex_modifier(board: Board, target: HexRef) -> int:
    """Rule 11.1 and 11.4: the terrain of the target hex. A road hex uses its other terrain."""
    return board.terrain[board.hex(target).terrain].tem


def hexside_modifier(board: Board, hexsides: Mapping[str, HexsideRule], traced: Sequence[HexRef], firer: HexRef, target: HexRef) -> int:
    """Rule 11.53: the wall or hedge hexside that the LOS crosses into the target hex."""
    path = [firer] + list(traced) + [target]
    last = path[-2]
    d = geometry.direction_to(last, target)
    if d is None:
        return 0
    feature = board.hexside(last, d)
    if feature in HEXSIDE_MODIFIERS:
        return hexsides[feature].tem
    return 0


def group_hexside_modifier(board: Board, hexsides: Mapping[str, HexsideRule], per_member: Sequence[int]) -> int:
    """Rule 11.6: a hexside modifier applies only when each LOS of the fire group crosses it."""
    if not per_member:
        return 0
    return min(per_member) if all(m == per_member[0] for m in per_member) else 0


def is_open_ground(board: Board, hex_ref: HexRef) -> bool:
    """Rule 13.42 note: wheatfields and shellholes are not open ground."""
    return board.hex(hex_ref).terrain in OPEN_GROUND


def moving_in_open_modifier(board: Board, target: HexRef) -> int:
    """Rule 16.5 with rule 44.32: the modifier against a unit that moved in the target hex.

    Rule 16.5 gives minus two in open ground. Rule 44.32 makes it minus one in a shellhole,
    because the hole gives cover to a unit that moves through it. Each other terrain type
    gives nothing, and rule 44.23 says the same for a wheatfield.
    """
    if is_open_ground(board, target):
        return -2
    adjusted = r44_rural.moved_modifier(board, target)
    return adjusted if adjusted is not None else 0
