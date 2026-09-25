"""The roads on the top of the 3D board follow the named road hexsides (PR-50).

The 3D window draws the board with `slwindow.render` into one texture, and each hex top
reads its part of it. This test reads that texture back from Panda3D and counts the road
pixels at the corner of the crossroads I5 of city seed 1, where two road hexes touch and
no road crosses the hexside between them (see tests/window/test_road_sides.py).
"""

from __future__ import annotations

import pytest

pytest.importorskip("panda3d")
pytest.importorskip("pygame")

from panda3d.core import loadPrcFileData  # noqa: E402

# The offscreen window type must be set before a ShowBase is built.
loadPrcFileData("", "window-type offscreen")
loadPrcFileData("", "win-size 320 240")
loadPrcFileData("", "audio-library-name null")

from slboards.generator import GeneratorParameters, generate_with_retry  # noqa: E402
from slcore.view import board_document  # noqa: E402
from sldata.loaders import load_terrain  # noqa: E402
from slwindow import theme  # noqa: E402


def crossroads_board(named: bool) -> dict:
    """City seed 1, with its road hexsides (version 8) or with none (the reading of version 7)."""
    board, _ = generate_with_retry(GeneratorParameters(seed=1), load_terrain())
    by_id = {h.id: h for h in board}
    document = board_document(board)
    for item in document["hexes"]:
        item.pop("road_sides", None)
        if named and by_id[item["id"]].road_sides:
            item["road_sides"] = list(by_id[item["id"]].road_sides)
    return document


@pytest.fixture(scope="module")
def app():
    """One offscreen window for the module. Panda3D permits one ShowBase in a process, so a
    window that another module built is used again."""
    import builtins

    from slwindow3d.app import Board3DApp

    existing = getattr(builtins, "base", None)
    if isinstance(existing, Board3DApp):
        yield existing
        return
    instance = Board3DApp(crossroads_board(True))
    yield instance
    instance.destroy()


def road_pixels(texture, camera, document: dict, a: str, b: str) -> int:
    """The road colour pixels of the texture in a small square at the hexside of a and b."""
    centres = {h["id"]: h["center"] for h in document["hexes"]}
    point = ((centres[a][0] + centres[b][0]) / 2.0, (centres[a][1] + centres[b][1]) / 2.0)
    x, y = camera.to_screen(*point)
    width, height = texture.getXSize(), texture.getYSize()
    raw = bytes(texture.getRamImageAs("RGBA"))
    reach = max(2, int(camera.scale * 0.3))
    count = 0
    for dx in range(-reach, reach + 1):
        for dy in range(-reach, reach + 1):
            px, py = int(x) + dx, int(y) + dy
            # Panda3D holds the rows bottom to top.
            at = ((height - 1 - py) * width + px) * 4
            if tuple(raw[at : at + 3]) == theme.ROAD:
                count += 1
    return count


def test_the_3d_board_texture_has_no_road_across_the_corner(app):
    old = crossroads_board(False)
    texture, camera = app._board_texture(old)
    assert road_pixels(texture, camera, old, "J5", "I6") > 0, "the drawing before PR-50 cut the corner"

    named = crossroads_board(True)
    texture, camera = app._board_texture(named)
    assert road_pixels(texture, camera, named, "J5", "I6") == 0
    assert road_pixels(texture, camera, named, "I6", "H5") == 0
    for other in ("J5", "I6", "H5"):
        assert road_pixels(texture, camera, named, "I5", other) > 0, f"the arm I5 to {other} is drawn"
