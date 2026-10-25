"""The board of the desktop window: terrain drawn as shapes on the ground.

The window draws the board document and the view document that the host sends. It applies
no rule and it reads no rule table (AR-06). Every shape here comes from a field of one of
those two documents.

The look comes from a study of the owner's own boards. What that gave is the visual
language, and the shapes and the colours here are the project's own (SR-07):

- The ground is a light yellow-green. It is the colour, and terrain is a shape on it.
- Woods are a mass of crowns with a ragged edge, and not a green hexagon. The mass spills
  over the hexsides in the same way a wood does.
- A building is the plan of a structure: blocks with a roof, a body, and a wall line. One
  building of four hexes is one plan with panel lines, and not four counters.
- A road is a ribbon with a curve. It enters a hex at one hexside and leaves at another,
  and it bends through the middle.
- A hill is a flat contour in brown that takes the place of the ground, with a crest line
  where two levels meet (rule 43.2).
- A wheatfield is the one terrain that is a hexagon, because it fills its hex (rule 44.2).
- An orchard (PR-56) is rows of small fruit trees on mown ground. It fills its hex as a
  wheatfield does, and its crowns stand in rows, so it does not read as a wood.
- A mill and a windmill (PR-57) are buildings with a mark of their own: a water wheel
  beside the south wall, or four sails over the roof.

The style is cel shading: flat tones with a hard edge, and no gradient. Each feature has a
lit face, a body, a shaded face, and a line around it. The light comes from the top of the
screen, so two hexes that share a hexside draw the same picture.

Nothing here is random at draw time. A crown of a wood and a pit of a shellhole take their
place from the hex they are in, so one board draws the same picture each time.
"""

from __future__ import annotations

import math
from typing import Any

import pygame

from slwindow import theme
from slwindow.layout import ROOT_THREE, Camera, hex_corners, hexside_segment

LABEL_SCALE = 11.0
DETAIL_SCALE = 6.0
GRID_WIDTH = 1
CREST_WIDTH = 3
# The six directions of the lattice, in the order the core numbers them.
STEPS = ((0, -2), (3, -1), (3, 1), (0, 2), (-3, 1), (-3, -1))
MULTI_STORY = 3
# A building block pulls in to this share of the step to a neighbour hex on a side that
# faces open ground, so the footprint is about two thirds of the hex and the ground shows
# around it. A side that a block of the same building covers reaches the full step.
BUILDING_INSET = 0.64
# Below this the crowns of a wood are too small for the light on top of them.
CROWN_LIGHT_SCALE = 12.0
# How many points a road curve is sampled at.
CURVE_STEPS = 10
# The width of a road, as a share of the camera scale. The browser draws with the same
# share (`ROAD_WIDTH_SHARE` in client/src/board/render.ts).
ROAD_WIDTH_SHARE = 0.40


def draw_board(surface: pygame.Surface, board: dict[str, Any], camera: Camera, font: pygame.font.Font) -> None:
    surface.fill(theme.PAPER)
    hexes = board["hexes"]
    levels = {tuple(h["center"]): int(h.get("elevation", 0)) for h in hexes}
    for hexagon in hexes:
        _ground(surface, hexagon, camera)
    for hexagon in hexes:
        _outline(surface, hexagon, camera)
    # The crest line goes over the grid, because a level change is a fact of the ground and
    # the grid is only a help to the eye (rule 43.2).
    for hexagon in hexes:
        _crest(surface, hexagon, camera, levels)
    _roads(surface, board, camera)
    if camera.scale >= DETAIL_SCALE:
        for hexagon in hexes:
            _ground_detail(surface, hexagon, camera)
    _buildings(surface, board, camera)
    if camera.scale >= DETAIL_SCALE:
        for hexagon in hexes:
            if hexagon["terrain"] == "woods":
                _woods(surface, hexagon, camera)
            elif hexagon["terrain"] == "orchard":
                _orchard(surface, hexagon, camera)
        _landmarks(surface, board, camera)
        # The centre dot goes on top of the terrain, because rule 7.1 threads a line of
        # sight from one centre dot to the next.
        for hexagon in hexes:
            _centre_dot(surface, hexagon, camera)
    for hexagon in hexes:
        _hexsides(surface, hexagon, camera, levels)
    if camera.scale >= LABEL_SCALE:
        for hexagon in hexes:
            _label(surface, hexagon, camera, font)


