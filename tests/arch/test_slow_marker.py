"""The `slow` marker of tests/conftest.py (B9).

The conftest gives the marker by node ID. A renamed test leaves a stale ID in the list,
and the test then runs in the quick run again. This test collects the suite with
`-m slow` in a new process and finds each ID of the list in the result.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import conftest

ROOT = Path(__file__).resolve().parents[2]


def collect(marker: str) -> set[str]:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", "-m", marker, "tests"],
        capture_output=True,
        text=True,
        timeout=300,
        cwd=str(ROOT),
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]
    return {line.strip() for line in result.stdout.splitlines() if "::" in line}


def test_each_listed_test_has_the_slow_marker():
    slow = collect("slow")
    every = collect("slow or not slow")
    assert slow <= every
    # A module that skips itself on an install with no extra has no ID in the collection.
    # An ID of a module that is in the collection must be in it too, or it is stale.
    modules = {nodeid.split("::")[0] for nodeid in every}
    listed = {nodeid for nodeid in conftest.SLOW_TESTS if nodeid.split("::")[0] in modules}
    stale = sorted(listed - slow)
    assert stale == [], f"these IDs are not tests of the suite now; correct tests/conftest.py: {stale}"


def test_the_quick_run_leaves_out_the_slow_tests():
    quick = collect("not slow and not gate and not integration")
    assert not (quick & conftest.SLOW_TESTS)
    assert len(quick) > 1000
