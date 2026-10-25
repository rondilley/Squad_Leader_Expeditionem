"""The route action of the learned agent and the no-return filter of the Movement Phase.

The design is `docs/reports/2026-10-20_attack_movement_design.md`. The examination of
2026-10-20 played the L02 clone of the evolved v7 as the attacker: it won 0 of 50 games
against v7, and the teacher won 4 of 12. Two faults were in the Movement Phase.

A move of the core is one hex. A route of four hexes was four decisions of the net, and at
each one the net had to select the same unit and the correct next hex, with no memory of
the route it started. Its squads stopped 12 hexes from the objective, where the teacher's
came to 3. So the net selects a destination for a unit or a stack (`route`, `stack_route`),
and the agent plays the hex steps through the core. Each step is a legal command of the
frame, so the core keeps each rule, the command log holds the single steps, and a replay
gives the same hash sequence.

The net also moved one unit back and forth between two hexes until the unit had no
movement factor left. The repeat guards did not find it, because `mf_used` is a part of the
position key. So a move into a hex that its unit held in the phase is a return. The agent
plays a return last, and the environment leaves it out of the choices unless nothing else
is legal (`without_returns`).

The paths read the movement costs of the core (`r05_movement.entry_cost_halves`), as the
scripted v7 does in `_reach`. A path does not enter a hex with an enemy unit or counter that
the moving player sees (`r05_movement.enemy_in_hex`, rules 5.7, 25.2, and 42.1).

A snapshot keeps the count of its actions. A net from before the routes has fewer actions
than `stack_route` needs, so `uses_routes` is false for it and it plays the commands of the
core as before.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass
from typing import Any, Mapping

from slcore.engine import Engine
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import PHASE_MOVEMENT, State
from slcore.geometry import HexRef
from slcore.rules import r05_movement
from slcore.units import KIND_LEADER

ROUTE = "route"
STACK_ROUTE = "stack_route"
ROUTE_ACTIONS = frozenset({ROUTE, STACK_ROUTE})
MOVE_ACTIONS = frozenset({"move", "stack_move"})
# The step of the core that each route plays.
STEP_OF = {ROUTE: "move", STACK_ROUTE: "stack_move"}

Key = tuple[int, int, int, int]


@dataclass(frozen=True)
class Route:
    """One route: the core step it plays, the units of that step, and the hexes it enters.

    `units` is the unit tuple of each step command: the one unit of a `move`, or the sorted
    ids of the leader and its squads of a `stack_move`. The last hex of `path` is the
    destination.
    """

    action: str
    units: tuple[int, ...]
    lead: int
    start: HexRef
    path: tuple[HexRef, ...]

    @property
    def step(self) -> str:
        return STEP_OF[self.action]

    @property
    def destination(self) -> HexRef:
        return self.path[-1]


def uses_routes(spaces: Any) -> bool:
    """Whether a net of these spaces has the route actions."""
    from slagents.learned.encoding import ACTION_INDEX

    return int(spaces.actions) > ACTION_INDEX[STACK_ROUTE]


class PhaseMemory:
    """The hexes that each unit of the acting side held in the current phase.

    The core keeps the hexes a unit entered in the phase (`Unit.track`), and not the hex it
    started in, so the memory adds the hex of each unit the first time it sees the unit in
    the phase.
    """

    def __init__(self) -> None:
        self.phase: tuple[int, str, int] | None = None
        self.held: dict[int, set[HexRef]] = {}

    def clear(self) -> None:
        self.phase = None
        self.held = {}

    def update(self, state: State, player: int) -> None:
        phase = (state.turn, state.phase, player)
        if phase != self.phase:
            self.phase = phase
            self.held = {}
        for u in state.player_units(player):
            if u.hex is None:
                continue
            held = self.held.setdefault(u.id, set())
            held.add(u.hex)
            held.update(u.track)

    def returns(self, command: Any) -> bool:
        """Whether this command moves a unit into a hex that the unit held in the phase."""
        if command.action not in MOVE_ACTIONS or command.hex is None:
            return False
        return any(command.hex in self.held.get(u, ()) for u in command.units)


def without_returns(groups: Mapping[Key, LegalCommand], memory: PhaseMemory) -> dict[Key, LegalCommand]:
    """`groups` with no return, or all of it when only returns are legal."""
    kept = {key: legal for key, legal in groups.items() if not memory.returns(legal.command)}
    return kept if kept else dict(groups)


def reach(engine: Engine, state: State, player: int, start: HexRef, budget: int) -> dict[HexRef, tuple[HexRef, ...]]:
    """The cheapest path to each hex a unit in `start` enters with `budget` movement halves.

    A tie of cost goes to the path that the heap gives first, by the lowest hex reference, so
    the paths are the same in each run. The start hex is not a key.
    """
    ctx = engine.move_ctx
    board = engine.board
    best: dict[HexRef, int] = {start: 0}
    previous: dict[HexRef, HexRef] = {}
    heap: list[tuple[int, HexRef]] = [(0, start)]
    while heap:
        spent, here = heapq.heappop(heap)
        if spent > best[here]:
            continue
        for nxt in board.neighbors(here):
            if r05_movement.enemy_in_hex(state, player, nxt):
                continue
            cost, _ = r05_movement.entry_cost_halves(ctx, here, nxt)
            if cost is None or spent + cost > budget:
                continue
            if spent + cost < best.get(nxt, budget + 1):
                best[nxt] = spent + cost
                previous[nxt] = here
                heapq.heappush(heap, (spent + cost, nxt))
    paths: dict[HexRef, tuple[HexRef, ...]] = {}
    for dest in best:
        if dest == start:
            continue
        path = [dest]
        while path[-1] in previous and previous[path[-1]] != start:
            path.append(previous[path[-1]])
        paths[dest] = tuple(reversed(path))
    return paths


def stack_option(state: State, leader_id: int, units: tuple[int, ...]) -> int | None:
    """The option of a stack: the bit mask of its squads in the sorted squads beside the leader.

    The squads beside the leader are the other infantry of its side in its hex, sorted by
    unit id, so the same stack has the same option in each position. A mask above the option
    head has no option.
    """
    from slagents.learned.encoding import MAX_OPTIONS

    leader = state.unit(leader_id)
    beside = sorted(
        u.id for u in state.units_in(leader.hex) if u.player == leader.player and u.is_infantry and u.kind != KIND_LEADER
    )
    mask = 0
    for uid in units:
        if uid == leader_id:
            continue
        if uid not in beside:
            return None
        mask |= 1 << beside.index(uid)
    return mask if 0 < mask < MAX_OPTIONS else None


def route_table(
    engine: Engine, state: State, frame: DecisionFrame, hexes: Mapping[HexRef, int], memory: PhaseMemory
) -> dict[Key, tuple[Route, LegalCommand]]:
    """The routes of the frame, by key, each with the legal command of its first step.

    A route is in the table only when its first step is a legal command of the frame, so a
    route always starts. A destination that its unit held in the phase is a return and is
    not in the table.
    """
    from slagents.learned.encoding import ACTION_INDEX

    if frame.phase != PHASE_MOVEMENT:
        return {}
    steps: dict[tuple[str, tuple[int, ...], HexRef], LegalCommand] = {}
    for legal in frame.commands:
        c = legal.command
        if c.action in MOVE_ACTIONS and c.hex is not None:
            steps[(c.action, tuple(c.units), c.hex)] = legal
    if not steps:
        return {}
    ctx = engine.move_ctx
    player = frame.player
    table: dict[Key, tuple[Route, LegalCommand]] = {}
    groups = sorted({(a, units) for a, units, _ in steps})
    for action, units in groups:
        if action == "move":
            unit = state.unit(units[0])
            budget = r05_movement.allowance_halves(ctx, state, unit, leader_bonus=False) - unit.mf_used
            kind, lead, option = ROUTE, unit.id, 0
        else:
            members = [state.unit(i) for i in units]
            leader = next(u for u in members if u.kind == KIND_LEADER)
            budget = min(
                r05_movement.allowance_halves(ctx, state, u, leader_bonus=u.kind != KIND_LEADER) - u.mf_used for u in members
            )
            found = stack_option(state, leader.id, units)
            if found is None:
                continue
            kind, lead, option = STACK_ROUTE, leader.id, found
        start = state.unit(lead).hex
        if start is None or budget <= 0:
            continue
        held = set().union(*(memory.held.get(u, set()) for u in units))
        for dest, path in reach(engine, state, player, start, budget).items():
            if dest in held:
                continue
            first = steps.get((action, units, path[0]))
            if first is None:
                continue
            key = (lead + 1, ACTION_INDEX[kind], hexes[dest], option)
            table[key] = (Route(kind, units, lead, start, path), first)
    return table


def with_routes(groups: Mapping[Key, LegalCommand], table: Mapping[Key, tuple[Route, LegalCommand]]) -> dict[Key, LegalCommand]:
    """`groups` with the routes in place of the single steps that they replace.

    A `move` of a unit with a route, and a `stack_move` of a stack with a route, leave the
    choices. Each route key gives the command of its first step.
    """
    if not table:
        return dict(groups)
    covered = {(route.step, route.units) for route, _ in table.values()}
    out = {key: legal for key, legal in groups.items() if (legal.command.action, tuple(legal.command.units)) not in covered}
    for key, (_, first) in table.items():
        out[key] = first
    return out


def route_key(table: Mapping[Key, tuple[Route, LegalCommand]], command: Any, path: list[HexRef]) -> Key | None:
    """The key of the route of this step command to the last hex of `path` that has one.

    `command` is the first step of a run of moves and `path` is the hexes of the run, so the
    label of a teacher's run is the route to where the run ended.
    """
    by_end = {
        (route.step, route.units, route.destination): key for key, (route, _) in table.items()
    }
    units = tuple(command.units)
    for dest in reversed(path):
        key = by_end.get((command.action, units, dest))
        if key is not None:
            return key
    return None


def next_step(route: Route, done: int, state: State, frame: DecisionFrame) -> LegalCommand | None:
    """The legal command of the next step of a route after `done` steps, or None at its end.

    The route ends at its destination, when its unit is not where the route left it, and
    when the frame does not offer the next step: a broken unit, a new enemy in view, or a
    stack over the limit of rule 6.1.
    """
    if done >= len(route.path) or frame.phase != PHASE_MOVEMENT:
        return None
    here = state.unit(route.lead).hex
    if here != (route.path[done - 1] if done else route.start):
        return None
    target = route.path[done]
    for legal in frame.commands:
        c = legal.command
        if c.action == route.step and tuple(c.units) == route.units and c.hex == target:
            return legal
    return None
