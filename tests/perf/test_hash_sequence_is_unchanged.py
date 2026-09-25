"""P1 (slice 5 of the 2026-09-23 review): the speed work keeps each game the same.

Each case is one game with fixed agents and one seed, on the board document that
`tests/perf/boards/` holds for the scenario. The digest is SHA-256 over the command ID
and the state hash of each step, in sequence.

The values were recorded on 2026-09-23 with a copy of the tree from before the speed
work (the plain `json.dumps` hash, the full rout search, `dataclasses.replace`, and no
memo). A change that only makes the core faster keeps every digest. A change of a rule,
of a scenario file, or of a board document moves them, and the author names that
change when the value is recorded again.

The cases use the random agent and v1 only. The owner of v7 changes it often, so a v7
game is not a fixed input for a test of the core. The values are the same as the ones the
board generator work of the same day recorded for the version 8 boards.
"""

from __future__ import annotations

import hashlib

import pytest

from slcli.play import make_agent, play_game

from perf.fixture_engines import fixture_engine

# The last hash of v1 against v1 on scenario 1 with seed 1, on the fixture board.
V1_LAST_HASH = "70536aa16e433017435558e7fa700dbde11f945c0e1543da563021e5f0820fd7"

FAST_CASES = [
    ("s01_guards_counterattack", "random", 1, 844, "e5205ddcfd4309d468592a69a3096e66e0bb3cd2666ff895f18e11538329f5cf"),
    ("s01_guards_counterattack", "random", 2, 864, "4ce2d9bebe7241f58ce29b0be8d5970a571871cb7cc7fcb2c67b204d900988e4"),
    ("s01_guards_counterattack", "random", 3, 1063, "eeacef6e93dcfd3d1190cbb1cb2c2a9ad56664e20b5d16bc056206224661a799"),
    ("s01_guards_counterattack", "v1", 1, 771, "4e2e7d1e6c95a0bf5da3cdce73938ecfae31eaf4b10448e659cbb0a4f2f9b571"),
]

SLOW_CASES = [
    ("s02_tractor_works", "random", 1, 2358, "efdf25802bace0a28cbab8bd85d21b4873a20a4a84fff6424fd84e84be973dc7"),
    ("s02_tractor_works", "random", 2, 2551, "f115c29ecf9a6b94dfc49dfbc6ebe774c1118f344614b2a22d43d61ec2d2930e"),
    ("s02_tractor_works", "random", 3, 2315, "4482ee54b3b425d65912d66bd6efea857d8c9a85f7ad8f072a48ef0decba24e9"),
    ("s03a_streets_of_stalingrad", "random", 1, 3096, "a91eed97ebcf30fbe28013552b9232b7ca75565924eddeeba08f2d2dea5d8d72"),
    ("s03a_streets_of_stalingrad", "random", 2, 2907, "539fe6dd397bdf674de47fbb452fcff5d5e900e7ae3d3ad3659e446db0021690"),
    ("s03a_streets_of_stalingrad", "random", 3, 2846, "5fedcf5896745de87084dc410507054e515aca71f21a82d2e46dcf07d9ab22f1"),
    ("s04_armor_probe", "random", 1, 534, "69885e2acc8ed6ad70e0908f5e81f5c720edd99f53c137280524e75cee16d66d"),
    ("s04_armor_probe", "random", 2, 551, "857bafd84c00b64293fc371b73d9bbcd8aa4519d97a3f8a0cec8f2adee22cd6b"),
    ("s04_armor_probe", "random", 3, 573, "930fe1569800c3ad1c49370ba2a4a705c51b9ffddac602bfed5f96a8442aba1c"),
]

_ENGINES: dict[str, object] = {}


def _engine(scenario: str):
    if scenario not in _ENGINES:
        _ENGINES[scenario] = fixture_engine(scenario)
    return _ENGINES[scenario]


def _play(scenario: str, kind: str, seed: int):
    engine = _engine(scenario)
    record = play_game(engine, seed, (make_agent(kind, engine, seed, 0), make_agent(kind, engine, seed, 1)))
    digest = hashlib.sha256()
    for logged in record.commands:
        digest.update(logged["command_id"].encode("ascii"))
        digest.update(logged["hash"].encode("ascii"))
    return engine, record, digest.hexdigest()


def _check(scenario: str, kind: str, seed: int, steps: int, expected: str) -> None:
    engine, record, digest = _play(scenario, kind, seed)
    assert len(record.commands) == steps
    assert digest == expected, f"{scenario} {kind} seed {seed}: the command and hash sequence changed"
    # The replay of the command log gives the same hash sequence (TR-02).
    assert engine.replay(seed, [c["payload"] for c in record.commands]) == record.hashes


@pytest.mark.parametrize("scenario,kind,seed,steps,expected", FAST_CASES)
def test_the_fast_games_keep_their_sequence(scenario, kind, seed, steps, expected):
    _check(scenario, kind, seed, steps, expected)


def test_v1_against_v1_ends_on_the_recorded_hash():
    _, record, _ = _play("s01_guards_counterattack", "v1", 1)
    assert record.hashes[-1] == V1_LAST_HASH


@pytest.mark.slow
@pytest.mark.parametrize("scenario,kind,seed,steps,expected", SLOW_CASES)
def test_the_long_games_keep_their_sequence(scenario, kind, seed, steps, expected):
    _check(scenario, kind, seed, steps, expected)
