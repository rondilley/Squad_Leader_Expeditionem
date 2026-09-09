"""From the exact lattice of the core to the pixels of the window.

The core keeps a hex centre as a pair of integers, where the y value carries an implicit
factor of the square root of three (NFR-05). A screen has no such factor, so the camera is
the one place in the project that multiplies by it, and it multiplies pixels and never a
rule value.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Iterable, Sequence

# The lattice: a hex is two units of x from its centre to a left or right vertex, and one
# unit of y. A y unit stands for the square root of three, which is the constant that makes
# the six sides of the hexagon the same length. `client/src/board/geometry.ts` reads the
# same constant, so the two consumers draw the same shape.
ROOT_THREE = math.sqrt(3.0)
VERTEX_OFFSETS = ((2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1), (1, -1))

MIN_SCALE = 2.0
MAX_SCALE = 64.0
DEFAULT_SCALE = 12.0


@dataclass(frozen=True)
class Camera:
    """Where the board sits in the window and how large it is drawn."""

    scale: float = DEFAULT_SCALE
    offset_x: float = 0.0
    offset_y: float = 0.0

    def to_screen(self, x: float, y: float) -> tuple[float, float]:
        return (self.offset_x + x * self.scale, self.offset_y + y * self.scale * ROOT_THREE)

    def to_lattice(self, sx: float, sy: float) -> tuple[float, float]:
        return ((sx - self.offset_x) / self.scale, (sy - self.offset_y) / (self.scale * ROOT_THREE))

    def zoomed(self, factor: float, anchor: tuple[float, float]) -> "Camera":
        """Zoom about a point on the screen, so the board does not move under the pointer.

        The anchor is a point and not a hex, so the lattice position keeps its fraction.
        A round to the nearest hex centre here makes the board jump on each notch of the
        wheel.
        """
        scale = min(MAX_SCALE, max(MIN_SCALE, self.scale * factor))
        if scale == self.scale:
            return self
        lx, ly = self.to_lattice(*anchor)
        moved = replace(self, scale=scale)
        nx, ny = moved.to_screen(lx, ly)
        return replace(moved, offset_x=moved.offset_x + anchor[0] - nx, offset_y=moved.offset_y + anchor[1] - ny)

    def panned(self, dx: float, dy: float) -> "Camera":
        return replace(self, offset_x=self.offset_x + dx, offset_y=self.offset_y + dy)


def hex_corners(centre: Sequence[int], camera: Camera) -> list[tuple[float, float]]:
    """The six corners of one hex, in screen pixels."""
    cx, cy = int(centre[0]), int(centre[1])
    return [camera.to_screen(cx + dx, cy + dy) for dx, dy in VERTEX_OFFSETS]


def polygon_points(points: Iterable[Sequence[int]], camera: Camera) -> list[tuple[float, float]]:
    return [camera.to_screen(int(p[0]), int(p[1])) for p in points]


def hexside_segment(centre: Sequence[int], direction: int, camera: Camera) -> tuple[tuple[float, float], tuple[float, float]]:
    """The two ends of one hexside, in screen pixels.

    The hexside of index d lies between the vertices d+4 and d+5, which is the mapping the
    core uses in `r28_vehicles.crossed_hexsides`.
    """
    corners = hex_corners(centre, camera)
    return corners[(direction + 4) % 6], corners[(direction + 5) % 6]


def fit(board: dict, width: int, height: int, margin: int = 24) -> Camera:
    """A camera that puts the whole board inside a window of this size."""
    xs = [h["center"][0] for h in board["hexes"]]
    ys = [h["center"][1] for h in board["hexes"]]
    if not xs:
        return Camera()
    low_x, high_x = min(xs) - 2, max(xs) + 2
    low_y, high_y = min(ys) - 1, max(ys) + 1
    span_x = max(1, high_x - low_x)
    span_y = max(1, high_y - low_y) * ROOT_THREE
    scale = min((width - 2 * margin) / span_x, (height - 2 * margin) / span_y)
    scale = min(MAX_SCALE, max(MIN_SCALE, scale))
    camera = Camera(scale=scale)
    x0, y0 = camera.to_screen(low_x, low_y)
    x1, y1 = camera.to_screen(high_x, high_y)
    return Camera(
        scale=scale,
        offset_x=(width - (x1 - x0)) / 2 - x0,
        offset_y=(height - (y1 - y0)) / 2 - y0,
    )


def hex_at(board: dict, sx: float, sy: float, camera: Camera) -> str | None:
    """The hex under a point on the screen, or None when the point is off the board."""
    lx, ly = camera.to_lattice(sx, sy)
    best: str | None = None
    best_distance = 0.0
    for hexagon in board["hexes"]:
        cx, cy = hexagon["center"]
        dx = lx - cx
        dy = (ly - cy) * ROOT_THREE
        distance = dx * dx + dy * dy
        if best is None or distance < best_distance:
            best, best_distance = hexagon["id"], distance
    # A hex is two lattice units across its short radius, so a point further than that
    # from every centre is off the board.
    return best if best_distance <= 4.0 else None
