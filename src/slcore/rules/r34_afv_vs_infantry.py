"""Rule 34, an armoured fighting vehicle against infantry.

The main armament first rolls on the to-hit table (rule 34.2). A hit is worth the
firepower of the gun's calibre on the Infantry Fire Table, and the effect roll takes the
terrain and situation modifiers of rule 11. The machine guns roll again on their own
(rule 34.3), and they roll even when the main armament missed (rule 34.4).

Rule 34.8 marks a vehicle that used its all-round machine gun with a crew exposed
counter. Infantry may then fire at the vehicle from any hex in any fire phase.
"""

from __future__ import annotations

from slcore import geometry
from slcore.events import Event
from slcore.game import FireGroup, State
from slcore.geometry import HexRef
from slcore.rng import roll_2d6
from slcore.rules import r10_resolution, r28_vehicles, r32_afv_cover, r33_afv_combat
from slcore.rules.r10_resolution import FireContext
from slcore.rules.r33_afv_combat import AMMO_HE, ArmorContext
from slcore.units import Unit

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
    """Rule 34.2: the main armament against the infantry of one hex."""
    concealed = bool(state.concealment_in(target))
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
    """Rule 34.8: the counter comes off at the end of the next enemy fire phase."""
    changed = {}
    events: list[Event] = []
    for vehicle in r28_vehicles.vehicles(state, player):
        if vehicle.crew_exposed:
            changed[vehicle.id] = vehicle.with_(crew_exposed=False)
            events.append(Event(RULE_34_8, "crew_inside", {"unit": vehicle.id}))
    return (state.with_units(changed) if changed else state), events
