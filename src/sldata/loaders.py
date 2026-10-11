"""Loaders for the data files. This is a file boundary, so errors are typed."""

from __future__ import annotations

from dataclasses import dataclass, replace

import json
from importlib import resources
from pathlib import Path
from typing import Any, Mapping

from slboards.compose import CompositionError, Placement, compose
from slboards.generator import GeneratorError, GeneratorParameters, generate_with_retry
from slcore.scenario import Scenario, scenario_from_dict
from slcore.state import Board, HexsideRule, TerrainType, hexside_table_from_dict, terrain_table_from_dict
from slcore.tabledata import (
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
from slcore.units import UnitType, counter_types_from_dict

NATIONALITIES = ("german", "russian", "american")


class DataError(Exception):
    """A data file is missing or not valid."""


class DataKeyError(DataError):
    """A data file holds a key that no reader of its kind reads (M2).

    A misspelled key (`hidden_placment`) is not an error for a reader that uses `get` with
    a default, so the scenario played with no hidden placement and no message. The closed
    key sets below give the error at the load, with the file and the key.
    """

    def __init__(self, label: str, path: str, key: str, known: Any) -> None:
        self.file = label
        self.path = path
        self.key = key
        super().__init__(
            f"data file {label} has the unknown key {key!r} at {path}; "
            f"the known keys there are {', '.join(sorted(known))}"
        )


# The closed key sets (M2). Each set holds the keys that the reader of the kind reads (the
# `*_from_dict` functions of the core, the generator, the victory rules, the campaign, the
# provider table), and the keys that only document a row: `note`, `what`, `rule`,
# `provenance`, `version`, `table`. A spec is one of these:
#
# - `Keys({...})`: an object with these keys only, each with the spec of its value.
# - `Each(spec)`: a list, each item with the spec.
# - `Values(spec)`: an object with free keys (a table row name), each value with the spec.
# - `ByKind(common, kinds)`: an object whose `kind` picks its keys (the victory conditions).
# - `None`: a value with no key check (text, numbers, a list of numbers, a free mapping).


@dataclass(frozen=True)
class Keys:
    fields: Mapping[str, Any]


@dataclass(frozen=True)
class Each:
    item: Any


@dataclass(frozen=True)
class Values:
    item: Any


@dataclass(frozen=True)
class ByKind:
    common: Mapping[str, Any]
    kinds: Mapping[str, Mapping[str, Any]]


_DOCUMENT = {"table": None, "version": None, "provenance": None, "note": None, "notes": None}

# The band keys of `slcore.scenario.in_band` and `near_band`.
_BAND = {"min_col": None, "max_col": None, "min_row": None, "max_row": None}
NEAR_KEYS = Keys({**_BAND, "max_distance": None})

# A set up area: `_area_from_dict` reads `building`, `hexes`, and `zone`, and each other key
# is a parameter that `resolve_zone`, `resolve_columns`, `resolve_edge`, and `zone_filter` read.
AREA_KEYS = Keys(
    {
        "building": None,
        "hexes": None,
        "zone": None,
        **_BAND,
        "near": NEAR_KEYS,
        "terrain": None,
        "not_terrain": None,
        "road": None,
        "level": None,
        "side": None,
        "depth": None,
        "max_hexes": None,
        "min_hexes": None,
        "rank": None,
    }
)

# `slboards.generator.ZoneConstraint.from_dict` and `GeneratorParameters.from_dict`.
ZONE_KEYS = Keys({"count": None, "min_hexes": None, "max_hexes": None, **_BAND, "near": NEAR_KEYS})
_GENERATOR = {
    "seed": None,
    "board_type": None,
    "cols": None,
    "rows": None,
    "version": None,
    "building_density": None,
    "style": None,
    "zones": Each(ZONE_KEYS),
}
GENERATOR_KEYS = Keys(_GENERATOR)

# `slcore.rules.victory.evaluate` and the agents that read a condition.
VICTORY_KEYS = ByKind(
    {"kind": None, "side": None, "note": None},
    {
        "building_swing": {"enemy_groups": None, "own_groups": None, "margin": None},
        "unbroken_squad_ratio": {"numerator": None, "denominator": None},
        "building_count": {"groups": None, "count": None},
        "hex_control": {"groups": None, "count": None},
        "sole_occupant": {"groups": None},
        "force_eliminated": {},
        "casualty_exchange": {"margin": None},
    },
)

# `slcore.scenario.scenario_from_dict`.
SCENARIO_KEYS = Keys(
    {
        "id": None,
        "title": None,
        "board": None,
        "turns": None,
        "first_mover": None,
        "setup_order": None,
        "sides": Each(
            Keys(
                {
                    "side": None,
                    "nationality": None,
                    "groups": Each(
                        Keys(
                            {
                                "id": None,
                                "units": Each(Keys({"type": None, "count": None, "name": None})),
                                "area": AREA_KEYS,
                                "objective": None,
                                "setup_pass": None,
                                "nationality": None,
                            }
                        )
                    ),
                }
            )
        ),
        "rules_used": None,
        "switches": None,
        "victory": Each(VICTORY_KEYS),
        "objectives": None,
        "board_generator": GENERATOR_KEYS,
        "board_composition": Keys({"side": None, "boards": Each(Keys({**_GENERATOR, "turned": None}))}),
        "board_columns": None,
        "board_retries": None,
        "first_mover_roll": None,
        "smoke_counters": None,
        "concealment_counters": None,
        "hidden_placement": Keys({"side": None, "note": None}),
        "fanatic": Keys({"side": None, "area": AREA_KEYS}),
        "notes": None,
<<<<<<< Updated upstream
=======
        # The text for the players on the scenario card; the notes are the provenance.
        "situation": None,
>>>>>>> Stashed changes
    }
)

# `slcore.units.counter_types_from_dict`. `count` is the count on the countersheet and
# `leaders` the names of the leader counters; no reader reads them, and they document the set.
COUNTER_ROW_KEYS = Keys(
    {
        "kind": None,
        "fp": None,
        "range": None,
        "morale": None,
        "broken_morale": None,
        "leadership": None,
        "breakdown": None,
        "penetration": None,
        "pp_squad": None,
        "pp_leader": None,
        "pp_squad_half": None,
        "pp_leader_half": None,
        "elite": None,
        "assault_engineer": None,
        "weapon_class": None,
        "heavy": None,
        "vehicle_class": None,
        "mp": None,
        "gun": None,
        "gun_he_only": None,
        "gun_low_velocity": None,
        "mg_ca": None,
        "mg_360": None,
        "survival": None,
        "armor_key": None,
        "open_top": None,
        "fires_twice": None,
        "transport_pp": None,
        "canister": None,
        "heat": None,
        "quad_fifty": None,
        "count": None,
        "note": None,
    }
)
COUNTERS_KEYS = Keys(
    {**_DOCUMENT, "nationality": None, "types": Values(COUNTER_ROW_KEYS), "leaders": Each(Keys({"name": None, "type": None}))}
)

# `slcore.state.Board.from_dict`, and the `generator` record that `sl-cli boards --write` adds.
BOARD_KEYS = Keys(
    {
        **_DOCUMENT,
        "name": None,
        "cols": None,
        "rows": None,
        "generator": GENERATOR_KEYS,
        "hexes": Each(
            Keys(
                {
                    "id": None,
                    "terrain": None,
                    "elevation": None,
                    "road": None,
                    "road_sides": None,
                    "building": Keys({"id": None, "kind": None, "size": None}),
                    "hexsides": None,
                    "sewer": None,
                    "stairs": None,
                    "polygons": Each(Keys({"kind": None, "points": None})),
                }
            )
        ),
    }
)

# `slcore.state.terrain_table_from_dict` and `hexside_table_from_dict`. The `road` row
# documents the road costs that rule 5 holds in code.
TERRAIN_KEYS = Keys(
    {
        **_DOCUMENT,
        "terrain": Values(Keys({"tem": None, "mf_halves": None, "los": None, "building": None, "note": None})),
        "hexsides": Values(Keys({"tem": None, "mf_extra_halves": None, "los": None, "passable": None, "note": None})),
        "road": Keys({"mf_halves_from_other_hexside": None, "mf_halves_from_road_hexside": None, "note": None}),
    }
)

# `slcore.tabledata.ift_from_dict`. The `modifiers` rows document the modifiers that rules
# 8 and 10 hold in code.
IFT_KEYS = Keys(
    {
        **_DOCUMENT,
        "columns": None,
        "rows": None,
        "row_below_2": None,
        "modifiers": Values(Keys({"multiplier": None, "drm": None, "note": None, "rule": None})),
    }
)

# `slcore.tabledata.cc_from_dict`.
CLOSE_COMBAT_KEYS = Keys({**_DOCUMENT, "odds": Each(Keys({"label": None, "attack": None, "defense": None, "kill": None}))})

_ARMOR_PART = {"note": None, "rule": None}
_HANDHELD = Keys({**_ARMOR_PART, "ranges": None, "prep_or_defensive_fire": None, "advancing_fire_after_movement": None})

# `slcore.tabledata.armor_from_dict`.
ARMOR_KEYS = Keys(
    {
        **_DOCUMENT,
        "to_hit": Keys(
            {
                **_ARMOR_PART,
                "ranges": Each(Keys({"low": None, "high": None})),
                "rows": Each(Keys({"target": None, "default": None, "russian": None, "what": None})),
            }
        ),
        "hit_modifiers": Keys({**_ARMOR_PART, "cases": Each(Keys({"case": None, "modifier": None, "what": None}))}),
        "kill_number_modifiers": Keys({**_ARMOR_PART, "vehicles": Each(Keys({"vehicle": None, "drm": None}))}),
        "kill_table": Keys(
            {
                **_ARMOR_PART,
                "weapons": Each(Keys({"weapon": None, "ammunition": None, "what": None})),
                "rows": Each(Keys({"target": None, "kill": None, "what": None})),
            }
        ),
        "pre_afv_attack": Keys({**_ARMOR_PART, "rows": Each(Keys({"location": None, "roll": None, "what": None}))}),
        "panzerfaust_to_hit": _HANDHELD,
        "bazooka_to_hit": _HANDHELD,
        "gun_columns": Keys(
            {**_ARMOR_PART, "guns": Each(Keys({"calibre": None, "kill_ap": None, "kill_he": None, "firepower": None}))}
        ),
    }
)

# `slcore.tabledata.vehicle_movement_from_dict`. The `rules` rows and `replaces_terrain`
# document the rules of rule 30 that the code holds.
_VEHICLE_COST = {"afv": None, "truck": None, "note": None}
VEHICLE_MOVEMENT_KEYS = Keys(
    {
        **_DOCUMENT,
        "terrain": Values(Keys({**_VEHICLE_COST, "breakdown": None, "no_halftrack": None})),
        "hexsides": Values(Keys(_VEHICLE_COST)),
        "extra": Values(Keys({**_VEHICLE_COST, "replaces_terrain": None})),
        "rules": None,
    }
)

# `slcampaign.campaign.load_rules`.
CAMPAIGN_KEYS = Keys(
    {
        **_DOCUMENT,
        "ranks": Each(Keys({"name": None, "title": None, "morale": None, "leadership": None})),
        "elan": Each(Keys({"id": None, "points": None, "what": None, "awaits": None})),
        "cowardice": Each(Keys({"id": None, "points": None, "what": None})),
        "promotion_threshold": None,
        "scenarios_in_a_campaign": None,
    }
)

# `load_qa_rulings`, `load_project_rulings`, and `tests/conformance/test_rulings.py`.
QA_RULINGS_KEYS = Keys(
    {**_DOCUMENT, "rulings": Each(Keys({"id": None, "rule": None, "summary": None, "status": None, "modeled": None, "cases": None}))}
)
PROJECT_RULINGS_KEYS = Keys(
    {**_DOCUMENT, "rulings": Each(Keys({"id": None, "ruling": None, "cause": None, "decided": None, "extends": None}))}
)

# `slagents.prompted.providers.base.ProviderConfig.from_dict`. `request` is a free mapping
# that the adapter adds to each request.
PROVIDERS_KEYS = Keys(
    {
        **_DOCUMENT,
        "allowlist": None,
        "providers": Each(
            Keys(
                {
                    "name": None,
                    "kind": None,
                    "endpoint": None,
                    "model": None,
                    "key": None,
                    "health": None,
                    "version": None,
                    "timeout_seconds": None,
                    "tier": None,
                    "request": None,
                }
            )
        ),
    }
)

TABLE_KEYS: dict[str, Keys] = {
    "terrain": TERRAIN_KEYS,
    "ift": IFT_KEYS,
    "close_combat": CLOSE_COMBAT_KEYS,
    "armor": ARMOR_KEYS,
    "vehicle_movement": VEHICLE_MOVEMENT_KEYS,
    "campaign": CAMPAIGN_KEYS,
}


def keys_for(relative: str) -> Any:
    """The closed key set of a data file of the package, by its path inside `sldata`.

    A path of no known kind gives None. The test of the data files holds each file of the
    package to a kind, so a new kind of file gets its key set in the same change.
    """
    path = relative.replace("\\", "/")
    folder, _, name = path.rpartition("/")
    stem = name[: -len(".json")] if name.endswith(".json") else name
    if folder == "scenarios":
        return SCENARIO_KEYS
    if folder == "counters":
        return COUNTERS_KEYS
    if folder == "boards":
        return BOARD_KEYS
    if folder == "tables":
        return TABLE_KEYS.get(stem)
    if path == "rulings/qa.json":
        return QA_RULINGS_KEYS
    if path == "rulings/project.json":
        return PROJECT_RULINGS_KEYS
    if path == "providers.json":
        return PROVIDERS_KEYS
    return None


def check_keys(value: Any, spec: Any, label: str, path: str = "$") -> None:
    """Raise `DataKeyError` for the first key of `value` that `spec` does not hold.

    The check is of the keys only. A value of the wrong type is the reader's error, which
    each loader turns into a `DataError` of its own.
    """
    if spec is None:
        return
    if isinstance(spec, Keys):
        if not isinstance(value, Mapping):
            return
        for key, item in value.items():
            if key not in spec.fields:
                raise DataKeyError(label, path, str(key), spec.fields)
            check_keys(item, spec.fields[key], label, f"{path}.{key}")
    elif isinstance(spec, Each):
        if isinstance(value, list):
            for index, item in enumerate(value):
                check_keys(item, spec.item, label, f"{path}[{index}]")
    elif isinstance(spec, Values):
        if isinstance(value, Mapping):
            for key, item in value.items():
                check_keys(item, spec.item, label, f"{path}.{key}")
    elif isinstance(spec, ByKind):
        if not isinstance(value, Mapping):
            return
        kind = value.get("kind")
        if kind not in spec.kinds:
            raise DataError(
                f"data file {label} has the unknown kind {kind!r} at {path}; "
                f"the known kinds are {', '.join(sorted(spec.kinds))}"
            )
        check_keys(value, Keys({**spec.common, **spec.kinds[kind]}), label, path)
    else:
        raise TypeError(f"no key set of type {type(spec).__name__}")


def _parse(text: str, label: str) -> dict[str, Any]:
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise DataError(f"data file {label} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise DataError(f"data file {label} must hold a JSON object")
    return data


def _read_json(relative: str) -> dict[str, Any]:
    ref = resources.files("sldata").joinpath(relative)
    try:
        with ref.open("r", encoding="utf-8") as fh:
            text = fh.read()
    except FileNotFoundError as exc:
        raise DataError(f"data file not found: {relative}") from exc
    except OSError as exc:
        raise DataError(f"cannot read data file {relative}: {exc}") from exc
    data = _parse(text, relative)
    check_keys(data, keys_for(relative), relative)
    return data


def read_data(relative: str) -> dict[str, Any]:
    """One data file of the package, by its path inside `sldata`."""
    return _read_json(relative)


def read_json_file(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise DataError(f"file not found: {p}") from exc
    except OSError as exc:
        raise DataError(f"cannot read {p}: {exc}") from exc
    return _parse(text, str(p))


def load_terrain_document() -> dict[str, Any]:
    return _read_json("tables/terrain.json")


def load_terrain() -> dict[str, TerrainType]:
    """The terrain table (rules 5.5, 7.2, 11.1)."""
    try:
        return terrain_table_from_dict(load_terrain_document())
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"terrain table is not valid: {exc}") from exc


def load_hexsides() -> dict[str, HexsideRule]:
    """The hexside table (rules 11.2, 11.5)."""
    try:
        return hexside_table_from_dict(load_terrain_document())
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"hexside table is not valid: {exc}") from exc


def load_counters(nationality: str) -> dict[str, UnitType]:
    try:
        return counter_types_from_dict(_read_json(f"counters/{nationality}.json"))
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"counter file for {nationality} is not valid: {exc}") from exc


