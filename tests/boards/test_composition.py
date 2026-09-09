"""Board composition, FR-29: two to four boards make one playing surface.

The scenarios of Game Set II and later play on more than one board. RV-2 section 6 records
the diagrams: the boards touch along their long edges, which stacks them from north to
south, or along their short edges, which puts them end to end. A board can be turned one
hundred and eighty degrees first.
"""

from __future__ import annotations

import pytest

from slboards import edges
from slboards.compose import (
    EAST,
    SOUTH,
    CompositionError,
    Placement,
    board_coordinate,
    compose,
    offsets,
    size,
    turn,
)
from slboards.generator import BOARD_TYPES, GeneratorParameters, generate
from slcore import geometry
from slcore.los_cache import LosTable
from slcore.los_eval import evaluate
from sldata.loaders import load_terrain

TERRAIN = load_terrain()


def board(seed: int, board_type: str = "city"):
    return generate(GeneratorParameters(seed=seed, board_type=board_type), TERRAIN)


# ------------------------------------------------------------------------- the turn


def test_a_turn_keeps_the_hex_count_and_the_size():
    one = board(11)
    other = turn(one)
    assert other.cols == one.cols
    assert other.rows == one.rows
    assert len(other) == len(one)


def test_a_turn_twice_gives_the_board_again():
    one = board(12)
    assert turn(turn(one)).to_dict()["hexes"] == one.to_dict()["hexes"]


def test_a_turn_moves_the_first_hex_to_the_last_place():
    one = board(13)
    other = turn(one)
    first = one.hex((0, 1))
    last = other.hex((one.cols - 1, one.rows))
    assert last.terrain == first.terrain
    assert last.road == first.road


def test_a_turn_moves_a_hexside_feature_to_the_other_side():
    """A wall between two hexes is still between them after the board turns."""
    one = board(55, "village")
    other = turn(one)
    for h in one:
        for d, feature in enumerate(h.hexsides):
            if feature is None:
                continue
            there = (one.cols - 1 - h.col, one.rows + 1 - h.row - (h.col & 1))
            assert other.hex(there).hexsides[(d + 3) % 6] == feature


def test_a_turn_keeps_the_polygons_on_the_lattice():
    """A woods hex keeps its shape, so the line of sight through it does not change."""
    one = board(14)
    other = turn(one)
    for h in one:
        there = (one.cols - 1 - h.col, one.rows + 1 - h.row - (h.col & 1))
        assert len(other.hex(there).polygons) == len(h.polygons)
        for polygon in other.hex(there).polygons:
            for x, y in polygon.points:
                assert isinstance(x, int) and isinstance(y, int)


def test_a_turned_board_still_satisfies_the_edge_constants():
    """The edge constants are symmetrical, so a turn keeps FR-24."""
    for board_type in BOARD_TYPES:
        assert edges.check_edges(edges.kind_map(turn(board(21, board_type)))) == []


def test_a_board_with_an_even_column_count_cannot_turn():
    one = board(15).subset_columns(0, 9)
    with pytest.raises(CompositionError) as exc:
        turn(one)
    assert "odd column count" in str(exc.value)


# ------------------------------------------------------------------- the offsets


def test_a_join_on_the_east_costs_one_column():
    """Rule 3.5: the half hexes of the two edges become one hex."""
    two = [Placement(board(11)), Placement(board(12))]
    assert offsets(two, EAST) == [(0, 0), (32, 0)]
    assert size(two, EAST) == (65, 10)


def test_a_join_on_the_south_costs_one_row():
    two = [Placement(board(11)), Placement(board(12))]
    assert offsets(two, SOUTH) == [(0, 0), (0, 10)]
    assert size(two, SOUTH) == (33, 20)


def test_four_boards_end_to_end():
    four = [Placement(board(seed)) for seed in (11, 12, 13, 14)]
    assert offsets(four, EAST) == [(0, 0), (32, 0), (64, 0), (96, 0)]
    assert size(four, EAST) == (129, 10)


def test_a_side_that_is_not_a_join_names_the_two():
    with pytest.raises(CompositionError) as exc:
        offsets([Placement(board(11)), Placement(board(12))], "up")
    assert EAST in str(exc.value) and SOUTH in str(exc.value)


# --------------------------------------------------------------- the composition


@pytest.mark.parametrize("side,shape", [(EAST, (65, 10)), (SOUTH, (33, 20))])
def test_two_boards_make_one_surface(side: str, shape):
    composed = compose([Placement(board(11)), Placement(board(12, "village"))], side, TERRAIN)
    assert (composed.cols, composed.rows) == shape
    assert len(composed) == sum(1 for _ in composed)


@pytest.mark.parametrize("count", [2, 3, 4])
@pytest.mark.parametrize("side", [EAST, SOUTH])
def test_two_to_four_boards_compose(count: int, side: str):
    placements = [Placement(board(20 + i, BOARD_TYPES[i % len(BOARD_TYPES)])) for i in range(count)]
    composed = compose(placements, side, TERRAIN)
    if side == EAST:
        assert composed.cols == 33 + 32 * (count - 1)
        assert composed.rows == 10
    else:
        assert composed.cols == 33
        assert composed.rows == 10 * count


def test_one_board_is_not_a_composition():
    with pytest.raises(CompositionError) as exc:
        compose([Placement(board(11))], EAST, TERRAIN)
    assert "two to four" in str(exc.value)


