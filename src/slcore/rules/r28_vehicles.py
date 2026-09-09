"""Rule 28, armoured fighting vehicles, and rule 29, vehicle stacking and placement.

A vehicle counter carries its movement points, its main gun calibre, and its two machine
gun factors (rule 28). It also carries a facing, because rule 29.4 builds the covered arc
from the spine the gun barrel points at. Project ruling PR-21 puts the facing in the
command payload, so a replay reproduces it.

The geometry here is exact integer work on the lattice of `slcore.geometry` (NFR-05).
"""

from __future__ import annotations

from typing import Mapping

from slcore import geometry
from slcore.game import State
from slcore.geometry import HexRef
from slcore.state import Board
from slcore.units import (
    CLASS_JEEP,
    CLASS_TRUCK,
    KIND_SW,
    THIS_TIER_CLASSES,
    Unit,
    UnitType,
)

RULE_28 = "28"
RULE_28_1 = "28.1"
RULE_28_2 = "28.2"
RULE_28_4 = "28.4"
RULE_29_1 = "29.1"
RULE_29_2 = "29.2"
RULE_29_3 = "29.3"
RULE_29_4 = "29.4"
RULE_33_5 = "33.5"

# Rule 29.2: three infantry units, of which two may be squads, and five portage points of
# support weapons may stack beneath a vehicle.
BENEATH_INFANTRY = 3
BENEATH_SQUADS = 2
BENEATH_PORTAGE = 5

FRONT = "afv_front"
SIDE = "afv_side"
REAR = "afv_rear"
TRUCK_OR_JEEP = "truck_or_jeep"

# Rule 33.5: the harder facing wins when the line of sight runs along a spine.
FACING_ORDER = (FRONT, SIDE, REAR)


class VehicleNotAvailable(Exception):
    """A scenario asks for a vehicle whose rules are not in this tier (PR-20)."""

    def __init__(self, type_key: str, vehicle_class: str) -> None:
        super().__init__(
            f"the counter {type_key} is a {vehicle_class}, and rules 47 and 51 hold its rules. "
            "This tier plays rules 28 to 41, which cover tanks and self-propelled guns."
        )
        self.type_key = type_key
        self.vehicle_class = vehicle_class
        self.rule_id = "28"


def check_class(type_key: str, unit_type: UnitType) -> None:
    """PR-20: refuse a halftrack, a truck, or a jeep until rules 47 and 51 are written."""
    if not unit_type.is_vehicle:
        return
    if unit_type.vehicle_class not in THIS_TIER_CLASSES:
        raise VehicleNotAvailable(type_key, unit_type.vehicle_class or "vehicle")


def in_play(state: State) -> bool:
    """Whether this game has a vehicle at all. An infantry game skips every rule here."""
    return any(u.is_vehicle for u in state.units)


def vehicles(state: State, player: int | None = None) -> list[Unit]:
    return [
        u
        for u in state.units
        if u.is_vehicle and not u.eliminated and (player is None or u.player == player)
    ]


def vehicle_in(state: State, hex_ref: HexRef | None) -> Unit | None:
    """Rule 29.1: at most one working vehicle stands in a hex."""
    if hex_ref is None:
        return None
    for u in state.units_in(hex_ref):
        if u.is_vehicle and not u.wreck:
            return u
    return None


def wrecks_in(state: State, hex_ref: HexRef | None) -> list[Unit]:
    """Rule 40.2: a wreck does not count towards the vehicle stacking limit."""
    if hex_ref is None:
        return []
    return [u for u in state.units_in(hex_ref) if u.is_vehicle and u.wreck]


def passengers_of(state: State, vehicle_id: int) -> list[Unit]:
    """Rule 31.2: the units on top of the counter, which are the ones being transported."""
    return [u for u in state.units if u.passenger_of == vehicle_id and not u.eliminated]


def beneath(state: State, vehicle: Unit) -> list[Unit]:
    """Rule 29.3: the friendly infantry on foot in the same hex as the vehicle."""
    if vehicle.hex is None:
        return []
    return [
        u
        for u in state.units_in(vehicle.hex)
        if u.is_infantry and u.player == vehicle.player and not u.riding
    ]


def beneath_room(state: State, types: Mapping[str, UnitType], vehicle: Unit, extra: Unit | None = None) -> bool:
    """Rule 29.2: whether one more infantry unit fits beneath the vehicle counter."""
    units = beneath(state, vehicle)
    if extra is not None:
        units = [u for u in units if u.id != extra.id] + [extra]
    infantry = len(units)
    squads = sum(1 for u in units if types[u.type_key].is_squad_like)
    portage = 0
    for u in units:
        for w in state.carried_by(u.id):
            portage += types[w.type_key].portage_squad_halves
    if vehicle.hex is not None:
        for w in state.units_in(vehicle.hex):
            if w.kind == KIND_SW and w.carrier is None:
                portage += types[w.type_key].portage_squad_halves
    return infantry <= BENEATH_INFANTRY and squads <= BENEATH_SQUADS and portage <= BENEATH_PORTAGE * 2


# ------------------------------------------------------------------- the covered arc


