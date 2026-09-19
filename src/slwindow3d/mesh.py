"""The board as a set of hex prisms, one for each hex, lifted by its elevation.

The prototype in `background/board3d_prototype.py` proved the shape. This module holds the
same geometry: a top face in the terrain colour, six side faces in a darker tone, and a
board slab under the whole thing. The elevation of a hex sets the height of its prism, so a
level 2 hex stands two steps above a level 0 hex, and a slope shades under the light.

The geometry reads the same lattice the rest of the project reads. A hex centre is two
units of x to a vertex and one unit of y, and a y unit carries an implicit factor of the
square root of three (NFR-05). This module maps the lattice to world space, and it is the
one place here that multiplies by the square root of three, the same way the camera of the
pygame window is the one place that multiplies by it.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    Texture,
)

from slcore.geometry import VERTEX_OFFSETS
from slwindow import theme

ROOT_THREE = math.sqrt(3.0)
# Each elevation level lifts a hex by this much. The 1977 board shows a hill as a flat brown
# area, so the height here is a game aid and not a measure. It is small: just enough that the
# side face of a level change is a thin step the eye reads, and not a tower.
HEIGHT_PER_LEVEL = 0.6
THICKNESS = 0.35
SIDE_SHADE = 0.62


def hex_world(center: Sequence[float]) -> tuple[float, float]:
    """The world x and y of a hex centre. The y unit carries the square root of three."""
    return (float(center[0]), float(center[1]) * ROOT_THREE)


def elevation_z(level: int, height_per_level: float = HEIGHT_PER_LEVEL) -> float:
    """The world z of the top face of a hex at this elevation level."""
    return float(level) * height_per_level


def hex_at_world(board_doc: dict[str, Any], wx: float, wy: float, level: int | None = None) -> dict[str, Any] | None:
    """The hex whose top holds a world point, or None when the point is off the board.

    With a level, only a hex of that elevation counts, because a ray that meets the plane
    of one level in the footprint of a hex of another level did not meet that hex's top.
    A hex is two units from its centre to a vertex, so a point further than that from each
    centre is off the board (the same test as `slwindow.layout.hex_at`).
    """
    best = None
    best_distance = 0.0
    for hexagon in board_doc.get("hexes", []):
        if level is not None and int(hexagon.get("elevation", 0) or 0) != level:
            continue
        cx, cy = hex_world(hexagon["center"])
        dx, dy = wx - cx, wy - cy
        distance = dx * dx + dy * dy
        if best is None or distance < best_distance:
            best, best_distance = hexagon, distance
    return best if best is not None and best_distance <= 4.0 else None


def hex_on_ray(
    board_doc: dict[str, Any],
    near: Sequence[float],
    far: Sequence[float],
    height_per_level: float = HEIGHT_PER_LEVEL,
) -> str | None:
    """The id of the first hex top a ray from `near` to `far` meets, or None.

    The tops are flat planes, one for each elevation level of the board, so the ray meets
    each plane at one point. The hex under that point counts when its level is the level
    of the plane, and the nearest such point along the ray is the hex the pointer is on.
    A hill in front of a lower hex hides it, which is what the eye expects.
    """
    nx, ny, nz = float(near[0]), float(near[1]), float(near[2])
    dx, dy, dz = float(far[0]) - nx, float(far[1]) - ny, float(far[2]) - nz
    if abs(dz) < 1e-9:
        return None
    levels = sorted({int(h.get("elevation", 0) or 0) for h in board_doc.get("hexes", [])})
    found: str | None = None
    found_t = 0.0
    for level in levels:
        t = (elevation_z(level, height_per_level) - nz) / dz
        if t < 0.0:
            continue
        hexagon = hex_at_world(board_doc, nx + dx * t, ny + dy * t, level)
        if hexagon is not None and (found is None or t < found_t):
            found, found_t = str(hexagon["id"]), t
    return found


def _col01(rgb: Sequence[int]) -> tuple[float, float, float, float]:
    return (rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0, 1.0)


def _darker(rgb: Sequence[int], factor: float = SIDE_SHADE) -> tuple[float, float, float, float]:
    return (rgb[0] * factor / 255.0, rgb[1] * factor / 255.0, rgb[2] * factor / 255.0, 1.0)


def build_board_geom(
    board_doc: dict[str, Any],
    height_per_level: float = HEIGHT_PER_LEVEL,
    thickness: float = THICKNESS,
) -> GeomNode:
    """One GeomNode with a prism for each hex of the board document.

    The top face fans from the centre of the hex to its six corners, at the elevation z of
    the hex. The six sides drop from that top down to the base of the slab. The terrain of
    the hex gives the colour of the top face, and a darker tone gives the sides, so the
    light picks out the slope of a hill.
    """
    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData("board", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    color = GeomVertexWriter(vdata, "color")
    tris = GeomTriangles(Geom.UHStatic)
    count = [0]

    def add_vertex(position, face_normal, rgba) -> int:
        vertex.addData3(*position)
        normal.addData3(*face_normal)
        color.addData4(*rgba)
        index = count[0]
        count[0] += 1
        return index

    for hexagon in board_doc["hexes"]:
        cx, world_y = hex_world(hexagon["center"])
        lattice_y = float(hexagon["center"][1])
        level = int(hexagon.get("elevation", 0) or 0)
        top_z = elevation_z(level, height_per_level)
        base_z = -thickness
        base_rgb = theme.TERRAIN.get(hexagon["terrain"], theme.GROUND)
        top = _col01(base_rgb)
        side = _darker(base_rgb)
        corners = [
            (cx + ox, (lattice_y + oy) * ROOT_THREE) for ox, oy in VERTEX_OFFSETS
        ]
        # The top face is a fan from the centre to each pair of corners.
        centre_index = add_vertex((cx, world_y, top_z), (0, 0, 1), top)
        top_indices = [add_vertex((x, y, top_z), (0, 0, 1), top) for x, y in corners]
        for i in range(6):
            tris.addVertices(centre_index, top_indices[i], top_indices[(i + 1) % 6])
        # Each of the six sides is a quad from the top edge down to the base.
        for i in range(6):
            x1, y1 = corners[i]
            x2, y2 = corners[(i + 1) % 6]
            nx, ny = (y2 - y1), -(x2 - x1)
            length = math.hypot(nx, ny) or 1.0
            face_normal = (nx / length, ny / length, 0.0)
            a = add_vertex((x1, y1, top_z), face_normal, side)
            b = add_vertex((x1, y1, base_z), face_normal, side)
            c = add_vertex((x2, y2, base_z), face_normal, side)
            d = add_vertex((x2, y2, top_z), face_normal, side)
            tris.addVertices(a, b, c)
            tris.addVertices(a, c, d)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("board")
    node.addGeom(geom)
    return node


def _uv(camera: Any, tex_w: int, tex_h: int, lattice_x: float, lattice_y: float) -> tuple[float, float]:
    """The texture coordinate of a lattice point, from the same 2D layout camera the pygame
    window draws the board with. The `_surface_to_texture` path flips the image, so the v of
    a pixel `py` from the top of the surface is `1 - py / height`."""
    px, py = camera.to_screen(lattice_x, lattice_y)
    return (px / tex_w, 1.0 - py / tex_h)


def _build_tops(board_doc: dict[str, Any], camera: Any, tex_w: int, tex_h: int, height_per_level: float) -> GeomNode:
    """The top face of each hex, with a texture coordinate that reads the 2D board picture."""
    vdata = GeomVertexData("tops", GeomVertexFormat.getV3n3t2(), Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    texcoord = GeomVertexWriter(vdata, "texcoord")
    tris = GeomTriangles(Geom.UHStatic)
    count = [0]

    def add(position, uv) -> int:
        vertex.addData3(*position)
        normal.addData3(0.0, 0.0, 1.0)
        texcoord.addData2(*uv)
        index = count[0]
        count[0] += 1
        return index

    for hexagon in board_doc["hexes"]:
        cx, world_y = hex_world(hexagon["center"])
        lat_x = float(hexagon["center"][0])
        lat_y = float(hexagon["center"][1])
        top_z = elevation_z(int(hexagon.get("elevation", 0) or 0), height_per_level)
        centre = add((cx, world_y, top_z), _uv(camera, tex_w, tex_h, lat_x, lat_y))
        corner_indices = []
        for ox, oy in VERTEX_OFFSETS:
            corner_indices.append(
                add((cx + ox, (lat_y + oy) * ROOT_THREE, top_z), _uv(camera, tex_w, tex_h, lat_x + ox, lat_y + oy))
            )
        for i in range(6):
            tris.addVertices(centre, corner_indices[i], corner_indices[(i + 1) % 6])
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("tops")
    node.addGeom(geom)
    return node


def _build_sides(board_doc: dict[str, Any], height_per_level: float, thickness: float) -> GeomNode:
    """The six side faces of each hex, in a darker tone, so a level change is a shaded step."""
    vdata = GeomVertexData("sides", GeomVertexFormat.getV3n3c4(), Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    color = GeomVertexWriter(vdata, "color")
    tris = GeomTriangles(Geom.UHStatic)
    count = [0]

    def add(position, face_normal, rgba) -> int:
        vertex.addData3(*position)
        normal.addData3(*face_normal)
        color.addData4(*rgba)
        index = count[0]
        count[0] += 1
        return index

    for hexagon in board_doc["hexes"]:
        cx, _ = hex_world(hexagon["center"])
        lat_y = float(hexagon["center"][1])
        top_z = elevation_z(int(hexagon.get("elevation", 0) or 0), height_per_level)
        base_z = -thickness
        side = _darker(theme.TERRAIN.get(hexagon["terrain"], theme.GROUND))
        corners = [(cx + ox, (lat_y + oy) * ROOT_THREE) for ox, oy in VERTEX_OFFSETS]
        for i in range(6):
            x1, y1 = corners[i]
            x2, y2 = corners[(i + 1) % 6]
            nx, ny = (y2 - y1), -(x2 - x1)
            length = math.hypot(nx, ny) or 1.0
            face_normal = (nx / length, ny / length, 0.0)
            a = add((x1, y1, top_z), face_normal, side)
            b = add((x1, y1, base_z), face_normal, side)
            c = add((x2, y2, base_z), face_normal, side)
            d = add((x2, y2, top_z), face_normal, side)
            tris.addVertices(a, b, c)
            tris.addVertices(a, c, d)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("sides")
    node.addGeom(geom)
    return node


def build_textured_board(
    board_doc: dict[str, Any],
    camera: Any,
    texture: Texture,
    tex_w: int,
    tex_h: int,
    height_per_level: float = HEIGHT_PER_LEVEL,
    thickness: float = THICKNESS,
) -> NodePath:
    """The board with the full 2D artwork on the top of each hex and shaded side faces.

    The caller renders the 2D board (woods, buildings, roads, fields, and the rest) to one
    texture and gives the layout camera that drew it. Each hex top reads its own part of that
    picture, so the 3D board shows the same detail as the pygame window, with the elevation
    added as a step. The top art is flat lit, because the 2D picture is already shaded.
    """
    parent = NodePath("board")
    tops = parent.attachNewNode(_build_tops(board_doc, camera, tex_w, tex_h, height_per_level))
    tops.setTexture(texture)
    tops.setLightOff()
    parent.attachNewNode(_build_sides(board_doc, height_per_level, thickness))
    return parent
