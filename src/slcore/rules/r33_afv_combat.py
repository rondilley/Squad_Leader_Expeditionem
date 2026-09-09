"""Rule 33, AFV combat, with rules 38, 39, 40, and 41 that hang from it.

Combat with the main armament is two steps (rule 33.3). The to-hit table says whether the
shell reached the target. The kill table says whether it went through the armour. Both
numbers are roll-or-less numbers on two dice.

Three things ride on the same to-hit roll. An unmodified twelve puts the gun out of order
(rule 38.1). An unmodified two can hit even when the number needed is below two, with a
third die (rule 33.32). A hit on infantry goes to the Infantry Fire Table instead of the
kill table (rule 34.2), which `r34_afv_vs_infantry` does.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from slcore import geometry
from slcore.events import Event
from slcore.game import (
    PHASE_ADVANCING_FIRE,
    PHASE_DEFENSIVE_FIRE,
    PHASE_PREP_FIRE,
    State,
)
from slcore.geometry import HexRef
from slcore.los_cache import LosTable
from slcore.los_eval import thread_hexes
from slcore.rng import roll_2d6, roll_die
from slcore.rules import r28_vehicles, r31_transport, r32_afv_cover
from slcore.state import Board, HexsideRule
from slcore.tabledata import ArmorTables, IftTable
from slcore.units import Unit, UnitType

RULE_33_2 = "33.2"
RULE_33_3 = "33.3"
RULE_33_31 = "33.31"
RULE_33_32 = "33.32"
RULE_33_33 = "33.33"
RULE_33_34 = "33.34"
RULE_33_4 = "33.4"
RULE_33_41 = "33.41"
RULE_33_5 = "33.5"
RULE_33_6 = "33.6"
RULE_33_7 = "33.7"
RULE_33_8 = "33.8"
RULE_33_9 = "33.9"
RULE_38_1 = "38.1"
RULE_38_2 = "38.2"
RULE_39_2 = "39.2"
RULE_39_3 = "39.3"
RULE_40_1 = "40.1"
RULE_41_1 = "41.1"

MALFUNCTION_ROLL = 12
POSSIBLE_HIT_ROLL = 2
THIRD_DIE_LIMIT = 6
LONG_RANGE_B = 6
LONG_RANGE_C = 12

AMMO_AP = "ap"
AMMO_HE = "he"


@dataclass(frozen=True)
class ArmorContext:
    """The static things the armor rules read. It has no state and no side effects."""

    board: Board
    hexsides: Mapping[str, HexsideRule]
    types: Mapping[str, UnitType]
    armor: ArmorTables
    ift: IftTable
    los: LosTable


def traced(ctx: ArmorContext, firer: HexRef, target: HexRef) -> tuple[HexRef, ...]:
    """The hexes between the firer and the target, in order."""
    return thread_hexes(ctx.los, firer, target)


# ---------------------------------------------------------------- the to-hit modifiers


def hull_down(ctx: ArmorContext, state: State, firer: HexRef, target: Unit) -> bool:
    """Rule 41.1 with PR-23: behind a wall, or behind a wreck on the traced path."""
    if target.hex is None or target.hex == firer:
        return False
    path = traced(ctx, firer, target.hex)
    if r32_afv_cover.hull_down_behind_wreck(ctx.board, state, path, firer, target.hex):
        return True
    for side in r28_vehicles.crossed_hexsides(target.hex, firer):
        if ctx.board.hexside(target.hex, side) == "wall":
            return True
    return False


def hit_cases(
    ctx: ArmorContext,
    state: State,
    firer: Unit,
    target_hex: HexRef,
    phase: str,
    target_moved: bool,
    concealed: bool,
) -> tuple[str, ...]:
    """Rule 33.31: the cases that apply to this shot, in order.

    Rule 33.32 makes them cumulative with two limits. Case C replaces case B, because a
    target beyond twelve hexes is also beyond six. The penalty for a pivot and the penalty
    for a move to a new hex are not cumulative either, so a vehicle that entered a new hex
    reads case F and not case E.
    """
    if firer.hex is None:
        return ()
    kind = ctx.types[firer.type_key]
    distance = geometry.distance(firer.hex, target_hex)
    cases: list[str] = []
    if phase == PHASE_DEFENSIVE_FIRE and target_moved:
        cases.append("A")
    if kind.gun_low_velocity:
        if distance > LONG_RANGE_C:
            cases.append("C")
        elif distance > LONG_RANGE_B:
            cases.append("B")
    if kind.is_turreted and not r28_vehicles.in_covered_arc(firer.hex, firer.facing, target_hex):
        cases.append("D")
    if phase == PHASE_ADVANCING_FIRE:
        if firer.moved:
            cases.append("F")
        elif firer.pivoted:
            cases.append("E" if kind.is_turreted else "G")
    if phase == PHASE_DEFENSIVE_FIRE and firer.pivoted and not kind.is_turreted:
        cases.append("I")
    if concealed:
        cases.append("H")
    if distance == 1:
        cases.append("J")
    elif distance == 0:
        cases.append("K")
    return tuple(cases)


def may_fire_main(ctx: ArmorContext, state: State, firer: Unit, phase: str) -> bool:
    """Rules 33.2, 38.1, and 39.4: whether the main armament can fire in this phase."""
    kind = ctx.types[firer.type_key]
    if kind.gun <= 0 or firer.wreck or firer.eliminated or firer.hex is None:
        return False
    if firer.malfunction or firer.disabled:
        return False
    if firer.overran:
        # Rule 35.9: a vehicle that overran fires nothing in that player turn.
        return False
    limit = 2 if kind.fires_twice else 1
    if firer.gun_shots >= limit:
        return False
    if phase == PHASE_ADVANCING_FIRE and firer.prep_fired:
        return False
    if phase != PHASE_ADVANCING_FIRE and phase != PHASE_DEFENSIVE_FIRE and firer.moved:
        # Rule 33.2: a vehicle that fires in the Prep Fire Phase may not move, and the
        # engine enforces the other half of the trade by keeping a mover out of prep fire.
        return False
    if not kind.is_turreted and firer.moved and phase == PHASE_ADVANCING_FIRE:
        # Rule 33.31: a self-propelled gun cannot fire its main armament in the same player
        # turn it moves to a new hex.
        return False
    return True


def may_fire_mg(ctx: ArmorContext, firer: Unit, phase: str) -> bool:
    """Rule 34.3 with rule 38.2: whether a machine gun factor is available."""
    kind = ctx.types[firer.type_key]
    if kind.mg_ca <= 0 and kind.mg_360 <= 0:
        return False
    if firer.wreck or firer.eliminated or firer.hex is None or firer.overran:
        return False
    if firer.mg_malfunction or firer.mg_disabled or firer.mg_fired:
        return False
    if phase == PHASE_PREP_FIRE and firer.moved:
        return False
    if phase == PHASE_ADVANCING_FIRE and firer.prep_fired:
        return False
    return True


# Rule 28.4: every machine gun of a vehicle has a normal range of eight hexes, and rule
# 9.2 lets a machine gun reach twice that at half strength.
MG_RANGE = 8


def mg_firepower(ctx: ArmorContext, firer: Unit, target_hex: HexRef, main_target: HexRef | None) -> int:
    """Rules 28.4, 34.7, and 9.2: the machine gun factors that reach this hex.

    The left number fires only in the covered arc and only at the hex the main gun fired
    at. The right number fires in any direction. Rule 34.7 halves the left number when the
    vehicle moved or turned, and the right number when it moved to a new hex. Rule 9.2
    halves both again past the normal range of eight hexes and stops them past sixteen.
    """
    if firer.hex is None:
        return 0
    distance = geometry.distance(firer.hex, target_hex)
    if distance > 2 * MG_RANGE:
        return 0
    long_range = distance > MG_RANGE
    kind = ctx.types[firer.type_key]
    total = 0
    if kind.mg_ca and r28_vehicles.in_covered_arc(firer.hex, firer.facing, target_hex):
        if main_target is None or main_target == target_hex:
            value = kind.mg_ca
            if firer.moved or firer.pivoted:
                value //= 2
            total += value
    if kind.mg_360:
        value = kind.mg_360
        if firer.moved:
            value //= 2
        total += value
    if long_range:
        total //= 2
    return total


# --------------------------------------------------------------------- the to-hit roll


@dataclass(frozen=True)
class ToHit:
    hit: bool
    raw: int
    adjusted: int
    needed: int | None
    cases: tuple[str, ...]
    modifier: int
    third_die: int | None
    malfunction: bool
    row: str


def roll_to_hit(
    ctx: ArmorContext,
    state: State,
    firer: Unit,
    target_hex: HexRef,
    row: str,
    cases: tuple[str, ...],
    extra_modifier: int = 0,
) -> tuple[State, ToHit]:
    """Rules 33.3, 33.31, 33.32, and 38.1 in one roll."""
    if firer.hex is None:
        raise ValueError("a firer must be on the board")
    nationality = ctx.types[firer.type_key].nationality
    distance = geometry.distance(firer.hex, target_hex)
    needed = ctx.armor.to_hit(row, distance, nationality)
    modifier = ctx.armor.hit_modifier(cases) + extra_modifier
    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    adjusted = raw + modifier
    third: int | None = None
    hit = needed is not None and adjusted <= needed
    if needed is not None and raw == POSSIBLE_HIT_ROLL and needed < POSSIBLE_HIT_ROLL:
        # Rule 33.32: an unmodified two can still hit. Add one for each number below two
        # that the shot needed, and a total under six is a hit.
        rng, third = roll_die(state.rng)
        state = state.with_(rng=rng)
        hit = third + (POSSIBLE_HIT_ROLL - needed) < THIRD_DIE_LIMIT
    return state, ToHit(
        hit=hit,
        raw=raw,
        adjusted=adjusted,
        needed=needed,
        cases=cases,
        modifier=modifier,
        third_die=third,
        malfunction=raw == MALFUNCTION_ROLL,
        row=row,
    )


def to_hit_event(firer: Unit, target_hex: HexRef, result: ToHit) -> Event:
    return Event(
        RULE_33_3,
        "to_hit",
        {
            "unit": firer.id,
            "target": geometry.hex_id(*target_hex),
            "row": result.row,
            "raw": result.raw,
            "modifier": result.modifier,
            "cases": list(result.cases),
            "adjusted": result.adjusted,
            "needed": result.needed,
            "third_die": result.third_die,
            "hit": result.hit,
        },
    )


def mark_gun_fired(state: State, firer: Unit, result: ToHit) -> tuple[State, list[Event]]:
    """Rules 33.2 and 38.1: count the shot and mark the gun when it broke."""
    unit = state.units[firer.id]
    changed = unit.with_(gun_shots=unit.gun_shots + 1, fired=True)
    events: list[Event] = []
    if result.malfunction:
        changed = changed.with_(malfunction=True)
        events.append(Event(RULE_38_1, "gun_malfunction", {"unit": firer.id}))
    return state.with_unit(changed), events


# ----------------------------------------------------------------------- the kill roll


@dataclass(frozen=True)
class Kill:
    killed: bool
    raw: int
    adjusted: int
    needed: int | None
    face: str
    column: str
    modifier: int


def kill_column_for(ctx: ArmorContext, firer: Unit, ammunition: str) -> str:
    kind = ctx.types[firer.type_key]
    if kind.gun_he_only and ammunition == AMMO_AP:
        raise ValueError("rule 33.6: an overscored gun fires high explosive only")
    return ctx.armor.gun_kill_column(kind.gun, ammunition)


def roll_kill(
    ctx: ArmorContext, state: State, firer_hex: HexRef, target: Unit, column: str
) -> tuple[State, Kill]:
    """Rules 33.4 and 33.41: does the shell go through the armour."""
    face = r28_vehicles.target_face(target, firer_hex, ctx.types)
    armor_key = ctx.types[target.type_key].armor_key
    needed = ctx.armor.kill_number(face, column, armor_key)
    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    modifier = ctx.armor.kill_number_modifiers.get(armor_key, 0)
    killed = needed is not None and raw <= needed
    return state, Kill(
        killed=killed,
        raw=raw,
        adjusted=raw,
        needed=needed,
        face=face,
        column=column,
        modifier=modifier,
    )


def kill_event(firer_id: int, target: Unit, result: Kill) -> Event:
    return Event(
        RULE_33_4,
        "kill_roll",
        {
            "unit": firer_id,
            "target": target.id,
            "face": result.face,
            "column": result.column,
            "raw": result.raw,
            "needed": result.needed,
            "armor_modifier": result.modifier,
            "killed": result.killed,
        },
    )


# ------------------------------------------------------------------ death and its crew


def crew_for(state: State, vehicle_id: int) -> Unit | None:
    """The crew counter the engine set aside for this vehicle (rule 33.9)."""
    for unit in state.units:
        if unit.from_wreck == vehicle_id and not unit.eliminated and unit.hex is None:
            return unit
    return None


def destroy(
    ctx: ArmorContext, state: State, vehicle_id: int, cause: str, close_combat: bool = False
) -> tuple[State, list[Event]]:
    """Rules 40.1, 33.9, 31.8, and 32.5 when a vehicle dies.

    The counter turns over and becomes a wreck. Rule 31.8 kills the passengers. Rule 32.5
    puts the infantry on foot beneath it through a morale check. Rule 33.9 gives the crew a
    chance to get out, except after close combat.
    """
    from slcore.rules import r12_morale  # local: r12_morale imports no armor rule

    events: list[Event] = [Event(RULE_40_1, "wreck", {"unit": vehicle_id, "cause": cause})]
    beneath = r32_afv_cover.morale_check_after_loss(state, vehicle_id)
    state, gone = r31_transport.kill_passengers(state, vehicle_id)
    events.extend(gone)
    state = state.with_unit(
        state.units[vehicle_id].with_(
            wreck=True,
            immobilized=True,
            crew_exposed=False,
            malfunction=False,
            mg_malfunction=False,
        )
    )
    if not close_combat:
        state, ev = crew_escape(ctx, state, vehicle_id)
        events.extend(ev)
    for unit_id in beneath:
        state, ev = r12_morale.morale_check(state, ctx.types, state.units[unit_id], 0, "vehicle lost")
        events.extend(ev)
    return state, events


def crew_escape(ctx: ArmorContext, state: State, vehicle_id: int) -> tuple[State, list[Event]]:
    """Rule 33.9: two dice against the survival number on the wreck side."""
    vehicle = state.units[vehicle_id]
    survival = ctx.types[vehicle.type_key].survival
    if survival <= 0 or vehicle.hex is None:
        return state, []
    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    crew = crew_for(state, vehicle_id)
    made_it = raw <= survival and crew is not None
    events = [
        Event(
            RULE_33_9,
            "crew_survival",
            {
                "vehicle": vehicle_id,
                "dice": list(dice),
                "survival": survival,
                "survived": made_it,
                "crew": None if crew is None else crew.id,
            },
        )
    ]
    if made_it and crew is not None:
        state = state.with_unit(crew.with_(hex=vehicle.hex, moved=True))
    return state, events


def crew_abandons(ctx: ArmorContext, state: State, vehicle_id: int, cause: str) -> tuple[State, list[Event]]:
    """Rules 39.2 and 39.3: the crew of an immobilized vehicle checks its morale.

    A pass keeps the crew at its weapons. A failure does not break the crew, but it leaves
    the vehicle, which becomes a wreck with a crew counter on it.
    """
    from slcore.rules import r12_morale

    vehicle = state.units[vehicle_id]
    crew = crew_for(state, vehicle_id)
    if crew is None or vehicle.hex is None or vehicle.wreck:
        return state, []
    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    morale = r12_morale.morale_value(ctx.types, crew)
    passed = raw <= morale
    events = [
        Event(
            RULE_39_2,
            "crew_morale",
            {"vehicle": vehicle_id, "crew": crew.id, "dice": list(dice), "morale": morale, "stayed": passed, "cause": cause},
        )
    ]
    if passed:
        return state, events
    state = state.with_unit(state.units[vehicle_id].with_(wreck=True, immobilized=True))
    state = state.with_unit(state.units[crew.id].with_(hex=vehicle.hex, moved=True))
    events.append(Event(RULE_39_2, "crew_abandons", {"vehicle": vehicle_id, "crew": crew.id}))
    return state, events


def immobilize(ctx: ArmorContext, state: State, vehicle_id: int, cause: str) -> tuple[State, list[Event]]:
    """Rule 39: mark the vehicle and send its crew through the morale check of rule 39.2."""
    vehicle = state.units[vehicle_id]
    if vehicle.wreck or vehicle.immobilized:
        return state, []
    state = state.with_unit(vehicle.with_(immobilized=True))
    events = [Event("39", "immobilized", {"unit": vehicle_id, "cause": cause})]
    state, ev = crew_abandons(ctx, state, vehicle_id, cause)
    events.extend(ev)
    return state, events
