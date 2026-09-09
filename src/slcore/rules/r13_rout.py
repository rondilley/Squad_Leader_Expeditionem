"""Rule 13, broken units and rout."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from slcore import geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import State
from slcore.geometry import HexRef
from slcore.los_cache import LosTable
from slcore.los_eval import evaluate
from slcore.paths import route, shortest_paths
from slcore.rules import r06_stacking, r11_terrain
from slcore.rules.r05_movement import MoveContext, entry_cost_halves
from slcore.state import Board
from slcore.units import KIND_LEADER, Unit, UnitType

RULE_13_2 = "13.2"
RULE_13_3 = "13.3"
RULE_13_4 = "13.4"
RULE_13_41 = "13.41"
RULE_13_42 = "13.42"
RULE_13_43 = "13.43"
RULE_13_44 = "13.44"
RULE_13_46 = "13.46"
RULE_13_47 = "13.47"

COVER_KINDS = ("woods", "wooden_building", "stone_building")


@dataclass(frozen=True)
class RoutContext:
    move: MoveContext
    los: LosTable


def is_cover(board: Board, hex_ref: HexRef) -> bool:
    """Rule 13.4: cover is a building or a woods hex."""
    return board.hex(hex_ref).terrain in COVER_KINDS


def broken_units(state: State, player: int) -> list[Unit]:
    return [u for u in state.player_units(player) if u.broken and u.hex is not None and u.carrier is None]


def adjacent_enemy(state: State, unit: Unit) -> bool:
    if unit.hex is None:
        return False
    board_neighbors = geometry.neighbors(*unit.hex)
    for n in board_neighbors:
        for other in state.infantry_in(n):
            if other.player != unit.player and not other.broken:
                return True
    return False


def known_enemies(ctx: RoutContext, state: State, unit: Unit) -> list[Unit]:
    """The rulings for 13.41: an enemy unit with a line of sight to the broken unit."""
    if unit.hex is None:
        return []
    out = []
    for other in state.units:
        if other.player == unit.player or other.broken or other.eliminated or other.hex is None or not other.is_infantry:
            continue
        if evaluate(ctx.move.board, ctx.los, other.hex, unit.hex).clear:
            out.append(other)
    return out


def in_range_and_los(ctx: RoutContext, types: Mapping[str, UnitType], enemy: Unit, hex_ref: HexRef) -> bool:
    """Rule 13.42: the hex is in the line of sight and the normal range of the enemy unit."""
    if enemy.hex is None:
        return False
    if geometry.distance(enemy.hex, hex_ref) > types[enemy.type_key].range:
        return False
    return evaluate(ctx.move.board, ctx.los, enemy.hex, hex_ref).clear


def rout_step_allowed(ctx: RoutContext, types: Mapping[str, UnitType], state: State, unit: Unit, enemies: list[Unit]) -> callable:
    board = ctx.move.board
    start = unit.hex

    def allowed(prev: HexRef, nxt: HexRef) -> bool:
        for u in state.infantry_in(nxt):
            if u.player != unit.player:
                return False
        for enemy in enemies:
            if enemy.hex is None:
                continue
            if geometry.distance(nxt, enemy.hex) < geometry.distance(start, enemy.hex):
                return False
        if r11_terrain.is_open_ground(board, nxt) and not behind_cover_hexside(board, prev, nxt):
            for enemy in enemies:
                if in_range_and_los(ctx, types, enemy, nxt):
                    return False
        return True

    return allowed


def behind_cover_hexside(board: Board, prev: HexRef, nxt: HexRef) -> bool:
    """Rule 13.42: an open ground hex behind a wall or hedge is allowed."""
    d = geometry.direction_to(prev, nxt)
    if d is None:
        return False
    return board.hexside(prev, d) in ("wall", "hedge")


def rout_allowance(state: State, types: Mapping[str, UnitType], unit: Unit) -> int:
    """Rule 13.3: a broken squad with a leader in its hex has 6 movement factors."""
    halves = types[unit.type_key].mf_halves
    if unit.kind != KIND_LEADER and unit.hex is not None:
        if any(u.kind == KIND_LEADER and u.player == unit.player for u in state.infantry_in(unit.hex)):
            halves += 4
    return halves


def must_rout(ctx: RoutContext, state: State, unit: Unit) -> bool:
    """Rules 13.4 and 13.46: a broken unit in cover and not next to an enemy may stay."""
    if unit.hex is None:
        return False
    if adjacent_enemy(state, unit):
        return True
    return not is_cover(ctx.move.board, unit.hex)


def rout_options(ctx: RoutContext, types: Mapping[str, UnitType], state: State, unit: Unit) -> list[HexRef]:
    """Rule 13.43: the nearest cover hexes by movement factors along a legal route."""
    if unit.hex is None:
        return []
    enemies = known_enemies(ctx, state, unit)
    allowed = rout_step_allowed(ctx, types, state, unit, enemies)
    dist, _ = shortest_paths(ctx.move, unit.hex, allowed)
    board = ctx.move.board
    best: int | None = None
    out: list[HexRef] = []
    for ref, cost in sorted(dist.items()):
        if ref == unit.hex or not is_cover(board, ref):
            continue
        if r06_stacking.rule_6_1_overstacked(state, types, ref, unit.player, extra_ids=(unit.id,)):
            continue
        if adjacent_enemy(state, unit.with_(hex=ref)):
            continue
        if best is None or cost < best:
            best = cost
            out = [ref]
        elif cost == best:
            out.append(ref)
    return out


def legal_rout_commands(ctx: RoutContext, types: Mapping[str, UnitType], state: State, player: int) -> list[Command]:
    out: list[Command] = []
    for unit in broken_units(state, player):
        if unit.stay or unit.routed:
            # Rule 13.43: a broken unit routs with its movement allowance, one time in the
            # Rout Phase. A unit that could not reach cover stays where it stopped, and it
            # goes on in the next Rout Phase.
            continue
        if not must_rout(ctx, state, unit):
            out.append(Command("stay", units=(unit.id,)))
            continue
        for dest in rout_options(ctx, types, state, unit):
            out.append(Command("rout", units=(unit.id,), hex=dest))
    return out


def hopeless(ctx: RoutContext, types: Mapping[str, UnitType], state: State, unit: Unit) -> bool:
    """Rule 13.47: a broken unit that cannot satisfy rule 13.4 is eliminated."""
    if not must_rout(ctx, state, unit):
        return False
    return not rout_options(ctx, types, state, unit)


def eliminate_hopeless(ctx: RoutContext, types: Mapping[str, UnitType], state: State, player: int) -> tuple[State, list[Event]]:
    events: list[Event] = []
    for unit in broken_units(state, player):
        if unit.stay or unit.routed or not hopeless(ctx, types, state, state.units[unit.id]):
            continue
        state = state.with_unit(state.units[unit.id].with_(eliminated=True, hex=None, carrier=None))
        events.append(Event(RULE_13_47, "eliminated", {"unit": unit.id, "cause": "no rout route"}))
    return state, events


def apply_rout(ctx: RoutContext, types: Mapping[str, UnitType], state: State, command: Command) -> tuple[State, list[Event]]:
    """Rules 13.43 to 13.45: move along the shortest legal route, up to the movement factors."""
    unit = state.units[command.units[0]]
    dest = command.hex
    if dest is None or unit.hex is None:
        raise ValueError("rout needs a destination")
    enemies = known_enemies(ctx, state, unit)
    allowed = rout_step_allowed(ctx, types, state, unit, enemies)
    dist, pred = shortest_paths(ctx.move, unit.hex, allowed)
    if dest not in pred:
        raise ValueError("the rout destination is not reachable by a legal route")
    path = route(pred, unit.hex, dest)
    allowance = rout_allowance(state, types, unit)
    spent = 0
    here = unit.hex
    for step in path:
        cost, _ = entry_cost_halves(ctx.move, here, step)
        if cost is None or spent + cost > allowance:
            break
        spent += cost
        here = step
    reached = here == dest
    moved = state.units[unit.id].with_(
        hex=here, routed=True, stay=reached and is_cover(ctx.move.board, here)
    )
    state = state.with_unit(moved)
    events = [
        Event(
            RULE_13_43,
            "rout",
            {"unit": unit.id, "from": geometry.hex_id(*unit.hex), "to": geometry.hex_id(*here), "goal": geometry.hex_id(*dest), "reached": reached, "halves": spent},
        )
    ]
    return state, events


def apply_stay(state: State, command: Command) -> tuple[State, list[Event]]:
    unit = state.units[command.units[0]]
    return state.with_unit(unit.with_(stay=True)), [Event(RULE_13_46, "stay", {"unit": unit.id})]


def eliminate_overstacked_broken(ctx: RoutContext, types: Mapping[str, UnitType], state: State) -> tuple[State, list[Event]]:
    """The ruling for 13.44: broken units over the stacking limit at the end of the Rout Phase are eliminated."""
    events: list[Event] = []
    hexes = sorted({u.hex for u in state.units if u.hex is not None and u.carrier is None and not u.eliminated})
    for h in hexes:
        for player in (0, 1):
            while r06_stacking.rule_6_1_overstacked(state, types, h, player) and any(u.broken and u.player == player for u in state.infantry_in(h)):
                victim = sorted((u for u in state.infantry_in(h) if u.broken and u.player == player), key=lambda u: u.id)[-1]
                state = state.with_unit(victim.with_(eliminated=True, hex=None, carrier=None))
                events.append(Event(RULE_13_44, "eliminated", {"unit": victim.id, "cause": "over the stacking limit after the rout"}))
    return state, events
