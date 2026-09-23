"""The counters of the desktop window, drawn from the view document.

A counter carries what the 1977 counter carries. A squad shows two men and its firepower,
range, and morale in one line (rules 2.2 to 2.4). A leader shows one man, his name up the
side, and his morale with his leadership modifier up the edge (rules 2.5, 2.6). A support
weapon shows its icon and three lines: the weapon, its firepower and range, and its
breakdown number (rules 2.7 to 2.9). A vehicle shows its plan from above, turned to its
facing, with the movement points top right, the gun bottom left, and the machine guns
bottom right (rule 28). The reverse of a squad or a leader says that it is broken and gives
its broken morale, with its men down (rule 12). The reverse of a weapon has a white cross
over its icon and its repair number (rule 18).

The layout follows the study of the owner's photographs of the 1977 pieces,
`docs/research/2026-09-17_RV-10_counter_study.md`. The silhouettes are the project's own
point lists in `slwindow.silhouettes`. No scan and no printed layout is in the tree (SR-07).
"""

from __future__ import annotations

import math
from typing import Any, Sequence

import pygame

from slwindow import silhouettes, theme
from slwindow.layout import ROOT_THREE, Camera
from slwindow.overlay import position_of

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
# A vehicle counter is five eighths of an inch and an infantry counter is one half (RV-1
# section 8), so a vehicle chit is this much wider than a squad chit.
VEHICLE_SCALE = 1.25
# The armies whose men walk to the right on the 1977 sheets. The figures face left, and the
# renderer mirrors them for these armies (RV-10 section 2).
FACES_RIGHT = frozenset({"russian"})

# The layout of a face, as fractions of the printed face. `client/src/counters/draw.ts`
# holds the same table, and `tests/browser/test_render_constants.py` compares the two, so
# the browser and the window print one counter and not two (RV-10 section 3).
LAYOUT: dict[str, float] = {
    # a squad: two men side by side over one line of numbers
    "squad_figure_top": 0.06,
    "squad_figure_height": 0.50,
    "squad_figure_width": 0.30,
    "squad_first_left": 0.16,
    "squad_second_left": 0.52,
    "crew_shrink": 0.82,
    "squad_text_top": 0.60,
    "squad_text_px": 0.32,
    "squad_text_left": 0.07,
    # a leader: one man at the left, the name and the value up the right side
    "leader_figure_left": 0.06,
    "leader_figure_top": 0.10,
    "leader_figure_width": 0.34,
    "leader_figure_height": 0.80,
    "leader_name_x": 0.53,
    "leader_name_px": 0.15,
    "leader_value_x": 0.78,
    "leader_value_px": 0.36,
    # a support weapon: the icon at the left, three lines at the right
    "weapon_icon_left": 0.05,
    "weapon_icon_top": 0.18,
    "weapon_icon_width": 0.36,
    "weapon_icon_height": 0.64,
    "weapon_text_left": 0.44,
    "weapon_name_top": 0.08,
    "weapon_name_px": 0.21,
    "weapon_value_top": 0.36,
    "weapon_value_px": 0.26,
    "weapon_break_top": 0.66,
    "weapon_break_px": 0.21,
    # the reverse of a squad or a leader: the word, the number, the men down
    "back_word_px": 0.24,
    "back_word_top": 0.06,
    "back_number_px": 0.34,
    "back_number_top": 0.30,
    "back_figures_top": 0.56,
    "back_figures_height": 0.38,
    # a vehicle: the plan in the middle, the numbers in the corners
    "vehicle_plan_size": 0.58,
    "vehicle_corner_px": 0.24,
    "vehicle_small_px": 0.17,
    "vehicle_inset": 0.05,
    # the white cross on a broken weapon and the marker tab
    "cross_width": 0.16,
    "tab_size": 0.36,
}

