"""The numbers the renderer shares with the core (FR-30, AR-06).

The client applies no rule, but it does read the same lattice. When it looks for the hex
across a hexside, to draw the crest line of rule 43.2, it steps by the offsets of
`geometry.DIRECTIONS`. Those offsets live twice, once in Python and once in TypeScript,
and a difference between the two draws a crest line along the wrong hexside.

So this test reads the numbers out of the TypeScript source and compares them with the
core. It reads text, and it needs no browser and no build.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from slcore import geometry
from slwindow import theme

RENDER = Path("client") / "src" / "board" / "render.ts"

pytestmark = pytest.mark.skipif(not RENDER.is_file(), reason="the client sources are not here")


def pairs_of(name: str) -> list[tuple[int, int]]:
    """The number pairs of a `const NAME: [number, number][] = [...]` table."""
    text = RENDER.read_text(encoding="utf-8")
    match = re.search(rf"const {name}: \[number, number\]\[\] = \[(.*?)\];", text, re.S)
    assert match, f"{name} is not in {RENDER}"
    return [(int(a), int(b)) for a, b in re.findall(r"\[\s*(-?\d+),\s*(-?\d+),?\s*\]", match.group(1))]


def test_the_renderer_steps_by_the_direction_offsets_of_the_core():
    assert pairs_of("STEPS") == [tuple(d) for d in geometry.DIRECTIONS]


def test_the_renderer_names_the_two_corners_of_each_hexside():
    """The corner indexes have to name the same two vertices the core names."""
    offsets = list(geometry.VERTEX_OFFSETS)
    for direction, (first, second) in enumerate(pairs_of("SIDE_CORNERS")):
        expected = geometry.HEXSIDE_VERTICES[direction]
        assert (offsets[first], offsets[second]) == expected


def test_the_renderer_has_one_shade_for_each_hill_level():
    """Rule 43.1: three levels, and each one is a brown of its own."""
    assert list_of("HILL_FILLS") == [rgb(c) for c in theme.HILL]


def named(name: str) -> str:
    """The value of a `const NAME = "...";` line."""
    text = RENDER.read_text(encoding="utf-8")
    match = re.search(rf'const {name} = "([^"]+)";', text)
    assert match, f"{name} is not in {RENDER}"
    return match.group(1)


def list_of(name: str) -> list[str]:
    """The strings of a `const NAME = [...]` table."""
    text = RENDER.read_text(encoding="utf-8")
    match = re.search(rf"const {name} = \[(.*?)\];", text, re.S)
    assert match, f"{name} is not in {RENDER}"
    return re.findall(r'"([^"]+)"', match.group(1))


def record_of(path: Path, name: str) -> dict[str, str]:
    """The pairs of a `const NAME: Record<string, string> = {...}` table."""
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"const {name}: Record<string, string> = \{{(.*?)\}};", text, re.S)
    assert match, f"{name} is not in {path}"
    return dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", match.group(1)))


def rgb(colour: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % colour


def test_the_browser_and_the_window_hold_the_same_base_tone_of_each_terrain():
    """The two consumers draw one board, so a terrain has one colour and not two.

    The window adds the cel shading of a lit face and a shaded face. The tone below that
    shading is the one the browser fills, so a picture of one and a picture of the other
    show the same board.
    """
    fills = record_of(RENDER, "FILLS")
    assert fills == {k: rgb(v) for k, v in theme.TERRAIN.items()}
    assert named("PAPER") == rgb(theme.PAPER)
    assert named("ROAD_COLOR") == rgb(theme.ROAD)
    assert named("CREST") == rgb(theme.CREST)
    assert named("GRID") == rgb(theme.GRID)
    assert named("CENTRE_DOT") == rgb(theme.CENTRE_DOT)
    assert record_of(RENDER, "HEXSIDE_COLORS") == {k: rgb(v) for k, v in theme.HEXSIDE.items()}


def test_the_browser_and_the_window_hold_the_same_national_colours():
    counters = Path("client") / "src" / "counters" / "draw.ts"
    assert record_of(counters, "NATIONAL") == {k: rgb(v) for k, v in theme.NATIONAL.items()}
