"""Scenario 4, the first game that plays the armor rules 28 to 41.

The conformance corpus proves each rule in a state that the harness builds. These tests
play real games, because a rule that holds in one built state can still be unreachable in
a game: no command offers it, or the phase never opens.
"""

from __future__ import annotations

import collections

import pytest

from slagents.base import RandomAgent
from slcli.play import build_engine, make_agent, play_game
from slcore.engine import Engine
from slcore.rules import r28_vehicles, r30_vehicle_movement, r33_afv_combat
from slcore.rules.r28_vehicles import VehicleNotAvailable
from slcore.scenario import scenario_from_dict
from slcore.tabledata import Tables
from sldata.loaders import load_all_counters, load_hexsides, load_tables, load_terrain

SCENARIO = "s04_armor_probe"
ARMOR_RULES = tuple(str(n) for n in range(28, 42))


def play_bounded(engine: Engine, seed: int, commands: int) -> collections.Counter:
    """The rule IDs that the first `commands` commands of one random game applied."""
    state = engine.new_game(seed)
    agents = (RandomAgent(seed, 0), RandomAgent(seed + 1, 1))
    seen: collections.Counter = collections.Counter()
    for _ in range(commands):
        if state.game_over:
            break
        frame = engine.legal_commands(state)
        if not frame.commands:
            break
        chosen = frame.by_id(agents[frame.player].select(state, frame))
        assert chosen is not None
        state, events = engine.apply(state, chosen.command, frame)
        seen.update(e.rule_id for e in events)
    return seen


def test_the_scenario_builds_with_its_vehicles_and_their_crews():
    engine = build_engine(SCENARIO)
    assert engine.has_vehicles
    state = engine.new_game(7)
    vehicles = r28_vehicles.vehicles(state)
    assert len(vehicles) == 6, "three tanks or guns for each side"
    for vehicle in vehicles:
        crew = r33_afv_combat.crew_for(state, vehicle.id)
        assert crew is not None, f"rule 33.9 needs a crew counter for vehicle {vehicle.id}"
        assert crew.hex is None, "a crew counter waits off the board until its vehicle dies"


def test_the_crews_are_not_placed_during_set_up():
    """Rule 33.9: the crew counter comes on the board when the vehicle dies, not before."""
    engine = build_engine(SCENARIO)
    state = engine.new_game(7)
    frame = engine.legal_commands(state)
    crews = {u.id for u in state.units if u.from_wreck is not None}
    for command in frame.commands:
        assert not (set(command.command.units) & crews), command.payload


def test_a_vehicle_is_placed_with_a_facing():
    """PR-21: the place command of a vehicle carries the spine it faces."""
    engine = build_engine(SCENARIO)
    state = engine.new_game(7)
    frame = engine.legal_commands(state)
    facings = set()
    for command in frame.commands:
        unit = state.units[command.command.units[0]]
        if unit.is_vehicle:
            assert "facing" in command.payload, command.payload
            facings.add(command.payload["facing"])
        else:
            assert "facing" not in command.payload, command.payload
    assert facings == set(range(6)), "every spine is on offer"


def test_no_vehicle_is_placed_in_a_stone_building():
    """Rule 30.1: a vehicle may not enter a stone building hex under any circumstance."""
    engine = build_engine(SCENARIO)
    state = engine.new_game(7)
    for command in engine.legal_commands(state).commands:
        unit = state.units[command.command.units[0]]
        if unit.is_vehicle and command.command.hex is not None:
            assert engine.board.hex(command.command.hex).terrain != "stone_building"


