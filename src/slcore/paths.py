"""Shortest routes in movement factors (rules 13.43 and 18.42). Dijkstra on the board with integer costs."""

from __future__ import annotations

import heapq
from typing import Callable

from slcore import geometry
from slcore.geometry import HexRef
from slcore.rules.r05_movement import MoveContext, entry_cost_halves

StepAllowed = Callable[[HexRef, HexRef], bool]


def shortest_paths(ctx: MoveContext, start: HexRef, step_allowed: StepAllowed, limit: int | None = None) -> tuple[dict[HexRef, int], dict[HexRef, HexRef]]:
    """Costs in halves from start to each reachable hex, and the predecessor of each.

    step_allowed(prev, nxt) says whether the route may go from prev into nxt.
    Ties break on the hex reference, so the result is deterministic.
    """
    dist: dict[HexRef, int] = {start: 0}
    pred: dict[HexRef, HexRef] = {}
    heap: list[tuple[int, HexRef]] = [(0, start)]
    while heap:
        cost, here = heapq.heappop(heap)
        if cost > dist.get(here, 1 << 30):
            continue
        if limit is not None and cost > limit:
            continue
        for d in range(6):
            nxt = geometry.neighbor(*here, d)
            if nxt not in ctx.board or not step_allowed(here, nxt):
                continue
            step, _ = entry_cost_halves(ctx, here, nxt)
            if step is None:
                continue
            total = cost + step
            if total < dist.get(nxt, 1 << 30) or (total == dist.get(nxt) and pred.get(nxt, (1 << 30, 0)) > here):
                dist[nxt] = total
                pred[nxt] = here
                heapq.heappush(heap, (total, nxt))
    return dist, pred


def nearest_goals(
    ctx: MoveContext, start: HexRef, step_allowed: StepAllowed, is_goal: Callable[[HexRef], bool]
) -> tuple[int | None, list[HexRef], dict[HexRef, HexRef]]:
    """The cost of the nearest goal hexes, those hexes in sorted order, and the predecessors.

    This is `shortest_paths` that stops at the first goal hex it takes from the heap.
    Each step costs one half or more, so each hex of a lower cost is done at that time:
    the cost of each hex at the goal cost is final, and so is its predecessor with the
    same tie break. A route from `route` to one of the goals is the route that the full
    search gives. The start hex is never a goal. With no goal in reach the cost is None
    and the list is empty.
    """
    dist: dict[HexRef, int] = {start: 0}
    pred: dict[HexRef, HexRef] = {}
    heap: list[tuple[int, HexRef]] = [(0, start)]
    board = ctx.board
    neighbor = geometry.neighbor
    best: int | None = None
    while heap:
        cost, here = heapq.heappop(heap)
        if cost > dist.get(here, 1 << 30):
            continue
        if here != start and is_goal(here):
            best = cost
            break
        for d in range(6):
            nxt = neighbor(*here, d)
            if nxt not in board or not step_allowed(here, nxt):
                continue
            step, _ = entry_cost_halves(ctx, here, nxt)
            if step is None:
                continue
            total = cost + step
            if total < dist.get(nxt, 1 << 30) or (total == dist.get(nxt) and pred.get(nxt, (1 << 30, 0)) > here):
                dist[nxt] = total
                pred[nxt] = here
                heapq.heappush(heap, (total, nxt))
    if best is None:
        return None, [], pred
    goals = sorted(ref for ref, cost in dist.items() if cost == best and ref != start and is_goal(ref))
    return best, goals, pred


def route(pred: dict[HexRef, HexRef], start: HexRef, goal: HexRef) -> list[HexRef]:
    """The hexes from start to goal, start excluded, goal included."""
    out: list[HexRef] = []
    here = goal
    while here != start:
        out.append(here)
        here = pred[here]
    out.reverse()
    return out