def test_five_boards_are_not_a_composition():
    with pytest.raises(CompositionError):
        compose([Placement(board(10 + i)) for i in range(5)], EAST, TERRAIN)


def test_a_turned_board_composes():
    composed = compose(
        [Placement(board(31)), Placement(board(32, "rural"), turned=True)], EAST, TERRAIN
    )
    assert composed.cols == 65
    assert "turned" in composed.name


def test_the_composition_is_repeatable():
    def build():
        return compose([Placement(board(41)), Placement(board(42), turned=True)], SOUTH, TERRAIN)

    assert build().to_dict() == build().to_dict()


def test_a_building_of_a_composition_carries_the_number_of_its_board():
    """Two boards each name their buildings B1 and B2, so the names have to change."""
    composed = compose([Placement(board(51)), Placement(board(52))], EAST, TERRAIN)
    ids = {h.building.id for h in composed if h.building is not None}
    assert any(i.startswith("1-") for i in ids)
    assert any(i.startswith("2-") for i in ids)
    for building_id in ids:
        hexes = {h.ref for h in composed if h.building is not None and h.building.id == building_id}
        columns = {ref[0] for ref in hexes}
        assert max(columns) - min(columns) < 33, "no building crosses a seam"


def test_the_hexes_of_a_seam_are_one_hex():
    """Rule 3.5. The column that the two boards share appears one time."""
    first = board(61)
    second = board(62, "hills")
    composed = compose([Placement(first), Placement(second)], EAST, TERRAIN)
    seam = [h for h in composed if h.col == first.cols - 1]
    assert len(seam) == first.rows
    for h in seam:
        assert h.terrain == first.hex((first.cols - 1, h.row)).terrain
        assert h.terrain == second.hex((0, h.row)).terrain


def test_a_composition_names_the_board_a_hex_came_from():
    """Rule 3.5 gives a hex the board it belongs to, and this is that name."""
    composed = compose([Placement(board(71)), Placement(board(72))], EAST, TERRAIN)
    near = board_coordinate(composed, (2, 3))
    far = board_coordinate(composed, (40, 3))
    assert near.endswith(":C3")
    assert ":" in far and not far.endswith(":C3")
    assert near.split(":")[0] != far.split(":")[0]


# --------------------------------------------------------------------- the seam


def test_the_line_of_sight_crosses_a_seam():
    """The composition is one board, so a thread runs from one side of the seam to the other."""
    composed = compose([Placement(board(81)), Placement(board(82))], EAST, TERRAIN)
    table = LosTable(composed)
    result = evaluate(composed, table, (28, 5), (38, 5))
    assert result.traced, "the thread goes through the hexes between them"
    columns = {ref[0] for ref in result.traced}
    assert min(columns) < 32 < max(columns), "and it crosses the seam"


def test_two_hexes_across_a_seam_are_neighbours():
    composed = compose([Placement(board(83)), Placement(board(84))], EAST, TERRAIN)
    assert composed.adjacent((31, 5), (32, 5))
    assert composed.adjacent((32, 5), (33, 5))


def test_a_road_runs_across_a_seam():
    """FR-24 puts a road entry on each edge, so a road crosses each join."""
    composed = compose([Placement(board(85)), Placement(board(86))], EAST, TERRAIN)
    assert composed.hex((32, 5)).road
    assert composed.hex((32, 6)).road


def test_a_composition_that_does_not_agree_at_a_seam_says_where():
    """A hand-made board that breaks FR-24 must not compose in silence."""
    from slcore.state import Board, Hex, default_polygons

    good = board(87)
    hexes = []
    for h in good:
        kind = "woods" if (h.col, h.row) == (0, 5) else h.terrain
        hexes.append(
            Hex(
                col=h.col,
                row=h.row,
                terrain=kind,
                elevation=h.elevation,
                road=h.road and kind != "woods",
                building=h.building,
                hexsides=h.hexsides,
                sewer=h.sewer,
                polygons=default_polygons(h.col, h.row, kind, TERRAIN),
            )
        )
    broken = Board(good.cols, good.rows, hexes, TERRAIN, name="broken")
    with pytest.raises(CompositionError) as exc:
        compose([Placement(board(88)), Placement(broken)], EAST, TERRAIN)
    assert "seam" in str(exc.value)


# --------------------------------------------------------- a scenario on two boards


def test_a_scenario_plays_on_a_composition():
    from slcli.play import build_engine

    engine = build_engine("s00c_two_board_advance")
    assert engine.board.cols == 65
    assert engine.board.rows == 10
    state = engine.new_game(5)
    assert state.units
    columns = set()
    for side in engine.scenario.sides:
        for group in side.groups:
            columns.update(ref[0] for ref in group.area.resolve(engine.board))
    assert min(columns) < 32 < max(columns), "the two sides set up on different boards"


def test_a_game_on_a_composition_replays():
    """A composition is one board, so a game on it is a seed and a command log like any other."""
    from slcli.play import build_engine, make_agent, play_game

    engine = build_engine("s00c_two_board_advance")
    first = play_game(engine, 5, (make_agent("v1", engine, 5, 0), make_agent("v1", engine, 5, 1)))
    second = play_game(engine, 5, (make_agent("v1", engine, 5, 0), make_agent("v1", engine, 5, 1)))
    assert first.hashes == second.hashes
    assert first.result == second.result
