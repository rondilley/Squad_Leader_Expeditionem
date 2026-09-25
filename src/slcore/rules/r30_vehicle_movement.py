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

from slcore import actions, geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import State
from slcore.geometry import HexRef
from slcore.rng import roll_die
from slcore.rules import r28_vehicles, r31_transport, r35_overrun, r42_hidden
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
    """Rule 30 chart and PR-50: the move goes through a hexside that the road crosses.

    Two road hexes that touch do not always share a road. The hexside must carry it.
    """
    direction = geometry.direction_to(src, dst)
    if direction is None:
        return False
    return board.road_crosses(src, direction)


def seen_vehicle_in(state: State, hex_ref: HexRef, player: int) -> Unit | None:
    """The working vehicle of a hex as this player knows it.

    A hidden vehicle of the other side is on its owner's record and not on the board
    (rule 42.1), so it changes no legal list and no cost of this player (PR-49).
    """
    for u in state.units_in(hex_ref):
        if u.is_vehicle and not u.wreck and (u.player == player or not u.hidden):
            return u
    return None


def enemy_vehicle_in(state: State, player: int, hex_ref: HexRef) -> Unit | None:
    found = seen_vehicle_in(state, hex_ref, player)
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

    occupants = len(
        [u for u in state.units_in(dst) if u.is_vehicle and (u.player == vehicle.player or not u.hidden)]
    )
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


def can_leave(ctx: VehicleContext, state: State, vehicle: Unit, dst: HexRef, remaining: int, facing: int) -> bool:
    """Rule 30.8: a vehicle may not stop in a hex that holds another vehicle.

    A move into such a hex is legal only when the vehicle can pay its way out again. The
    facing the move names (PR-21) is the one the exit costs are read with, because rule
    29.4 charges a move out of the covered arc.
    """
    if vehicle.hex is None:
        return False
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
        crowded = seen_vehicle_in(state, dst, vehicle.player) is not None
        # Rule 30.5 and PR-21: the vehicle takes any facing in the hex it enters, and the
        # move command names it.
        for facing in range(6):
            if crowded and not can_leave(ctx, state, vehicle, dst, left, facing):
                continue
            out.append(Command("vehicle_move", units=(vehicle.id,), hex=dst, extra=(("facing", facing),)))
    return out


def pivots_for(ctx: VehicleContext, state: State, vehicle: Unit) -> list[Command]:
    """Rule 30.5 and rule 33.31 case E: a turn inside the hex, which the fire rules charge.

    PR-30: at most one free pivot in a movement phase. A pivot costs no movement point
    (rule 33.32), so without this limit a vehicle turns back and forth without end and the
    game never terminates. One pivot reads a facing straight from the payload and reaches
    any of the six facings, so a second pivot is never necessary. The `pivoted` flag resets
    on the per-turn movement reset (engine), so a vehicle pivots once each player turn.
    """
    if vehicle.hex is None or vehicle.immobilized or vehicle.pivoted:
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
    facing = command_facing(command)
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


# ------------------------------------------------------------------ the command handlers (M3)


@actions.action("vehicle_move", unconceals=actions.CAUSE_MOVED)
def _on_vehicle_move(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    """Rule 30 with the overrun of rule 35 and the reveal of rule 42.6."""
    vehicle_id = command.units[0]
    target = command.hex
    mover = state.units[vehicle_id]
    src = mover.hex
    if target is None or src is None:
        raise ValueError("a vehicle move needs a vehicle on the board and a destination")
    overrun = r35_overrun.may_overrun(state, mover, target)
    hidden_here = r42_hidden.enemy_hidden_in(state, target, mover.player)
    hidden_vehicle = any(
        u.is_vehicle and not u.wreck for u in r42_hidden.hidden_in(state, target) if u.player != mover.player
    )
    events: list[Event] = []
    attacks = overrun or (hidden_here and not mover.overran)
    if attacks and not hidden_vehicle and r35_overrun.carries_passengers(state, vehicle_id):
        # Rule 35.5: the passengers do not ride into the overrun hex. They get off in the
        # hex the vehicle leaves, before it enters.
        state, off = r31_transport.force_dismount(
            engine.board, state, vehicle_id, r35_overrun.RULE_35_5, "an overrun", charge=False
        )
        events.extend(off)
    state, moved = apply_move(engine.vehicle_ctx, state, command)
    events.extend(moved)
    if hidden_here:
        # Rule 42.6: the moving player is told, the hidden unit is overrun, and it loses
        # its hidden status at once.
        state, shown = r42_hidden.reveal_in(state, target, None, r35_overrun.RULE_42_6, r42_hidden.RULE_42_2)
        events.extend(shown)
        if hidden_vehicle:
            # PR-49: an AFV does not overrun an AFV (rule 35.1) and does not stop in a hex
            # with another vehicle (rule 30.8). The vehicle goes back to the hex it came
            # from, with the cost of the entry spent.
            state, back = _back_from_hidden_vehicle(state, vehicle_id, src, target)
            events.extend(back)
            return state, events
        overrun = not state.units[vehicle_id].overran
    if overrun:
        state, ev = r35_overrun.resolve(engine.armor_ctx, engine.fire_ctx, state, vehicle_id, target)
        events.extend(ev)
    return state, events


def _back_from_hidden_vehicle(state: State, vehicle_id: int, src: HexRef, tried: HexRef) -> tuple[State, list[Event]]:
    """PR-49: the vehicle that met a hidden AFV stands again in the hex it left."""
    vehicle = state.units[vehicle_id]
    changed = {vehicle_id: vehicle.with_(hex=src, track=vehicle.track[:-1])}
    for rider in r28_vehicles.passengers_of(state, vehicle_id):
        changed[rider.id] = rider.with_(hex=src, track=rider.track[:-1])
        for weapon in state.carried_by(rider.id):
            changed[weapon.id] = weapon.with_(hex=src)
    return state.with_units(changed), [
        Event(
            r35_overrun.RULE_42_6,
            "stopped",
            {"unit": vehicle_id, "hex": geometry.hex_id(*src), "tried": geometry.hex_id(*tried)},
        )
    ]


@actions.action("vehicle_pivot", unconceals=actions.CAUSE_MOVED)
def _on_vehicle_pivot(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    return apply_pivot(engine.vehicle_ctx, state, command)
