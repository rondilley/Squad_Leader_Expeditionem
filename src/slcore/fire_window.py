"""The legal commands of the fire window of the three fire phases (rules 8 to 17, 22, 33 to 38).

With no fire group open, each unit that can fire gets a command to start a group at each
target it sees, and the guns, the anti-tank weapons, and the flamethrowers get their own
shots. With a group open, the commands add a member, name the directing leader, or fire
the group. The window registers in the table of `slcore.actions` by its sub-step name.
"""

from __future__ import annotations

from typing import Any

from slcore import actions, geometry
from slcore.commands import Command
from slcore.game import PHASE_DEFENSIVE_FIRE, PHASE_PREP_FIRE, FireGroup, State
from slcore.geometry import HexRef
from slcore.los_eval import LosContext
from slcore.los_eval import evaluate as evaluate_los
from slcore.phases import FIRE_WINDOW, SubStep, fire_rule
from slcore.rules import (
    r08_fire,
    r10_resolution,
    r15_leadership,
    r16_defensive_fire,
    r22_flamethrower,
    r28_vehicles,
    r30_vehicle_movement,
    r33_afv_combat,
    r34_afv_vs_infantry,
    r36_infantry_vs_afv,
    r37_at_weapons,
    r38_fate,
)
from slcore.rules.r33_afv_combat import AMMO_AP, AMMO_HE, AMMO_HEAT
from slcore.units import Unit


@actions.window(FIRE_WINDOW)
def fire_commands(engine: Any, state: State, step: SubStep) -> list[Command]:
    player = state.active
    rule = fire_rule(state.phase)
    out: list[Command] = []
    if state.phase == PHASE_DEFENSIVE_FIRE and state.fire_group is None:
        # Rule 16.1 and PR-53: a track hex that a unit of the defender sees.
        out.extend(r16_defensive_fire.legal_track_returns(state, player, engine._sees_fn(state)))
    group = state.fire_group
    candidates = r08_fire.firing_units(state, player)
    if group is None:
        targets = _targets_for(engine, state, candidates, player)
        for unit in candidates:
            for target in targets.get(unit.id, ()):  # rule 8.6, a new group at any target in sight
                out.extend(_add_commands(engine, state, unit, target, rule))
                out.extend(_flamethrower_commands(engine, state, unit, target, rule))
        out.extend(_armor_fire_commands(engine, state))
        out.append(Command("end_phase"))
        return out
    for unit in candidates:
        if unit.hex is None or not r08_fire.chain_allows(state, group, unit.hex):
            continue
        if (unit.hex, group.target) in state.fired_pairs:
            continue
        if not engine._can_see(state, unit.hex, group.target):
            continue
        out.extend(_add_commands(engine, state, unit, group.target, rule, group))
    out.extend(_leader_commands(engine, state, group))
    if group.members:
        out.append(Command("group_fire"))
    return out


# ------------------------------------------------------------------ armor


def _armor_fire_commands(engine: Any, state: State) -> list[Command]:
    """Rules 33 to 38 in a fire phase: the guns, the rockets, and the tank hunters."""
    ctx = engine.armor_ctx
    if ctx is None or not engine.has_vehicles:
        return []
    player = state.active
    phase = state.phase
    out: list[Command] = []
    los_ctx = engine._los_ctx(state)
    blind = engine._blind_hexes(state, player)
    for vehicle in r28_vehicles.vehicles(state, player):
        if vehicle.wreck or vehicle.hex is None:
            continue
        targets = _armor_targets(engine, state, vehicle, los_ctx, blind)
        if r33_afv_combat.may_fire_main(ctx, state, vehicle, phase):
            for target in targets:
                out.extend(_main_gun_commands(engine, state, vehicle, target, blind))
        if r33_afv_combat.may_fire_mg(ctx, vehicle, phase):
            for target in targets:
                if not _infantry_target(state, target, vehicle.player) and target not in blind:
                    continue
                if r33_afv_combat.mg_firepower(ctx, vehicle, target, None) > 0:
                    out.append(Command("afv_mg", units=(vehicle.id,), hex=target))
        if phase == PHASE_DEFENSIVE_FIRE and not engine.types[vehicle.type_key].is_turreted:
            # Rule 33.31 case I: a self-propelled gun may turn in this phase and fire.
            if not vehicle.immobilized and not vehicle.fired:
                out.extend(r30_vehicle_movement.pivots_for(engine.vehicle_ctx, state, vehicle))
    sees = engine._sees_fn(state)
    # Rule 8.1 with rule 37: an anti-tank weapon fires at a vehicle it sees.
    out.extend(r37_at_weapons.legal_shots(ctx, state, player, phase, sees))
    if phase == PHASE_DEFENSIVE_FIRE:
        out.extend(r36_infantry_vs_afv.legal_attacks(engine.board, state, engine.types, player))
    if phase == PHASE_PREP_FIRE:
        out.extend(r38_fate.legal_smoke(ctx, state, player, phase, sees))
    return out


