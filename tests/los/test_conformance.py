"""Conformance cases for rule 7 on the fixture board. Each case cites its rule."""

import json
from pathlib import Path

import pytest

from slcore import geometry
from slcore.los_cache import LosTable
from slcore.los_eval import evaluate

from los.fixture_board import build_fixture

CASES_PATH = Path(__file__).parent / "cases" / "rule07_cases.json"


def load_cases():
    with CASES_PATH.open("r", encoding="utf-8") as fh:
        doc = json.load(fh)
    return doc["cases"]


CASES = load_cases()
BOARD = build_fixture()
TABLE = LosTable(BOARD)


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case(case):
    assert case["citation"], "each case needs a citation"
    firer = geometry.parse_hex_id(case["firer"])
    target = geometry.parse_hex_id(case["target"])
    result = evaluate(BOARD, TABLE, firer, target)
    assert result.clear == (case["expect"] == "clear"), result
    if "rule_id" in case:
        assert result.rule_id == case["rule_id"], result
    if "blocking_hex" in case:
        assert result.blocking_hex == geometry.parse_hex_id(case["blocking_hex"]), result
    if "traced" in case:
        assert [geometry.hex_id(*r) for r in result.traced] == case["traced"], result
    if "not_traced" in case:
        for hid in case["not_traced"]:
            assert geometry.parse_hex_id(hid) not in result.traced
    if "hindrance" in case:
        assert result.hindrance == case["hindrance"], result


def test_every_case_names_a_rule_in_scope():
    for case in CASES:
        assert case["rule"].split(".")[0].isdigit()
