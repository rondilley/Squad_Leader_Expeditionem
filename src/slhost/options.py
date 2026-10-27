"""The options of one unit, for the overlay of a window (the `options_request` message).

A window has no rule logic (AR-06), so it cannot say why a hex refuses a counter, where
a unit can go in a whole Movement Phase, or which hexes a unit can fire at. The host
reads the core and answers for one unit of the person's side:

- In the set up (rule 21.2): the text of the set up area of the unit's group, the hexes
  of that area that the stacking limits of rule 6.1 and rule 29.2 close, and a reason for
  each hex of the area that refuses the counter. A weapon gets a reason for each hex
  where no unit can carry it. A counter of a later set up pass gets that reason.
- In the Movement Phase (rules 5.4 to 5.54): each hex the unit, or the stack it moves
  with, can enter with the movement factors it has left, with the cost in half factors.
  A move of the core is one hex, so this is the cheapest path of single steps
  (`slagents.learned.routes.reach`, the same costs as the core). The `move_to` message
  plays that path one step at a time, and each step is a command of the legal list at
  that time (`route_step`). A vehicle has its own costs (rule 30) and a facing: rule 30.5
  lets it take any facing in the hex it enters, so it faces the next hex of its path, and
  only its first step can pay the cost of a hex outside its covered arc (rule 29.4),
  unless it uses its one free pivot of PR-30 first (`vehicle_paths`).
- In a fire phase (rules 7, 9.1, 9.2): each hex in normal range and in long range of the
  unit or of a weapon it carries, with a clear line of sight. The line of sight is the
  one the core reads for a fire target (`los_eval.evaluate` with no context). In strict
  mode (rule 19.3 of the host) the field is not given, as a free line of sight check is
  not.

The answer reads the state of the person's side only: the stacking counts the person's
units, and a path does not enter a hex with an enemy that the person sees. It gives no
fact of a hidden unit of the other side (AR-09).
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any

from slagents.learned.routes import reach
from slcore import geometry
from slcore.engine import Engine
from slcore.game import PHASE_ADVANCING_FIRE, PHASE_DEFENSIVE_FIRE, PHASE_MOVEMENT, PHASE_PREP_FIRE, PHASE_SETUP, State
from slcore.los_eval import evaluate as evaluate_los
from slcore.phases import fire_rule
from slcore.geometry import HexRef
from slcore.rules import r05_movement, r06_stacking, r08_fire, r28_vehicles, r30_vehicle_movement
from slcore.rules.r05_movement import LEADER_MAX_PORTAGE
from slcore.scenario import SetupArea, band_text
from slcore.units import KIND_LEADER, KIND_SW, Unit

KIND_SETUP = "setup"
KIND_MOVE = "move"
KIND_FIRE = "fire"
KIND_NONE = "none"

FIRE_PHASES = (PHASE_PREP_FIRE, PHASE_DEFENSIVE_FIRE, PHASE_ADVANCING_FIRE)
_ORDINALS = ("largest", "second largest", "third largest", "fourth largest", "fifth largest")


def unit_options(engine: Engine, state: State, unit_id: int, strict_los: bool = False) -> dict[str, Any]:
    """The answer for one unit. The caller has made sure that the person holds its side."""
    unit = state.units[unit_id]
    if state.phase == PHASE_SETUP:
        return setup_options(engine, state, unit)
    if state.phase == PHASE_MOVEMENT:
        return move_options(engine, state, unit)
    if state.phase in FIRE_PHASES:
        return fire_options(engine, state, unit, strict_los)
    return {"kind": KIND_NONE}


def type_name(unit: Unit) -> str:
    return unit.type_key.split(":")[-1]


# --------------------------------------------------------------------------- set up


def area_text(engine: Engine, area: SetupArea) -> str:
    """The set up area of a group in words, as a card names it."""
    params = dict(area.params)
    if area.hexes:
        return "in the hexes that the scenario names"
    if area.building is not None:
        return f"in building {area.building}"
    if area.zone == "stone_building":
        rank = int(params.get("rank", 0))
        size = _ORDINALS[rank] if rank < len(_ORDINALS) else f"rank {rank + 1}"
        return f"in the {size} stone building {band_text(params)}"
    if area.zone == "edge":
        depth = max(1, int(params.get("depth", 1)))
        rows = "hex" if depth == 1 else f"{depth} hexes"
        text = f"in the {rows} next to the {params.get('side', 'west')} edge"
    else:
        text = band_text(params)
    return text + _filter_text(params)


def _filter_text(params: dict[str, Any]) -> str:
    def names(value: Any) -> str:
        kinds = [value] if isinstance(value, str) else list(value)
        return " or ".join(str(k).replace("_", " ") for k in kinds)

    parts = []
    if params.get("terrain") is not None:
        parts.append(f"on {names(params['terrain'])} hexes only")
    if params.get("not_terrain") is not None:
        parts.append(f"not in {names(params['not_terrain'])} hexes")
    if params.get("road") is True:
        parts.append("on road hexes only")
    elif params.get("road") is False:
        parts.append("not on road hexes")
    if params.get("level") is not None:
        parts.append(f"at level {int(params['level'])} only")
    return (", " + ", ".join(parts)) if parts else ""


def stacking_reason(engine: Engine, state: State, hex_ref, player: int, extra: tuple[int, ...]) -> str | None:
    """Why rule 6.1 or rule 29.2 closes this hex to these units, or None when it does not."""
    name = geometry.hex_id(*hex_ref)
    infantry, squads, portage = r06_stacking.hex_load(state, engine.types, hex_ref, player, extra_ids=extra)
    if squads > r06_stacking.LIMIT_SQUADS:
        return f"{name} would hold {squads} squads of yours. Rule 6.1 lets a hex hold {r06_stacking.LIMIT_SQUADS}."
    if infantry > r06_stacking.LIMIT_INFANTRY:
        return f"{name} would hold {infantry} infantry units of yours. Rule 6.1 lets a hex hold {r06_stacking.LIMIT_INFANTRY}."
    if portage > r06_stacking.LIMIT_PORTAGE:
        return f"{name} would hold {portage} portage points of yours. Rule 6.1 lets a hex hold {r06_stacking.LIMIT_PORTAGE}."
    if r06_stacking.beneath_a_vehicle_overstacked(state, engine.types, hex_ref, player, extra_ids=extra):
        return (
            f"{name} has a vehicle. Rule 29.2 lets {r28_vehicles.BENEATH_INFANTRY} infantry units of yours stand below it, "
            f"{r28_vehicles.BENEATH_SQUADS} of them squads."
        )
    if r06_stacking.rule_6_1_overstacked(state, engine.types, hex_ref, player, extra_ids=extra):
        return f"{name} would be over the stacking limit of rule 6.1."
    return None


def _carry_reason(engine: Engine, state: State, carrier: Unit, weapon: Unit) -> str | None:
    """Why this unit cannot take the weapon at set up, or None when it can."""
    types = engine.types
    t = types[weapon.type_key]
    if carrier.kind == KIND_LEADER:
        if t.pp_leader is None:
            return f"A leader cannot carry the {type_name(weapon)} (rule 5.7)."
        total = sum(types[w.type_key].pp_leader or 0 for w in state.carried_by(carrier.id)) + t.pp_leader
        if total > LEADER_MAX_PORTAGE:
            return f"The {type_name(carrier)} would carry {total} portage points. Rule 5.7 lets a leader carry {LEADER_MAX_PORTAGE}."
    if carrier.hex is None:
        return None
    return stacking_reason(engine, state, carrier.hex, carrier.player, (weapon.id,))


def setup_options(engine: Engine, state: State, unit: Unit) -> dict[str, Any]:
    scenario = engine.scenario
    name = type_name(unit)
    out: dict[str, Any] = {"kind": KIND_SETUP, "rule_id": "21.2", "area": "", "full": [], "why": {}, "later": ""}
    if unit.player != state.active:
        out["later"] = f"The other side sets up now. The {name} goes on the board in your set up."
        return out
    if scenario.group_pass(unit.group) != state.setup_index:
        out["later"] = f"The {name} sets up in a later step of the set up (rule 21.2)."
        return out
    area = scenario.group(unit.group).area
    hexes = area.resolve(engine.board)
    out["area"] = area_text(engine, area)
    why: dict[str, str] = {}
    full: list[str] = []
    for h in hexes:
        if unit.kind == KIND_SW:
            carriers = [
                c
                for c in state.units_in(h)
                if c.player == unit.player and c.kind != KIND_SW and c.group == unit.group and c.carrier is None and c.id != unit.id
            ]
            if not carriers:
                reason = stacking_reason(engine, state, h, unit.player, (unit.id,))
                why[geometry.hex_id(*h)] = reason or f"No unit of yours in {geometry.hex_id(*h)} can carry the {name}."
                continue
            reasons = [_carry_reason(engine, state, c, unit) for c in carriers]
            if all(reasons):
                why[geometry.hex_id(*h)] = str(reasons[0])
            continue
        reason = stacking_reason(engine, state, h, unit.player, (unit.id,))
        if reason is not None:
            why[geometry.hex_id(*h)] = reason
            full.append(geometry.hex_id(*h))
    out["why"] = why
    out["full"] = sorted(full)
    return out


# ------------------------------------------------------------------------ movement


def move_plan(engine: Engine, state: State, unit: Unit) -> tuple[tuple[int, ...] | None, int]:
    """How the unit moves now, from the legal list: the units of its step (the unit alone
    for `move`, or each unit of the stack for `stack_move`, rule 15.4), and the movement
    halves it has left. A stack moves with the factors of its slowest unit. A unit with no
    step in the list gives (None, 0).
    """
    if unit.player != state.active or unit.hex is None or unit.berserk:
        # Rule 18.42: a berserk unit moves on its charge, and the legal list has it.
        return None, 0
    frame = engine.legal_commands(state)
    solo = False
    stacks: list[tuple[int, ...]] = []
    for legal in frame.commands:
        command = legal.command
        if unit.id not in command.units:
            continue
        if command.action == "move":
            solo = True
        elif command.action == "stack_move":
            stacks.append(command.units)
    if not solo and not stacks:
        return None, 0
    ctx = engine.move_ctx
    if solo:
        return (unit.id,), r05_movement.allowance_halves(ctx, state, unit, False) - unit.mf_used
    # Each step of a stack names the same units, and a leader is in each stack it leads.
    ids = stacks[0]
    leaders = [i for i in ids if state.units[i].kind == KIND_LEADER]
    left = min(r05_movement.allowance_halves(ctx, state, state.units[i], i not in leaders) - state.units[i].mf_used for i in ids)
    return ids, left


def move_paths(engine: Engine, state: State, unit: Unit) -> tuple[tuple[int, ...] | None, int, dict]:
    """The step units, the halves left, and the cheapest path to each hex the unit reaches."""
    ids, left = move_plan(engine, state, unit)
    if ids is None or left <= 0 or unit.hex is None:
        return ids, max(0, left), {}
    return ids, left, reach(engine, state, unit.player, unit.hex, left)


@dataclass(frozen=True)
class Step:
    """One command of a route: its action, its units, and its hex and facing, if any."""

    action: str
    units: tuple[int, ...]
    hex: HexRef | None = None
    facing: int | None = None


@dataclass(frozen=True)
class VehicleReach:
    """The hexes a vehicle can stop in: the cost, the path, and the use of the pivot."""

    left: int
    cost: dict[HexRef, int]
    path: dict[HexRef, tuple[HexRef, ...]]
    pivot: dict[HexRef, bool]


def _vehicle_can_move(engine: Engine, state: State, vehicle: Unit) -> tuple[bool, bool]:
    """Whether the legal list moves this vehicle now, and whether it can pivot (PR-30)."""
    moves = pivots = False
    for legal in engine.legal_commands(state).commands:
        command = legal.command
        if tuple(command.units) != (vehicle.id,):
            continue
        moves = moves or command.action == "vehicle_move"
        pivots = pivots or command.action == "vehicle_pivot"
    return moves, pivots


def vehicle_paths(engine: Engine, state: State, vehicle: Unit) -> VehicleReach:
    """The cheapest path to each hex the vehicle can stop in, by the costs of the core.

    The search runs over the hex and the use of the pivot. Rule 30.5 lets the vehicle take
    any facing in the hex it enters, so each step after the first faces its next hex and
    pays no cost of rule 29.4. The first step leaves with the facing the vehicle has, or,
    after the pivot, with the facing to the first hex. Rule 30.3 gives a vehicle that has
    not moved its first hex whatever the cost. A hex of an enemy unit is the end of a path
    (rule 30.7 and the overrun of rule 35), and a hex of another vehicle of the side is a
    hex to go through and not to stop in (rule 30.8).
    """
    ctx = engine.vehicle_ctx
    empty = VehicleReach(0, {}, {}, {})
    if ctx is None or vehicle.hex is None or vehicle.player != state.active:
        return empty
    moves, can_pivot = _vehicle_can_move(engine, state, vehicle)
    if not moves:
        return empty
    left = r30_vehicle_movement.allowance_halves(engine.types, vehicle) - vehicle.mp_used
    first_free = vehicle.mp_used == 0
    start = vehicle.hex
    player = vehicle.player
    best: dict[tuple[HexRef, bool], int] = {}
    previous: dict[tuple[HexRef, bool], tuple[HexRef, bool]] = {}
    heap: list[tuple[int, int, HexRef]] = []
    for pivoted in (False, True) if can_pivot else (False,):
        best[(start, pivoted)] = 0
        heapq.heappush(heap, (0, int(pivoted), start))
    while heap:
        spent, flag, here = heapq.heappop(heap)
        key = (here, bool(flag))
        if spent > best.get(key, spent):
            continue
        if here != start:
            if spent >= left:
                continue
            if r30_vehicle_movement.enemy_infantry_in(state, player, here):
                continue
            if r30_vehicle_movement.enemy_vehicle_in(state, player, here) is not None:
                continue
        for nxt in engine.board.neighbors(here):
            if nxt == start:
                continue
            if here == start:
                facing = r28_vehicles.facing_towards(here, nxt) if flag else vehicle.facing
            else:
                facing = r28_vehicles.facing_towards(here, nxt)
            probe = vehicle.with_(hex=here, facing=facing)
            cost, _, _ = r30_vehicle_movement.entry_cost_halves(ctx, state, probe, nxt)
            if cost is None:
                continue
            total = spent + cost
            if total > left:
                if not (here == start and first_free):
                    continue
                total = left
            nkey = (nxt, bool(flag))
            if total < best.get(nkey, left + 1):
                best[nkey] = total
                previous[nkey] = key
                heapq.heappush(heap, (total, flag, nxt))
    out = VehicleReach(max(0, left), {}, {}, {})
    # The path with no pivot comes first, so a tie keeps the pivot for later in the phase.
    for (hex_ref, pivoted), total in sorted(best.items(), key=lambda item: (item[0][0], item[0][1])):
        if hex_ref == start:
            continue
        if r30_vehicle_movement.seen_vehicle_in(state, hex_ref, player) is not None:
            continue
        held = out.cost.get(hex_ref)
        if held is not None and held <= total:
            continue
        path = [hex_ref]
        key = (hex_ref, pivoted)
        while previous[key][0] != start:
            key = previous[key]
            path.append(key[0])
        out.cost[hex_ref] = total
        out.path[hex_ref] = tuple(reversed(path))
        out.pivot[hex_ref] = pivoted
    return out


def move_options(engine: Engine, state: State, unit: Unit) -> dict[str, Any]:
    """The hexes the unit can enter in the rest of this Movement Phase, with the cost of
    the cheapest path to each in half movement factors (movement points for a vehicle)."""
    out: dict[str, Any] = {"kind": KIND_MOVE, "rule_id": "5.4", "reach": {}, "left": 0}
    if unit.is_vehicle:
        found = vehicle_paths(engine, state, unit)
        out["rule_id"] = "30.2"
        out["left"] = found.left
        out["reach"] = {geometry.hex_id(*h): cost for h, cost in found.cost.items()}
        return out
    _ids, left, paths = move_paths(engine, state, unit)
    out["left"] = left
    ctx = engine.move_ctx
    costs: dict[str, int] = {}
    for dest, path in paths.items():
        spent = 0
        here = unit.hex
        for step in path:
            cost, _ = r05_movement.entry_cost_halves(ctx, here, step)
            spent += cost or 0
            here = step
        costs[geometry.hex_id(*dest)] = spent
    out["reach"] = costs
    return out


def route(engine: Engine, state: State, unit: Unit, target: HexRef) -> list[Step] | None:
    """The commands that move the unit to the hex by the path of `move_options`, or None
    when the unit cannot get there in this phase."""
    if unit.is_vehicle:
        found = vehicle_paths(engine, state, unit)
        path = found.path.get(target)
        if path is None or unit.hex is None:
            return None
        steps: list[Step] = []
        if found.pivot[target]:
            steps.append(Step("vehicle_pivot", (unit.id,), None, r28_vehicles.facing_towards(unit.hex, path[0])))
        here = unit.hex
        for index, hex_ref in enumerate(path):
            # Rule 30.5: the vehicle faces its next hex, and at the end its way of travel.
            if index + 1 < len(path):
                facing = r28_vehicles.facing_towards(hex_ref, path[index + 1])
            else:
                facing = geometry.direction_to(here, hex_ref)
            steps.append(Step("vehicle_move", (unit.id,), hex_ref, facing))
            here = hex_ref
        return steps
    ids, _left, paths = move_paths(engine, state, unit)
    path = paths.get(target)
    if ids is None or path is None:
        return None
    action = "move" if len(ids) == 1 else "stack_move"
    return [Step(action, tuple(ids), hex_ref) for hex_ref in path]


def route_step(engine: Engine, state: State, step: Step) -> Any:
    """The current frame and its legal entry that plays this step, or None for the entry.
    The route of `move_to` plays only commands of the legal list."""
    frame = engine.legal_commands(state)
    for legal in frame.commands:
        command = legal.command
        if command.action != step.action or tuple(command.units) != step.units or command.hex != step.hex:
            continue
        if step.facing is not None and dict(command.extra).get("facing") != step.facing:
            continue
        return frame, legal
    return frame, None


# ---------------------------------------------------------------------------- fire


def fire_options(engine: Engine, state: State, unit: Unit, strict_los: bool) -> dict[str, Any]:
    """The hexes in range of the unit and its weapons with a clear line of sight."""
    out: dict[str, Any] = {"kind": KIND_FIRE, "rule_id": "9.1", "normal": [], "long": [], "strict": strict_los, "note": ""}
    if unit.hex is None or unit.carrier is not None:
        return out
    rule = fire_rule(state.phase)
    types = engine.types
    ranges = []
    if r08_fire.can_fire_inherent(state, types, unit, rule):
        ranges.append(types[unit.type_key].range)
    for weapon in state.carried_by(unit.id):
        if r08_fire.can_fire_weapon(state, types, unit, weapon, rule) and types[weapon.type_key].range > 0:
            ranges.append(types[weapon.type_key].range)
    ranges = [r for r in ranges if r > 0]
    if not ranges:
        if unit.kind == KIND_LEADER and types[unit.type_key].firepower <= 0:
            out["note"] = f"The {type_name(unit)} has no firepower. It directs the fire of the units in its hex (rule 15.2)."
        else:
            out["note"] = f"The {type_name(unit)} cannot fire in this phase."
        return out
    if strict_los:
        return out
    normal_reach = max(ranges)
    long_reach = 2 * normal_reach
    here = unit.hex
    normal: list[str] = []
    long: list[str] = []
    for h in engine.board:
        ref = h.ref
        if ref == here:
            continue
        distance = geometry.distance(here, ref)
        if distance > long_reach:
            continue
        if not evaluate_los(engine.board, engine.los, here, ref).clear:
            continue
        (normal if distance <= normal_reach else long).append(geometry.hex_id(*ref))
    out["normal"] = sorted(normal)
    out["long"] = sorted(long)
    return out