# ------------------------------------------------------------------------ the ground


def _ground(surface: pygame.Surface, hexagon: dict[str, Any], camera: Camera) -> None:
    """The colour of the hex: the ground, a hill contour, or a wheatfield.

    Rule 43.15: a hill hex with no other feature is open ground for the rules, and brown on
    the board. Rule 44.2: a wheatfield fills its hex, so it is the one hexagon of colour.
    A woods hex on flat ground takes the woods colour below its crowns, so no part of the
    mass is bare. On a hill it takes the brown of its level, because the level is the fact
    that the eye has to find and the crowns already say that the hex is a wood.

    A building hex takes the ground it stands on, because a building is a plan that is drawn
    on the ground and not a coloured hexagon.
    """
    kind = hexagon["terrain"]
    level = int(hexagon.get("elevation", 0))
    if kind == "wheat":
        colour = theme.GRAIN
    elif kind == "orchard":
        # PR-56: an orchard fills its hex, as a wheatfield does, so it keeps its tone on a hill.
        colour = theme.ORCHARD_GROUND
    elif level > 0:
        colour = theme.HILL[min(level, len(theme.HILL)) - 1]
    elif kind == "woods":
        colour = theme.WOODS
    elif kind == "shellhole":
        colour = theme.SHELLHOLE
    else:
        colour = theme.GROUND
    pygame.draw.polygon(surface, colour, hex_corners(hexagon["center"], camera))


def _ground_detail(surface: pygame.Surface, hexagon: dict[str, Any], camera: Camera) -> None:
    """The mark that a wheatfield and a shellhole carry inside their hex."""
    kind = hexagon["terrain"]
    cx, cy = camera.to_screen(*hexagon["center"])
    size = camera.scale
    if kind == "wheat":
        _grain(surface, cx, cy, size)
    elif kind == "shellhole":
        _shellhole(surface, cx, cy, size, hexagon)
    if hexagon.get("sewer"):
        # Rule 27.1: the cover of a sewer entrance.
        pygame.draw.circle(surface, theme.SEWER, (cx, cy + size * 0.55), max(2.0, size * 0.20))
        pygame.draw.circle(surface, theme.INK, (cx, cy + size * 0.55), max(2.0, size * 0.20), 1)


def _grain(surface: pygame.Surface, cx: float, cy: float, size: float) -> None:
    """Rule 44.2: furrows of standing crop, so the hex is not a plain yellow patch."""
    rows = 5
    tall = size * ROOT_THREE
    for i in range(rows):
        share = (i + 0.5) / rows
        y = cy - tall * 0.78 + tall * 1.56 * share
        # The hex is two units wide at its middle and one unit wide at its top and bottom.
        half = size * (2.0 - abs(y - cy) / tall) * 0.80
        pygame.draw.line(surface, theme.GRAIN_LINE, (cx - half, y), (cx + half, y), max(1, int(size * 0.07)))
        if i % 2:
            continue
        for step in (-0.55, 0.0, 0.55):
            x = cx + half * step
            pygame.draw.line(surface, theme.GRAIN_STALK, (x, y), (x, y - size * 0.22), max(1, int(size * 0.07)))


def _shellhole(surface: pygame.Surface, cx: float, cy: float, size: float, hexagon: dict[str, Any]) -> None:
    """Rule 44.3: a group of pits. Each pit is a rim in the light and a floor in the shade."""
    radius = max(2.0, size * 0.26)
    for dx, dy in _scatter(hexagon, 6, 0.58):
        x, y = cx + dx * size, cy + dy * size
        pygame.draw.circle(surface, theme.SHELLHOLE_LIGHT, (x, y), radius)
        pygame.draw.circle(surface, theme.SHELLHOLE_PIT, (x, y + radius * 0.28), radius * 0.72)