def load_all_counters() -> dict[str, dict[str, UnitType]]:
    return {n: load_counters(n) for n in NATIONALITIES}


def load_scenario(name: str) -> Scenario:
    try:
        return scenario_from_dict(_read_json(f"scenarios/{name}.json"))
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"scenario {name} is not valid: {exc}") from exc


def load_scenario_file(path: str | Path) -> Scenario:
    try:
        data = read_json_file(path)
        check_keys(data, SCENARIO_KEYS, str(path))
        return scenario_from_dict(data)
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"scenario file {path} is not valid: {exc}") from exc


def load_board(name: str, terrain: dict[str, TerrainType] | None = None) -> Board:
    if terrain is None:
        terrain = load_terrain()
    try:
        return Board.from_dict(_read_json(f"boards/{name}.json"), terrain)
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"board {name} is not valid: {exc}") from exc


def load_board_file(path: str | Path, terrain: dict[str, TerrainType] | None = None) -> Board:
    if terrain is None:
        terrain = load_terrain()
    try:
        data = read_json_file(path)
        check_keys(data, BOARD_KEYS, str(path))
        return Board.from_dict(data, terrain)
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"board file {path} is not valid: {exc}") from exc


def load_ift() -> IftTable:
    """The Infantry Fire Table (rule 10.3)."""
    try:
        return ift_from_dict(_read_json("tables/ift.json"))
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"the infantry fire table is not valid: {exc}") from exc


