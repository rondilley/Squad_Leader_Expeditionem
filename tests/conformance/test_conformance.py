"""The conformance runner (TC-01). Each case in `cases/` cites its rule and runs here."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from slcore import geometry
from slcore.engine import IllegalCommand
from slcore.game import FireGroup
from slcore.rules import r06_stacking, r08_fire, r10_resolution, r11_terrain, r25_concealment
from slcore.tabledata import CcTable, IftTable

from conformance import harness

CASES_DIR = Path(__file__).parent / "cases"
CASE_TYPES = ("valid", "invalid", "boundary", "interaction")


def load_all() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(CASES_DIR.glob("*.json")):
        doc = json.loads(path.read_text(encoding="utf-8"))
        for case in doc["cases"]:
            case["_file"] = path.name
            out.append(case)
    return out


CASES = load_all()


def _check_units(cs: harness.CaseState, expected: dict[str, dict[str, Any]]) -> None:
    for ref, fields in expected.items():
        unit = cs.unit(ref)
        for key, value in fields.items():
            if key == "hex":
                got = None if unit.hex is None else geometry.hex_id(*unit.hex)
            elif key == "carrier":
                got = None if unit.carrier is None else next(r for r, i in cs.ids.items() if i == unit.carrier)
            else:
                got = getattr(unit, key)
            assert got == value, f"unit {ref}.{key} is {got!r}, the case wants {value!r}"


@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_case(case: dict[str, Any]) -> None:
    assert case["citation"], "each case cites its rule"
    assert case["type"] in CASE_TYPES, case["type"]
    check = case.get("check", "legality")
    if check == "ift":
        return _run_ift(case)
    if check == "cc_odds":
        return _run_cc_odds(case)
    cs = harness.build_case(case)
    if check == "legality":
        return _run_legality(cs, case)
    if check == "effect":
        return _run_effect(cs, case)
    if check == "firepower":
        return _run_firepower(cs, case)
    if check == "drm":
        return _run_drm(cs, case)
    if check == "stacking":
        return _run_stacking(cs, case)
    if check == "morale":
        return _run_morale(cs, case)
    if check == "group_firepower":
        return _run_group_firepower(cs, case)
    if check == "conceal":
        return _run_conceal(cs, case)
    raise AssertionError(f"unknown check {check!r}")


def _run_legality(cs: harness.CaseState, case: dict[str, Any]) -> None:
    ids = harness.frame_ids(cs)
    for payload in case.get("legal", []):
        cmd = cs.command(payload)
        assert cmd.id in ids, f"{payload} should be legal"
    for payload in case.get("illegal", []):
        cmd = cs.command(payload)
        assert cmd.id not in ids, f"{payload} should not be legal"
        with pytest.raises(IllegalCommand):
            cs.engine.apply(cs.state, cmd)


def _run_effect(cs: harness.CaseState, case: dict[str, Any]) -> None:
    events = harness.apply_payloads(cs, case.get("apply", []))
    wanted = case.get("expect_events", [])
    assert harness.events_contain(events, wanted), f"the events do not hold {wanted}: {[ (e['rule_id'], e['kind']) for e in events ]}"
    for key, value in case.get("expect_state", {}).items():
        if key in ("phasing", "active"):
            got = cs.engine.scenario.players()[getattr(cs.state, key)]
        else:
            got = getattr(cs.state, key)
        assert got == value, f"state.{key} is {got!r}, the case wants {value!r}"
    _check_units(cs, case.get("expect_units", {}))
    for key in ("concealment", "smoke", "demo", "sewer_closed", "sewer_lost"):
        wanted = case.get(f"expect_{key}_count")
        if wanted is not None:
            got = len(getattr(cs.state, key))
            assert got == wanted, f"the state has {got} of {key}, the case wants {wanted}"
    for ref in case.get("expect_eliminated", []):
        assert cs.unit(ref).eliminated, f"unit {ref} should be eliminated"
    for ref in case.get("expect_alive", []):
        assert not cs.unit(ref).eliminated, f"unit {ref} should not be eliminated"
    ids = harness.frame_ids(cs)
    for payload in case.get("expect_legal_after", []):
        assert cs.command(payload).id in ids, f"{payload} should be legal after the commands"
    for payload in case.get("expect_illegal_after", []):
        assert cs.command(payload).id not in ids, f"{payload} should not be legal after the commands"
    if case.get("expect_no_events_of_rule"):
        for rule in case["expect_no_events_of_rule"]:
            assert not any(e["rule_id"] == rule for e in events), f"no event of rule {rule} was expected"


def _run_firepower(cs: harness.CaseState, case: dict[str, Any]) -> None:
    target = geometry.parse_hex_id(case["target"])
    unit = cs.unit(case["unit"])
    weapon = cs.unit(case["weapon"]) if case.get("weapon") else None
    result = r08_fire.member_firepower(cs.state, cs.engine.types, unit, weapon, target, bool(case.get("moving", False)))
    if case.get("expect_halves") is None:
        assert result is None, f"the case expects no legal fire, and the code gives {result}"
        return
    assert result is not None, "the case expects a firepower value, and the code gives none"
    assert result.halves == case["expect_halves"], f"firepower is {result.halves} halves, the case wants {case['expect_halves']}"
    for rule in case.get("expect_modifiers", []):
        assert rule in result.modifiers, f"modifier {rule} is missing from {result.modifiers}"


def _run_conceal(cs: harness.CaseState, case: dict[str, Any]) -> None:
    """Rule 25.3: may this unit get a concealment counter at the end of its player turn?"""
    unit = cs.unit(case["unit"])
    got = r25_concealment.can_conceal(cs.state, cs.engine.board, unit)
    assert got == bool(case["expect_conceal"]), f"can_conceal is {got}, the case wants {case['expect_conceal']}"


def _run_drm(cs: harness.CaseState, case: dict[str, Any]) -> None:
    target = geometry.parse_hex_id(case["target"])
    members = tuple((cs.ids[u], None) for u in case["members"])
    leader = cs.ids[case["leader"]] if case.get("leader") else None
    group = FireGroup(target, members, leader)
    total, parts = r10_resolution.common_modifier(cs.engine.fire_ctx, cs.state, group)
    assert total == case["expect_drm"], f"the modifier is {total}, the case wants {case['expect_drm']}: {parts}"


def _run_stacking(cs: harness.CaseState, case: dict[str, Any]) -> None:
    ref = geometry.parse_hex_id(case["hex"])
    player = cs.engine.scenario.side_index(str(case.get("side", "russian")))
    load = r06_stacking.hex_load(cs.state, cs.engine.types, ref, player)
    assert list(load) == case["expect_load"], f"the load is {load}, the case wants {case['expect_load']}"
    assert r06_stacking.over_limit(load) == case["expect_over_limit"]


def _run_morale(cs: harness.CaseState, case: dict[str, Any]) -> None:
    from slcore.rules import r12_morale

    unit = cs.unit(case["unit"])
    cs.state, evs = r12_morale.morale_check(cs.state, cs.engine.types, unit, int(case.get("modifier", 0)), str(case.get("cause", "fire")))
    events = [e.to_dict() for e in evs]
    wanted = case.get("expect_events", [])
    assert harness.events_contain(events, wanted), f"the events do not hold {wanted}: {[(e['rule_id'], e['kind']) for e in events]}"
    _check_units(cs, case.get("expect_units", {}))
    for ref in case.get("expect_eliminated", []):
        assert cs.unit(ref).eliminated, f"unit {ref} should be eliminated"


def _run_group_firepower(cs: harness.CaseState, case: dict[str, Any]) -> None:
    target = geometry.parse_hex_id(case["target"])
    members = tuple((cs.ids[m[0]], None if m[1] is None else cs.ids[m[1]]) for m in case["members"])
    group = FireGroup(target, members, None)
    halves, records = r08_fire.group_firepower(cs.state, cs.engine.types, group)
    assert halves == case["expect_halves"], f"the group has {halves} halves, the case wants {case['expect_halves']}: {records}"
    if "expect_members" in case:
        assert len(records) == case["expect_members"], f"the group has {len(records)} members that fire, the case wants {case['expect_members']}"


def _run_ift(case: dict[str, Any]) -> None:
    table: IftTable = harness.build_engine().tables.ift
    if "expect_column" in case:
        i = table.column_index(case["firepower"])
        got = None if i is None else table.columns[i]
        assert got == case["expect_column"], f"the column for {case['firepower']} is {got}, the case wants {case['expect_column']}"
    if "expect_result" in case:
        got = table.lookup(case["firepower"], case["roll"])
        assert got == case["expect_result"], f"firepower {case['firepower']} at roll {case['roll']} gives {got}, the case wants {case['expect_result']}"


def _run_cc_odds(case: dict[str, Any]) -> None:
    table: CcTable = harness.build_engine().tables.cc
    row = table.odds_row(case["attack"], case["defense"])
    assert row.label == case["expect_odds"], f"{case['attack']} to {case['defense']} gives {row.label}, the case wants {case['expect_odds']}"
    if "expect_kill" in case:
        assert row.kill == case["expect_kill"]


def test_every_rule_family_has_the_four_case_types() -> None:
    """TR-01: a conformance matrix, not one case for each rule."""
    families: dict[str, set[str]] = {}
    for case in CASES:
        family = case["rule"].split(".")[0]
        families.setdefault(family, set()).add(case["type"])
    missing = {f: sorted(set(CASE_TYPES) - t) for f, t in families.items() if set(CASE_TYPES) - t}
    assert not missing, f"these rule families do not have all four case types: {missing}"


def test_the_corpus_covers_the_rules_of_scenario_one() -> None:
    families = {int(c["rule"].split(".")[0]) for c in CASES}
    wanted = set(range(4, 22))
    assert wanted <= families, f"the corpus does not cover rules {sorted(wanted - families)}"
