"""TC-05: random legal games from many seeds replay to the same hash sequence."""

import pytest

from slagents.base import RandomAgent
from slagents.scripted.v0 import ScriptedV0
from slcore.commands import Command
from slcore.game import State
from slcli.play import build_engine, play_game, replay_record

SEEDS = list(range(1, 25))


@pytest.fixture(scope="module")
def engine():
    return build_engine("s00_movement_drill")


@pytest.mark.parametrize("seed", SEEDS)
def test_random_game_replays(engine, seed):
    record = play_game(engine, seed, (RandomAgent(seed, 0), RandomAgent(seed, 1)))
    assert record.result == "no_result"
    assert replay_record(engine, record)
    assert len(set(record.hashes)) == len(record.hashes), "each command changes the hash"


def test_scripted_game_replays_and_reaches_the_objective(engine):
    record = play_game(engine, 5, (ScriptedV0(engine, 0), ScriptedV0(engine, 1)))
    assert replay_record(engine, record)
    moves = [c for c in record.commands if c["payload"]["action"] in ("move", "stack_move", "advance")]
    assert len(moves) > 10


def test_state_document_round_trip(engine):
    record = play_game(engine, 3, (RandomAgent(3, 0), RandomAgent(3, 1)))
    state = engine.new_game(3)
    for c in record.commands[:40]:
        state, _ = engine.apply(state, Command.from_payload(c["payload"]))
    again = State.from_dict(state.to_dict())
    assert again == state
    assert engine.hash_state(again) == engine.hash_state(state)


def test_two_engines_agree(engine):
    other = build_engine("s00_movement_drill")
    record = play_game(engine, 11, (RandomAgent(11, 0), RandomAgent(11, 1)))
    hashes = other.replay(11, [c["payload"] for c in record.commands])
    assert hashes == record.hashes
