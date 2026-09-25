"""P1 item 2: the rout search that stops at the nearest cover gives the full search's answer.

The reference here is the search of rule 13.43 as the core had it before: Dijkstra over
the whole board, then the nearest cover hexes of all the hexes it reached. The test
compares the destinations and the route to each of them, on each broken unit of the
Rout Phases of real games.
"""

from __future__ import annotations

import pytest

from slagents.base import RandomAgent
from slcore import geometry
from slcore.game import PHASE_ROUT
from slcore.paths import route, shortest_paths
from slcore.rules import r06_stacking, r11_terrain, r13_rout

from perf.fixture_engines import fixture_engine


def _reference_allowed(ctx, types, state, unit, enemies):
    """The step test of rule 13.42 as it was, with no memo."""
    board = ctx.move.board
    start = unit.hex

    def allowed(prev, nxt):
        if state.enemy_counter_in(nxt, unit.player):
            return False
        for u in state.infantry_in(nxt):
            if u.player != unit.player and not u.hidden:
                return False
        for enemy in enemies:
            if enemy.hex is not None and geometry.distance(nxt, enemy.hex) < geometry.distance(start, enemy.hex):
                return False
        if r11_terrain.is_open_ground(board, nxt) and not r13_rout.behind_cover_hexside(board, prev, nxt):
            for enemy in enemies:
                if r13_rout.in_range_and_los(ctx, types, enemy, nxt):
                    return False
        return True

    return allowed


def _reference(ctx, types, state, unit):
    enemies = r13_rout.known_enemies(ctx, state, unit)
    allowed = _reference_allowed(ctx, types, state, unit, enemies)
    dist, pred = shortest_paths(ctx.move, unit.hex, allowed)
    best = None
    out = []
    for ref, cost in sorted(dist.items()):
        if ref == unit.hex or not r13_rout.is_cover(ctx.move.board, ref):
            continue
        if r06_stacking.rule_6_1_overstacked(state, types, ref, unit.player, extra_ids=(unit.id,)):
            continue
        if r13_rout.adjacent_enemy(state, unit.with_(hex=ref)):
            continue
        if best is None or cost < best:
            best = cost
            out = [ref]
        elif cost == best:
            out.append(ref)
    return out, pred


def _rout_states(engine, seeds):
    for seed in seeds:
        agents = (RandomAgent(seed, 0), RandomAgent(seed, 1))
        state = engine.new_game(seed)
        while not state.game_over:
            if state.phase == PHASE_ROUT:
                yield state
            frame = engine.legal_commands(state)
            chosen = agents[state.active].select(state, frame)
            state, _ = engine.apply(state, frame.by_id(chosen).command, frame)


@pytest.mark.parametrize("scenario,seeds", [("s01_guards_counterattack", (1, 2, 3, 4)), ("s00b_combined_forces", (1,))])
def test_the_bounded_search_gives_the_full_answer(scenario, seeds):
    engine = fixture_engine(scenario)
    ctx, types = engine.rout_ctx, engine.types
    checked = 0
    for state in _rout_states(engine, seeds):
        for unit in r13_rout.broken_units(state, state.active):
            expected, full_pred = _reference(ctx, types, state, unit)
            assert r13_rout.rout_options(ctx, types, state, unit) == expected
            options, pred = r13_rout._rout_search(ctx, types, state, unit)
            for dest in options:
                assert route(pred, unit.hex, dest) == route(full_pred, unit.hex, dest)
            assert r13_rout.hopeless(ctx, types, state, unit) == (r13_rout.must_rout(ctx, state, unit) and not expected)
            checked += 1
    assert checked > 20


def test_the_search_is_kept_for_the_unit_of_the_state_only():
    engine = fixture_engine("s01_guards_counterattack")
    ctx, types = engine.rout_ctx, engine.types
    for state in _rout_states(engine, (1, 2, 3)):
        broken = r13_rout.broken_units(state, state.active)
        if not broken:
            continue
        unit = broken[0]
        first = r13_rout._rout_search(ctx, types, state, unit)
        assert r13_rout._rout_search(ctx, types, state, unit) is not None
        assert state.__dict__[r13_rout.ROUT_MEMO_ATTRIBUTE][unit.id][2] == first[0]
        # A unit that an agent changed is not the unit of the state: no memo is read or kept.
        moved = unit.with_(broken=True)
        assert moved is not state.units[unit.id]
        assert r13_rout.rout_options(ctx, types, state, moved) == _reference(ctx, types, state, moved)[0]
        return
    pytest.fail("no Rout Phase with a broken unit in three games")
