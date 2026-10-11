"""Rule 35, overruns, with rule 38.3 and rule 42.6.

An overrun is an attack a vehicle makes in the Movement Phase by driving into a hex that
enemy infantry holds. It is resolved on the Infantry Fire Table the moment the vehicle
enters (rule 35.1). A vehicle overruns one hex in a player turn, and it must be the first
enemy hex it enters (rule 35.8). After an overrun the vehicle fires nothing for the rest
of that player turn (rule 35.9).
<<<<<<< Updated upstream
=======

Project ruling PR-54: the vehicle declares the overrun as it enters, and the attack
resolves on the Infantry Fire Table at the end of the Defensive Fire Phase that follows,
if the vehicle is not a wreck by then. Rule 35.1 says "as the AFV enters", and rule 35.6
says it must first survive all defensive fire, which comes only in the next phase; the
Advanced Sequence of Play resolves overruns in that phase, after the fire.
>>>>>>> Stashed changes
"""

from __future__ import annotations

from typing import Mapping

from slcore import actions, geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import PHASE_MOVEMENT, State
from slcore.geometry import HexRef
from slcore.rng import roll_2d6
from slcore.rules import r10_resolution, r28_vehicles, r31_transport, r33_afv_combat
from slcore.rules.r10_resolution import FireContext
from slcore.rules.r33_afv_combat import ArmorContext
from slcore.state import Board
from slcore.units import CLASS_HALFTRACK, Unit, UnitType

# Rule 35.8: a cliff hexside stops the step to one side.
CLIFF = "cliff"

RULE_35_1 = "35.1"
RULE_35_3 = "35.3"
RULE_35_4 = "35.4"
RULE_35_5 = "35.5"
RULE_35_8 = "35.8"
RULE_35_9 = "35.9"
RULE_38_3 = "38.3"
RULE_42_6 = "42.6"

# Rule 35.3: sixteen firepower factors for a tank or a self-propelled gun, eight for an
# armed halftrack, and half of that when one weapon is out of order.
TANK_FIREPOWER = 16
HALFTRACK_FIREPOWER = 8
# Rule 35.3: an overrun on a truck or a jeep takes a minus five on the dice roll.
SOFT_TARGET_MODIFIER = -5
# Rule 38.3: an unmodified twelve detracks the vehicle for the rest of the scenario.
GRENADE_BUNDLE_ROLL = 12


def firepower(ctx: ArmorContext, vehicle: Unit) -> int:
    """Rule 35.3: the firepower factors of this overrun, or zero when nothing works."""
    kind = ctx.types[vehicle.type_key]
    base = HALFTRACK_FIREPOWER if kind.vehicle_class == CLASS_HALFTRACK else TANK_FIREPOWER
    has_gun = kind.gun > 0
    has_mg = kind.mg_ca > 0 or kind.mg_360 > 0
    gun_out = has_gun and (vehicle.malfunction or vehicle.disabled)
    mg_out = has_mg and (vehicle.mg_malfunction or vehicle.mg_disabled)
    if (not has_gun or gun_out) and (not has_mg or mg_out):
        return 0
    if gun_out or mg_out:
        return base // 2
    return base


def targets_in(state: State, hex_ref: HexRef, player: int) -> list[Unit]:
    """Rule 35.1: enemy infantry in the hex. A vehicle is never overrun."""
    return [
        u
        for u in state.units_in(hex_ref)
        if u.player != player and u.is_infantry and not u.riding
    ]


def may_overrun(state: State, vehicle: Unit, hex_ref: HexRef) -> bool:
    """Rules 35.1 and 35.8: one overrun a turn, against the first enemy hex entered.

    PR-31: a concealment counter of the other side is an opposing squad, so the hex of a
    counter is overrun whether a unit is below it or not. The attack on a dummy is the
    fire at a counter of `apply_to_hex`, and the moving player learns what any attack on
    the counter tells.
    """
    if vehicle.overran:
        return False
    if r28_vehicles.vehicle_in(state, hex_ref) is not None:
        return False
    if state.enemy_counter_in(hex_ref, vehicle.player):
        return True
    return bool(targets_in(state, hex_ref, vehicle.player))