# The face font: a bold condensed sans, the family of the 1977 print. The list gives
# pygame a machine font to find, and the project supplies no font file.
FACE_FONT = "arialnarrow,dejavusanscondensed,liberationsansnarrow,arial,dejavusans"


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
        # Rule 16.1: a unit that the defender returned to its track stays at its end hex on
        # the screen, and the overlay puts a ghost on the track hex (`slwindow.overlay`).
        here = position_of(unit)
        if here is None or unit["carrier"] is not None:
            continue
        stacks.setdefault(here, []).append(unit)
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
    inset = size * 0.09
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
            radius = max(1, int(size * (0.025 + 0.01 * (bits % 3))))
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

    The reverse of a 1977 counter is the same stock as its front, so `flipped` keeps the
    base tone and the caller prints the reverse on it. A chit too small for any print takes
    a darker tone when it is flipped, so the state is still visible at a distance. The light
    is at the top of the screen (theme), so the top and the left of the face take a highlight
    and the bottom and the right take a shade. The returned rectangle is the printed face.

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
    face_base = _darken(base, theme.BACK_SHADE) if flipped and size < SYMBOL_MIN else base
    pygame.draw.rect(surface, face_base, face, border_radius=face_radius)
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


def _stock(unit: dict[str, Any]) -> tuple[int, int, int]:
    """The stock a counter is printed on: red for a berserk squad, else the army's colour.

    A support weapon is on the stock of its army too, which is what the sheets show (RV-10
    section 2), so a weapon and the squad that carries it are one colour.
    """
    if unit.get("berserk"):
        return theme.BERSERK
    return theme.NATIONAL.get(unit["nationality"], theme.NATIONAL["german"])


def _body(surface: pygame.Surface, unit: dict[str, Any], x: float, y: float, size: float, shadow: bool = True) -> pygame.Rect:
    return _chit(surface, x, y, size, _stock(unit), unit["id"], flipped=bool(unit["broken"]), nationality=unit["nationality"], shadow=shadow)


# ------------------------------------------------------------------------- the print

_FONTS: dict[tuple[int, bool], pygame.font.Font] = {}
_FONTS_CLEAR_ON_QUIT = False


def _face_font(px: float, bold: bool = True) -> pygame.font.Font:
    """The face font at one pixel size, cached, because a frame prints many numbers.

    A font of the library dies with `pygame.quit()`, and a process that opens the library
    again (a test suite, the 3D window after the 2D one) must not print with a dead one.
    So the cache empties itself on each quit.
    """
    global _FONTS_CLEAR_ON_QUIT
    key = (max(6, int(px)), bold)
    font = _FONTS.get(key)
    if font is None:
        if not pygame.font.get_init():
            pygame.font.init()
        if not _FONTS_CLEAR_ON_QUIT:
            pygame.register_quit(_FONTS.clear)
            _FONTS_CLEAR_ON_QUIT = True
        font = pygame.font.SysFont(FACE_FONT, key[0], bold=bold)
        _FONTS[key] = font
    return font


def _render(text: str, px: float, colour: tuple[int, int, int], max_width: float | None = None, bold: bool = True) -> pygame.Surface:
    """Render one line, and shrink it until it fits `max_width`, as a printer would."""
    size = max(6, int(px))
    label = _face_font(size, bold).render(text, True, colour)
    while max_width is not None and label.get_width() > max_width and size > 6:
        size -= 1
        label = _face_font(size, bold).render(text, True, colour)
    return label


def _print(
    surface: pygame.Surface,
    text: str,
    px: float,
    colour: tuple[int, int, int],
    *,
    left: float | None = None,
    right: float | None = None,
    centerx: float | None = None,
    top: float | None = None,
    bottom: float | None = None,
    centery: float | None = None,
    max_width: float | None = None,
    bold: bool = True,
) -> pygame.Rect:
    label = _render(text, px, colour, max_width, bold)
    rect = label.get_rect()
    if left is not None:
        rect.left = int(left)
    if right is not None:
        rect.right = int(right)
    if centerx is not None:
        rect.centerx = int(centerx)
    if top is not None:
        rect.top = int(top)
    if bottom is not None:
        rect.bottom = int(bottom)
    if centery is not None:
        rect.centery = int(centery)
    surface.blit(label, rect)
    return rect


