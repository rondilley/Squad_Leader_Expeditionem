"""The public surface of the rules core (AR-05, M4).

This module is the contract for the port of the core to Rust. A consumer (the host, the
agents, the trainer, the board generator, the loaders, the windows, the command line)
reads the core only through the names below. The Rust port gives each of them, with the
same behaviour, and it is free to change all else in the core.

The centre of the contract is the `Engine` and its three public functions:

- `Engine.legal_commands(state)` gives the decision frame of a state.
- `Engine.apply(state, command, frame)` gives the next state and its events.
- `Engine.hash_state(state)` gives the hash of a state.

Around it are the data types the engine reads and gives (`State`, `DecisionFrame`,
`Command`, `Event`, the scenario, the board, the units, and the tables), the per-player
view (`view.build`, `view.visible_to`, `view.event_visible`, `player_state.for_player`),
the seeded generator of `slcore.rng`, the lattice of `slcore.geometry`, and the rule
helpers that the scripted agents and the odds read with no die.

`SURFACE` names each submodule of the contract and the names of it that a consumer may
read. `tests/arch/test_core_api.py` holds each import of `slcore` outside the core to
this table, so a new coupling to the core is a test failure and a decision, not an
accident. To add a name, add it here with the cause in the change.
"""

from __future__ import annotations

from slcore import __version__, geometry, hashing, los_cache, los_eval, player_state, scenario, view
from slcore.commands import Command
from slcore.engine import Engine, IllegalCommand
from slcore.events import Event
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import (
    PHASE_ADVANCE,
    PHASE_ADVANCING_FIRE,
    PHASE_CLOSE_COMBAT,
    PHASE_DEFENSIVE_FIRE,
    PHASE_MOVEMENT,
    PHASE_PREP_FIRE,
    PHASE_RALLY,
    PHASE_ROUT,
    PHASE_SETUP,
    PLAYER_TURN_PHASES,
    FireGroup,
    Smoke,
    State,
)
from slcore.geometry import VERTEX_OFFSETS, HexRef, Point
from slcore.player_state import for_player
from slcore.rng import RngState, choice_index, seed_state
from slcore.rules import (
    r05_movement,
    r06_stacking,
    r08_fire,
    r10_resolution,
    r11_terrain,
    r12_morale,
    r13_rout,
    r14_rally,
    r15_leadership,
    r20_close_combat,
    r22_flamethrower,
    r23_demolition,
    r24_smoke,
    r25_concealment,
    r26_fanaticism,
    r28_vehicles,
    r30_vehicle_movement,
    r34_afv_vs_infantry,
    r37_at_weapons,
    victory,
)
from slcore.scenario import Group, Scenario, SetupArea, SideSpec, UnitEntry, VictoryCondition, scenario_from_dict
from slcore.state import Board, Building, Hex, HexsideRule, Polygon, TerrainType, hexside_table_from_dict, terrain_table_from_dict
from slcore.tabledata import (
    RESULT_KIA,
    RESULT_MC,
    RESULT_NONE,
    ArmorTables,
    CcTable,
    IftTable,
    Tables,
    VehicleMovement,
    armor_from_dict,
    cc_from_dict,
    ift_from_dict,
    vehicle_movement_from_dict,
)
from slcore.units import CLASS_TANK, KIND_CREW, KIND_LEADER, KIND_SQUAD, KIND_SW, KIND_VEHICLE, Unit, UnitType, counter_types_from_dict
from slcore.view import SPECTATOR, board_document, event_visible, nationalities_of, visible_to

