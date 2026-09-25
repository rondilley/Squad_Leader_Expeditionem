"""The closed key sets of the data files (M2).

Each JSON file of `src/sldata` has a kind, each kind has a closed key set, and each file
loads through its real loader. A key that no reader reads is a `DataKeyError` that names
the file and the key, so a misspelled key does not go silently to a default.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from slcampaign.campaign import load_rules
from slagents.prompted.providers.base import load_config
from sldata import loaders
from sldata.loaders import DataError, DataKeyError, check_keys, keys_for

DATA = Path(loaders.__file__).resolve().parent
FILES = sorted(p.relative_to(DATA).as_posix() for p in DATA.rglob("*.json"))


def test_the_data_directory_has_files() -> None:
    assert "scenarios/s01_guards_counterattack.json" in FILES
    assert "providers.json" in FILES


@pytest.mark.parametrize("relative", FILES)
def test_each_data_file_has_a_key_set_and_holds_to_it(relative: str) -> None:
    spec = keys_for(relative)
    assert spec is not None, f"{relative} has no closed key set in sldata.loaders.keys_for"
    check_keys(json.loads((DATA / relative).read_text(encoding="utf-8")), spec, relative)


@pytest.mark.parametrize("relative", [f for f in FILES if f.startswith("scenarios/")])
def test_each_scenario_loads(relative: str) -> None:
    name = Path(relative).stem
    scenario = loaders.load_scenario(name)
    assert scenario.id
    loaders.board_and_parameters(scenario)


def test_each_other_kind_loads_through_its_loader() -> None:
    terrain = loaders.load_terrain()
    loaders.load_hexsides()
    assert set(loaders.load_all_counters()) == set(loaders.NATIONALITIES)
    tables = loaders.load_tables()
    assert tables.armor is not None and tables.vehicle is not None
    for relative in FILES:
        if relative.startswith("boards/"):
            loaders.load_board(Path(relative).stem, terrain)
    assert loaders.load_qa_rulings()
    assert loaders.load_project_rulings()
    assert load_rules().threshold > 0
    assert load_config().providers


def _scenario_document(name: str = "s02_tractor_works") -> dict:
    return json.loads((DATA / "scenarios" / f"{name}.json").read_text(encoding="utf-8"))


def test_a_misspelled_top_key_of_a_scenario_is_refused_by_name(tmp_path: Path) -> None:
    doc = _scenario_document()
    doc["hidden_placment"] = {"side": "german"}
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DataKeyError) as caught:
        loaders.load_scenario_file(path)
    assert caught.value.key == "hidden_placment"
    assert caught.value.file == str(path)
    assert "hidden_placment" in str(caught.value) and str(path) in str(caught.value)


def test_the_same_document_with_the_right_key_loads(tmp_path: Path) -> None:
    doc = _scenario_document()
    doc["hidden_placement"] = {"side": "german"}
    path = tmp_path / "good.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    assert loaders.load_scenario_file(path).hidden_side == "german"


@pytest.mark.parametrize(
    "change, key, where",
    [
        (lambda d: d["sides"][0]["groups"][0].__setitem__("objectve", True), "objectve", "$.sides[0].groups[0]"),
        (lambda d: d["sides"][0]["groups"][0]["units"][0].__setitem__("cout", 2), "cout", "$.sides[0].groups[0].units[0]"),
        (lambda d: d["sides"][0]["groups"][0]["area"].__setitem__("max_colum", 3), "max_colum", "$.sides[0].groups[0].area"),
        (lambda d: d["victory"][0].__setitem__("margn", 3), "margn", "$.victory[0]"),
        (lambda d: d["board_generator"].__setitem__("sede", 3), "sede", "$.board_generator"),
    ],
)
def test_a_misspelled_nested_key_is_refused_with_its_place(change, key: str, where: str) -> None:
    doc = copy.deepcopy(_scenario_document("s01_guards_counterattack"))
    change(doc)
    with pytest.raises(DataKeyError) as caught:
        check_keys(doc, keys_for("scenarios/x.json"), "scenarios/x.json")
    assert caught.value.key == key
    assert caught.value.path == where


def test_an_unknown_victory_kind_is_refused() -> None:
    doc = _scenario_document("s01_guards_counterattack")
    doc["victory"][0]["kind"] = "hex_contol"
    with pytest.raises(DataError, match="hex_contol"):
        check_keys(doc, keys_for("scenarios/x.json"), "scenarios/x.json")


def test_a_misspelled_counter_field_is_refused() -> None:
    doc = json.loads((DATA / "counters" / "german.json").read_text(encoding="utf-8"))
    doc["types"]["4-6-7"]["moral"] = 7
    with pytest.raises(DataKeyError) as caught:
        check_keys(doc, keys_for("counters/german.json"), "counters/german.json")
    assert caught.value.key == "moral"
    assert caught.value.path == "$.types.4-6-7"


def test_a_misspelled_board_field_is_refused(tmp_path: Path) -> None:
    doc = json.loads((DATA / "boards" / "fixture_10x10.json").read_text(encoding="utf-8"))
    doc["hexes"][0]["elevaton"] = 1
    path = tmp_path / "board.json"
    path.write_text(json.dumps(doc), encoding="utf-8")
    with pytest.raises(DataKeyError, match="elevaton"):
        loaders.load_board_file(path)


def test_a_misspelled_provider_field_is_refused() -> None:
    doc = json.loads((DATA / "providers.json").read_text(encoding="utf-8"))
    doc["providers"][0]["timeout"] = 5
    with pytest.raises(DataKeyError, match="timeout"):
        check_keys(doc, keys_for("providers.json"), "providers.json")
