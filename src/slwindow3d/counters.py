"""The 3D counters, drawn from the same chit art the pygame window draws.

A counter is a small flat card that lies on the top face of its hex. The picture on the
card is the die-cut chit of `slwindow.counters`, so the 3D view and the pygame window show
the same piece and there is no second counter drawing to keep in step (SR-07).

The path is: draw one chit to an offscreen pygame Surface with the SDL dummy video driver,
copy the pixels into a Panda3D Texture, then put the texture on a CardMaker quad that lies
flat and faces up. The texture is cached by the visible fields of the unit, so a unit that
does not change does not draw again.

This module holds no rule (AR-06). It reads the view document and it draws.
"""

from __future__ import annotations

import math
import os
from typing import Any

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    SamplerState,
    Texture,
    TransparencyAttrib,
)

from slwindow import counters as chit_counters
from slwindow import theme

# The counter is drawn to a small square Surface. This is the pixel size of that chit
# picture, not a world size; the card in the scene is one world unit wide.
CHIT_PIXELS = 128
# A counter is a die-cut chit, so it has a thickness. This is that thickness in world units.
COUNTER_THICKNESS = 0.22
# The step to the side between two counters that share a hex, in world units. It is small,
# so a stack is a heap and not a staircase; the per-counter jitter does the rest.
STACK_STEP = 0.14
# The largest side jitter of one counter in a stack, in world units, and the largest turn in
# degrees. They come from the unit id, so a stack is a deterministic messy heap (SR-07).
JITTER = 0.34
TWIST = 9.0
# The world size of one counter card. A hex is two units across its short radius.
CARD_SIZE = 2.4
# The corner radius of the prism footprint, as a fraction of the card size. It matches the
# 2D chit radius, so the pale cardboard edge follows the same rounded outline (SR-07).
CORNER_FRAC = chit_counters.CHIT_RADIUS_FRAC
# The number of segments that round one corner of the prism.
CORNER_SEGMENTS = 5
# The pale cardboard edge of the chit thickness (the same tone the 2D chit shows).
_EDGE_RGBA = (theme.CHIT_EDGE[0] / 255.0, theme.CHIT_EDGE[1] / 255.0, theme.CHIT_EDGE[2] / 255.0, 1.0)


def _rounded_outline(size: float, radius: float) -> list[tuple[float, float]]:
    """The corner points of a rounded square, counter-clockwise, in the x-y plane.

    The footprint of the counter prism is this outline. It matches the rounded rectangle the
    2D chit draws, so the cut edge of the prism follows the same die-cut corner (SR-07).
    """
    half = size / 2.0
    r = min(radius, half)
    inner = half - r
    points: list[tuple[float, float]] = []
    # The four corner arc centres, counter-clockwise from the bottom-right.
    centres = ((inner, -inner), (inner, inner), (-inner, inner), (-inner, -inner))
    starts = (-math.pi / 2.0, 0.0, math.pi / 2.0, math.pi)
    for (ccx, ccy), start in zip(centres, starts):
        for s in range(CORNER_SEGMENTS + 1):
            angle = start + (math.pi / 2.0) * (s / CORNER_SEGMENTS)
            points.append((ccx + r * math.cos(angle), ccy + r * math.sin(angle)))
    return points