def resolve(
    ctx: ArmorContext,
    fire_ctx: FireContext,
    state: State,
    vehicle_id: int,
    hex_ref: HexRef,
) -> tuple[State, list[Event]]:
    """Rules 35.1, 35.3, 35.4, and 38.3: the attack the vehicle makes as it drives in."""
    vehicle = state.units[vehicle_id]
    factors = firepower(ctx, vehicle)
    state = state.with_unit(state.units[vehicle_id].with_(overran=True))
    if factors <= 0:
        return state, [
            Event(RULE_35_3, "overrun_unarmed", {"unit": vehicle_id, "hex": geometry.hex_id(*hex_ref)})
        ]
    rng, dice = roll_2d6(state.rng)
    state = state.with_(rng=rng)
    raw = dice[0] + dice[1]
    # Rule 35.4: the terrain modifiers apply, and the minus two for infantry moving in the
    # open does not, because that one belongs to the Defensive Fire Phase.
    from slcore.rules import r11_terrain

    drm = r11_terrain.target_hex_modifier(ctx.board, hex_ref)
    parts = [{"rule": RULE_35_4, "value": drm, "cause": ctx.board.hex(hex_ref).terrain}]
    events = [
        Event(
            RULE_35_1,
            "overrun",
            {
                "unit": vehicle_id,
                "hex": geometry.hex_id(*hex_ref),
                "firepower": factors,
                "column": r10_resolution.column_label(ctx.ift, factors),
                "dice": list(dice),
                "modifiers": parts,
                "adjusted": raw + drm,
            },
        )
    ]
    state, hit = r10_resolution.apply_to_hex(
        fire_ctx, state, hex_ref, factors * 2, raw, drm, PHASE_MOVEMENT, vehicle.player
    )
    events.extend(hit)
    if raw == GRENADE_BUNDLE_ROLL:
        state, ev = r33_afv_combat.immobilize(ctx, state, vehicle_id, "a grenade bundle in an overrun")
        events.append(Event(RULE_38_3, "grenade_bundle", {"unit": vehicle_id, "roll": raw}))
        events.extend(ev)
    return state, events


<<<<<<< Updated upstream
def pushed_units(state: State, player: int) -> list[Unit]:
    """Rule 35.8: the infantry on foot of this player in the hex of an enemy vehicle.

    The vehicle is working and on the board. A hidden vehicle is on its owner's record and
    not on the board (rule 42.1), so it pushes nothing.
    """
    out: list[Unit] = []
    for vehicle in r28_vehicles.vehicles(state, 1 - player):
        if vehicle.hex is None or vehicle.wreck or vehicle.hidden:
            continue
=======
def declare(state: State, vehicle_id: int, hex_ref: HexRef) -> tuple[State, list[Event]]:
    """PR-54: the vehicle enters the hex and declares the overrun. No die is rolled now."""
    vehicle = state.units[vehicle_id]
    state = state.with_unit(vehicle.with_(overran=True, overrun_hex=hex_ref))
    return state, [Event(RULE_35_6, "overrun_declared", {"unit": vehicle_id, "hex": geometry.hex_id(*hex_ref)})]


def resolve_pending(
    ctx: ArmorContext, fire_ctx: FireContext, state: State, player: int
) -> tuple[State, list[Event]]:
    """PR-54 and rule 35.6: at the end of the Defensive Fire Phase, each declared overrun
    of this player resolves if its vehicle survived the defensive fire."""
    events: list[Event] = []
    for vehicle in r28_vehicles.vehicles(state, player):
        hex_ref = vehicle.overrun_hex
        if hex_ref is None:
            continue
        state = state.with_unit(state.units[vehicle.id].with_(overrun_hex=None))
        current = state.units[vehicle.id]
        where = geometry.hex_id(*hex_ref)
        if current.wreck or current.eliminated:
            events.append(Event(RULE_35_6, "overrun_stopped", {"unit": vehicle.id, "hex": where}))
            continue
        if not targets_in(state, hex_ref, player) and not state.enemy_counter_in(hex_ref, player):
            events.append(Event(RULE_35_6, "overrun_empty", {"unit": vehicle.id, "hex": where}))
            continue
        state, ev = resolve(ctx, fire_ctx, state, vehicle.id, hex_ref)
        events.extend(ev)
    return state, events


def stops_infantry_attack(board: Board, vehicle: Unit, unit: Unit) -> bool:
    """Rule 35.7: infantry in the open-terrain hex the vehicle overruns makes no infantry
    attack on that vehicle. An anti-tank weapon is not an infantry attack and may fire."""
    if vehicle.overrun_hex is None or unit.hex != vehicle.overrun_hex:
        return False
    return board.hex(vehicle.overrun_hex).terrain == "open"