def _print_up(surface: pygame.Surface, text: str, px: float, colour: tuple[int, int, int], centerx: float, centery: float, max_height: float | None = None, bold: bool = True) -> pygame.Rect:
    """Print a line that reads from the bottom up, the way a leader's name and value do."""
    label = _render(text, px, colour, max_height, bold)
    label = pygame.transform.rotate(label, 90)
    rect = label.get_rect(center=(int(centerx), int(centery)))
    surface.blit(label, rect)
    return rect


def _fill(surface: pygame.Surface, parts: silhouettes.Silhouette, box: tuple[float, float, float, float], colour: tuple[int, int, int], mirror: bool = False) -> None:
    """Fill the parts of one silhouette, scaled to `box` (left, top, width, height)."""
    left, top, width, height = box
    for kind, data in parts:
        if kind == "poly":
            points = silhouettes.transform(data, left, top, width, height, mirror)  # type: ignore[arg-type]
            if len(points) >= 3:
                pygame.draw.polygon(surface, colour, points)
        else:
            cx, cy, r = data  # type: ignore[misc]
            if mirror:
                cx = 1.0 - cx
            pygame.draw.circle(surface, colour, (left + cx * width, top + cy * height), max(1.0, r * min(width, height)))


# ------------------------------------------------------------------------- the faces


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
    """One infantry counter, front or reverse, with its state tabs.

    The front is the squad, the leader, or the weapon face. A broken squad or leader shows
    its reverse (rule 12), and a weapon with a malfunction shows its reverse (rule 18.1).
    `font` and `small` are the window's fonts; the face prints with `FACE_FONT` at sizes
    from the counter, so a large counter prints large and a small one stays legible.
    """
    face = _body(surface, unit, x, y, size, shadow=shadow)
    if size < SYMBOL_MIN:
        return
    kind = unit["kind"]
    if kind == "sw":
        _weapon_face(surface, unit, face)
    elif unit["broken"]:
        _broken_face(surface, unit, face)
    elif kind == "leader":
        _leader_face(surface, unit, face)
    else:
        _squad_face(surface, unit, face)
    _tabs(surface, unit, face)


def _squad_face(surface: pygame.Surface, unit: dict[str, Any], face: pygame.Rect) -> None:
    """Two men over one line: firepower, range, morale (rules 2.2 to 2.4).

    A line squad walks, an elite squad runs with its submachine guns, and a crew is two
    smaller men at a run. The men of the Russian army walk to the right (RV-10 section 2).
    """
    s = face.width
    kind = unit["kind"]
    figure = silhouettes.FIGURES[silhouettes.figure_for(kind, bool(unit.get("elite")))]
    shrink = LAYOUT["crew_shrink"] if kind == "crew" else 1.0
    width = s * LAYOUT["squad_figure_width"] * shrink
    height = s * LAYOUT["squad_figure_height"] * shrink
    top = face.top + s * LAYOUT["squad_figure_top"] + (s * LAYOUT["squad_figure_height"] - height)
    mirror = unit["nationality"] in FACES_RIGHT
    for key in ("squad_first_left", "squad_second_left"):
        left = face.left + s * LAYOUT[key] + (s * LAYOUT["squad_figure_width"] - width) / 2
        _fill(surface, figure, (left, top, width, height), theme.INK, mirror)
    text = f"{unit['firepower']}-{unit['range']}-{unit['morale']}"
    _print(surface, text, s * LAYOUT["squad_text_px"], theme.INK, left=face.left + s * LAYOUT["squad_text_left"], top=face.top + s * LAYOUT["squad_text_top"], max_width=s * 0.90)