def test_a_scenario_that_asks_for_a_halftrack_is_refused():
    """PR-20: rules 47 and 51 hold the halftrack, the truck, and the jeep."""
    engine = build_engine(SCENARIO)
    document = {
        "id": "halftrack_probe",
        "title": "A halftrack before its rules",
        "board": engine.board.name,
        "turns": 4,
        "first_mover": "german",
        "setup_order": ["german", "russian"],
        "rules_used": ["28"],
        "sides": [
            {
                "side": side,
                "nationality": side,
                "groups": [
                    {
                        "id": f"{side}_all",
                        "area": {"zone": "columns", "min_col": 0 if side == "german" else 20, "max_col": 1 if side == "german" else 21},
                        "units": [{"type": "SdKfz251" if side == "german" else "4-4-7", "count": 1}],
                    }
                ],
            }
            for side in ("german", "russian")
        ],
        "victory": [],
    }
    scenario = scenario_from_dict(document)
    with pytest.raises(VehicleNotAvailable) as exc:
        Engine(scenario, engine.board, load_terrain(), load_hexsides(), load_all_counters(), load_tables())
    assert "47" in str(exc.value) and "51" in str(exc.value)


def test_an_engine_with_no_armor_tables_refuses_a_scenario_with_vehicles():
    """A deferred feature gives an error that names what it waits for, and no stub."""
    engine = build_engine(SCENARIO)
    tables = load_tables()
    bare = Tables(tables.ift, tables.cc)
    with pytest.raises(ValueError) as exc:
        Engine(engine.scenario, engine.board, load_terrain(), load_hexsides(), load_all_counters(), bare)
    assert "armor tables" in str(exc.value)


def test_a_random_game_reaches_the_armor_rules():
    """A rule with no command that offers it is a rule the game never plays."""
    engine = build_engine(SCENARIO)
    seen: collections.Counter = collections.Counter()
    for seed in (3, 7, 11, 19, 23, 29):
        seen.update(play_bounded(engine, seed, 900))
    families = {rule.split(".")[0] for rule in seen}
    for rule in ("30", "33", "39"):
        assert rule in families, f"no game applied a rule of family {rule}: {sorted(families)}"
    assert seen["30.2"] > 0, "no vehicle moved"
    assert seen["30.5"] > 0, "no vehicle turned"


@pytest.mark.slow
def test_the_armor_scenario_plays_to_the_end_and_replays():
    engine = build_engine(SCENARIO)
    record = play_game(engine, 5, (make_agent("v1", engine, 5, 0), make_agent("v2", engine, 5, 1)))
    assert record.result in tuple(engine.scenario.players()) + ("draw", "no_result")
    assert record.turns_played >= 2
    assert engine.replay(5, [c["payload"] for c in record.commands]) == record.hashes


def test_a_vehicle_never_ends_the_movement_phase_on_another_vehicle():
    """Rule 30.8: a vehicle may not end its movement in the same hex with another vehicle.

    The check runs at the moment the Movement Phase closes. Rule 16.1 can put two vehicles
    in one hex later in the turn, because the defender pulls moved units back to a hex on
    their track for the Defensive Fire Phase, and rule 16.3 puts them back afterwards.
    """
    engine = build_engine(SCENARIO)
    closes = 0
    for seed in (3, 7, 11):
        state = engine.new_game(seed)
        agents = (RandomAgent(seed, 0), RandomAgent(seed + 1, 1))
        for _ in range(900):
            if state.game_over:
                break
            frame = engine.legal_commands(state)
            if not frame.commands:
                break
            chosen = frame.by_id(agents[frame.player].select(state, frame))
            was = state.phase
            state, _ = engine.apply(state, chosen.command, frame)
            if was != "movement" or state.phase == "movement":
                continue
            closes += 1
            for vehicle in r28_vehicles.vehicles(state):
                assert not r30_vehicle_movement.must_leave(state, vehicle), (
                    f"vehicle {vehicle.id} shares its hex when the Movement Phase closed"
                )
    assert closes > 5, "the games did not close enough Movement Phases to prove anything"


def test_a_game_with_no_vehicle_keeps_the_state_document_it_had():
    """The vehicle fields are written only when they leave their default (NFR-01)."""
    engine = build_engine("s01_guards_counterattack")
    assert not engine.has_vehicles
    state = engine.new_game(4)
    for unit in state.units:
        document = unit.to_dict()
        for key in ("facing", "mp_used", "wreck", "immobilized", "passenger_of"):
            assert key not in document, key
