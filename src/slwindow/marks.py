"""The 2D drawing of the tactical overlay (`slwindow.overlay`).

The marks are quiet and thin, in the manner of a pencil on a field map. A shade is a
translucent fill of one hex under the counters. A tracer is a thin dashed line from the
firer to the target that stops short of both counters. A burst is a few short spokes on
the target. A ghost is the dashed outline of a counter on the track hex where the
defensive fire catches a moved unit (rule 16.1). The focus is a thin line round one hex.

Everything here reads the model and the board document. Nothing here decides a rule.
"""

from __future__ import annotations

import math
from typing import Any

import pygame

from slwindow import theme
from slwindow.counters import COUNTER_SCALE, MIN_COUNTER
from slwindow.layout import Camera, hex_corners
from slwindow.overlay import RESULT_BROKEN, RESULT_CHECK, RESULT_KILL, Overlay

# The dash of a tracer and of a ghost outline, in pixels: the mark, then the gap.
DASH = (6, 4)
# A tracer starts this far from the centre of the firer and stops this far from the
# target, as a share of the hex size, so the two counters and the burst stay clear.
TRACER_CLEAR = 0.70
# The spokes of a burst: the count for each result and the length as a share of the size.
SPOKES = {RESULT_KILL: 12, RESULT_BROKEN: 8, RESULT_CHECK: 6}
SPOKES_DEFAULT = 6
SPOKE_LENGTH = 0.30
SPOKE_TURN = 15.0
FOCUS_WIDTH = 2


def draw_shades(surface: pygame.Surface, board: dict[str, Any], camera: Camera, overlay: Overlay) -> None:
    """The translucent fills, drawn before the counters so a counter stays on top."""
    if not overlay.shades:
        return
    centres = _centres(board)
    layer = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    for hex_id, tone in overlay.shades.items():
        centre = centres.get(hex_id)
        colour = theme.SHADE.get(tone)
        if centre is None or colour is None:
            continue
        pygame.draw.polygon(layer, colour, hex_corners(centre, camera))
    surface.blit(layer, (0, 0))


def draw_marks(
    surface: pygame.Surface,
    board: dict[str, Any],
    view: dict[str, Any] | None,
    camera: Camera,
    overlay: Overlay,
    small: pygame.font.Font,
) -> None:
    """The tracers, the bursts, the ghosts, and the focus, drawn after the counters."""
    centres = _centres(board)
    size = camera.scale
    units = {int(u["id"]): u for u in (view or {}).get("units", [])}
    for ghost in overlay.ghosts:
        centre = centres.get(ghost.hex)
        unit = units.get(ghost.unit)
        if centre is not None and unit is not None:
            _ghost(surface, unit, camera.to_screen(*centre), size, small)
    for tracer in overlay.tracers:
        source = centres.get(tracer.source)
        target = centres.get(tracer.target)
        if source is None or target is None:
            continue
        colour = theme.TRACER.get(tracer.kind, theme.TRACER["other"])
        _tracer(surface, camera.to_screen(*source), camera.to_screen(*target), size, colour)
    for burst in overlay.bursts:
        centre = centres.get(burst.hex)
        if centre is not None:
            _burst(surface, camera.to_screen(*centre), size, burst.result)
    if overlay.focus_hex:
        centre = centres.get(overlay.focus_hex)
        if centre is not None:
            pygame.draw.polygon(surface, theme.SELECT, hex_corners(centre, camera), FOCUS_WIDTH)


# ---------------------------------------------------------------------- the pieces


def _centres(board: dict[str, Any]) -> dict[str, tuple[int, int]]:
    index = board.get("_centre_by_id")
    if index is None:
        index = {h["id"]: tuple(h["center"]) for h in board["hexes"]}
        board["_centre_by_id"] = index
    return index


def _line_width(size: float) -> int:
    return 1 if size < 26 else 2


