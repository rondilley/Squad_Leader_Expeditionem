"""The official Q and A rulings (FR-07, TC-02) and the project rulings.

Each official ruling for rules 1 to 21 is either modeled in the core or names the tier
it waits for. Each project ruling names the rule it extends and its cause.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from sldata.loaders import load_project_rulings, load_qa_rulings

CASES_DIR = Path(__file__).parent / "cases"


def corpus_rules() -> set[str]:
    rules: set[str] = set()
    for path in CASES_DIR.glob("*.json"):
        for case in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            rules.add(case["rule"])
            rules.add(case["rule"].split(".")[0])
    return rules


QA = load_qa_rulings()
PROJECT = load_project_rulings()
CORPUS = corpus_rules()


def test_the_rulings_file_covers_the_rules_of_scenario_one():
    families = {int(r["rule"].split(".")[0]) for r in QA}
    assert families <= set(range(1, 28))
    assert len(QA) >= 20, "the rulebook has about twenty rulings for rules 1 to 21"


@pytest.mark.parametrize("ruling", QA, ids=[r["id"] for r in QA])
def test_each_ruling_is_modeled_or_names_its_tier(ruling):
    assert ruling["summary"], "each ruling is in the project's own words"
    assert ruling["status"], "each ruling says what the core does with it"
    if ruling["modeled"]:
        family = ruling["rule"].split(".")[0]
        assert family in CORPUS, f"the corpus has no case for rule family {family}, which ruling {ruling['id']} needs"
    else:
        assert any(word in ruling["status"] for word in ("v0.3", "Scale", "vNext")), f"ruling {ruling['id']} must name the tier it waits for: {ruling['status']}"


@pytest.mark.parametrize("ruling", PROJECT, ids=[r["id"] for r in PROJECT])
def test_each_project_ruling_names_a_rule_and_a_cause(ruling):
    assert ruling["extends"], "a project ruling extends a numbered rule"
    assert ruling["cause"], "a project ruling says why the rules text needs it"
    assert ruling["decided"], "a project ruling carries its date"


def test_the_project_rulings_are_referenced_by_the_corpus_or_the_code():
    """PR-01 to PR-06 are the rulings that the code applies today."""
    ids = {r["id"] for r in PROJECT}
    assert {"PR-01", "PR-02", "PR-03", "PR-04", "PR-05", "PR-06"} <= ids
    text = "\n".join((CASES_DIR / p.name).read_text(encoding="utf-8") for p in CASES_DIR.glob("*.json"))
    for pr in ("PR-01", "PR-03", "PR-04", "PR-05"):
        assert pr in text, f"the corpus does not cite {pr}"