def _scatter(hexagon: dict[str, Any], count: int, spread: float) -> list[tuple[float, float]]:
    """Points about the centre of a hex, the same ones each time for the same hex.

    The core has one generator and it belongs to the rules, so the window does not touch it.
    These points come from the hex itself, so a board draws the same picture on each frame
    and in each session.
    """
    cx, cy = hexagon["center"]
    out: list[tuple[float, float]] = []
    value = (cx * 73856093) ^ (cy * 19349663)
    for _ in range(count):
        value = (value * 1103515245 + 12345) & 0x7FFFFFFF
        angle = (value % 3600) / 3600.0 * math.tau
        value = (value * 1103515245 + 12345) & 0x7FFFFFFF
        radius = spread * math.sqrt((value % 1000) / 1000.0)
        out.append((math.cos(angle) * radius * 1.55, math.sin(angle) * radius))
    return out


# ------------------------------------------------------------------------- the woods


def _woods(surface: pygame.Surface, hexagon: dict[str, Any], camera: Camera) -> None:
    """Rule 7.2: a wood is a mass of crowns with a ragged edge.

    The mass reaches past the hexsides, in the same way a wood does on the ground. The hex
    below it carries the woods colour, or the brown of its hill level, so no part of it is
    bare.
    """
    cx, cy = camera.to_screen(*hexagon["center"])
    size = camera.scale
    crowns = _scatter(hexagon, 11, 0.95)
    radius = max(2.0, size * 0.38)
    for dx, dy in crowns:
        pygame.draw.circle(surface, theme.WOODS_LINE, (cx + dx * size, cy + dy * size), radius)
    for dx, dy in crowns:
        pygame.draw.circle(
            surface, theme.WOODS_SHADE, (cx + dx * size, cy + dy * size + radius * 0.16), radius * 0.9
        )
    for dx, dy in crowns:
        pygame.draw.circle(surface, theme.WOODS, (cx + dx * size, cy + dy * size - radius * 0.10), radius * 0.82)
    if size < CROWN_LIGHT_SCALE:
        return
    for dx, dy in crowns[::2]:
        pygame.draw.circle(
            surface,
            theme.WOODS_LIGHT,
            (cx + dx * size - radius * 0.24, cy + dy * size - radius * 0.34),
            radius * 0.34,
        )


# ----------------------------------------------------------------------- the orchard

# PR-56: the trees of an orchard stand in three rows of two, three, and two, as offsets from
# the hex centre in units of the camera scale. The rows run east to west.
ORCHARD_TREES = (
    (-0.55, -0.62), (0.55, -0.62),
    (-1.05, 0.0), (0.0, 0.0), (1.05, 0.0),
    (-0.55, 0.62), (0.55, 0.62),
)
ORCHARD_RADIUS = 0.36


def _orchard(surface: pygame.Surface, hexagon: dict[str, Any], camera: Camera) -> None:
    """PR-56: rows of fruit trees on mown ground.

    Each crown has the four tones of a wood crown (the line, the shade, the crown, and the
    light on top), but it is smaller and lighter, and the crowns stand in rows with ground
    between them. A mown strip under each row of trees shows the rows when the crowns are
    small.
    """
    cx, cy = camera.to_screen(*hexagon["center"])
    size = camera.scale
    tall = size * ROOT_THREE
    strip = max(1, int(size * 0.16))
    for dy in (-0.62, 0.0, 0.62):
        y = cy + dy * size
        half = size * (2.0 - abs(y - cy) / tall) * 0.82
        pygame.draw.line(surface, theme.ORCHARD_ROW, (cx - half, y + size * 0.12), (cx + half, y + size * 0.12), strip)
    radius = max(1.5, size * ORCHARD_RADIUS)
    for dx, dy in ORCHARD_TREES:
        x, y = cx + dx * size, cy + dy * size
        pygame.draw.circle(surface, theme.ORCHARD_TREE_LINE, (x, y), radius)
        pygame.draw.circle(surface, theme.ORCHARD_TREE_SHADE, (x, y + radius * 0.16), radius * 0.88)
        pygame.draw.circle(surface, theme.ORCHARD_TREE, (x, y - radius * 0.10), radius * 0.78)
        if size >= CROWN_LIGHT_SCALE:
            pygame.draw.circle(surface, theme.ORCHARD_TREE_LIGHT, (x - radius * 0.24, y - radius * 0.34), radius * 0.32)