def arc_directions(facing: int) -> tuple[int, int]:
    """Rule 29.4: the two hexsides that meet at the spine the gun barrel points at.

    A spine of index f lies between the hexside f+1 and the hexside f+2, because the
    vertex offsets of the lattice sit between the direction offsets in that order.
    """
    return ((facing + 1) % 6, (facing + 2) % 6)


def in_covered_arc(origin: HexRef, facing: int, target: HexRef) -> bool:
    """Rule 29.4: whether the target hex lies in the wedge between the two hexsides.

    The wedge is every hex that is a sum of the two direction vectors with counts that are
    zero or more, so the two hex rows themselves are in the arc and everything between them
    is as well. The vehicle's own hex is in its arc.
    """
    if facing < 0:
        return False
    left, right = arc_directions(facing)
    ax, ay = geometry.DIRECTIONS[left]
    bx, by = geometry.DIRECTIONS[right]
    ox, oy = geometry.center(*origin)
    tx, ty = geometry.center(*target)
    dx, dy = tx - ox, ty - oy
    det = geometry.cross(ax, ay, bx, by)
    if det == 0:
        raise ValueError("two hex directions cannot be parallel")
    a = geometry.cross(dx, dy, bx, by)
    b = geometry.cross(ax, ay, dx, dy)
    if det < 0:
        a, b, det = -a, -b, -det
    if a % det or b % det:
        return False
    return a >= 0 and b >= 0


def covered_arc_hexes(board: Board, origin: HexRef, facing: int) -> tuple[HexRef, ...]:
    """Every hex of the board in the covered arc, the vehicle's own hex first."""
    return tuple(h.ref for h in board if in_covered_arc(origin, facing, h.ref))


def facing_towards(origin: HexRef, target: HexRef) -> int:
    """The spine to face so the target is in the covered arc and as near the middle as it can be.

    A player names the facing, and a computer opponent needs one sensible answer. Every
    spine whose arc holds the target is correct; this picks the first of them in order,
    which keeps the choice the same for the same pair of hexes.
    """
    for facing in range(6):
        if in_covered_arc(origin, facing, target):
            return facing
    return 0


# -------------------------------------------------------------------- target facing


def crossed_hexsides(target: HexRef, firer: HexRef) -> tuple[int, ...]:
    """The hexside or hexsides of the target hex that the line of sight crosses.

    Two come back when the firer lies exactly along a spine of the target hex, which is
    the case rule 33.5 settles by taking the harder facing.
    """
    if target == firer:
        return ()
    tx, ty = geometry.center(*target)
    fx, fy = geometry.center(*firer)
    vx, vy = fx - tx, fy - ty
    out: list[int] = []
    for d in range(6):
        px, py = geometry.VERTEX_OFFSETS[(d + 4) % 6]
        qx, qy = geometry.VERTEX_OFFSETS[(d + 5) % 6]
        det = geometry.cross(px, py, qx, qy)
        a = geometry.cross(vx, vy, qx, qy)
        b = geometry.cross(px, py, vx, vy)
        if det < 0:
            a, b = -a, -b
        if a >= 0 and b >= 0:
            out.append(d)
    return tuple(out)


def facing_class(target_facing: int, hexside: int) -> str:
    """PR-22: front, side, or rear for one hexside of a vehicle that faces a spine."""
    left, right = arc_directions(target_facing)
    if hexside in (left, right):
        return FRONT
    if hexside in ((left + 3) % 6, (right + 3) % 6):
        return REAR
    return SIDE


def target_face(target: Unit, firer_hex: HexRef, types: Mapping[str, UnitType]) -> str:
    """Rule 33.5 with PR-22: the row of the kill table this shot reads.

    A truck and a jeep have one row of their own, so their facing does not matter.
    """
    if types[target.type_key].vehicle_class in (CLASS_TRUCK, CLASS_JEEP):
        return TRUCK_OR_JEEP
    if target.hex is None or target.hex == firer_hex:
        # Rule 33.31 case K puts the firer in the target's hex. No hexside is crossed, and
        # a shot from inside the hex reaches the least protected face.
        return REAR
    sides = crossed_hexsides(target.hex, firer_hex)
    if not sides:
        return SIDE
    classes = [facing_class(target.facing, d) for d in sides]
    for name in FACING_ORDER:
        if name in classes:
            return name
    return SIDE


def to_hit_row(board: Board, state: State, target: Unit, hull_down: bool) -> str:
    """Rule 33.3: which row of the to-hit table a vehicle target reads."""
    if hull_down:
        return "vehicle_hull_down"
    if target.hex is not None:
        kind = board.hex(target.hex).terrain
        if kind == "woods" or board.is_building_kind(kind):
            return "vehicle_in_woods_or_building"
    return "vehicle_in_other"


def infantry_to_hit_row(board: Board, hex_ref: HexRef) -> str:
    """Rule 33.3: which row of the to-hit table an infantry target reads."""
    hexagon = board.hex(hex_ref)
    if board.is_building_kind(hexagon.terrain) or hexagon.terrain == "shellhole":
        return "infantry_in_building"
    if hexagon.terrain == "woods":
        return "infantry_in_woods"
    return "infantry_in_other"