def load_close_combat() -> CcTable:
    """The Close Combat Table (rule 20.3)."""
    try:
        return cc_from_dict(_read_json("tables/close_combat.json"))
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"the close combat table is not valid: {exc}") from exc


def load_armor() -> ArmorTables:
    """The armor combat tables of rules 33.3, 33.31, 33.4, 33.41, 34.2, 36.12, 37.31, 37.41."""
    try:
        return armor_from_dict(_read_json("tables/armor.json"))
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"the armor tables are not valid: {exc}") from exc


def load_vehicle_movement() -> VehicleMovement:
    """The Vehicle Movement Cost Chart of rule 30."""
    try:
        return vehicle_movement_from_dict(_read_json("tables/vehicle_movement.json"))
    except (KeyError, ValueError, TypeError) as exc:
        raise DataError(f"the vehicle movement chart is not valid: {exc}") from exc


def load_tables() -> Tables:
    return Tables(load_ift(), load_close_combat(), load_armor(), load_vehicle_movement())


def board_for_scenario(scenario: Scenario, terrain: dict[str, TerrainType] | None = None) -> Board:
    """The board of a scenario: from the generator when it names one, else from a data file."""
    board, _ = board_and_parameters(scenario, terrain)
    return board


def _zones_in_the_subset(
    params: GeneratorParameters, columns: tuple[int, int] | None
) -> GeneratorParameters:
    """Put the zone columns of a scenario on the columns of the board the generator makes.

    A scenario that plays on part of a board counts its columns from the first column in
    play, because that is what the hex names on that board say. The generator works on
    the whole board. So a zone column of the scenario moves by the first column of the
    subset, and a zone with no columns of its own gets the whole subset.

    Scenario 1 plays on columns 0 to 15, where the two systems agree. Scenario 2 plays on
    columns 14 to 32, where they do not.
    """
    if columns is None or not params.zones:
        return params
    lo, hi = columns

    def shifted(min_col: int | None, max_col: int | None) -> tuple[int, int]:
        if min_col is None and max_col is None:
            return lo, hi
        low = lo if min_col is None else min(hi, lo + min_col)
        high = hi if max_col is None else min(hi, lo + max_col)
        return low, high

    zones = []
    for z in params.zones:
        low, high = shifted(z.min_col, z.max_col)
        near = z.near
        if near:
            band = dict(near)
            near_low, near_high = shifted(band.get("min_col"), band.get("max_col"))
            band["min_col"] = near_low
            band["max_col"] = near_high
            near = tuple(sorted(band.items()))
        zones.append(replace(z, min_col=low, max_col=high, near=near))
    return replace(params, zones=tuple(zones))


