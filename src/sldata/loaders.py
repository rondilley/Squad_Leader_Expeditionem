"""Loaders for the data files. This is a file boundary, so errors are typed."""

from __future__ import annotations

from dataclasses import replace

import json
from importlib import resources
from pathlib import Path
from typing import Any

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
    return _parse(text, relative)


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
        return scenario_from_dict(read_json_file(path))
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
        return Board.from_dict(read_json_file(path), terrain)
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
