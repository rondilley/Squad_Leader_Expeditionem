"""The road hexsides of PR-50 on a generated board and on a composition.

The core reads the road rate of the Vehicle Movement Cost Chart where the road crosses the
hexside of the move (`Board.road_crosses`). A board document that names no road hexside
keeps the reading from before the ruling: two adjacent road hexes are joined. Generator
version 8 names the road hexsides, so two road hexes that touch across the corner of a
crossroads are not joined by the road.

The `Board` constructor refuses a road hexside that only one of its two hexes names, so
each board these tests build has passed that check.
"""

from __future__ import annotations

import pytest

from slboards import edges
from slboards.compose import EAST, SOUTH, Placement, compose, turn
from slboards.generator import (
    BOARD_TYPES,
    GENERATOR_VERSION,
    GeneratorParameters,
    default_style,
    generate,
    generate_with_retry,
    junctions,
    middle_row,
    road_groups,
)
from slcore import geometry
from slcore.state import Board, Hex
from sldata.loaders import load_terrain

TERRAIN = load_terrain()
SEEDS = (5, 101)


def build(seed: int, board_type: str = "city", version: int = GENERATOR_VERSION) -> Board:
    board, _ = generate_with_retry(GeneratorParameters(seed=seed, board_type=board_type, version=version), TERRAIN)
    return board


def road_graph_parts(board: Board) -> list[set]:
    """The road hexes in parts that the named road hexsides join."""
    roads = {h.ref for h in board if h.road}
    seen: set = set()
    parts = []
    for start in sorted(roads):
        if start in seen:
            continue
        part = set()
        stack = [start]
        while stack:
            here = stack.pop()
            if here in part:
                continue
            part.add(here)
            for d in board.hex(here).road_sides:
                there = geometry.neighbor(*here, d)
                if there in roads and there not in part:
                    stack.append(there)
        seen |= part
        parts.append(part)
    return parts


def test_the_generator_version_names_the_road_hexsides():
    assert GENERATOR_VERSION >= 8


@pytest.mark.parametrize("board_type", BOARD_TYPES)
def test_each_road_hex_names_a_road_hexside(board_type: str):
    for seed in SEEDS:
        board = build(seed, board_type)
        assert board.named_road_sides
        bare = [h.id for h in board if h.road and not h.road_sides]
        assert not bare, f"{board_type} seed {seed}: road hexes with no road hexside {bare}"
        stray = [h.id for h in board if h.road_sides and not h.road]
        assert not stray, f"{board_type} seed {seed}: hexes that are not road hexes name a road hexside {stray}"


@pytest.mark.parametrize("board_type", BOARD_TYPES)
def test_the_road_hexsides_join_each_road_group_into_one_road(board_type: str):
    """The named hexsides make the same network as the road hexes that touch."""
    for seed in SEEDS:
        board = build(seed, board_type)
        touching = road_groups({h.ref for h in board if h.road})
        joined = road_graph_parts(board)
        assert len(joined) == len(touching), (
            f"{board_type} seed {seed}: {len(touching)} road groups, and the road hexsides make {len(joined)}"
        )


@pytest.mark.parametrize("board_type", BOARD_TYPES)
def test_the_road_does_not_cut_the_corner_of_a_crossroads(board_type: str):
    """Rule 30 with PR-50: the hexes on each side of a crossroads touch, and no road joins them."""
    for seed in SEEDS:
        board = build(seed, board_type)
        roads = {h.ref for h in board if h.road}
        crossings = junctions(roads, board.cols, default_style(board_type)["roads"], board.rows)
        assert crossings
        for centre in crossings:
            assert len(board.hex(centre).road_sides) == 4, f"the crossroads {centre} of {board_type}"
            arms = [geometry.neighbor(*centre, d) for d in board.hex(centre).road_sides]
            corners = 0
            for a in arms:
                for b in arms:
                    d = geometry.direction_to(a, b)
                    if a < b and d is not None:
                        corners += 1
                        assert not board.road_crosses(a, d), f"{a} and {b} beside the crossroads {centre}"
                        assert not board.road_crosses(b, (d + 3) % 6)
            assert corners > 0, "a crossroads on this lattice has arms that touch"


def test_the_road_runs_along_the_middle_row_and_each_road_column():
    board = build(101)
    row = middle_row(board.rows)
    for col in range(board.cols - 1):
        a, b = (col, row), (col + 1, row)
        d = geometry.direction_to(a, b)
        assert d is not None and board.road_crosses(a, d), f"the middle road breaks between {a} and {b}"
    for col in edges.road_column_indexes(board.cols):
        for r in range(1, board.rows):
            assert board.road_crosses((col, r), 3), f"the road of column {col} breaks at row {r}"