def composition_boards(
    scenario: Scenario, terrain: dict[str, TerrainType]
) -> tuple[Board, list[GeneratorParameters]]:
    """The playing surface of a scenario that uses two to four boards (FR-29).

    The record names a side, `east` or `south`, and one generator record for each board in
    order. A board with `turned` true is turned one hundred and eighty degrees before it
    goes down. Each board satisfies its own zones, so each one retries its own seed.
    """
    record = dict(scenario.board_composition)
    side = str(record.get("side", "east"))
    entries = list(record.get("boards", []))
    if not entries:
        raise DataError(f"scenario {scenario.id} has a composition with no board")
    placements = []
    used: list[GeneratorParameters] = []
    for index, entry in enumerate(entries):
        wanted = dict(entry)
        turned = bool(wanted.pop("turned", False))
        asked = GeneratorParameters.from_dict(wanted)
        try:
            board, params = generate_with_retry(asked, terrain, scenario.board_retries)
        except GeneratorError as exc:
            raise DataError(
                f"board {index + 1} of scenario {scenario.id} cannot be generated: {exc}"
            ) from exc
        placements.append(Placement(board, turned))
        used.append(params)
    try:
        return compose(placements, side, terrain), used
    except CompositionError as exc:
        raise DataError(f"the boards of scenario {scenario.id} do not make one surface: {exc}") from exc


