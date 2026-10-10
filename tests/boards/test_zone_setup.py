"""O-04 and FR-21: zone set up moves scenario 1 onto a generated city board.

The question O-04 asks is whether zone-based set up areas keep scenario 1 the same game
when the printed layout is not in the repository. The answer these tests give is that it
does, on the condition that the zone says how much room a group needs. Without that
condition the Russian guards draw a three-hex building on some seeds, and twelve squads
do not stack in three hexes.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from slboards.generator import GeneratorParameters, generate
from slcore.engine import Engine
from slcore.geometry import distance
from slcore.scenario import resolve_zone
from sldata.loaders import (
    board_and_parameters,
    load_all_counters,
    load_hexsides,
    load_scenario,
    load_tables,
    load_terrain,
)

TERRAIN = load_terrain()
BASE = load_scenario("s01_guards_counterattack")
HEXSIDES = load_hexsides()
COUNTERS = load_all_counters()
TABLES = load_tables()
SEEDS = 200


def scenario_with_seed(seed: int):
    generator = dict(BASE.board_generator)
    generator["seed"] = seed
    return replace(BASE, board_generator=tuple(sorted(generator.items())))


def build(seed: int):
    scenario = scenario_with_seed(seed)
    board, params = board_and_parameters(scenario, TERRAIN)
    engine = Engine(scenario, board, TERRAIN, HEXSIDES, COUNTERS, TABLES)
    return engine, board, params


def test_two_hundred_seeds_set_up_scenario_one_with_no_error():
    retries = 0
    for seed in range(1, SEEDS + 1):
        engine, board, params = build(seed)
        if params.seed != seed:
            retries += 1
        seen: dict[str, str] = {}
        for side in engine.scenario.sides:
            for group in side.groups:
                building = group.area.building_id(board)
                assert building is not None, f"seed {seed}: {group.id} has no building"
                assert building not in seen, f"seed {seed}: {group.id} shares {building} with {seen[building]}"
                seen[building] = group.id
        assert len(seen) == 10
    # The measured rate on generator version 6 is 25 of 200, and a lower building density
    # does not change it: the limit is how many buildings the eight columns of the band
    # hold, and not how many the generator tries to put there. The bar is above that rate
    # and below a generator that mostly misses, so a regression still shows.
    assert retries <= SEEDS // 5, f"{retries} of {SEEDS} seeds needed a retry, which is too many"


def test_the_largest_russian_group_always_gets_a_building_it_can_stack_in():
    for seed in range(1, 61):
        engine, board, _ = build(seed)
        guards = engine.scenario.group("r_guards")
        hexes = guards.area.resolve(board)
        assert len(hexes) >= 4, f"seed {seed}: twelve squads do not stack in {len(hexes)} hexes"


def test_the_two_sides_set_up_in_their_own_band_of_rows_and_close_together():
    """The card puts the Germans in rows 5 to 9 and each Russian building on top of them.

    The front runs along the rows, and the two sides are two to five hexes apart. The
    earlier column bands put the sides six to twelve hexes apart, and then no attacker
    reached a German building in five turns against a German who fired at range six.
    """
    for seed in range(1, 61):
        engine, board, _ = build(seed)
        german: list[tuple[int, int]] = []
        russian: dict[str, tuple[tuple[int, int], ...]] = {}
        for side in engine.scenario.sides:
            for group in side.groups:
                hexes = group.area.resolve(board)
                north = min(row for _col, row in hexes)
                if side.side == "german":
                    assert 5 <= north <= 9, f"seed {seed}: {group.id} is outside rows 5 to 9"
                    german.extend(hexes)
                else:
                    assert 1 <= north <= 4, f"seed {seed}: {group.id} is outside rows 1 to 4"
                    russian[group.id] = hexes
        for group_id, hexes in russian.items():
            nearest = min(distance(a, b) for a in hexes for b in german)
            assert nearest <= 5, f"seed {seed}: {group_id} is {nearest} hexes from the nearest German group"


def test_a_band_with_no_building_large_enough_names_the_building_and_the_need():
    """The generator makes no building above six hexes, so a need of seven cannot hold."""
    board = generate(GeneratorParameters(seed=19771001), TERRAIN).subset_columns(0, 15)
    with pytest.raises(ValueError) as exc:
        resolve_zone(board, "stone_building", {"min_col": 0, "max_col": 7, "rank": 0, "min_hexes": 7})
    message = str(exc.value)
    assert "hexes, and the set up area needs 7" in message
    assert "columns A to H" in message


def test_a_rank_that_the_band_does_not_hold_names_the_count():
    board = generate(GeneratorParameters(seed=19771001), TERRAIN).subset_columns(0, 15)
    with pytest.raises(ValueError) as exc:
        resolve_zone(board, "stone_building", {"min_col": 0, "max_col": 7, "rank": 9})
    assert "asks for rank 9" in str(exc.value)


def test_a_zone_kind_the_project_does_not_have_names_the_zones_it_has():
    board = generate(GeneratorParameters(seed=5, cols=9, rows=10), TERRAIN)
    with pytest.raises(NotImplementedError) as exc:
        resolve_zone(board, "orchard", {})
    for name in ("stone_building", "columns", "edge"):
        assert name in str(exc.value)


# ------------------------------------------------- the column zone and the edge zone


def village_board():
    return generate(GeneratorParameters(seed=404, board_type="village", cols=33, rows=10), TERRAIN)


def test_a_column_zone_takes_each_hex_of_its_band():
    board = village_board()
    hexes = resolve_zone(board, "columns", {"min_col": 4, "max_col": 6})
    assert hexes
    assert {ref[0] for ref in hexes} == {4, 5, 6}
    assert len(hexes) == sum(1 for ref in board.order if 4 <= ref[0] <= 6)


def test_a_column_zone_with_a_terrain_test_takes_only_that_terrain():
    board = village_board()
    hexes = resolve_zone(board, "columns", {"min_col": 0, "max_col": 32, "terrain": "woods"})
    assert hexes
    assert all(board.hex(ref).terrain == "woods" for ref in hexes)


def test_a_column_zone_can_ask_for_the_road_hexes():
    """RV-2 section 6: a card names an entry on a road hex of one edge."""
    board = village_board()
    hexes = resolve_zone(board, "columns", {"min_col": 0, "max_col": 2, "road": True})
    assert hexes
    assert all(board.hex(ref).road for ref in hexes)


def test_a_column_zone_can_ask_for_one_hill_level():
    """Rule 43: a set up area on a hill takes the hexes of that level."""
    board = village_board()
    hexes = resolve_zone(board, "columns", {"min_col": 0, "max_col": 32, "level": 1})
    assert hexes
    assert all(board.hex(ref).elevation == 1 for ref in hexes)


def test_an_edge_zone_takes_the_hexes_of_one_edge():
    board = village_board()
    west = resolve_zone(board, "edge", {"side": "west", "depth": 2})
    east = resolve_zone(board, "edge", {"side": "east", "depth": 2})
    assert {ref[0] for ref in west} == {0, 1}
    assert {ref[0] for ref in east} == {board.cols - 2, board.cols - 1}
    assert not set(west) & set(east)


def test_the_north_and_the_south_edges_are_rows():
    board = village_board()
    north = resolve_zone(board, "edge", {"side": "north", "depth": 1})
    south = resolve_zone(board, "edge", {"side": "south", "depth": 1})
    assert north and south
    for ref in north:
        first = 0 if ref[0] & 1 else 1
        assert ref[1] == first
    for ref in south:
        assert ref[1] == board.rows
    assert not set(north) & set(south)


def test_an_edge_that_is_not_a_compass_direction_names_the_four():
    board = village_board()
    with pytest.raises(ValueError) as exc:
        resolve_zone(board, "edge", {"side": "up"})
    for name in ("north", "south", "east", "west"):
        assert name in str(exc.value)
