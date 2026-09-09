"""The victory evaluator (FR-14).

A scenario lists its victory conditions as typed records. The core tests them at the
end of the last player turn, and it tests a sudden-death condition at the end of each
phase. The result is one line for each condition with its count and its threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from slcore import geometry
from slcore.game import State
from slcore.scenario import Scenario, VictoryCondition
from slcore.state import Board
from slcore.units import KIND_LEADER, UnitType

RULE_VICTORY = "victory"

KIND_BUILDING_SWING = "building_swing"
KIND_UNBROKEN_SQUAD_RATIO = "unbroken_squad_ratio"
KIND_BUILDING_COUNT = "building_count"
KIND_HEX_CONTROL = "hex_control"
KIND_SOLE_OCCUPANT = "sole_occupant"
KIND_FORCE_ELIMINATED = "force_eliminated"
KIND_CASUALTY_EXCHANGE = "casualty_exchange"

RESULT_DRAW = "draw"


@dataclass(frozen=True)
class ConditionResult:
    kind: str
    side: str
    count: int
    threshold: int
    satisfied: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "side": self.side,
            "count": self.count,
            "threshold": self.threshold,
            "satisfied": self.satisfied,
            "detail": self.detail,
        }


def buildings_on(board: Board) -> dict[str, tuple]:
    out: dict[str, list] = {}
    for h in board:
        if h.building is not None:
            out.setdefault(h.building.id, []).append(h.ref)
    return {k: tuple(sorted(v)) for k, v in out.items()}


def update_last_occupant(state: State, board: Board) -> State:
    """PR-07: the core records the last side with an unbroken unit in each building.

    The record is refreshed at the end of each phase, which is where the core can see
    the board. The rules say "the last to have occupied any hex of the building with an
    unbroken unit" and give no moment of record.
    """
    current = dict(state.last_occupant)
    by_hex = dict(state.hex_occupant)
    changed = False
    for u in state.units:
        if u.eliminated or u.broken or u.hex is None or u.carrier is not None or not u.is_infantry:
            continue
        name = geometry.hex_id(*u.hex)
        if by_hex.get(name) != u.player:
            by_hex[name] = u.player
            changed = True
        building = board.hex(u.hex).building
        if building is None:
            continue
        if current.get(building.id) != u.player:
            current[building.id] = u.player
            changed = True
    if not changed:
        return state
    return state.with_(last_occupant=tuple(sorted(current.items())), hex_occupant=tuple(sorted(by_hex.items())))


def hex_controlled_by(state: State, hex_ref, player: int) -> bool:
    """The scenario 2 card: the last side with an unbroken unit in the hex controls it.

    A hex where the two sides are in Close Combat belongs to neither side, and an enemy
    unit in the hex takes the control away while it is there.
    """
    if state.in_melee(hex_ref):
        return False
    for u in state.infantry_in(hex_ref):
        if u.player != player:
            return False
    return dict(state.hex_occupant).get(geometry.hex_id(*hex_ref)) == player


def group_hexes(scenario: Scenario, board: Board, group_ids: Any) -> list:
    """The hexes of the buildings that the named groups set up in."""
    out: list = []
    for gid in group_ids:
        building = scenario.group(str(gid)).area.building_id(board)
        if building is None:
            continue
        out.extend(buildings_on(board).get(building, ()))
    return sorted(set(out))


def controlled_by(state: State, board: Board, building_id: str, player: int) -> bool:
    """Complete occupation: no enemy squad or leader in the building and the last occupant is the player."""
    hexes = buildings_on(board).get(building_id, ())
    for h in hexes:
        for u in state.infantry_in(h):
            if u.player != player and u.is_infantry:
                return False
    return dict(state.last_occupant).get(building_id) == player


def group_buildings(scenario: Scenario, board: Board, group_ids: Any) -> list[str]:
    """The building of each named group's set up area."""
    out: list[str] = []
    for gid in group_ids:
        found = scenario.group(str(gid)).area.building_id(board)
        if found is not None:
            out.append(found)
    return out


def eliminated_squads(state: State, types: Mapping[str, UnitType], player: int) -> int:
    """The squads and the crews of a player that the game has removed.

    A leader is not a squad. The victory conditions of the random scenarios count squads,
    and the campaign game counts a leader on its own personnel file.
    """
    return sum(
        1
        for u in state.units
        if u.player == player and u.eliminated and types[u.type_key].kind not in (KIND_LEADER, "sw")
    )


def standing_infantry(state: State, types: Mapping[str, UnitType], player: int) -> int:
    """Each infantry unit of a player that is on the board, broken or not."""
    return sum(
        1
        for u in state.units
        if u.player == player and not u.eliminated and types[u.type_key].kind != "sw"
    )


def unbroken_squads(state: State, types: Mapping[str, UnitType], player: int) -> int:
    return sum(
        1
        for u in state.player_units(player)
        if u.kind != KIND_LEADER and u.is_infantry and not u.broken and u.from_wreck is None
    )


