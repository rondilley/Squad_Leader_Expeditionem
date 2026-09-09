"""The Campaign Game of Game Set IV: the scorer, the ranks, and the ladder (FR-17).

The scorer reads a list of events, so each test of rule 4 gives it the events that rule
names. That keeps the test on the rule and off the game that produced the events.
"""

from __future__ import annotations

import pytest

from slcampaign.campaign import (
    Campaign,
    Leader,
    Performance,
    advance,
    load_rules,
    names,
    score,
)
from slcampaign.ladder import Ladder

RULES = load_rules()
ME = 7
THEM = 9
MY_PLAYER = 0


def event(rule_id: str, kind: str, **data):
    return {"rule_id": rule_id, "kind": kind, "data": data}


def points_of(events, won: bool = False) -> Performance:
    return score(events, ME, MY_PLAYER, won, RULES)


# ------------------------------------------------------------------ the rank table


def test_the_seven_ranks_are_the_ones_rule_3_1_lists():
    assert [r.name for r in RULES.ranks] == ["Cpl", "Sgt", "1st Sgt", "2nd Lt", "1st Lt", "CPT", "MAJ"]
    assert [r.morale for r in RULES.ranks] == [7, 8, 8, 9, 9, 10, 10]
    assert [r.leadership for r in RULES.ranks] == [0, 0, -1, -1, -2, -2, -3]


def test_each_rank_names_a_counter_the_project_already_has():
    """Rule 3.2 puts the counter of the rank in the force, so the counter has to exist."""
    from sldata.loaders import load_all_counters

    german = load_all_counters()["german"]
    for index in range(len(RULES.ranks)):
        assert RULES.counter_for(index) in german


def test_a_rank_index_outside_the_list_gives_the_nearest_rank():
    assert RULES.rank(-5).name == "Cpl"
    assert RULES.rank(50).name == "MAJ"


# ------------------------------------------------------------------- rule 4.1, Elan


def test_a_win_is_one_elan_point():
    """Rule 4.1F."""
    assert points_of([], won=True).elan == RULES.elan["4.1F"]


def test_rallying_a_squad_is_one_elan_point_for_each_squad():
    """Rule 4.1D. The rally event names the leader whose modifier applied."""
    events = [
        event("14.2", "rallied", unit=21, hex="C3", leader=ME),
        event("14.2", "rallied", unit=22, hex="C3", leader=ME),
        event("14.2", "rallied", unit=23, hex="D4", leader=THEM),
        event("14.2", "rallied", unit=ME, hex="C3", leader=None),
    ]
    assert points_of(events).elan == 2 * RULES.elan["4.1D"]


def test_directed_fire_that_kills_a_squad_is_one_elan_point():
    """Rule 4.1E. Rule 15.2 names the leader who directed the fire group."""
    events = [
        event("15.2", "group_leader", leader=ME),
        event("8.8", "eliminated", unit=31, player=1, cause="KIA"),
        event("13.6", "eliminated", unit=32, player=1, hex="F5"),
    ]
    assert points_of(events).elan == 2 * RULES.elan["4.1E"]


def test_a_kill_that_another_leader_directed_is_not_my_point():
    events = [
        event("15.2", "group_leader", leader=THEM),
        event("8.8", "eliminated", unit=31, player=1, cause="KIA"),
    ]
    assert points_of(events).elan == 0


def test_a_kill_after_the_phase_ends_belongs_to_no_leader():
    """The direction of a fire group lasts for that fire and not for the phase."""
    events = [
        event("15.2", "group_leader", leader=ME),
        event("4", "phase", name="rout"),
        event("13.6", "eliminated", unit=31, player=1, hex="F5"),
    ]
    assert points_of(events).elan == 0


def test_close_combat_that_clears_the_hex_is_three_elan_points():
    """Rule 4.1B."""
    events = [event("20.3", "cc_kill", player=MY_PLAYER, leader=ME, attackers=[3, ME], targets=[31, 32])]
    assert points_of(events).elan == RULES.elan["4.1B"]


# -------------------------------------------------------------- rule 4.2, Cowardice


