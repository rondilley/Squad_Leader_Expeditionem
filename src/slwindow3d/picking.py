"""Which hex is under the mouse: a ray against the hex prisms of the board.

The 3D window turns a mouse position into a ray in world space through its lens (see
`app.py`). This module holds the rest, and it imports no part of Panda3D, so a test reads
it with no window.

A hex is a prism (see `mesh.py`): a top face at the elevation of the hex and six side faces
down to the base of the board slab. The ray can hit a top face, or the side face of a hill
before it gets to a lower hex behind the hill. The pick is the face with the nearest hit, so
the hex the person sees under the pointer is the hex the pick gives, in the 2D camera and in
the 3D camera.

`world_xy` maps the lattice to world space for the whole window: world x is lattice x, and
world y is minus lattice y times the square root of three. The lattice y grows to the south
(row 1 is at the top of the 2D board), and the world y of Panda3D grows to the north, so the
sign keeps north at the top. Without it the 3D board was a mirror of the 2D board: the play
was the same, but each hex label read backwards. This module holds no rule (AR-06).
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from slcore.geometry import VERTEX_OFFSETS

ROOT_THREE = math.sqrt(3.0)
EPSILON = 1e-9

Vector = tuple[float, float, float]


def world_xy(lattice_x: float, lattice_y: float) -> tuple[float, float]:
    """The world x and y of a lattice point. North (a lower row) is a higher world y."""
    return (float(lattice_x), -float(lattice_y) * ROOT_THREE)


def corner_offsets() -> tuple[tuple[int, int], ...]:
    """`VERTEX_OFFSETS` in the order that goes counterclockwise in world space.

    The world y has the opposite sign of the lattice y, so the lattice order goes clockwise
    in the world. A face built in the reversed order faces up, and a side face built from it
    faces out."""
    return tuple(reversed(VERTEX_OFFSETS))


def hex_corners(hexagon: dict[str, Any]) -> list[tuple[float, float]]:
    """The six corners of a hex in world x and y, counterclockwise."""
    cx = float(hexagon["center"][0])
    cy = float(hexagon["center"][1])
    return [world_xy(cx + ox, cy + oy) for ox, oy in corner_offsets()]


def _inside(point: tuple[float, float], corners: Sequence[tuple[float, float]]) -> bool:
    """True when the point is in the convex hexagon or on its edge."""
    sign = 0
    for i in range(len(corners)):
        x1, y1 = corners[i]
        x2, y2 = corners[(i + 1) % len(corners)]
        cross = (x2 - x1) * (point[1] - y1) - (y2 - y1) * (point[0] - x1)
        if abs(cross) <= EPSILON:
            continue
        side = 1 if cross > 0 else -1
        if sign == 0:
            sign = side
        elif side != sign:
            return False
    return True


def _top_hit(origin: Vector, direction: Vector, top_z: float, corners) -> float | None:
    if abs(direction[2]) <= EPSILON:
        return None
    t = (top_z - origin[2]) / direction[2]
    if t <= 0:
        return None
    point = (origin[0] + direction[0] * t, origin[1] + direction[1] * t)
    return t if _inside(point, corners) else None


def _side_hit(origin: Vector, direction: Vector, top_z: float, base_z: float, a, b) -> float | None:
    """The hit of the ray on the vertical face from corner a to corner b, or None."""
    ex, ey = b[0] - a[0], b[1] - a[1]
    # Solve origin + t * direction = a + s * edge in x and y.
    denominator = direction[0] * ey - direction[1] * ex
    if abs(denominator) <= EPSILON:
        return None
    wx, wy = a[0] - origin[0], a[1] - origin[1]
    t = (wx * ey - wy * ex) / denominator
    s = (wx * direction[1] - wy * direction[0]) / denominator
    if t <= 0 or s < 0 or s > 1:
        return None
    z = origin[2] + direction[2] * t
    if z < base_z - EPSILON or z > top_z + EPSILON:
        return None
    return t


def pick_hex(
    board_doc: dict[str, Any],
    origin: Vector,
    direction: Vector,
    height_per_level: float,
    thickness: float,
) -> str | None:
    """The id of the hex whose prism the ray hits first, or None when it hits no hex.

    `origin` and `direction` are in world space. `height_per_level` and `thickness` are the
    numbers the mesh was built with, so the pick and the picture agree.
    """
    best_t = math.inf
    best_id: str | None = None
    base_z = -thickness
    for hexagon in board_doc["hexes"]:
        top_z = float(int(hexagon.get("elevation", 0) or 0)) * height_per_level
        corners = hex_corners(hexagon)
        t = _top_hit(origin, direction, top_z, corners)
        if t is not None and t < best_t:
            best_t, best_id = t, hexagon["id"]
        if top_z <= 0:
            # A level 0 hex shows no side face over the ground, so a hit on its sides is a
            # hit on the slab edge. The top test covers the hex.
            continue
        for i in range(6):
            t = _side_hit(origin, direction, top_z, base_z, corners[i], corners[(i + 1) % 6])
            if t is not None and t < best_t:
                best_t, best_id = t, hexagon["id"]
    return best_id
