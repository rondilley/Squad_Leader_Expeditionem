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


# ------------------------------------------------------------------ the counter faces
#
# The window and the browser print one counter. The layout table and the silhouettes live
# twice, once in Python and once in TypeScript, and a difference between the two puts a
# leader's value in a different place or gives a squad a different man (RV-10).

COUNTERS_TS = Path("client") / "src" / "counters" / "draw.ts"
SILHOUETTES_TS = Path("client") / "src" / "counters" / "silhouettes.ts"


def number_record_of(path: Path, name: str) -> dict[str, float]:
    """The pairs of a `const NAME: Record<string, number> = {...}` table."""
    text = path.read_text(encoding="utf-8")
    match = re.search(rf"const {name}: Record<string, number> = \{{(.*?)\}};", text, re.S)
    assert match, f"{name} is not in {path}"
    return {k: float(v) for k, v in re.findall(r"(\w+):\s*(-?[\d.]+)", match.group(1))}


def silhouette_of(name: str) -> list:
    """The parts of an `export const NAME: Silhouette = [...]` list, as Python values."""
    import json

    text = SILHOUETTES_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name}: Silhouette = \[(.*?)\n\];", text, re.S)
    assert match, f"{name} is not in {SILHOUETTES_TS}"
    return json.loads("[" + strip_commas(match.group(1)) + "]")


def strip_commas(body: str) -> str:
    """Drop the trailing commas of TypeScript literals, which JSON does not take."""
    return re.sub(r",\s*(?=[\]\}])", "", body).rstrip().rstrip(",")


def plan_of(name: str) -> dict[str, list]:
    """The parts of an `export const NAME: Plan = {...}` record, keyed by part name."""
    import json

    text = SILHOUETTES_TS.read_text(encoding="utf-8")
    match = re.search(rf"export const {name}: Plan = \{{(.*?)\n\}};", text, re.S)
    assert match, f"{name} is not in {SILHOUETTES_TS}"
    out: dict[str, list] = {}
    for key, body in re.findall(r"(\w+): \[(.*?)\n  \],", match.group(1), re.S):
        out[key] = json.loads("[" + strip_commas(body) + "]")
    return out


def same_parts(ts_parts: list, py_parts: list) -> None:
    assert len(ts_parts) == len(py_parts)
    for (ts_kind, ts_data), (py_kind, py_data) in zip(ts_parts, py_parts):
        assert ts_kind == py_kind
        if py_kind == "poly":
            assert len(ts_data) == len(py_data)
            for (tx, ty), (px, py) in zip(ts_data, py_data):
                assert abs(tx - px) < 1e-3 and abs(ty - py) < 1e-3
        else:
            for t, p in zip(ts_data, py_data):
                assert abs(t - p) < 1e-3


def test_the_browser_and_the_window_print_the_counter_face_from_one_layout():
    from slwindow import counters

    assert number_record_of(COUNTERS_TS, "LAYOUT") == pytest.approx(counters.LAYOUT)


@pytest.mark.parametrize(
    "ts_name, py_name",
    [
        ("RIFLEMAN_WALK", "rifleman_walk"),
        ("RUNNER_SMG", "runner_smg"),
        ("LEADER_STAND", "leader_stand"),
        ("PRONE_RIFLEMAN", "prone_rifleman"),
        ("KNEELING_MAN", "kneeling_man"),
    ],
)
def test_the_browser_and_the_window_draw_the_same_men(ts_name, py_name):
    from slwindow import silhouettes

    same_parts(silhouette_of(ts_name), silhouettes.FIGURES[py_name])


@pytest.mark.parametrize(
    "ts_name, py_name",
    [
        ("LMG_ICON", "mg_light"),
        ("MMG_ICON", "mg_medium"),
        ("HMG_ICON", "mg_heavy"),
        ("FLAMETHROWER_ICON", "flamethrower"),
        ("DEMO_CHARGE_ICON", "demo"),
        ("PANZERFAUST_ICON", "panzerfaust"),
        ("BAZOOKA_ICON", "bazooka"),
    ],
)
def test_the_browser_and_the_window_draw_the_same_weapon_icons(ts_name, py_name):
    from slwindow import silhouettes

    same_parts(silhouette_of(ts_name), silhouettes.ICONS[py_name])


@pytest.mark.parametrize(
    "ts_name, py_plan",
    [
        ("TANK_PLAN", "tank"),
        ("SP_GUN_PLAN", "sp_gun"),
        ("HALFTRACK_PLAN", "halftrack"),
        ("TRUCK_PLAN", "truck"),
        ("JEEP_PLAN", "jeep"),
    ],
)
def test_the_browser_and_the_window_draw_the_same_vehicle_plans(ts_name, py_plan):
    from slwindow import silhouettes

    ts = plan_of(ts_name)
    py = silhouettes.PLANS[py_plan]
    assert list(ts) == list(py)
    for key in py:
        same_parts(ts[key], py[key])


def test_the_browser_and_the_window_draw_the_same_wreck():
    from slwindow import silhouettes

    ts = plan_of("WRECK_PLAN")
    assert list(ts) == list(silhouettes.WRECK_PLAN)
    for key in ts:
        same_parts(ts[key], silhouettes.WRECK_PLAN[key])


def test_the_browser_holds_the_counter_stock_colours_of_the_theme():
    """The berserk red, the marker white, and the open top plan are one tone in both."""
    text = COUNTERS_TS.read_text(encoding="utf-8")

    def const(name: str) -> str:
        match = re.search(rf'const {name} = "([^"]+)";', text)
        assert match, f"{name} is not in {COUNTERS_TS}"
        return match.group(1)

    assert const("BERSERK") == rgb(theme.BERSERK)
    assert const("MARKER") == rgb(theme.MARKER)
    assert const("MARKER_RED") == rgb(theme.MARKER_RED)
    assert const("OPEN_TOP") == rgb(theme.OPEN_TOP)
    assert const("TURRET_BAND") == rgb(theme.TURRET_BAND)
    assert const("WRECK") == rgb(theme.WRECK)
