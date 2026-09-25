"""Rule 32, an armoured fighting vehicle as cover.

Three things happen when a vehicle stands between a firer and its target, or in the hex
that is fired on.

Rule 32.3 makes the outline of the vehicle a stone wall on the far hexside of its hex. A
firer in an adjacent hex is not affected. A firer further away adds the wall modifier when
it fires into the hex just behind the vehicle, and it cannot see past that.

Rule 32.5 gives the infantry on foot in the vehicle's hex a plus one, because the hull is
cover. Rule 32.1 gives the passengers on top of the counter a plus two when the fire comes
across the covered arc at the same height or lower, and nothing when it comes from the
side, the rear, or above.

Rule 32.2 and rule 32.7 take away the minus two for a target moving in the open when a
vehicle is the cover.
"""

from __future__ import annotations

from typing import Mapping

from slcore.game import PHASE_DEFENSIVE_FIRE, State
from slcore.geometry import HexRef
from slcore.los_cache import LosTable
from slcore.rules import r28_vehicles
from slcore.state import Board
from slcore.units import Unit, UnitType

RULE_32_1 = "32.1"
RULE_32_2 = "32.2"
RULE_32_3 = "32.3"
RULE_32_5 = "32.5"
RULE_32_6 = "32.6"
RULE_32_7 = "32.7"

# Rule 32.3 and rule 11.51: a vehicle outline is a stone wall, which is a plus two.
WALL_MODIFIER = 2
# Rule 32.5: the hull of the vehicle over the heads of the infantry on foot.
BENEATH_MODIFIER = 1
# Rule 32.1: fire that comes across the covered arc at the same height or lower.
PASSENGER_MODIFIER = 2

CLEAR = "clear"
BLOCKED = "blocked"


def blocks_this_phase(state: State, vehicle: Unit, phase: str) -> bool:
    """Rule 32.6: a vehicle that moved is no obstacle in the Defensive Fire Phase."""
    if phase == PHASE_DEFENSIVE_FIRE and vehicle.moved:
        return False
    return True


def obstacle_hexes(state: State, phase: str) -> frozenset[HexRef]:
    """Every hex whose vehicle or wreck counts as an obstacle in this phase.

    Rule 40.5 gives a wreck the same effect as a working vehicle. Rule 32.6 takes the
    effect away from a vehicle that moved, for the Defensive Fire Phase that follows.
    """
    out: set[HexRef] = set()
    for unit in state.units:
        if not unit.is_vehicle or unit.eliminated or unit.hex is None:
            continue
        if unit.hidden:
            # Rule 42.1 and PR-49: a hidden vehicle is on the owner's record and not on the
            # board, so it is no obstacle, and the line of sight of the other side does
            # not tell where it is.
            continue
        if not unit.wreck and not blocks_this_phase(state, unit, phase):
            continue
        out.add(unit.hex)
    return frozenset(out)


def vehicle_block(
    board: Board, vehicle_hexes: frozenset[HexRef], firer: HexRef, traced: tuple[HexRef, ...], target: HexRef
) -> tuple[bool, int]:
    """Rule 32.3: does the line of sight stop at a vehicle, and what does it add.

    `traced` is the hexes between the firer and the target, in order. A vehicle is a stone
    wall on the far hexside of its own hex, so a shot that ends in the hex right behind it
    takes the wall modifier and a shot that goes further is blocked. A vehicle in a hex
    next to the firer has no effect at all.

    Each vehicle on the line is a wall of its own. So the line is blocked when any one of
    them is more than one hex in front of the target, whatever the other vehicles do.
    """
    if not vehicle_hexes:
        return False, 0
    modifier = 0
    for ref in traced:
        if ref not in vehicle_hexes or board.adjacent(firer, ref):
            continue
        if not board.adjacent(ref, target):
            return True, 0
        modifier = WALL_MODIFIER
    return False, modifier


def hull_down_behind_wreck(
    board: Board, state: State, traced: tuple[HexRef, ...], firer: HexRef, target: HexRef
) -> bool:
    """Rule 40.6 and PR-23: a vehicle behind a wreck is hull down to the firer."""
    for ref in traced:
        if any(u.is_vehicle and u.wreck for u in state.units_in(ref)):
            return True
    return False


def passengers_only(state: State, hex_ref: HexRef) -> bool:
    """PR-27: every infantry unit in the hex is riding, so rule 32.1 gives the modifier."""
    infantry = [u for u in state.units_in(hex_ref) if u.is_infantry]
    return bool(infantry) and all(u.riding for u in infantry)


