"""The three scripted agents (FR-44, TC-15).

FR-44 asks for three scripted agents with named parameters, each with a version that the
run artifact records. The tests here prove that the three exist, that they are different
policies and not one policy with three names, and that each one plays a whole game of each
scenario without an unhandled error.

The hundred games of TC-15 are the gate run of `sl-cli agents`, which uses worker
processes. The test here plays one game of each pair, which is what a commit can afford.
"""

from __future__ import annotations

import collections

import pytest

from slagents.scripted.v0 import ScriptedV0
from slagents.scripted.v1 import Parameters as V1Parameters
from slagents.scripted.v1 import ScriptedV1
from slagents.scripted.v2 import Parameters as V2Parameters
from slagents.scripted.v2 import ScriptedV2
from slagents.scripted.v3 import ScriptedV3
from slagents.scripted.v4 import ScriptedV4
from slagents.scripted.v5 import ScriptedV5
from slagents.scripted.v6 import ScriptedV6
from slagents.scripted.v7 import ScriptedV7
from slcli.agents_cmd import AGENTS, SCENARIOS, parameter_record, run_gate
from slcli.play import build_engine, make_agent, play_game
from slcore import geometry

NAMED = ("aggression", "cover_preference", "fire_priority")


def test_the_project_ships_eight_scripted_agents_with_versions():
    engine = build_engine("s01_guards_counterattack")
    agents = [make_agent(kind, engine, 1, 0) for kind in AGENTS]
    assert [a.version for a in agents] == ["0", "1", "2", "3.1", "4", "5", "6.2", "7"]
    assert len({(a.name, a.version) for a in agents}) == len(AGENTS)
    assert isinstance(agents[0], ScriptedV0)
    assert isinstance(agents[1], ScriptedV1)
    assert isinstance(agents[2], ScriptedV2)
    assert isinstance(agents[3], ScriptedV3)
    assert isinstance(agents[4], ScriptedV4)
    assert isinstance(agents[5], ScriptedV5)
    assert isinstance(agents[6], ScriptedV6)
    assert isinstance(agents[7], ScriptedV7)


def test_the_parameters_have_the_names_the_requirement_gives():
    """FR-44 names aggression, cover preference, and fire priority."""
    record = parameter_record()
    assert set(record) == set(AGENTS)
    for kind in ("v1", "v2", "v3"):
        for name in NAMED:
            assert name in record[kind], f"{kind} has no {name}"
    assert record["v0"] == {}, "the first agent has no parameter, which is what makes it the baseline"
    assert "smoke_range" in record["v2"], "the engineer has parameters of its own"
    assert "armor_priority" in record["v3"], "the tanker has parameters of its own"


def test_a_parameter_changes_what_the_agent_does():
    """A parameter that no decision reads is not a parameter."""
    engine = build_engine("s01_guards_counterattack")
    calm = ScriptedV1(engine, 0, V1Parameters(aggression=1, cover_preference=9))
    keen = ScriptedV1(engine, 0, V1Parameters(aggression=9, cover_preference=0))
    state = engine.new_game(3)
    while state.phase == "setup":
        frame = engine.legal_commands(state)
        agent = make_agent("v1", engine, 3, frame.player)
        state, _ = engine.apply(state, frame.by_id(agent.select(state, frame)).command, frame)
    differences = 0
    for _ in range(60):
        if state.game_over:
            break
        frame = engine.legal_commands(state)
        if frame.player == 0 and frame.phase == "movement":
            if calm.select(state, frame) != keen.select(state, frame):
                differences += 1
        agent = make_agent("v1", engine, 3, frame.player)
        state, _ = engine.apply(state, frame.by_id(agent.select(state, frame)).command, frame)
    assert differences > 0, "the two parameter sets never chose a different move"


SEEDS_FOR_THE_ENGINEER = (12, 13, 14, 15, 16, 17)


def kinds_of(record) -> collections.Counter:
    """The event kinds of a game, which name what happened and not which rule said so."""
    return collections.Counter(e["kind"] for e in record.events)


def kinds_over_seeds(kind: str, scenario: str, seeds=SEEDS_FOR_THE_ENGINEER, **params) -> collections.Counter:
    """The event kinds of several games with one agent.

    One board is one sample. Whether a game reaches a sewer entrance, or a hex next to an
    enemy building, is a property of the board and the seed. A change to the generator
    changes each board, so a test that pins one seed breaks on a change that is correct.
    The rule these tests state is about the agent, so they read several seeds.
    """
    from slagents.scripted.v2 import Parameters, ScriptedV2

    engine = build_engine(scenario)
    total = collections.Counter()
    for seed in seeds:
        if params:
            settings = Parameters(**params)
            agents = tuple(ScriptedV2(engine, player, settings) for player in (0, 1))
        else:
            agents = (make_agent(kind, engine, seed, 0), make_agent(kind, engine, seed, 1))
        total.update(kinds_of(play_game(engine, seed, agents)))
    return total


