import pytest

from slcore import geometry
from slcore.los_cache import LosTable, build_thread
from slcore.los_eval import LosContext, evaluate, thread_hexes
from slcore.state import Board

from los.fixture_board import build_fixture


@pytest.fixture(scope="module")
def board() -> Board:
    return build_fixture()


@pytest.fixture(scope="module")
def table(board: Board) -> LosTable:
    return LosTable(board)


def ref(text: str):
    return geometry.parse_hex_id(text)


def ids(refs):
    return [geometry.hex_id(*r) for r in refs]


def test_straight_column_thread(table):
    t = table.thread(ref("G1"), ref("G10"))
    assert [s.choice for s in t.steps] == [False] * 8
    assert ids(t.hexes()) == ["G2", "G3", "G4", "G5", "G6", "G7", "G8", "G9"]


def test_row_thread_has_hexside_choices(table):
    t = table.thread(ref("C5"), ref("G5"))
    assert [ids(s.hexes) for s in t.steps] == [["D4", "D5"], ["E5"], ["F4", "F5"]]
    assert [s.choice for s in t.steps] == [True, False, True]


def test_diagonal_thread_alternates_edges_and_interiors(table):
    t = table.thread(ref("C1"), ref("E4"))
    assert [ids(s.hexes) for s in t.steps] == [["C2", "D1"], ["D2"], ["D3", "E3"]]
    assert ids(t.steps[2].kinds and t.steps[2].hexes) == ["D3", "E3"]
    assert t.steps[2].kinds[1] == frozenset({"woods"})
    assert t.steps[2].kinds[0] == frozenset()


def test_reverse_thread_is_reversed(board, table):
    sample = [r for r in board.order if (r[0] + r[1]) % 3 == 0]
    for i, a in enumerate(sample):
        for b in sample[i + 1:]:
            forward = build_thread(board, a, b)
            backward = build_thread(board, b, a)
            assert backward == forward.reversed(), (a, b)


def test_consecutive_traced_hexes_are_adjacent(board, table):
    for a in board.order[::7]:
        for b in board.order[::5]:
            if a == b:
                continue
            path = [a] + list(thread_hexes(table, a, b)) + [b]
            for x, y in zip(path, path[1:]):
                assert board.adjacent(x, y), (ids([a, b]), ids(path))


def test_sub_hex_polygon_is_crossed_only_when_the_line_enters_it(table):
    t = table.thread(ref("C3"), ref("C5"))
    assert ids(t.hexes()) == ["C4"]
    assert t.steps[0].kinds[0] == frozenset({"stone_building"})
    t = table.thread(ref("C3"), ref("B5"))
    assert ids(t.hexes()) == ["C4", "B4"]
    assert t.steps[0].kinds[0] == frozenset()


def test_explicit_choice_changes_the_verdict(board, table):
    auto = evaluate(board, table, ref("I5"), ref("G5"))
    assert auto.clear and ids(auto.traced) == ["H5"] and ids(auto.choices) == ["H5"]
    forced = evaluate(board, table, ref("I5"), ref("G5"), choices={0: ref("H4")})
    assert not forced.clear and forced.rule_id == "7.3" and forced.blocking_hex == ref("H4")
    with pytest.raises(ValueError):
        evaluate(board, table, ref("I5"), ref("G5"), choices={0: ref("H6")})


def test_hindrance_counts_wheat_and_smoke(board, table):
    r = evaluate(board, table, ref("I4"), ref("I7"))
    assert r.clear and r.hindrance == 2 and ids(r.traced) == ["I5", "I6"]
    r = evaluate(board, table, ref("H6"), ref("J6"))
    assert r.clear and r.hindrance == 0 and ids(r.traced) == ["I7"]
    r = evaluate(board, table, ref("H6"), ref("J6"), choices={0: ref("I6")})
    assert r.clear and r.hindrance == 1
    smoke = LosContext(smoke=frozenset({ref("I5"), ref("A1")}))
    r = evaluate(board, table, ref("I4"), ref("I7"), ctx=smoke)
    assert r.hindrance == 3 and ids(r.smoke_hexes) == ["I5"]


def test_build_all_fills_every_pair(board):
    table = LosTable(board)
    n = len(board)
    assert table.build_all() == n * (n - 1) // 2


def test_board_round_trip(board):
    data = board.to_dict()
    again = Board.from_dict(data, board.terrain)
    assert again.to_dict() == data
    assert again.by_id("C4").polygons == board.by_id("C4").polygons
    assert again.hexside(ref("F5"), 3) == "wall" and again.hexside(ref("F6"), 0) == "wall"
