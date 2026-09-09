"""TC-14a: every generated board satisfies the geomorphic edge rules and joins another.

The gate is 100 percent of 1,000 seeds. The test generates each board in full, because a
rule that only the polygon pass or the fill pass can break must not escape.
"""

from __future__ import annotations

import pytest

from slboards import edges
from slboards.generator import GeneratorParameters, generate
from sldata.loaders import load_terrain

TERRAIN = load_terrain()
SEEDS = 1000


def board_of(seed: int):
    return generate(GeneratorParameters(seed=seed), TERRAIN)


def test_one_thousand_seeds_satisfy_the_edge_rules():
    bad: list[str] = []
    for seed in range(1, SEEDS + 1):
        problems = edges.check_edges(edges.kind_map(board_of(seed)))
        if problems:
            bad.append(f"seed {seed}: {problems[0]}")
    assert not bad, f"{len(bad)} of {SEEDS} boards break an edge rule. First: {bad[:3]}"


def test_boards_from_different_seeds_join_on_the_east_and_on_the_south():
    pairs = [(seed, seed + 1) for seed in range(1, 41)]
    maps = {s: edges.kind_map(board_of(s)) for s in range(1, 42)}
    for a, b in pairs:
        assert edges.check_join(maps[a], maps[b], "east") == []
        assert edges.check_join(maps[a], maps[b], "south") == []


def test_a_board_joins_itself_because_the_constants_are_the_same():
    one = edges.kind_map(board_of(7))
    assert edges.check_join(one, one, "east") == []
    assert edges.check_join(one, one, "south") == []


def test_a_join_side_that_does_not_exist_is_an_error():
    one = edges.kind_map(board_of(3))
    with pytest.raises(ValueError) as exc:
        edges.check_join(one, one, "up")
    assert "east or the south" in str(exc.value)


def test_a_board_with_a_broken_edge_reports_the_hex():
    one = edges.kind_map(board_of(11))
    ref = edges.woods_half_hexes()[0]
    one[ref] = "open"
    problems = edges.check_edges(one)
    assert len(problems) == 1
    assert "must be woods on a seam" in problems[0]
