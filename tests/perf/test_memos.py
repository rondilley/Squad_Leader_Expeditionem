"""P1 items 4 to 6: each memo and each short form of the speed work gives the answer of
the long form it replaces."""

from __future__ import annotations

import random

import pytest

from slagents.base import RandomAgent
from slcore import geometry
from slcore.los_cache import LosTable, load_static, static_snapshot, warm_static
from slcore.los_eval import evaluate
from slcore.rules import r06_stacking
from slcore.rules.r05_movement import _entry_cost, entry_cost_halves
from slcore.scenario import SetupArea
from slcore.units import KIND_CREW, KIND_SQUAD, KIND_SW, KIND_VEHICLE

from perf.fixture_engines import fixture_engine


def _states(engine, seeds, limit=600):
    for seed in seeds:
        agents = (RandomAgent(seed, 0), RandomAgent(seed, 1))
        state = engine.new_game(seed)
        steps = 0
        while not state.game_over and steps < limit:
            yield state
            frame = engine.legal_commands(state)
            chosen = agents[state.active].select(state, frame)
            state, _ = engine.apply(state, frame.by_id(chosen).command, frame)
            steps += 1


# ------------------------------------------------------------------ geometry


def _center_distance(a, b):
    ax, ay = geometry.center(*a)
    bx, by = geometry.center(*b)
    dcol = abs(bx - ax) // geometry.COL_STEP
    dy = abs(by - ay)
    return dcol if dy <= dcol else dcol + (dy - dcol) // 2


def _center_direction(a, b):
    ax, ay = geometry.center(*a)
    bx, by = geometry.center(*b)
    for d, offset in enumerate(geometry.DIRECTIONS):
        if offset == (bx - ax, by - ay):
            return d
    return None


def test_the_short_geometry_gives_the_lattice_answer():
    hexes = [(c, r) for c in range(-2, 36) for r in range(-2, 24)]
    rng = random.Random(7)
    for a in hexes:
        for d in range(6):
            cx, cy = geometry.center(*a)
            dx, dy = geometry.DIRECTIONS[d]
            assert geometry.neighbor(*a, d) == geometry.hex_from_center(cx + dx, cy + dy)
        for b in rng.sample(hexes, 60) + [geometry.neighbor(*a, d) for d in range(6)]:
            assert geometry.distance(a, b) == _center_distance(a, b)
            assert geometry.direction_to(a, b) == _center_direction(a, b)


# ------------------------------------------------------------------ entry costs


def test_the_kept_entry_cost_is_the_calculated_one():
    engine = fixture_engine("s01_guards_counterattack")
    ctx = engine.move_ctx
    for ref in engine.board.order:
        for d in range(6):
            nxt = geometry.neighbor(*ref, d)
            if nxt in engine.board:
                assert entry_cost_halves(ctx, ref, nxt) == _entry_cost(ctx, ref, nxt)
                assert entry_cost_halves(ctx, ref, nxt) == _entry_cost(ctx, ref, nxt)


# ------------------------------------------------------------------ LOS table


def test_a_loaded_los_snapshot_gives_the_lazy_answers():
    engine = fixture_engine("s00_movement_drill")
    filled = LosTable(engine.board)
    count = warm_static(filled)
    assert count == len(engine.board.order) ** 2
    snapshot = static_snapshot(filled)
    fresh = fixture_engine("s00_movement_drill")
    assert load_static(fresh.los, snapshot) == count
    lazy = LosTable(engine.board)
    for a in engine.board.order:
        for b in engine.board.order:
            assert fresh.los.static_results[(a, b)] == evaluate(engine.board, lazy, a, b)


def test_a_snapshot_of_another_board_is_refused():
    small = fixture_engine("s00_movement_drill")
    other = fixture_engine("s01_guards_counterattack")
    snapshot = static_snapshot(small.los)
    with pytest.raises(ValueError):
        load_static(other.los, snapshot)


def test_a_game_on_a_loaded_table_keeps_its_hashes():
    first = fixture_engine("s00_movement_drill")
    second = fixture_engine("s00_movement_drill")
    warm_static(second.los)
    third = fixture_engine("s00_movement_drill")
    load_static(third.los, static_snapshot(second.los))
    payloads = []
    hashes = []
    agents = (RandomAgent(9, 0), RandomAgent(9, 1))
    state = first.new_game(9)
    while not state.game_over:
        frame = first.legal_commands(state)
        chosen = frame.by_id(agents[state.active].select(state, frame))
        state, _ = first.apply(state, chosen.command, frame)
        payloads.append(chosen.payload)
        hashes.append(first.hash_state(state))
    assert third.replay(9, payloads) == hashes


def _reference_evaluate(board, table, firer, target, ctx):
    """The evaluator with a context as it was: the trace is made again for each call."""
    from slcore.los_eval import _result, _search_clear, resolve_choices
    from slcore.rules import r07_los

    thread = table.thread(firer, target)
    traced, made = resolve_choices(board, thread, None)
    verdict = r07_los.evaluate_traced(board, firer, target, traced)
    if not verdict.clear and any(s.choice for s in thread.steps):
        alt = _search_clear(board, thread, firer, target)
        if alt is not None:
            traced, made, verdict = alt
    return _result(board, thread, firer, target, traced, made, verdict, ctx)


