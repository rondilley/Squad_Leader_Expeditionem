"""The memory of a game worker stays bounded (2026-10-17).

A library search plays 100 candidates in each worker. With no limit, a worker kept an
engine for each candidate, and the line of sight table of each engine grew with each game.
The farm hosts of 30 workers ran out of memory on the slots of two to four boards.
"""

from __future__ import annotations

from collections import OrderedDict

from slcli import gauntlet
from slcli.play import build_engine, make_agent, play_game

SCENARIOS = (
    "s01_guards_counterattack",
    "s02_tractor_works",
    "s03a_streets_of_stalingrad",
    "s04_armor_probe",
    "lib01_grain_office",
    "lib02_pump_house",
)


def test_the_cache_keeps_the_last_scenarios_only(monkeypatch):
    monkeypatch.setattr(gauntlet, "_ENGINES", OrderedDict())
    for name in SCENARIOS:
        engine = gauntlet._engine_for(name, name)
        assert engine.scenario.id == name
    assert len(gauntlet._ENGINES) == gauntlet.ENGINE_LIMIT
    assert list(gauntlet._ENGINES) == list(SCENARIOS[-gauntlet.ENGINE_LIMIT:])


def test_a_scenario_in_the_cache_is_the_same_engine(monkeypatch):
    monkeypatch.setattr(gauntlet, "_ENGINES", OrderedDict())
    first = gauntlet._engine_for(SCENARIOS[0], SCENARIOS[0])
    assert gauntlet._engine_for(SCENARIOS[0], SCENARIOS[0]) is first


def _hashes(engine, seed):
    agents = (make_agent("v3", engine, seed, 0), make_agent("v3", engine, seed, 1))
    return play_game(engine, seed, agents).hashes


def test_a_game_after_a_clear_of_the_line_of_sight_table_is_the_same_game():
    """The table holds results that read the board only, so a clear changes no answer."""
    engine = build_engine("s01_guards_counterattack", None)
    first = _hashes(engine, 5)
    assert engine.los.entries() > 0
    engine.los.clear()
    assert engine.los.entries() == 0
    assert _hashes(engine, 5) == first
    assert _hashes(build_engine("s01_guards_counterattack", None), 5) == first


def test_a_worker_clears_a_table_above_the_limit_and_keeps_one_below_it(monkeypatch):
    engine = build_engine("s01_guards_counterattack", None)
    _hashes(engine, 5)
    held = engine.los.entries()
    gauntlet._trim(engine)
    assert engine.los.entries() == held
    monkeypatch.setattr(gauntlet, "LOS_ENTRY_LIMIT", held - 1)
    gauntlet._trim(engine)
    assert engine.los.entries() == 0