# The submodules of the contract and the names of each that a consumer may read.
SURFACE: dict[str, tuple[str, ...]] = {
    "slcore": ("__version__",),
    "slcore.commands": ("Command",),
    "slcore.engine": ("Engine", "IllegalCommand"),
    "slcore.events": ("Event",),
    "slcore.frame": ("DecisionFrame", "LegalCommand"),
    "slcore.game": (
        "FireGroup",
        "PHASE_ADVANCE",
        "PHASE_ADVANCING_FIRE",
        "PHASE_CLOSE_COMBAT",
        "PHASE_DEFENSIVE_FIRE",
        "PHASE_MOVEMENT",
        "PHASE_PREP_FIRE",
        "PHASE_RALLY",
        "PHASE_ROUT",
        "PHASE_SETUP",
        "PLAYER_TURN_PHASES",
        "Smoke",
        "State",
    ),
    "slcore.geometry": (
        "COL_STEP",
        "HexRef",
        "Point",
        "VERTEX_OFFSETS",
        "center",
        "column_index",
        "column_label",
        "direction_to",
        "distance",
        "hex_id",
        "neighbor",
        "neighbors",
        "normalize_polygon",
        "parse_hex_id",
    ),
    # The position key of a state without its sequence number: the repeat guard of the
    # learned agent reads it (2026-09-23).
    "slcore.hashing": ("position_key",),
    # The static line of sight table of a board. The bench and the worker pools fill it
    # one time in the parent and share the snapshot (the perf pass of 2026-09-23). A port
    # that keeps the cache inside the core gives these as no-op calls.
    "slcore.los_cache": ("board_fingerprint", "load_static", "static_snapshot", "warm_static"),
    "slcore.los_eval": ("evaluate",),
    "slcore.player_state": ("for_player",),
    "slcore.rng": ("RngState", "choice_index", "seed_state"),
    "slcore.scenario": (
        "Group",
        "Scenario",
        "SetupArea",
        "SideSpec",
        "UnitEntry",
        "VictoryCondition",
        "band_text",
        "in_band",
        "near_band",
        "scenario_from_dict",
    ),
    "slcore.state": (
        "Board",
        "Building",
        "Hex",
        "HexsideRule",
        "Polygon",
        "TerrainType",
        "hexside_table_from_dict",
        "terrain_table_from_dict",
    ),
    "slcore.tabledata": (
        "ArmorTables",
        "CcTable",
        "IftTable",
        "RESULT_KIA",
        "RESULT_MC",
        "RESULT_NONE",
        "Tables",
        "VehicleMovement",
        "armor_from_dict",
        "cc_from_dict",
        "ift_from_dict",
        "vehicle_movement_from_dict",
    ),
    "slcore.units": (
        "CLASS_TANK",
        "KIND_CREW",
        "KIND_LEADER",
        "KIND_SQUAD",
        "KIND_SW",
        "KIND_VEHICLE",
        "Unit",
        "UnitType",
        "counter_types_from_dict",
    ),
    "slcore.view": ("SPECTATOR", "board_document", "build", "event_visible", "nationalities_of", "visible_to"),
    # The rule helpers that the scripted agents, the odds, and the reward read with no die.
    "slcore.rules.r05_movement": ("entry_cost_halves",),
    "slcore.rules.r06_stacking": ("LIMIT_SQUADS", "overstacked_hexes", "rule_6_1_overstacked"),
    "slcore.rules.r08_fire": ("can_fire_inherent", "can_fire_weapon", "group_firepower", "member_firepower"),
    "slcore.rules.r10_resolution": ("common_modifier", "enemy_occupied_hexes", "rural_halves"),
    "slcore.rules.r11_terrain": ("is_open_ground", "moving_in_open_modifier", "target_hex_modifier"),
    "slcore.rules.r12_morale": ("BERSERK_ROLL", "RUSSIAN", "morale_value"),
    "slcore.rules.r13_rout": ("hopeless", "is_cover"),
    "slcore.rules.r14_rally": ("DESPERATION_PENALTY", "SELF_CASUALTY_ROLL"),
    "slcore.rules.r15_leadership": ("modifier_for_check",),
    "slcore.rules.r20_close_combat": ("firepower",),
    # Who may use a flamethrower and a charge, and the odds of each (2026-09-24 and 2026-09-25).
    "slcore.rules.r22_flamethrower": ("halves", "in_range", "is_flamethrower", "may_operate"),
    "slcore.rules.r23_demolition": ("MALFUNCTION_ROLL", "can_place", "halves", "is_charge", "may_place"),
    "slcore.rules.r24_smoke": ("blocks_path",),
    "slcore.rules.r25_concealment": ("halves_for",),
    "slcore.rules.r26_fanaticism": ("modifier_for",),
    "slcore.rules.r28_vehicles": ("facing_towards", "in_covered_arc", "vehicle_in"),
    # The route and the firing positions of the armor policy (`slagents/scripted/armor.py`,
    # 2026-10-10): the entry cost of a hex, the stops of rule 30.8, and the AT weapons.
    "slcore.rules.r30_vehicle_movement": ("enemy_infantry_in", "enemy_vehicle_in", "entry_cost_halves", "must_leave"),
    "slcore.rules.r34_afv_vs_infantry": ("firepower_halves",),
    "slcore.rules.r37_at_weapons": ("anti_tank_weapons",),
    "slcore.rules.victory": (
        "KIND_BUILDING_COUNT",
        "KIND_BUILDING_SWING",
        "KIND_HEX_CONTROL",
        "KIND_SOLE_OCCUPANT",
        "buildings_on",
        "controlled_by",
        "evaluate",
        "group_buildings",
        "group_hexes",
        "hex_controlled_by",
    ),
}

