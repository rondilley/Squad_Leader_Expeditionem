"""Rule 14, rally, with the repair and special morale rules of 18.2 and 18.3."""

from __future__ import annotations

from typing import Mapping

from slcore import geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import State
from slcore.rng import roll_2d6, roll_die
from slcore.rules import r12_morale, r15_leadership, r26_fanaticism
from slcore.units import KIND_LEADER, KIND_SW, Unit, UnitType

RULE_14_1 = "14.1"
RULE_14_2 = "14.2"
RULE_14_3 = "14.3"
RULE_14_4 = "14.4"
RULE_14_6 = "14.6"
RULE_14_7 = "14.7"
RULE_18_2 = "18.2"
RULE_18_3 = "18.3"

DESPERATION_PENALTY = 4
REPAIR_ROLL = 1
REMOVE_ROLL = 6
SELF_CASUALTY_ROLL = 12


def can_rally(state: State, unit: Unit) -> bool:
    """Rules 14.1, 14.3, and 14.4."""
    if not unit.broken or unit.eliminated or unit.rally_tried or unit.hex is None or unit.carrier is not None:
        return False
    if state.in_melee(unit.hex):
        return False
    if unit.kind == KIND_LEADER:
        return True
    return any(u.kind == KIND_LEADER and u.player == unit.player and not u.broken for u in state.infantry_in(unit.hex))


def repairable(state: State, weapon: Unit) -> bool:
    """Rule 18.2: a malfunctioning weapon with an unbroken squad or leader in its hex."""
    if weapon.kind != KIND_SW or not weapon.malfunction or weapon.eliminated or weapon.repair_tried:
        return False
    holder_hex = weapon.hex if weapon.carrier is None else state.units[weapon.carrier].hex
    if holder_hex is None or state.in_melee(holder_hex):
        return False
    return any(u.player == weapon.player and not u.broken for u in state.infantry_in(holder_hex))


def legal_rally_commands(state: State, player: int) -> list[Command]:
    out: list[Command] = []
    for w in state.player_units(player):
        if repairable(state, w):
            out.append(Command("repair", weapon=w.id))
    for u in state.player_units(player):
        if can_rally(state, u):
            out.append(Command("rally", units=(u.id,)))
    return out


def apply_repair(state: State, types: Mapping[str, UnitType], command: Command) -> tuple[State, list[Event]]:
    weapon = state.units[command.weapon] if command.weapon is not None else None
    if weapon is None:
        raise ValueError("repair needs a weapon")
    rng, die = roll_die(state.rng)
    state = state.with_(rng=rng)
    data = {"weapon": weapon.id, "die": die}
    if die == REPAIR_ROLL:
        state = state.with_unit(weapon.with_(malfunction=False, repair_tried=True))
        return state, [Event(RULE_18_2, "repaired", data)]
    if die == REMOVE_ROLL:
        state = state.with_unit(weapon.with_(eliminated=True, carrier=None, hex=None, repair_tried=True))
        return state, [Event(RULE_18_2, "weapon_removed", data)]
    state = state.with_unit(weapon.with_(repair_tried=True))
    return state, [Event(RULE_18_2, "repair_failed", data)]


def apply_rally(state: State, types: Mapping[str, UnitType], command: Command) -> tuple[State, list[Event]]:
    """Rule 14.2 with the desperation morale of 14.6 and the casualty roll of 18.3."""
    unit = state.units[command.units[0]]
    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    modifier, leader_id = r15_leadership.modifier_for_check(state, types, unit)
    fanatic = r26_fanaticism.modifier_for(state, unit)
    target = r12_morale.morale_value(types, unit)
    if unit.dm:
        target -= DESPERATION_PENALTY
    adjusted = raw + modifier + fanatic
    data = {
        "unit": unit.id,
        "hex": geometry.hex_id(*unit.hex) if unit.hex else None,
        "dice": list(dice),
        "leadership": modifier,
        "leader": leader_id,
        "fanatic": fanatic,
        "adjusted": adjusted,
        "target": target,
        "desperation": unit.dm,
    }
    state = state.with_unit(state.units[unit.id].with_(rally_tried=True))
    if raw == SELF_CASUALTY_ROLL:
        state = state.with_unit(state.units[unit.id].with_(eliminated=True, hex=None, carrier=None))
        state, drop = r12_morale.drop_weapons(state, unit.id)
        events = [Event(RULE_18_3, "eliminated", data)] + drop
        if unit.kind == KIND_LEADER and unit.hex is not None:
            for other in sorted(state.infantry_in(unit.hex), key=lambda u: u.id):
                if other.player != unit.player or other.eliminated:
                    continue
                state, ev = r12_morale.morale_check(state, types, state.units[other.id], 0, "leader_casualty")
                events.extend(ev)
        return state, events
    if adjusted <= target:
        state = state.with_unit(state.units[unit.id].with_(broken=False, stay=False, dm=False))
        return state, [Event(RULE_14_2, "rallied", data)]
    return state, [Event(RULE_14_7, "rally_failed", data)]