def pushed_units(state: State, player: int) -> list[Unit]:
    """Rule 35.8: the infantry on foot of this player in the hex of an enemy vehicle.

    The vehicle is working and on the board. A hidden vehicle is on its owner's record and
    not on the board (rule 42.1), so it pushes nothing.
    """
    out: list[Unit] = []
    for vehicle in r28_vehicles.vehicles(state, 1 - player):
        if vehicle.hex is None or vehicle.wreck or vehicle.hidden:
            continue
>>>>>>> Stashed changes
        out.extend(u for u in targets_in(state, vehicle.hex, vehicle.player) if not u.hidden)
    return sorted(out, key=lambda u: u.id)


def push_hexes(board: Board, state: State, types: Mapping[str, UnitType], unit: Unit) -> list[HexRef]:
    """Rule 35.8 and PR-51: the adjacent hexes this unit may step into.

    The hex is on the board, the hexside is not a cliff, the hex holds no enemy unit and no
    enemy concealment counter, and the unit fits the stacking limit of rule 6.1 there.
    """
    from slcore.rules import r05_movement, r06_stacking

    if unit.hex is None:
        return []
    out: list[HexRef] = []
    for direction in range(6):
        dst = geometry.neighbor(unit.hex[0], unit.hex[1], direction)
        if dst not in board:
            continue
        if board.hexside(unit.hex, direction) == CLIFF:
            continue
        if r05_movement.enemy_in_hex(state, unit.player, dst):
            continue
        if r06_stacking.rule_6_1_overstacked(state, types, dst, unit.player, extra_ids=(unit.id,)):
            continue
        out.append(dst)
    return sorted(out)


def legal_pushes(board: Board, state: State, types: Mapping[str, UnitType], player: int) -> list[Command]:
    """PR-51: one command for each unit and each hex it may step into."""
    return [
        Command("push_out", units=(unit.id,), hex=dst)
        for unit in pushed_units(state, player)
        for dst in push_hexes(board, state, types, unit)
    ]


def apply_push(state: State, command: Command) -> tuple[State, list[Event]]:
    """Rule 35.8: the unit and the weapons it carries step to the hex the owner chose."""
    dst = command.hex
    if dst is None:
        raise ValueError("a push out needs a hex")
    unit = state.units[command.units[0]]
    vehicle = r28_vehicles.vehicle_in(state, unit.hex)
    changed = {unit.id: unit.with_(hex=dst)}
    for weapon in state.carried_by(unit.id):
        changed[weapon.id] = weapon.with_(hex=dst)
    return state.with_units(changed), [
        Event(
            RULE_35_8,
            "pushed_out",
            {"unit": unit.id, "vehicle": None if vehicle is None else vehicle.id, "hex": geometry.hex_id(*dst)},
        )
    ]


def crush_left(board: Board, state: State, types: Mapping[str, UnitType], player: int) -> tuple[State, list[Event]]:
    """Rule 35.8: a unit that has no hex to step into is eliminated with its weapons.

    The window gives each unit with a hex a command, and it does not close while one of
    them is left, so the units here are the ones the board edge, the stacking limit, a
    cliff, or an enemy unit pins in place.
    """
    events: list[Event] = []
    changed: dict[int, Unit] = {}
    for unit in pushed_units(state, player):
        vehicle = r28_vehicles.vehicle_in(state, unit.hex)
        changed[unit.id] = unit.with_(eliminated=True, hex=None)
        for weapon in state.carried_by(unit.id):
            changed[weapon.id] = weapon.with_(eliminated=True, hex=None, carrier=None)
        events.append(Event(RULE_35_8, "crushed", {"unit": unit.id, "vehicle": None if vehicle is None else vehicle.id}))
    return (state.with_units(changed) if changed else state), events


def carries_passengers(state: State, vehicle_id: int) -> bool:
    """Rule 35.5: a vehicle with passengers may not drive them into an overrun."""
    return bool(r31_transport.riders(state, vehicle_id))


# ------------------------------------------------------------------ the command handler (M3)
# Rule 35.8: the step to one side is a move of the infantry.


@actions.action("push_out", unconceals=actions.CAUSE_MOVED)
def _on_push_out(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    return apply_push(state, command)
