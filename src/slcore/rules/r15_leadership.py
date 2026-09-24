"""Rule 15, leadership: fire direction, morale, and rally modifiers."""

from __future__ import annotations

from typing import Mapping

from slcore.game import State
from slcore.geometry import HexRef
from slcore.units import KIND_LEADER, Unit, UnitType

RULE_15_1 = "15.1"
RULE_15_2 = "15.2"
RULE_15_4 = "15.4"
RULE_15_5 = "15.5"
RULE_15_6 = "15.6"
RULE_15_7 = "15.7"
RULE_15_8 = "15.8"
RULE_17_4 = "17.4"


def leaders_in(state: State, hex_ref: HexRef, player: int, unbroken_only: bool = True) -> list[Unit]:
    out = [u for u in state.units_in(hex_ref) if u.kind == KIND_LEADER and u.player == player]
    if unbroken_only:
        out = [u for u in out if not u.broken]
    return sorted(out, key=lambda u: u.id)


def best_leader(state: State, types: Mapping[str, UnitType], hex_ref: HexRef, player: int, exclude: int | None = None) -> Unit | None:
    """Rule 15.7: the owner selects one leader. The core selects the strongest rating.

    Rule 15.6: the rating of an unbroken leader applies to the morale checks of the
    other units in the hex. Rule 17.4 takes the benefit away from a leader who mans a
    machine gun. A leader who only points the fire of a squad keeps the benefit.
    """
    best: Unit | None = None
    for u in leaders_in(state, hex_ref, player):
        if u.id == exclude or u.manned_mg:
            continue
        if best is None or types[u.type_key].leadership < types[best.type_key].leadership:
            best = u
    return best


def modifier_for_check(state: State, types: Mapping[str, UnitType], unit: Unit) -> tuple[int, int | None]:
    """The leadership modifier for a morale check or a rally attempt, and the leader that gives it.

    Rule 12.4 and 14.3: a leader does not apply its own rating to its own check.
    Rule 15.1 and the ruling for 15.1: a poor leader cannot be refused here.
    """
    if unit.hex is None:
        return 0, None
    exclude = unit.id if unit.kind == KIND_LEADER else None
    leader = best_leader(state, types, unit.hex, unit.player, exclude=exclude)
    if leader is None:
        return 0, None
    return types[leader.type_key].leadership, leader.id
