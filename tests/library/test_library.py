"""The scenario library: 12 project scenarios from 12 slots (owner directive, 2026-10-16).

Each test reads the real slot file and the real counter data, and a candidate goes through
the checks of a scenario file and sets up a real game.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from slagents.registry import build_engine
from slcampaign import library
from slcampaign.run import counter_types, point_values
from slcli import library_cmd
from slcli.play import make_agent, play_game
from slcore import scenario as core_scenario
from sldata.loaders import load_all_counters, scenario_from_document


@pytest.fixture(scope="module")
def data():
    types = counter_types()
    slots, vehicles = library.load_slots()
    return slots, vehicles, types, point_values(types)


def candidate(data, slot_id: str, seed: int = 1, board_seed: int = 1):
    slots, vehicles, types, values = data
    slot = next(s for s in slots if s.id == slot_id)
    return library.candidate(slot, seed, board_seed, types, values, vehicles)


def test_the_library_has_twelve_slots_that_go_up_in_rules_and_boards(data):
    slots, vehicles, _, _ = data
    assert [s.id for s in slots] == [f"L{n:02d}" for n in range(1, 13)]
    assert [s.rules for s in slots] == sorted(s.rules for s in slots)
    assert [len(s.boards) for s in slots] == sorted(len(s.boards) for s in slots)
    assert len({s.title for s in slots}) == 12
    counters = load_all_counters()
    for s in slots:
        assert s.attacker_side != s.defender_side, s.id
        armies = {s.attacker, s.defender} | ({s.defender_second} if s.defender_second else set())
        assert any(w in counters[a] for a in armies for w in s.weapons), s.id
    for army, keys in vehicles.items():
        for key in keys:
            assert counters[army][key].kind == "vehicle", (army, key)


def test_a_candidate_is_the_same_document_for_the_same_seeds(data):
    first, _ = candidate(data, "L04", 5, 9)
    again, _ = candidate(data, "L04", 5, 9)
    assert json.dumps(first, sort_keys=True) == json.dumps(again, sort_keys=True)


def test_a_new_board_seed_changes_the_board_and_not_the_forces(data):
    """The balance searches the board seeds with the forces fixed (owner, 2026-10-16)."""
    a, draw_a = candidate(data, "L08", 3, 1)
    b, draw_b = candidate(data, "L08", 3, 2)
    assert draw_a.to_dict() == draw_b.to_dict()
    assert a["sides"] == b["sides"] and a["turns"] == b["turns"] and a["victory"] == b["victory"]
    seeds_a = [board["seed"] for board in a["board_composition"]["boards"]]
    seeds_b = [board["seed"] for board in b["board_composition"]["boards"]]
    assert seeds_a != seeds_b


def units_of(document) -> set[str]:
    return {u["type"] for side in document["sides"] for g in side["groups"] for u in g["units"]}


def test_a_slot_takes_only_the_features_of_its_rule_level(data):
    l01, _ = candidate(data, "L01")
    assert "smoke_counters" not in l01 and "concealment_counters" not in l01 and "hidden_placement" not in l01
    assert not units_of(l01) & {"FT", "DC", "PF", "8-3-8", "2-4-7", "2-3-7"}
    assert not any(g["id"].endswith("_armor") for side in l01["sides"] for g in side["groups"])
    assert l01["rules_used"][-1] == "21"

    l04, draw = candidate(data, "L04")
    assert draw.attacker.vehicles and draw.defender.vehicles
    assert "smoke_counters" in l04 and "concealment_counters" in l04

    l05, _ = candidate(data, "L05")
    assert l05["hidden_placement"]["side"] == "axis"

    l03, draw = candidate(data, "L03")
    assert l03["first_mover_roll"] is True and l03["victory"][0]["kind"] == "hex_control"
    holds = {g["id"] for side in l03["sides"] for g in side["groups"] if "_hold" in g["id"]}
    assert holds == {"a_hold1", "d_hold1"} and l03["victory"][0]["groups"] == ["d_hold1"]
    # The two sides hold a building each, and the side of the condition gets the attack share.
    assert draw.attacker.points > draw.defender.points


def test_a_slot_of_several_boards_stacks_them_and_holds_a_building_on_each(data):
    for slot_id, count in (("L08", 2), ("L11", 3), ("L12", 4)):
        document, _ = candidate(data, slot_id)
        composition = document["board_composition"]
        assert composition["side"] == "south" and len(composition["boards"]) == count
        holds = [g for side in document["sides"] for g in side["groups"] if "_hold" in g["id"]]
        assert len(holds) == count, slot_id
        assert set(document["victory"][0]["groups"]) == {g["id"] for g in holds}


def test_the_second_army_of_a_defence_holds_the_last_board(data):
    document, draw = candidate(data, "L12")
    assert draw.defender_second is not None and draw.defender_second.nationality == "russian"
    allied = next(s for s in document["sides"] if s["side"] == "allied")
    russian = [g for g in allied["groups"] if g.get("nationality") == "russian"]
    assert russian and all(g["area"]["min_row"] >= 31 for g in russian)


def test_each_slot_gives_a_scenario_that_sets_up(data):
    """The document passes the checks of a scenario file, and the engine sets it up."""
    slots = data[0]
    for slot in slots:
        document, _ = candidate(data, slot.id)
        scenario = scenario_from_document(document)
        assert scenario.title == slot.title and scenario.notes and document["situation"]
        engine = build_engine(document)
        state = engine.new_game(1)
        assert engine.legal_commands(state).commands, slot.id


def test_a_game_of_the_first_slot_plays_to_the_end(data):
    document, _ = candidate(data, "L01")
    engine = build_engine(document)
    record = play_game(engine, 7, (make_agent("v3", engine, 7, 0), make_agent("v3", engine, 7, 1)))
    assert record.result in ("axis", "allied")
    assert record.turns_played == document["turns"] or "condition" in record.result_cause


def test_a_columns_area_takes_a_row_band(data):
    document, _ = candidate(data, "L08")
    engine = build_engine(document)
    band = core_scenario.resolve_columns(engine.board, {"min_col": 2, "max_col": 8, "min_row": 11, "max_row": 20})
    assert band and all(11 <= row <= 20 and 2 <= col <= 8 for col, row in band)
    whole = core_scenario.resolve_columns(engine.board, {"min_col": 2, "max_col": 8})
    assert set(band) < set(whole)


def test_the_card_counts_one_item_in_the_singular():
    assert library.counted(1, "leader", "leaders") == "1 leader"
    assert library.counted(3, "leader", "leaders") == "3 leaders"


def test_the_card_lists_two_items_with_no_comma():
    two = library.LibraryForce("russian", (), (("9-1", 2),), (("4-4-7", 5),), (("LMG", 3),), 0)
    assert library._force_text(two) == "5 squads under 2 leaders and 3 support weapons"
    three = library.LibraryForce("german", (("T34", 1),), (("9-1", 1),), (("4-6-7", 4),), (("LMG", 1),), 0)
    assert library._force_text(three) == "4 squads under 1 leader, 1 support weapon, and 1 armored vehicle"


def test_the_seed_list_takes_ranges_and_lists():
    assert library_cmd.parse_seeds("1-3,7") == [1, 2, 3, 7]
    with pytest.raises(ValueError):
        library_cmd.parse_seeds(" , ")


def test_the_draw_command_writes_a_scenario_file(tmp_path: Path):
    path, document, _ = library_cmd.write_candidate("L02", 4, 6, tmp_path)
    assert path.is_file() and path.name == "lib02_pump_house_s4_b6.json"
    assert json.loads(path.read_text(encoding="utf-8")) == document
    assert build_engine(f"file:{path}").scenario.id == "lib02_pump_house"


def test_the_screen_ranks_the_candidate_nearest_to_an_equal_result(tmp_path: Path):
    """Two draw seeds and two board seeds: the best pair has no failed game and the first
    side nearest to 50 percent. The outcomes are the dicts that a game job gives."""
    pairs = [(1, 1), (1, 2), (2, 1), (2, 2)]
    candidates = {}
    for seed, board_seed in pairs:
        path, document, _ = library_cmd.write_candidate("L01", seed, board_seed, tmp_path)
        candidates[(seed, board_seed)] = (path, document)
    first = candidates[(1, 1)][1]["first_mover"]
    other = "axis" if first == "allied" else "allied"

    def games(wins, losses, errors=0):
        return [{"winner": first, "error": None}] * wins + [{"winner": other, "error": None}] * losses + [
            {"winner": None, "error": "RuntimeError"}
        ] * errors

    outcomes = games(1, 9) + games(4, 5, errors=1) + games(4, 6) + games(8, 2)
    rows, ranked = library_cmd.rank_screen(pairs, candidates, outcomes, 10)
    assert [r["rate"] for r in rows] == [10.0, 40.0, 40.0, 80.0]
    # The pair with a failed game is out; the others go from the nearest to 50 percent.
    assert [(r["draw_seed"], r["board_seed"]) for r in ranked] == [(2, 1), (2, 2), (1, 1)]


def test_the_result_is_the_confirmed_pair_nearest_to_an_equal_result():
    def row(seed, board, rate, errors=0):
        return {"draw_seed": seed, "board_seed": board, "rate": rate, "errors": errors, "balanced": 45 <= rate <= 55}

    confirmations = [row(4, 1, 40.9), row(9, 10, 46.6), row(9, 9, 50.1, errors=2)]
    best = library_cmd.best_confirmation(confirmations)
    assert (best["draw_seed"], best["board_seed"], best["balanced"]) == (9, 10, True)
    assert library_cmd.best_confirmation([]) == {}


def test_a_slot_always_gets_its_required_counters(data):
    """The L02 card names a flamethrower, a charge, and assault engineers, so each draw of
    the slot has them (owner, 2026-10-17)."""
    for seed in range(1, 21):
        _, draw = candidate(data, "L02", seed)
        squads, weapons = dict(draw.attacker.squads), dict(draw.attacker.weapons)
        assert squads.get("8-3-8", 0) >= 2 and weapons.get("FT", 0) >= 1 and weapons.get("DC", 0) >= 1, seed
        assert sum(weapons.values()) <= draw.attacker.squad_count(), seed


def test_a_required_counter_must_be_in_the_army(data):
    slots, vehicles, types, values = data
    slot = next(s for s in slots if s.id == "L01")
    from dataclasses import replace

    wrong = replace(slot, required=((("PF", 1),), ()))
    with pytest.raises(library.ScenarioError, match="PF"):
        library.draw(wrong, 1, types, values, vehicles)


WEAPONS = {"LMG", "MMG", "HMG", "FT", "DC", "PF", "BAZ"}


def test_no_group_is_only_weapons(data):
    """A weapon sets up with a unit. The L03 candidate of draw seed 5 and board seed 8 had
    a group of one MMG before the correction of 2026-10-17."""
    slots = data[0]
    for slot in slots:
        for seed in range(1, 11):
            try:
                document, _ = candidate(data, slot.id, seed, 8)
            except library.ScenarioError:
                continue  # a draw seed with no candidate; the search skips it
            for side in document["sides"]:
                for group in side["groups"]:
                    types = {u["type"] for u in group["units"]}
                    assert not types or not types <= WEAPONS, (slot.id, seed, group["id"])


def test_the_search_skips_a_draw_seed_that_gives_no_candidate(tmp_path: Path):
    """L05 draw seed 3 buys 2 German squads after the vehicles, so it has no candidate."""
    candidates, skipped = library_cmd.make_candidates("L05", [2, 3], [1, 2], tmp_path)
    assert sorted(candidates) == [(2, 1), (2, 2)]
    assert [seed for seed, _ in skipped] == [3] and "squads" in skipped[0][1]


def test_the_card_names_each_building_and_not_a_mark_that_the_board_does_not_have(data):
    """Nothing on the board marks a building. The card named "the marked building", and on
    the L03 card the two sides each held "the largest stone building" (owner, 2026-10-17)."""
    for slot in data[0]:
        document, _ = candidate(data, slot.id)
        texts = [document["situation"]] + [c["note"] for c in document["victory"]]
        assert not any("marked" in t for t in texts), slot.id
        assert "largest stone building" in document["victory"][0]["note"], slot.id


def test_a_two_sided_card_names_the_building_of_the_attacker_and_says_it_does_not_count(data):
    document, _ = candidate(data, "L03", 8, 10)
    assert "The Germans also hold the largest stone building in columns C to I." in document["situation"]
    assert "It does not count for the victory." in document["situation"]
    assert "of the largest stone building in columns U to EE" in document["victory"][0]["note"]
    assert "each wants the other end" not in document["situation"]


def test_the_library_scenarios_are_their_candidates():
    """Each library file is the candidate of its seeds, with the notes of its balance."""
    for name, slot_id, seed, board_seed in (
        ("lib01_grain_office", "L01", 9, 10),
        ("lib02_pump_house", "L02", 3, 4),
        ("lib03_under_the_square", "L03", 8, 10),
        ("lib04_mill_road", "L04", 4, 3),
        ("lib05_orchard_line", "L05", 7, 3),
        ("lib06_the_crest", "L06", 8, 9),
        ("lib07_hedgerows", "L07", 9, 1),
        ("lib08_village_and_hills", "L08", 10, 3),
        ("lib09_street_by_street", "L09", 6, 5),
        ("lib10_hills_and_fields", "L10", 1, 9),
        ("lib11_three_sectors", "L11", 5, 3),
        ("lib12_the_long_front", "L12", 8, 4),
    ):
        path = Path(core_scenario.__file__).parents[1] / "sldata" / "scenarios" / f"{name}.json"
        stored = json.loads(path.read_text(encoding="utf-8"))
        slot, vehicles = library.slot_by_id(slot_id)
        types = counter_types()
        made, _ = library.candidate(slot, seed, board_seed, types, point_values(types), vehicles)
        assert {k: v for k, v in stored.items() if k != "notes"} == {k: v for k, v in made.items() if k != "notes"}, name
        assert f"draw seed {seed} and board seed {board_seed}" in stored["notes"], name


def test_the_mill_of_l04_is_the_building_that_the_defenders_hold(data):
    """PR-57: the card names the mill, and the mill is the building of the victory."""
    from slcore.rules.victory import group_buildings

    document, _ = candidate(data, "L04", 4, 3)
    assert "the mill (the largest stone building in columns U to EE)" in document["victory"][0]["note"]
    engine = build_engine(document)
    hold = group_buildings(engine.scenario, engine.board, ["d_hold1"])
    mills = {h.building.id for h in engine.board if h.building is not None and h.building.landmark == "mill"}
    assert mills == set(hold)


def test_each_board_of_l05_has_its_orchards(data):
    """PR-56: the theme says orchards, so the board has them."""
    document, _ = candidate(data, "L05", 1, 1)
    assert document["board_generator"]["style"] == {"orchards": 2}
    engine = build_engine(document)
    assert sum(1 for h in engine.board if h.terrain == "orchard") >= 6


def test_the_hidden_sentence_gives_the_rules_of_hidden_placement(data):
    """Rule 42: a unit in a woods or building hex is hidden, and each other unit is in view."""
    document, _ = candidate(data, "L05", 1, 1)
    text = document["situation"]
    assert "Each German unit that sets up in a woods hex or a building hex is hidden" in text
    assert "the other units set up in full view" in text
    assert "first shot" not in text and "two orchards" in text


def test_the_card_of_two_defending_armies_names_the_two(data):
    """Rule 42 names a side, so the Russians of the Allied side in L12 hide too (2026-10-18)."""
    document, _ = candidate(data, "L12", 8, 4)
    text = document["situation"]
    assert "Each American or Russian unit that sets up in a woods hex or a building hex is hidden" in text
    assert "Otherwise the Americans and the Russians win." in text
    assert "Allied side" not in text
    assert document["hidden_placement"]["side"] == "allied"