def anyone_beneath(state: State, hex_ref: HexRef) -> bool:
    """Rule 32.5: infantry on foot in a hex that holds a working vehicle."""
    vehicle = r28_vehicles.vehicle_in(state, hex_ref)
    if vehicle is None:
        return False
    return any(u.is_infantry and not u.riding for u in state.units_in(hex_ref))


def target_modifier(
    board: Board, state: State, types: Mapping[str, UnitType], firer: HexRef, target: HexRef
) -> tuple[int, str]:
    """Rules 32.1 and 32.5: what the vehicle in the target hex adds, and the rule that says so."""
    vehicle = r28_vehicles.vehicle_in(state, target)
    if vehicle is None or vehicle.hidden:
        return 0, ""
    if passengers_only(state, target):
        if not r28_vehicles.in_covered_arc(target, vehicle.facing, firer):
            return 0, RULE_32_1
        if board.hex(firer).elevation > board.hex(target).elevation:
            return 0, RULE_32_1
        return PASSENGER_MODIFIER, RULE_32_1
    if anyone_beneath(state, target):
        return BENEATH_MODIFIER, RULE_32_5
    return 0, ""


def fire_modifier(
    board: Board,
    los: "LosTable",
    types: Mapping[str, UnitType],
    state: State,
    group: "object",
    phase: str,
) -> tuple[int, list[dict]]:
    """Everything rule 32 adds to the effect roll of one fire group.

    The vehicle in the target hex gives rule 32.1 or rule 32.5. A vehicle on the line of
    sight gives the wall modifier of rule 32.3. The group takes the wall modifier one time,
    in the same way rule 11.53 takes the hexside modifier one time.
    """
    members = getattr(group, "members", ())
    target = getattr(group, "target", None)
    if target is None or not members:
        return 0, []
    if not any(u.is_vehicle for u in state.units if not u.eliminated):
        return 0, []
    total = 0
    parts: list[dict] = []
    firers = [state.units[uid].hex for uid, _ in members]
    value, rule = 0, ""
    for firer in firers:
        if firer is None:
            continue
        here, this_rule = target_modifier(board, state, types, firer, target)
        if here > value:
            value, rule = here, this_rule
    if value:
        total += value
        parts.append({"rule": rule, "value": value, "cause": "the vehicle in the target hex"})
    # A local import: `los_eval` reads `vehicle_block` from this module for rule 32.3, so a
    # module level import here would be a cycle.
    from slcore.los_eval import thread_hexes

    obstacles = obstacle_hexes(state, phase)
    wall = 0
    for firer in firers:
        if firer is None or firer == target:
            continue
        traced = thread_hexes(los, firer, target)
        _, here = vehicle_block(board, obstacles, firer, traced, target)
        wall = max(wall, here)
    if wall:
        total += wall
        parts.append({"rule": RULE_32_3, "value": wall, "cause": "a vehicle on the line of sight"})
    return total, parts


def group_cancels_open_ground(board: Board, los: "LosTable", state: State, group: "object", phase: str) -> bool:
    """Rules 32.2 and 32.7 for a whole fire group."""
    target = getattr(group, "target", None)
    members = getattr(group, "members", ())
    if target is None or not members:
        return False
    if not any(u.is_vehicle for u in state.units if not u.eliminated):
        return False
    if passengers_only(state, target):
        return True
    from slcore.los_eval import thread_hexes

    for uid, _ in members:
        firer = state.units[uid].hex
        if firer is None or firer == target:
            continue
        traced = thread_hexes(los, firer, target)
        if any(u.is_vehicle and not u.hidden for ref in traced for u in state.units_in(ref)):
            return True
    return False


def morale_check_after_loss(state: State, vehicle_id: int) -> list[int]:
    """Rule 32.5: the units on foot beneath a vehicle take a morale check when it dies."""
    vehicle = state.units[vehicle_id]
    if vehicle.hex is None:
        return []
    return sorted(
        u.id
        for u in state.units_in(vehicle.hex)
        if u.is_infantry and not u.riding and not u.broken
    )


# Rule 32.5 says the infantry below a vehicle counter is untouched by an anti-tank
# attack, and it names the flamethrower and the demolition charge as the two exceptions.
# `r37_at_weapons` holds that rule by construction: an anti-tank shot reads the kill table
# against the vehicle, and only the flamethrower reads the Infantry Fire Table again.
