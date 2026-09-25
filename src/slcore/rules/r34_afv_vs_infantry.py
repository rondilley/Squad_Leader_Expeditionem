"""Rule 34, an armoured fighting vehicle against infantry.

The main armament first rolls on the to-hit table (rule 34.2). A hit is worth the
firepower of the gun's calibre on the Infantry Fire Table, and the effect roll takes the
terrain and situation modifiers of rule 11. The machine guns roll again on their own
(rule 34.3), and they roll even when the main armament missed (rule 34.4).

Rule 34.8 marks a vehicle that used its all-round machine gun with a crew exposed
counter. Infantry may then fire at the vehicle from any hex in any fire phase.
"""

from __future__ import annotations

from typing import Mapping

from slcore import actions, geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import FireGroup, State
from slcore.geometry import HexRef
from slcore.rng import roll_2d6
from slcore.rules import r10_resolution, r28_vehicles, r31_transport, r32_afv_cover, r33_afv_combat
from slcore.rules.r10_resolution import FireContext
from slcore.rules.r33_afv_combat import AMMO_AP, AMMO_HE, AMMO_HEAT, ArmorContext
from slcore.state import Board
from slcore.tabledata import RESULT_KIA, IftTable
from slcore.units import Unit, UnitType

RULE_34_1 = "34.1"
RULE_34_2 = "34.2"
RULE_34_3 = "34.3"
RULE_34_4 = "34.4"
RULE_34_5 = "34.5"
RULE_34_6 = "34.6"
RULE_34_7 = "34.7"
RULE_34_8 = "34.8"
RULE_34_9 = "34.9"
RULE_38_2 = "38.2"

# Rule 34.5: a hit at point blank range is worth twice the firepower.
POINT_BLANK = 1
# Rule 34.9: canister has a range of three hexes, a penetration factor of three, and the
# firepower of twenty infantry factors. A to-hit roll of seven or more spends the rounds.
CANISTER_RANGE = 3
CANISTER_FIREPOWER = 20
CANISTER_PENETRATION = 3
CANISTER_SPENT_ROLL = 7
AMMO_CANISTER = "canister"
MG_MALFUNCTION_ROLL = 12
# Rule 34.8: fire at an exposed crew takes plus two for the wall of the hull.
CREW_EXPOSED_MODIFIER = 2


def firepower_halves(ctx: ArmorContext, firer: Unit, target: HexRef) -> int:
    """Rule 34.2 with rule 34.5: the Infantry Fire Table firepower of one hit, in halves."""
    if firer.hex is None:
        return 0
    calibre = ctx.types[firer.type_key].gun
    halves = ctx.armor.gun_firepower(calibre) * 2
    if geometry.distance(firer.hex, target) <= POINT_BLANK:
        halves *= 2
    return halves


def moving_target(state: State, target: HexRef, firer_player: int) -> bool:
    """Rule 34.6: infantry of the other side in the hex that moved this player turn."""
    return any(u.moved for u in state.infantry_in(target) if u.player != firer_player)


def effect_modifier(
    ctx: ArmorContext, fire_ctx: FireContext, state: State, firer: Unit, target: HexRef, phase: str
) -> tuple[int, list[dict]]:
    """Rule 11.1: the modifiers that apply to every unit in the target hex.

    Rule 34.6, the minus two for infantry that moved in the open, is per unit. `apply_to_hex`
    adds it, and it adds it one time. A second add here put the modifier on twice.
    """
    del ctx, phase
    group = FireGroup(target, ((firer.id, None),), None)
    return r10_resolution.common_modifier(fire_ctx, state, group)


def fire_main(
    ctx: ArmorContext,
    fire_ctx: FireContext,
    state: State,
    firer: Unit,
    target: HexRef,
    phase: str,
    ammunition: str = AMMO_HE,
) -> tuple[State, list[Event]]:
    """Rule 34.2: the main armament against the infantry of one hex.

    Case H of rule 33.31 reads a counter of the target side only. A counter of the
    firer's own side in the hex does not conceal the enemy in it.
    """
    concealed = state.enemy_counter_in(target, firer.player)
    canister = ammunition == AMMO_CANISTER
    row = r28_vehicles.infantry_to_hit_row(ctx.board, target)
    cases = r33_afv_combat.hit_cases(
        ctx, state, firer, target, phase, moving_target(state, target, firer.player), concealed
    )
    state, result = r33_afv_combat.roll_to_hit(ctx, state, firer, target, row, cases)
    events = [r33_afv_combat.to_hit_event(firer, target, result)]
    state, marked = r33_afv_combat.mark_gun_fired(state, firer, result)
    events.extend(marked)
    if canister:
        state, spent = spend_canister(state, firer, result.raw)
        events.extend(spent)
    if not result.hit:
        return state, events
    halves = CANISTER_FIREPOWER * 2 if canister else firepower_halves(ctx, firer, target)
    state, effect = resolve_effect(
        ctx,
        fire_ctx,
        state,
        firer,
        target,
        halves,
        phase,
        RULE_34_2,
        CANISTER_PENETRATION if canister else 0,
    )
    events.extend(effect)
    return state, events


