"""The observation and the composed command space of the learned agent (FR-50, FR-51).

The trainer sees three things and nothing else:

- A board tensor. One plane for each thing a player can read from the board, over the
  columns and rows of the scenario. The planes come from the acting player's view, so a
  concealed stack is a counter and not the units below it (rule 25.2, SR-09).
- A unit tensor. One row for each unit slot of the acting player, with what that player
  knows about the unit.
- A scalar vector: the turn, the phase, the sub-step, and which side acts.

The planes and the rows hold what the policy needs for the decisions the game asks. The
imitation of 2026-09-16 gave the reason for four of them: the policy fired a group at the
teacher's moment in none of 93 states, and it ended a Movement or Advance Phase at the
teacher's moment in none of 60, because the observation had no fire group, no target of
it, and no sign of which units still had a command. A state with one unit in the group
and a state with five looked the same. So the rows say which units are in the group, who
leads it, and which units have a legal command now, and the planes say the target of the
group, the buildings a positional victory condition names, and who holds each one.

The command is composed of four parts: which unit, which action, which hex, and which
option. A command with no unit uses the slot of the whole side, and a command with no
hex uses the target slot of no hex. Two support weapons at one hex share the first three
parts. The option is that command's place in command-id order. The masks say which parts
are legal, so an illegal command cannot be selected by construction.

Why these parts and not an index into the legal list: an index is a position, and a
position moves when the list changes. The parts name the same thing in each state, which
is the same reason the command ID is a hash of the payload and not a position (TC-38).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np

from slcore import geometry
from slcore.commands import Command
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import PLAYER_TURN_PHASES, PHASE_SETUP, State
from slcore.hashing import position_key as core_position_key
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
    # Rule 35.8: the push out of an overrun, after the Defensive Fire Phase. It is last, so
    # each index before it keeps its meaning.
    "push_out",
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

# Four planes of terrain features, six of units, four of counters (rules 24 and 25), one
# of the fire group's target, and three of the objective buildings and their control.
BOARD_PLANES = len(TERRAIN_KINDS) + 18
# Twenty-one features for a counter of any kind, five for a vehicle (rules 28 to 41), and
# eight for the fire group, the legal list, and the flags of the phase.
UNIT_FEATURES = 34
SCALARS = len(PLAYER_TURN_PHASES) + 8
NO_UNIT = 0  # slot 0 is the side itself, for a command that names no unit
NO_HEX = 0  # target slot 0 is "no hex"
# Two support weapons at one hex are two commands with the same unit, action, and hex.
# A close combat hex does the same with every attack that starts with the same unit.
# The option head names which command. Sixty-four covers that list on the scenarios
# the trainer plays. A longer list keeps the lowest command ids.
MAX_OPTIONS = 64


@dataclass(frozen=True)
class Spaces:
    """The sizes of the heads for one scenario."""

    units: int
    actions: int
    targets: int
    cols: int
    rows: int
    options: int = MAX_OPTIONS

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
        options=MAX_OPTIONS,
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


def group_commands(frame: DecisionFrame, hexes: Mapping[HexRef, int]) -> dict[tuple[int, int, int, int], LegalCommand]:
    """The legal commands by unit, action, hex, and option.

    Two support weapons at one hex share the first three parts. The options are those
    commands in command-id order. Option 0 is the only command when the triple is unique.
    The environment applies the command of the option. It does not apply the lowest id
    and drop the other weapon.
    """
    buckets: dict[tuple[int, int, int], list[LegalCommand]] = {}
    for legal in frame.commands:
        buckets.setdefault(command_triple(legal.command, hexes), []).append(legal)
    out: dict[tuple[int, int, int, int], LegalCommand] = {}
    for key, commands in buckets.items():
        for option, legal in enumerate(sorted(commands, key=lambda c: c.id)[:MAX_OPTIONS]):
            out[(*key, option)] = legal
    return out


def command_index(
    legal: LegalCommand, groups: Mapping[tuple[int, int, int, int], LegalCommand]
) -> tuple[int, int, int, int]:
    """The four parts of one legal command in the map from `group_commands`."""
    for key, command in groups.items():
        if command.id == legal.id:
            return key
    raise KeyError(f"the command {legal.id} is not in the grouped legal list")


def masks_from(groups: Mapping[tuple[int, int, int, int], LegalCommand], spaces: Spaces) -> tuple[np.ndarray, np.ndarray]:
    """The unit mask and the action mask of one state.

    The target mask is not here, because a mask over each unit, each action, and each hex
    is a hundred times larger than the state itself. The environment gives the target mask
    for the unit and the action the policy selected.
    """
    unit_mask = np.zeros(spaces.units, dtype=np.int8)
    action_mask = np.zeros((spaces.units, spaces.actions), dtype=np.int8)
    for unit, action, _, _ in groups:
        unit_mask[unit] = 1
        action_mask[unit, action] = 1
    return unit_mask, action_mask


def target_mask_for(
    groups: Mapping[tuple[int, int, int, int], LegalCommand], spaces: Spaces, unit: int, action: int
) -> np.ndarray:
    mask = np.zeros(spaces.targets, dtype=np.int8)
    for u, a, t, _ in groups:
        if u == unit and a == action:
            mask[t] = 1
    return mask


def option_mask_for(
    groups: Mapping[tuple[int, int, int, int], LegalCommand], spaces: Spaces, unit: int, action: int, target: int
) -> np.ndarray:
    """The fourth head: which command of this unit, action, and hex is legal."""
    mask = np.zeros(spaces.options, dtype=np.int8)
    for u, a, t, option in groups:
        if u == unit and a == action and t == target:
            mask[option] = 1
    return mask


@dataclass(frozen=True)
class Objectives:
    """The buildings and the hexes that the positional victory conditions of a scenario name.

    Built once for an engine by `objectives_for`, because the buildings do not move. The
    control of each one is read from the state at each observation.
    """

    buildings: tuple[tuple[str, tuple[HexRef, ...]], ...] = ()
    hexes: tuple[HexRef, ...] = ()


def objectives_for(engine) -> Objectives:
    """The objective buildings and hexes of the engine's scenario, from the victory evaluator's helpers."""
    from slcore.rules import victory

    buildings: dict[str, tuple[HexRef, ...]] = {}
    hexes: list[HexRef] = []
    on_board = victory.buildings_on(engine.board)
    for condition in engine.scenario.victory:
        params = dict(condition.params)
        if condition.kind in (victory.KIND_BUILDING_SWING, victory.KIND_BUILDING_COUNT):
            groups = list(params.get("enemy_groups", [])) + list(params.get("own_groups", [])) + list(params.get("groups", []))
            for building in victory.group_buildings(engine.scenario, engine.board, groups):
                buildings[building] = tuple(on_board.get(building, ()))
        elif condition.kind in (victory.KIND_HEX_CONTROL, victory.KIND_SOLE_OCCUPANT):
            hexes.extend(victory.group_hexes(engine.scenario, engine.board, params.get("groups", [])))
    return Objectives(tuple(sorted(buildings.items())), tuple(sorted(set(hexes))))


# The static reads of a board, made once for each board. A board does not change after
# it is built, and the key holds the board itself, so a new board with the id of an old
# one that was freed does not read the old entry. The profile of the review of 2026-09-23
# gave `buildings_on` and the terrain planes about four tenths of an observation.
_BUILDINGS: dict[int, tuple[Board, Mapping[str, tuple[HexRef, ...]]]] = {}
_TERRAIN: dict[tuple[int, Spaces], tuple[Board, np.ndarray]] = {}
_CACHE_LIMIT = 16


def _buildings_of(board: Board) -> Mapping[str, tuple[HexRef, ...]]:
    """`victory.buildings_on` of the board, from the memo."""
    from slcore.rules.victory import buildings_on

    entry = _BUILDINGS.get(id(board))
    if entry is None or entry[0] is not board:
        if len(_BUILDINGS) >= _CACHE_LIMIT:
            _BUILDINGS.clear()
        entry = (board, buildings_on(board))
        _BUILDINGS[id(board)] = entry
    return entry[1]


def _terrain_planes(board: Board, spaces: Spaces) -> np.ndarray:
    """The planes of the terrain features, with each other plane zero, as a new array."""
    key = (id(board), spaces)
    entry = _TERRAIN.get(key)
    if entry is None or entry[0] is not board:
        if len(_TERRAIN) >= _CACHE_LIMIT:
            _TERRAIN.clear()
        planes = np.zeros(spaces.board_shape, dtype=np.float32)
        kinds = {name: i for i, name in enumerate(TERRAIN_KINDS)}
        base = len(TERRAIN_KINDS)
        for h in board:
            col, row = h.ref
            index = kinds.get(h.terrain)
            if index is not None:
                planes[index, col, row] = 1.0
            planes[base + 0, col, row] = 1.0 if h.road else 0.0
            planes[base + 1, col, row] = 1.0 if h.building is not None else 0.0
            planes[base + 2, col, row] = 1.0 if h.sewer else 0.0
            planes[base + 3, col, row] = float(h.elevation) / 3.0
        planes.setflags(write=False)
        entry = (board, planes)
        _TERRAIN[key] = entry
    return entry[1].copy()


def _seen_control(state: State, board: Board, building_id: str, player: int, viewer: int) -> bool:
    """Whether this viewer sees `player` holding the building.

    A hidden or concealed enemy does not change the plane. The victory rule still
    counts that unit. This read is only the observation.
    """
    from slcore.view import visible_to

    hexes = _buildings_of(board).get(building_id, ())
    for h in hexes:
        for unit in state.infantry_in(h):
            if unit.player == player:
                continue
            if unit.player == viewer or visible_to(state, unit, viewer):
                return False
    if player != viewer:
        return any(
            visible_to(state, unit, viewer) and unit.player == player
            for h in hexes
            for unit in state.infantry_in(h)
        )
    return dict(state.last_occupant).get(building_id) == player


def _seen_hex(state: State, hex_ref: HexRef, player: int, viewer: int) -> bool:
    """The same rule as `_seen_control`, for one hex the card names."""
    from slcore.view import visible_to

    if state.in_melee(hex_ref):
        return False
    for unit in state.infantry_in(hex_ref):
        if unit.player == player:
            continue
        if unit.player == viewer or visible_to(state, unit, viewer):
            return False
    if player != viewer:
        return any(visible_to(state, unit, viewer) and unit.player == player for unit in state.infantry_in(hex_ref))
    return dict(state.hex_occupant).get(geometry.hex_id(*hex_ref)) == player


def board_tensor(
    board: Board,
    state: State,
    types: Mapping[str, UnitType],
    player: int,
    spaces: Spaces,
    objectives: Objectives | None = None,
) -> np.ndarray:
    """The board as planes, from what this player is allowed to know.

    A unit below a concealment counter of the other side is not in the unit planes. Its
    hex has the counter plane set, which is what the player sees on the table (rule 25.2).
    `objectives` gives the buildings the victory conditions name, and the planes then say
    which of them this player holds and which the other side holds, from the evaluator's
    own control reading.
    """
    from slcore.view import visible_to

    planes = _terrain_planes(board, spaces)
    base = len(TERRAIN_KINDS) + 4
    for unit in state.units:
        if unit.eliminated or unit.hex is None or unit.carrier is not None:
            continue
        if unit.player != player and not visible_to(state, unit, player):
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
    base += 4
    if state.fire_group is not None:
        target = state.fire_group.target
        planes[base, target[0], target[1]] = 1.0
    if objectives is not None:
        for building, hexes in objectives.buildings:
            mine = _seen_control(state, board, building, player, player)
            theirs = _seen_control(state, board, building, 1 - player, player)
            for col, row in hexes:
                planes[base + 1, col, row] = 1.0
                planes[base + 2, col, row] = 1.0 if mine else 0.0
                planes[base + 3, col, row] = 1.0 if theirs else 0.0
        for col, row in objectives.hexes:
            planes[base + 1, col, row] = 1.0
            planes[base + 2, col, row] = 1.0 if _seen_hex(state, (col, row), player, player) else 0.0
            planes[base + 3, col, row] = 1.0 if _seen_hex(state, (col, row), 1 - player, player) else 0.0
    return planes


def unit_tensor(
    state: State,
    types: Mapping[str, UnitType],
    player: int,
    spaces: Spaces,
    board: Board,
    legal_units: Sequence[int] | None = None,
) -> np.ndarray:
    """One row for each unit slot. Slot 0 is the side, and it stays zero.

    `legal_units` is the unit slots with a legal command in this frame, from the legal
    list the core gave, so a row says whether its unit can still act in this phase.
    """
    rows = np.zeros(spaces.unit_shape, dtype=np.float32)
    from slcore.view import visible_to

    group = state.fire_group
    members = {member[0] for member in group.members} if group is not None else set()
    leader = group.leader if group is not None else None
    legal = set(legal_units) if legal_units is not None else set()
    for unit in state.units:
        slot = unit.id + 1
        if slot >= spaces.units:
            continue
        if unit.eliminated:
            continue
        if unit.player != player and not visible_to(state, unit, player):
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
        row[26] = 1.0 if unit.id in members else 0.0
        row[27] = 1.0 if unit.id == leader else 0.0
        row[28] = 1.0 if slot in legal else 0.0
        row[29] = 1.0 if unit.stay else 0.0
        row[30] = 1.0 if unit.routed else 0.0
        row[31] = 1.0 if unit.directed else 0.0
        row[32] = 1.0 if unit.rally_tried else 0.0
        row[33] = 1.0 if unit.malfunction else 0.0
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


def position_key(state: State) -> str:
    """The state without its command count, so a cycle of commands shows as a repeat.

    The core's hash counts the commands (`seq`), so no two states of a game share it. A
    pickup and a drop give the position before them with a count two higher. This key is
    that position. The environment reads it to stop a cycle, and the learned agent reads it
    to keep out of one.

    The core makes the key from the JSON text it keeps for each unit, which is the text
    of `json.dumps` of the state document without `seq` (NFR-01).
    """
    return core_position_key(state)