__all__ = [
    "SURFACE",
    "__version__",
    # The submodules a consumer reads by attribute.
    "geometry",
    "hashing",
    "los_cache",
    "los_eval",
    "player_state",
    "scenario",
    "view",
    "r05_movement",
    "r06_stacking",
    "r08_fire",
    "r10_resolution",
    "r11_terrain",
    "r12_morale",
    "r13_rout",
    "r14_rally",
    "r15_leadership",
    "r20_close_combat",
    "r22_flamethrower",
    "r23_demolition",
    "r24_smoke",
    "r25_concealment",
    "r26_fanaticism",
    "r28_vehicles",
    "r30_vehicle_movement",
    "r34_afv_vs_infantry",
    "r37_at_weapons",
    "victory",
    # The engine and its data types.
    "Command",
    "DecisionFrame",
    "Engine",
    "Event",
    "IllegalCommand",
    "LegalCommand",
    "State",
    "FireGroup",
    "Smoke",
    "PHASE_ADVANCE",
    "PHASE_ADVANCING_FIRE",
    "PHASE_CLOSE_COMBAT",
    "PHASE_DEFENSIVE_FIRE",
    "PHASE_MOVEMENT",
    "PHASE_PREP_FIRE",
    "PHASE_RALLY",
    "PHASE_ROUT",
    "PHASE_SETUP",
    "PLAYER_TURN_PHASES",
    # The lattice and the seeded generator.
    "HexRef",
    "Point",
    "VERTEX_OFFSETS",
    "RngState",
    "choice_index",
    "seed_state",
    # The per-player view.
    "SPECTATOR",
    "board_document",
    "event_visible",
    "for_player",
    "nationalities_of",
    "visible_to",
    # The scenario, the board, the units, and the tables, with their readers.
    "Group",
    "Scenario",
    "SetupArea",
    "SideSpec",
    "UnitEntry",
    "VictoryCondition",
    "scenario_from_dict",
    "Board",
    "Building",
    "Hex",
    "HexsideRule",
    "Polygon",
    "TerrainType",
    "hexside_table_from_dict",
    "terrain_table_from_dict",
    "CLASS_TANK",
    "KIND_CREW",
    "KIND_LEADER",
    "KIND_SQUAD",
    "KIND_SW",
    "KIND_VEHICLE",
    "Unit",
    "UnitType",
    "counter_types_from_dict",
    "ArmorTables",
    "CcTable",
    "IftTable",
    "RESULT_KIA",
    "RESULT_MC",
    "RESULT_NONE",
    "Tables",
    "VehicleMovement",
    "armor_from_dict",
    "cc_from_dict",
    "ift_from_dict",
    "vehicle_movement_from_dict",
]