def test_the_kept_trace_gives_the_result_with_smoke_and_vehicles():
    from slcore.los_eval import LosContext

    engine = fixture_engine("s04_armor_probe")
    board = engine.board
    rng = random.Random(11)
    refs = list(board.order)
    fresh = LosTable(board)
    for _ in range(40):
        ctx = LosContext(
            smoke=frozenset(rng.sample(refs, rng.randint(0, 4))),
            vehicles=frozenset(rng.sample(refs, rng.randint(0, 5))),
        )
        for _ in range(60):
            firer, target = rng.choice(refs), rng.choice(refs)
            assert evaluate(board, engine.los, firer, target, ctx) == _reference_evaluate(board, fresh, firer, target, ctx)
            # The static answer after a call with a context is still the static answer.
            assert evaluate(board, engine.los, firer, target) == _reference_evaluate(board, fresh, firer, target, LosContext())


# ------------------------------------------------------------------ set up zones


def test_the_kept_zone_is_the_zone_of_the_board():
    engine = fixture_engine("s01_guards_counterattack")
    other = fixture_engine("s02_tractor_works")
    for side in engine.scenario.sides:
        for g in side.groups:
            first = g.area.resolve(engine.board)
            assert first == g.area._resolve(engine.board)
            assert g.area.resolve(engine.board) is first
    area = SetupArea(zone="columns", params=(("min_col", 0), ("max_col", 2)))
    one = area.resolve(engine.board)
    two = area.resolve(other.board)
    assert one == area._resolve(engine.board) and two == area._resolve(other.board)
    assert area == SetupArea(zone="columns", params=(("min_col", 0), ("max_col", 2)))


# ------------------------------------------------------------------ hex loads


def _reference_load(state, types, hex_ref, player, extra_ids=(), without_ids=()):
    """The count of rule 6.1 as it was, with no memo."""
    counted = []
    seen = set()
    for u in state.units_in(hex_ref):
        if u.player != player or u.id in without_ids:
            continue
        counted.append(u)
        seen.add(u.id)
    for uid in extra_ids:
        if uid in seen:
            continue
        u = state.units[uid]
        if u.eliminated or u.player != player or uid in without_ids:
            continue
        counted.append(u)
        seen.add(uid)
    infantry = squads = portage = 0
    for u in counted:
        if u.kind == KIND_SW:
            portage += types[u.type_key].portage_squad_halves
            continue
        if u.kind == KIND_VEHICLE:
            continue
        infantry += 1
        if u.kind in (KIND_SQUAD, KIND_CREW):
            squads += 1
        for w in state.carried_by(u.id):
            if w.kind == KIND_SW:
                portage += types[w.type_key].portage_squad_halves
    return infantry, squads, -(-portage // 2)


@pytest.mark.parametrize("scenario", ["s01_guards_counterattack", "s04_armor_probe"])
def test_the_kept_hex_load_is_the_counted_one(scenario):
    engine = fixture_engine(scenario)
    types = engine.types
    rng = random.Random(3)
    checked = 0
    for state in _states(engine, (1, 2), limit=400):
        hexes = sorted({u.hex for u in state.units if u.hex is not None})
        ids = [u.id for u in state.units]
        for h in hexes:
            for player in (0, 1):
                cases = [((), ())]
                for _ in range(3):
                    cases.append((tuple(rng.sample(ids, rng.randint(1, 3))), ()))
                    cases.append((tuple(rng.sample(ids, 1)), tuple(rng.sample(ids, rng.randint(1, 2)))))
                for extra, without in cases:
                    got = r06_stacking.hex_load(state, types, h, player, extra, without)
                    assert got == _reference_load(state, types, h, player, extra, without)
                    checked += 1
    assert checked > 5000


# ------------------------------------------------------------------ decision frame


def test_the_engine_keeps_the_frame_of_the_last_state():
    engine = fixture_engine("s01_guards_counterattack")
    state = engine.new_game(4)
    frame = engine.legal_commands(state)
    assert engine.legal_commands(state) is frame
    assert engine._build_frame(state) == frame
    after, _ = engine.apply(state, frame.commands[0].command, frame)
    other = engine.legal_commands(after)
    assert other is not frame and other == engine._build_frame(after)
    # A second state object with the same content gets a frame equal to the first one.
    copy = state.with_(seq=state.seq)
    assert engine.legal_commands(copy) == frame


# ------------------------------------------------------------------ fire table


def test_the_kept_fire_table_result_is_the_table_result():
    engine = fixture_engine("s01_guards_counterattack")
    ift = engine.tables.ift
    for firepower in range(-2, 40):
        for roll in range(-8, 20):
            assert ift.lookup(firepower, roll) == ift._lookup(firepower, roll)
            assert ift.lookup(firepower, roll) == ift._lookup(firepower, roll)
