"""Rule 36, infantry against armoured fighting vehicles with no anti-tank weapon.

Two ways in. In the Defensive Fire Phase a squad in cover that the vehicle drove past may
try to immobilize it (rule 36.1). In the Close Combat Phase infantry that advanced onto
the vehicle may destroy it (rule 36.2).

Both start with the Pre-AFV Attack Morale Check of rule 36.11. Failing it costs nothing:
the unit simply does not make the attack.
"""

from __future__ import annotations

from typing import Mapping

from slcore import geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import State
from slcore.rng import roll_2d6
from slcore.rules import r10_resolution, r15_leadership, r28_vehicles, r33_afv_combat
from slcore.rules.r10_resolution import FireContext
from slcore.rules.r33_afv_combat import ArmorContext
from slcore.state import Board
from slcore.units import KIND_LEADER, Unit, UnitType

RULE_36_1 = "36.1"
RULE_36_11 = "36.11"
RULE_36_12 = "36.12"
RULE_36_13 = "36.13"
RULE_36_2 = "36.2"
RULE_36_21 = "36.21"
RULE_36_22 = "36.22"
RULE_36_23 = "36.23"
RULE_36_24 = "36.24"
RULE_36_3 = "36.3"
RULE_36_4 = "36.4"

LEADER_KILL_NUMBER = 2
LARGE_BUILDING = 3


def location_key(board: Board, types: Mapping[str, UnitType], unit: Unit) -> str | None:
    """Rule 36.12: which row of the chart this attacker reads, or None for open ground."""
    if unit.hex is None:
        return None
    hexagon = board.hex(unit.hex)
    kind = hexagon.terrain
    if unit.kind == KIND_LEADER:
        return None if kind == "open" else "leader_in_cover"
    if kind == "wheat":
        return "squad_in_wheat"
    if kind == "shellhole":
        return "squad_in_small_building"
    if board.is_building_kind(kind):
        size = hexagon.building.size if hexagon.building is not None else 1
        return "squad_in_woods_or_large_building" if size >= LARGE_BUILDING else "squad_in_small_building"
    if kind == "woods":
        return "squad_in_woods_or_large_building"
    return None


def attackers_for(
    board: Board, state: State, types: Mapping[str, UnitType], vehicle: Unit, player: int
) -> list[Unit]:
    """Rule 36.1: unbroken squads and leaders next to the vehicle, in cover.

    Rule 34.8 widens this: a vehicle with its crew exposed can be fired on from any hex in
    any fire phase, so distance and cover do not hold the attacker back.
    """
    if vehicle.hex is None:
        return []
    out: list[Unit] = []
    for unit in state.player_units(player):
        if not unit.is_infantry or unit.hex is None or unit.broken or unit.riding:
            continue
        if unit.fired or unit.prep_fired or unit.directed or unit.carrier is not None:
            continue
        if vehicle.crew_exposed:
            out.append(unit)
            continue
        if not board.adjacent(unit.hex, vehicle.hex):
            continue
        if location_key(board, types, unit) is None:
            continue
        out.append(unit)
    return out


def legal_attacks(
    board: Board, state: State, types: Mapping[str, UnitType], player: int
) -> list[Command]:
    """Rule 36.1: one command for each squad or leader that may try the vehicle."""
    out: list[Command] = []
    for vehicle in r28_vehicles.vehicles(state, 1 - player):
        if vehicle.hex is None or vehicle.wreck:
            continue
        for unit in attackers_for(board, state, types, vehicle, player):
            out.append(Command("afv_attack", units=(unit.id,), hex=vehicle.hex))
    return out


def pre_attack_check(
    ctx: ArmorContext, state: State, unit: Unit
) -> tuple[State, bool, list[Event]]:
    """Rule 36.11: a normal morale check with no penalty for failing it."""
    from slcore.rules import r12_morale

    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    leader_mod, leader_id = r15_leadership.modifier_for_check(state, ctx.types, unit)
    adjusted = raw + leader_mod
    morale = r12_morale.morale_value(ctx.types, unit)
    passed = adjusted <= morale
    return (
        state,
        passed,
        [
            Event(
                RULE_36_11,
                "pre_afv_check",
                {
                    "unit": unit.id,
                    "dice": list(dice),
                    "leadership": leader_mod,
                    "leader": leader_id,
                    "adjusted": adjusted,
                    "morale": morale,
                    "passed": passed,
                },
            )
        ],
    )


def apply_defensive_attack(
    ctx: ArmorContext,
    fire_ctx: FireContext,
    state: State,
    command: Command,
    phase: str,
) -> tuple[State, list[Event]]:
    """Rules 36.11, 36.12, and 36.13: the check, the immobilize roll, and the passengers."""
    unit = state.units[command.units[0]]
    hex_ref = command.hex
    if hex_ref is None:
        raise ValueError("an attack on a vehicle needs the vehicle's hex")
    vehicle = r28_vehicles.vehicle_in(state, hex_ref)
    if vehicle is None:
        raise ValueError("no vehicle stands in that hex")
    state = state.with_unit(state.units[unit.id].with_(fired=True))
    state, passed, events = pre_attack_check(ctx, state, unit)
    if not passed:
        return state, events
    location = location_key(ctx.board, ctx.types, unit)
    needed = ctx.armor.pre_afv_number(location) if location else LEADER_KILL_NUMBER
    leader_mod, leader_id = r15_leadership.modifier_for_check(state, ctx.types, unit)
    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    adjusted = raw + leader_mod
    stopped = adjusted <= needed
    events.append(
        Event(
            RULE_36_12,
            "immobilize_attempt",
            {
                "unit": unit.id,
                "vehicle": vehicle.id,
                "dice": list(dice),
                "leadership": leader_mod,
                "leader": leader_id,
                "adjusted": adjusted,
                "needed": needed,
                "location": location,
                "immobilized": stopped,
            },
        )
    )
    if stopped:
        state, ev = r33_afv_combat.immobilize(ctx, state, vehicle.id, "rule 36.12")
        events.extend(ev)
        return state, events
    # Rule 36.13: the same dice roll goes on the Infantry Fire Table against the
    # passengers on top of the counter. The infantry on foot beneath it are not touched.
    state, ev = passengers_hit(ctx, fire_ctx, state, unit, vehicle, raw, phase)
    events.extend(ev)
    return state, events