def test_breaking_under_fire_is_one_cowardice_point_each_time():
    """Rule 4.2E."""
    events = [event("12.3", "broken", unit=ME, hex="C3", cause="fire")]
    assert points_of(events).cowardice == RULES.cowardice["4.2E"]


def test_breaking_twice_with_no_rally_is_total_cowardice():
    """Rule 4.2A, the second half: broke two times without rallying."""
    events = [
        event("12.3", "broken", unit=ME, hex="C3", cause="fire"),
        event("12.3", "broken", unit=ME, hex="C3", cause="fire"),
    ]
    performance = points_of(events)
    assert ("4.2A", RULES.cowardice["4.2A"]) in performance.awards
    assert performance.cowardice == 2 * RULES.cowardice["4.2E"] + RULES.cowardice["4.2A"]


def test_the_break_of_the_leader_that_breaks_a_squad_costs_two_for_each_squad():
    """Rule 4.2C, which follows rule 12.22."""
    events = [
        event("12.3", "broken", unit=ME, hex="C3", cause="fire"),
        event("12.3", "broken", unit=21, hex="C3", cause="leader_break"),
        event("12.3", "broken", unit=22, hex="C3", cause="leader_break"),
    ]
    performance = points_of(events)
    assert performance.cowardice == RULES.cowardice["4.2E"] + 2 * RULES.cowardice["4.2C"]


def test_a_squad_that_breaks_on_its_own_is_not_my_cowardice():
    events = [event("12.3", "broken", unit=21, hex="C3", cause="fire")]
    assert points_of(events).cowardice == 0


def test_a_weapon_that_malfunctions_under_my_direction_costs_one():
    """Rule 4.2D."""
    events = [
        event("15.2", "group_leader", leader=ME),
        event("18.1", "malfunction", weapon=57, roll=12, breakdown=10),
    ]
    assert points_of(events).cowardice == RULES.cowardice["4.2D"]


def test_a_rally_roll_of_twelve_removes_the_leader_and_costs_eight():
    """Rule 4.2A, the first half, with rule 18.3."""
    events = [event("18.3", "eliminated", unit=ME, hex="C3", dice=[6, 6])]
    performance = points_of(events)
    assert performance.cowardice == RULES.cowardice["4.2A"]
    assert performance.killed


def test_a_squad_that_surrenders_in_my_hex_costs_three():
    """Rule 4.2B."""
    events = [
        event("21.2", "place", unit=ME, hex="C3"),
        event("18.3", "eliminated", unit=21, hex="C3", dice=[6, 6]),
    ]
    assert points_of(events).cowardice == RULES.cowardice["4.2B"]


def test_a_leader_killed_by_fire_is_out_of_the_campaign():
    """Rule 5.1: only a KIA result removes a leader from the campaign game."""
    events = [event("8.8", "eliminated", unit=ME, cause="KIA")]
    assert points_of(events).killed


# -------------------------------------------------- rules 2.4 to 2.7, the personnel file


def test_ten_points_promote_one_rank_and_ten_points_come_off_the_total():
    leader, fresh = advance(Leader("A"), Performance(elan=12), RULES, "B")
    assert RULES.rank(leader.rank_index).name == "Sgt"
    assert leader.carried == 2
    assert not fresh


def test_a_promotion_is_one_rank_a_scenario_however_many_points_there_are():
    """Rule 2.6."""
    leader, _ = advance(Leader("A"), Performance(elan=45), RULES, "B")
    assert leader.rank_index == 1
    assert leader.carried == 35


def test_minus_ten_demotes_one_rank_and_ten_points_go_back_on():
    start = Leader("A", rank_index=3)
    leader, fresh = advance(start, Performance(cowardice=-12), RULES, "B")
    assert leader.rank_index == 2
    assert leader.carried == -2
    assert not fresh


def test_a_corporal_who_is_busted_starts_again_with_a_new_name():
    """Rule 2.7."""
    leader, fresh = advance(Leader("A"), Performance(cowardice=-12), RULES, "B")
    assert leader.name == "B"
    assert leader.rank_index == 0
    assert leader.carried == 0
    assert fresh