def evaluate_condition(state: State, board: Board, scenario: Scenario, types: Mapping[str, UnitType], condition: VictoryCondition) -> ConditionResult:
    params = dict(condition.params)
    side = str(params.get("side", ""))
    player = scenario.side_index(side) if side else 0
    if condition.kind == KIND_BUILDING_SWING:
        enemy = group_buildings(scenario, board, params.get("enemy_groups", []))
        own = group_buildings(scenario, board, params.get("own_groups", []))
        taken = [b for b in enemy if controlled_by(state, board, b, player)]
        lost = [b for b in own if not controlled_by(state, board, b, player)]
        margin = int(params.get("margin", 2))
        swing = len(taken) - len(lost)
        return ConditionResult(
            condition.kind,
            side,
            swing,
            margin,
            swing >= margin,
            f"took {sorted(taken)}, lost {sorted(lost)}",
        )
    if condition.kind == KIND_UNBROKEN_SQUAD_RATIO:
        own = unbroken_squads(state, types, player)
        other = unbroken_squads(state, types, 1 - player)
        numerator = int(params.get("numerator", 3))
        denominator = int(params.get("denominator", 1))
        satisfied = own * denominator >= numerator * other
        return ConditionResult(
            condition.kind,
            side,
            own,
            other,
            satisfied,
            f"{own} unbroken squads against {other}, needs {numerator} to {denominator}",
        )
    if condition.kind == KIND_HEX_CONTROL:
        hexes = group_hexes(scenario, board, params.get("groups", []))
        held = [h for h in hexes if hex_controlled_by(state, h, player)]
        threshold = min(int(params.get("count", 1)), len(hexes))
        return ConditionResult(
            condition.kind,
            side,
            len(held),
            threshold,
            bool(hexes) and len(held) >= threshold,
            f"controls {len(held)} of {len(hexes)} hexes, and needs {threshold} (PR-16)",
        )
    if condition.kind == KIND_SOLE_OCCUPANT:
        hexes = group_hexes(scenario, board, params.get("groups", []))
        mine = sum(1 for h in hexes for u in state.infantry_in(h) if u.player == player and not u.broken)
        theirs = sum(1 for h in hexes for u in state.infantry_in(h) if u.player != player and not u.broken)
        return ConditionResult(
            condition.kind,
            side,
            mine,
            1,
            mine > 0 and theirs == 0,
            f"{mine} unbroken units in the building against {theirs}",
        )
    if condition.kind == KIND_BUILDING_COUNT:
        wanted = group_buildings(scenario, board, params.get("groups", []))
        held = [b for b in wanted if controlled_by(state, board, b, player)]
        threshold = int(params.get("count", 1))
        return ConditionResult(condition.kind, side, len(held), threshold, len(held) >= threshold, f"holds {sorted(held)}")
    if condition.kind == KIND_FORCE_ELIMINATED:
        # The random scenario construction of Game Set IV: the defending force is gone.
        left = standing_infantry(state, types, 1 - player)
        return ConditionResult(
            condition.kind,
            side,
            left,
            0,
            left == 0,
            f"the other side has {left} infantry units on the board",
        )
    if condition.kind == KIND_CASUALTY_EXCHANGE:
        # The random scenario construction of Game Set IV: kill more than you lose.
        took = eliminated_squads(state, types, 1 - player)
        lost = eliminated_squads(state, types, player)
        margin = int(params.get("margin", 1))
        return ConditionResult(
            condition.kind,
            side,
            took - lost,
            margin,
            took - lost >= margin,
            f"eliminated {took} squads and lost {lost}",
        )
    raise NotImplementedError(f"victory condition {condition.kind!r} waits for the scenario that uses it, in v0.3")


def evaluate(state: State, board: Board, scenario: Scenario, types: Mapping[str, UnitType]) -> tuple[str, str, list[ConditionResult]]:
    """The winner, the cause, and one line for each condition."""
    results = [evaluate_condition(state, board, scenario, types, c) for c in scenario.victory]
    winners = sorted({r.side for r in results if r.satisfied})
    if len(winners) == 1:
        winner = winners[0]
        cause = "; ".join(f"{r.kind}: {r.detail}" for r in results if r.satisfied and r.side == winner)
        return winner, cause, results
    if len(winners) > 1:
        return RESULT_DRAW, "the two sides satisfied a victory condition", results
    losers = sorted({r.side for r in results})
    if len(losers) == 1:
        other = [s.side for s in scenario.sides if s.side != losers[0]]
        cause = "; ".join(f"{r.kind}: {r.detail}" for r in results)
        return (other[0] if other else RESULT_DRAW), f"the other side did not satisfy its conditions ({cause})", results
    return RESULT_DRAW, "no side satisfied a victory condition", results
