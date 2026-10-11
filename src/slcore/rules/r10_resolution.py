"""Rule 10, fire combat resolution, with the dice roll modifiers of rule 11, the
machine gun penetration of rules 17.5 to 17.7, and the breakdown of rule 18.1.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from slcore import geometry
from slcore.events import Event
from slcore.game import PHASE_DEFENSIVE_FIRE, FireGroup, State
from slcore.geometry import HexRef
from slcore.los_cache import LosTable
from slcore.los_eval import evaluate
from slcore.rng import roll_2d6
from slcore.rules import (
    r08_fire,
    r44_rural,
    r11_terrain,
    r12_morale,
    r22_flamethrower,
    r24_smoke,
    r25_concealment,
    r32_afv_cover,
    r42_hidden,
)
from slcore.state import Board, HexsideRule
from slcore.tabledata import RESULT_KIA, RESULT_MC, RESULT_NONE, IftTable
from slcore.units import KIND_LEADER, KIND_SW, Unit, UnitType

RULE_10_3 = "10.3"
RULE_10_5 = "10.5"
RULE_10_6 = "10.6"
RULE_8_8 = "8.8"
RULE_8_9 = "8.9"
RULE_17_5 = "17.5"
RULE_17_6 = "17.6"
RULE_18_1 = "18.1"


@dataclass(frozen=True)
class FireContext:
    board: Board
    hexsides: Mapping[str, HexsideRule]
    types: Mapping[str, UnitType]
    ift: IftTable
    los: LosTable
    # Rule 44.24: the crop stands from June to October, and out of season a wheatfield
    # hex plays as open ground.
    wheat_in_season: bool = True
    # Rules 28 to 41. A scenario with no vehicle skips every rule 32 test, and the fire
    # path does not walk the unit list to find that out (NFR-01).
    vehicles_in_play: bool = False


def traced_path(ctx: FireContext, firer: HexRef, target: HexRef) -> tuple[HexRef, ...]:
    return evaluate(ctx.board, ctx.los, firer, target).traced


def common_modifier(
    ctx: FireContext, state: State, group: FireGroup, phase: str = "", known_only: bool = False
) -> tuple[int, list[dict]]:
    """Rules 11.1, 11.53, 11.6, and 15.2: the modifiers that apply to every unit in the target hex.

    With known_only the modifiers that read the units in the target hex (a flamethrower
    there, the cover of a vehicle) are left out. That is what the firer knows before the
    fire, and the preview of the fire uses it, so a preview names no hidden enemy unit."""
    parts: list[dict] = []
    total = r11_terrain.target_hex_modifier(ctx.board, group.target)
    if total:
        parts.append({"rule": r11_terrain.RULE_11_1, "value": total, "cause": ctx.board.hex(group.target).terrain})
    per_member: list[int] = []
    for uid, _ in group.members:
        firer = state.units[uid].hex
        if firer is None or firer == group.target:
            continue
        traced = traced_path(ctx, firer, group.target)
        per_member.append(r11_terrain.hexside_modifier(ctx.board, ctx.hexsides, traced, firer, group.target))
    side = r11_terrain.group_hexside_modifier(ctx.board, ctx.hexsides, per_member)
    if side:
        total += side
        parts.append({"rule": r11_terrain.RULE_11_53, "value": side, "cause": "hexside"})
    if group.leader is not None:
        rating = ctx.types[state.units[group.leader].type_key].leadership
        total += rating
        parts.append({"rule": "15.2", "value": rating, "cause": f"leader {group.leader}"})
    if known_only:
        return total, parts
    if r22_flamethrower.in_hex(state, ctx.types, group.target):
        total += r22_flamethrower.TARGET_MODIFIER
        parts.append(
            {"rule": r22_flamethrower.RULE_22_7, "value": r22_flamethrower.TARGET_MODIFIER, "cause": "flamethrower in the target hex"}
        )
    if ctx.vehicles_in_play:
        armour, armour_parts = r32_afv_cover.fire_modifier(ctx.board, ctx.los, ctx.types, state, group, phase)
        total += armour
        parts.extend(armour_parts)
    return total, parts


def smoke_modifier(ctx: FireContext, state: State, group: FireGroup) -> tuple[State, int, list[dict]]:
    """Rules 24.6 and 24.7: one die for the fire group whose line of sight meets smoke."""
    seen = False
    for uid, _ in group.members:
        firer = state.units[uid].hex
        if firer is None:
            continue
        traced = traced_path(ctx, firer, group.target) if firer != group.target else ()
        if r24_smoke.blocks_path(state, traced, firer, group.target):
            seen = True
            break
    if not seen:
        return state, 0, []
    state, value = r24_smoke.modifier(state, ())
    return state, value, [{"rule": r24_smoke.RULE_24_6, "value": value, "cause": "smoke on the line of sight"}]


def smoke_event(target: HexRef, value: int) -> Event:
    """Rule 24.7: the log shows the smoke die of this fire group and no other."""
    return Event(r24_smoke.RULE_24_6, "smoke_modifier", {"target": geometry.hex_id(*target), "value": value})


def rural_halves(
    ctx: FireContext, state: State, group: FireGroup, members: list, in_season: bool = True
) -> tuple[int, list]:
    """Rule 44 on the firepower of each member of a fire group.

    Rule 44.21 halves the fire of a member whose thread goes through a wheatfield hex, and
    a height advantage over the crop takes the halving away. Rule 44.1 triples the Point
    Blank Fire of a member that is above a cliff hexside, and rule 9.1 already doubled it,
    so the member gets one half more.
    """
    out = []
    total = 0
    for member in members:
        firer = state.units[member.unit].hex
        halves = member.halves
        modifiers = list(member.modifiers)
        if firer is not None and firer != group.target:
            traced = traced_path(ctx, firer, group.target)
            after = r44_rural.halves_through_crop(
                ctx.board, firer, group.target, traced, halves, in_season
            )
            if after != halves:
                halves = after
                modifiers.append(r44_rural.RULE_44_21)
            if r08_fire.RULE_9_1 in modifiers:
                point_blank = r44_rural.point_blank_halves(ctx.board, firer, group.target)
                if point_blank != r44_rural.POINT_BLANK_HALVES:
                    halves = halves * point_blank // r44_rural.POINT_BLANK_HALVES
                    modifiers.append(r44_rural.RULE_44_1)
        out.append(replace(member, halves=halves, modifiers=tuple(modifiers)))
        total += halves
    return total, out


def resolve_group(ctx: FireContext, state: State, group: FireGroup, phase: str) -> tuple[State, list[Event]]:
    """Rules 10.1 to 10.6 for one fire group, then the results of rule 8.8."""
    halves, members = r08_fire.group_firepower(state, ctx.types, group)
    halves, members = rural_halves(ctx, state, group, members, ctx.wheat_in_season)
    firepower = halves // 2
    state_rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=state_rng)
    raw = dice[0] + dice[1]
    drm, parts = common_modifier(ctx, state, group, phase)
    state, smoke_drm, smoke_parts = smoke_modifier(ctx, state, group)
    drm += smoke_drm
    parts.extend(smoke_parts)
    smoke_events = [smoke_event(group.target, smoke_drm)] if smoke_parts else []
    events: list[Event] = [
        Event(
            RULE_10_6,
            "fire",
            {
                "target": geometry.hex_id(*group.target),
                "members": [{"unit": m.unit, "weapon": m.weapon, "halves": m.halves, "modifiers": list(m.modifiers)} for m in members],
                "firepower": firepower,
                "column": column_label(ctx.ift, firepower),
                "dice": list(dice),
                "modifiers": parts,
                "adjusted": raw + drm,
                "phase": phase,
            },
        )
    ]
    events.extend(smoke_events)
    state, mark = mark_fired(state, group)
    events.extend(mark)
    state, brk = breakdown(ctx, state, group, raw)
    events.extend(brk)
    open_cancelled = ctx.vehicles_in_play and r32_afv_cover.group_cancels_open_ground(
        ctx.board, ctx.los, state, group, phase
    )
    state, hit = apply_to_hex(
        ctx,
        state,
        group.target,
        halves,
        raw,
        drm,
        phase,
        firing_player(state, group),
        open_ground_cancelled=open_cancelled,
    )
    events.extend(hit)
    state, pen = penetrate(ctx, state, group, halves, raw, phase)
    events.extend(pen)
    return state, events


def preview(ctx: FireContext, state: State, group: FireGroup) -> dict:
    """Rule 10.3 and rule 10.5 before the dice: the fire group the player builds now.

    It gives the firepower, the IFT column, the modifiers the firer knows, and for each IFT
    result the number of the 36 rolls of two dice that give it. It rolls no die and it
    changes no state. Left out, and named in the notes: the smoke die of rule 24.6, the
    modifiers that read the units in the target hex, the half firepower of rule 25.8
    against a concealed unit, and the moving target modifier of rule 16.5.
    """
    halves, members = r08_fire.group_firepower(state, ctx.types, group)
    halves, members = rural_halves(ctx, state, group, members, ctx.wheat_in_season)
    firepower = halves // 2
    drm, parts = common_modifier(ctx, state, group, known_only=True)
    rolls: dict[str, int] = {}
    for first in range(1, 7):
        for second in range(1, 7):
            result = ctx.ift.lookup(firepower, first + second + drm)
            rolls[result] = rolls.get(result, 0) + 1
    return {
        "rule_id": RULE_10_3,
        "target": geometry.hex_id(*group.target),
        "firepower": firepower,
        "column": column_label(ctx.ift, firepower),
        "drm": drm,
        "modifiers": parts,
        "rolls_of_36": dict(sorted(rolls.items())),
        "notes": [
            "24.6 a smoke die is not in the preview",
            "25.8 a concealed unit takes half the firepower",
            "16.5 a unit that moved in the open adds its modifier",
        ],
    }


def firing_player(state: State, group: FireGroup) -> int:
    return state.units[group.members[0][0]].player if group.members else state.active


def column_label(ift: IftTable, firepower: int) -> int:
    i = ift.column_index(firepower)
    return 0 if i is None else ift.columns[i]


def mark_fired(state: State, group: FireGroup) -> tuple[State, list[Event]]:
    changed: dict[int, Unit] = {}
    for uid, wid in group.members:
        unit = state.units[uid]
        if wid is None:
            changed[uid] = changed.get(uid, unit).with_(fired=True)
        else:
            changed[wid] = state.units[wid].with_(fired=True)
    if group.leader is not None:
        leader = changed.get(group.leader, state.units[group.leader])
        changed[group.leader] = leader.with_(directed=True)
    return state.with_units(changed), []


def breakdown(ctx: FireContext, state: State, group: FireGroup, raw: int) -> tuple[State, list[Event]]:
    """Rule 18.1: one roll tests each firing weapon against its own breakdown number."""
    events: list[Event] = []
    changed: dict[int, Unit] = {}
    for _, wid in group.members:
        if wid is None:
            continue
        weapon = state.units[wid]
        number = ctx.types[weapon.type_key].breakdown
        if number and raw >= number:
            changed[wid] = weapon.with_(malfunction=True)
            events.append(Event(RULE_18_1, "malfunction", {"weapon": wid, "roll": raw, "breakdown": number}))
    if changed:
        state = state.with_units(changed)
    return state, events


def apply_to_hex(
    ctx: FireContext,
    state: State,
    target: HexRef,
    halves: int,
    raw: int,
    drm: int,
    phase: str,
    firer_player: int,
    affect_all: bool = False,
    kill_weapons: bool = False,
    open_ground_cancelled: bool = False,
) -> tuple[State, list[Event]]:
    """Rules 8.8, 8.9, and 16.6: the result for each unit in the target hex.

    The firepower comes in half factors, because rule 25.8 halves it against a concealed
    unit while rule 25.41 keeps it whole against an unconcealed unit in the same hex. So
    the units of one hex can be in two firepower groups as well as in two modifier
    groups.

    With affect_all the fire also hits the units of the firing side. Rule 17.6 does that
    for the hexes beyond the target of a machine gun, and rule 20.83 for a melee hex.
    With kill_weapons a KIA also eliminates the support weapons of the hex, which is what
    rules 22.9 and 23.7 ask for after a flamethrower or a demolition charge.
    """
    events: list[Event] = []
    occupants = [u for u in state.infantry_in(target) if not u.eliminated]
    if not occupants:
        return state, events
    affect_all = affect_all or state.in_melee(target)
    moved_bonus = r11_terrain.moving_in_open_modifier(ctx.board, target) if phase == PHASE_DEFENSIVE_FIRE else 0
    if open_ground_cancelled:
        # Rules 32.2 and 32.7: a vehicle is the cover, so the target keeps no penalty for
        # moving in the open.
        moved_bonus = 0
    groups: dict[tuple[int, int], list[Unit]] = {}
    for u in occupants:
        if u.player == firer_player and not affect_all:
            continue
        extra = moved_bonus if (moved_bonus and u.moved) else 0
        own = r25_concealment.halves_for(state, u, halves) if u.player != firer_player else halves
        if u.hidden and u.player != firer_player and own == halves:
            # Rule 42.4 with rule 9.4: a hidden unit takes the fire at half strength, in
            # the same way as a concealed unit under rule 25.8. A unit that is both takes
            # the halving one time.
            own = halves // 2
        groups.setdefault((raw + drm + extra, own), []).append(u)
    had_result = False
    for adjusted, own_halves in sorted(groups):
        units = sorted(groups[(adjusted, own_halves)], key=lambda u: (u.kind != KIND_LEADER, u.id))
        firepower = own_halves // 2
        result = ctx.ift.lookup(firepower, adjusted)
        events.append(
            Event(
                RULE_10_5,
                "fire_result",
                {
                    "target": geometry.hex_id(*target),
                    "adjusted": adjusted,
                    "firepower": firepower,
                    "concealed": own_halves != halves,
                    "result": result,
                    "units": [u.id for u in units],
                },
            )
        )
        if result == RESULT_NONE:
            continue
        had_result = True
        # Rule 42.4: a result that is not "No Effect" puts the hidden units of the hex on
        # the board, whatever the morale checks that follow give.
        state, shown = r42_hidden.reveal_in(
            state, target, None, r42_hidden.CAUSE_HIT, r42_hidden.RULE_42_4
        )
        events.extend(shown)
        if result == RESULT_KIA:
            changed = {}
            for u in units:
                changed[u.id] = state.units[u.id].with_(eliminated=True, hex=None, carrier=None)
            state = state.with_units(changed)
            for u in units:
                state, drop = r12_morale.drop_weapons(state, u.id)
                events.extend(drop)
                events.append(Event(RULE_8_8, "eliminated", {"unit": u.id, "cause": "KIA"}))
            if kill_weapons:
                state, gone = eliminate_weapons_in(state, target, firer_player)
                events.extend(gone)
            continue
        modifier = 0 if result == RESULT_MC else int(result)
        for u in units:
            state = mark_dm(state, u.id)
            state, ev = r12_morale.morale_check(state, ctx.types, state.units[u.id], modifier, "fire")
            events.extend(ev)
    if had_result:
        state, ev = r25_concealment.remove_in(state, target, None, r25_concealment.RULE_25_9, "the attack had a result")
        events.extend(ev)
    return state, events


def eliminate_weapons_in(state: State, target: HexRef, firer_player: int) -> tuple[State, list[Event]]:
    """Rules 22.9 and 23.7: a KIA from a flamethrower or a charge takes the weapons too."""
    events: list[Event] = []
    changed: dict[int, Unit] = {}
    for u in state.units:
        if u.eliminated or u.kind != KIND_SW or u.player == firer_player:
            continue
        where = u.hex if u.carrier is None else state.units[u.carrier].hex
        if where != target:
            continue
        changed[u.id] = u.with_(eliminated=True, hex=None, carrier=None)
        events.append(Event(RULE_8_8, "weapon_eliminated", {"weapon": u.id, "cause": "KIA"}))
    return (state.with_units(changed) if changed else state), events


def mark_dm(state: State, unit_id: int) -> State:
    """Rule 14.6: a unit fired on since the preceding Rally Phase rallies on desperation morale."""
    unit = state.units[unit_id]
    if unit.dm:
        return state
    return state.with_unit(unit.with_(dm=True))


def penetrate(ctx: FireContext, state: State, group: FireGroup, halves: int, raw: int, phase: str) -> tuple[State, list[Event]]:
    """Rules 17.5 and 17.6: machine gun fire continues along the LOS beyond the target hex.

    The core applies penetration when every member of the group is in one hex, which is
    the case the rules illustrate. A multi-hex group has no single line to extend.
    """
    hexes = r08_fire.member_hexes(state, group)
    if len(hexes) != 1:
        return state, []
    firer = next(iter(hexes))
    factors = 0
    for _, wid in group.members:
        if wid is None:
            continue
        factors = max(factors, ctx.types[state.units[wid].type_key].penetration)
    if factors <= 0 or firer == group.target:
        return state, []
    events: list[Event] = []
    used = 1
    for nxt in ctx.los.ray(firer, group.target):
        if used >= factors:
            break
        if not penetration_continues(ctx, group.target if used == 1 else nxt, nxt):
            break
        result = evaluate(ctx.board, ctx.los, firer, nxt)
        if not result.clear:
            break
        occupants = [u for u in state.infantry_in(nxt) if not u.eliminated]
        if not occupants:
            continue
        used += 1
        drm, _ = common_modifier(ctx, state, FireGroup(nxt, group.members, group.leader))
        events.append(Event(RULE_17_5, "penetration", {"target": geometry.hex_id(*nxt), "factor": used, "of": factors}))
        state, ev = apply_to_hex(ctx, state, nxt, halves, raw, drm, phase, firing_player(state, group), affect_all=True)
        events.extend(ev)
    return state, events


def penetration_continues(ctx: FireContext, previous: HexRef, nxt: HexRef) -> bool:
    """Rule 2.8 and the ruling for 17.5: a building, woods, or wall stops the penetration."""
    if ctx.board.los_class(ctx.board.hex(previous).terrain) == "block":
        return False
    d = geometry.direction_to(previous, nxt)
    if d is not None and ctx.board.hexside(previous, d) == "wall":
        return False
    return True


def enemy_occupied_hexes(state: State, player: int) -> list[HexRef]:
    """The hexes that hold an enemy infantry unit."""
    out: set[HexRef] = set()
    for u in state.units:
        if u.eliminated or u.hex is None or u.carrier is not None or not u.is_infantry:
            continue
        if u.player != player:
            out.add(u.hex)
    return sorted(out)


def targets_in_los(ctx: FireContext, state: State, firer: HexRef, player: int) -> list[HexRef]:
    """The enemy hexes that the firing hex can see (rule 7)."""
    return [h for h in enemy_occupied_hexes(state, player) if h != firer and evaluate(ctx.board, ctx.los, firer, h).clear]
