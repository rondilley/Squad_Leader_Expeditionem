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
# The corner radius as a fraction of the counter size. The 1977 counter has a small die-cut
# radius, so this is smaller than the older `theme.CHIT_RADIUS`, and it is the one the 3D
# prism footprint uses too, so the pale edge follows the same rounded outline (SR-07).
CHIT_RADIUS_FRAC = 0.08
# A minimum face size, in pixels, below which the counter shows no symbol and no numbers.
SYMBOL_MIN = 18


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


def _str_seed(text: str) -> int:
    """A stable seed from a string (FNV-1a), because the built-in hash is not stable."""
    h = 2166136261
    for ch in text:
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return h


def _lighten(colour: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
    return tuple(min(255, c + amount) for c in colour)


def _darken(colour: tuple[int, int, int], amount: int) -> tuple[int, int, int]:
    return tuple(max(0, c - amount) for c in colour)


def _wear_marks(seed: int, face: pygame.Rect, size: float) -> list[tuple[int, int, int]]:
    """The corner nicks of one counter, from its id and not from a generator (SR-07, DR-01).

    A physical counter wears at the corners first. A hashed bit of the id decides whether a
    corner carries a nick and how large it is, so the same counter draws the same wear in
    each session and no picture holds a random number.
    """
    h = (int(seed) * 2654435761 + 1013904223) & 0xFFFFFFFF
    inset = size * 0.16
    corners = (
        (face.left + inset, face.top + inset),
        (face.right - inset, face.top + inset),
        (face.left + inset, face.bottom - inset),
        (face.right - inset, face.bottom - inset),
    )
    marks: list[tuple[int, int, int]] = []
    for i, (px, py) in enumerate(corners):
        bits = (h >> (i * 4)) & 0xF
        if bits < 5:  # about a third of the corners carry a nick
            radius = max(1, int(size * (0.05 + 0.02 * (bits % 3))))
            marks.append((int(px), int(py), radius))
    return marks


def _chit(
    surface: pygame.Surface,
    cx: float,
    cy: float,
    size: float,
    base: tuple[int, int, int],
    seed: int,
    *,
    flipped: bool = False,
    nationality: str | None = None,
    outline: tuple[int, int, int] = theme.INK,
    edge_width: int = 2,
    shadow: bool = True,
) -> pygame.Rect:
    """One die-cut cardboard chit: shadow, cut edge, printed face, bevel, and corner wear.

    A broken unit is a counter turned to its reverse, so `flipped` draws the plainer back
    with a colour band of its side. The light is at the top of the screen (theme), so the
    top and the left of the face take a highlight and the bottom and the right take a shade.
    The returned rectangle is the printed face, which the caller writes the numbers on.

    `shadow` is on for the pygame window, where a flat chit needs a drop shadow to lift off
    the board. It is off for the 3D texture, where the real prism thickness throws the shadow
    and a second painted one would double it.
    """
    radius = max(2, int(size * CHIT_RADIUS_FRAC))
    rect = pygame.Rect(round(cx - size / 2), round(cy - size / 2), round(size), round(size))
    if shadow:
        offset = max(1, int(size * 0.08))
        layer = pygame.Surface((rect.width + offset, rect.height + offset), pygame.SRCALPHA)
        pygame.draw.rect(layer, (*theme.CHIT_SHADOW, theme.CHIT_SHADOW_ALPHA), pygame.Rect(offset, offset, rect.width, rect.height), border_radius=radius)
        surface.blit(layer, (rect.left, rect.top))
    pygame.draw.rect(surface, theme.CHIT_EDGE, rect, border_radius=radius)
    face = rect.inflate(-edge_width * 2, -edge_width * 2)
    face_radius = max(1, radius - edge_width)
    face_base = theme.BACK if flipped else base
    pygame.draw.rect(surface, face_base, face, border_radius=face_radius)
    if flipped and nationality is not None and face.height >= 12:
        height = max(3, int(face.height * 0.30))
        band = pygame.Surface((face.width, height), pygame.SRCALPHA)
        colour = theme.NATIONAL.get(nationality, theme.NATIONAL["german"])
        pygame.draw.rect(band, (*colour, 236), pygame.Rect(0, 0, face.width, height), border_top_left_radius=face_radius, border_top_right_radius=face_radius)
        surface.blit(band, face.topleft)
    if size >= 12:
        light = _lighten(face_base, theme.CHIT_BEVEL_LIGHT)
        dark = _darken(face_base, theme.CHIT_BEVEL_DARK)
        pygame.draw.line(surface, light, (face.left + face_radius, face.top + 1), (face.right - face_radius, face.top + 1))
        pygame.draw.line(surface, light, (face.left + 1, face.top + face_radius), (face.left + 1, face.bottom - face_radius))
        pygame.draw.line(surface, dark, (face.left + face_radius, face.bottom - 1), (face.right - face_radius, face.bottom - 1))
        pygame.draw.line(surface, dark, (face.right - 1, face.top + face_radius), (face.right - 1, face.bottom - face_radius))
        for px, py, worn in _wear_marks(seed, face, size):
            pygame.draw.circle(surface, theme.CHIT_WEAR, (px, py), worn)
    pygame.draw.rect(surface, outline, rect, 1, border_radius=radius)
    return face


def _body(surface: pygame.Surface, unit: dict[str, Any], x: float, y: float, size: float, shadow: bool = True) -> pygame.Rect:
    base = theme.WEAPON if unit["kind"] == "sw" else theme.NATIONAL.get(unit["nationality"], theme.NATIONAL["german"])
    return _chit(surface, x, y, size, base, unit["id"], flipped=unit["broken"], nationality=unit["nationality"], shadow=shadow)


def _counter(
    surface: pygame.Surface,
    unit: dict[str, Any],
    x: float,
    y: float,
    size: float,
    font: pygame.font.Font,
    small: pygame.font.Font,
    shadow: bool = True,
) -> None:
    """One infantry counter: a unit symbol in the top of the face, the numbers below it.

    The 1977 counter carries a symbol and its numbers. A full squad shows two soldiers, a
    half-squad (a crew) one, a leader one officer, and a support weapon its icon (rule 2).
    The symbols are the project's own silhouettes, drawn with primitives (SR-07). The numbers
    sit in the lower part of the face, the way the printed counter has them below the symbol.
    """
    rect = _body(surface, unit, x, y, size, shadow=shadow)
    if size < SYMBOL_MIN:
        return
    kind = unit["kind"]
    # The face splits into a top band for the symbol and a lower band for the numbers.
    symbol_rect = pygame.Rect(rect.left, rect.top, rect.width, int(rect.height * 0.56))
    number_top = rect.top + int(rect.height * 0.58)
    ink = theme.INK
    if kind == "leader":
        _officer(surface, symbol_rect, ink)
        text = f"{unit['morale']}{unit['leadership']:+d}"
    elif kind == "sw":
        _mg_icon(surface, symbol_rect, ink, unit["type"])
        fp = unit.get("firepower", 0)
        rng = unit.get("range", 0)
        text = f"{fp}-{rng}" if rng else ""
    elif kind == "crew":
        _soldiers(surface, symbol_rect, ink, 1)
        text = f"{unit['firepower']}-{unit['range']}-{unit['morale']}"
    else:  # a full squad
        _soldiers(surface, symbol_rect, ink, 2)
        text = f"{unit['firepower']}-{unit['range']}-{unit['morale']}"
    if text:
        label = small.render(text, True, ink)
        surface.blit(label, (rect.centerx - label.get_width() / 2, number_top))
    _markers(surface, unit, rect, small)


def _soldier(surface: pygame.Surface, cx: float, cy: float, h: float, ink: tuple[int, int, int]) -> None:
    """One soldier silhouette: a round head, a body, and two legs, from primitives (SR-07).

    The figure is the project's own simple shape and not a scan. It reads as a standing
    infantryman at counter size.
    """
    head_r = max(1, int(h * 0.16))
    head_cy = cy - h * 0.34
    pygame.draw.circle(surface, ink, (int(cx), int(head_cy)), head_r)
    # The trunk is a tapered body from the neck to the hips.
    neck = head_cy + head_r
    hips = cy + h * 0.10
    width = max(1, int(h * 0.16))
    pygame.draw.line(surface, ink, (int(cx), int(neck)), (int(cx), int(hips)), width)
    # Two arms slope down from the shoulders.
    shoulder = neck + h * 0.06
    arm = h * 0.22
    pygame.draw.line(surface, ink, (int(cx), int(shoulder)), (int(cx - arm), int(shoulder + arm * 0.7)), max(1, int(h * 0.08)))
    pygame.draw.line(surface, ink, (int(cx), int(shoulder)), (int(cx + arm), int(shoulder + arm * 0.4)), max(1, int(h * 0.08)))
    # Two legs from the hips.
    foot = cy + h * 0.44
    leg = max(1, int(h * 0.09))
    pygame.draw.line(surface, ink, (int(cx), int(hips)), (int(cx - h * 0.14), int(foot)), leg)
    pygame.draw.line(surface, ink, (int(cx), int(hips)), (int(cx + h * 0.14), int(foot)), leg)


def _soldiers(surface: pygame.Surface, rect: pygame.Rect, ink: tuple[int, int, int], count: int) -> None:
    """One soldier for a half-squad, two side by side for a full squad (rule 2)."""
    h = rect.height * 0.86
    cy = rect.centery
    if count == 1:
        _soldier(surface, rect.centerx, cy, h, ink)
        return
    gap = rect.width * 0.24
    _soldier(surface, rect.centerx - gap, cy, h, ink)
    _soldier(surface, rect.centerx + gap, cy, h, ink)


def _officer(surface: pygame.Surface, rect: pygame.Rect, ink: tuple[int, int, int]) -> None:
    """One officer silhouette for a leader: a soldier with an arm raised, waving the squad on.

    The raised arm tells the leader apart from a squad's soldier at a glance (rule 2).
    """
    h = rect.height * 0.86
    cx, cy = rect.centerx, rect.centery
    _soldier(surface, cx, cy, h, ink)
    # A raised arm over the head, so the figure reads as an officer and not a rifleman.
    shoulder_y = cy - h * 0.16
    pygame.draw.line(surface, ink, (int(cx), int(shoulder_y)), (int(cx + h * 0.24), int(cy - h * 0.48)), max(1, int(h * 0.08)))


def _mg_icon(surface: pygame.Surface, rect: pygame.Rect, ink: tuple[int, int, int], label: str) -> None:
    """A machine gun on its mount: a barrel over a bipod or a tripod, with its label above.

    The icon is the project's own simple shape (SR-07). An HMG or an MMG stands on a tripod,
    an LMG on a bipod, so the number of legs reads the class off the counter.
    """
    if rect.height >= 16:
        tag = _tiny_label(label)
        text = _label_font().render(tag, True, ink)
        if text.get_width() <= rect.width:
            surface.blit(text, (rect.centerx - text.get_width() / 2, rect.top + 1))
    cx = rect.centerx
    base_y = rect.bottom - rect.height * 0.14
    barrel_y = rect.centery + rect.height * 0.10
    half = rect.width * 0.30
    # The barrel: a level bar with a small receiver box on its right.
    pygame.draw.line(surface, ink, (int(cx - half), int(barrel_y)), (int(cx + half), int(barrel_y)), max(1, int(rect.height * 0.10)))
    box = max(2, int(rect.width * 0.12))
    pygame.draw.rect(surface, ink, pygame.Rect(int(cx + half - box), int(barrel_y - box / 2), box, box))
    # The mount: a tripod for the heavy guns (three legs), a bipod for the light one.
    legs = 3 if label.upper() in ("MMG", "HMG") else 2
    apex = (int(cx), int(barrel_y))
    if legs == 3:
        for dx in (-half * 0.7, 0.0, half * 0.7):
            pygame.draw.line(surface, ink, apex, (int(cx + dx), int(base_y)), max(1, int(rect.height * 0.06)))
    else:
        for dx in (-half * 0.5, half * 0.5):
            pygame.draw.line(surface, ink, apex, (int(cx + dx), int(base_y)), max(1, int(rect.height * 0.06)))


def _tiny_label(text: str) -> str:
    """Keep the weapon label short enough for the top band of a small counter."""
    return text[:4]


_LABEL_FONT: Any = None


def _label_font() -> pygame.font.Font:
    global _LABEL_FONT
    if _LABEL_FONT is None:
        if not pygame.font.get_init():
            pygame.font.init()
        _LABEL_FONT = pygame.font.SysFont("dejavusansmono,consolas,couriernew", 11, bold=True)
    return _LABEL_FONT


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
    shadow: bool = True,
) -> None:
    """Rule 28: the counter shows the movement points, the gun, and a band for a turret."""
    width = size * 1.15
    colour = theme.WRECK if unit["wreck"] else theme.NATIONAL.get(unit["nationality"], theme.NATIONAL["german"])
    rect = _chit(surface, x, y, width, colour, unit["id"], outline=theme.VEHICLE_EDGE, edge_width=2, shadow=shadow)
    if not unit["wreck"] and width >= SYMBOL_MIN:
        _hull(surface, rect, theme.VEHICLE_EDGE)
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


def _hull(surface: pygame.Surface, rect: pygame.Rect, ink: tuple[int, int, int]) -> None:
    """A simple top-view tank hull: a rounded body with a turret circle, the project's own.

    It is a thin outline, so the movement points and the gun number stay readable over it
    (rule 28). The gun barrel of `_gun_barrel` draws on top and gives the facing.
    """
    body = rect.inflate(-int(rect.width * 0.30), -int(rect.height * 0.42))
    pygame.draw.rect(surface, ink, body, max(1, int(rect.width * 0.03)), border_radius=max(1, int(rect.width * 0.10)))
    pygame.draw.circle(surface, ink, (rect.centerx, rect.centery), max(2, int(rect.width * 0.14)), max(1, int(rect.width * 0.03)))


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
        seed = _str_seed(str(token["hex"])) ^ (1 if token.get("own") else 0)
        _chit(surface, cx, cy, size * 0.7, theme.CONCEALED, seed, edge_width=1)
