"""The shape statistics of a position, for one side.

A statistic is a number a person could read off the table: how many groups the side
stands in, how far apart, how wide and how deep, how near the objective, how much in
cover, how many squads have a leader at hand, how many units the enemy sees. The
analysis asks which of these differ between the side that wins and the side that loses,
at the same turn, beyond the count of the squads and the buildings.

The material statistics come first, so the analysis can hold them fixed and read the
shape on top of them.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from slcore import geometry
from slcore.game import State
from slcore.geometry import HexRef
from slcore.los_eval import evaluate as evaluate_los
from slcore.rules import victory
from slcore.rules.r11_terrain import is_open_ground
from slcore.rules.r13_rout import is_cover
from slcore.units import KIND_LEADER, KIND_SQUAD, KIND_CREW, Unit

MATERIAL: tuple[str, ...] = (
    "squads",  # unbroken squads and crews
    "leaders",  # unbroken leaders
    "broken",  # broken units
    "held",  # objective buildings the side controls
    "enemy_squads",
    "enemy_leaders",
    "enemy_broken",
    "enemy_held",
)

SHAPE: tuple[str, ...] = (
    "hexes",  # distinct hexes the unbroken units stand in
    "max_stack",  # the most unbroken units in one hex
    "clusters",  # rule 8.6 chains: groups of adjacent occupied hexes
    "largest_cluster",  # units in the largest chain
    "nn_distance",  # mean distance from each occupied hex to the nearest other one
    "col_range",  # the width of the side across the columns
    "row_range",  # the depth of the side along the rows
    "col_std",
    "row_std",
    "to_enemy_buildings",  # mean distance of the units to the nearest hex of an enemy objective building
    "near_enemy_buildings",  # share of units within two hexes of one
    "to_own_buildings",  # mean distance to the nearest hex of an own objective building
    "in_own_buildings",  # share of units in an own objective building
    "cover_share",  # share of units in a building or woods
    "open_share",  # share of units in open ground
    "leader_at_hand",  # share of squads in a hex with an unbroken leader or next to one
    "contact",  # share of units adjacent to an unbroken enemy unit
    "seen_by",  # mean count of unbroken enemy squads with a line of sight to the unit
    "sees",  # mean count of unbroken enemy units the unit has a line of sight to
    "flank_balance",  # the smaller share of the units on either column side of the enemy centroid
    "to_enemy_centroid",  # distance of the side's centroid to the enemy's centroid
)

FEATURE_NAMES: tuple[str, ...] = MATERIAL + SHAPE
_INDEX = {name: i for i, name in enumerate(FEATURE_NAMES)}


def _standing(state: State, player: int) -> list[Unit]:
    return [
        u
        for u in state.player_units(player)
        if not u.eliminated and u.hex is not None and u.carrier is None and u.is_infantry
    ]


def _clusters(board: Any, hexes: set[HexRef]) -> list[set[HexRef]]:
    left = set(hexes)
    out: list[set[HexRef]] = []
    while left:
        start = min(left)
        cluster = {start}
        left.discard(start)
        edge = [start]
        while edge:
            h = edge.pop()
            for near in board.neighbors(h):
                if near in left:
                    left.discard(near)
                    cluster.add(near)
                    edge.append(near)
        out.append(cluster)
    return out


def _mean_distance_to(units: list[Unit], targets: tuple[HexRef, ...]) -> float:
    if not units or not targets:
        return 0.0
    return float(np.mean([min(geometry.distance(u.hex, t) for t in targets) for u in units]))


def side_buildings(engine: Any, objectives: Mapping[str, tuple[HexRef, ...]]) -> dict[int, tuple[HexRef, ...]]:
    """The objective hexes each player set up in: the buildings of its own groups.

    In a building swing condition the attacker has to take the buildings of the other
    side and hold its own. The set up areas of the scenario say whose building each is.
    """
    out: dict[int, list[HexRef]] = {0: [], 1: []}
    for player, side in enumerate(engine.scenario.players()):
        spec = next((s for s in engine.scenario.sides if s.side == side), None)
        if spec is None:
            continue
        for group in spec.groups:
            building = group.area.building_id(engine.board)
            if building is not None and building in objectives:
                out[player].extend(objectives[building])
    return {player: tuple(sorted(set(hexes))) for player, hexes in out.items()}


def features_of(
    engine: Any,
    state: State,
    objectives: Mapping[str, tuple[HexRef, ...]],
    buildings_of: Mapping[int, tuple[HexRef, ...]],
    player: int,
) -> np.ndarray:
    """The statistics of one side in one position."""
    board = engine.board
    out = np.zeros(len(FEATURE_NAMES), dtype=np.float32)
    own_all = _standing(state, player)
    enemy_all = _standing(state, 1 - player)
    own = [u for u in own_all if not u.broken]
    enemy = [u for u in enemy_all if not u.broken]
    own_squads = [u for u in own if u.kind in (KIND_SQUAD, KIND_CREW)]
    own_leaders = [u for u in own if u.kind == KIND_LEADER]
    enemy_squads = [u for u in enemy if u.kind in (KIND_SQUAD, KIND_CREW)]

    def put(name: str, value: float) -> None:
        out[_INDEX[name]] = float(value)

    put("squads", len(own_squads))
    put("leaders", len(own_leaders))
    put("broken", sum(1 for u in own_all if u.broken))
    put("enemy_squads", len(enemy_squads))
    put("enemy_leaders", sum(1 for u in enemy if u.kind == KIND_LEADER))
    put("enemy_broken", sum(1 for u in enemy_all if u.broken))
    held = sum(1 for b in objectives if victory.controlled_by(state, board, b, player))
    enemy_held = sum(1 for b in objectives if victory.controlled_by(state, board, b, 1 - player))
    put("held", held)
    put("enemy_held", enemy_held)
    if not own:
        return out

    hexes = {u.hex for u in own}
    put("hexes", len(hexes))
    counts: dict[HexRef, int] = {}
    for u in own:
        counts[u.hex] = counts.get(u.hex, 0) + 1
    put("max_stack", max(counts.values()))
    clusters = _clusters(board, hexes)
    put("clusters", len(clusters))
    put("largest_cluster", max(sum(counts[h] for h in c) for c in clusters))
    if len(hexes) > 1:
        put("nn_distance", float(np.mean([min(geometry.distance(h, k) for k in hexes if k != h) for h in hexes])))
    cols = np.array([u.hex[0] for u in own], dtype=np.float32)
    rows = np.array([u.hex[1] for u in own], dtype=np.float32)
    put("col_range", cols.max() - cols.min())
    put("row_range", rows.max() - rows.min())
    put("col_std", cols.std())
    put("row_std", rows.std())
    enemy_buildings = buildings_of.get(1 - player, ())
    own_buildings = buildings_of.get(player, ())
    put("to_enemy_buildings", _mean_distance_to(own, enemy_buildings))
    if enemy_buildings:
        put("near_enemy_buildings", np.mean([min(geometry.distance(u.hex, t) for t in enemy_buildings) <= 2 for u in own]))
    put("to_own_buildings", _mean_distance_to(own, own_buildings))
    if own_buildings:
        own_set = set(own_buildings)
        put("in_own_buildings", np.mean([u.hex in own_set for u in own]))
    put("cover_share", np.mean([is_cover(board, u.hex) for u in own]))
    put("open_share", np.mean([is_open_ground(board, u.hex) for u in own]))
    if own_squads:
        leader_hexes = {u.hex for u in own_leaders}
        near_leader = set()
        for h in leader_hexes:
            near_leader.add(h)
            near_leader.update(board.neighbors(h))
        put("leader_at_hand", np.mean([u.hex in near_leader for u in own_squads]))
    enemy_hexes = {u.hex for u in enemy}
    if enemy_hexes:
        adjacent = set()
        for h in enemy_hexes:
            adjacent.update(board.neighbors(h))
        put("contact", np.mean([u.hex in adjacent for u in own]))
        seen = []
        sees = []
        los_cache: dict[tuple[HexRef, HexRef], bool] = {}

        def clear(a: HexRef, b: HexRef) -> bool:
            key = (a, b) if a <= b else (b, a)
            found = los_cache.get(key)
            if found is None:
                found = evaluate_los(board, engine.los, key[0], key[1]).clear
                los_cache[key] = found
            return found

        for h in hexes:
            seen.append(sum(1 for e in enemy_squads if e.hex != h and clear(h, e.hex)))
            sees.append(sum(1 for e in enemy if e.hex != h and clear(h, e.hex)))
        put("seen_by", float(np.mean(seen)))
        put("sees", float(np.mean(sees)))
        enemy_cols = np.array([u.hex[0] for u in enemy], dtype=np.float32)
        enemy_rows = np.array([u.hex[1] for u in enemy], dtype=np.float32)
        centroid_col = float(enemy_cols.mean())
        left = float(np.mean(cols < centroid_col))
        right = float(np.mean(cols > centroid_col))
        put("flank_balance", min(left, right))
        put("to_enemy_centroid", float(np.hypot(cols.mean() - centroid_col, (rows.mean() - enemy_rows.mean()) * 0.866)))
    return out