def _armor_targets(
    engine: Any, state: State, vehicle: Unit, los_ctx: LosContext | None, blind: frozenset[HexRef] = frozenset()
) -> list[HexRef]:
    """Rule 33.1 and rule 34.1: the hexes this vehicle can shoot at.

    PR-52 adds the hexes of blind fire, where no enemy is known to be.
    """
    if vehicle.hex is None:
        return []
    seen: list[HexRef] = []
    hexes = {u.hex for u in state.player_units(1 - vehicle.player) if u.hex is not None}
    hexes.update(c.hex for c in state.concealment if c.player != vehicle.player)
    hexes.update(blind)
    for hex_ref in sorted(hexes):
        if hex_ref == vehicle.hex:
            continue
        if (
            hex_ref not in blind
            and not _infantry_target(state, hex_ref, vehicle.player)
            and not any(
                u.is_vehicle and not u.wreck and not u.hidden
                for u in state.units_in(hex_ref)
                if u.player != vehicle.player
            )
        ):
            continue
        if not engine._can_see(state, vehicle.hex, hex_ref, los_ctx):
            continue
        seen.append(hex_ref)
    return seen


def _infantry_target(state: State, hex_ref: HexRef, player: int) -> bool:
    """Rule 25.2 and PR-31: the hex holds enemy infantry the player sees, or an enemy counter.

    A hidden unit is no target (rule 42.1). A counter is a target whether a unit is below it
    or not, so a dummy and a real stack give the same legal list.
    """
    if state.enemy_counter_in(hex_ref, player):
        return True
    return any(u.is_infantry and not u.hidden and u.player != player for u in state.units_in(hex_ref))


def _main_gun_commands(
    engine: Any, state: State, vehicle: Unit, target: HexRef, blind: frozenset[HexRef] = frozenset()
) -> list[Command]:
    """PR-29: one command for each shot the gun can make at this hex.

    A hex that holds a vehicle and infantry gives two commands, because rule 33.3 and rule
    34.2 are different shots. The shell is chosen by the aim: armour piercing at a vehicle
    where the gun has it, and high explosive at infantry. A gun marked H6 has HEAT at a
    vehicle as a third choice (rule 63.3, PR-45).
    """
    kind = engine.types[vehicle.type_key]
    out: list[Command] = []
    if not kind.is_turreted and vehicle.hex is not None:
        # Rule 33.1: a vehicle fires its main armament in its covered arc. Rule 33.34 gives
        # a tank the way out, and it costs case D. A self-propelled gun has no turret and no
        # way out, so the shot is not on the list at all.
        if not r28_vehicles.in_covered_arc(vehicle.hex, vehicle.facing, target):
            return out
    enemy_vehicle = r28_vehicles.vehicle_in(state, target)
    # PR-49: a hidden vehicle is no target of the other side.
    if enemy_vehicle is not None and enemy_vehicle.player != vehicle.player and not enemy_vehicle.hidden:
        ammo = AMMO_HE if kind.gun_he_only else AMMO_AP
        out.append(Command("afv_fire", units=(vehicle.id,), hex=target, extra=(("aim", "vehicle"), ("ammo", ammo))))
        if r33_afv_combat.heat_available(engine.armor_ctx, vehicle):
            out.append(
                Command("afv_fire", units=(vehicle.id,), hex=target, extra=(("aim", "vehicle"), ("ammo", AMMO_HEAT)))
            )
    if _infantry_target(state, target, vehicle.player) or target in blind:
        out.append(Command("afv_fire", units=(vehicle.id,), hex=target, extra=(("aim", "infantry"), ("ammo", AMMO_HE))))
        if r34_afv_vs_infantry.canister_available(engine.armor_ctx, vehicle):
            distance = geometry.distance(vehicle.hex, target) if vehicle.hex else 99
            if distance <= r34_afv_vs_infantry.CANISTER_RANGE:
                out.append(
                    Command(
                        "afv_fire",
                        units=(vehicle.id,),
                        hex=target,
                        extra=(("aim", "infantry"), ("ammo", r34_afv_vs_infantry.AMMO_CANISTER)),
                    )
                )
    return out


