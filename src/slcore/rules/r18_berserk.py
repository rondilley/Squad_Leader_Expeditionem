"""Rule 18.4, berserk units: the charge of rule 18.42 and the movement factors of 18.43.

Rule 12 makes the unit berserk (r12_morale.go_berserk). This module gives what the unit
must do after that, under project ruling PR-37:

- 18.42: in its Movement Phase and its Advance Phase the unit charges the nearest enemy
  unit in its line of sight, by the shortest route in movement factors, to destroy it in
  close combat. Rule 5.6 keeps it out of the enemy hex in the Movement Phase, so the
  Movement Phase takes it next to the hex and the Advance Phase takes it in. The Close
  Combat Phase then asks it to attack.
- 18.43: 6 movement factors for a squad, 8 for a leader, and 8 for a squad in a stack
  with a berserk leader. `r05_movement.allowance_halves` holds the numbers.

A concealment counter of the other side counts as an enemy unit for the charge, as rule
25.2 asks (PR-31), so a dummy and a real stack give the same charge. A hidden unit is not
on the board the charging player sees, so it is no target.
"""

from __future__ import annotations

import heapq
from typing import Callable

from slcore import geometry
from slcore.commands import Command
from slcore.game import State
from slcore.geometry import HexRef
from slcore.rules import r05_movement
from slcore.rules.r05_movement import (
    ADVANCE_LEADER_PORTAGE,
    ADVANCE_SQUAD_PORTAGE,
    MOVE_MODE_ADVANCED,
    MOVE_MODE_NONE,
    MOVE_MODE_STACK,
    MoveContext,
    entry_cost_halves,
    enemy_in_hex,
)
from slcore.rules import r06_stacking
from slcore.units import KIND_LEADER, KIND_SW, Unit

RULE_18_41 = "18.41"
RULE_18_42 = "18.42"
RULE_18_43 = "18.43"

Sees = Callable[[HexRef, HexRef], bool]


def enemy_hexes(state: State, player: int) -> set[HexRef]:
    """The hexes where the player sees an enemy unit or an enemy concealment counter."""
    out: set[HexRef] = set()
    for u in state.units:
        if u.player == player or u.eliminated or u.hex is None or u.carrier is not None:
            continue
        if u.kind == KIND_SW or u.hidden or u.wreck:
            continue
        if state.concealed(u):
            # The counter stands for the unit (rule 25.2). It is added below.
            continue
        out.add(u.hex)
    for counter in state.concealment:
        if counter.player != player:
            out.add(counter.hex)
    return out


def charge_targets(state: State, unit: Unit, sees: Sees) -> tuple[HexRef, ...]:
    """Rule 18.42: the enemy hexes in the unit's line of sight at the least distance in hexes."""
    if unit.hex is None:
        return ()
    best: int | None = None
    found: list[HexRef] = []
    for hex_ref in sorted(enemy_hexes(state, unit.player)):
        if hex_ref == unit.hex or not sees(unit.hex, hex_ref):
            continue
        distance = geometry.distance(unit.hex, hex_ref)
        if best is None or distance < best:
            best = distance
            found = [hex_ref]
        elif distance == best:
            found.append(hex_ref)
    return tuple(found)


def distance_to(ctx: MoveContext, state: State, player: int, targets: tuple[HexRef, ...]) -> dict[HexRef, int]:
    """The least cost in movement factors from each hex into one of the target hexes.

    One search runs backward from the targets, so each hex reads the cost of the entry it
    would pay (rule 5.5 is not the same in the two directions on a slope). A route does
    not pass through another enemy hex, and it ends at the first target it enters.
    """
    goal = set(targets)
    dist: dict[HexRef, int] = {t: 0 for t in targets}
    heap: list[tuple[int, HexRef]] = [(0, t) for t in sorted(goal)]
    while heap:
        cost, here = heapq.heappop(heap)
        if cost > dist.get(here, 1 << 30):
            continue
        for d in range(6):
            before = geometry.neighbor(*here, d)
            if before not in ctx.board or before in goal:
                continue
            if enemy_in_hex(state, player, before):
                continue
            step, _ = entry_cost_halves(ctx, before, here)
            if step is None:
                continue
            total = cost + step
            if total < dist.get(before, 1 << 30):
                dist[before] = total
                heapq.heappush(heap, (total, before))
    return dist


def route_steps(ctx: MoveContext, state: State, unit: Unit, targets: tuple[HexRef, ...]) -> tuple[HexRef, ...] | None:
    """The hexes next to the unit that begin a shortest route in movement factors to a target.

    None means no route reaches any target. A target hex next to the unit is a step when
    the direct entry is a shortest route.
    """
    if unit.hex is None or not targets:
        return None
    dist = distance_to(ctx, state, unit.player, targets)
    total = dist.get(unit.hex)
    if total is None:
        return None
    steps: list[HexRef] = []
    for d in range(6):
        nxt = geometry.neighbor(*unit.hex, d)
        if nxt not in ctx.board or nxt not in dist:
            continue
        cost, _ = entry_cost_halves(ctx, unit.hex, nxt)
        if cost is not None and cost + dist[nxt] == total:
            steps.append(nxt)
    return tuple(sorted(steps))


