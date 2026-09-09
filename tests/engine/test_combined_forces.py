"""The three armies of the 1977 counter set, and a side that fields two of them.

The counter sheet has German, Russian, and American counters. The three printed scenarios
of year one are German against Russian, and the first printed card with an American force
is scenario 7, which needs rules 42 to 52. So the project has its own scenario that puts
the three armies in one game inside rules 1 to 27.
"""

from __future__ import annotations

import collections

import pytest

from slcli.play import build_engine, make_agent, play_game
from sldata.loaders import NATIONALITIES, load_all_counters

SCENARIO = "s00b_combined_forces"


@pytest.fixture(scope="module")
def counters():
    return load_all_counters()


def test_the_counter_set_holds_the_three_armies(counters):
    assert set(NATIONALITIES) == {"german", "russian", "american"}
    assert set(counters) == set(NATIONALITIES)


@pytest.mark.parametrize("nationality", ["german", "russian", "american"])
def test_each_army_has_squads_leaders_and_support_weapons(counters, nationality: str):
    table = counters[nationality]
    kinds = collections.Counter(t.kind for t in table.values())
    assert kinds["squad"] >= 2, "a line squad and an elite squad"
    assert kinds["crew"] >= 1
    assert kinds["leader"] >= 7, "the rank-only leaders of RV-1 section 3"
    assert kinds["sw"] >= 2


def test_the_american_values_are_the_ones_rv_one_records(counters):
    """RV-1 sections 2 and 4. The 8-4-7 squad is the 1977 counter, not the 7-4-7."""
    table = counters["american"]
    line = table["6-6-6"]
    assert (line.firepower, line.range, line.morale) == (6, 6, 6)
    elite = table["8-4-7"]
    assert (elite.firepower, elite.range, elite.morale) == (8, 4, 7)
    assert elite.elite
    crew = table["2-4-6"]
    assert (crew.firepower, crew.range, crew.morale) == (2, 4, 6)
    mmg = table["MMG"]
    assert (mmg.firepower, mmg.range, mmg.breakdown) == (4, 12, 12)
    hmg = table["HMG"]
    assert (hmg.firepower, hmg.range, hmg.breakdown) == (8, 20, 12)
    assert hmg.heavy, "rule 27.3 keeps the heavy machine gun out of the sewers"
    assert "LMG" not in table, "RV-1 section 4 lists no American light machine gun"


def test_the_american_and_the_german_squads_are_not_the_same_counter(counters):
    """A shared type key must not give one army the values of another."""
    assert counters["american"]["MMG"].range != counters["russian"]["MMG"].range
    assert set(counters["american"]) != set(counters["german"])


# ------------------------------------------------------- a side with two armies


def test_a_group_names_its_own_army_and_the_side_keeps_the_rest():
    engine = build_engine(SCENARIO)
    allied = engine.scenario.side_spec("allied")
    assert allied.nationality == "russian"
    assert allied.armies() == ("russian", "american")
    for group in allied.groups:
        expected = group.nationality or "russian"
        assert allied.army_of(group) == expected


def test_the_game_starts_with_the_three_armies_on_the_board():
    engine = build_engine(SCENARIO)
    state = engine.new_game(7)
    armies = collections.Counter(u.type_key.split(":")[0] for u in state.units)
    assert set(armies) == {"german", "russian", "american"}
    for army, count in armies.items():
        assert count > 0, army
    # Two sides, whatever the armies are. Rule 4 gives a turn to a side, not to an army.
    assert set(u.player for u in state.units) == {0, 1}


def test_the_two_armies_of_one_side_are_the_same_player():
    engine = build_engine(SCENARIO)
    state = engine.new_game(7)
    players = {}
    for unit in state.units:
        players.setdefault(unit.type_key.split(":")[0], set()).add(unit.player)
    assert players["russian"] == players["american"], "one side, one player"
    assert players["german"] != players["russian"]


@pytest.mark.slow
def test_the_combined_scenario_plays_to_a_result():
    engine = build_engine(SCENARIO)
    record = play_game(engine, 5, (make_agent("v2", engine, 5, 0), make_agent("v2", engine, 5, 1)))
    assert record.result in ("axis", "allied", "draw")
    assert len(record.commands) > 100


def test_the_view_names_the_army_of_each_unit_so_the_client_can_colour_it():
    """FR-31: the client picks the counter colour from the nationality of the view."""
    from slcore import view

    engine = build_engine(SCENARIO)
    state = engine.new_game(7)
    document = view.build(state, engine.types, 1)
    armies = {u["nationality"] for u in document["units"]}
    assert "american" in armies, "the Allied player sees its own American units"
    assert armies <= {"german", "russian", "american"}
