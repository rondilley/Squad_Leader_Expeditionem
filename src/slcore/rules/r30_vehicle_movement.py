"""Rule 30, AFV movement, with the Vehicle Movement Cost Chart and rule 39.1.

Movement points are in halves, so the half point of a road move is the integer 1 and no
rule path needs a fraction (NFR-05).

Rule 30.5 says a vehicle changes its facing freely after it moves into a hex and moves
with its front towards the hex it enters. The chart charges a vehicle that enters a hex
outside its covered arc, which is the cost of turning to face that hex. The two together
give one rule the core can apply: the move pays the extra when the destination is outside
the arc the vehicle has, and the player names the facing the vehicle takes on arrival
(PR-21).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from slcore import geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import State
from slcore.geometry import HexRef
from slcore.rng import roll_die
from slcore.rules import r28_vehicles
from slcore.state import Board, HexsideRule, TerrainType
from slcore.tabledata import VehicleMovement
from slcore.units import CLASS_JEEP, CLASS_TRUCK, MOVE_MODE_SOLO, Unit, UnitType

RULE_30_1 = "30.1"
RULE_30_2 = "30.2"
RULE_30_3 = "30.3"
RULE_30_5 = "30.5"
RULE_30_6 = "30.6"
RULE_30_7 = "30.7"
RULE_30_8 = "30.8"
RULE_39_1 = "39.1"
RULE_40_3 = "40.3"

GERMAN_BREAKDOWN = 5
OTHER_BREAKDOWN = 6


@dataclass(frozen=True)
class VehicleContext:
    board: Board
    terrain: Mapping[str, TerrainType]
    hexsides: Mapping[str, HexsideRule]
    types: Mapping[str, UnitType]
    chart: VehicleMovement


def is_truck(types: Mapping[str, UnitType], unit: Unit) -> bool:
    return types[unit.type_key].vehicle_class in (CLASS_TRUCK, CLASS_JEEP)


def allowance_halves(types: Mapping[str, UnitType], unit: Unit) -> int:
    """Rule 28.1: the movement points of the counter, in halves."""
    return types[unit.type_key].mp_halves


def breakdown_number(types: Mapping[str, UnitType], unit: Unit) -> int:
    """Rule 39.1: a 6 breaks an American or a Russian vehicle, a 5 or a 6 a German one."""
    return GERMAN_BREAKDOWN if types[unit.type_key].nationality == "german" else OTHER_BREAKDOWN


def along_road(board: Board, src: HexRef, dst: HexRef) -> bool:
    """Rule 30 chart: the move goes along a road, through the hexside the road crosses."""
    return board.hex(src).road and board.hex(dst).road


def enemy_vehicle_in(state: State, player: int, hex_ref: HexRef) -> Unit | None:
    found = r28_vehicles.vehicle_in(state, hex_ref)
    return found if found is not None and found.player != player else None


def enemy_infantry_in(state: State, player: int, hex_ref: HexRef) -> bool:
    """Rule 30.7 and rule 35: infantry of the other side that the moving player can see."""
    return any(
        u.player != player and u.is_infantry and not u.hidden and not u.riding
        for u in state.units_in(hex_ref)
    )


def entry_cost_halves(
    ctx: VehicleContext, state: State, vehicle: Unit, dst: HexRef
) -> tuple[int | None, tuple[str, ...], bool]:
    """The cost to enter dst, the rule IDs applied, and whether rule 39.1 needs its die.

    A cost of None means the chart does not allow the move.
    """
    src = vehicle.hex
    if src is None:
        return None, (), False
    direction = geometry.direction_to(src, dst)
    if direction is None:
        return None, (), False
    chart = ctx.chart
    truck = is_truck(ctx.types, vehicle)
    from_hex = ctx.board.hex(src)
    to_hex = ctx.board.hex(dst)
    rules = [RULE_30_2]
    total = 0

    feature = from_hex.hexsides[direction]
    if feature is not None:
        extra = chart.hexside_cost(feature, truck)
        if extra is None:
            return None, (RULE_30_1,), False
        total += extra

    road = along_road(ctx.board, src, dst)
    breakdown = False
    if road:
        cost = chart.extra_cost("road", truck)
        if cost is None:
            return None, (RULE_30_2,), False
        total += cost
    else:
        cost = chart.terrain_cost(to_hex.terrain, truck)
        if cost is None:
            return None, (RULE_30_1,), False
        total += cost
        if chart.needs_breakdown_roll(to_hex.terrain):
            breakdown = True
            rules.append(RULE_39_1)

    if to_hex.elevation > from_hex.elevation:
        total += chart.extra_cost("higher_terrain", truck) or 0

    occupants = len([u for u in state.units_in(dst) if u.is_vehicle])
    if occupants:
        total += (chart.extra_cost("each_vehicle_or_wreck", truck) or 0) * occupants
        rules.append(RULE_40_3)

    if state.smoke_in(dst):
        total += chart.extra_cost("smoke", truck) or 0

    if not r28_vehicles.in_covered_arc(src, vehicle.facing, dst):
        total += chart.extra_cost("outside_covered_arc", truck) or 0
        rules.append("29.4")

    hostile_vehicle = enemy_vehicle_in(state, vehicle.player, dst)
    if hostile_vehicle is not None:
        extra = chart.extra_cost("enemy_afv_hex", truck)
        if extra is None:
            return None, (RULE_30_7,), False
        total += extra
        rules.append(RULE_30_7)
    elif enemy_infantry_in(state, vehicle.player, dst):
        # Rule 30.7: a vehicle may enter an enemy occupied hex, and rule 35 makes that an
        # overrun. The chart gives no extra for infantry, so the cost is the terrain cost.
        rules.append(RULE_30_7)

    return total, tuple(rules), breakdown


def can_leave(ctx: VehicleContext, state: State, vehicle: Unit, dst: HexRef, remaining: int) -> bool:
    """Rule 30.8: a vehicle may not stop in a hex that holds another vehicle.

    A move into such a hex is legal only when the vehicle can pay its way out again. The
    facing it will have on arrival is the one the exit costs are read with, because rule
    29.4 charges a move out of the covered arc and PR-21 fixes the arrival facing.
    """
    if vehicle.hex is None:
        return False
    direction = geometry.direction_to(vehicle.hex, dst)
    facing = arrival_facing(direction) if direction is not None else vehicle.facing
    standing = vehicle.with_(hex=dst, facing=facing)
    for onward in ctx.board.neighbors(dst):
        if onward == vehicle.hex:
            continue
        cost, _, _ = entry_cost_halves(ctx, state, standing, onward)
        if cost is not None and cost <= remaining:
            return True
    return False


def must_leave(state: State, vehicle: Unit) -> bool:
    """Rule 30.8: this vehicle shares its hex with another working vehicle.

    A vehicle that was destroyed or immobilized while it drove through the hex is the
    exception the rule names, so it stays where it stopped.
    """
    if vehicle.hex is None or vehicle.wreck or vehicle.immobilized:
        return False
    return any(
        u.id != vehicle.id and u.is_vehicle and not u.wreck and not u.eliminated and u.hex == vehicle.hex
        for u in state.units
    )


def movers(state: State, types: Mapping[str, UnitType], player: int) -> list[Unit]:
    """Rule 30.4: vehicles of the phasing player that may still move this phase.

    Rule 33.2 stops a vehicle that fired in the Prep Fire Phase, rule 39 stops one that is
    immobilized, and rule 31.3 stops one that infantry boarded this turn.
    """
    return [
        u
        for u in r28_vehicles.vehicles(state, player)
        if u.hex is not None and not u.wreck and not u.immobilized and not u.prep_fired and not u.boarded
    ]


def legal_moves(ctx: VehicleContext, state: State) -> list[Command]:
    out: list[Command] = []
    for vehicle in movers(state, ctx.types, state.active):
        out.extend(moves_for(ctx, state, vehicle))
        out.extend(pivots_for(ctx, state, vehicle))
    return out


def moves_for(ctx: VehicleContext, state: State, vehicle: Unit) -> list[Command]:
    if vehicle.hex is None:
        return []
    allowance = allowance_halves(ctx.types, vehicle)
    remaining = allowance - vehicle.mp_used
    out: list[Command] = []
    for d in range(6):
        dst = geometry.neighbor(*vehicle.hex, d)
        if dst not in ctx.board:
            continue
        cost, _, _ = entry_cost_halves(ctx, state, vehicle, dst)
        if cost is None:
            continue
        # Rule 30.3: a vehicle always moves one hex per turn, whatever the chart says.
        if cost > remaining and vehicle.mp_used > 0:
            continue
        left = max(0, remaining - cost)
        if r28_vehicles.vehicle_in(state, dst) is not None and not can_leave(ctx, state, vehicle, dst, left):
            continue
        out.append(Command("vehicle_move", units=(vehicle.id,), hex=dst))
    return out


def arrival_facing(direction: int) -> int:
    """PR-21: the spine a vehicle takes when it moves one hex in this direction.

    The front of a vehicle covers two hexsides, so a direction of travel has two facings
    that put it in the covered arc. The move takes the first of them and the free pivot
    command of rule 30.5 reaches the other, so no two commands do the same thing.
    """
    return (direction - 1) % 6


def pivots_for(ctx: VehicleContext, state: State, vehicle: Unit) -> list[Command]:
    """Rule 30.5 and rule 33.31 case E: a turn inside the hex, which the fire rules charge."""
    if vehicle.hex is None or vehicle.immobilized:
        return []
    return [
        Command("vehicle_pivot", units=(vehicle.id,), extra=(("facing", facing),))
        for facing in range(6)
        if facing != vehicle.facing
    ]


def command_facing(command: Command) -> int:
    for key, value in command.extra:
        if key == "facing":
            return int(value)
    raise ValueError("a vehicle command needs a facing (PR-21)")


def apply_move(ctx: VehicleContext, state: State, command: Command) -> tuple[State, list[Event]]:
    vehicle = state.units[command.units[0]]
    dst = command.hex
    if dst is None or vehicle.hex is None:
        raise ValueError("a vehicle move needs a vehicle on the board and a destination")
    cost, rules, breakdown = entry_cost_halves(ctx, state, vehicle, dst)
    if cost is None:
        raise ValueError("the vehicle movement chart does not allow that move")
    direction = geometry.direction_to(vehicle.hex, dst)
    if direction is None:
        raise ValueError("a vehicle moves one hex at a time")
    facing = arrival_facing(direction)
    src = vehicle.hex
    moved = vehicle.with_(
        hex=dst,
        facing=facing,
        moved=True,
        mp_used=vehicle.mp_used + cost,
        move_mode=MOVE_MODE_SOLO,
        track=vehicle.track + (dst,),
    )
    changed = {moved.id: moved}
    for rider in r28_vehicles.passengers_of(state, vehicle.id):
        changed[rider.id] = rider.with_(hex=dst, moved=True, track=rider.track + (dst,))
        for weapon in state.carried_by(rider.id):
            changed[weapon.id] = weapon.with_(hex=dst)
    events = [
        Event(
            RULE_30_2,
            "vehicle_move",
            {
                "unit": vehicle.id,
                "from": geometry.hex_id(*src),
                "to": geometry.hex_id(*dst),
                "cost_halves": cost,
                "facing": facing,
                "rules": list(rules),
            },
        )
    ]
    state = state.with_units(changed)
    if breakdown:
        state, ev = breakdown_roll(ctx, state, moved.id)
        events.extend(ev)
    return state, events


def breakdown_roll(ctx: VehicleContext, state: State, vehicle_id: int) -> tuple[State, list[Event]]:
    """Rule 39.1: one die on entering a woods hex or a wooden building hex."""
    vehicle = state.units[vehicle_id]
    rng, die = roll_die(state.rng)
    state = state.with_(rng=rng)
    needed = breakdown_number(ctx.types, vehicle)
    events = [
        Event(
            RULE_39_1,
            "breakdown_roll",
            {"unit": vehicle_id, "die": die, "breaks_on": needed, "immobilized": die >= needed},
        )
    ]
    if die >= needed:
        state = state.with_unit(state.units[vehicle_id].with_(immobilized=True))
    return state, events


def apply_pivot(ctx: VehicleContext, state: State, command: Command) -> tuple[State, list[Event]]:
    vehicle = state.units[command.units[0]]
    facing = command_facing(command)
    turned = vehicle.with_(facing=facing, pivoted=True)
    return state.with_unit(turned), [
        Event(RULE_30_5, "vehicle_pivot", {"unit": vehicle.id, "facing": facing, "was": vehicle.facing})
    ]