def passengers_hit(
    ctx: ArmorContext,
    fire_ctx: FireContext,
    state: State,
    unit: Unit,
    vehicle: Unit,
    raw: int,
    phase: str,
) -> tuple[State, list[Event]]:
    """Rule 36.13: the failed immobilize roll is read again against the passengers."""
    from slcore.rules import r32_afv_cover

    if vehicle.hex is None or not r28_vehicles.passengers_of(state, vehicle.id):
        return state, []
    if not r32_afv_cover.passengers_only(state, vehicle.hex):
        return state, []
    halves = ctx.types[unit.type_key].firepower * 2
    if halves <= 0:
        return state, []
    drm, _rule = r32_afv_cover.target_modifier(
        ctx.board, state, ctx.types, unit.hex or vehicle.hex, vehicle.hex
    )
    events = [
        Event(
            RULE_36_13,
            "passenger_fire",
            {
                "unit": unit.id,
                "vehicle": vehicle.id,
                "firepower": halves // 2,
                "column": r10_resolution.column_label(ctx.ift, halves // 2),
                "roll": raw,
                "adjusted": raw + drm,
            },
        )
    ]
    state, hit = r10_resolution.apply_to_hex(
        fire_ctx, state, vehicle.hex, halves, raw, drm, phase, unit.player
    )
    events.extend(hit)
    return state, events


# ------------------------------------------------------------------- the close combat


def legal_close_combat(
    board: Board, state: State, types: Mapping[str, UnitType], player: int
) -> list[Command]:
    """Rule 36.2: infantry that advanced onto the vehicle attacks it in close combat."""
    out: list[Command] = []
    for vehicle in r28_vehicles.vehicles(state, 1 - player):
        if vehicle.hex is None or vehicle.wreck:
            continue
        # Rule 36.22: enemy infantry in the hex takes precedence, and the close combat
        # rules of rule 20 settle that fight instead.
        if any(u.player != player and u.is_infantry for u in state.units_in(vehicle.hex)):
            continue
        for unit in state.units_in(vehicle.hex):
            if unit.player != player or not unit.is_infantry or unit.broken or unit.fired:
                continue
            out.append(Command("cc_afv", units=(unit.id,), hex=vehicle.hex))
    return out


def apply_close_combat(
    ctx: ArmorContext, state: State, command: Command
) -> tuple[State, list[Event]]:
    """Rules 36.21, 36.23, and 36.24: the check, the kill roll, and the walk back."""
    unit = state.units[command.units[0]]
    hex_ref = command.hex
    if hex_ref is None:
        raise ValueError("a close combat attack on a vehicle needs the vehicle's hex")
    vehicle = r28_vehicles.vehicle_in(state, hex_ref)
    if vehicle is None:
        raise ValueError("no vehicle stands in that hex")
    state = state.with_unit(state.units[unit.id].with_(fired=True))
    state, passed, events = pre_attack_check(ctx, state, unit)
    if not passed:
        state, back = walk_back(state, unit)
        events.extend(back)
        return state, events
    leader_mod, leader_id = r15_leadership.modifier_for_check(state, ctx.types, unit)
    needed = (
        LEADER_KILL_NUMBER if unit.kind == KIND_LEADER else ctx.types[unit.type_key].firepower
    )
    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    adjusted = raw + leader_mod
    killed = adjusted <= needed
    events.append(
        Event(
            RULE_36_23,
            "close_combat_vs_afv",
            {
                "unit": unit.id,
                "vehicle": vehicle.id,
                "dice": list(dice),
                "leadership": leader_mod,
                "leader": leader_id,
                "adjusted": adjusted,
                "needed": needed,
                "killed": killed,
            },
        )
    )
    if killed:
        state, ev = r33_afv_combat.destroy(ctx, state, vehicle.id, "close combat", close_combat=True)
        events.extend(ev)
        return state, events
    state, back = walk_back(state, unit)
    events.extend(back)
    return state, events


def walk_back(state: State, unit: Unit) -> tuple[State, list[Event]]:
    """Rule 36.24: an attack that fails puts the unit back where it advanced from."""
    if unit.returned_from is None:
        return state, []
    dst = unit.returned_from
    changed = {unit.id: state.units[unit.id].with_(hex=dst)}
    for weapon in state.carried_by(unit.id):
        changed[weapon.id] = weapon.with_(hex=dst)
    return state.with_units(changed), [
        Event(RULE_36_24, "returned", {"unit": unit.id, "hex": geometry.hex_id(*dst)})
    ]
