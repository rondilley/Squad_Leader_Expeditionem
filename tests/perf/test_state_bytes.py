"""P1 item 1: the state text from the unit JSON cache is the full canonical JSON.

`slcore.hashing.state_bytes` puts the kept JSON text of each unit in the place of the
unit list. These tests compare its bytes with `json.dumps(state.to_dict())` with the
canonical options, on each state of real games of each scenario.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from slagents.base import RandomAgent
from slcore import hashing

from perf.fixture_engines import fixture_engine

STEPS_PER_GAME = 700


def _canonical(document) -> bytes:
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _states(scenario: str, seeds: tuple[int, ...]):
    engine = fixture_engine(scenario)
    for seed in seeds:
        agents = (RandomAgent(seed, 0), RandomAgent(seed, 1))
        state = engine.new_game(seed)
        yield state
        steps = 0
        while not state.game_over and steps < STEPS_PER_GAME:
            frame = engine.legal_commands(state)
            chosen = agents[state.active].select(state, frame)
            state, _ = engine.apply(state, frame.by_id(chosen).command, frame)
            steps += 1
            yield state


def _compare(scenario: str, seeds: tuple[int, ...]) -> int:
    count = 0
    for state in _states(scenario, seeds):
        full = _canonical(state.to_dict())
        assert hashing.state_bytes(state) == full
        # A second read uses the kept unit texts and gives the same bytes.
        assert hashing.state_bytes(state) == full
        document = state.to_dict()
        del document["seq"]
        assert hashing.position_key(state) == hashlib.sha256(_canonical(document)).hexdigest()
        count += 1
    return count


@pytest.mark.parametrize("scenario", ["s00_movement_drill", "s01_guards_counterattack"])
def test_the_state_bytes_are_the_canonical_json(scenario):
    assert _compare(scenario, (1, 2)) > 200


@pytest.mark.slow
@pytest.mark.parametrize(
    "scenario",
    ["s00b_combined_forces", "s00c_two_board_advance", "s02_tractor_works", "s03a_streets_of_stalingrad", "s04_armor_probe"],
)
def test_the_state_bytes_are_the_canonical_json_in_the_long_scenarios(scenario):
    assert _compare(scenario, (1, 2)) > 200


def test_a_changed_unit_gets_new_text():
    engine = fixture_engine("s00_movement_drill")
    state = engine.new_game(5)
    hashing.state_bytes(state)
    unit = state.units[0]
    moved = state.with_unit(unit.with_(hex=(3, 5), moved=True))
    assert hashing.UNIT_JSON_ATTRIBUTE not in moved.units[0].__dict__
    assert hashing.state_bytes(moved) == _canonical(moved.to_dict())
    assert hashing.hash_state(moved) != hashing.hash_state(state)
