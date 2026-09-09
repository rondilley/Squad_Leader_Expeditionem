"""The counters of the desktop window, drawn from the view document.

An infantry counter carries the numbers the 1977 counter carries: firepower, range, and
morale for a squad, and morale with the leadership modifier for a leader. A vehicle counter
carries its movement points and its main gun calibre, and a white band marks a turret
(rule 28). The wedge of the covered arc is drawn from the facing (rule 29.4).

The art is the project's own. No scan and no printed layout is in the tree (SR-07).
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import pygame

from slwindow import theme
from slwindow.layout import Camera, ROOT_THREE

MIN_COUNTER = 14
COUNTER_SCALE = 1.5
STACK_STEP = 0.18
DIRECTIONS = ((0, -2), (3, -1), (3, 1), (0, 2), (-3, 1), (-3, -1))
ARC_LENGTH = 5


def draw_counters(
    surface: pygame.Surface,
    board: dict[str, Any],
    view: dict[str, Any],
    camera: Camera,
    font: pygame.font.Font,
    small: pygame.font.Font,
    arc_for: int | None = None,
) -> None:
    centres = {h["id"]: h["center"] for h in board["hexes"]}
    size = max(MIN_COUNTER, camera.scale * COUNTER_SCALE)
    _smoke(surface, centres, view, camera, size)
    if arc_for is not None:
        _covered_arc(surface, board, view, camera, arc_for)
    stacks: dict[str, list[dict[str, Any]]] = {}
    for unit in view["units"]:
        if unit["hex"] is None or unit["carrier"] is not None:
            continue
        stacks.setdefault(unit["hex"], []).append(unit)
    for hex_id, units in sorted(stacks.items()):
        centre = centres.get(hex_id)
        if centre is None:
            continue
        cx, cy = camera.to_screen(*centre)
        # A vehicle is the widest counter, so it goes down first and the infantry on foot
        # sit on top of it, which is how rule 29.3 stacks them on a table.
        units.sort(key=lambda u: (u["kind"] != "vehicle", u["id"]))
        step = size * STACK_STEP
        for index, unit in enumerate(units):
            x = cx - step * (len(units) - 1) / 2 + step * index
            y = cy + step * index * 0.6
            if unit["kind"] == "vehicle":
                _vehicle(surface, unit, x, y, size, font, small)
            else:
                _counter(surface, unit, x, y, size, font, small)
    _concealment(surface, centres, view, camera, size)


def _body(surface: pygame.Surface, unit: dict[str, Any], x: float, y: float, size: float) -> pygame.Rect:
    rect = pygame.Rect(x - size / 2, y - size / 2, size, size)
    colour = theme.NATIONAL.get(unit["nationality"], theme.NATIONAL["german"])
    if unit["broken"]:
        colour = theme.BROKEN
    if unit["kind"] == "sw":
        colour = theme.WEAPON
    pygame.draw.rect(surface, colour, rect)
    pygame.draw.rect(surface, theme.INK, rect, 1)
    return rect


def _counter(
    surface: pygame.Surface,
    unit: dict[str, Any],
    x: float,
    y: float,
    size: float,
    font: pygame.font.Font,
    small: pygame.font.Font,
) -> None:
    rect = _body(surface, unit, x, y, size)
    if size < 18:
        return
    kind = unit["kind"]
    if kind == "leader":
        text = f"{unit['morale']}{unit['leadership']:+d}"
    elif kind == "sw":
        text = unit["type"]
    else:
        text = f"{unit['firepower']}-{unit['range']}-{unit['morale']}"
    label = small.render(text, True, theme.INK)
    surface.blit(label, (rect.centerx - label.get_width() / 2, rect.centery - label.get_height() / 2))
    _markers(surface, unit, rect, small)


def _markers(surface: pygame.Surface, unit: dict[str, Any], rect: pygame.Rect, small: pygame.font.Font) -> None:
    marks = []
    if unit["prep_fired"]:
        marks.append("P")
    if unit["moved"]:
        marks.append("M")
    if unit["malfunction"]:
        marks.append("X")
    if unit.get("riding") is not None:
        marks.append("R")
    if not marks:
        return
    label = small.render("".join(marks), True, theme.INK)
    surface.blit(label, (rect.right - label.get_width() - 1, rect.top + 1))


def _vehicle(
    surface: pygame.Surface,
    unit: dict[str, Any],
    x: float,
    y: float,
    size: float,
    font: pygame.font.Font,
    small: pygame.font.Font,
) -> None:
    """Rule 28: the counter shows the movement points, the gun, and a band for a turret."""
    width = size * 1.15
    rect = pygame.Rect(x - width / 2, y - width / 2, width, width)
    colour = theme.WRECK if unit["wreck"] else theme.NATIONAL.get(unit["nationality"], theme.NATIONAL["german"])
    pygame.draw.rect(surface, colour, rect)
    pygame.draw.rect(surface, theme.VEHICLE_EDGE, rect, 2)
    facing = int(unit.get("facing", -1))
    if facing >= 0 and not unit["wreck"]:
        _gun_barrel(surface, x, y, width, facing)
    if unit["wreck"]:
        pygame.draw.line(surface, theme.INK, rect.topleft, rect.bottomright, 2)
        pygame.draw.line(surface, theme.INK, rect.topright, rect.bottomleft, 2)
        return
    if unit["immobilized"]:
        pygame.draw.rect(surface, theme.IMMOBILE, rect, 3)
    if unit["crew_exposed"]:
        pygame.draw.circle(surface, theme.CREW_EXPOSED, (rect.centerx, rect.top + 3), 3)
    if width < 20:
        return
    top = small.render(str(unit.get("movement_points", 0)), True, theme.INK)
    surface.blit(top, (rect.right - top.get_width() - 2, rect.top + 1))
    gun = unit.get("gun", 0)
    if gun:
        bottom = small.render(str(gun), True, theme.INK)
        surface.blit(bottom, (rect.left + 2, rect.bottom - bottom.get_height() - 1))
    if unit["malfunction"]:
        mark = small.render("X", True, theme.BROKEN)
        surface.blit(mark, (rect.left + 2, rect.top + 1))


def _gun_barrel(surface: pygame.Surface, x: float, y: float, width: float, facing: int) -> None:
    """Rule 29.4: the gun barrel lies along the spine that the covered arc is built from.

    The spines of the lattice point at the vertex offsets, so the barrel of facing zero
    points to the right and the rest follow around it.
    """
    dx, dy = _spine_direction(facing)
    end = (x + dx * width * 0.72, y + dy * width * 0.72)
    pygame.draw.line(surface, theme.VEHICLE_EDGE, (x, y), end, max(2, int(width * 0.12)))


def _spine_direction(facing: int) -> tuple[float, float]:
    """The unit vector of one spine, in screen pixels."""
    offsets = ((2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1), (1, -1))
    ox, oy = offsets[facing % 6]
    x = float(ox)
    y = float(oy) * ROOT_THREE
    length = math.hypot(x, y) or 1.0
    return (x / length, y / length)


def _covered_arc(
    surface: pygame.Surface, board: dict[str, Any], view: dict[str, Any], camera: Camera, unit_id: int
) -> None:
    """Rule 29.4: the wedge the gun covers, shaded over the board."""
    unit = next((u for u in view["units"] if u["id"] == unit_id), None)
    if unit is None or unit["hex"] is None or unit["kind"] != "vehicle":
        return
    facing = int(unit.get("facing", -1))
    if facing < 0:
        return
    centres = {h["id"]: tuple(h["center"]) for h in board["hexes"]}
    origin = centres.get(unit["hex"])
    if origin is None:
        return
    left, right = (facing + 1) % 6, (facing + 2) % 6
    inside = {origin}
    for a in range(ARC_LENGTH + 1):
        for b in range(ARC_LENGTH + 1):
            x = origin[0] + DIRECTIONS[left][0] * a + DIRECTIONS[right][0] * b
            y = origin[1] + DIRECTIONS[left][1] * a + DIRECTIONS[right][1] * b
            inside.add((x, y))
    for hexagon in board["hexes"]:
        if tuple(hexagon["center"]) not in inside:
            continue
        corners = [camera.to_screen(*p) for p in _corner_points(hexagon["center"])]
        _shade(surface, corners, theme.ARC, theme.ARC_ALPHA)


def _corner_points(centre: Sequence[int]) -> list[tuple[int, int]]:
    cx, cy = int(centre[0]), int(centre[1])
    return [(cx + dx, cy + dy) for dx, dy in ((2, 0), (1, 1), (-1, 1), (-2, 0), (-1, -1), (1, -1))]


def _shade(
    surface: pygame.Surface, corners: Sequence[tuple[float, float]], colour: tuple[int, int, int], alpha: int
) -> None:
    xs = [p[0] for p in corners]
    ys = [p[1] for p in corners]
    left, top = min(xs), min(ys)
    width = max(1, int(math.ceil(max(xs) - left)) + 1)
    height = max(1, int(math.ceil(max(ys) - top)) + 1)
    layer = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.polygon(layer, (*colour, alpha), [(x - left, y - top) for x, y in corners])
    surface.blit(layer, (left, top))


def _smoke(
    surface: pygame.Surface, centres: dict[str, Any], view: dict[str, Any], camera: Camera, size: float
) -> None:
    """Rule 24: a smoke counter covers its hex and hides nothing."""
    for hex_id in view.get("smoke", []):
        centre = centres.get(hex_id)
        if centre is None:
            continue
        cx, cy = camera.to_screen(*centre)
        layer = pygame.Surface((int(size * 1.4), int(size * 1.4)), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*theme.SMOKE, 184), (layer.get_width() // 2, layer.get_height() // 2), size * 0.62)
        surface.blit(layer, (cx - layer.get_width() / 2, cy - layer.get_height() / 2))


def _concealment(
    surface: pygame.Surface, centres: dict[str, Any], view: dict[str, Any], camera: Camera, size: float
) -> None:
    """Rule 25: the token stands for a stack, and the other side does not see what is below."""
    for token in view.get("concealment", []):
        centre = centres.get(token["hex"])
        if centre is None:
            continue
        cx, cy = camera.to_screen(*centre)
        rect = pygame.Rect(cx - size * 0.34, cy - size * 0.34, size * 0.68, size * 0.68)
        pygame.draw.rect(surface, theme.CONCEALED, rect)
        pygame.draw.rect(surface, theme.INK, rect, 1)