def board_and_parameters(
    scenario: Scenario, terrain: dict[str, TerrainType] | None = None
) -> tuple[Board, GeneratorParameters | None]:
    """The board and the generator record that made it, for the run artifact (FR-25).

    When the seed of the scenario does not satisfy its zones, the generator tries the
    next seeds and gives the record of the one that worked (FR-21).

    A scenario with a composition gives back the composed surface and the record of its
    first board. `composition_boards` gives the record of each board, and the run artifact
    reads that one.
    """
    if terrain is None:
        terrain = load_terrain()
    params: GeneratorParameters | None = None
    if scenario.board_composition:
        board, used = composition_boards(scenario, terrain)
        params = used[0] if used else None
    elif scenario.board_generator:
        asked = GeneratorParameters.from_dict(dict(scenario.board_generator))
        asked = _zones_in_the_subset(asked, scenario.board_columns)
        try:
            board, params = generate_with_retry(asked, terrain, scenario.board_retries)
        except GeneratorError as exc:
            raise DataError(
                f"generated mode is not available for scenario {scenario.id} with seed {asked.seed}: {exc}"
            ) from exc
    else:
        board = load_board(scenario.board, terrain)
    if scenario.board_columns is not None:
        board = board.subset_columns(scenario.board_columns[0], scenario.board_columns[1])
    return board, params


def load_qa_rulings() -> list[dict[str, Any]]:
    data = _read_json("rulings/qa.json")
    rulings = data.get("rulings")
    if not isinstance(rulings, list):
        raise DataError("rulings/qa.json must hold a list under 'rulings'")
    return rulings


def load_project_rulings() -> list[dict[str, Any]]:
    data = _read_json("rulings/project.json")
    rulings = data.get("rulings")
    if not isinstance(rulings, list):
        raise DataError("rulings/project.json must hold a list under 'rulings'")
    return rulings
