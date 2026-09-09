"""The road network of a generated board.

A road that stops in the middle of a field is not a road. These tests read the network as
a graph: one connected group, an entry on each edge, and a real crossroads where a north
to south road meets the east to west road.

The first version of `road_grid` put the odd columns one row lower than the even ones. On
this lattice a column of an odd index already sits half a hex lower, so that made a line
of hexes two apart. The board had 47 road hexes in 21 pieces. `test_the_road_network_is_one
_connected_group` is the measurement that finds that again.
"""

from __future__ import annotations

import pytest

from slboards.edges import road_column_indexes
from slboards.generator import (
    BOARD_TYPES,
    GeneratorParameters,
    default_style,
    generate_with_retry,
    junctions,
    middle_row,
    road_groups,
)
from slcore import geometry
from sldata.loaders import load_terrain

SEEDS = (101, 4242, 77)
WIDTHS = (25, 33)


def build(seed: int, board_type: str, cols: int = 33):
    terrain = load_terrain()
    board, _ = generate_with_retry(GeneratorParameters(seed=seed, board_type=board_type, cols=cols), terrain)
    return board


def road_refs(board) -> set:
    return {h.ref for h in board if h.road}


@pytest.mark.parametrize("board_type", BOARD_TYPES)
def test_the_road_network_is_one_connected_group(board_type: str):
    for seed in SEEDS:
        board = build(seed, board_type)
        roads = road_refs(board)
        groups = road_groups(roads)
        assert len(groups) == 1, (
            f"{board_type} seed {seed} has {len(roads)} road hexes in {len(groups)} pieces, "
            f"of sizes {[len(g) for g in groups]}"
        )


@pytest.mark.parametrize("board_type", BOARD_TYPES)
def test_a_road_crosses_the_board_from_west_to_east(board_type: str):
    for seed in SEEDS:
        board = build(seed, board_type)
        roads = road_refs(board)
        columns = {c for c, _ in roads}
        assert 0 in columns, f"{board_type} seed {seed} has no road on the west edge"
        assert board.cols - 1 in columns, f"{board_type} seed {seed} has no road on the east edge"


@pytest.mark.parametrize("board_type", BOARD_TYPES)
def test_a_road_crosses_the_board_from_north_to_south(board_type: str):
    for seed in SEEDS:
        board = build(seed, board_type)
        rows = {r for _, r in road_refs(board)}
        assert min(rows) <= 1, f"{board_type} seed {seed} has no road on the north edge"
        assert max(rows) >= board.rows, f"{board_type} seed {seed} has no road on the south edge"


@pytest.mark.parametrize("board_type", BOARD_TYPES)
def test_the_board_has_a_real_crossroads(board_type: str):
    """A crossroads hex has four road hexes around it, and the style says how many there are."""
    for seed in SEEDS:
        board = build(seed, board_type)
        roads = road_refs(board)
        crossroads = [r for r in roads if sum(1 for n in geometry.neighbors(*r) if n in roads) >= 4]
        assert crossroads, f"{board_type} seed {seed} has no hex with four roads around it"
        wanted = junctions(roads, board.cols, default_style(board_type)["roads"], board.rows)
        assert wanted, f"{board_type} seed {seed} has no junction of a column road and the middle road"
        for ref in wanted:
            around = sum(1 for n in geometry.neighbors(*ref) if n in roads)
            assert around >= 4, f"the junction {ref} of {board_type} has {around} roads around it"


def test_the_middle_road_holds_one_row_index_for_each_column():
    """One row index gives the zigzag, because an odd column sits half a hex lower."""
    board = build(101, "city")
    row = middle_row(board.rows)
    line = sorted(h.ref for h in board if h.road and h.ref[1] == row)
    assert len(line) == board.cols, "the middle road does not reach each column"
    for left, right in zip(line, line[1:]):
        assert geometry.direction_to(left, right) is not None, f"{left} and {right} do not touch"


def test_each_road_column_runs_from_the_north_edge_to_the_south_edge():
    board = build(101, "city")
    roads = road_refs(board)
    columns = road_column_indexes(board.cols)[: default_style("city")["roads"]]
    assert columns
    for col in columns:
        rows = sorted(r for c, r in roads if c == col)
        assert rows, f"column {col} carries no road"
        assert rows[0] <= 1 and rows[-1] >= board.rows, f"column {col} does not cross the board"
        for a, b in zip(rows, rows[1:]):
            assert geometry.direction_to((col, a), (col, b)) is not None, f"column {col} breaks at row {a}"


@pytest.mark.parametrize("cols", WIDTHS)
def test_a_narrow_board_keeps_its_network(cols: int):
    """A scenario that plays on part of a board still gets one network."""
    board = build(4242, "village", cols=cols)
    assert len(road_groups(road_refs(board))) == 1
