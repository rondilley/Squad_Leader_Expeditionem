"""Rule 31, transporting infantry on tanks and self-propelled guns.

A passenger sits on top of the vehicle counter (rule 31.2). In the state that is
`passenger_of`, which names the vehicle. A unit in the same hex with no `passenger_of` is
on foot beneath the counter, which rule 32 makes a different thing.
"""

from __future__ import annotations

from typing import Mapping

from slcore import geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import State
from slcore.geometry import HexRef
from slcore.rules import r05_movement, r06_stacking, r28_vehicles
from slcore.state import Board
from slcore.units import KIND_LEADER, MOVE_MODE_NONE, Unit, UnitType

RULE_31_1 = "31.1"
RULE_31_3 = "31.3"
RULE_31_4 = "31.4"
RULE_31_5 = "31.5"
RULE_31_6 = "31.6"
RULE_31_7 = "31.7"
RULE_31_8 = "31.8"

# Rule 31.1: two infantry units, of which one may be a squad, and five portage points.
MAX_RIDERS = 2
MAX_RIDING_SQUADS = 1
MAX_RIDING_PORTAGE = 5

# Rule 31.3: the vehicle pays this to let its passengers get off.
DEBARK_COST_HALVES = 4


def riders(state: State, vehicle_id: int) -> list[Unit]:
    return r28_vehicles.passengers_of(state, vehicle_id)


def riding_load(state: State, types: Mapping[str, UnitType], vehicle_id: int) -> tuple[int, int, int]:
    """The count of passengers, of squads among them, and of their portage points."""
    units = riders(state, vehicle_id)
    squads = sum(1 for u in units if types[u.type_key].is_squad_like)
    portage = 0
    for u in units:
        for w in state.carried_by(u.id):
            portage += types[w.type_key].portage_squad_halves
    return len(units), squads, portage


def has_room(state: State, types: Mapping[str, UnitType], vehicle: Unit, rider: Unit) -> bool:
    """Rule 31.1: two infantry units, one squad at most, and five portage points."""
    count, squads, portage = riding_load(state, types, vehicle.id)
    if count + 1 > MAX_RIDERS:
        return False
    if types[rider.type_key].is_squad_like and squads + 1 > MAX_RIDING_SQUADS:
        return False
    extra = sum(types[w.type_key].portage_squad_halves for w in state.carried_by(rider.id))
    return portage + extra <= MAX_RIDING_PORTAGE * 2


def can_board(state: State, types: Mapping[str, UnitType], unit: Unit, vehicle: Unit) -> bool:
    """Rules 31.4 and 31.6: an unbroken infantry unit in the vehicle's hex may get on."""
    if not unit.is_infantry or unit.riding or unit.broken or unit.carrier is not None:
        return False
    if unit.hex is None or unit.hex != vehicle.hex:
        return False
    if unit.player != vehicle.player or vehicle.wreck or vehicle.eliminated:
        return False
    if unit.prep_fired or unit.fired or unit.directed:
        return False
    if state.in_melee(unit.hex):
        return False
    return has_room(state, types, vehicle, unit)


def legal_boarding(state: State, types: Mapping[str, UnitType], player: int) -> list[Command]:
    out: list[Command] = []
    for vehicle in r28_vehicles.vehicles(state, player):
        if vehicle.hex is None or vehicle.wreck or vehicle.moved:
            # Rule 31.3: the vehicle may not move on the turn infantry board it, so the
            # core only offers boarding to a vehicle that has not moved yet this turn.
            continue
        for unit in state.units_in(vehicle.hex):
            if can_board(state, types, unit, vehicle):
                out.append(Command("board", units=(unit.id,), extra=(("vehicle", vehicle.id),)))
    return out


def legal_debarking(
    board: Board, state: State, types: Mapping[str, UnitType], player: int
) -> list[Command]:
    """Rule 31.4: a passenger gets off into its own hex or an adjacent hex with no enemy."""
    out: list[Command] = []
    for vehicle in r28_vehicles.vehicles(state, player):
        if vehicle.hex is None:
            continue
        for rider in riders(state, vehicle.id):
            for dst in (vehicle.hex,) + board.neighbors(vehicle.hex):
                if r05_movement.enemy_in_hex(state, player, dst):
                    continue
                if dst != vehicle.hex and r06_stacking.rule_6_1_overstacked(
                    state, types, dst, player, extra_ids=(rider.id,)
                ):
                    continue
                out.append(Command("debark", units=(rider.id,), hex=dst))
    return out


def command_vehicle(command: Command) -> int:
    for key, value in command.extra:
        if key == "vehicle":
            return int(value)
    raise ValueError("a board command needs a vehicle")


def apply_board(state: State, command: Command) -> tuple[State, list[Event]]:
    unit = state.units[command.units[0]]
    vehicle_id = command_vehicle(command)
    vehicle = state.units[vehicle_id]
    changed = {
        unit.id: unit.with_(passenger_of=vehicle_id, hex=vehicle.hex, move_mode=MOVE_MODE_NONE),
        # Rule 31.3: the vehicle may not move during the turn infantry board it.
        vehicle_id: vehicle.with_(boarded=True),
    }
    for weapon in state.carried_by(unit.id):
        changed[weapon.id] = weapon.with_(hex=vehicle.hex)
    return state.with_units(changed), [
        Event(RULE_31_1, "board", {"unit": unit.id, "vehicle": vehicle_id})
    ]


