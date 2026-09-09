"""The four board types of FR-25 and the style record of FR-26.

Every type has to satisfy the geomorphic edge constants of FR-24, because a scenario may
put any two generated boards next to each other. So each rule here runs over all four
types, and the tests that follow say what makes each type itself.
"""

from __future__ import annotations

import pytest

from slboards import edges
from slboards.generator import (
    BOARD_TYPES,
    MAX_LEVEL,
    STYLE_KEYS,
    TYPE_CITY,
    TYPE_HILLS,
    TYPE_RURAL,
    TYPE_VILLAGE,
    GeneratorError,
    GeneratorParameters,
    default_style,
    generate,
)
from slcore import geometry
from sldata.loaders import load_terrain

TERRAIN = load_terrain()
SEEDS = [3, 101, 4242]


def params(seed: int, board_type: str, **style: int) -> GeneratorParameters:
    return GeneratorParameters(
        seed=seed,
        board_type=board_type,
        cols=edges.COLS,
        rows=edges.ROWS,
        style=tuple(sorted(style.items())),
    )


def board(seed: int, board_type: str, **style: int):
    return generate(params(seed, board_type, **style), TERRAIN)


def levels(b) -> dict:
    return {h.ref: h.elevation for h in b}


def counts(b) -> dict[str, int]:
    out: dict[str, int] = {}
    for h in b:
        out[h.terrain] = out.get(h.terrain, 0) + 1
    return out


# ------------------------------------------------------- what every type has to satisfy


@pytest.mark.parametrize("board_type", BOARD_TYPES)
@pytest.mark.parametrize("seed", SEEDS)
def test_every_type_satisfies_the_geomorphic_edges(board_type: str, seed: int):
    assert edges.check_edges(edges.kind_map(board(seed, board_type))) == []


@pytest.mark.parametrize("board_type", BOARD_TYPES)
def test_two_boards_of_one_type_join_on_both_sides(board_type: str):
    west = edges.kind_map(board(21, board_type))
    east = edges.kind_map(board(22, board_type))
    assert edges.check_join(west, east, "east") == []
    assert edges.check_join(west, east, "south") == []


def test_boards_of_different_types_join():
    """A scenario may put a city next to a rural board, so the seam has to hold there too."""
    city = edges.kind_map(board(31, TYPE_CITY))
    country = edges.kind_map(board(32, TYPE_RURAL))
    assert edges.check_join(city, country, "east") == []
    assert edges.check_join(city, country, "south") == []


@pytest.mark.parametrize("board_type", BOARD_TYPES)
@pytest.mark.parametrize("seed", SEEDS)
def test_the_outer_ring_of_every_board_is_ground_level(board_type: str, seed: int):
    """A seam between two levels would be a step that no rule describes, so there is none."""
    b = board(seed, board_type)
    for ref, elevation in levels(b).items():
        col, row = ref
        first = 0 if col & 1 else 1
        if col in (0, b.cols - 1) or row in (first, b.rows):
            assert elevation == 0, f"{geometry.hex_id(*ref)} is on the rim and above ground"


@pytest.mark.parametrize("board_type", BOARD_TYPES)
@pytest.mark.parametrize("seed", SEEDS)
def test_no_slope_is_steeper_than_one_level(board_type: str, seed: int):
    """A step of two levels is a cliff (rule 44.1), and the generator makes no cliffs."""
    plan = levels(board(seed, board_type))
    for ref, here in plan.items():
        for other in geometry.neighbors(*ref):
            if other in plan:
                assert abs(here - plan[other]) <= 1


@pytest.mark.parametrize("board_type", BOARD_TYPES)
def test_no_level_is_above_the_third(board_type: str):
    """Rule 43.1: the game has three levels of hills."""
    assert max(levels(board(77, board_type)).values()) <= MAX_LEVEL


@pytest.mark.parametrize("board_type", BOARD_TYPES)
def test_a_hexside_feature_reads_the_same_from_both_hexes(board_type: str):
    b = board(55, board_type)
    for h in b:
        for d, feature in enumerate(h.hexsides):
            if feature is None:
                continue
            other = geometry.neighbor(h.col, h.row, d)
            assert b.hexside(other, (d + 3) % 6) == feature


@pytest.mark.parametrize("board_type", BOARD_TYPES)
def test_every_type_is_repeatable(board_type: str):
    assert board(9, board_type).to_dict() == board(9, board_type).to_dict()


# ------------------------------------------------------------ what makes each type itself


def test_a_hills_board_has_all_three_levels():
    seen = set()
    for seed in SEEDS:
        seen.update(levels(board(seed, TYPE_HILLS)).values())
    assert {1, 2, 3} <= seen


def test_a_city_board_is_flat_and_a_hills_board_is_not():
    """Rule 43 belongs to the country boards, and the city board stays on ground level."""
    assert set(levels(board(101, TYPE_CITY)).values()) == {0}
    assert len([e for e in levels(board(101, TYPE_HILLS)).values() if e]) > 20


def test_a_rural_board_is_mostly_grain_and_hedges():
    """Rule 44.2 wheatfields, and the hedgerows of rule 11.5."""
    b = board(101, TYPE_RURAL)
    kinds = counts(b)
    hedges = sum(1 for h in b for f in h.hexsides if f == "hedge")
    assert kinds.get("wheat", 0) > kinds.get("stone_building", 0) * 3
    assert hedges >= 2