# --------------------------------------------------------------------- the buildings


def _buildings(surface: pygame.Surface, board: dict[str, Any], camera: Camera) -> None:
    """Rules 7.4 and 7.5: a building is the plan of a structure and not a hexagon.

    Each hex of the building is one small block of the plan. The block sits inside the hex,
    so the ground shows around it and it stays within the hex boundary. The block reaches
    out to a neighbour hex only when that hex holds the same building. So a block that faces
    open ground pulls in from the hex edge, and a block that faces another block of the same
    building reaches to the shared line. Several hexes of one building then read as one
    connected mass, and one hex reads as a small house.

    The outline goes on the sides of a block that no block of the same building covers. So
    the line follows the outside of one building. Two buildings that touch each keep a line,
    and a shared side inside one building carries none.

    Rule 7.5: a building of three hexes or more has a second story, which is a smaller block
    on the roof.
    """
    index = _by_centre(board)
    plans = []
    for hexagon in board["hexes"]:
        building = hexagon.get("building")
        if building is None:
            continue
        tones = theme.BUILDING.get(hexagon["terrain"])
        if tones is None:
            continue
        plans.append((hexagon, building, tones))
    if not plans:
        return
    size = camera.scale
    # The full step from a hex centre to a neighbour centre is 1.5 units across and one
    # short radius down. The block reaches this far on a side that a neighbour block covers.
    reach_x, reach_y = size * 1.5, size * ROOT_THREE
    # A side that faces open ground pulls in to this share of the step, so the footprint is
    # about two thirds of the hex and the ground shows around it.
    inset = BUILDING_INSET
    edge = max(1, int(size * 0.10))
    lift = max(2.0, size * 0.20)

    def joined(hexagon, building, dx: int, dy: int) -> bool:
        cx, cy = hexagon["center"]
        other = index.get((cx + dx, cy + dy))
        return other is not None and (other.get("building") or {}).get("id") == building.get("id")

    def block(hexagon, building, shift: float = 0.0) -> pygame.Rect:
        """The rectangle of one hex, pulled in on each open side and full on a joined side."""
        cx, cy = camera.to_screen(*hexagon["center"])
        north = reach_y if joined(hexagon, building, 0, -2) else reach_y * inset
        south = reach_y if joined(hexagon, building, 0, 2) else reach_y * inset
        west = reach_x if joined(hexagon, building, -3, -1) or joined(hexagon, building, -3, 1) else reach_x * inset
        east = reach_x if joined(hexagon, building, 3, -1) or joined(hexagon, building, 3, 1) else reach_x * inset
        left = round(cx - west + shift)
        top = round(cy - north + shift)
        return pygame.Rect(left, top, round(cx + east + shift) - left, round(cy + south + shift) - top)

    for hexagon, building, _tones in plans:
        pygame.draw.rect(surface, theme.GROUND_SHADE, block(hexagon, building, shift=lift))
    for hexagon, building, tones in plans:
        pygame.draw.rect(surface, tones["roof"], block(hexagon, building))
    # The wall that the light does not reach is on the south of the mass, which is the block
    # that has no block of the same building below it.
    for hexagon, building, tones in plans:
        if joined(hexagon, building, 0, 2):
            continue
        rect = block(hexagon, building)
        band = max(2, int(rect.height * 0.30))
        pygame.draw.rect(surface, tones["body"], pygame.Rect(rect.left, rect.bottom - band, rect.width, band))
    # A panel line where two blocks of one plan meet, so the eye reads the roof as sections.
    for hexagon, building, tones in plans:
        pygame.draw.rect(surface, tones["body"], block(hexagon, building), 1)
    if size >= DETAIL_SCALE:
        for hexagon, building, tones in plans:
            if int(building.get("size", 1)) < MULTI_STORY:
                continue
            rect = block(hexagon, building)
            rect = rect.inflate(-rect.width * 0.5, -rect.height * 0.5)
            upper = max(2, int(rect.height * 0.30))
            pygame.draw.rect(surface, tones["roof"], rect)
            pygame.draw.rect(surface, tones["shade"], pygame.Rect(rect.left, rect.bottom - upper, rect.width, upper))
            pygame.draw.rect(surface, tones["line"], rect, 1)
    for hexagon, building, tones in plans:
        _wall_line(surface, block(hexagon, building), hexagon, building, tones["line"], edge, joined)