def _leader_face(surface: pygame.Surface, unit: dict[str, Any], face: pygame.Rect) -> None:
    """One man, his name up the side, his morale and leadership up the edge (rules 2.5, 2.6)."""
    s = face.width
    box = (
        face.left + s * LAYOUT["leader_figure_left"],
        face.top + s * LAYOUT["leader_figure_top"],
        s * LAYOUT["leader_figure_width"],
        s * LAYOUT["leader_figure_height"],
    )
    _fill(surface, silhouettes.LEADER_STAND, box, theme.INK, unit["nationality"] in FACES_RIGHT)
    name = str(unit.get("name") or "").strip()
    if name and s >= 28:
        _print_up(surface, name, s * LAYOUT["leader_name_px"], theme.INK, face.left + s * LAYOUT["leader_name_x"], face.centery, max_height=s * 0.86)
    # A leader with no modifier prints as 8-0, the way the 1977 counter prints him.
    sign = "+" if unit["leadership"] > 0 else "-"
    value = f"{unit['morale']}{sign}{abs(unit['leadership'])}"
    _print_up(surface, value, s * LAYOUT["leader_value_px"], theme.INK, face.left + s * LAYOUT["leader_value_x"], face.centery, max_height=s * 0.92)


def _weapon_face(surface: pygame.Surface, unit: dict[str, Any], face: pygame.Rect) -> None:
    """The icon at the left and three lines at the right: the weapon, its firepower and range,
    and its breakdown number (rules 2.7 to 2.9). A malfunction turns the counter over: the
    icon under a white cross, with the repair roll and the loss roll of rule 18 (RV-10
    section 4)."""
    s = face.width
    icon = silhouettes.ICONS[silhouettes.icon_for(str(unit.get("type", "")), str(unit.get("weapon_class", "")))]
    box = (
        face.left + s * LAYOUT["weapon_icon_left"],
        face.top + s * LAYOUT["weapon_icon_top"],
        s * LAYOUT["weapon_icon_width"],
        s * LAYOUT["weapon_icon_height"],
    )
    _fill(surface, icon, box, theme.INK)
    left = face.left + s * LAYOUT["weapon_text_left"]
    width = face.right - left - s * 0.04
    if unit.get("malfunction"):
        _cross(surface, face)
        _print(surface, "R1", s * LAYOUT["weapon_value_px"], theme.INK, left=left, top=face.top + s * LAYOUT["weapon_name_top"], max_width=width)
        _print(surface, "X6", s * LAYOUT["weapon_value_px"], theme.INK, left=left, top=face.top + s * LAYOUT["weapon_break_top"], max_width=width)
        return
    _print(surface, str(unit.get("type", ""))[:4], s * LAYOUT["weapon_name_px"], theme.INK, left=left, top=face.top + s * LAYOUT["weapon_name_top"], max_width=width)
    fp = int(unit.get("firepower", 0) or 0)
    rng = int(unit.get("range", 0) or 0)
    value = f"{fp}-{rng}" if fp and rng else (str(rng) if rng else "")
    if value:
        _print(surface, value, s * LAYOUT["weapon_value_px"], theme.INK, left=left, top=face.top + s * LAYOUT["weapon_value_top"], max_width=width)
    breakdown = int(unit.get("breakdown", 0) or 0)
    if breakdown:
        # A flamethrower's number is the roll that takes it out of the game (rule 22.6), so
        # it prints with an X and not a B.
        letter = "X" if str(unit.get("weapon_class", "")) == "flamethrower" else "B"
        _print(surface, f"{letter}{breakdown}", s * LAYOUT["weapon_break_px"], theme.INK, left=left, top=face.top + s * LAYOUT["weapon_break_top"], max_width=width)


def _cross(surface: pygame.Surface, face: pygame.Rect) -> None:
    """The white cross of a weapon reverse: two bands from corner to corner."""
    width = face.width * LAYOUT["cross_width"]
    layer = pygame.Surface(face.size, pygame.SRCALPHA)
    w, h = face.size
    pygame.draw.line(layer, (*theme.MARKER, 230), (0, 0), (w, h), max(2, int(width)))
    pygame.draw.line(layer, (*theme.MARKER, 230), (w, 0), (0, h), max(2, int(width)))
    surface.blit(layer, face.topleft)