def open_ground_cancelled(
    ctx: ArmorContext, fire_ctx: FireContext, state: State, firer: Unit, target: HexRef, phase: str
) -> bool:
    """Rules 32.2 and 32.7: a vehicle that is the cover takes the open-ground modifier away."""
    if not fire_ctx.vehicles_in_play:
        return False
    group = FireGroup(target, ((firer.id, None),), None)
    return r32_afv_cover.group_cancels_open_ground(ctx.board, ctx.los, state, group, phase)


def resolve_effect(
    ctx: ArmorContext,
    fire_ctx: FireContext,
    state: State,
    firer: Unit,
    target: HexRef,
    halves: int,
    phase: str,
    rule_id: str,
    penetration: int = 0,
) -> tuple[State, list[Event]]:
    """One roll on the Infantry Fire Table for a hit that is already secured."""
    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    drm, parts = effect_modifier(ctx, fire_ctx, state, firer, target, phase)
    events = [
        Event(
            rule_id,
            "afv_fire",
            {
                "unit": firer.id,
                "target": geometry.hex_id(*target),
                "firepower": halves // 2,
                "column": r10_resolution.column_label(ctx.ift, halves // 2),
                "dice": list(dice),
                "modifiers": parts,
                "adjusted": raw + drm,
                "phase": phase,
            },
        )
    ]
    state, hit = r10_resolution.apply_to_hex(
        fire_ctx,
        state,
        target,
        halves,
        raw,
        drm,
        phase,
        firer.player,
        open_ground_cancelled=open_ground_cancelled(ctx, fire_ctx, state, firer, target, phase),
    )
    events.extend(hit)
    if penetration > 1 and firer.hex is not None:
        # Rule 34.9: canister keeps going for its penetration factor. The target hex
        # spent the first factor. The walk is the machine-gun walk of rule 17.5.
        group = FireGroup(target, ((firer.id, None),), None)
        state, pen = r10_resolution.penetrate(
            fire_ctx, state, group, halves, raw, phase, factor_limit=penetration
        )
        events.extend(pen)
    return state, events


def fire_mg(
    ctx: ArmorContext,
    fire_ctx: FireContext,
    state: State,
    firer: Unit,
    target: HexRef,
    phase: str,
) -> tuple[State, list[Event]]:
    """Rules 34.3, 34.4, and 34.7: the machine gun factors of the vehicle."""
    halves = r33_afv_combat.mg_firepower(ctx, firer, target, None) * 2
    if halves <= 0:
        return state, []
    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    drm, parts = effect_modifier(ctx, fire_ctx, state, firer, target, phase)
    events = [
        Event(
            RULE_34_3,
            "afv_mg_fire",
            {
                "unit": firer.id,
                "target": geometry.hex_id(*target),
                "firepower": halves // 2,
                "column": r10_resolution.column_label(ctx.ift, halves // 2),
                "dice": list(dice),
                "modifiers": parts,
                "adjusted": raw + drm,
                "phase": phase,
            },
        )
    ]
    marked = state.units[firer.id].with_(mg_fired=True, fired=True)
    if raw >= MG_MALFUNCTION_ROLL:
        # Rule 38.2: a twelve on the Infantry Fire Table puts every machine gun of the
        # vehicle out of order, the covered arc one and the all-round one together.
        marked = marked.with_(mg_malfunction=True)
        events.append(Event(RULE_38_2, "mg_malfunction", {"unit": firer.id, "roll": raw}))
    state = state.with_unit(marked)
    state, hit = r10_resolution.apply_to_hex(
        fire_ctx,
        state,
        target,
        halves,
        raw,
        drm,
        phase,
        firer.player,
        open_ground_cancelled=open_ground_cancelled(ctx, fire_ctx, state, firer, target, phase),
    )
    events.extend(hit)
    state, exposed = expose_crew(ctx, state, firer, target)
    events.extend(exposed)
    return state, events


def expose_crew(ctx: ArmorContext, state: State, firer: Unit, target: HexRef) -> tuple[State, list[Event]]:
    """Rule 34.8: the all-round machine gun puts a crew member out of the hatch."""
    if firer.hex is None:
        return state, []
    kind = ctx.types[firer.type_key]
    if not kind.mg_360:
        return state, []
    if kind.mg_ca and r28_vehicles.in_covered_arc(firer.hex, firer.facing, target):
        # The covered arc gun could have done this shot, so nobody had to lean out.
        return state, []
    return state.with_unit(state.units[firer.id].with_(crew_exposed=True)), [
        Event(RULE_34_8, "crew_exposed", {"unit": firer.id})
    ]


def exposed_vehicle_in(state: State, hex_ref: HexRef, firer_player: int) -> Unit | None:
    """Rule 34.8: a vehicle of the other side in this hex with its crew exposed.

    A hidden vehicle is on its owner's record and not on the board (rule 42.1), so it is
    never this target.
    """
    for unit in state.units_in(hex_ref):
        if unit.is_vehicle and unit.player != firer_player and unit.crew_exposed and not unit.wreck and not unit.hidden:
            return unit
    return None


def exposed_targets(state: State, player: int) -> list[HexRef]:
    """Rule 34.8 and PR-44: the hexes of the enemy vehicles whose crew is exposed."""
    return sorted(
        {
            u.hex
            for u in r28_vehicles.vehicles(state, 1 - player)
            if u.hex is not None and u.crew_exposed and not u.wreck and not u.hidden
        }
    )


def fire_at_exposed_crew(
    types: Mapping[str, UnitType],
    ift: IftTable,
    state: State,
    target: HexRef,
    firer_player: int,
    halves: int,
    raw: int,
    group_modifier: int,
    parts: list[dict],
) -> tuple[State, list[Event]]:
    """Rule 34.8 with PR-44: the roll of an infantry fire group read against an exposed crew.

    The group attacks the infantry of the hex as usual. The same roll then goes on the
    Infantry Fire Table against the crew, with plus two for the vehicle, the leadership and
    smoke of the group, and no terrain and no minus two for movement. A morale check
    result is ignored. A KIA sends the crew through the morale check of rule 39.2, and a
    failure abandons the vehicle.
    """
    vehicle = exposed_vehicle_in(state, target, firer_player)
    if vehicle is None:
        return state, []
    firepower = halves // 2
    adjusted = raw + CREW_EXPOSED_MODIFIER + group_modifier
    result = ift.lookup(firepower, adjusted)
    modifiers = [{"rule": RULE_34_8, "value": CREW_EXPOSED_MODIFIER, "cause": "the hull around the exposed crew"}]
    modifiers.extend(parts)
    events = [
        Event(
            RULE_34_8,
            "crew_fire",
            {
                "vehicle": vehicle.id,
                "target": geometry.hex_id(*target),
                "firepower": firepower,
                "roll": raw,
                "modifiers": modifiers,
                "adjusted": adjusted,
                "result": result,
            },
        )
    ]
    if result != RESULT_KIA:
        return state, events
    state, ev = r33_afv_combat.crew_check(types, state, vehicle.id, "a KIA on the exposed crew", RULE_34_8)
    events.extend(ev)
    return state, events


def spend_canister(state: State, firer: Unit, raw: int) -> tuple[State, list[Event]]:
    """Rule 34.92: a to-hit roll of seven or more leaves the gun with no canister."""
    if raw < CANISTER_SPENT_ROLL:
        return state, []
    return state.with_unit(state.units[firer.id].with_(canister_spent=True)), [
        Event(RULE_34_9, "canister_spent", {"unit": firer.id, "roll": raw})
    ]


def canister_available(ctx: ArmorContext, firer: Unit) -> bool:
    """Rule 34.9: only the German MkIVF1 has canister, and only until it runs out."""
    return ctx.types[firer.type_key].canister and not firer.canister_spent


def clear_exposure(state: State, player: int) -> tuple[State, list[Event]]:
    """Rule 34.8: the counter comes off at the end of the next enemy fire phase.

    The engine calls this at the end of each fire phase for the side that did not fire in
    it (PR-44). A counter that the side put on in its own earlier fire phase has then seen
    one fire phase of the enemy, and it is that phase that ends.
    """
    changed = {}
    events: list[Event] = []
    for vehicle in r28_vehicles.vehicles(state, player):
        if vehicle.crew_exposed:
            changed[vehicle.id] = vehicle.with_(crew_exposed=False)
            events.append(Event(RULE_34_8, "crew_inside", {"unit": vehicle.id}))
    return (state.with_units(changed) if changed else state), events


# ------------------------------------------------------------------ the command handlers (M3)
# The main gun fires at a vehicle by rule 33.3 or at infantry by this rule. This module
# imports rule 33, so the handler of the two shots is here.


@actions.action("afv_fire", unconceals=actions.CAUSE_FIRED)
def _on_afv_fire(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    """Rule 33.3 at a vehicle, or rule 34.2 at infantry."""
    extra = dict(command.extra)
    vehicle = state.units[command.units[0]]
    target = command.hex
    if target is None:
        raise ValueError("a vehicle shot needs a target hex")
    state, events = r31_transport.force_dismount(
        engine.board, state, vehicle.id, r31_transport.RULE_31_7, "the vehicle fired", charge=True
    )
    if str(extra.get("aim")) == "vehicle":
        state, ev = _gun_at_vehicle(engine.armor_ctx, engine.board, state, vehicle, target, str(extra.get("ammo", AMMO_AP)))
    else:
        state, ev = fire_main(
            engine.armor_ctx, engine.fire_ctx, state, vehicle, target, state.phase, str(extra.get("ammo", AMMO_HE))
        )
    events.extend(ev)
    return state, events


def _gun_at_vehicle(
    ctx: ArmorContext, board: Board, state: State, firer: Unit, target: HexRef, ammunition: str
) -> tuple[State, list[Event]]:
    enemy = r28_vehicles.vehicle_in(state, target)
    if enemy is None:
        raise ValueError("no vehicle stands in that hex")
    hull_down = r33_afv_combat.hull_down(ctx, state, firer.hex, enemy) if firer.hex else False
    row = r28_vehicles.to_hit_row(board, state, enemy, hull_down)
    # Case H of rule 33.31 is a target below a concealment counter. A vehicle is never
    # below one (PR-33), whatever counter the infantry of its hex holds.
    cases = r33_afv_combat.hit_cases(ctx, state, firer, target, state.phase, enemy.moved, False)
    state, result = r33_afv_combat.roll_to_hit(ctx, state, firer, target, row, cases)
    events = [r33_afv_combat.to_hit_event(firer, target, result)]
    state, marked = r33_afv_combat.mark_gun_fired(state, firer, result)
    events.extend(marked)
    if ammunition == AMMO_HEAT:
        # Rule 63.32 and PR-45: a roll of 6 or more spends the HEAT, and that shot is high
        # explosive.
        state, still_heat, spent = r33_afv_combat.spend_heat(state, firer, result.raw)
        events.extend(spent)
        if not still_heat:
            ammunition = AMMO_HE
    if not result.hit:
        return state, events
    column = r33_afv_combat.kill_column_for(ctx, firer, ammunition)
    state, kill = r33_afv_combat.roll_kill(ctx, state, firer.hex, enemy, column)
    events.append(r33_afv_combat.kill_event(firer.id, enemy, kill))
    if kill.killed:
        state, ev = r33_afv_combat.destroy(ctx, state, enemy.id, "a main gun hit")
        events.extend(ev)
    elif enemy.immobilized:
        # Rule 39.3: a hit that does not destroy a vehicle already immobilized sends its
        # crew through the morale check of rule 39.2 again.
        state, ev = r33_afv_combat.crew_abandons(ctx, state, enemy.id, "rule 39.3")
        events.extend(ev)
    return state, events


@actions.action("afv_mg", unconceals=actions.CAUSE_FIRED)
def _on_afv_mg(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    vehicle = state.units[command.units[0]]
    target = command.hex
    if target is None:
        raise ValueError("a machine gun shot needs a target hex")
    state, events = r31_transport.force_dismount(
        engine.board, state, vehicle.id, r31_transport.RULE_31_7, "the vehicle fired", charge=True
    )
    state, ev = fire_mg(engine.armor_ctx, engine.fire_ctx, state, vehicle, target, state.phase)
    events.extend(ev)
    return state, events
