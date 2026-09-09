from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from slcore import geometry
from slcore.geometry import Crossing


def test_column_labels_round_trip():
    assert geometry.column_label(0) == "A"
    assert geometry.column_label(25) == "Z"
    assert geometry.column_label(26) == "AA"
    assert geometry.column_label(32) == "GG"
    for col in range(40):
        assert geometry.column_index(geometry.column_label(col)) == col
    with pytest.raises(ValueError):
        geometry.column_index("AB")


def test_hex_id_round_trip():
    assert geometry.hex_id(2, 4) == "C4"
    assert geometry.parse_hex_id("GG10") == (32, 10)
    assert geometry.parse_hex_id("B0") == (1, 0)
    with pytest.raises(ValueError):
        geometry.parse_hex_id("7")


def test_center_and_parity():
    assert geometry.center(0, 1) == (0, 2)
    assert geometry.center(1, 0) == (3, 1)
    assert geometry.center(1, 10) == (3, 21)
    assert geometry.center(32, 10) == (96, 20)
    for col in range(33):
        first = 0 if col & 1 else 1
        for row in range(first, 11):
            assert geometry.hex_from_center(*geometry.center(col, row)) == (col, row)
    assert geometry.hex_from_center(1, 2) is None
    assert geometry.hex_from_center(0, 3) is None


def test_vertices_are_shared_with_neighbors():
    a = (4, 5)
    va = set(geometry.vertices(*a))
    for d in range(6):
        b = geometry.neighbor(*a, d)
        shared = va & set(geometry.vertices(*b))
        assert len(shared) == 2, (a, b, shared)
        v1, v2 = geometry.HEXSIDE_VERTICES[d]
        cx, cy = geometry.center(*a)
        assert shared == {(cx + v1[0], cy + v1[1]), (cx + v2[0], cy + v2[1])}


def test_neighbors_are_symmetric_and_direction_to():
    a = (5, 3)
    for d in range(6):
        b = geometry.neighbor(*a, d)
        assert geometry.neighbor(*b, (d + 3) % 6) == a
        assert geometry.direction_to(a, b) == d
        assert geometry.direction_to(b, a) == (d + 3) % 6
    assert geometry.direction_to((0, 1), (0, 3)) is None


def test_distance_examples():
    assert geometry.distance((0, 1), (0, 1)) == 0
    assert geometry.distance((0, 1), (1, 1)) == 1
    assert geometry.distance((0, 1), (0, 3)) == 2
    assert geometry.distance((0, 1), (2, 1)) == 2
    assert geometry.distance((0, 1), (1, 3)) == 3
    assert geometry.distance((2, 1), (4, 4)) == 4


@given(st.integers(0, 32), st.integers(0, 10), st.integers(0, 32), st.integers(0, 10))
def test_distance_is_a_metric_on_neighbors(c1, r1, c2, r2):
    a = (c1, r1)
    b = (c2, r2)
    d = geometry.distance(a, b)
    assert d == geometry.distance(b, a)
    if a != b:
        best = min(geometry.distance(n, b) for n in geometry.neighbors(*a))
        assert best == d - 1


def test_clip_interior_edge_and_vertex():
    hexagon = geometry.hex_polygon(1, 1)
    p = geometry.center(1, 0)
    q = geometry.center(1, 2)
    kind, clip = geometry.classify_crossing(p, q, hexagon)
    assert kind == Crossing.INTERIOR
    assert clip is not None and clip.t0 == Fraction(1, 4) and clip.t1 == Fraction(3, 4)
    p = geometry.center(0, 1)
    q = geometry.center(2, 1)
    kind, clip = geometry.classify_crossing(p, q, hexagon)
    assert kind == Crossing.EDGE
    assert clip is not None and clip.t0 == Fraction(1, 3) and clip.t1 == Fraction(2, 3)
    kind, clip = geometry.classify_crossing((1, 1), (1, 5), hexagon)
    assert kind == Crossing.NONE
    assert clip is not None and clip.t0 == clip.t1 == Fraction(1, 2)
    kind, clip = geometry.classify_crossing((2, 2), (2, 6), hexagon)
    assert kind == Crossing.INTERIOR
    kind, clip = geometry.classify_crossing((0, 0), (0, 4), hexagon)
    assert kind == Crossing.NONE
    assert clip is None


def test_normalize_polygon_rejects_bad_input():
    assert geometry.normalize_polygon([(0, 0), (0, 2), (2, 2)]) == ((2, 2), (0, 2), (0, 0))
    with pytest.raises(ValueError):
        geometry.normalize_polygon([(0, 0), (1, 1), (2, 2)])
    with pytest.raises(ValueError):
        geometry.normalize_polygon([(0, 0), (4, 0), (1, 1), (0, 4)])
