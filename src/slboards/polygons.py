"""The polygon pass (ARCHITECTURE section 7, pass 4).

Each hex that blocks or hinders the line of sight gets its terrain shape on the exact
lattice. A building fills its hex, as the printed boards mostly do. A woods hex gets one
of a small set of convex shapes, so that a thread through the hex can miss the trees and
the edge does not look procedural.

The lattice has a hex of side 2, so the integer points inside one hex are the center,
the six vertices, and the six points at distance 1 along the axes. The shapes below use
only those points. A finer polygon scale is open question O-07.
"""

from __future__ import annotations

from slcore import geometry
from slcore.geometry import Point
from slcore.state import Polygon, TerrainType
from typing import Mapping, Sequence

# Offsets from a hex center. The whole hex is the six vertices.
WHOLE: tuple[Point, ...] = geometry.VERTEX_OFFSETS

# Convex shapes inside one hex, from the integer points the lattice gives.
SHAPES: tuple[tuple[Point, ...], ...] = (
    WHOLE,
    ((2, 0), (1, 1), (-1, 1), (-1, -1), (1, -1)),
    ((-2, 0), (-1, 1), (1, 1), (1, -1), (-1, -1)),
    ((-1, -1), (1, -1), (2, 0), (1, 1), (-1, 1), (-2, 0)),
    ((0, -1), (2, 0), (0, 1), (-2, 0)),
    ((1, -1), (2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1)),
)


def shape_for(kind: str, index: int) -> tuple[Point, ...]:
    """The outline of one terrain shape. A building fills its hex."""
    if kind.endswith("building"):
        return WHOLE
    return SHAPES[index % len(SHAPES)]


def polygon_at(col: int, row: int, kind: str, index: int) -> Polygon:
    cx, cy = geometry.center(col, row)
    points = [(cx + dx, cy + dy) for dx, dy in shape_for(kind, index)]
    return Polygon.make(kind, points)


def polygons_for(col: int, row: int, kind: str, terrain: Mapping[str, TerrainType], index: int) -> tuple[Polygon, ...]:
    """The shapes of one hex. Terrain that does not touch the line of sight has none."""
    if terrain[kind].los == "clear":
        return ()
    return (polygon_at(col, row, kind, index),)


def convex(points: Sequence[Point]) -> bool:
    return geometry.normalize_polygon(points) is not None