def test_a_road_entry_on_the_north_or_the_south_edge_names_the_edge_hexside():
    """A board type with fewer road columns has no road in the other entries, so this reads
    the city, which has all three."""
    board = build(101, "city")
    checked = 0
    for ref in edges.road_edge_hexes(board.cols, board.rows):
        if ref[0] in (0, board.cols - 1):
            continue
        h = board.hex(ref)
        assert h.road
        edge = 0 if ref[1] <= 1 else 3
        assert edge in h.road_sides, f"{h.id} does not lead off the board"
        checked += 1
    assert checked == 6


def test_a_version_7_record_builds_the_board_it_built_before():
    """Version 8 changes no terrain, and a record of version 7 names no road hexside."""
    old = generate(GeneratorParameters(seed=101, version=7), TERRAIN)
    new = generate(GeneratorParameters(seed=101, version=8), TERRAIN)
    assert not old.named_road_sides
    assert new.named_road_sides
    for h in old:
        other = new.hex(h.ref)
        assert (h.terrain, h.road, h.elevation, h.hexsides, h.sewer) == (
            other.terrain,
            other.road,
            other.elevation,
            other.hexsides,
            other.sewer,
        )
        assert (h.building is None) == (other.building is None)
    # The old reading joins two adjacent road hexes, which is not what version 8 says.
    roads = {h.ref for h in old if h.road}
    junction = junctions(roads, old.cols, 3, old.rows)[0]
    arms = [geometry.neighbor(*junction, d) for d in range(6) if geometry.neighbor(*junction, d) in roads]
    pair = next((a, b) for a in arms for b in arms if a < b and geometry.direction_to(a, b) is not None)
    d = geometry.direction_to(*pair)
    assert old.road_crosses(pair[0], d)
    assert not new.road_crosses(pair[0], d)


def test_a_column_subset_keeps_a_valid_road():
    board = build(101)
    part = board.subset_columns(0, 20)
    assert part.named_road_sides
    assert all(h.road_sides for h in part if h.road)


@pytest.mark.parametrize("first,second", [("city", "city"), ("city", "hills"), ("village", "rural")])
def test_the_road_goes_on_across_a_join_on_the_south(first: str, second: str):
    north = build(11, first)
    south = build(12, second)
    composed = compose([Placement(north), Placement(south)], SOUTH, TERRAIN)
    for ref in edges.road_edge_hexes(north.cols, north.rows):
        if ref[1] != north.rows or ref[0] in (0, north.cols - 1):
            continue
        below = (ref[0], ref[1] + 1)
        both = composed.hex(ref).road and composed.hex(below).road
        assert composed.road_crosses(ref, 3) == both, f"{geometry.hex_id(*ref)} and the board below"
        if both:
            assert composed.road_crosses(below, 0)


def test_the_road_goes_on_across_a_join_on_the_east():
    composed = compose([Placement(build(11)), Placement(build(12, "village"))], EAST, TERRAIN)
    row = middle_row(composed.rows)
    for col in range(composed.cols - 1):
        a, b = (col, row), (col + 1, row)
        assert composed.road_crosses(a, geometry.direction_to(a, b)), f"the road breaks between {a} and {b}"
    assert len(road_graph_parts(composed)) == len(road_groups({h.ref for h in composed if h.road}))


def test_a_turned_board_turns_its_road_hexsides():
    board = build(21, "village")
    turned = turn(board)
    for h in board:
        there = (board.cols - 1 - h.col, board.rows + 1 - h.row - (h.col & 1))
        assert turned.hex(there).road_sides == tuple(sorted((d + 3) % 6 for d in h.road_sides))
    compose([Placement(board), Placement(board, turned=True)], SOUTH, TERRAIN)


def test_a_board_that_names_no_road_hexside_keeps_its_roads_in_a_mixed_composition():
    """A board of version 7 next to a board of version 8 still has each of its roads."""
    old = build(11, version=7)
    composed = compose([Placement(old), Placement(build(12))], EAST, TERRAIN)
    assert composed.named_road_sides
    for h in old:
        if not h.road:
            continue
        for d in range(6):
            there = geometry.neighbor(h.col, h.row, d)
            if there in {x.ref for x in old if x.road} and 0 <= there[0] < old.cols - 1:
                assert composed.road_crosses(h.ref, d), f"{h.id} lost its road in direction {d}"


def test_a_road_hexside_named_from_one_side_is_refused():
    """The check of the core that the generator and the composition satisfy."""
    hexes = [Hex(col=0, row=1, road=True, road_sides=(3,)), Hex(col=0, row=2, road=True)]
    with pytest.raises(ValueError):
        Board(1, 2, hexes, TERRAIN)