def _prism_node(size: float, thickness: float, rgba: tuple) -> GeomNode:
    """A rounded-square prism: the body of a counter, with a visible thickness.

    The prism sits on top of its hex: its bottom is at z 0 and its top at plus the thickness,
    so a single counter already shows its cut edge. The top face is textured with the chit
    art and mapped so the picture fills the rounded outline. The side walls carry the pale
    cardboard-edge colour and are lit, so the thickness shades under the scene light.
    """
    half = size / 2.0
    bottom, top = 0.0, thickness
    outline = _rounded_outline(size, size * CORNER_FRAC)
    n = len(outline)
    edge = (rgba[0], rgba[1], rgba[2], 1.0)

    fmt = GeomVertexFormat.getV3n3c4t2()
    vdata = GeomVertexData("prism", fmt, Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    normal = GeomVertexWriter(vdata, "normal")
    color = GeomVertexWriter(vdata, "color")
    uv = GeomVertexWriter(vdata, "texcoord")
    tris = GeomTriangles(Geom.UHStatic)
    count = [0]

    def emit(position, face_normal, col, tex):
        vertex.addData3(*position)
        normal.addData3(*face_normal)
        color.addData4(*col)
        uv.addData2(*tex)
        index = count[0]
        count[0] += 1
        return index

    white = (1.0, 1.0, 1.0, 1.0)

    def to_uv(x, y):
        # Map the outline to the chit picture: x to the right is u, y up is v. The pygame
        # picture already accounts for the y flip in `_surface_to_texture`, so v is straight.
        return ((x + half) / size, (y + half) / size)

    # The top face is a triangle fan around the centre, textured with the chit picture.
    centre_top = emit((0.0, 0.0, top), (0, 0, 1), white, (0.5, 0.5))
    top_ring = [emit((x, y, top), (0, 0, 1), white, to_uv(x, y)) for (x, y) in outline]
    for i in range(n):
        a = top_ring[i]
        b = top_ring[(i + 1) % n]
        tris.addVertices(centre_top, a, b)

    # The bottom face, a plain fan with the edge colour. It faces down.
    centre_bot = emit((0.0, 0.0, bottom), (0, 0, -1), edge, (0.5, 0.5))
    bot_ring = [emit((x, y, bottom), (0, 0, -1), edge, (0.5, 0.5)) for (x, y) in outline]
    for i in range(n):
        a = bot_ring[i]
        b = bot_ring[(i + 1) % n]
        tris.addVertices(centre_bot, b, a)

    # The side wall: one quad for each edge of the outline, with an outward normal, in the
    # cardboard-edge colour, so the rim shades under the light.
    for i in range(n):
        x0, y0 = outline[i]
        x1, y1 = outline[(i + 1) % n]
        nx, ny = (y1 - y0), -(x1 - x0)
        length = math.hypot(nx, ny) or 1.0
        nrm = (nx / length, ny / length, 0.0)
        a = emit((x0, y0, bottom), nrm, edge, (0.0, 0.0))
        b = emit((x1, y1, bottom), nrm, edge, (1.0, 0.0))
        c = emit((x1, y1, top), nrm, edge, (1.0, 1.0))
        d = emit((x0, y0, top), nrm, edge, (0.0, 1.0))
        tris.addVertices(a, b, c)
        tris.addVertices(a, c, d)

    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("counter-prism")
    node.addGeom(geom)
    return node

_pygame = None
_font = None
_small = None
_texture_cache: dict[str, Texture] = {}


def _ensure_pygame():
    """Import pygame with the dummy video driver, so it needs no display (SR-07 path)."""
    global _pygame, _font, _small
    if _pygame is not None:
        return _pygame
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
    import pygame

    if not pygame.get_init():
        pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    # A dummy display gives pygame a convert format, so a Surface can be read as pixels. The
    # driver is the dummy one, so no window opens (SR-07 path).
    if pygame.display.get_surface() is None:
        pygame.display.set_mode((1, 1))
    _pygame = pygame
    _font = pygame.font.SysFont("dejavusans,arial,helvetica", 44)
    _small = pygame.font.SysFont("dejavusansmono,consolas,couriernew", 40)
    return pygame


def _unit_key(unit: dict[str, Any]) -> str:
    """A stable key of the fields that change the picture of one counter."""
    parts = [
        str(unit.get("id")),
        str(unit.get("kind")),
        str(unit.get("nationality")),
        str(unit.get("type")),
        str(unit.get("broken")),
        str(unit.get("berserk")),
        str(unit.get("dm")),
        str(unit.get("name")),
        str(unit.get("firepower")),
        str(unit.get("range")),
        str(unit.get("morale")),
        str(unit.get("leadership")),
        str(unit.get("movement_points")),
        str(unit.get("gun")),
        str(unit.get("facing")),
        str(unit.get("wreck")),
        str(unit.get("immobilized")),
        str(unit.get("crew_exposed")),
        str(unit.get("malfunction")),
        str(unit.get("prep_fired")),
        str(unit.get("moved")),
        str(unit.get("riding")),
    ]
    return "|".join(parts)


def _surface_to_texture(surface: Any, key: str) -> Texture:
    """Copy an RGBA pygame Surface into a Panda3D Texture."""
    pygame = _ensure_pygame()
    width, height = surface.get_size()
    # Panda3D reads the image bottom to top, so flip the y of the pygame Surface first.
    flipped = pygame.transform.flip(surface, False, True)
    raw = pygame.image.tostring(flipped, "RGBA", False)
    texture = Texture(f"counter-{key}")
    texture.setup2dTexture(width, height, Texture.TUnsignedByte, Texture.FRgba)
    texture.setRamImageAs(raw, "RGBA")
    texture.setMinfilter(SamplerState.FTLinearMipmapLinear)
    texture.setMagfilter(SamplerState.FTLinear)
    return texture


def counter_texture(unit: dict[str, Any]) -> Texture:
    """A Panda3D Texture of the chit of one unit, cached by its visible fields."""
    key = _unit_key(unit)
    cached = _texture_cache.get(key)
    if cached is not None:
        return cached
    pygame = _ensure_pygame()

    surface = pygame.Surface((CHIT_PIXELS, CHIT_PIXELS), pygame.SRCALPHA)
    centre = CHIT_PIXELS / 2.0
    # The chit fills the whole picture, so the art reaches the rounded edge of the prism top.
    # The 3D chit draws flat (no drop shadow): the real prism thickness throws the shadow.
    size = CHIT_PIXELS
    if unit.get("kind") == "vehicle":
        chit_counters._vehicle(surface, unit, centre, centre, size / chit_counters.VEHICLE_SCALE, _font, _small, shadow=False)
    else:
        chit_counters._counter(surface, unit, centre, centre, size, _font, _small, shadow=False)
    texture = _surface_to_texture(surface, key)
    _texture_cache[key] = texture
    return texture


def _jitter_of(unit_id: Any, stack_index: int) -> tuple[float, float, float]:
    """A stable side offset (dx, dy) and a turn, in world units and degrees, from the id.

    A real stack of counters is a messy heap, not a staircase to one side. Each counter of a
    hex takes a small offset and a small turn from a hash of its id (SR-07, DR-01), so the
    heap is deterministic and holds no random number, and the same unit sits the same way in
    each session. The bottom counter (stack_index 0) stays square and centred, so a lone
    counter is not askew; only the counters above it lean.
    """
    if stack_index == 0:
        return (0.0, 0.0, 0.0)
    h = chit_counters._str_seed(f"{unit_id}:{stack_index}")
    # Three independent bytes of the hash: two for the offset, one for the turn. Each maps to
    # the range minus one to plus one.
    ux = ((h & 0xFF) / 255.0) * 2.0 - 1.0
    uy = (((h >> 8) & 0xFF) / 255.0) * 2.0 - 1.0
    ut = (((h >> 16) & 0xFF) / 255.0) * 2.0 - 1.0
    return (ux * JITTER, uy * JITTER, ut * TWIST)


def add_counter(
    render_node: NodePath,
    unit: dict[str, Any],
    world_x: float,
    world_y: float,
    z: float,
    stack_index: int = 0,
    card_size: float = CARD_SIZE,
) -> NodePath:
    """Place a die-cut counter prism with the unit's chit on the top of its hex.

    The counter body is a rounded-square prism that sits on top of the hex: its bottom is at
    the hex top and its top a thickness above it, so a single counter already shows its cut
    edge. The chit picture is on the top face of the prism, mapped so the art fills the
    rounded outline. Several units in one hex form a messy heap: each one a thickness higher
    than the last, and each with a small deterministic side offset and turn from its id.
    """
    parent = render_node.attachNewNode(f"counter-{unit.get('id')}")
    texture = counter_texture(unit)
    # The body of the counter is a rounded-square prism, so the chit has a real thickness and
    # its cut edge follows the rounded top. The top face carries the chit texture. The prism
    # is lit, so the cardboard rim shades under the scene light. Alpha lets the rounded corner
    # of the picture show the board through it.
    prism = parent.attachNewNode(_prism_node(card_size, COUNTER_THICKNESS, _EDGE_RGBA))
    prism.setTexture(texture)
    prism.setTransparency(TransparencyAttrib.MAlpha)
    # The base of the stack sits at z 0 of the placement, the next a thickness higher, and so
    # on, so the heap grows up from the hex top and each counter shows its own edge.
    dx, dy, twist = _jitter_of(unit.get("id"), stack_index)
    step = STACK_STEP * stack_index
    lift = stack_index * (COUNTER_THICKNESS * 1.02)
    parent.setPos(world_x + step + dx, world_y - step * 0.4 + dy, z + lift)
    parent.setH(twist)
    return parent
