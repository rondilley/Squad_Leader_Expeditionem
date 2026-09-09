"""The contract of the three public functions, and the memos that speed them up.

A memo must not change an answer. These tests compare the memoized path with a fresh
engine and with an explicit context.
"""

from __future__ import annotations

import pytest

from slcore import geometry
from slcore.commands import Command
from slcore.engine import IllegalCommand
from slcore.frame import DecisionFrame
from slcore.hashing import CACHE_ATTRIBUTE, hash_state, state_bytes
from slcore.los_cache import LosTable
from slcore.los_eval import LosContext, evaluate
from slcli.play import build_engine

from los.fixture_board import build_fixture


@pytest.fixture(scope="module")
def engine():
    return build_engine("s00_movement_drill")


def test_apply_refuses_a_frame_that_does_not_belong_to_the_state(engine):
    state = engine.new_game(1)
    frame = engine.legal_commands(state)
    command = frame.commands[0].command
    state2, _ = engine.apply(state, command, frame)
    stale = DecisionFrame(frame.frame_id, frame.player, frame.phase, frame.sub_step, frame.turn, frame.commands)
    assert stale.frame_id != engine.hash_state(state2)
    with pytest.raises(IllegalCommand):
        engine.apply(state2, command, stale), "the same placement is not legal a second time"


def test_a_frame_from_another_state_does_not_widen_the_legal_list(engine):
    """A frame with a command that is not legal now must not let that command through."""
    state = engine.new_game(1)
    frame = engine.legal_commands(state)
    place = next(lc for lc in frame.commands if lc.command.action == "place")
    state2, _ = engine.apply(state, place.command, frame)
    with pytest.raises(IllegalCommand):
        engine.apply(state2, place.command, frame)


def test_the_state_hash_memo_is_not_part_of_the_record(engine):
    state = engine.new_game(3)
    first = hash_state(state)
    assert getattr(state, CACHE_ATTRIBUTE) == first
    assert CACHE_ATTRIBUTE not in state.to_dict()
    again = state.with_(seq=state.seq)
    assert not hasattr(again, CACHE_ATTRIBUTE), "a copy carries no memo"
    assert hash_state(again) == first
    changed = state.with_(seq=state.seq + 1)
    assert hash_state(changed) != first
    assert state_bytes(state) != state_bytes(changed)


def test_the_line_of_sight_memo_gives_the_answer_of_a_fresh_table():
    board = build_fixture()
    warm = LosTable(board)
    refs = board.order[::5]
    for a in refs:
        for b in refs:
            if a == b:
                continue
            evaluate(board, warm, a, b)
    fresh = LosTable(board)
    for a in refs:
        for b in refs:
            if a == b:
                continue
            assert evaluate(board, warm, a, b) == evaluate(board, fresh, a, b), (a, b)


def test_a_context_with_smoke_is_not_served_from_the_memo():
    board = build_fixture()
    table = LosTable(board)
    a = geometry.parse_hex_id("I4")
    b = geometry.parse_hex_id("I7")
    plain = evaluate(board, table, a, b)
    assert plain.hindrance == 2
    smoky = evaluate(board, table, a, b, ctx=LosContext(smoke=frozenset({geometry.parse_hex_id("I5")})))
    assert smoky.hindrance == 3
    assert evaluate(board, table, a, b).hindrance == 2, "the memo still holds the answer with no smoke"


def test_a_command_id_is_stable_across_equal_commands():
    a = Command("cc_attack", units=(1,), extra=(("targets", (2, 3)),))
    b = Command.from_payload(a.payload())
    assert b == a
    assert a.id == b.id
    assert a.payload()["targets"] == [2, 3], "a sequence value is a list in the payload"


def test_replay_gives_the_same_hashes_with_and_without_a_frame(engine):
    from slagents.base import RandomAgent

    state = engine.new_game(9)
    agents = (RandomAgent(9, 0), RandomAgent(9, 1))
    with_frame = []
    payloads = []
    while not state.game_over:
        frame = engine.legal_commands(state)
        legal = frame.by_id(agents[state.active].select(state, frame))
        payloads.append(legal.payload)
        state, _ = engine.apply(state, legal.command, frame)
        with_frame.append(engine.hash_state(state))
    assert engine.replay(9, payloads) == with_frame
