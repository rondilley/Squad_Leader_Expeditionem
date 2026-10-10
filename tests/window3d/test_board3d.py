"""Tests for the 3D board view.

They need the `view3d` extra. Without panda3d the whole module is skipped, the same way the
pygame window tests skip without pygame.
"""

from __future__ import annotations

import pytest

pytest.importorskip("panda3d")

from panda3d.core import GeomNode, loadPrcFileData  # noqa: E402

# The offscreen window type must be set before a ShowBase is built.
loadPrcFileData("", "window-type offscreen")
loadPrcFileData("", "win-size 320 240")
loadPrcFileData("", "audio-library-name null")

from slcli.play import build_engine  # noqa: E402
from slcore.view import board_document  # noqa: E402
from slwindow3d.mesh import HEIGHT_PER_LEVEL, build_board_geom  # noqa: E402


def _synthetic_board(elevations):
    """A tiny board document with one hex for each elevation in the list."""
    hexes = []
    for i, level in enumerate(elevations):
        hexes.append(
            {
                "id": f"A{i + 1}",
                "col": i,
                "row": 0,
                "center": [i * 6, 0],
                "terrain": "open",
                "elevation": level,
            }
        )
    return {"name": "synthetic", "cols": len(hexes), "rows": 1, "hexes": hexes, "terrain": {}}


def _geom_z_range(node: GeomNode):
    """The lowest and highest world z of every vertex in the node."""
    from panda3d.core import GeomVertexReader

    geom = node.getGeom(0)
    reader = GeomVertexReader(geom.getVertexData(), "vertex")
    lows, highs = [], []
    while not reader.isAtEnd():
        point = reader.getData3()
        lows.append(point.getZ())
        highs.append(point.getZ())
    return (min(lows), max(highs))


def test_build_board_geom_has_vertices():
    engine = build_engine("s01_guards_counterattack")
    board = board_document(engine.board)
    node = build_board_geom(board)
    assert isinstance(node, GeomNode)
    vdata = node.getGeom(0).getVertexData()
    assert vdata.getNumRows() > 0


def test_higher_elevation_reaches_higher_z():
    node = build_board_geom(_synthetic_board([0, 2]))
    _, top = _geom_z_range(node)
    # A level 2 prism reaches 2 * height per level at its top face.
    assert top == pytest.approx(2 * HEIGHT_PER_LEVEL)

    flat = build_board_geom(_synthetic_board([0, 0]))
    _, flat_top = _geom_z_range(flat)
    assert top > flat_top


def test_offscreen_screenshot_is_not_flat(tmp_path):
    from slwindow3d.app import Board3DApp

    engine = build_engine("s01_guards_counterattack")
    board = board_document(engine.board)
    # Synthesize a hill, so the screenshot has 3D relief that shades.
    import math

    cx0 = sum(h["center"][0] for h in board["hexes"]) / len(board["hexes"])
    cy0 = sum(h["center"][1] for h in board["hexes"]) / len(board["hexes"])
    for h in board["hexes"]:
        d = math.hypot(h["center"][0] - cx0, (h["center"][1] - cy0) * math.sqrt(3.0))
        h["elevation"] = max(0, min(3, int((60 - d) / 16)))

    out = tmp_path / "board.png"
    Board3DApp.render_screenshot(board, str(out), frames=3)
    assert out.exists()

    from panda3d.core import PNMImage, Filename

    image = PNMImage()
    assert image.read(Filename.fromOsSpecific(str(out)))
    assert image.getReadXSize() == 320
    assert image.getReadYSize() == 240
    # Not a single flat colour: sample pixels and assert more than one distinct colour.
    seen = set()
    for x in range(0, image.getReadXSize(), 16):
        for y in range(0, image.getReadYSize(), 16):
            seen.add(
                (
                    round(image.getRed(x, y), 2),
                    round(image.getGreen(x, y), 2),
                    round(image.getBlue(x, y), 2),
                )
            )
    assert len(seen) > 1
