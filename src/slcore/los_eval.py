"""The LOS rule evaluator with the firer as the context (FR-28).

It takes the static thread from `los_cache`, applies the firer's hexside
choices of rule 17.7, adds the dynamic hindrances, and calls the rule 7
functions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product

from slcore.geometry import HexRef
from slcore.los_cache import LosTable, Thread
from slcore.rules import r07_los, r32_afv_cover
from slcore.rules.r07_los import LosVerdict, TracedHex
from slcore.state import LOS_BLOCK, LOS_HINDER, Board


@dataclass(frozen=True)
class LosContext:
    """Dynamic state that changes LOS: smoke hexes (rule 24) and vehicle hexes (rule 32)."""

    smoke: frozenset[HexRef] = field(default_factory=frozenset)
    vehicles: frozenset[HexRef] = field(default_factory=frozenset)


@dataclass(frozen=True)
class LosResult:
    firer: HexRef
    target: HexRef
    clear: bool
    rule_id: str
    traced: tuple[HexRef, ...]
    choices: tuple[HexRef, ...]
    hindrance: int
    smoke_hexes: tuple[HexRef, ...]
    blocking_hex: HexRef | None = None
    blocking_hexside: tuple[HexRef, int] | None = None
    vehicle_modifier: int = 0


def _severity(board: Board, ref: HexRef, kinds: frozenset[str]) -> int:
    if not kinds:
        return 0
    if all(board.los_class(k) == LOS_HINDER for k in kinds):
        return 1
    if r07_los.crossed_multi_story_building(board, ref, kinds):
        return 3
    if any(board.los_class(k) == LOS_BLOCK for k in kinds):
        return 2
    return 1


def resolve_choices(board: Board, thread: Thread, choices: dict[int, HexRef] | None) -> tuple[list[TracedHex], tuple[HexRef, ...]]:
    """Apply the rule 17.7 choices. A choice names the hex for a step index.

    Without an explicit choice, the evaluator selects the side with the least
    obstruction, and the first hex in sorted order on a tie. That is the
    choice a firer makes when the question is whether any LOS exists.
    """
    traced: list[TracedHex] = []
    made: list[HexRef] = []
    for i, step in enumerate(thread.steps):
        if not step.choice:
            traced.append(TracedHex(step.hexes[0], step.kinds[0]))
            continue
        pick = 0
        if choices is not None and i in choices:
            wanted = choices[i]
            if wanted not in step.hexes:
                raise ValueError(f"hex {wanted} is not a side of step {i}")
            pick = step.hexes.index(wanted)
        else:
            best = None
            for k, (h, kinds) in enumerate(zip(step.hexes, step.kinds)):
                sev = _severity(board, h, kinds)
                if best is None or sev < best[0]:
                    best = (sev, k)
            pick = best[1] if best is not None else 0
        traced.append(TracedHex(step.hexes[pick], step.kinds[pick]))
        made.append(step.hexes[pick])
    return traced, tuple(made)


def evaluate(
    board: Board,
    table: LosTable,
    firer: HexRef,
    target: HexRef,
    ctx: LosContext | None = None,
    choices: dict[int, HexRef] | None = None,
) -> LosResult:
    """Is there a LOS from firer to target, and with what hindrance.

    With no explicit choices the result is clear when any combination of the
    rule 17.7 choices gives a clear LOS. The traced hexes of the result are
    the hexes of that combination.
    """
    if ctx is None:
        ctx = LosContext()
    static = choices is None and not ctx.smoke and not ctx.vehicles
    if static:
        found = table.static_results.get((firer, target))
        if found is not None:
            return found  # type: ignore[return-value]
    thread = table.thread(firer, target)
    traced, made = resolve_choices(board, thread, choices)
    verdict = r07_los.evaluate_traced(board, firer, target, traced)
    if not verdict.clear and choices is None and any(s.choice for s in thread.steps):
        alt = _search_clear(board, thread, firer, target)
        if alt is not None:
            traced, made, verdict = alt
    result = _result(board, thread, firer, target, traced, made, verdict, ctx)
    if static:
        table.static_results[(firer, target)] = result
    return result


def _search_clear(board: Board, thread: Thread, firer: HexRef, target: HexRef):
    choice_steps = [i for i, s in enumerate(thread.steps) if s.choice]
    if len(choice_steps) > 12:
        return None
    options = [thread.steps[i].hexes for i in choice_steps]
    for combo in product(*options):
        choices = dict(zip(choice_steps, combo))
        traced, made = resolve_choices(board, thread, choices)
        verdict = r07_los.evaluate_traced(board, firer, target, traced)
        if verdict.clear:
            return traced, made, verdict
    return None


def _result(board: Board, thread: Thread, firer: HexRef, target: HexRef, traced: list[TracedHex], made: tuple[HexRef, ...], verdict: LosVerdict, ctx: LosContext) -> LosResult:
    refs = tuple(t.ref for t in traced)
    smoke = tuple(r for r in refs if r in ctx.smoke)
    hindrance = r07_los.hindrance_count(board, traced) + len(smoke)
    # Rule 32.3: a vehicle outline on the path is a stone wall on the far hexside of its
    # hex, so it blocks a shot that goes past the hex behind it and adds the wall modifier
    # to a shot that ends there.
    blocked, vehicle_modifier = r32_afv_cover.vehicle_block(board, ctx.vehicles, firer, refs, target)
    clear = verdict.clear and not blocked
    rule_id = r32_afv_cover.RULE_32_3 if blocked else verdict.rule_id
    blocking = verdict.blocking_hex
    if blocked:
        blocking = next(r for r in reversed(refs) if r in ctx.vehicles and not board.adjacent(firer, r))
    return LosResult(
        firer=firer,
        target=target,
        clear=clear,
        rule_id=rule_id,
        traced=refs,
        choices=made,
        hindrance=hindrance,
        smoke_hexes=smoke,
        blocking_hex=blocking,
        blocking_hexside=verdict.blocking_hexside,
        vehicle_modifier=vehicle_modifier,
    )


def thread_hexes(table: LosTable, firer: HexRef, target: HexRef, choices: dict[int, HexRef] | None = None) -> tuple[HexRef, ...]:
    """The hexes along the LOS in firer-to-target order, after choices (for rule 17.5)."""
    thread = table.thread(firer, target)
    traced, _ = resolve_choices(table.board, thread, choices)
    return tuple(t.ref for t in traced)