def test_a_village_gathers_its_buildings_around_one_junction():
    """A village is a cluster, so its buildings sit closer together than a city block grid.

    One board is one sample, and a sample can go either way. The rule is about the mean of
    the distance from a building hex to the middle of the buildings, over several seeds.
    """
    def gather(board_type: str) -> float:
        totals = []
        for seed in (101, 202, 303, 404, 505):
            b = board(seed, board_type)
            refs = [h.ref for h in b if h.building is not None]
            if len(refs) < 2:
                continue
            middle = (
                sum(r[0] for r in refs) // len(refs),
                sum(r[1] for r in refs) // len(refs),
            )
            totals.append(sum(geometry.distance(middle, r) for r in refs) / len(refs))
        return sum(totals) / len(totals)

    assert gather(TYPE_VILLAGE) < gather(TYPE_CITY)


def test_a_city_board_has_the_sewer_entrances_and_a_country_board_has_none():
    """Rule 27 is a city rule, so a rural board carries no entrance."""
    assert any(h.sewer for h in board(101, TYPE_CITY))
    assert not any(h.sewer for h in board(101, TYPE_RURAL))


# ------------------------------------------------------------------- the style of FR-26


def test_the_style_of_a_type_names_every_key():
    for board_type in BOARD_TYPES:
        assert set(default_style(board_type)) == set(STYLE_KEYS)


def test_a_style_override_changes_the_board():
    plain = board(101, TYPE_RURAL)
    thick = board(101, TYPE_RURAL, hedges=40)
    assert sum(1 for h in thick for f in h.hexsides if f == "hedge") > sum(
        1 for h in plain for f in h.hexsides if f == "hedge"
    )


def test_a_style_with_no_hills_gives_a_flat_board():
    assert set(levels(board(101, TYPE_HILLS, hills=0)).values()) == {0}


def test_an_unknown_style_key_names_the_keys_it_knows():
    with pytest.raises(GeneratorError) as exc:
        params(1, TYPE_CITY, mountains=3).styles()
    assert "mountains" in str(exc.value)
    assert "buildings" in str(exc.value)


def test_the_style_record_round_trips():
    p = params(9, TYPE_VILLAGE, hedges=12, walls=3)
    assert GeneratorParameters.from_dict(p.to_dict()) == p
    assert p.styles()["hedges"] == 12


def test_the_older_density_field_still_names_the_building_density():
    """A parameter record written before the style record still builds its board."""
    p = GeneratorParameters(seed=9, board_type=TYPE_CITY, building_density=7)
    assert p.styles()["buildings"] == 7
    assert GeneratorParameters.from_dict(p.to_dict()) == p


def test_a_board_type_the_generator_does_not_know_names_the_four():
    with pytest.raises(NotImplementedError) as exc:
        generate(GeneratorParameters(seed=1, board_type="tundra", cols=33, rows=10), TERRAIN)
    for name in BOARD_TYPES:
        assert name in str(exc.value)


# ------------------------------------------------------------------ rule 44.1, cliffs


def cliff_count(b) -> int:
    return sum(1 for h in b for f in h.hexsides if f == "cliff") // 2


def test_a_hills_board_has_cliffs_and_a_city_board_has_none():
    """Rule 44.1: a black hexside on a hill. A flat city board has no hill to put one on."""
    assert cliff_count(board(101, TYPE_HILLS)) > 0
    assert cliff_count(board(101, TYPE_CITY)) == 0


def test_a_cliff_sits_where_the_level_changes():
    """Rule 44.1 puts a cliff on a hill hexside, so the two hexes are on different levels."""
    b = board(101, TYPE_HILLS)
    found = 0
    for h in b:
        for d, feature in enumerate(h.hexsides):
            if feature != "cliff":
                continue
            other = geometry.neighbor(h.col, h.row, d)
            assert b.hex(other).elevation != h.elevation
            found += 1
    assert found > 0


@pytest.mark.parametrize("board_type", BOARD_TYPES)
@pytest.mark.parametrize("seed", SEEDS)
def test_a_cliff_never_cuts_the_board_in_two(board_type: str, seed: int):
    """A board that a cliff cuts in two is a board that no scenario can use."""
    b = board(seed, board_type)
    refs = [h.ref for h in b]
    start = refs[0]
    seen = {start}
    frontier = [start]
    while frontier:
        here = frontier.pop()
        for d in range(6):
            if b.hexside(here, d) == "cliff":
                continue
            nxt = geometry.neighbor(*here, d)
            if nxt in seen or nxt not in b:
                continue
            seen.add(nxt)
            frontier.append(nxt)
    assert len(seen) == len(refs)


def test_a_style_with_no_cliffs_makes_none():
    assert cliff_count(board(101, TYPE_HILLS, cliffs=0)) == 0


def test_no_cliff_is_on_the_rim():
    """A cliff on a seam would not meet the board next to it."""
    b = board(202, TYPE_HILLS)
    for h in b:
        first = 0 if h.col & 1 else 1
        on_rim = h.col in (0, b.cols - 1) or h.row in (first, b.rows)
        if on_rim:
            assert not any(f == "cliff" for f in h.hexsides)
