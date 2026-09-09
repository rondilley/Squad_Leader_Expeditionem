"""Scenario 1 from its data file (FR-19) and the victory evaluator (FR-14)."""

import pytest

from slagents.scripted.v1 import ScriptedV1
from slcore.rules import victory
from slcli.play import build_engine, play_game, replay_record


@pytest.fixture(scope="module")
def engine():
    return build_engine("s01_guards_counterattack")


def test_the_force_lists_match_the_scenario_card(engine):
    state = engine.new_game(1)
    german = [u for u in state.units if u.player == 1]
    russian = [u for u in state.units if u.player == 0]
    german_squads = [u for u in german if u.kind == "squad"]
    russian_squads = [u for u in russian if u.kind == "squad"]
    assert len(german_squads) == 13, "the card gives the Germans 13 squads"
    assert len(russian_squads) == 21, "the card gives the Russians 21 squads"
    assert len([u for u in german if u.kind == "leader"]) == 5, "the card names five German leaders"
    assert len([u for u in russian if u.kind == "leader"]) == 3, "the card names three Russian leaders; the M2 and N2 groups have none"
    guards = [u for u in russian_squads if u.type_key.endswith("6-2-8")]
    assert len(guards) == 12, "the guards battalion has 12 elite squads"
    weapons = [u for u in german if u.kind == "sw"]
    assert sorted(w.type_key.split(":")[1] for w in weapons) == ["HMG", "LMG", "LMG", "LMG", "LMG", "LMG", "LMG", "LMG", "LMG", "MMG"]
    assert state.turn_limit == 5


def test_each_group_sets_up_in_its_own_building(engine):
    seen = {}
    for side in engine.scenario.sides:
        for group in side.groups:
            hexes = group.area.resolve(engine.board)
            building = group.area.building_id(engine.board)
            assert building is not None, group.id
            for h in hexes:
                assert h not in seen, f"{group.id} and {seen.get(h)} share a hex"
                seen[h] = group.id


def control_map(engine, german_player=1, russian_player=0):
    out = {}
    for gid in [g.id for g in engine.scenario.side_spec("german").groups]:
        out[engine.scenario.group(gid).area.building_id(engine.board)] = german_player
    for gid in [g.id for g in engine.scenario.side_spec("russian").groups]:
        out[engine.scenario.group(gid).area.building_id(engine.board)] = russian_player
    return tuple(sorted(out.items()))


def test_the_victory_conditions_read_the_building_control(engine):
    """At the start each side holds its own buildings, so the swing is zero."""
    state = engine.new_game(1).with_(last_occupant=control_map(engine))
    winner, cause, results = victory.evaluate(state, engine.board, engine.scenario, engine.types)
    kinds = [r.kind for r in results]
    assert kinds == ["building_swing", "unbroken_squad_ratio"]
    swing = results[0]
    assert swing.count == 0 and swing.threshold == 2, "no building has changed hands before the first turn"
    ratio = results[1]
    assert ratio.count == 21 and ratio.threshold == 13
    assert winner == "german", "the Germans win by avoiding the Russian conditions"
    assert "building_swing" in cause


def test_a_russian_building_sweep_wins(engine):
    """The Russians hold every German building and lose none of their own."""
    state = engine.new_game(1)
    german_groups = [g.id for g in engine.scenario.side_spec("german").groups]
    russian_groups = [g.id for g in engine.scenario.side_spec("russian").groups]
    control = {}
    for gid in german_groups + russian_groups:
        building = engine.scenario.group(gid).area.building_id(engine.board)
        control[building] = 0
    german_units = {u.id: u.with_(eliminated=True, hex=None) for u in state.units if u.player == 1}
    state = state.with_units(german_units).with_(last_occupant=tuple(sorted(control.items())))
    winner, cause, results = victory.evaluate(state, engine.board, engine.scenario, engine.types)
    assert winner == "russian", cause
    assert results[0].count == 5 and results[0].satisfied


@pytest.mark.slow
def test_two_scripted_games_play_to_the_end_and_replay(engine):
    for seed in (11, 12):
        record = play_game(engine, seed, (ScriptedV1(engine, 0), ScriptedV1(engine, 1)))
        assert record.result in ("german", "russian", "draw")
        assert record.turns_played == 5
        assert replay_record(engine, record)
        rules = {e["rule_id"] for e in record.events}
        for wanted in ("10.6", "10.5", "5.5", "21.2", "4.9"):
            assert wanted in rules, f"rule {wanted} was not applied in the game"
