"""The picture of a position: the board as planes of counts on the hex lattice.

A picture is what a person sees on the table with the counters turned up: the terrain,
the units of each side by kind and state, and the objective buildings with their
control. It is the spectator's view and not a player's, because the study asks what the
position is and not what one side knows of it (a per-player view goes out of the host,
a picture goes into an analysis on the owner's machine).

The planes are small integers, so a corpus of ten thousand positions is a few tens of
megabytes. Each plane is `[cols, rows + 1]`, the index of the lattice, so a picture of a
board turns into a tensor with no map between the two.
"""

from __future__ import annotations

from typing import Any, Mapping

import numpy as np

from slcore.game import State
from slcore.geometry import HexRef
from slcore.rules import victory
from slcore.state import Board
from slcore.units import KIND_CREW, KIND_LEADER, KIND_SQUAD, UnitType

TERRAIN_KINDS: tuple[str, ...] = ("open", "woods", "wheat", "shellhole", "stone_building", "wooden_building")

# The planes after the terrain kinds, in order.
PLANE_NAMES: tuple[str, ...] = TERRAIN_KINDS + (
    "road",
    "objective",
    "side0_squads",  # squads and crews of player 0, unbroken
    "side0_leaders",
    "side0_broken",
    "side1_squads",
    "side1_leaders",
    "side1_broken",
    "held_by_0",  # an objective building player 0 controls
    "held_by_1",
)
PLANES = len(PLANE_NAMES)
_INDEX = {name: i for i, name in enumerate(PLANE_NAMES)}


def shape_of(board: Board) -> tuple[int, int, int]:
    return (PLANES, board.cols, board.rows + 1)


def objective_buildings(engine: Any) -> dict[str, tuple[HexRef, ...]]:
    """The buildings the victory conditions name, each with its hexes."""
    on_board = victory.buildings_on(engine.board)
    out: dict[str, tuple[HexRef, ...]] = {}
    for condition in engine.scenario.victory:
        params = dict(condition.params)
        if condition.kind in (victory.KIND_BUILDING_SWING, victory.KIND_BUILDING_COUNT):
            groups = list(params.get("enemy_groups", [])) + list(params.get("own_groups", [])) + list(params.get("groups", []))
            for building in victory.group_buildings(engine.scenario, engine.board, groups):
                out[building] = tuple(on_board.get(building, ()))
    return out


def terrain_planes(board: Board, objectives: Mapping[str, tuple[HexRef, ...]]) -> np.ndarray:
    """The planes that do not move: the terrain, the roads, and the objective hexes."""
    planes = np.zeros(shape_of(board), dtype=np.uint8)
    kinds = {name: i for i, name in enumerate(TERRAIN_KINDS)}
    for h in board:
        col, row = h.ref
        # PR-56: an orchard has the rules of a wheatfield, so it takes the wheat plane.
        index = kinds.get("wheat" if h.terrain == "orchard" else h.terrain)
        if index is not None:
            planes[index, col, row] = 1
        if h.road:
            planes[_INDEX["road"], col, row] = 1
    for hexes in objectives.values():
        for col, row in hexes:
            planes[_INDEX["objective"], col, row] = 1
    return planes


def picture(
    board: Board,
    state: State,
    types: Mapping[str, UnitType],
    fixed: np.ndarray,
    objectives: Mapping[str, tuple[HexRef, ...]],
) -> np.ndarray:
    """The picture of one position, on top of the fixed planes of the board."""
    planes = fixed.copy()
    for unit in state.units:
        if unit.eliminated or unit.hex is None or unit.carrier is not None or not unit.is_infantry:
            continue
        col, row = unit.hex
        side = f"side{unit.player}"
        if unit.broken:
            planes[_INDEX[f"{side}_broken"], col, row] += 1
        elif unit.kind == KIND_LEADER:
            planes[_INDEX[f"{side}_leaders"], col, row] += 1
        elif unit.kind in (KIND_SQUAD, KIND_CREW):
            planes[_INDEX[f"{side}_squads"], col, row] += 1
    for building, hexes in objectives.items():
        for player in (0, 1):
            if victory.controlled_by(state, board, building, player):
                for col, row in hexes:
                    planes[_INDEX[f"held_by_{player}"], col, row] = 1
    return planes


def plane(pic: np.ndarray, name: str) -> np.ndarray:
    return pic[_INDEX[name]]