def _broken_face(surface: pygame.Surface, unit: dict[str, Any], face: pygame.Rect) -> None:
    """The reverse of a squad or a leader: the word, the broken morale, and the men down.

    Rule 12 turns a broken unit over. The reverse gives the morale a rally uses (rule 14.1),
    and it shows a man on his front with his rifle forward. A squad shows a second man on
    one knee. The word is the project's own and not the printed one.
    """
    s = face.width
    _print(surface, "Broken", s * LAYOUT["back_word_px"], theme.INK, left=face.left + s * 0.07, top=face.top + s * LAYOUT["back_word_top"], max_width=s * 0.86)
    number = _print(surface, str(unit["morale"]), s * LAYOUT["back_number_px"], theme.INK, left=face.left + s * 0.07, top=face.top + s * LAYOUT["back_number_top"])
    mirror = unit["nationality"] in FACES_RIGHT
    top = face.top + s * LAYOUT["back_figures_top"]
    height = s * LAYOUT["back_figures_height"]
    if unit["kind"] == "leader":
        _fill(surface, silhouettes.PRONE_RIFLEMAN, (face.left + s * 0.10, top, s * 0.80, height), theme.INK, mirror)
        return
    _fill(surface, silhouettes.KNEELING_MAN, (number.right + s * 0.04, face.top + s * 0.26, s * 0.30, s * 0.34), theme.INK, mirror)
    _fill(surface, silhouettes.PRONE_RIFLEMAN, (face.left + s * 0.10, top, s * 0.80, height), theme.INK, mirror)


def _tabs(surface: pygame.Surface, unit: dict[str, Any], face: pygame.Rect) -> None:
    """The state of a unit as small white tabs at the top right, the markers of the game.

    The 1977 game puts a white marker on a unit that has fired in the Prep Fire Phase, and
    a DM marker on a broken unit under desperation morale. The window puts a small tab of
    the marker stock on the counter for each, and a tab for a unit that moved (rule 16) and
    one for a passenger (rule 31), so the state reads without a second counter.
    """
    tabs: list[tuple[str, tuple[int, int, int]]] = []
    if unit.get("prep_fired"):
        tabs.append(("PF", theme.MARKER_RED))
    if unit.get("moved"):
        tabs.append(("M", theme.INK))
    if unit.get("dm"):
        tabs.append(("DM", theme.INK))
    if unit.get("riding") is not None:
        tabs.append(("R", theme.INK))
    if not tabs or face.width < 24:
        return
    size = face.width * LAYOUT["tab_size"]
    x = face.right - size
    y = face.top
    for text, colour in tabs[:3]:
        tab = pygame.Rect(int(x), int(y), int(size), int(size * 0.62))
        pygame.draw.rect(surface, theme.MARKER, tab)
        pygame.draw.rect(surface, theme.INK, tab, 1)
        _print(surface, text, size * 0.52, colour, centerx=tab.centerx, centery=tab.centery, max_width=size * 0.9)
        y += tab.height + 1


