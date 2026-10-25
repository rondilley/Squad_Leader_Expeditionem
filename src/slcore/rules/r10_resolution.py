"""Rule 10, fire combat resolution, with the dice roll modifiers of rule 11, the
machine gun penetration of rules 17.5 to 17.7, and the breakdown of rule 18.1.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from slcore import actions, geometry
from slcore.commands import Command
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
    r15_leadership,
    r16_defensive_fire,
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


def common_modifier(ctx: FireContext, state: State, group: FireGroup, phase: str = "") -> tuple[int, list[dict]]:
    """Rules 11.1, 11.53, 11.6, and 15.2: the modifiers that apply to every unit in the target hex."""
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
        rating = leadership_modifier(ctx, state, group)
        total += rating
        void = leader_void(ctx, state, group)
        cause = f"leader {group.leader} gives no modifier to this group" if void else f"leader {group.leader}"
        parts.append({"rule": "15.2", "value": rating, "cause": cause})
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


def leadership_modifier(ctx: FireContext, state: State, group: FireGroup) -> int:
    """Rule 15.2 and QA-15.2: the leadership modifier of a fire group.

    One hex uses the leader the player named. A chain uses the least effective rating
    among that leader and the best leader in each other member hex. A 9-2 in one hex
    does not erase an 8-0 in the next hex. A member hex with no eligible leader makes
    the modifier zero, whatever the sequence of the commands (PR-40).
    """
    if group.leader is None or leader_void(ctx, state, group):
        return 0
    named = state.units[group.leader]
    named_rating = ctx.types[named.type_key].leadership
    hexes = r08_fire.member_hexes(state, group)
    if len(hexes) <= 1:
        return named_rating
    ratings = [named_rating]
    for hex_ref in hexes:
        if hex_ref == named.hex:
            continue
        best = _best_rating(ctx, state, group, hex_ref, named.player)
        if best is not None:
            ratings.append(best)
    return max(ratings)


def _mans_mg_in(group: FireGroup, unit_id: int) -> bool:
    """Rule 17.4: the leader fires a weapon of this group."""
    return any(uid == unit_id and wid is not None for uid, wid in group.members)


def _best_rating(ctx: FireContext, state: State, group: FireGroup, hex_ref: HexRef, player: int) -> int | None:
    """The best rating of an eligible leader in one member hex of a chain (QA-15.2)."""
    best: int | None = None
    for leader in r15_leadership.leaders_in(state, hex_ref, player):
        if leader.fired or leader.directed or _mans_mg_in(group, leader.id):
            continue
        value = ctx.types[leader.type_key].leadership
        if best is None or value < best:
            best = value
    return best


def leader_void(ctx: FireContext, state: State, group: FireGroup) -> bool:
    """PR-40: the named leader gives this group no modifier.

    Rule 17.4: a leader who mans a machine gun in the group gives its rating only to a
    group of its own fire. QA-15.2: each hex of a chain must hold an eligible leader.
    """
    if group.leader is None:
        return False
    named = state.units[group.leader]
    if _mans_mg_in(group, named.id) and any(uid != named.id for uid, _ in group.members):
        return True
    hexes = r08_fire.member_hexes(state, group)
    if hexes and named.hex not in hexes:
        return True
    for hex_ref in hexes:
        if hex_ref == named.hex:
            continue
        if _best_rating(ctx, state, group, hex_ref, named.player) is None:
            return True
    return False


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
                crop = r44_rural.crop_hexes(ctx.board, traced, in_season)
                modifiers.extend(r44_rural.crop_rules(ctx.board, crop))
            if r08_fire.RULE_9_1 in modifiers:
                point_blank = r44_rural.point_blank_halves(ctx.board, firer, group.target)
                if point_blank != r44_rural.POINT_BLANK_HALVES:
                    halves = halves * point_blank // r44_rural.POINT_BLANK_HALVES
                    modifiers.append(r44_rural.RULE_44_1)
        if halves == member.halves and len(modifiers) == len(member.modifiers):
            # No rule of 44 applied: the member is the same record (NFR-01).
            out.append(member)
        else:
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
    state, mark = mark_fired(state, group, ctx.types, directed=not leader_void(ctx, state, group))
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
    if ctx.vehicles_in_play:
        # Rule 34.8 and PR-44: the same roll goes against the exposed crew of a vehicle in
        # the target hex. A local import, because rule 34 reads this module.
        from slcore.rules import r34_afv_vs_infantry

        group_parts = [p for p in parts if p["rule"] in (r15_leadership.RULE_15_2, r24_smoke.RULE_24_6)]
        state, crew = r34_afv_vs_infantry.fire_at_exposed_crew(
            ctx.types,
            ctx.ift,
            state,
            group.target,
            firing_player(state, group),
            halves,
            raw,
            sum(int(p["value"]) for p in group_parts),
            group_parts,
        )
        events.extend(crew)
    state, pen = penetrate(ctx, state, group, halves, raw, phase, smoke_drm)
    events.extend(pen)
    return state, events


def firing_player(state: State, group: FireGroup) -> int:
    return state.units[group.members[0][0]].player if group.members else state.active


def column_label(ift: IftTable, firepower: int) -> int:
    i = ift.column_index(firepower)
    return 0 if i is None else ift.columns[i]


def mark_fired(state: State, group: FireGroup, types: Mapping[str, UnitType], directed: bool = True) -> tuple[State, list[Event]]:
    """The units and weapons of the group have fired. The leader directed it when `directed`."""
    changed: dict[int, Unit] = {}
    for uid, wid in group.members:
        unit = state.units[uid]
        if wid is None:
            changed[uid] = changed.get(uid, unit).with_(fired=True)
        else:
            changed[wid] = state.units[wid].with_(fired=True)
            # Rule 17.4: a leader who mans the machine gun gives no morale benefit after.
            if unit.kind == KIND_LEADER and types[state.units[wid].type_key].weapon_class == "mg":
                leader = changed.get(uid, unit)
                changed[uid] = leader.with_(manned_mg=True)
    if group.leader is not None and directed:
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
    affect_all = affect_all or state.in_melee(target)
    # PR-31: a concealment counter with no unit of its side below it (rule 25.7) takes
    # the fire as a concealed squad would, so that a dummy and a real stack give the
    # same outcome for the counter.
    dummies = {
        c.player
        for c in state.concealment
        if c.hex == target and (affect_all or c.player != firer_player)
    } - {u.player for u in occupants}
    if not occupants and not dummies:
        return state, events
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
                    "firer": firer_player,
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
            for u in units:
                # Rule 13.5: the weapon falls in the hex. The carrier still has that hex.
                state, drop = r12_morale.drop_weapons(state, u.id)
                events.extend(drop)
            changed = {}
            for u in units:
                changed[u.id] = state.units[u.id].with_(eliminated=True, hex=None, carrier=None)
                events.append(Event(RULE_8_8, "eliminated", {"unit": u.id, "cause": "KIA"}))
            state = state.with_units(changed)
            if kill_weapons:
                state, gone = eliminate_weapons_in(state, target, firer_player)
                events.extend(gone)
            continue
        modifier = 0 if result == RESULT_MC else int(result)
        for u in units:
            state = mark_dm(state, u.id)
            state, ev = r12_morale.morale_check(state, ctx.types, state.units[u.id], modifier, "fire")
            events.extend(ev)
    if dummies and not had_result:
        # Rule 25.8 halves the fire at the counter, and rule 25.9 removes it on any result
        # that is not "No Effect". The fire has no other effect on a dummy.
        had_result = ctx.ift.lookup((halves // 2) // 2, raw + drm) != RESULT_NONE
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


def penetrate(
    ctx: FireContext,
    state: State,
    group: FireGroup,
    halves: int,
    raw: int,
    phase: str,
    smoke_drm: int = 0,
    factor_limit: int | None = None,
) -> tuple[State, list[Event]]:
    """Rules 17.5 and 17.6: machine gun fire continues along the LOS beyond the target hex.

    The core applies penetration when every member of the group is in one hex, which is
    the case the rules illustrate. A multi-hex group has no single line to extend.

    Each hex the line enters, empty or not, spends one factor. The target hex spent the
    first. A wall on the hexside the line is about to cross stops the walk. The smoke die
    is the die the fire group already rolled (rule 24.7). The walk does not roll another.
    """
    hexes = r08_fire.member_hexes(state, group)
    if len(hexes) != 1:
        return state, []
    firer = next(iter(hexes))
    if factor_limit is None:
        factors = 0
        for _, wid in group.members:
            if wid is None:
                continue
            factors = max(factors, ctx.types[state.units[wid].type_key].penetration)
    else:
        factors = factor_limit
    if factors <= 1 or firer == group.target:
        return state, []
    events: list[Event] = []
    previous = group.target
    used = 1
    for nxt in ctx.los.ray(firer, group.target):
        if used >= factors:
            break
        if not penetration_continues(ctx, previous, nxt):
            break
        result = evaluate(ctx.board, ctx.los, firer, nxt)
        if not result.clear:
            break
        used += 1
        previous = nxt
        occupants = [u for u in state.infantry_in(nxt) if not u.eliminated]
        if not occupants and not state.concealment_in(nxt):
            # An empty hex takes nothing. A hex with a counter takes the fire whether a
            # unit is below the counter or not (PR-31).
            continue
        drm, _ = common_modifier(ctx, state, FireGroup(nxt, group.members, group.leader), phase)
        drm += smoke_drm
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
    """The hexes that hold an enemy infantry unit or an enemy concealment counter.

    Rule 25.2 treats each counter as an opposing squad (PR-31), so the hex of a counter
    is a target whether a unit is below it or not. A hidden unit is not a target (rule
    42.1), and the hex of a concealed unit is a target through its counter only.
    """
    out: set[HexRef] = set()
    for u in state.units:
        if u.eliminated or u.hidden or u.hex is None or u.carrier is not None or not u.is_infantry:
            continue
        if u.player != player:
            out.add(u.hex)
    for counter in state.concealment:
        if counter.player != player:
            out.add(counter.hex)
    return sorted(out)


def targets_in_los(ctx: FireContext, state: State, firer: HexRef, player: int) -> list[HexRef]:
    """The enemy hexes that the firing hex can see (rule 7)."""
    return [h for h in enemy_occupied_hexes(state, player) if h != firer and evaluate(ctx.board, ctx.los, firer, h).clear]


# ------------------------------------------------------------------ the command handler (M3)


def _group_members(before: State, command: Command) -> tuple[int, ...]:
    """Rule 25.4: the fire of a group is the act of each unit of the group."""
    group = before.fire_group
    return tuple(sorted({uid for uid, _ in group.members})) if group is not None else ()


@actions.action("group_fire", unconceals=actions.CAUSE_FIRED, acting=_group_members)
def _on_group_fire(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    group = state.fire_group
    if group is None:
        raise ValueError("no fire group is open")
    pairs = set(state.fired_pairs)
    for uid, _ in group.members:
        h = state.units[uid].hex
        if h is not None:
            pairs.add((h, group.target))
    state, events = resolve_group(engine.fire_ctx, state, group, state.phase)
    if state.phase == PHASE_DEFENSIVE_FIRE:
        state, returned = r16_defensive_fire.return_units(state)
        events.extend(returned)
    state = state.with_(fire_group=None, fired_pairs=tuple(sorted(pairs)))
    return state, events


# The flamethrower of rule 22 resolves on this table, and this module imports rule 22, so
# its handler is here and rule 22 does not import rule 10 back.
@actions.action("ft_fire", unconceals=actions.CAUSE_FIRED)
def _on_flamethrower(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    """Rules 22.1, 22.2, 22.6, 22.8, and 22.9: one weapon, one target, and no modifier."""
    unit_id, weapon_id, target = command.units[0], command.weapon, command.hex
    if weapon_id is None or target is None:
        raise ValueError("flamethrower fire needs a weapon and a target hex")
    halves = r22_flamethrower.halves(engine.types, state.units[weapon_id])
    state, dice = r22_flamethrower.roll(state)
    raw = dice[0] + dice[1]
    events = [
        Event(
            r22_flamethrower.RULE_22_2,
            "fire",
            {
                "target": geometry.hex_id(*target),
                "members": [{"unit": unit_id, "weapon": weapon_id, "halves": halves, "modifiers": []}],
                "firepower": halves // 2,
                "dice": list(dice),
                "modifiers": [],
                "adjusted": raw,
                "phase": state.phase,
            },
        )
    ]
    state = state.with_units(
        {unit_id: state.units[unit_id].with_(fired=True), weapon_id: state.units[weapon_id].with_(fired=True)}
    )
    player = state.units[unit_id].player
    # Rule 22.2: no modifier of any kind, so no minus two of rule 16.5 against a unit that
    # moved in the open when the flamethrower fires in the Defensive Fire Phase.
    state, hit = apply_to_hex(
        engine.fire_ctx, state, target, halves, raw, 0, state.phase, player, kill_weapons=True, open_ground_cancelled=True
    )
    events.extend(hit)
    state, fuel = r22_flamethrower.out_of_fuel(state, weapon_id, raw)
    events.extend(fuel)
    pairs = set(state.fired_pairs)
    where = state.units[unit_id].hex
    if where is not None:
        pairs.add((where, target))
    return state.with_(fired_pairs=tuple(sorted(pairs))), events
