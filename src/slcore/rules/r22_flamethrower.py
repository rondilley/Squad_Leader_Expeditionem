"""Rule 22, flamethrowers.

A flamethrower is a support weapon of 20 firepower and 2 hexes of range, and it is not
like the other weapons in four ways:

- It fires alone. It never joins a fire group, not even with a second flamethrower
  (rule 22.3).
- Its attack has no dice roll modifier of any kind: no terrain, no defensive fire against
  moving infantry, no smoke, and no leadership (rule 22.2).
- It has no long range and no point blank bonus. The firepower is always 20, and the one
  reduction is the halving against a concealed target (rule 22.1).
- Advancing Fire does not halve it, even when the unit moved (rule 22.8).

Two more rules make it dangerous to hold and to face. A dice roll of 9 or more empties
the fuel and the weapon leaves the game (rule 22.6). A hex that holds a flamethrower
gives the units that fire at that hex one more point of modifier (rule 22.7).
"""

from __future__ import annotations

from typing import Mapping

from slcore import geometry
from slcore.events import Event
from slcore.game import State
from slcore.geometry import HexRef
from slcore.rng import roll_2d6
from slcore.units import KIND_LEADER, KIND_SW, Unit, UnitType

RULE_22_1 = "22.1"
RULE_22_2 = "22.2"
RULE_22_3 = "22.3"
RULE_22_4 = "22.4"
RULE_22_5 = "22.5"
RULE_22_6 = "22.6"
RULE_22_7 = "22.7"
RULE_22_8 = "22.8"
RULE_22_9 = "22.9"

WEAPON_CLASS = "flamethrower"
OUT_OF_FUEL = 9
TARGET_MODIFIER = -1
LEADER_RATING = -2


def is_flamethrower(types: Mapping[str, UnitType], unit: Unit) -> bool:
    return unit.kind == KIND_SW and types[unit.type_key].weapon_class == WEAPON_CLASS


def may_operate(types: Mapping[str, UnitType], unit: Unit) -> bool:
    """Rule 22.4: an assault engineer squad, or a leader of minus two or better."""
    t = types[unit.type_key]
    if t.assault_engineer:
        return True
    return unit.kind == KIND_LEADER and t.leadership <= LEADER_RATING


def in_hex(state: State, types: Mapping[str, UnitType], hex_ref: HexRef) -> bool:
    """Rule 22.7: a flamethrower in the hex, carried or on the ground."""
    for u in state.units:
        if u.eliminated or not is_flamethrower(types, u):
            continue
        where = u.hex if u.carrier is None else state.units[u.carrier].hex
        if where == hex_ref:
            return True
    return False


def can_fire(state: State, types: Mapping[str, UnitType], unit: Unit, weapon: Unit, phase_rule: str) -> bool:
    """Rule 22.4 with the phase restrictions of rules 4.2 and 4.5."""
    if not is_flamethrower(types, weapon) or weapon.carrier != unit.id:
        return False
    if weapon.malfunction or weapon.fired or weapon.eliminated:
        return False
    if unit.broken or unit.hex is None or state.in_melee(unit.hex):
        return False
    if not may_operate(types, unit):
        return False
    if phase_rule == "prep" and (unit.prep_fired or unit.moved):
        return False
    if phase_rule == "advancing" and unit.prep_fired:
        return False
    return True


def in_range(types: Mapping[str, UnitType], weapon: Unit, firer: HexRef, target: HexRef) -> bool:
    """Rule 22.1: two hexes, with no long range band."""
    return geometry.distance(firer, target) <= types[weapon.type_key].range


def halves(types: Mapping[str, UnitType], weapon: Unit) -> int:
    """Rule 22.1: always the printed firepower, in half factors (NFR-05)."""
    return types[weapon.type_key].firepower * 2


def out_of_fuel(state: State, weapon_id: int, raw: int) -> tuple[State, list[Event]]:
    """Rule 22.6: a roll of 9 or more empties the fuel after the attack is resolved."""
    if raw < OUT_OF_FUEL:
        return state, []
    weapon = state.units[weapon_id]
    state = state.with_unit(weapon.with_(eliminated=True, carrier=None, hex=None))
    return state, [Event(RULE_22_6, "out_of_fuel", {"weapon": weapon_id, "roll": raw})]


def roll(state: State) -> tuple[State, tuple[int, int]]:
    rng, dice = roll_2d6(state.rng)
    return state.with_(rng=rng), dice
