"""Rule 38, fate versus armor, and the parts of rules 40 and 41 that stand alone.

Rule 38.1 breaks a main gun on an unmodified twelve on the to-hit dice, and the gun is
repaired one die at a time in the Rally Phase: a one puts it back in order and a six
disables it for the game. Rule 38.2 does the same for the machine guns of the vehicle,
with the twelve on the Infantry Fire Table instead.

Rule 40.4 lets a working vehicle push a wreck out of the way. Rule 41.3 lets a tank fire
smoke instead of its main armament, and rule 41.4 gives every German tank one set of smoke
dischargers for its own hex.
"""

from __future__ import annotations

from slcore import geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import PHASE_PREP_FIRE, State
from slcore.geometry import HexRef
from slcore.rng import roll_die
from slcore.rules import r24_smoke, r28_vehicles, r33_afv_combat
from slcore.rules.r33_afv_combat import ArmorContext
from slcore.units import Unit

RULE_38_1 = "38.1"
RULE_38_2 = "38.2"
RULE_40_4 = "40.4"
RULE_41_3 = "41.3"
RULE_41_4 = "41.4"

REPAIR_ROLL = 1
DISABLE_ROLL = 6
GERMAN = "german"
SMOKE_ROW = "infantry_in_other"


def repairable(vehicle: Unit) -> tuple[bool, bool]:
    """Whether the main gun and the machine guns of this vehicle can be worked on."""
    main = vehicle.malfunction and not vehicle.disabled and not vehicle.wreck
    machine = vehicle.mg_malfunction and not vehicle.mg_disabled and not vehicle.wreck
    return main, machine


def legal_repairs(state: State, player: int) -> list[Command]:
    """Rule 38.1 and rule 38.2: one repair attempt for each broken weapon in the Rally Phase."""
    out: list[Command] = []
    for vehicle in r28_vehicles.vehicles(state, player):
        if vehicle.repair_tried:
            continue
        main, machine = repairable(vehicle)
        if main:
            out.append(Command("afv_repair", units=(vehicle.id,), extra=(("armament", "main"),)))
        if machine:
            out.append(Command("afv_repair", units=(vehicle.id,), extra=(("armament", "mg"),)))
    return out


def repair_target(command: Command) -> str:
    """Which armament this repair works on. The key is not `weapon`, because that name
    belongs to the support weapon field of a command payload."""
    for key, value in command.extra:
        if key == "armament":
            return str(value)
    raise ValueError("a vehicle repair command names the main gun or the machine guns")


def apply_repair(state: State, command: Command) -> tuple[State, list[Event]]:
    """Rule 38.1: one die. A one repairs, a six disables, anything else waits a turn."""
    vehicle = state.units[command.units[0]]
    which = repair_target(command)
    rng, die = roll_die(state.rng)
    state = state.with_(rng=rng)
    data = {"unit": vehicle.id, "weapon": which, "die": die}
    changed = vehicle.with_(repair_tried=True)
    rule = RULE_38_1 if which == "main" else RULE_38_2
    if die == REPAIR_ROLL:
        changed = changed.with_(malfunction=False) if which == "main" else changed.with_(mg_malfunction=False)
        return state.with_unit(changed), [Event(rule, "afv_repaired", data)]
    if die == DISABLE_ROLL:
        changed = changed.with_(disabled=True) if which == "main" else changed.with_(mg_disabled=True)
        return state.with_unit(changed), [Event(rule, "afv_disabled", data)]
    return state.with_unit(changed), [Event(rule, "afv_repair_failed", data)]


# ------------------------------------------------------------------------ the wrecks


def legal_wreck_pushes(state: State, board, player: int) -> list[Command]:
    """Rule 40.4: a working vehicle next to a wreck may push it away in the Rally Phase."""
    out: list[Command] = []
    for vehicle in r28_vehicles.vehicles(state, player):
        if vehicle.hex is None or vehicle.wreck or vehicle.immobilized or vehicle.moved or vehicle.fired:
            continue
        for neighbour in board.neighbors(vehicle.hex):
            if r28_vehicles.wrecks_in(state, neighbour) and r28_vehicles.vehicle_in(state, neighbour) is None:
                out.append(Command("push_wreck", units=(vehicle.id,), hex=neighbour))
    return out