def test_a_leader_killed_in_action_starts_again_as_a_corporal():
    """Rule 2.7."""
    leader, fresh = advance(Leader("A", rank_index=4), Performance(killed=True), RULES, "B")
    assert leader.name == "B"
    assert leader.rank_index == 0
    assert fresh


def test_points_between_the_two_thresholds_keep_the_rank():
    leader, _ = advance(Leader("A", rank_index=2, carried=3), Performance(elan=4, cowardice=-2), RULES, "B")
    assert leader.rank_index == 2
    assert leader.carried == 5


# --------------------------------------------------------------- rule 5, the victory


def test_a_campaign_scores_one_point_for_a_win_and_one_for_each_rank():
    run = Campaign(rules=RULES, leader=Leader("A"))
    identities = names(1, 4)
    run.add(1, "s1", 10, "attacker", True, Performance(elan=12), identities[1])
    run.add(2, "s2", 11, "attacker", True, Performance(elan=12), identities[2])
    run.add(3, "s3", 12, "defender", False, Performance(), identities[3])
    assert run.scenarios_won == 2
    assert run.leader.rank_index == 2
    assert run.victory_points() == 2 + 2


def test_a_leader_who_did_not_survive_gives_no_rank_points():
    """Rule 5.1: the leader that scores the rank points must have survived the last game."""
    run = Campaign(rules=RULES, leader=Leader("A"))
    identities = names(1, 3)
    run.add(1, "s1", 10, "attacker", True, Performance(elan=12), identities[1])
    run.add(2, "s2", 11, "attacker", True, Performance(elan=2, killed=True), identities[2])
    assert run.scenarios_won == 2
    assert run.leader.rank_index == 0, "a new Corporal took over"
    assert run.victory_points() == 2


def test_the_record_names_the_leader_that_played_the_scenario():
    run = Campaign(rules=RULES, leader=Leader("A"))
    run.add(1, "s1", 10, "defender", False, Performance(killed=True), "B")
    assert run.records[0].leader_name == "A"
    assert run.leader.name == "B"


# --------------------------------------------------------------------- the ladder


def test_a_win_makes_the_next_defence_stronger_and_a_loss_makes_it_weaker():
    ladder = Ladder()
    even = ladder.points_for(0, 0, 0)
    assert ladder.points_for(2, 0, 0) > even
    assert ladder.points_for(0, 2, 0) < even


def test_the_defence_stays_between_the_floor_and_the_ceiling():
    ladder = Ladder()
    assert ladder.points_for(50, 0, 200) == ladder.ceiling
    assert ladder.points_for(0, 50, -200) == ladder.floor


def test_the_points_on_the_personnel_file_move_the_defence_too():
    ladder = Ladder()
    assert ladder.points_for(1, 1, 20) > ladder.points_for(1, 1, 0)


def test_the_seed_of_the_next_scenario_follows_the_record():
    ladder = Ladder()
    winning = ladder.seed_for(5, 3, 3, 0, 8)
    losing = ladder.seed_for(5, 3, 0, 3, -8)
    assert winning != losing, "a campaign that goes differently meets a different scenario"
    assert ladder.seed_for(5, 3, 3, 0, 8) == winning, "and the same record gives the same one"


@pytest.mark.parametrize("wins,losses,carried", [(0, 0, 0), (4, 1, 12), (1, 4, -12), (9, 9, 0)])
def test_each_seed_is_a_non_negative_integer(wins: int, losses: int, carried: int):
    seed = Ladder().seed_for(31, 2, wins, losses, carried)
    assert isinstance(seed, int)
    assert seed >= 0


def test_a_leader_that_replaced_the_one_before_scores_no_rank_point():
    """Rule 5.1 again, read through the record and not through the rank alone."""
    run = Campaign(rules=RULES, leader=Leader("A", rank_index=3))
    run.add(1, "s1", 10, "attacker", True, Performance(elan=2), "B")
    assert not run.leader.replaced
    assert run.victory_points() == 1 + 3
    run.add(2, "s2", 11, "attacker", True, Performance(killed=True), "C")
    assert run.leader.replaced
    assert run.leader.name == "C", "rule 2.7 puts a new Corporal on the file"
    assert run.records[1].leader_name == "A", "and the record names the one that played"
    assert run.victory_points() == 2