def _tracer(
    surface: pygame.Surface,
    start: tuple[float, float],
    end: tuple[float, float],
    size: float,
    colour: tuple[int, int, int],
) -> None:
    dx, dy = end[0] - start[0], end[1] - start[1]
    length = math.hypot(dx, dy)
    clear = size * TRACER_CLEAR
    if length <= clear * 2:
        return
    ux, uy = dx / length, dy / length
    a = (start[0] + ux * clear, start[1] + uy * clear)
    b = (end[0] - ux * clear, end[1] - uy * clear)
    _dashed(surface, a, b, colour, _line_width(size))


def _dashed(
    surface: pygame.Surface,
    a: tuple[float, float],
    b: tuple[float, float],
    colour: tuple[int, ...],
    width: int,
) -> None:
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    if length < 1.0:
        return
    ux, uy = dx / length, dy / length
    mark, gap = DASH
    at = 0.0
    while at < length:
        stop = min(length, at + mark)
        pygame.draw.line(surface, colour, (a[0] + ux * at, a[1] + uy * at), (a[0] + ux * stop, a[1] + uy * stop), width)
        at = stop + gap


def _burst(surface: pygame.Surface, centre: tuple[float, float], size: float, result: str) -> None:
    """A few spokes on the target. A pale stroke under the tone keeps the mark readable on
    a counter of any stock, the way a stencil reads on a crate."""
    colour = theme.BURST.get(result, theme.BURST["none"])
    count = SPOKES.get(result, SPOKES_DEFAULT)
    length = max(4.0, size * SPOKE_LENGTH)
    width = _line_width(size)
    inner = length * 0.35
    spokes = []
    for i in range(count):
        angle = math.radians(SPOKE_TURN + 360.0 * i / count)
        spokes.append(
            (
                (centre[0] + math.cos(angle) * inner, centre[1] + math.sin(angle) * inner),
                (centre[0] + math.cos(angle) * length, centre[1] + math.sin(angle) * length),
            )
        )
    for stroke, tone in ((width + 2, theme.BURST_HALO), (width, colour)):
        for a, b in spokes:
            pygame.draw.line(surface, tone, a, b, stroke)
    pygame.draw.circle(surface, theme.BURST_HALO, centre, max(2.5, size * 0.06 + 1))
    pygame.draw.circle(surface, colour, centre, max(1.5, size * 0.06))


def _ghost(
    surface: pygame.Surface,
    unit: dict[str, Any],
    centre: tuple[float, float],
    size: float,
    small: pygame.font.Font,
) -> None:
    """The outline of the counter where the fire catches it, and the name of the unit."""
    side = max(MIN_COUNTER, size * COUNTER_SCALE)
    rect = pygame.Rect(0, 0, round(side), round(side))
    rect.center = (round(centre[0]), round(centre[1]))
    stock = theme.NATIONAL.get(str(unit.get("nationality", "")), theme.MARKER)
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(layer, (*stock, theme.GHOST_FILL_ALPHA), layer.get_rect(), border_radius=max(2, int(side * theme.CHIT_RADIUS)))
    surface.blit(layer, rect.topleft)
    line = (*theme.GHOST_LINE, theme.GHOST_LINE_ALPHA)
    corners = [rect.topleft, rect.topright, rect.bottomright, rect.bottomleft]
    for a, b in zip(corners, corners[1:] + corners[:1]):
        _dashed(surface, a, b, line, 1)
    name = ghost_label(unit)
    if name and side >= MIN_COUNTER * 1.5:
        label = small.render(name, True, theme.GHOST_LINE)
        surface.blit(label, (rect.centerx - label.get_width() / 2, rect.centery - label.get_height() / 2))


def ghost_label(unit: dict[str, Any]) -> str:
    """The words on a ghost: the name of a leader, or the three numbers of a squad."""
    name = str(unit.get("name") or "")
    if name:
        return name
    if unit.get("kind") in ("squad", "crew") and "firepower" in unit:
        return f"{unit.get('firepower')}-{unit.get('range')}-{unit.get('morale')}"
    return str(unit.get("type") or "")
