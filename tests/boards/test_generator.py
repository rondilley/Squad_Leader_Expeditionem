"""The first generator pass: the geomorphic edges (FR-24) and a repeatable board."""

import pytest

from slboards import edges
from slboards.generator import (
    GENERATOR_VERSION,
    GeneratorError,
    GeneratorParameters,
    ZoneConstraint,
    generate,
    generate_city,
    generate_with_retry,
)
from slcli.play import build_engine_with_record
from slcore import geometry
from slcore.scenario import stone_buildings
from sldata.loaders import board_and_parameters, load_scenario, load_terrain

TERRAIN = load_terrain()
SEEDS = [1, 2, 3, 7, 42, 101, 19771001]


def params(seed: int) -> GeneratorParameters:
    return GeneratorParameters(seed=seed, board_type="city", cols=edges.COLS, rows=edges.ROWS)


@pytest.mark.parametrize("seed", SEEDS)
def test_the_edges_satisfy_the_geomorphic_rules(seed: int):
    board = generate_city(params(seed), TERRAIN)
    kinds = {h.ref: ("road" if h.road else h.terrain) for h in board}
    problems = edges.check_edges(kinds, board.cols, board.rows)
    assert not problems, problems


@pytest.mark.parametrize("seed", SEEDS)
def test_a_city_board_has_buildings_and_roads(seed: int):
    board = generate_city(params(seed), TERRAIN)
    assert len(board) == 346, "33 columns with half hexes on the long edges"
    buildings = stone_buildings(board)
    assert len(buildings) >= 8, f"a city needs building blocks, and this board has {len(buildings)}"
    for _, hexes in buildings:
        assert 2 <= len(hexes) <= 6
        assert connected(hexes), hexes
    assert sum(1 for h in board if h.road) > 60


def connected(hexes) -> bool:
    remaining = set(hexes)
    stack = [next(iter(remaining))]
    seen = set()
    while stack:
        here = stack.pop()
        if here in seen:
            continue
        seen.add(here)
        for n in geometry.neighbors(*here):
            if n in remaining and n not in seen:
                stack.append(n)
    return seen == remaining


def test_the_same_parameters_give_the_same_board():
    a = generate_city(params(5), TERRAIN)
    b = generate_city(params(5), TERRAIN)
    assert a.to_dict() == b.to_dict()
    c = generate_city(params(6), TERRAIN)
    assert c.to_dict() != a.to_dict()


def test_the_parameter_record_round_trips():
    p = params(9)
    assert GeneratorParameters.from_dict(p.to_dict()) == p


def test_a_column_subset_keeps_the_hex_names_and_the_buildings():
    board = generate_city(params(19771001), TERRAIN)
    west = board.subset_columns(0, 15)
    assert west.cols == 16
    assert len(west) == 168
    for _, hexes in stone_buildings(west):
        for h in hexes:
            assert h in west


def test_a_zone_constraint_counts_only_the_buildings_the_scenario_can_use():
    zone = ZoneConstraint(count=1, min_hexes=2, max_hexes=4, min_col=0, max_col=15)
    assert zone.holds([(3, 4), (3, 5)]) is True
    assert zone.holds([(3, 4)]) is False, "one hex is below the minimum"
    assert zone.holds([(3, 4), (4, 4), (5, 4), (6, 4), (7, 4)]) is False, "five hexes is above the maximum"
    assert zone.holds([(15, 4), (16, 4)]) is False, "the column subset cuts this building"
    assert "columns 0 to 15" in zone.where()
    assert ZoneConstraint(count=1).where() == "on the board"


DENSE = 2


def first_seed_that_misses(zones, first=100, last=400):
    """A seed the zones refuse. The generator changes, so the test finds one at run time.

    The density is the one that makes the count vary from seed to seed. At the default the
    count is the same on each board, so no demand separates a seed that misses from a seed
    that holds, and the retry has nothing to prove.
    """
    for seed in range(first, last):
        try:
            generate(GeneratorParameters(seed=seed, building_density=DENSE, zones=zones), TERRAIN)
        except GeneratorError:
            return seed
    return None


def test_a_seed_that_misses_the_zones_gives_the_next_seed_that_holds():
    zones = (ZoneConstraint(count=13, min_hexes=2, max_hexes=6, min_col=0, max_col=15),)
    seed = first_seed_that_misses(zones)
    assert seed is not None, "no seed in the range refuses thirteen buildings, so widen the test"
    asked = GeneratorParameters(seed=seed, building_density=DENSE, zones=zones)
    with pytest.raises(GeneratorError) as exc:
        generate(asked, TERRAIN)
    assert "stone buildings" in str(exc.value) and "columns 0 to 15" in str(exc.value)
    board, used = generate_with_retry(asked, TERRAIN, tries=40)
    assert used.seed > seed, "the retry moves to a later seed"
    assert board.name.endswith(f"-{used.seed}-v{GENERATOR_VERSION}"), board.name


def test_a_zone_no_seed_can_satisfy_names_the_seed_range():
    zones = (ZoneConstraint(count=99, min_hexes=2, max_hexes=6),)
    with pytest.raises(GeneratorError) as exc:
        generate_with_retry(GeneratorParameters(seed=200, zones=zones), TERRAIN, tries=3)
    message = str(exc.value)
    assert "from 200 to 202" in message
    assert "another seed or another board type" in message


def test_the_zone_record_round_trips_with_its_columns():
    zone = ZoneConstraint(count=4, min_hexes=3, max_hexes=5, min_col=1, max_col=9)
    assert ZoneConstraint.from_dict(zone.to_dict()) == zone
    params = GeneratorParameters(seed=3, zones=(zone,))
    assert GeneratorParameters.from_dict(params.to_dict()) == params


def test_scenario_one_gives_every_group_its_own_stone_building():
    scenario = load_scenario("s01_guards_counterattack")
    board, params = board_and_parameters(scenario, TERRAIN)
    assert params is not None
    bands = {(z.min_col, z.max_col): z for z in params.zones if z.min_hexes == 2}
    assert bands[(0, 7)].count == 5, "the Russians need five buildings in the west band"
    assert bands[(8, 15)].count == 5, "the Germans need five buildings in the east band"
    room = [z for z in params.zones if z.min_hexes == 4]
    assert len(room) == 1 and room[0].max_col == 7, "the guards need a building of four hexes" 
    seen: dict[str, str] = {}
    for side in scenario.sides:
        for group in side.groups:
            building = group.area.building_id(board)
            assert building is not None, f"{group.id} has no building"
            assert building not in seen, f"{group.id} and {seen[building]} share building {building}"
            seen[building] = group.id
    assert len(seen) == 10


def test_the_board_record_of_a_run_builds_the_same_board_again():
    engine, record = build_engine_with_record("s01_guards_counterattack")
    assert record["board_source"] == "generated"
    assert record["board"] == engine.board.name
    again = generate(GeneratorParameters.from_dict(record["generator"]), TERRAIN)
    low, high = record["board_columns"]
    assert again.subset_columns(low, high).to_dict() == engine.board.to_dict()
