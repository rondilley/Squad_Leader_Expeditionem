"""P1 item 3: the fast `with_` gives the `dataclasses.replace` copy, with no memo.

`slcore.units.copy_with` copies the attribute dictionary of a frozen record and drops
each name of `MEMO_ATTRIBUTES`. A memo that a copy kept would be wrong for the copy: the
hash of the old state, its unit index, its rout searches, or its hex loads. So the test
plays real games, finds each attribute of each state and unit that is not a field, and
fails when one of them is not in the list.
"""

from __future__ import annotations

import dataclasses

import pytest

from slagents.base import RandomAgent, decide
from slcore import game, hashing, player_state
from slcore.game import STATE_FIELDS, State
from slcore.rules import r06_stacking, r13_rout
from slcore.units import MEMO_ATTRIBUTES, UNIT_FIELDS, Unit

from perf.fixture_engines import fixture_engine


def _extra_names(record) -> set[str]:
    names = STATE_FIELDS if isinstance(record, State) else UNIT_FIELDS
    return set(record.__dict__) - names


def test_each_memo_name_of_the_core_is_in_the_list():
    for name in (
        hashing.CACHE_ATTRIBUTE,
        hashing.UNIT_JSON_ATTRIBUTE,
        game.INDEX_ATTRIBUTE,
        r13_rout.ROUT_MEMO_ATTRIBUTE,
        r06_stacking.LOAD_MEMO_ATTRIBUTE,
        player_state.OFF_BOARD_ATTRIBUTE,
    ):
        assert name in MEMO_ATTRIBUTES


@pytest.mark.parametrize("scenario", ["s01_guards_counterattack", "s04_armor_probe"])
def test_a_game_leaves_no_memo_that_the_copy_keeps(scenario):
    engine = fixture_engine(scenario)
    found: set[str] = set()
    for seed in (1, 2):
        agents = (RandomAgent(seed, 0), RandomAgent(seed, 1))
        state = engine.new_game(seed)
        while not state.game_over:
            frame = engine.legal_commands(state)
            # The agent reads the player state, as in play, so its memo is in the scan too.
            chosen = decide(agents[state.active], state, frame)
            before = state
            state, _ = engine.apply(state, frame.by_id(chosen).command, frame)
            engine.hash_state(state)
            found |= _extra_names(before)
            for unit in before.units:
                found |= _extra_names(unit)
            # A copy of a state that holds memos has none of them.
            copy = before.with_(seq=before.seq)
            assert not _extra_names(copy)
            assert copy == before
    unknown = found - set(MEMO_ATTRIBUTES)
    assert not unknown, f"a memo that with_ does not drop: {sorted(unknown)}"
    # The game did make memos, so the check above looked at something.
    assert {hashing.CACHE_ATTRIBUTE, game.INDEX_ATTRIBUTE, hashing.UNIT_JSON_ATTRIBUTE} <= found


def test_the_copy_is_the_replace_copy():
    engine = fixture_engine("s01_guards_counterattack")
    state = engine.new_game(3)
    engine.hash_state(state)
    hashing.state_bytes(state)
    unit = state.units[2]
    fast = unit.with_(hex=(4, 4), broken=True)
    slow = dataclasses.replace(unit, hex=(4, 4), broken=True)
    assert fast == slow and type(fast) is Unit
    assert fast.__dict__ == slow.__dict__
    moved = state.with_unit(fast)
    assert moved == dataclasses.replace(state, units=tuple(fast if u.id == fast.id else u for u in state.units))
    assert not _extra_names(moved)
    assert hashing.hash_state(moved) != hashing.hash_state(state)
    changed = state.with_units({1: state.units[1].with_(stay=True), 2: fast})
    assert changed.units[1].stay and changed.units[2] is fast


def test_a_copy_with_an_unknown_field_is_an_error():
    engine = fixture_engine("s00_movement_drill")
    state = engine.new_game(1)
    with pytest.raises(TypeError):
        state.with_(no_such_field=1)
    with pytest.raises(TypeError):
        state.units[0].with_(no_such_field=1)