# ---------------------------------------------------------------------- the vehicles


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
    """Rule 28: the plan of the vehicle turned to its facing, and its numbers in the corners.

    A closed vehicle prints as a dark plan and an open top one as a light plan, and a
    turret carries a white band, all as rule 28 describes the counter. The plan turns to
    the facing of the unit, so the barrel lies along the spine of the covered arc (rule
    29.4). A wreck shows the white reverse with the wreck and its survival number (rule 33.9).
    """
    width = size * VEHICLE_SCALE
    if unit["wreck"]:
        face = _chit(surface, x, y, width, theme.MARKER, unit["id"], outline=theme.VEHICLE_EDGE, edge_width=2, shadow=shadow)
        if width >= SYMBOL_MIN:
            _wreck_face(surface, unit, face)
        return
    face = _chit(surface, x, y, width, _stock(unit), unit["id"], outline=theme.VEHICLE_EDGE, edge_width=2, shadow=shadow)
    if width < SYMBOL_MIN:
        return
    s = face.width
    plan = silhouettes.PLANS.get(str(unit.get("vehicle_class", "")), silhouettes.TANK_PLAN)
    facing = int(unit.get("facing", -1))
    _plan(surface, plan, face.center, s * LAYOUT["vehicle_plan_size"], facing, bool(unit.get("open_top")))
    if unit["immobilized"]:
        pygame.draw.rect(surface, theme.IMMOBILE, face, 3)
    if unit["crew_exposed"]:
        pygame.draw.circle(surface, theme.CREW_EXPOSED, (face.centerx, face.top + 3), 3)
    if s < 24:
        return
    inset = s * LAYOUT["vehicle_inset"]
    corner = s * LAYOUT["vehicle_corner_px"]
    small_px = s * LAYOUT["vehicle_small_px"]
    _print(surface, str(unit.get("movement_points", 0)), corner, theme.INK, right=face.right - inset, top=face.top + inset * 0.6)
    if unit.get("gun_low_velocity"):
        _print(surface, "*", corner, theme.INK, left=face.left + inset, top=face.top + inset * 0.6)
    gun = int(unit.get("gun", 0) or 0)
    transport = int(unit.get("transport_pp", 0) or 0)
    if gun:
        rect = _print(surface, str(gun), corner, theme.INK, left=face.left + inset, bottom=face.bottom - inset * 0.4)
        if unit.get("gun_he_only"):
            # The bar over the calibre marks a gun that fires high explosive only (rule 28.2).
            pygame.draw.line(surface, theme.INK, (rect.left, rect.top), (rect.right, rect.top), max(1, int(s * 0.03)))
    elif transport:
        _print(surface, f"P{transport}", corner, theme.MARKER, left=face.left + inset, bottom=face.bottom - inset * 0.4)
    mg_ca = int(unit.get("mg_ca", 0) or 0)
    mg_360 = int(unit.get("mg_360", 0) or 0)
    if mg_ca or mg_360:
        mgs = f"{mg_ca or '-'}/{mg_360 or '-'}"
        _print(surface, mgs, small_px, theme.INK, right=face.right - inset, bottom=face.bottom - inset * 0.4)
    if s >= 40:
        # The name sits in the band over the plan, between the asterisk and the movement
        # points, where it does not cross the ink of the plan.
        name = str(unit.get("type", ""))
        _print(surface, name, small_px * 0.85, theme.INK, centerx=face.left + s * 0.42, top=face.top + inset * 0.5, max_width=s * 0.46, bold=False)
    if unit["malfunction"]:
        _print(surface, "X", corner, theme.BROKEN, centerx=face.centerx, top=face.top + inset)


def _plan(surface: pygame.Surface, plan: dict[str, silhouettes.Silhouette], centre: tuple[int, int], size: float, facing: int, open_top: bool) -> None:
    """The plan from above, turned so its front points along the facing spine.

    The parts draw in the unit box and then turn about its centre. A closed vehicle is the
    ink with a light band round its turret; an open top vehicle is the light stock with an
    ink line round it (rule 28).
    """
    angle = _spine_angle(facing)
    body = theme.OPEN_TOP if open_top else theme.INK
    line = theme.INK if open_top else theme.TURRET_BAND
    for key in ("tracks", "wheels", "hull", "casemate", "cab"):
        for part in plan.get(key, []):
            _turned_part(surface, part, centre, size, angle, body, line if open_top or key in ("casemate", "cab") else None)
    for part in plan.get("barrel", []):
        _turned_part(surface, part, centre, size, angle, theme.INK, None)
    for part in plan.get("turret", []):
        _turned_part(surface, part, centre, size, angle, body, line, band=True)


