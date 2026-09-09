"""A random scenario that the engine plays, and a campaign that runs (FR-17)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slcampaign.build import ATTACKER, DEFENDER, build_scenario, split_force
from slcampaign.generator import draw_scenario
from slcampaign.ladder import Ladder
from slcampaign.run import counter_types, play_campaign, point_values, with_personal_leader
from slcli.play import make_agent, play_game
from slcore.engine import Engine
from sldata.loaders import board_and_parameters, load_all_counters, load_hexsides, load_tables, load_terrain

TYPES = counter_types()
VALUES = point_values(TYPES)
TERRAIN = load_terrain()
HEXSIDES = load_hexsides()
COUNTERS = load_all_counters()
TABLES = load_tables()


def engine_for(seed: int) -> Engine:
    draw, defending, attacking = draw_scenario(seed, TYPES, VALUES)
    scenario = build_scenario(seed, draw, defending, attacking, TYPES)
    board, _ = board_and_parameters(scenario, TERRAIN)
    return Engine(scenario, board, TERRAIN, HEXSIDES, COUNTERS, TABLES)


# --------------------------------------------------------------- the scenario builds


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5, 6, 7, 8])
def test_a_random_scenario_builds_a_board_and_a_set_up(seed: int):
    engine = engine_for(seed)
    state = engine.new_game(seed)
    assert state.units
    assert engine.scenario.first_mover == ATTACKER
    assert engine.scenario.setup_order[0] == DEFENDER, "rule 11: the defender sets up first"


def test_the_holding_group_stays_inside_the_stacking_limits():
    """Rule 6.1. The building can be two hexes, so the holding group has to fit in two."""
    from slcore.rules import r06_stacking

    for seed in (1, 5, 11, 23):
        _, defending, _ = draw_scenario(seed, TYPES, VALUES)
        hold, _ = split_force(defending, TYPES)
        squads = sum(e.count for e in hold if TYPES[f"{defending.nationality}:{e.type_key}"].is_squad_like)
        assert squads <= r06_stacking.LIMIT_SQUADS


def test_the_two_sides_start_apart():
    """Rule 12: no attacker sets up next to the defender."""
    engine = engine_for(3)
    board = engine.board
    areas = {}
    for side in engine.scenario.sides:
        for group in side.groups:
            areas[group.id] = set(group.area.resolve(board))
    attacker = areas["a_force"]
    defender = set().union(*[hexes for gid, hexes in areas.items() if gid.startswith("d_")])
    assert attacker and defender
    assert not attacker & defender
    assert max(ref[0] for ref in attacker) < min(ref[0] for ref in defender)


def test_the_scenario_says_how_it_was_made():
    engine = engine_for(6)
    notes = engine.scenario.notes
    assert "Game Set IV" in notes
    assert "points" in notes


@pytest.mark.slow
@pytest.mark.parametrize("seed", [1, 4])
def test_a_random_scenario_plays_to_a_result(seed: int):
    engine = engine_for(seed)
    record = play_game(engine, seed, (make_agent("v2", engine, seed, 0), make_agent("v1", engine, seed, 1)))
    assert record.result in (ATTACKER, DEFENDER, "draw", "no_result")
    assert record.commands


# ------------------------------------------------------------- the personal leader


def test_the_personal_leader_joins_the_force_of_the_player():
    """Rule 3.2."""
    draw, defending, attacking = draw_scenario(9, TYPES, VALUES)
    scenario = build_scenario(9, draw, defending, attacking, TYPES)
    before = sum(e.count for side in scenario.sides for g in side.groups for e in g.units)
    with_leader = with_personal_leader(scenario, ATTACKER, "8-1", "Sgt Test")
    after = sum(e.count for side in with_leader.sides for g in side.groups for e in g.units)
    assert after == before + 1
    named = [
        e
        for side in with_leader.sides
        if side.side == ATTACKER
        for g in side.groups
        for e in g.units
        if e.name == "Sgt Test"
    ]
    assert len(named) == 1
    assert named[0].type_key == "8-1"


# --------------------------------------------------------------------- a campaign


@pytest.mark.slow
def test_a_campaign_is_repeatable_from_its_seed():
    def agents(engine, seed):
        return (make_agent("v1", engine, seed, 0), make_agent("v1", engine, seed, 1))

    first = play_campaign(21, agents, play_game, scenarios=2)
    second = play_campaign(21, agents, play_game, scenarios=2)
    assert first.to_dict() == second.to_dict()


@pytest.mark.slow
def test_the_campaign_record_holds_one_line_for_each_scenario():
    def agents(engine, seed):
        return (make_agent("v2", engine, seed, 0), make_agent("v1", engine, seed, 1))

    run = play_campaign(33, agents, play_game, scenarios=3)
    document = run.to_dict()
    assert document["scenarios_played"] == 3
    assert [r["index"] for r in document["records"]] == [1, 2, 3]
    for record in document["records"]:
        assert record["seed"] >= 0
        assert record["defence_points"] > 0
        assert record["starting_rank"] in [r.name for r in run.rules.ranks]
        assert record["ending_rank"] in [r.name for r in run.rules.ranks]
    assert document["victory_points"] >= document["scenarios_won"]


@pytest.mark.slow
def test_the_record_changes_the_scenario_that_comes_next():
    """The sequence follows the performance, which is what a campaign ladder means."""
    ladder = Ladder()
    seeds_when_winning = [ladder.seed_for(7, i, i, 0, 4 * i) for i in range(1, 4)]
    seeds_when_losing = [ladder.seed_for(7, i, 0, i, -4 * i) for i in range(1, 4)]
    assert seeds_when_winning != seeds_when_losing
    kinds_winning = [draw_scenario(s, TYPES, VALUES)[0].victory_kind for s in seeds_when_winning]
    kinds_losing = [draw_scenario(s, TYPES, VALUES)[0].victory_kind for s in seeds_when_losing]
    assert kinds_winning != kinds_losing or seeds_when_winning != seeds_when_losing


# ------------------------------------------------------------------- the command


def test_the_draw_command_writes_a_record_for_each_scenario(tmp_path: Path, capsys):
    from slcli.campaign_cmd import draw_set

    assert draw_set(4, 500, 400, tmp_path) == 0
    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == 4
    document = json.loads(files[0].read_text(encoding="utf-8"))
    assert document["draw"]["turns"] in (4, 6, 8, 10)
    assert document["defending"]["counts"]
    assert document["attacking"]["counts"]
    assert "Game Set IV" in document["notes"]
    assert "victory" in capsys.readouterr().out


# ------------------------------------------------ a random scenario as a scenario name


def test_a_scenario_name_can_be_a_seed():
    """`random:500` is a scenario, so each command that takes a scenario takes one."""
    from slcli.play import build_engine

    engine = build_engine("random:500")
    assert engine.scenario.id == "random-500"
    assert engine.new_game(1).units


def test_two_calls_with_one_seed_give_the_same_scenario():
    from slcli.play import build_engine

    first = build_engine("random:501")
    second = build_engine("random:501")
    assert first.hash_state(first.new_game(4)) == second.hash_state(second.new_game(4))


def test_a_random_name_without_a_seed_says_what_it_needs():
    from sldata.loaders import DataError
    from slcli.play import build_engine

    with pytest.raises(DataError) as exc:
        build_engine("random:tuesday")
    assert "seed" in str(exc.value)
