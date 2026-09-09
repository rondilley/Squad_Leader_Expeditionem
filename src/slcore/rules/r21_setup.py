"""Rule 21.2: each side sets up in the areas the scenario gives, in the scenario's sequence."""

from __future__ import annotations

from typing import Mapping

from slcore import geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import State
from slcore.rules import r06_stacking
from slcore.rules.r05_movement import LEADER_MAX_PORTAGE
from slcore.scenario import Scenario
from slcore.state import Board
from slcore.units import KIND_LEADER, KIND_SW, Unit, UnitType

RULE_21_2 = "21.2"


def unplaced(state: State, player: int) -> list[Unit]:
    """The counters of the player still to be placed.

    A crew counter that rule 33.9 holds in reserve for a vehicle is not one of them. It
    comes on the board when its vehicle dies, and never at set up.
    """
    return [u for u in state.player_units(player) if not u.placed and u.from_wreck is None]


def _lowest_of_each_type(units: list[Unit]) -> list[Unit]:
    """PR-06: identical counters are interchangeable, so offer the lowest ID of each type in each group."""
    seen: set[tuple[str, str]] = set()
    out: list[Unit] = []
    for u in sorted(units, key=lambda x: x.id):
        key = (u.group, u.type_key)
        if key in seen:
            continue
        seen.add(key)
        out.append(u)
    return out


def legal_setup(scenario: Scenario, board: Board, types: Mapping[str, UnitType], state: State) -> list[Command]:
    """Rule 21.2 with the project ruling PR-06.

    A side arranges its counters until it declares the set up complete, so a unit that
    is already on the board may be placed again on another hex of its area. Without
    that, a placement sequence can reach a state where a unit has no legal hex and the
    side cannot go on. See the project ruling PR-11.
    """
    player = state.active
    side = scenario.players()[player]
    spec = scenario.side_spec(side)
    areas = {g.id: g.area.resolve(board) for g in spec.groups}
    this_pass = {g.id for g in spec.groups if scenario.group_pass(g.id) == state.setup_index}
    out: list[Command] = []
    pending = [u for u in unplaced(state, player) if scenario.group_pass(u.group) == state.setup_index]
    stuck = False
    for u in _lowest_of_each_type(pending):
        hexes = areas[u.group]
        legal_hexes = [h for h in hexes if not r06_stacking.rule_6_1_overstacked(state, types, h, u.player, extra_ids=(u.id,))]
        if u.kind == KIND_SW:
            for carrier in state.player_units(player):
                if carrier.group != u.group or carrier.kind == KIND_SW or carrier.hex is None:
                    continue
                if _carry_allowed(types, state, carrier, u):
                    out.append(Command("place_weapon", units=(carrier.id,), weapon=u.id))
        for h in legal_hexes:
            out.append(Command("place", units=(u.id,), hex=h))
        if not legal_hexes and u.kind != KIND_SW:
            stuck = True
    if stuck:
        out.extend(_rearrangements(state, types, {k: v for k, v in areas.items() if k in this_pass}, player))
    if not pending:
        out.append(Command("end_setup"))
    return out


def _rearrangements(state: State, types: Mapping[str, UnitType], areas: Mapping[str, tuple], player: int) -> list[Command]:
    """Move a placed unit to another hex of its own area, so that set up can go on."""
    out: list[Command] = []
    for u in sorted(state.player_units(player), key=lambda x: x.id):
        if u.hex is None or u.carrier is not None or u.kind == KIND_SW:
            continue
        for h in areas.get(u.group, ()):
            if h == u.hex:
                continue
            if r06_stacking.rule_6_1_overstacked(state, types, h, u.player, extra_ids=(u.id,)):
                continue
            out.append(Command("place", units=(u.id,), hex=h))
    return out


def _carry_allowed(types: Mapping[str, UnitType], state: State, carrier: Unit, weapon: Unit) -> bool:
    t = types[weapon.type_key]
    if carrier.kind == KIND_LEADER:
        if t.pp_leader is None:
            return False
        total = sum(types[w.type_key].pp_leader or 0 for w in state.carried_by(carrier.id)) + t.pp_leader
        if total > LEADER_MAX_PORTAGE:
            return False
    if carrier.hex is None:
        return False
    return not r06_stacking.rule_6_1_overstacked(state, types, carrier.hex, carrier.player, extra_ids=(weapon.id,))


def apply_place(state: State, command: Command) -> tuple[State, list[Event]]:
    unit = state.units[command.units[0]]
    if command.hex is None:
        raise ValueError("place needs a hex")
    placed = unit.with_(hex=command.hex, carrier=None)
    return state.with_unit(placed), [Event(RULE_21_2, "place", {"unit": unit.id, "hex": geometry.hex_id(*command.hex)})]


def apply_place_weapon(state: State, command: Command) -> tuple[State, list[Event]]:
    carrier = state.units[command.units[0]]
    weapon = state.units[command.weapon] if command.weapon is not None else None
    if weapon is None:
        raise ValueError("place_weapon needs a weapon")
    placed = weapon.with_(hex=carrier.hex, carrier=carrier.id)
    return state.with_unit(placed), [Event(RULE_21_2, "place_weapon", {"weapon": weapon.id, "carrier": carrier.id})]