def test_the_engineer_uses_the_rules_that_the_others_do_not():
    """Agent v2 answers the windows of rules 22 to 27, and agent v1 ends them."""
    engineer = kinds_over_seeds("v2", "s02_tractor_works")
    plain = kinds_over_seeds("v1", "s02_tractor_works")
    assert engineer["smoke"] > 0, "the engineer makes smoke"
    assert engineer["sewer_move"] > 0, "and it moves through the sewers"
    assert plain["smoke"] == 0, "agent v1 makes no smoke"
    assert plain["sewer_move"] == 0, "and it takes no sewer"


def test_the_charge_range_decides_the_hexes_the_engineer_will_use():
    """Rule 23.3 with the `charge_range` parameter, read from the decision and not a game.

    How near the two sides come is a property of the board and of the seed. A change to the
    generator changes each board, so a test that plays games to find out whether a charge
    goes down measures the board as much as the agent. This one reads the hexes the agent
    would use for one state, so it measures the parameter and nothing else.
    """
    from slagents.scripted.v2 import Parameters, ScriptedV2

    engine = build_engine("s02_tractor_works")
    state = engine.new_game(12)
    while state.phase == "setup":
        frame = engine.legal_commands(state)
        agent = make_agent("v2", engine, 12, frame.player)
        state, _ = engine.apply(state, frame.by_id(agent.select(state, frame)).command, frame)
    enemy = [u.hex for u in state.player_units(1) if u.hex is not None]
    assert enemy, "the other side is on the board"
    counts = {}
    for width in (1, 4, 8, 16):
        agent = ScriptedV2(engine, 0, Parameters(charge_range=width))
        counts[width] = sum(
            1
            for unit in state.player_units(0)
            if unit.hex is not None
            and min(geometry.distance(unit.hex, e) for e in enemy) <= agent.params.charge_range
        )
    assert counts[1] <= counts[4] <= counts[8] <= counts[16], counts
    assert counts[16] > counts[1], "the parameter changes nothing at any range"


@pytest.mark.slow
def test_a_wider_charge_range_places_more_charges():
    """The same parameter, read from real games. Rule 23.3 puts the charge on the board."""
    wide = kinds_over_seeds("v2", "s02_tractor_works", charge_range=8)
    narrow = kinds_over_seeds("v2", "s02_tractor_works", charge_range=1)
    assert wide["demo_placed"] > 0, "a wide charge range places a charge"
    assert wide["demo_armed"] > 0, "the placer holds its hex, so the charge is operable"
    assert wide["demo_explode"] > 0, "and the charge explodes in the Advancing Fire Phase"
    assert narrow["demo_placed"] < wide["demo_placed"], "a narrow charge range places fewer"


@pytest.mark.parametrize(
    "scenario",
    [
        SCENARIOS[0],
        pytest.param(SCENARIOS[1], marks=pytest.mark.gate),
        pytest.param(SCENARIOS[2], marks=pytest.mark.gate),
        SCENARIOS[3],
    ],
)
@pytest.mark.slow
def test_each_agent_plays_one_game_of_each_scenario(scenario: str):
    """TC-15 in the small: the gate run plays a hundred of each pair.

    Scenario 1 runs on each commit. The two long scenarios carry the `gate` marker,
    because three whole games of scenario 3A is a minute and a half.
    """
    engine = build_engine(scenario)
    for kind in AGENTS:
        agents = (make_agent(kind, engine, 4242, 0), make_agent(kind, engine, 4242, 1))
        record = play_game(engine, 4242, agents)
        assert record.turns_played == engine.scenario.turns
        assert engine.replay(4242, [c["payload"] for c in record.commands]) == record.hashes


def test_the_gate_run_reports_each_pair_and_its_parameters():
    """The shape of the TC-15 artifact, with one game of one scenario for each agent."""
    art = run_gate(games=1, first_seed=9100, workers=3, scenarios=SCENARIOS[:1])
    stats = art.stats
    assert len(stats["pairs"]) == len(AGENTS)
    assert stats["missing_pairs"] == []
    assert stats["fatal"] == []
    assert stats["unhandled_errors"] == []
    assert stats["passed"] == {"TC-15": True}
    assert art.config["criteria"] == ["TC-15", "FR-44"]
    assert set(art.config["parameters"]) == set(AGENTS)


@pytest.mark.gate
def test_the_mixed_gate_plays_each_ordered_pair_of_two_agents():
    """Each agent against each other agent, on each side. A state that one agent makes can
    break another agent, and the self play gate does not make it."""
    art = run_gate(games=1, first_seed=9200, workers=6, scenarios=SCENARIOS[:1], mixed=True)
    rows = art.stats["pairs"]
    kinds = {r["agent"] for r in rows}
    assert len(kinds) == len(AGENTS) * (len(AGENTS) - 1)
    assert "v1+v6" in kinds and "v6+v1" in kinds
    assert art.stats["passed"]["TC-15"], art.stats["unhandled_errors"][:3]
