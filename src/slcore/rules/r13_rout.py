"""Rule 13, broken units and rout."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from slcore import actions, geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import State
from slcore.geometry import HexRef
from slcore.los_cache import LosTable
from slcore.los_eval import evaluate
from slcore.paths import nearest_goals, route, shortest_paths
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
RULE_42_5 = "42.5"

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


def known(state: State, other: Unit) -> bool:
    """QA-13.41 and PR-31: an enemy unit is a known enemy position for rule 13.

    A hidden unit (rule 42.1) and a unit below a concealment counter are not, so the
    rout of a broken unit does not change with what is below a counter.
    """
    return not other.hidden and not state.concealed(other)


def adjacent_enemy(state: State, unit: Unit) -> bool:
    if unit.hex is None:
        return False
    return _enemy_next_to(state, unit.hex, unit.player)


def _enemy_next_to(state: State, hex_ref: HexRef, player: int) -> bool:
    for n in geometry.neighbors(*hex_ref):
        for other in state.infantry_in(n):
            # Rule 13.2: an enemy unit next to it, even a broken one.
            if other.player != player and known(state, other):
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
        if not known(state, other):
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
    distance = geometry.distance
    # The distance from the start to each known enemy does not change during the search,
    # and each test of a hex that does not name the hex it comes from is the same for each
    # entry into that hex. So the two are calculated one time (NFR-01).
    near = [(enemy.hex, distance(start, enemy.hex)) for enemy in enemies if enemy.hex is not None]
    closed: dict[HexRef, bool] = {}
    exposed: dict[HexRef, bool] = {}

    def is_closed(nxt: HexRef) -> bool:
        # Rule 5.6 and PR-31: no entry into a hex with an enemy the player sees or an enemy
        # concealment counter. A hidden unit does not close the hex here, and the rout
        # stops before it when it is reached (PR-32).
        if state.enemy_counter_in(nxt, unit.player):
            return True
        for u in state.infantry_in(nxt):
            if u.player != unit.player and not u.hidden:
                return True
        for enemy_hex, from_start in near:
            if distance(nxt, enemy_hex) < from_start:
                return True
        return False

    def allowed(prev: HexRef, nxt: HexRef) -> bool:
        found = closed.get(nxt)
        if found is None:
            found = closed[nxt] = is_closed(nxt)
        if found:
            return False
        if r11_terrain.is_open_ground(board, nxt) and not behind_cover_hexside(board, prev, nxt):
            seen = exposed.get(nxt)
            if seen is None:
                seen = exposed[nxt] = any(in_range_and_los(ctx, types, enemy, nxt) for enemy in enemies)
            if seen:
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
    return list(_rout_search(ctx, types, state, unit)[0])


# The rout searches of one state, by unit ID. It is not a field of the record, so it is
# not in the state document, the equality, or a copy made with `with_`.
ROUT_MEMO_ATTRIBUTE = "_rout_memo"


def _rout_search(
    ctx: RoutContext, types: Mapping[str, UnitType], state: State, unit: Unit
) -> tuple[tuple[HexRef, ...], dict[HexRef, HexRef]]:
    """The rout destinations of rule 13.43 and the predecessors of the routes to them.

    The legal list, the test of rule 13.47, and `apply_rout` each ask for the same unit
    in the same state, so the answer is kept on the state (NFR-01). It is kept only for a
    unit that is the unit of the state with that ID, because an agent can ask about a
    unit it changed.
    """
    if unit.hex is None:
        return (), {}
    memo = state.__dict__.get(ROUT_MEMO_ATTRIBUTE)
    keep = state.units[unit.id] is unit
    if keep and memo is not None:
        found = memo.get(unit.id)
        if found is not None and found[0] is ctx and found[1] is types:
            return found[2], found[3]
    enemies = known_enemies(ctx, state, unit)
    allowed = rout_step_allowed(ctx, types, state, unit, enemies)
    board = ctx.move.board

    def is_destination(ref: HexRef) -> bool:
        return (
            is_cover(board, ref)
            and not r06_stacking.rule_6_1_overstacked(state, types, ref, unit.player, extra_ids=(unit.id,))
            and not _enemy_next_to(state, ref, unit.player)
        )

    _, goals, pred = nearest_goals(ctx.move, unit.hex, allowed, is_destination)
    options = tuple(goals)
    if keep:
        if memo is None:
            memo = {}
            state.__dict__[ROUT_MEMO_ATTRIBUTE] = memo
        memo[unit.id] = (ctx, types, options, pred)
    return options, pred


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
    options, pred = _rout_search(ctx, types, state, unit)
    if dest not in options:
        # A hex that is not a rout destination: the full search says whether a route goes
        # there at all, as it did before the search stopped at the nearest cover.
        enemies = known_enemies(ctx, state, unit)
        allowed = rout_step_allowed(ctx, types, state, unit, enemies)
        _, pred = shortest_paths(ctx.move, unit.hex, allowed)
    if dest not in pred:
        raise ValueError("the rout destination is not reachable by a legal route")
    path = route(pred, unit.hex, dest)
    allowance = rout_allowance(state, types, unit)
    spent = 0
    here = unit.hex
    blocked: HexRef | None = None
    for step in path:
        cost, _ = entry_cost_halves(ctx.move, here, step)
        if cost is None or spent + cost > allowance:
            break
        if any(u.hidden and u.player != unit.player for u in state.units_in(step)):
            # PR-32: the rout meets a hidden unit and stops in the hex before it.
            blocked = step
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
    if blocked is not None:
        events.append(
            Event(RULE_42_5, "stopped", {"unit": unit.id, "hex": geometry.hex_id(*here), "tried": geometry.hex_id(*blocked)})
        )
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


# ------------------------------------------------------------------ the command handlers (M3)
# A rout is a move for rules 25.4 and 42.2. A stay is not.


@actions.action("rout", unconceals=actions.CAUSE_MOVED)
def _on_rout(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    return apply_rout(engine.rout_ctx, engine.types, state, command)


@actions.action("stay")
def _on_stay(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    return apply_stay(state, command)
