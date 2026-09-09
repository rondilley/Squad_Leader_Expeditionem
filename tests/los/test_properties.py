"""Property tests for LOS (TR-03): symmetry, adjacency, and blind hexes."""

from __future__ import annotations

from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from slcore import geometry
from slcore.los_cache import LosTable
from slcore.los_eval import evaluate
from slcore.state import Board, Building, Hex, default_polygons
from sldata.loaders import load_terrain

COLS = 7
ROWS = 6
TERRAIN = load_terrain()

KINDS = ["open", "open", "open", "woods", "stone_building", "wooden_building", "wheat", "shellhole"]


def all_refs():
    out = []
    for col in range(COLS):
        first = 0 if col & 1 else 1
        for row in range(first, ROWS + 1):
            out.append((col, row))
    return out


REFS = all_refs()


@st.composite
def boards(draw):
    kinds = draw(st.lists(st.sampled_from(KINDS), min_size=len(REFS), max_size=len(REFS)))
    building_ids = draw(st.lists(st.integers(0, 3), min_size=len(REFS), max_size=len(REFS)))
    walls = draw(st.lists(st.tuples(st.sampled_from(REFS), st.integers(0, 5)), max_size=3))
    sizes: dict[str, int] = {}
    keys: dict[tuple[int, int], str] = {}
    for r, kind, bid in zip(REFS, kinds, building_ids):
        if TERRAIN[kind].building:
            key = f"{kind}-{bid}"
            keys[r] = key
            sizes[key] = sizes.get(key, 0) + 1
    sides: dict[tuple[int, int], dict[int, str]] = {}
    for r, d in walls:
        other = geometry.neighbor(*r, d)
        if other not in REFS:
            continue
        sides.setdefault(r, {})[d] = "wall"
        sides.setdefault(other, {})[(d + 3) % 6] = "wall"
    hexes = []
    for r, kind in zip(REFS, kinds):
        building = None
        if r in keys:
            key = keys[r]
            building = Building(key, "stone" if kind == "stone_building" else "wooden", sizes[key])
        hs: list[str | None] = [None] * 6
        for d, f in sides.get(r, {}).items():
            hs[d] = f
        hexes.append(Hex(col=r[0], row=r[1], terrain=kind, building=building, hexsides=tuple(hs), polygons=default_polygons(r[0], r[1], kind, TERRAIN)))
    return Board(COLS, ROWS, hexes, TERRAIN)


pairs = st.tuples(st.sampled_from(REFS), st.sampled_from(REFS))


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(boards(), pairs)
def test_los_is_symmetric(board, pair):
    a, b = pair
    table = LosTable(board)
    ab = evaluate(board, table, a, b)
    ba = evaluate(board, table, b, a)
    assert ab.clear == ba.clear, (geometry.hex_id(*a), geometry.hex_id(*b), ab, ba)
    assert ab.hindrance == ba.hindrance


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(boards())
def test_adjacent_hexes_always_have_los(board):
    table = LosTable(board)
    for a in board.order:
        for b in board.neighbors(a):
            r = evaluate(board, table, a, b)
            assert r.clear and r.rule_id == "7.8"


@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(boards(), st.sampled_from(REFS), st.integers(2, ROWS))
def test_blind_hex_behind_an_obstacle_in_a_column(board, firer, span):
    """Rule 7.4: a multi-story firer sees over woods and small buildings in its
    column, except the hex directly behind each obstacle and any multi-story
    building. A ground-level firer is blocked by the first obstacle."""
    col, row = firer
    target = (col, row + span)
    assume(target in board)
    table = LosTable(board)
    between = [(col, r) for r in range(row + 1, row + span)]
    obstacle = [board.los_class(board.hex(h).terrain) == "block" for h in between]
    ms_between = [board.hex(h).building is not None and board.hex(h).building.multi_story and board.los_class(board.hex(h).terrain) == "block" for h in between]
    fb = board.hex(firer).building
    tb = board.hex(target).building
    firer_ms = fb is not None and fb.multi_story
    target_ms = tb is not None and tb.multi_story
    walls = any(board.hexside(a, 3) in ("wall", "hedge") for a in between[:-1]) if len(between) > 1 else False
    r = evaluate(board, table, firer, target)
    if walls and not (firer_ms or target_ms):
        assert not r.clear and r.rule_id == "11.51"
        return
    if fb is not None and tb is not None and fb.id == tb.id and any(board.is_building_kind(board.hex(h).terrain) for h in between):
        assert not r.clear and r.rule_id == "7.7"
        return
    if any(ms_between):
        assert not r.clear and r.rule_id == "7.5"
        return
    if not firer_ms and not target_ms:
        assert r.clear == (not any(obstacle))
        return
    expect_blocked = False
    if (not target_ms or firer_ms) and obstacle[-1]:
        expect_blocked = True
    if (not firer_ms or target_ms) and obstacle[0]:
        expect_blocked = True
    assert r.clear == (not expect_blocked), (r, obstacle, firer_ms, target_ms)