# PR-57: the number of spokes of a water wheel and the angle of the sails of a windmill.
WHEEL_SPOKES = 8
SAIL_ANGLE = math.radians(20.0)


def _landmarks(surface: pygame.Surface, board: dict[str, Any], camera: Camera) -> None:
    """PR-57: the mark of each mill and each windmill on top of the plan of its building.

    The mark sits on the middle of the building: the mean of the centres of its hexes. A
    mill gets a water wheel at the south wall, with a strip of water below it. A windmill
    gets four sails on a hub, and the sails reach past the walls, as the sails of a windmill
    do from above.
    """
    found: dict[str, tuple[str, list[tuple[float, float]]]] = {}
    for hexagon in board["hexes"]:
        building = hexagon.get("building") or {}
        landmark = building.get("landmark")
        if landmark is None:
            continue
        found.setdefault(str(building["id"]), (str(landmark), []))[1].append(camera.to_screen(*hexagon["center"]))
    size = camera.scale
    tones = theme.LANDMARK
    line = max(1, int(size * 0.10))
    for _name, (landmark, centres) in sorted(found.items()):
        cx = sum(x for x, _ in centres) / len(centres)
        cy = sum(y for _, y in centres) / len(centres)
        if landmark == "mill":
            south = max(y for _, y in centres) + size * ROOT_THREE * BUILDING_INSET
            radius = max(3.0, size * 0.80)
            wx, wy = cx, south
            pygame.draw.rect(
                surface, tones["water"],
                pygame.Rect(round(wx - radius * 1.8), round(wy - radius * 0.25), round(radius * 3.6), round(radius * 0.5)),
            )
            pygame.draw.circle(surface, tones["line"], (wx, wy), radius + line)
            pygame.draw.circle(surface, tones["wood"], (wx, wy), radius)
            pygame.draw.circle(surface, tones["light"], (wx, wy - radius * 0.12), radius * 0.62)
            for i in range(WHEEL_SPOKES):
                angle = math.tau * i / WHEEL_SPOKES
                end = (wx + math.cos(angle) * radius, wy + math.sin(angle) * radius)
                pygame.draw.line(surface, tones["line"], (wx, wy), end, line)
            pygame.draw.circle(surface, tones["line"], (wx, wy), max(1.5, radius * 0.22))
        elif landmark == "windmill":
            length = max(4.0, size * 1.90)
            width = max(2.0, size * 0.42)
            for i in range(4):
                angle = SAIL_ANGLE + math.tau * i / 4
                ux, uy = math.cos(angle), math.sin(angle)
                px, py = -uy * width / 2.0, ux * width / 2.0
                near = (cx + ux * size * 0.20, cy + uy * size * 0.20)
                far = (cx + ux * length, cy + uy * length)
                sail = [
                    (near[0] + px, near[1] + py), (far[0] + px, far[1] + py),
                    (far[0] - px, far[1] - py), (near[0] - px, near[1] - py),
                ]
                pygame.draw.polygon(surface, tones["sail"], sail)
                pygame.draw.polygon(surface, tones["line"], sail, line)
                # The lattice of the sail: one bar along the middle of it.
                pygame.draw.line(surface, tones["line"], near, far, line)
            pygame.draw.circle(surface, tones["line"], (cx, cy), max(2.0, size * 0.30))
            pygame.draw.circle(surface, tones["wood"], (cx, cy), max(1.5, size * 0.22))


