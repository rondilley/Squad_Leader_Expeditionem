"""Rule 37, the special infantry weapons against armoured fighting vehicles.

A unit with one of these needs no Pre-AFV Attack Morale Check (rule 37.1).

The flamethrower hits any vehicle in range without a roll and goes straight to the
flamethrower column of the kill table (rule 37.2). The panzerfaust and the bazooka each
have a small to-hit chart of their own, and a hit reads their own column of the kill table
(rules 37.32 and 37.42).

Leadership modifies the to-hit roll of the two rockets and never the kill roll (rules
37.34 and 37.44).
"""

from __future__ import annotations

from typing import Mapping

from slcore import geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import PHASE_ADVANCING_FIRE, State
from slcore.geometry import HexRef
from slcore.rng import roll_2d6
from slcore.rules import r15_leadership, r28_vehicles, r33_afv_combat
from slcore.rules.r33_afv_combat import ArmorContext
from slcore.tabledata import HandheldToHit
from slcore.units import Unit, UnitType

RULE_37_1 = "37.1"
RULE_37_2 = "37.2"
RULE_37_3 = "37.3"
RULE_37_31 = "37.31"
RULE_37_32 = "37.32"
RULE_37_34 = "37.34"
RULE_37_35 = "37.35"
RULE_37_37 = "37.37"
RULE_37_4 = "37.4"
RULE_37_41 = "37.41"
RULE_37_42 = "37.42"
RULE_37_45 = "37.45"
RULE_37_46 = "37.46"

CLASS_PANZERFAUST = "panzerfaust"
CLASS_BAZOOKA = "bazooka"
CLASS_FLAMETHROWER = "flamethrower"

KILL_COLUMN = {
    CLASS_PANZERFAUST: "panzerfaust",
    CLASS_BAZOOKA: "bazooka",
    CLASS_FLAMETHROWER: "flamethrower",
}

# Rule 37.35 and rule 37.46: how many of each a squad may fire in one player turn.
SHOTS_FOR_EACH_TURN = {CLASS_PANZERFAUST: 4, CLASS_BAZOOKA: 2}
# Rule 37.45: an unmodified eleven or twelve takes the bazooka out of play.
BAZOOKA_SPENT = 11
# Rule 37.2: the flamethrower reads the same roll again on the twenty firepower column.
FLAMETHROWER_FIREPOWER = 20


def chart_for(ctx: ArmorContext, weapon_class: str) -> HandheldToHit | None:
    if weapon_class == CLASS_PANZERFAUST:
        return ctx.armor.panzerfaust
    if weapon_class == CLASS_BAZOOKA:
        return ctx.armor.bazooka
    return None


def anti_tank_weapons(state: State, types: Mapping[str, UnitType], unit: Unit) -> list[Unit]:
    """The panzerfausts, bazookas, and flamethrowers this unit carries."""
    return [
        w
        for w in sorted(state.carried_by(unit.id), key=lambda w: w.id)
        if types[w.type_key].weapon_class in KILL_COLUMN and not w.malfunction and not w.eliminated
    ]


def shots_left(state: State, types: Mapping[str, UnitType], unit: Unit, weapon_class: str) -> int:
    """Rules 37.35 and 37.46: what is left of the per turn count of this weapon class.

    A panzerfaust leaves the game when it fires, so a count of counters that are still
    carried stays at zero. The state records each shot.
    """
    del types
    used = sum(1 for firer_id, fired_class in state.at_shots if firer_id == unit.id and fired_class == weapon_class)
    limit = SHOTS_FOR_EACH_TURN.get(weapon_class)
    if limit is None:
        return 0 if used else 1
    return max(0, limit - used)


def in_range(ctx: ArmorContext, weapon: Unit, firer: HexRef, target: HexRef) -> bool:
    reach = ctx.types[weapon.type_key].range
    return 1 <= geometry.distance(firer, target) <= reach


def legal_shots(
    ctx: ArmorContext, state: State, player: int, phase: str
) -> list[Command]:
    """One command for each anti-tank weapon that can reach an enemy vehicle."""
    out: list[Command] = []
    hostile = [
        v
        for v in r28_vehicles.vehicles(state, 1 - player)
        if v.hex is not None and not v.wreck
    ]
    if not hostile:
        return out
    for unit in state.player_units(player):
        if not unit.is_infantry or unit.hex is None or unit.broken or unit.riding:
            continue
        if unit.carrier is not None or unit.fired or unit.prep_fired:
            continue
        for weapon in anti_tank_weapons(state, ctx.types, unit):
            weapon_class = ctx.types[weapon.type_key].weapon_class
            if shots_left(state, ctx.types, unit, weapon_class) <= 0:
                continue
            for vehicle in hostile:
                if vehicle.hex is None or not in_range(ctx, weapon, unit.hex, vehicle.hex):
                    continue
                out.append(Command("at_fire", units=(unit.id,), weapon=weapon.id, hex=vehicle.hex))
    return out


