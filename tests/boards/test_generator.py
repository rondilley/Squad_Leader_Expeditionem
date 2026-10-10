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
    assert "columns A to P" in zone.where()
    assert ZoneConstraint(count=1).where() == "on the board"


def test_a_zone_constraint_reads_a_row_band_and_a_near_band():
    """Scenario 1 puts the Russians in rows 1 to 4 next to the Germans in rows 5 to 9."""
    german = ZoneConstraint(count=1, min_row=5, max_row=9)
    assert german.holds([(6, 5), (6, 6)]) is True
    assert german.holds([(6, 4), (6, 5)]) is False, "the building crosses the row line"
    assert "rows 5 to 9" in german.where()
    russian = ZoneConstraint.from_dict(
        {"count": 1, "min_row": 1, "max_row": 4, "near": {"min_row": 5, "max_row": 9, "max_distance": 2}}
    )
    shapes = [[(6, 5), (6, 6)], [(6, 3), (6, 4)], [(12, 1), (12, 2)]]
    assert russian.holds(shapes[1], shapes) is True, "one hex from the German building"
    assert russian.holds(shapes[2], shapes) is False, "six columns from the German building"
    assert russian.holds(shapes[0], shapes) is False, "the German building is not in rows 1 to 4"
    assert "within 2 hexes of a stone building in rows 5 to 9" in russian.where()
    assert ZoneConstraint.from_dict(russian.to_dict()) == russian