def _wall_line(surface: pygame.Surface, rect, hexagon, building, colour, width: int, joined) -> None:
    """The sides of one block that face out of the building.

    A block draws a line on each side that faces open ground, and no line on a side that a
    block of the same building covers. So the line follows the outside of one building.
    """
    if not joined(hexagon, building, 0, -2):
        pygame.draw.line(surface, colour, (rect.left, rect.top), (rect.right, rect.top), width)
    if not joined(hexagon, building, 0, 2):
        pygame.draw.line(surface, colour, (rect.left, rect.bottom), (rect.right, rect.bottom), width)
    if not (joined(hexagon, building, -3, -1) or joined(hexagon, building, -3, 1)):
        pygame.draw.line(surface, colour, (rect.left, rect.top), (rect.left, rect.bottom), width)
    if not (joined(hexagon, building, 3, -1) or joined(hexagon, building, 3, 1)):
        pygame.draw.line(surface, colour, (rect.right, rect.top), (rect.right, rect.bottom), width)


# ------------------------------------------------------------------------- the roads


def _roads(surface: pygame.Surface, board: dict[str, Any], camera: Camera) -> None:
    """A road is a ribbon that enters a hex at one hexside and bends out at another.

    A hex with two ways out gets one curve through the middle, so a road turns instead of
    breaking at each centre. A junction gets a straight arm to each hexside and a round
    middle, so the crossing is one piece of road.
    """
    width = max(2, int(camera.scale * ROAD_WIDTH_SHARE))
    casing = width + max(2, width // 3)
    arms = road_arms(board)
    lone = [tuple(h["center"]) for h in board["hexes"] if h.get("road") and tuple(h["center"]) not in arms]
    for colour, thickness in ((theme.ROAD_EDGE, casing), (theme.ROAD, width)):
        for centre, ends in sorted(arms.items()):
            screen_centre = camera.to_screen(*centre)
            if len(ends) == 2:
                _curve(
                    surface,
                    colour,
                    camera.to_screen(*ends[0]),
                    screen_centre,
                    camera.to_screen(*ends[1]),
                    thickness,
                )
                continue
            for end in ends:
                pygame.draw.line(surface, colour, screen_centre, camera.to_screen(*end), thickness)
            pygame.draw.circle(surface, colour, screen_centre, thickness / 2.0)
        for centre in lone:
            pygame.draw.circle(surface, colour, camera.to_screen(*centre), thickness / 2.0)


def _curve(
    surface: pygame.Surface,
    colour: tuple[int, int, int],
    start: tuple[float, float],
    control: tuple[float, float],
    end: tuple[float, float],
    width: int,
) -> None:
    """One quadratic curve, drawn as short straight pieces with a round joint."""
    points = []
    for i in range(CURVE_STEPS + 1):
        t = i / CURVE_STEPS
        u = 1.0 - t
        x = u * u * start[0] + 2 * u * t * control[0] + t * t * end[0]
        y = u * u * start[1] + 2 * u * t * control[1] + t * t * end[1]
        points.append((x, y))
    for a, b in zip(points, points[1:]):
        pygame.draw.line(surface, colour, a, b, width)
    for point in points:
        pygame.draw.circle(surface, colour, point, width / 2.0)


def road_arms(board: dict[str, Any]) -> dict[tuple[int, int], list[tuple[float, float]]]:
    """The arms of road that each road hex draws, from its centre to a hexside midpoint.

    PR-50: a board document of generator version 8 names the hexsides each road crosses
    (`road_sides`). Each road hex then draws one arm to the midpoint of each named hexside,
    and no other. Two road hexes beside a crossroads touch, but no road joins them, so no
    arm goes across the corner of the junction.

    A board document that names no road hexside (a record of version 7) keeps the links of
    `_road_links`, the reading from before PR-50.
    """
    found = board.get("_road_arms")
    if found is not None:
        return found
    arms: dict[tuple[int, int], list[tuple[float, float]]] = {}
    if any(h.get("road_sides") for h in board["hexes"]):
        for h in board["hexes"]:
            if not h.get("road"):
                continue
            centre = tuple(h["center"])
            for direction in sorted(int(d) for d in h.get("road_sides", ())):
                dx, dy = STEPS[direction]
                arms.setdefault(centre, []).append((centre[0] + dx / 2.0, centre[1] + dy / 2.0))
    else:
        for pair in _road_links(board):
            first, second = sorted(pair)
            middle = ((first[0] + second[0]) / 2.0, (first[1] + second[1]) / 2.0)
            arms.setdefault(first, []).append(middle)
            arms.setdefault(second, []).append(middle)
    board["_road_arms"] = arms
    return arms


def _road_links(board: dict[str, Any]) -> list[frozenset]:
    """Which pairs of road hexes get a stroke between them.

    A road hex touches up to six other road hexes, and a stroke to each of them draws a
    junction as a ring of road around a hole of ground. The rule here is: a road that goes
    straight through a hex is drawn, and a link that turns a corner is drawn only when the
    two hexes have no way to each other through two straight links.

    A crossroads then reads as two roads that cross, which is what it is, and no stroke
    cuts the corner of the junction.
    """
    found = board.get("_road_links")
    if found is not None:
        return found
    centres = {tuple(h["center"]) for h in board["hexes"] if h.get("road")}
    straight: set[frozenset] = set()
    other: set[frozenset] = set()
    for centre in sorted(centres):
        for dx, dy in STEPS:
            near = (centre[0] + dx, centre[1] + dy)
            if near not in centres:
                continue
            back = (centre[0] - dx, centre[1] - dy)
            pair = frozenset((centre, near))
            if back in centres:
                straight.add(pair)
            else:
                other.add(pair)
    keep = set(straight)
    joined: dict[tuple, set] = {}
    for pair in keep:
        a, b = tuple(pair)
        joined.setdefault(a, set()).add(b)
        joined.setdefault(b, set()).add(a)
    for pair in sorted(other - keep, key=lambda p: sorted(p)):
        a, b = sorted(pair)
        if any(b in joined.get(step, ()) for step in joined.get(a, ())):
            continue
        keep.add(pair)
        joined.setdefault(a, set()).add(b)
        joined.setdefault(b, set()).add(a)
    links = sorted(keep, key=lambda p: sorted(p))
    board["_road_links"] = links
    return links


def _by_centre(board: dict[str, Any]) -> dict[tuple[int, int], dict[str, Any]]:
    """The hexes of the board by centre, built one time for each board document."""
    index = board.get("_centre_index")
    if index is None:
        index = {tuple(h["center"]): h for h in board["hexes"]}
        board["_centre_index"] = index
    return index


# ----------------------------------------------------------------- the hexside features


def _crest(
    surface: pygame.Surface, hexagon: dict[str, Any], camera: Camera, levels: dict[tuple[int, int], int]
) -> None:
    """Rule 43.2: a crest line goes on every hexside where two levels meet."""
    here = int(hexagon.get("elevation", 0))
    cx, cy = hexagon["center"]
    for d, (dx, dy) in enumerate(STEPS):
        other = levels.get((cx + dx, cy + dy))
        if other is None or other >= here:
            continue
        start, end = hexside_segment(hexagon["center"], d, camera)
        pygame.draw.line(surface, theme.CREST, start, end, CREST_WIDTH)


def _outline(surface: pygame.Surface, hexagon: dict[str, Any], camera: Camera) -> None:
    pygame.draw.polygon(surface, theme.GRID, hex_corners(hexagon["center"], camera), GRID_WIDTH)


def _centre_dot(surface: pygame.Surface, hexagon: dict[str, Any], camera: Camera) -> None:
    """Rule 3.5: the dot at the centre of the hex, which rule 7.1 threads a sight line to."""
    centre = camera.to_screen(*hexagon["center"])
    pygame.draw.circle(surface, theme.CENTRE_DOT, centre, max(1.0, camera.scale * 0.09))


def _hexsides(
    surface: pygame.Surface, hexagon: dict[str, Any], camera: Camera, levels: dict[tuple[int, int], int]
) -> None:
    """Rule 11.5: a wall, a hedge, or a cliff lies on one hexside and not in a hex.

    Each of the three has height. The body sits on the hexside, a lit band sits above it,
    and a shadow band sits below it. The light comes from the top of the screen, so both
    hexes of a hexside draw the same picture.
    """
    for key, feature in hexagon.get("hexsides", {}).items():
        if feature not in theme.HEXSIDE:
            continue
        direction = int(key)
        start, end = hexside_segment(hexagon["center"], direction, camera)
        if feature == "hedge":
            _hedge(surface, start, end, camera)
        elif feature == "cliff":
            _cliff(surface, hexagon, direction, start, end, camera, levels)
        else:
            _wall(surface, start, end, camera)


def _band(
    surface: pygame.Surface,
    start: tuple[float, float],
    end: tuple[float, float],
    lift: float,
    colour: tuple[int, int, int],
    width: int,
) -> None:
    """One flat band along a hexside, moved up the screen by `lift` pixels."""
    pygame.draw.line(surface, colour, (start[0], start[1] - lift), (end[0], end[1] - lift), width)


def _wall(surface: pygame.Surface, start, end, camera: Camera) -> None:
    """Rule 11.51: a stone wall. Three bands give it the height that stops a line of sight."""
    height = max(1.0, camera.scale * 0.18)
    body = max(3, int(camera.scale * 0.26))
    _band(surface, start, end, -height, theme.HEXSIDE_SHADOW["wall"], body)
    _band(surface, start, end, 0.0, theme.HEXSIDE["wall"], body)
    _band(surface, start, end, height, theme.HEXSIDE_TOP["wall"], max(2, int(body * 0.7)))


def _hedge(surface: pygame.Surface, start, end, camera: Camera) -> None:
    """Rule 11.5: a hedge. The top is a row of crowns, so it is not a wall at a glance."""
    height = max(1.0, camera.scale * 0.16)
    body = max(3, int(camera.scale * 0.24))
    _band(surface, start, end, -height, theme.HEXSIDE_SHADOW["hedge"], body)
    _band(surface, start, end, 0.0, theme.HEXSIDE["hedge"], body)
    leaves = max(3, int(camera.scale * 0.26))
    count = max(3, int(camera.scale // 3))
    for i in range(count + 1):
        share = i / count
        x = start[0] + (end[0] - start[0]) * share
        y = start[1] + (end[1] - start[1]) * share - height
        pygame.draw.circle(surface, theme.HEXSIDE_TOP["hedge"], (x, y), leaves / 2)


def _cliff(
    surface: pygame.Surface,
    hexagon: dict[str, Any],
    direction: int,
    start,
    end,
    camera: Camera,
    levels: dict[tuple[int, int], int],
) -> None:
    """Rule 44.1: a cliff. The ticks point down the face, so the low side is clear."""
    body = max(2, int(camera.scale * 0.26))
    _band(surface, start, end, 0.0, theme.HEXSIDE["cliff"], body)
    _band(surface, start, end, max(1.0, camera.scale * 0.14), theme.HEXSIDE_TOP["cliff"], max(1, body // 3))
    here = int(hexagon.get("elevation", 0))
    dx, dy = STEPS[direction]
    cx, cy = hexagon["center"]
    below = levels.get((cx + dx, cy + dy))
    if below is None or below >= here:
        return
    towards = camera.to_screen(cx + dx, cy + dy)
    length = max(2.0, camera.scale * 0.22)
    count = 3
    for i in range(1, count + 1):
        share = i / (count + 1)
        x = start[0] + (end[0] - start[0]) * share
        y = start[1] + (end[1] - start[1]) * share
        ux, uy = towards[0] - x, towards[1] - y
        size = math.hypot(ux, uy) or 1.0
        pygame.draw.line(
            surface,
            theme.HEXSIDE_SHADOW["cliff"],
            (x, y),
            (x + ux / size * length, y + uy / size * length),
            max(1, body // 3),
        )


def _label(surface: pygame.Surface, hexagon: dict[str, Any], camera: Camera, font: pygame.font.Font) -> None:
    cx, cy = camera.to_screen(*hexagon["center"])
    text = font.render(hexagon["id"], True, theme.LABEL)
    surface.blit(text, (cx - text.get_width() / 2, cy - camera.scale * 1.30))
