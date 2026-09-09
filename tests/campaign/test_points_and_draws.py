"""The force point scale and the random scenario construction of Game Set IV (FR-17)."""

from __future__ import annotations

import pytest

from slboards.generator import BOARD_TYPES
from slcampaign.generator import (
    ATTACK_SHARE,
    MIN_POINTS,
    MIN_SQUADS,
    TURNS,
    VICTORY_TABLE,
    ScenarioError,
    build_force,
    draw_scenario,
)
from slcampaign.points import force_points, unit_points
from slcampaign.run import counter_types, point_values
from slcore.rng import seed_state

TYPES = counter_types()
VALUES = point_values(TYPES)


# ------------------------------------------------------------------- the point scale


def test_an_elite_squad_costs_more_than_a_line_squad_of_its_army():
    assert unit_points(TYPES["german:8-3-8"]) > unit_points(TYPES["german:4-6-7"])
    assert unit_points(TYPES["russian:6-2-8"]) > unit_points(TYPES["russian:4-4-7"])
    assert unit_points(TYPES["american:8-4-7"]) > unit_points(TYPES["american:6-6-6"])


def test_a_heavier_machine_gun_costs_more():
    assert unit_points(TYPES["german:HMG"]) > unit_points(TYPES["german:MMG"])
    assert unit_points(TYPES["german:MMG"]) > unit_points(TYPES["german:LMG"])


def test_a_leader_with_a_modifier_costs_more_than_one_without():
    assert unit_points(TYPES["german:9-2"]) > unit_points(TYPES["german:9-1"])
    assert unit_points(TYPES["german:9-1"]) > unit_points(TYPES["german:8-0"])


def test_a_one_shot_weapon_costs_half_of_what_it_would_cost_again_and_again():
    """Rule 23.4 removes the demolition charge after it explodes, so it fires one time."""
    charge = TYPES["german:DC"]
    reusable = charge.firepower * 2 + charge.range
    assert unit_points(charge) == reusable // 2


def test_each_counter_has_a_value_above_zero():
    for key, value in VALUES.items():
        assert value > 0, key


def test_a_force_total_is_the_sum_of_its_counters():
    force = {"german:4-6-7": 3, "german:9-1": 1, "german:LMG": 2}
    expected = sum(unit_points(TYPES[k]) * n for k, n in force.items())
    assert force_points(TYPES, force) == expected


# ----------------------------------------------------------------- the force builder


def test_a_force_stays_inside_its_budget_and_holds_a_leader_and_squads():
    for seed in (1, 5, 90, 4321):
        rng = seed_state(seed)
        _, force = build_force(rng, TYPES, VALUES, "german", 400)
        assert force.points(VALUES) <= 400
        assert force.squads(TYPES) >= MIN_SQUADS
        assert any(TYPES[k].kind == "leader" for k, _ in force.counts)


def test_a_budget_that_cannot_buy_a_force_says_how_many_squads_it_bought():
    with pytest.raises(ScenarioError) as exc:
        build_force(seed_state(3), TYPES, VALUES, "german", 60)
    assert "squads" in str(exc.value)


# -------------------------------------------------------------------- the six draws


def test_the_draws_are_repeatable_from_the_seed():
    first = draw_scenario(77, TYPES, VALUES)
    second = draw_scenario(77, TYPES, VALUES)
    assert first[0] == second[0]
    assert first[1] == second[1]
    assert first[2] == second[2]


def test_a_different_seed_gives_a_different_scenario():
    seen = {draw_scenario(seed, TYPES, VALUES)[0] for seed in range(1, 30)}
    assert len(seen) > 10, "thirty seeds should not give the same scenario"


@pytest.mark.parametrize("seed", [1, 2, 3, 17, 400, 9999])
def test_each_draw_is_inside_the_tables_it_draws_from(seed: int):
    draw, defending, attacking = draw_scenario(seed, TYPES, VALUES)
    assert draw.board_type in BOARD_TYPES
    assert draw.turns in TURNS
    assert draw.victory_kind in {kind for kind, _ in VICTORY_TABLE}
    assert draw.attack_share in ATTACK_SHARE
    assert draw.defender != draw.attacker
    assert defending.nationality == draw.defender
    assert attacking.nationality == draw.attacker


def test_the_attacker_gets_more_points_than_the_defender():
    """Rule 10 of the printed method: the attack on a held position needs the larger force."""
    for seed in range(1, 12):
        draw, _, _ = draw_scenario(seed, TYPES, VALUES)
        assert draw.attacker_points > draw.defender_points


def test_a_point_total_below_the_floor_says_so():
    with pytest.raises(ScenarioError) as exc:
        draw_scenario(1, TYPES, VALUES, MIN_POINTS - 1)
    assert str(MIN_POINTS) in str(exc.value)


def test_the_draws_reach_each_army_and_each_board_type():
    boards = set()
    armies = set()
    for seed in range(1, 60):
        draw, _, _ = draw_scenario(seed, TYPES, VALUES)
        boards.add(draw.board_type)
        armies.add(draw.defender)
        armies.add(draw.attacker)
    assert boards == set(BOARD_TYPES)
    assert armies == {"german", "russian", "american"}