def _turned_part(surface: pygame.Surface, part: silhouettes.Part, centre: tuple[int, int], size: float, angle: float, fill: tuple[int, int, int], line: tuple[int, int, int] | None, band: bool = False) -> None:
    kind, data = part
    cos, sin = math.cos(angle), math.sin(angle)

    def turn(px: float, py: float) -> tuple[float, float]:
        dx, dy = (px - 0.5) * size, (py - 0.5) * size
        return (centre[0] + dx * cos - dy * sin, centre[1] + dx * sin + dy * cos)

    if kind == "poly":
        points = [turn(px, py) for px, py in data]  # type: ignore[union-attr]
        pygame.draw.polygon(surface, fill, points)
        if line is not None:
            pygame.draw.polygon(surface, line, points, max(1, int(size * 0.035)))
        return
    cx, cy, r = data  # type: ignore[misc]
    x, y = turn(cx, cy)
    radius = max(1.0, r * size)
    pygame.draw.circle(surface, fill, (x, y), radius)
    if line is not None:
        pygame.draw.circle(surface, line, (x, y), radius, max(1, int(size * (0.06 if band else 0.035))))


def _wreck_face(surface: pygame.Surface, unit: dict[str, Any], face: pygame.Rect) -> None:
    """The white reverse of a vehicle: the word, the burnt out plan, the survival number."""
    s = face.width
    _print(surface, "WRECK", s * LAYOUT["vehicle_corner_px"] * 0.9, theme.INK, centerx=face.centerx, top=face.top + s * 0.05, max_width=s * 0.9)
    centre = (face.centerx, int(face.top + s * 0.58))
    for key in ("tracks", "hull", "turret"):
        for part in silhouettes.WRECK_PLAN.get(key, []):
            _turned_part(surface, part, centre, s * 0.52, math.radians(35), theme.WRECK, None)
    for part in silhouettes.WRECK_PLAN["smoke"]:
        _turned_part(surface, part, centre, s * 0.52, math.radians(35), theme.INK, None)
    survival = int(unit.get("survival", 0) or 0)
    if survival and s >= 24:
        _print(surface, f"S{survival}", s * LAYOUT["vehicle_small_px"], theme.INK, right=face.right - s * 0.06, bottom=face.bottom - s * 0.04)


def _spine_angle(facing: int) -> float:
    """The turn, in radians, that points the top of the unit box along one spine.

    A facing below zero (a vehicle with no facing yet) points the plan up the screen.
    """
    if facing < 0:
        return 0.0
    dx, dy = _spine_direction(facing)
    return math.atan2(dy, dx) + math.pi / 2


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
    """Rule 25: the token stands for a stack, and the other side does not see what is below.

    The 1977 counter is a question mark on the stock of its army (RV-10 section 5). The
    token names its army when the host sends one, and it takes the plain stock otherwise.
    """
    for token in view.get("concealment", []):
        centre = centres.get(token["hex"])
        if centre is None:
            continue
        cx, cy = camera.to_screen(*centre)
        seed = _str_seed(str(token["hex"])) ^ (1 if token.get("own") else 0)
        army = _token_army(view, token)
        stock = theme.NATIONAL.get(army, theme.CONCEALED) if army else theme.CONCEALED
        face = _chit(surface, cx, cy, size * 0.7, stock, seed, edge_width=1)
        if face.width >= SYMBOL_MIN:
            _print(surface, "?", face.width * 0.70, theme.INK, centerx=face.centerx, centery=face.centery)


def _token_army(view: dict[str, Any], token: dict[str, Any]) -> str | None:
    """The army of a concealment token: the viewer's own, or the other side's.

    A token of the other side carries no player (rule 25.2, AR-09), and the other side is
    the player that is not the viewer. The view names the army of each player.
    """
    nationalities = view.get("nationalities")
    if not isinstance(nationalities, dict) or not nationalities:
        return None
    viewer = str(view.get("viewer", ""))
    if token.get("own"):
        return nationalities.get(str(token.get("player", viewer)), nationalities.get(viewer))
    others = [army for player, army in nationalities.items() if player != viewer]
    return others[0] if others else None