# ------------------------------------------------------------------ infantry


def _targets_for(engine: Any, state: State, candidates: list[Unit], player: int) -> dict[int, tuple[HexRef, ...]]:
    """The target hexes of each firing unit: the known enemy, and two more kinds.

    Rule 34.8 (PR-44) adds the hex of an enemy vehicle with its crew exposed, and rule 42.4
    (PR-52) adds the hexes of blind fire.
    """
    found = set(r10_resolution.enemy_occupied_hexes(state, player))
    if engine.has_vehicles:
        found.update(r34_afv_vs_infantry.exposed_targets(state, player))
    found.update(engine._blind_hexes(state, player))
    enemy_hexes = sorted(found)
    los_ctx = engine._los_ctx(state)
    fired = set(state.fired_pairs)
    board = engine.board
    los = engine.los
    # With no vehicle and no smoke in the way, the answer is the static table of the
    # board, and a read of the table does not need the evaluator (NFR-01).
    static = los.static_results if los_ctx is None else {}
    out: dict[int, tuple[HexRef, ...]] = {}
    for unit in candidates:
        here = unit.hex
        if here is None:
            continue
        seen: list[HexRef] = []
        for h in enemy_hexes:
            if h == here or (here, h) in fired:
                continue
            result = static.get((here, h))
            if result is None:
                result = evaluate_los(board, los, here, h, los_ctx)
            if result.clear:
                seen.append(h)
        out[unit.id] = tuple(seen)
    return out


def _add_commands(
    engine: Any, state: State, unit: Unit, target: HexRef, rule: str, group: FireGroup | None = None
) -> list[Command]:
    types = engine.types
    out: list[Command] = []
    in_group = group is not None
    if (group is None or not r08_fire.inherent_in_group(group, unit.id)) and r08_fire.can_fire_inherent(state, types, unit, rule):
        # PR-41: the inherent fire of a squad that forfeits it adds nothing to a group.
        if r08_fire.member_firepower(state, types, unit, None, target, unit.moved) is not None and not r08_fire.mg_forfeit(
            state, types, unit, group
        ):
            out.append(Command("group_add", units=(unit.id,), hex=target))
    weapons_used = r08_fire.weapons_in_group(group, unit.id) if in_group else 0
    if weapons_used < r08_fire.MAX_WEAPONS_FOR_EACH_UNIT:
        for weapon in sorted(state.carried_by(unit.id), key=lambda w: w.id):
            if in_group and any(uid == unit.id and wid == weapon.id for uid, wid in group.members):
                continue
            if not r08_fire.can_fire_weapon(state, types, unit, weapon, rule):
                continue
            if not r08_fire.mg_add_allowed(state, types, unit, weapon, group):
                continue
            if r08_fire.member_firepower(state, types, unit, weapon, target, unit.moved) is None:
                continue
            out.append(Command("group_add_weapon", units=(unit.id,), weapon=weapon.id, hex=target))
    return out


def _flamethrower_commands(engine: Any, state: State, unit: Unit, target: HexRef, rule: str) -> list[Command]:
    """Rule 22.3: a flamethrower fires alone, so it is its own command and not a group."""
    if unit.hex is None:
        return []
    out: list[Command] = []
    for weapon in sorted(state.carried_by(unit.id), key=lambda w: w.id):
        if not r22_flamethrower.can_fire(state, engine.types, unit, weapon, rule):
            continue
        if not r22_flamethrower.in_range(engine.types, weapon, unit.hex, target):
            continue
        out.append(Command("ft_fire", units=(unit.id,), weapon=weapon.id, hex=target))
    return out


def _leader_commands(engine: Any, state: State, group: FireGroup) -> list[Command]:
    """Rules 15.2 and 15.4 with the ruling for 15.2: one leader directs the group."""
    if group.leader is not None or not group.members:
        return []
    hexes = r08_fire.member_hexes(state, group)
    out: list[Command] = []
    per_hex: dict[HexRef, list[Unit]] = {}
    for h in hexes:
        leaders = [u for u in r15_leadership.leaders_in(state, h, state.active) if not u.directed and not u.fired]
        if not leaders:
            return []
        per_hex[h] = leaders
    for h in sorted(per_hex):
        for leader in per_hex[h]:
            # Rule 17.4 and PR-40: a leader who mans a machine gun of the group directs only
            # its own fire, and each hex of a chain needs an eligible leader.
            if r10_resolution.leader_void(engine.fire_ctx, state, FireGroup(group.target, group.members, leader.id)):
                continue
            out.append(Command("group_leader", units=(leader.id,)))
    return out
