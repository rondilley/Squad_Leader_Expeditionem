"""The observation and the composed command space of the learned agent (FR-50, FR-51).

The trainer sees three things and nothing else:

- A board tensor. One plane for each thing a player can read from the board, over the
  columns and rows of the scenario. The planes come from the acting player's view, so a
  concealed stack is a counter and not the units below it (rule 25.2, SR-09).
- A unit tensor. One row for each unit slot of the acting player, with what that player
  knows about the unit.
- A scalar vector: the turn, the phase, the sub-step, and which side acts.

The command is composed of three parts, as FR-51 asks: which unit, which action, and
which hex. A command with no unit uses the slot of the whole side, and a command with no
hex uses the target slot of no hex. The masks say which parts are legal, so an illegal
command cannot be selected by construction.

Why the three parts and not an index into the legal list: an index is a position, and a
position moves when the list changes. The three parts name the same thing in each state
and in each version of the code, which is the same reason the command ID is a hash of the
payload and not a position (TC-38).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from slcore import geometry
from slcore.commands import Command
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import PLAYER_TURN_PHASES, PHASE_SETUP, State
from slcore.geometry import HexRef
from slcore.state import Board
from slcore.units import KIND_CREW, KIND_LEADER, KIND_SQUAD, KIND_SW, KIND_VEHICLE, UnitType

# The actions of the composed head, in a fixed sequence. A new action goes at the end, so
# a saved policy keeps the meaning of the numbers it learned.
ACTIONS: tuple[str, ...] = (
    "end_phase",
    "end_setup",
    "place",
    "place_weapon",
    "place_concealment",
    "move",
    "stack_move",
    "advance",
    "pickup",
    "drop",
    "rally",
    "repair",
    "rout",
    "stay",
    "track_return",
    "group_add",
    "group_add_weapon",
    "group_leader",
    "group_fire",
    "cc_attack",
    "place_smoke",
    "place_demo",
    "explode_demo",
    "ft_fire",
    "sewer_move",
    "sewer_return",
    # Rules 28 to 41, the armor game. They go at the end so a saved policy keeps the
    # meaning of every number it learned before them.
    "vehicle_move",
    "vehicle_pivot",
    "board",
    "debark",
    "afv_fire",
    "afv_mg",
    "at_fire",
    "afv_attack",
    "cc_afv",
    "afv_repair",
    "push_wreck",
    "afv_smoke",
    "afv_dischargers",
)
ACTION_INDEX = {name: i for i, name in enumerate(ACTIONS)}

TERRAIN_KINDS: tuple[str, ...] = (
    "open",
    "woods",
    "wheat",
    "shellhole",
    "stone_building",
    "wooden_building",
)
KIND_ORDER: tuple[str, ...] = (KIND_SQUAD, KIND_CREW, KIND_LEADER, KIND_SW, KIND_VEHICLE)

# Four planes of terrain features, six of units, and four of counters (rules 24 and 25).
BOARD_PLANES = len(TERRAIN_KINDS) + 14
# Twenty-one features for a counter of any kind and five for a vehicle (rules 28 to 41).
UNIT_FEATURES = 26
SCALARS = len(PLAYER_TURN_PHASES) + 8
NO_UNIT = 0  # slot 0 is the side itself, for a command that names no unit
NO_HEX = 0  # target slot 0 is "no hex"


@dataclass(frozen=True)
class Spaces:
    """The sizes of the three heads for one scenario."""

    units: int
    actions: int
    targets: int
    cols: int
    rows: int

    @property
    def board_shape(self) -> tuple[int, int, int]:
        return (BOARD_PLANES, self.cols, self.rows + 1)

    @property
    def board_size(self) -> int:
        return BOARD_PLANES * self.cols * (self.rows + 1)

    @property
    def unit_shape(self) -> tuple[int, int]:
        return (self.units, UNIT_FEATURES)


def spaces_for(board: Board, unit_count: int) -> Spaces:
    """One slot for the side, one for each unit, and one target slot for each hex."""
    return Spaces(
        units=unit_count + 1,
        actions=len(ACTIONS),
        targets=len(board) + 1,
        cols=board.cols,
        rows=board.rows,
    )


def hex_slots(board: Board) -> dict[HexRef, int]:
    """The target slot of each hex. Slot 0 is no hex, so the hexes start at 1."""
    return {h.ref: i + 1 for i, h in enumerate(sorted(board, key=lambda x: x.ref))}


def command_triple(command: Command, hexes: Mapping[HexRef, int]) -> tuple[int, int, int]:
    """The three parts of one command: the unit slot, the action, and the target slot."""
    unit = command.units[0] + 1 if command.units else NO_UNIT
    action = ACTION_INDEX.get(command.action)
    if action is None:
        raise KeyError(f"the action {command.action!r} has no slot in the composed head")
    target = hexes.get(command.hex, NO_HEX) if command.hex is not None else NO_HEX
    return unit, action, target


def group_commands(frame: DecisionFrame, hexes: Mapping[HexRef, int]) -> dict[tuple[int, int, int], LegalCommand]:
    """The legal commands by their three parts.

    Two legal commands can have the same three parts, because a squad can fire one of two
    support weapons at the same hex. The lowest command ID wins, which is a stable choice
    in each version of the code.
    """
    out: dict[tuple[int, int, int], LegalCommand] = {}
    for legal in frame.commands:
        key = command_triple(legal.command, hexes)
        found = out.get(key)
        if found is None or legal.id < found.id:
            out[key] = legal
    return out


def masks_from(groups: Mapping[tuple[int, int, int], LegalCommand], spaces: Spaces) -> tuple[np.ndarray, np.ndarray]:
    """The unit mask and the action mask of one state.

    The target mask is not here, because a mask over each unit, each action, and each hex
    is a hundred times larger than the state itself. The environment gives the target mask
    for the unit and the action the policy selected.
    """
    unit_mask = np.zeros(spaces.units, dtype=np.int8)
    action_mask = np.zeros((spaces.units, spaces.actions), dtype=np.int8)
    for unit, action, _ in groups:
        unit_mask[unit] = 1
        action_mask[unit, action] = 1
    return unit_mask, action_mask


def target_mask_for(
    groups: Mapping[tuple[int, int, int], LegalCommand], spaces: Spaces, unit: int, action: int
) -> np.ndarray:
    mask = np.zeros(spaces.targets, dtype=np.int8)
    for u, a, t in groups:
        if u == unit and a == action:
            mask[t] = 1
    return mask


def board_tensor(board: Board, state: State, types: Mapping[str, UnitType], player: int, spaces: Spaces) -> np.ndarray:
    """The board as planes, from what this player is allowed to know.

    A unit below a concealment counter of the other side is not in the unit planes. Its
    hex has the counter plane set, which is what the player sees on the table (rule 25.2).
    """
    from slcore.view import concealed_from

    planes = np.zeros(spaces.board_shape, dtype=np.float32)
    kinds = {name: i for i, name in enumerate(TERRAIN_KINDS)}
    for h in board:
        col, row = h.ref
        index = kinds.get(h.terrain)
        if index is not None:
            planes[index, col, row] = 1.0
        base = len(TERRAIN_KINDS)
        planes[base + 0, col, row] = 1.0 if h.road else 0.0
        planes[base + 1, col, row] = 1.0 if h.building is not None else 0.0
        planes[base + 2, col, row] = 1.0 if h.sewer else 0.0
        planes[base + 3, col, row] = float(h.elevation) / 3.0
    base = len(TERRAIN_KINDS) + 4
    for unit in state.units:
        if unit.eliminated or unit.hex is None or unit.carrier is not None:
            continue
        if unit.player != player and concealed_from(state, unit, player):
            continue
        col, row = unit.hex
        own = unit.player == player
        offset = 0 if own else 3
        if unit.is_infantry:
            planes[base + offset + 0, col, row] += 0.25
            if unit.kind in (KIND_SQUAD, KIND_CREW):
                planes[base + offset + 1, col, row] += 0.34
            if unit.broken:
                planes[base + offset + 2, col, row] += 0.25
    base += 6
    for counter in state.concealment:
        col, row = counter.hex
        planes[base + (0 if counter.player == player else 1), col, row] = 1.0
    for smoke in state.smoke:
        planes[base + 2, smoke.hex[0], smoke.hex[1]] = 1.0
    for hex_ref in state.melee:
        planes[base + 3, hex_ref[0], hex_ref[1]] = 1.0
    return planes


def unit_tensor(state: State, types: Mapping[str, UnitType], player: int, spaces: Spaces, board: Board) -> np.ndarray:
    """One row for each unit slot. Slot 0 is the side, and it stays zero."""
    rows = np.zeros(spaces.unit_shape, dtype=np.float32)
    from slcore.view import concealed_from

    for unit in state.units:
        slot = unit.id + 1
        if slot >= spaces.units:
            continue
        if unit.eliminated:
            continue
        if unit.player != player and concealed_from(state, unit, player):
            continue
        t = types[unit.type_key]
        row = rows[slot]
        row[0] = 1.0
        row[1] = 1.0 if unit.player == player else 0.0
        if unit.hex is not None:
            row[2] = 1.0
            row[3] = unit.hex[0] / max(1, board.cols - 1)
            row[4] = unit.hex[1] / max(1, board.rows)
        row[5] = 1.0 if unit.carrier is not None else 0.0
        for i, kind in enumerate(KIND_ORDER):
            row[6 + i] = 1.0 if unit.kind == kind else 0.0
        row[11] = 1.0 if unit.broken else 0.0
        row[12] = 1.0 if unit.moved else 0.0
        row[13] = 1.0 if unit.fired else 0.0
        row[14] = 1.0 if unit.prep_fired else 0.0
        row[15] = 1.0 if unit.dm else 0.0
        row[16] = 1.0 if unit.berserk else 0.0
        row[17] = t.firepower / 8.0
        row[18] = t.range / 16.0
        row[19] = t.morale / 10.0
        row[20] = -t.leadership / 3.0
        if unit.is_vehicle:
            row[21] = (unit.facing + 1) / 6.0
            row[22] = 1.0 if unit.wreck else 0.0
            row[23] = 1.0 if unit.immobilized else 0.0
            row[24] = t.gun / 152.0
            row[25] = t.mp / 24.0
    return rows


def scalar_vector(state: State, frame: DecisionFrame, player: int) -> np.ndarray:
    """The turn, the phase, the sub-step, and which side acts."""
    out = np.zeros(SCALARS, dtype=np.float32)
    for i, phase in enumerate(PLAYER_TURN_PHASES):
        if state.phase == phase:
            out[i] = 1.0
    base = len(PLAYER_TURN_PHASES)
    out[base + 0] = 1.0 if state.phase == PHASE_SETUP else 0.0
    out[base + 1] = state.turn / max(1, state.turn_limit)
    out[base + 2] = state.sub_step / 8.0
    out[base + 3] = 1.0 if state.phasing == player else 0.0
    out[base + 4] = 1.0 if state.active == player else 0.0
    out[base + 5] = 1.0 if state.fire_group is not None else 0.0
    out[base + 6] = len(frame.commands) / 200.0
    out[base + 7] = 1.0 if state.game_over else 0.0
    return out
