"""Playing a campaign (FR-17).

One function plays a sequence of random scenarios and keeps the personnel file of rule 2.
Each scenario is a fresh draw from the campaign seed, so a campaign is its seed and
nothing else: the same seed gives the same six scenarios and the same games.

Rule 3.2 adds the personal leader counter to the counter mix of the scenario in play. So
before each game the runner puts a leader of the current rank into the force of the player,
with the name from the personnel file, and after the game it finds that unit again by name
and reads the events that name it.

The sequence follows the record. `ladder.Ladder` turns the wins, the losses, and the points
on the personnel file into the strength of the next defence and into the seed of its draw.
So a campaign that goes well and a campaign that goes badly do not meet the same scenarios,
even from one seed.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, Callable, Mapping

from slcampaign import campaign as cg
from slcampaign.build import ATTACKER, build_scenario
from slcampaign.generator import draw_scenario
from slcampaign.ladder import Ladder
from slcampaign.points import unit_points
from slcore.engine import Engine
from slcore.scenario import Scenario, SideSpec, UnitEntry
from slcore.units import UnitType
from sldata.loaders import (
    board_and_parameters,
    load_all_counters,
    load_hexsides,
    load_tables,
    load_terrain,
)

PLAYER_SIDE = ATTACKER


def counter_types() -> dict[str, UnitType]:
    """Each counter of each army, keyed the way the engine keys them."""
    out: dict[str, UnitType] = {}
    for nationality, table in load_all_counters().items():
        for key, unit_type in table.items():
            out[f"{nationality}:{key}"] = unit_type
    return out


def point_values(types: Mapping[str, UnitType]) -> dict[str, int]:
    return {key: unit_points(t) for key, t in types.items()}


def with_personal_leader(scenario: Scenario, side_name: str, counter: str, name: str) -> Scenario:
    """Rule 3.2: the personal leader counter joins the force of the player."""
    sides = []
    for side in scenario.sides:
        if side.side != side_name:
            sides.append(side)
            continue
        groups = list(side.groups)
        first = groups[0]
        groups[0] = replace(first, units=first.units + (UnitEntry(counter, 1, name),))
        sides.append(SideSpec(side.side, side.nationality, tuple(groups)))
    return replace(scenario, sides=tuple(sides))


def leader_unit_id(state, name: str) -> int:
    for unit in state.units:
        if unit.name == name:
            return unit.id
    raise cg.CampaignError(f"the personal leader {name!r} is not in the force of the scenario")


def scenario_for(
    index: int,
    seed: int,
    types,
    values,
    rules: cg.Rules,
    leader: cg.Leader,
    ladder: Ladder,
    wins: int,
    losses: int,
) -> tuple[Scenario, int, int]:
    """The scenario of one step of the campaign, and the seed and the points it used.

    The record so far decides both: the ladder mixes the wins, the losses, and the carried
    points into the seed of the draw, and it sets the point total of the defence.
    """
    scenario_seed = ladder.seed_for(seed, index, wins, losses, leader.carried)
    points = ladder.points_for(wins, losses, leader.carried)
    draw, defending, attacking = draw_scenario(scenario_seed, types, values, points)
    scenario = build_scenario(
        scenario_seed, draw, defending, attacking, types, name=f"campaign-{seed}-{index + 1}"
    )
    with_leader = with_personal_leader(
        scenario, PLAYER_SIDE, rules.counter_for(leader.rank_index), leader.name
    )
    return with_leader, scenario_seed, points


def play_campaign(
    seed: int,
    make_agents: Callable[[Engine, int], tuple[Any, Any]],
    play: Callable[..., Any],
    scenarios: int | None = None,
    ladder: Ladder | None = None,
) -> cg.Campaign:
    """A whole campaign. `make_agents` and `play` come from the CLI, so the core stays pure."""
    rules = cg.load_rules()
    steps = ladder or Ladder()
    count = scenarios or rules.scenarios
    identities = cg.names(seed, count + 1)
    run = cg.Campaign(rules=rules, leader=cg.Leader(name=identities[0]))
    terrain = load_terrain()
    hexsides = load_hexsides()
    counters = load_all_counters()
    tables = load_tables()
    types = counter_types()
    values = point_values(types)
    identity = 1
    for index in range(count):
        scenario, game_seed, points = scenario_for(
            index, seed, types, values, rules, run.leader, steps, run.scenarios_won, run.scenarios_lost
        )
        board, _ = board_and_parameters(scenario, terrain)
        engine = Engine(scenario, board, terrain, hexsides, counters, tables)
        record = play(engine, game_seed, make_agents(engine, game_seed))
        state = engine.new_game(game_seed)
        unit_id = leader_unit_id(state, run.leader.name)
        player = scenario.side_index(PLAYER_SIDE)
        won = record.result == PLAYER_SIDE
        performance = cg.score(record.events, unit_id, player, won, rules)
        next_name = identities[min(identity, len(identities) - 1)]
        fresh = run.add(index + 1, scenario.id, game_seed, record.result, won, performance, next_name)
        run.records[-1].defence_points = points
        if fresh:
            identity += 1
    return run