def apply_debark(ctx: r05_movement.MoveContext, state: State, command: Command) -> tuple[State, list[Event]]:
    unit = state.units[command.units[0]]
    dst = command.hex
    if dst is None:
        raise ValueError("a debark command needs a hex")
    vehicle_id = unit.passenger_of
    if vehicle_id is None:
        raise ValueError("only a passenger debarks")
    vehicle = state.units[vehicle_id]
    # Rule 31.4: a unit that gets off moves to the vehicle's hex or to one hex adjacent to
    # it, and the debark is that move. So it keeps no movement factors.
    spent = r05_movement.allowance_halves(ctx, state, unit, leader_bonus=False)
    changed: dict[int, Unit] = {
        unit.id: unit.with_(
            passenger_of=None, hex=dst, moved=True, mf_used=spent, track=unit.track + (dst,)
        )
    }
    for weapon in state.carried_by(unit.id):
        changed[weapon.id] = weapon.with_(hex=dst)
    events = [
        Event(
            RULE_31_4,
            "debark",
            {"unit": unit.id, "vehicle": vehicle_id, "hex": geometry.hex_id(*dst)},
        )
    ]
    # Rule 31.3: the vehicle pays two movement points, unless the unit that gets off is
    # broken. A broken passenger leaves under rule 31.6 and the vehicle pays nothing.
    if not unit.broken and not vehicle.wreck:
        changed[vehicle_id] = vehicle.with_(mp_used=vehicle.mp_used + DEBARK_COST_HALVES)
        events.append(
            Event(RULE_31_3, "debark_cost", {"vehicle": vehicle_id, "cost_halves": DEBARK_COST_HALVES})
        )
    return state.with_units(changed), events


def dismount_hex(board: Board, state: State, rider: Unit, player: int) -> HexRef | None:
    """Rules 31.6 and 31.7: the hex a passenger is put in when it must get off at once."""
    if rider.hex is None:
        return None
    if not r05_movement.enemy_in_hex(state, player, rider.hex):
        return rider.hex
    for dst in board.neighbors(rider.hex):
        if not r05_movement.enemy_in_hex(state, player, dst):
            return dst
    return None


def force_dismount(
    board: Board, state: State, vehicle_id: int, rule_id: str, cause: str, charge: bool
) -> tuple[State, list[Event]]:
    """Rules 31.6 and 31.7: every passenger gets off at once.

    Rule 31.7 makes the vehicle pay two movement points for each unit it puts off when it
    fires or takes a hit. Rule 31.6 charges nothing for a passenger that broke.
    """
    events: list[Event] = []
    changed: dict[int, Unit] = {}
    vehicle = state.units[vehicle_id]
    paid = 0
    for rider in riders(state, vehicle_id):
        dst = dismount_hex(board, state, rider, rider.player)
        if dst is None:
            continue
        changed[rider.id] = rider.with_(passenger_of=None, hex=dst)
        for weapon in state.carried_by(rider.id):
            changed[weapon.id] = weapon.with_(hex=dst)
        paid += 1
        events.append(
            Event(rule_id, "dismount", {"unit": rider.id, "vehicle": vehicle_id, "cause": cause, "hex": geometry.hex_id(*dst)})
        )
    if charge and paid and not vehicle.wreck:
        changed[vehicle_id] = vehicle.with_(mp_used=vehicle.mp_used + DEBARK_COST_HALVES * paid)
    if not changed:
        return state, []
    return state.with_units(changed), events


def kill_passengers(state: State, vehicle_id: int) -> tuple[State, list[Event]]:
    """Rule 31.8: every passenger of a destroyed vehicle is eliminated."""
    changed: dict[int, Unit] = {}
    events: list[Event] = []
    for rider in riders(state, vehicle_id):
        changed[rider.id] = rider.with_(eliminated=True, hex=None, passenger_of=None)
        for weapon in state.carried_by(rider.id):
            changed[weapon.id] = weapon.with_(eliminated=True, hex=None, carrier=None)
        events.append(Event(RULE_31_8, "passenger_eliminated", {"unit": rider.id, "vehicle": vehicle_id}))
    if not changed:
        return state, []
    return state.with_units(changed), events


def clear_boarded(state: State, player: int) -> State:
    """Rule 31.3: the hold on a vehicle lasts one turn, so the flag clears at the turn end."""
    changed = {
        u.id: u.with_(boarded=False)
        for u in r28_vehicles.vehicles(state, player)
        if u.boarded
    }
    return state.with_units(changed) if changed else state


def may_fire(unit: Unit) -> bool:
    """Rule 31.5: a unit that is being transported may not fire."""
    return not unit.riding


def leader_of(state: State, vehicle_id: int) -> Unit | None:
    for rider in riders(state, vehicle_id):
        if rider.kind == KIND_LEADER:
            return rider
    return None