def apply_shot(
    ctx: ArmorContext, state: State, command: Command, phase: str
) -> tuple[State, list[Event]]:
    """Rules 37.2, 37.3, and 37.4: one anti-tank shot at one vehicle."""
    unit = state.units[command.units[0]]
    if command.weapon is None:
        raise ValueError("an anti-tank shot needs a weapon")
    weapon = state.units[command.weapon]
    hex_ref = command.hex
    if hex_ref is None or unit.hex is None:
        raise ValueError("an anti-tank shot needs a target hex")
    vehicle = r28_vehicles.vehicle_in(state, hex_ref)
    if vehicle is None:
        raise ValueError("no vehicle stands in that hex")
    weapon_class = ctx.types[weapon.type_key].weapon_class
    column = KILL_COLUMN[weapon_class]
    changed = {weapon.id: state.units[weapon.id].with_(fired=True)}
    # A counted weapon (panzerfaust, bazooka) may fire again until the per-turn count is
    # spent. Marking the squad fired here would stop the second shot.
    if weapon_class not in SHOTS_FOR_EACH_TURN:
        changed[unit.id] = state.units[unit.id].with_(fired=True)
    state = state.with_units(changed)
    state = state.with_(at_shots=state.at_shots + ((unit.id, weapon_class),))
    events: list[Event] = []
    hit = True
    if weapon_class != CLASS_FLAMETHROWER:
        state, hit, ev = roll_handheld(ctx, state, unit, weapon, vehicle, phase)
        events.extend(ev)
    else:
        events.append(
            Event(RULE_37_2, "flamethrower_hit", {"unit": unit.id, "weapon": weapon.id, "vehicle": vehicle.id})
        )
    if weapon_class == CLASS_PANZERFAUST:
        # Rule 37.3: the counter is removed after use, whatever the result.
        state = state.with_unit(state.units[weapon.id].with_(eliminated=True, carrier=None, hex=None))
        events.append(Event(RULE_37_3, "panzerfaust_used", {"weapon": weapon.id}))
    if not hit:
        return state, events
    state, kill = r33_afv_combat.roll_kill(ctx, state, unit.hex, vehicle, column)
    events.append(r33_afv_combat.kill_event(unit.id, vehicle, kill))
    if kill.killed:
        state, ev = r33_afv_combat.destroy(ctx, state, vehicle.id, f"rule 37 {weapon_class}")
        events.extend(ev)
    elif vehicle.immobilized:
        # Rule 39.3: a hit on a vehicle that is already immobilized sends its crew through
        # the morale check again.
        state, ev = r33_afv_combat.crew_abandons(ctx, state, vehicle.id, "rule 39.3")
        events.extend(ev)
    return state, events


def roll_handheld(
    ctx: ArmorContext, state: State, unit: Unit, weapon: Unit, vehicle: Unit, phase: str
) -> tuple[State, bool, list[Event]]:
    """Rules 37.31 and 37.41 with rule 37.34: the to-hit roll of a rocket."""
    weapon_class = ctx.types[weapon.type_key].weapon_class
    chart = chart_for(ctx, weapon_class)
    if chart is None or unit.hex is None or vehicle.hex is None:
        return state, False, []
    distance = geometry.distance(unit.hex, vehicle.hex)
    after_movement = phase == PHASE_ADVANCING_FIRE and unit.moved
    needed = chart.number(distance, after_movement)
    leader_mod, leader_id = r15_leadership.modifier_for_check(state, ctx.types, unit)
    # Rules 37.31 and 37.41: the terrain modifier for a vehicle behind a wall goes on the
    # to-hit roll and never on the kill roll.
    terrain = 2 if r33_afv_combat.hull_down(ctx, state, unit.hex, vehicle) else 0
    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    adjusted = raw + leader_mod + terrain
    hit = needed is not None and adjusted <= needed
    rule = RULE_37_31 if weapon_class == CLASS_PANZERFAUST else RULE_37_41
    events = [
        Event(
            rule,
            "at_to_hit",
            {
                "unit": unit.id,
                "weapon": weapon.id,
                "vehicle": vehicle.id,
                "dice": list(dice),
                "leadership": leader_mod,
                "leader": leader_id,
                "hull_down": bool(terrain),
                "adjusted": adjusted,
                "needed": needed,
                "range": distance,
                "after_movement": after_movement,
                "hit": hit,
            },
        )
    ]
    if weapon_class == CLASS_BAZOOKA and raw >= BAZOOKA_SPENT:
        state = state.with_unit(state.units[weapon.id].with_(eliminated=True, carrier=None, hex=None))
        events.append(Event(RULE_37_45, "bazooka_spent", {"weapon": weapon.id, "roll": raw}))
    return state, hit, events


def flamethrower_infantry_halves() -> int:
    """Rule 37.2: the same roll again on the twenty firepower column, in halves."""
    return FLAMETHROWER_FIREPOWER * 2


def inside_a_vehicle(state: State, unit: Unit) -> bool:
    """Rule 37.37 and rule 37.48: a rocket is not fired from inside a vehicle."""
    return unit.riding