def _berserk_stack_squads(state: State, leader: Unit) -> list[Unit]:
    """Rule 18.43: the berserk squads that may move in a stack with this berserk leader."""
    if leader.hex is None:
        return []
    return [
        s
        for s in state.units_in(leader.hex)
        if s.player == leader.player
        and s.is_infantry
        and s.kind != KIND_LEADER
        and s.berserk
        and not s.broken
        and not s.prep_fired
        and not s.sewer_move
        and s.move_mode == MOVE_MODE_NONE
    ]


def _normal_moves(ctx: MoveContext, state: State, unit: Unit) -> list[Command]:
    """The moves the unit could make with its berserk factors and no charge to make."""
    out: list[Command] = []
    if unit.move_mode.startswith(MOVE_MODE_STACK):
        if unit.kind != KIND_LEADER:
            return out
        return r05_movement._stack_moves(ctx, state, unit, r05_movement.stack_members(state, unit))
    if unit.kind == KIND_LEADER and unit.move_mode == MOVE_MODE_NONE:
        for subset in r05_movement._subsets(_berserk_stack_squads(state, unit)):
            out.extend(r05_movement._stack_moves(ctx, state, unit, subset))
    out.extend(r05_movement._solo_moves(ctx, state, unit))
    return out


def charge_moves(ctx: MoveContext, state: State, sees: Sees) -> tuple[list[Command], list[Command]]:
    """Rule 18.42 in the Movement Phase: the moves of the berserk units of the active player.

    The first list holds the moves of a berserk unit with no charge to make, which it may
    make or not. The second holds the steps of each charge that is not complete. While it
    is not empty, the unit must take one of them and the phase may not end (PR-37).
    """
    free: list[Command] = []
    forced: list[Command] = []
    for unit in r05_movement.movers(state, state.active):
        if not unit.berserk:
            continue
        if unit.move_mode.startswith(MOVE_MODE_STACK) and unit.kind != KIND_LEADER:
            continue
        normal = _normal_moves(ctx, state, unit)
        targets = charge_targets(state, unit, sees)
        if not targets:
            free.extend(normal)
            continue
        if unit.hex is not None and any(geometry.distance(unit.hex, t) <= 1 for t in targets):
            # The unit stands next to its target, and rule 5.6 keeps it out of the hex.
            continue
        steps = route_steps(ctx, state, unit, targets)
        if steps is None:
            free.extend(normal)
            continue
        forced.extend(c for c in normal if c.hex in steps)
    return free, forced


def _advance_allowed(ctx: MoveContext, state: State, unit: Unit, dst: HexRef) -> bool:
    if dst not in ctx.board:
        return False
    cost, _ = entry_cost_halves(ctx, unit.hex, dst) if unit.hex is not None else (None, ())
    if cost is None:
        return False
    return not r06_stacking.rule_6_1_overstacked(state, ctx.types, dst, unit.player, extra_ids=(unit.id,))


def charge_advances(ctx: MoveContext, state: State, sees: Sees) -> tuple[list[Command], list[Command]]:
    """Rule 18.42 in the Advance Phase: into the target next to the unit, or one hex closer.

    The first list holds the advances of a berserk unit with no charge to make. The second
    holds the charge advances that are not made yet, and the phase does not end while it
    is not empty.
    """
    free_out: list[Command] = []
    forced: list[Command] = []
    for unit in state.player_units(state.active):
        if not unit.berserk or not unit.is_infantry or unit.hex is None or unit.carrier is not None:
            continue
        if unit.broken or unit.move_mode == MOVE_MODE_ADVANCED or state.in_melee(unit.hex):
            continue
        limit = ADVANCE_LEADER_PORTAGE if unit.kind == KIND_LEADER else ADVANCE_SQUAD_PORTAGE
        if r05_movement.weapon_portage(ctx, state, unit) > limit:
            continue
        free = [
            dst
            for dst in (geometry.neighbor(*unit.hex, d) for d in range(6))
            if _advance_allowed(ctx, state, unit, dst)
        ]
        targets = charge_targets(state, unit, sees)
        adjacent = [t for t in targets if geometry.distance(unit.hex, t) == 1]
        steps = None if adjacent else route_steps(ctx, state, unit, targets)
        if adjacent:
            forced.extend(Command("advance", units=(unit.id,), hex=t) for t in adjacent if t in free)
        elif steps is not None:
            forced.extend(Command("advance", units=(unit.id,), hex=h) for h in free if h in steps)
        else:
            # No target, or no route to one: the unit has no charge to make.
            free_out.extend(Command("advance", units=(unit.id,), hex=h) for h in free)
    return free_out, forced


def must_attack(state: State, declarations: list[Command]) -> bool:
    """Rule 18.42 in the Close Combat Phase: a berserk unit that can attack has not attacked.

    The unit is in a contested hex, and one of the legal declarations names it.
    """
    named: set[int] = set()
    for command in declarations:
        if command.action == "cc_attack":
            named.update(command.units)
    for unit in state.player_units(state.active):
        if unit.berserk and unit.id in named:
            return True
    return False
