"""Rules 8 and 9, fire combat principles and firepower modifiers, with the machine gun
manning rules of 17.1 to 17.4.

Firepower is carried in half factors so that the halving of rule 9 stays in integer
arithmetic (NFR-05). A squad with 4 firepower is 8 half factors.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from slcore import geometry
from slcore.game import FireGroup, State
from slcore.geometry import HexRef
from slcore.units import KIND_LEADER, KIND_SW, Unit, UnitType

RULE_8_2 = "8.2"
RULE_8_4 = "8.4"
RULE_8_5 = "8.5"
RULE_8_6 = "8.6"
RULE_8_7 = "8.7"
RULE_8_8 = "8.8"
RULE_9_1 = "9.1"
RULE_9_2 = "9.2"
RULE_9_3 = "9.3"
RULE_9_5 = "9.5"
RULE_17_1 = "17.1"
RULE_17_2 = "17.2"
RULE_17_3 = "17.3"
RULE_5_74 = "5.74"
RULE_5_75 = "5.75"

MAX_WEAPONS_FOR_EACH_UNIT = 2
MG_FREE_FIREPOWER = 4
# Rules 22.3, 23, and 37: these weapons have their own commands. They do not join a group,
# and they do not take the point-blank doubling of rule 9.1.
NOT_A_GROUP_WEAPON = frozenset({"flamethrower", "demo", "panzerfaust", "bazooka"})


@dataclass(frozen=True)
class MemberFire:
    unit: int
    weapon: int | None
    halves: int
    modifiers: tuple[str, ...]


def firing_units(state: State, player: int) -> list[Unit]:
    """Rule 8.1 with rule 31.5, which keeps a unit on top of a vehicle from firing."""
    return [
        u
        for u in state.player_units(player)
        if u.is_infantry and u.hex is not None and u.carrier is None and not u.broken and not u.riding
    ]


def can_fire_inherent(state: State, types: Mapping[str, UnitType], unit: Unit, phase_moved_rule: str) -> bool:
    """Rule 8.2: the inherent firepower fires one time in a player turn."""
    if unit.fired or unit.broken or unit.hex is None or state.in_melee(unit.hex):
        return False
    if types[unit.type_key].firepower <= 0:
        return False
    if phase_moved_rule == "prep" and (unit.prep_fired or unit.moved):
        return False
    if phase_moved_rule == "advancing" and unit.prep_fired:
        return False
    return True


def can_fire_weapon(state: State, types: Mapping[str, UnitType], unit: Unit, weapon: Unit, phase_moved_rule: str) -> bool:
    """Rules 5.74, 5.75, 17.1 to 17.3, and 18.1 for a support weapon."""
    if types[weapon.type_key].weapon_class in NOT_A_GROUP_WEAPON:
        return False
    if weapon.carrier != unit.id or weapon.malfunction or weapon.fired or weapon.eliminated:
        return False
    if unit.broken or unit.hex is None or state.in_melee(unit.hex):
        return False
    if phase_moved_rule == "prep" and (unit.prep_fired or unit.moved):
        return False
    if phase_moved_rule == "advancing" and unit.prep_fired:
        return False
    t = types[unit.type_key]
    if phase_moved_rule == "advancing":
        limit = 2 if unit.kind == KIND_LEADER else 4
        if unit.portage_max >= limit:
            return False
    if unit.kind == KIND_LEADER and types[weapon.type_key].pp_leader is None:
        return False
    return True


def weapons_in_group(group: FireGroup, unit_id: int) -> int:
    return sum(1 for uid, wid in group.members if uid == unit_id and wid is not None)


def inherent_in_group(group: FireGroup, unit_id: int) -> bool:
    return any(uid == unit_id and wid is None for uid, wid in group.members)


def member_hexes(state: State, group: FireGroup) -> set[HexRef]:
    out: set[HexRef] = set()
    for uid, _ in group.members:
        h = state.units[uid].hex
        if h is not None:
            out.add(h)
    return out


def chain_allows(state: State, group: FireGroup, hex_ref: HexRef) -> bool:
    """Rule 8.6: a fire group is a chain of hexes that are the same or adjacent."""
    hexes = member_hexes(state, group)
    if not hexes:
        return True
    if hex_ref in hexes:
        return True
    return any(geometry.direction_to(hex_ref, h) is not None for h in hexes)


def range_class(types: Mapping[str, UnitType], source_key: str, distance: int) -> str | None:
    """Rules 9.1 and 9.2: point blank, normal, long, or out of range."""
    printed = types[source_key].range
    if distance <= 1:
        return "point_blank"
    if distance <= printed:
        return "normal"
    if distance <= 2 * printed:
        return "long"
    return None


def member_firepower(state: State, types: Mapping[str, UnitType], unit: Unit, weapon: Unit | None, target: HexRef, moving: bool) -> MemberFire | None:
    """The firepower of one member in half factors, with the modifiers of rule 9."""
    if unit.hex is None:
        return None
    source_key = weapon.type_key if weapon is not None else unit.type_key
    distance = geometry.distance(unit.hex, target)
    rc = range_class(types, source_key, distance)
    if rc is None:
        return None
    halves = types[source_key].firepower * 2
    modifiers: list[str] = []
    if weapon is not None and unit.kind == KIND_LEADER:
        halves //= 2
        modifiers.append(RULE_17_3)
    if rc == "point_blank":
        halves *= 2
        modifiers.append(RULE_9_1)
    elif rc == "long":
        halves //= 2
        modifiers.append(RULE_9_2)
    if moving:
        halves //= 2
        modifiers.append(RULE_9_3)
    if halves <= 0:
        return None
    return MemberFire(unit.id, None if weapon is None else weapon.id, halves, tuple(modifiers))


def group_firepower(state: State, types: Mapping[str, UnitType], group: FireGroup) -> tuple[int, list[MemberFire]]:
    """Total half factors of the group and the record for each member.

    Rules 17.1 and 17.2: a squad fires one machine gun, or two whose combined firepower
    is 4 or less, at no cost. Above that the squad forfeits its inherent firepower.
    """
    members: list[MemberFire] = []
    forfeit: set[int] = set()
    for uid in {u for u, _ in group.members}:
        unit = state.units[uid]
        if unit.kind == KIND_LEADER:
            continue
        mg_fp = sum(
            types[state.units[wid].type_key].firepower
            for u2, wid in group.members
            if u2 == uid and wid is not None and types[state.units[wid].type_key].weapon_class == "mg"
        )
        if mg_fp > MG_FREE_FIREPOWER:
            forfeit.add(uid)
    for uid, wid in group.members:
        unit = state.units[uid]
        weapon = None if wid is None else state.units[wid]
        if wid is None and uid in forfeit:
            continue
        moving = unit.moved if weapon is None else (unit.moved or weapon.moved)
        mf = member_firepower(state, types, unit, weapon, group.target, moving)
        if mf is not None:
            members.append(mf)
    total = sum(m.halves for m in members)
    return total, members


def moving_members(state: State, group: FireGroup) -> bool:
    return any(state.units[uid].moved for uid, _ in group.members)
