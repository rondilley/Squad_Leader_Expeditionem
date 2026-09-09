"""Rule 6, stacking: 4 infantry units for each player in a hex, 3 of them squads, and
10 portage points.

Rule 6.1 gives the limit to each player ("each player may stack no more than 4 of his
infantry units"), and rule 6.2 lets the two sides occupy one hex in close combat, each
up to its own limit. So the load is counted for one player at a time.
"""

from __future__ import annotations

from typing import Mapping

from slcore.game import State
from slcore.geometry import HexRef
from slcore.units import KIND_CREW, KIND_SQUAD, KIND_SW, KIND_VEHICLE, Unit, UnitType

RULE_6_1 = "6.1"
RULE_6_2 = "6.2"
RULE_6_3 = "6.3"

LIMIT_INFANTRY = 4
LIMIT_SQUADS = 3
LIMIT_PORTAGE = 10
# Rule 29.1: one vehicle of any type in a hex. A wreck does not count (rule 40.2).
LIMIT_VEHICLES = 1


def hex_load(
    state: State,
    types: Mapping[str, UnitType],
    hex_ref: HexRef,
    player: int,
    extra_ids: tuple[int, ...] = (),
    without_ids: tuple[int, ...] = (),
) -> tuple[int, int, int]:
    """Infantry count, squad count, and portage points of one player in a hex.

    extra_ids are units counted as if they were in the hex, without_ids as if they had
    left it. A weapon counts with the unit that carries it.
    """
    counted: list[Unit] = []
    seen: set[int] = set()
    for u in state.units_in(hex_ref):
        if u.player != player or u.id in without_ids:
            continue
        counted.append(u)
        seen.add(u.id)
    for uid in extra_ids:
        if uid in seen:
            continue
        u = state.units[uid]
        if u.eliminated or u.player != player or uid in without_ids:
            continue
        counted.append(u)
        seen.add(uid)
    infantry = 0
    squads = 0
    portage = 0
    for u in counted:
        kind = u.kind
        if kind == KIND_SW:
            portage += types[u.type_key].portage_squad_halves
            continue
        if kind == KIND_VEHICLE:
            # Rule 29.1 gives a vehicle its own limit, and rule 29.2 gives the infantry
            # beneath it a smaller one. Neither is the infantry limit of rule 6.1.
            continue
        infantry += 1
        if kind == KIND_SQUAD or kind == KIND_CREW:
            squads += 1
        for w in state.carried_by(u.id):
            if w.kind == KIND_SW:
                portage += types[w.type_key].portage_squad_halves
    # Rule 6.1 states the limit in whole portage points, so the count comes back in whole
    # points. Rule 37.35 gives the panzerfaust half a point, and a half point of load is
    # still load, so the sum rounds up.
    return infantry, squads, -(-portage // 2)


def over_limit(load: tuple[int, int, int]) -> bool:
    infantry, squads, portage = load
    return infantry > LIMIT_INFANTRY or squads > LIMIT_SQUADS or portage > LIMIT_PORTAGE


def beneath_a_vehicle_overstacked(
    state: State,
    types: Mapping[str, UnitType],
    hex_ref: HexRef,
    player: int,
    extra_ids: tuple[int, ...] = (),
    without_ids: tuple[int, ...] = (),
) -> bool:
    """Rule 29.2: three infantry units below a vehicle counter, two of them squads.

    The limit is tighter than the four of rule 6.1, and it holds only while a working
    vehicle stands in the hex. Rule 40.2 says a wreck is not a vehicle for this.
    """
    from slcore.rules import r28_vehicles

    if r28_vehicles.vehicle_in(state, hex_ref) is None:
        return False
    infantry = 0
    squads = 0
    portage = 0
    seen: set[int] = set()
    for u in list(state.units_in(hex_ref)) + [state.units[i] for i in extra_ids]:
        if u.id in seen or u.id in without_ids or u.player != player or u.eliminated:
            continue
        seen.add(u.id)
        if u.kind == KIND_SW:
            portage += types[u.type_key].portage_squad_halves
            continue
        if u.kind == KIND_VEHICLE or u.riding:
            # Rule 31.2: a passenger is on the counter and not below it.
            continue
        infantry += 1
        if u.kind == KIND_SQUAD or u.kind == KIND_CREW:
            squads += 1
        for w in state.carried_by(u.id):
            if w.kind == KIND_SW:
                portage += types[w.type_key].portage_squad_halves
    return (
        infantry > r28_vehicles.BENEATH_INFANTRY
        or squads > r28_vehicles.BENEATH_SQUADS
        or portage > r28_vehicles.BENEATH_PORTAGE * 2
    )


def rule_6_1_overstacked(
    state: State,
    types: Mapping[str, UnitType],
    hex_ref: HexRef,
    player: int,
    extra_ids: tuple[int, ...] = (),
    without_ids: tuple[int, ...] = (),
) -> bool:
    """Whether this hex holds more of the player than the rules let it hold.

    Rule 6.1 gives the limit. Rule 29.2 gives a tighter one below a vehicle counter, and
    that one holds only while a working vehicle stands there.
    """
    if over_limit(hex_load(state, types, hex_ref, player, extra_ids, without_ids)):
        return True
    return beneath_a_vehicle_overstacked(state, types, hex_ref, player, extra_ids, without_ids)


def overstacked_hexes(state: State, types: Mapping[str, UnitType], player: int) -> tuple[HexRef, ...]:
    """The hexes where the player is over a limit of rule 6.1."""
    hexes = sorted({u.hex for u in state.units if u.hex is not None and u.carrier is None and not u.eliminated and u.player == player})
    return tuple(h for h in hexes if rule_6_1_overstacked(state, types, h, player))