def apply_wreck_push(state: State, command: Command) -> tuple[State, list[Event]]:
    """Rule 40.4 with PR-28: the wreck leaves the board and the vehicle takes its hex.

    Rule 40.4 spends two player turns on this: the vehicle neither moves nor fires in the
    first, and it ends the second in the hex the wreck held. The core does both at once and
    marks the vehicle as having spent its turn, which reaches the same board position.
    """
    vehicle = state.units[command.units[0]]
    hex_ref = command.hex
    if hex_ref is None or vehicle.hex is None:
        raise ValueError("a wreck push needs the wreck's hex")
    changed = {}
    removed: list[int] = []
    for wreck in r28_vehicles.wrecks_in(state, hex_ref):
        changed[wreck.id] = wreck.with_(eliminated=True, hex=None)
        removed.append(wreck.id)
    changed[vehicle.id] = vehicle.with_(hex=hex_ref, moved=True, prep_fired=True, fired=True)
    return state.with_units(changed), [
        Event(
            RULE_40_4,
            "wreck_pushed",
            {"unit": vehicle.id, "hex": geometry.hex_id(*hex_ref), "wrecks": removed},
        )
    ]


# ------------------------------------------------------------------------- the smoke


def may_fire_smoke(ctx: ArmorContext, state: State, vehicle: Unit, phase: str) -> bool:
    """Rule 41.3: smoke instead of the main armament, at the outset of the Prep Fire Phase."""
    if phase != PHASE_PREP_FIRE or vehicle.hex is None:
        return False
    if state.smoke_left[vehicle.player] <= 0:
        return False
    return r33_afv_combat.may_fire_main(ctx, state, vehicle, phase) and not vehicle.mg_fired


def smoke_targets(ctx: ArmorContext, state: State, vehicle: Unit) -> list[HexRef]:
    """Rule 41.3: any hex that is neither the vehicle's own nor next to it."""
    if vehicle.hex is None:
        return []
    near = set(ctx.board.neighbors(vehicle.hex)) | {vehicle.hex}
    return [h.ref for h in ctx.board if h.ref not in near and not state.smoke_in(h.ref)]


def legal_smoke(ctx: ArmorContext, state: State, player: int, phase: str) -> list[Command]:
    out: list[Command] = []
    for vehicle in r28_vehicles.vehicles(state, player):
        if may_fire_smoke(ctx, state, vehicle, phase):
            for hex_ref in smoke_targets(ctx, state, vehicle):
                out.append(Command("afv_smoke", units=(vehicle.id,), hex=hex_ref))
        if may_discharge(ctx, state, vehicle, phase):
            out.append(Command("afv_dischargers", units=(vehicle.id,)))
    return out


def apply_smoke(ctx: ArmorContext, state: State, command: Command) -> tuple[State, list[Event]]:
    """Rule 41.3: the to-hit roll against the `infantry in other` row places the smoke."""
    vehicle = state.units[command.units[0]]
    hex_ref = command.hex
    if hex_ref is None or vehicle.hex is None:
        raise ValueError("a smoke round needs a target hex")
    state, result = r33_afv_combat.roll_to_hit(ctx, state, vehicle, hex_ref, SMOKE_ROW, ())
    events = [r33_afv_combat.to_hit_event(vehicle, hex_ref, result)]
    state, marked = r33_afv_combat.mark_gun_fired(state, vehicle, result)
    events.extend(marked)
    if not result.hit:
        return state, events
    state, placed = r24_smoke.place(state, vehicle.id, hex_ref)
    events.append(Event(RULE_41_3, "afv_smoke", {"unit": vehicle.id, "hex": geometry.hex_id(*hex_ref)}))
    events.extend(placed)
    return state, events


def may_discharge(ctx: ArmorContext, state: State, vehicle: Unit, phase: str) -> bool:
    """Rule 41.4: one set of smoke dischargers on a German tank or self-propelled gun."""
    if vehicle.hex is None or vehicle.wreck or vehicle.dischargers_used:
        return False
    kind = ctx.types[vehicle.type_key]
    if kind.nationality != GERMAN or not kind.is_afv:
        return False
    if state.smoke_in(vehicle.hex):
        return False
    return not vehicle.overran


def apply_dischargers(state: State, command: Command) -> tuple[State, list[Event]]:
    """Rule 41.4: smoke in the vehicle's own hex, one time in the game."""
    vehicle = state.units[command.units[0]]
    if vehicle.hex is None:
        raise ValueError("a vehicle must be on the board to use its dischargers")
    state = state.with_unit(vehicle.with_(dischargers_used=True, gun_shots=vehicle.gun_shots + 1))
    state, placed = r24_smoke.place(state, vehicle.id, vehicle.hex)
    return state, [
        Event(RULE_41_4, "smoke_dischargers", {"unit": vehicle.id, "hex": geometry.hex_id(*vehicle.hex)})
    ] + placed
