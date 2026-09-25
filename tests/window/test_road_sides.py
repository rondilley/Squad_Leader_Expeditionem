"""The roads of a board that names its road hexsides (PR-50), in the window and the browser.

Generator version 8 writes the hexsides each road crosses. Seed 1 of a city board has a
crossroads at I5 with roads out of hexsides 0, 2, 3, and 4. The hexes J5, I6, and H5 are
road hexes beside it, and J5 and I6 touch, but no road crosses the hexside between them.
The drawing from before PR-50 joined each pair of adjacent road hexes, so it drew a road
across that corner of the junction. These tests find that stroke.

The browser test builds the renderer with the esbuild of the client and runs it in node,
as tests/host/test_annotate_coverage.py does for the log panel.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slboards.generator import GeneratorParameters, generate_with_retry  # noqa: E402
from slcore.view import board_document  # noqa: E402
from sldata.loaders import load_terrain  # noqa: E402
from slwindow import layout, render, theme  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RENDER_TS = ROOT / "client" / "src" / "board" / "render.ts"
ESBUILD = ROOT / "client" / "node_modules" / ".bin" / "esbuild"


def crossroads_board() -> tuple[dict, dict]:
    """The version 8 document of city seed 1, and the same board with no road hexside.

    The document names `road_sides` from the board, so the test does not depend on the
    version of `board_document` that is in the tree.
    """
    board, _ = generate_with_retry(GeneratorParameters(seed=1), load_terrain())
    assert board.named_road_sides, "generator version 8 names the road hexsides"
    by_id = {h.id: h for h in board}
    named = board_document(board)
    for item in named["hexes"]:
        sides = by_id[item["id"]].road_sides
        if sides:
            item["road_sides"] = list(sides)
    old = board_document(board)
    for item in old["hexes"]:
        item.pop("road_sides", None)
    return named, old


def centres(document: dict) -> dict[str, tuple[int, int]]:
    return {h["id"]: tuple(h["center"]) for h in document["hexes"]}


def midpoint(document: dict, a: str, b: str) -> tuple[float, float]:
    c = centres(document)
    return ((c[a][0] + c[b][0]) / 2.0, (c[a][1] + c[b][1]) / 2.0)


def arm_ends(arms: dict) -> set[tuple[float, float]]:
    return {tuple(end) for ends in arms.values() for end in ends}


def test_the_crossroads_is_what_the_tests_expect():
    named, _ = crossroads_board()
    by_id = {h["id"]: h for h in named["hexes"]}
    assert by_id["I5"]["road_sides"] == [0, 2, 3, 4]
    for name in ("J5", "I6", "H5"):
        assert by_id[name].get("road"), f"{name} is a road hex beside the crossroads"


def test_each_arm_goes_to_the_midpoint_of_a_named_hexside():
    named, _ = crossroads_board()
    arms = render.road_arms(named)
    for item in named["hexes"]:
        if not item.get("road"):
            continue
        centre = tuple(item["center"])
        expected = [
            (centre[0] + render.STEPS[d][0] / 2.0, centre[1] + render.STEPS[d][1] / 2.0)
            for d in sorted(item.get("road_sides", []))
        ]
        assert arms.get(centre, []) == expected, item["id"]


def test_no_arm_crosses_the_corner_of_the_crossroads():
    named, old = crossroads_board()
    corners = [midpoint(named, "J5", "I6"), midpoint(named, "I6", "H5")]
    before = arm_ends(render.road_arms(old))
    assert all(corner in before for corner in corners), "the drawing before PR-50 cut the corner"
    after = arm_ends(render.road_arms(named))
    assert not any(corner in after for corner in corners)
    assert len(render.road_arms(named)[centres(named)["I5"]]) == 4, "the crossroads has four arms"


def road_pixels(surface: pygame.Surface, camera: layout.Camera, point: tuple[float, float]) -> int:
    """The count of road colour pixels in a small square around a lattice point."""
    x, y = camera.to_screen(*point)
    reach = max(2, int(camera.scale * 0.3))
    count = 0
    for dx in range(-reach, reach + 1):
        for dy in range(-reach, reach + 1):
            if tuple(surface.get_at((int(x) + dx, int(y) + dy)))[:3] == theme.ROAD:
                count += 1
    return count


def test_the_window_paints_no_road_across_the_corner():
    named, old = crossroads_board()
    pygame.init()
    font = pygame.font.SysFont(None, 12)
    pictures = {}
    for key, document in (("named", named), ("old", old)):
        surface = pygame.Surface((1320, 400))
        camera = layout.fit(document, 1320, 400)
        render.draw_board(surface, document, camera, font)
        pictures[key] = (surface, camera)
    surface, camera = pictures["old"]
    assert road_pixels(surface, camera, midpoint(old, "J5", "I6")) > 0, "the old drawing cut the corner"
    surface, camera = pictures["named"]
    assert road_pixels(surface, camera, midpoint(named, "J5", "I6")) == 0
    assert road_pixels(surface, camera, midpoint(named, "I6", "H5")) == 0
    for other in ("J5", "I6", "H5"):
        assert road_pixels(surface, camera, midpoint(named, "I5", other)) > 0, f"the arm I5 to {other} is drawn"


def test_a_board_with_no_road_hexside_keeps_the_links_of_before():
    _, old = crossroads_board()
    expected: dict = {}
    for pair in render._road_links(old):
        first, second = sorted(pair)
        middle = ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)
        expected.setdefault(first, []).append(middle)
        expected.setdefault(second, []).append(middle)
    assert render.road_arms(old) == expected


def browser_arms(documents: dict[str, dict], tmp_path: Path) -> dict[str, dict[str, list[list[float]]]]:
    """Run roadArms of client/src/board/render.ts in node on each document."""
    node = shutil.which("node")
    if node is None or not ESBUILD.is_file():
        pytest.fail("node and the esbuild of the client are necessary; run `cd client && npm install`")
    bundle = tmp_path / "render.mjs"
    try:
        subprocess.run(
            [str(ESBUILD), str(RENDER_TS), "--bundle", "--format=esm", "--platform=node", f"--outfile={bundle}"],
            check=True,
            capture_output=True,
            timeout=120,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise AssertionError(f"esbuild did not build the renderer: {exc}") from exc
    for name, document in documents.items():
        (tmp_path / f"{name}.json").write_text(json.dumps(document), encoding="utf-8")
    runner = tmp_path / "run.mjs"
    runner.write_text(
        "import { readFileSync } from 'node:fs';\n"
        "import { roadArms } from './render.mjs';\n"
        f"const names = {json.dumps(sorted(documents))};\n"
        "const out = {};\n"
        "for (const name of names) {\n"
        "  const board = JSON.parse(readFileSync(new URL(`./${name}.json`, import.meta.url), 'utf8'));\n"
        "  out[name] = Object.fromEntries(roadArms(board));\n"
        "}\n"
        "console.log(JSON.stringify(out));\n",
        encoding="utf-8",
    )
    try:
        done = subprocess.run([node, str(runner)], check=True, capture_output=True, timeout=120, text=True)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise AssertionError(f"node did not run the renderer: {exc}") from exc
    return json.loads(done.stdout)


def as_keyed(arms: dict) -> dict[str, list[tuple[float, float]]]:
    return {f"{c[0]},{c[1]}": sorted((float(x), float(y)) for x, y in ends) for c, ends in arms.items()}


def test_the_browser_draws_the_same_arms_as_the_window(tmp_path):
    named, old = crossroads_board()
    found = browser_arms({"named": named, "old": old}, tmp_path)
    for name, document in (("named", named), ("old", old)):
        browser = {key: sorted((float(x), float(y)) for x, y in ends) for key, ends in found[name].items()}
        assert browser == as_keyed(render.road_arms(dict(document))), name
    corner = midpoint(named, "J5", "I6")
    assert not any(corner in ends for ends in as_keyed(render.road_arms(named)).values())
