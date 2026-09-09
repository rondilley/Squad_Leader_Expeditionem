"""Each scenario in the data directory builds a board and sets up (FR-19, FR-21).

A change to the generator changes each board, and a scenario asks its board for buildings in
a band of columns. So a generator change can leave a scenario with no board it can use, and
that failure showed up in twenty places across the suite the first two times it happened.

This test is the one place it should show up. It reads the directory, so a scenario added
later is covered without a change here.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slcore.engine import Engine
from slcore.scenario import scenario_from_dict
from sldata.loaders import (
    board_and_parameters,
    load_all_counters,
    load_hexsides,
    load_scenario,
    load_tables,
    load_terrain,
)

TERRAIN = load_terrain()
HEXSIDES = load_hexsides()
COUNTERS = load_all_counters()
TABLES = load_tables()
DIRECTORY = Path("src") / "sldata" / "scenarios"
NAMES = sorted(p.stem for p in DIRECTORY.glob("*.json"))


def test_the_directory_holds_the_scenarios_this_build_ships():
    assert NAMES, "no scenario data file was found"
    for expected in ("s01_guards_counterattack", "s02_tractor_works", "s03a_streets_of_stalingrad"):
        assert expected in NAMES


@pytest.mark.parametrize("name", NAMES)
def test_a_scenario_builds_its_board_and_its_set_up(name: str):
    scenario = load_scenario(name)
    board, params = board_and_parameters(scenario, TERRAIN)
    engine = Engine(scenario, board, TERRAIN, HEXSIDES, COUNTERS, TABLES)
    state = engine.new_game(3)
    assert state.units, f"{name} put no unit in the game"
    for side in engine.scenario.sides:
        for group in side.groups:
            assert group.area.resolve(board), f"{name}: {group.id} has an empty set up area"


@pytest.mark.parametrize("name", NAMES)
def test_a_scenario_stays_inside_its_retry_budget(name: str):
    """A scenario whose seed needs more retries than its budget is a scenario that fails.

    The test asks for the seed the scenario names and counts what the generator used. A
    margin below the budget leaves room for the next change to the generator.
    """
    document = json.loads((DIRECTORY / f"{name}.json").read_text(encoding="utf-8"))
    asked = document.get("board_generator", {}).get("seed")
    if asked is None:
        pytest.skip(f"{name} has no single generator record")
    scenario = load_scenario(name)
    _, params = board_and_parameters(scenario, TERRAIN)
    used = params.seed - asked
    budget = scenario.board_retries
    assert used < budget, f"{name} used {used} retries of a budget of {budget}"
    assert used <= budget - 8, f"{name} used {used} retries, which leaves less than eight in hand"
