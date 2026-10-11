"""Render one scenario to a printable card image.

The layout evokes the 1977 scenario card: a large serif title at the top, a red scenario
number at the upper left, a situation block, the rules introduced, a small board diagram
with a north arrow, a numbered turn record chart with two side labels, one order of battle
block per side with a side emblem and the units as mini-counters grouped by their set up
area, the victory conditions, and the special rules. Only the arrangement is from the study
of the original; every word comes from the scenario JSON and every shape is the project's
own drawing (SR-07, DR-01).

The mini-counters come from `slwindow.counters`, the same code the desktop window runs, so
a counter on the card and a counter in the game are the same drawing. This module builds a
minimal unit dict from each unit type string to feed that renderer. It draws nothing of a
counter itself.

The renderer runs offscreen: it sets the dummy SDL video driver before it imports pygame,
the same way `tools/make_docs_images.py` does, so it needs no display.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame  # noqa: E402

from slcore.scenario import band_text  # noqa: E402
from slwindow import theme  # noqa: E402
from slwindow.counters import _counter  # noqa: E402

# Print proportions near US Letter (8.5 by 11), portrait.
CARD_WIDTH = 1000
CARD_HEIGHT = 1294
MARGIN = 48
COUNTER = 46  # the mini-counter size on the card; large enough for the numbers to read

_SW_NAMES = {"LMG", "MMG", "HMG", "FT", "DC", "PF", "ATR", "MTR"}


def _fonts() -> dict[str, pygame.font.Font]:
    """The card fonts: a serif for the titles and headings, a sans for the body.

    The project ships no font file (SR-07), so it asks the system for a serif and a sans and
    it names a fallback. A machine with neither falls back to the pygame default font.
    """
    serif = "timesnewroman,dejavuserif,liberationserif,georgia,serif"
    sans = "dejavusans,arial,helvetica,liberationsans,sans"
    return {
        "title": pygame.font.SysFont(serif, 46, bold=True),
        "scenario": pygame.font.SysFont(sans, 26, bold=True),
        "heading": pygame.font.SysFont(serif, 22, bold=True),
        "subheading": pygame.font.SysFont(sans, 15, bold=True),
        "cell": pygame.font.SysFont(sans, 13, bold=True),
        "body": pygame.font.SysFont(sans, 15),
        "small": pygame.font.SysFont(sans, 12),
        "count": pygame.font.SysFont(sans, 18, bold=True),
        "chit": pygame.font.SysFont("dejavusansmono,consolas,couriernew", 12, bold=True),
    }


def _unit_dict(type_str: str, name: str | None, index: int) -> dict[str, Any]:
    """A minimal unit dict for `slwindow.counters._counter`.

    The counter renderer reads a small set of fields. This function fills them from the type
    string and leaves every marker off, because a card shows a unit at set up and not in play.
    A squad type is firepower, range, and morale. A leader type is morale and a signed
    leadership. A support weapon and a vehicle keep their name and draw as a weapon chit.
    """
    base = {
        "id": index,
        "nationality": "german",
        "broken": False,
        "prep_fired": False,
        "moved": False,
        "malfunction": False,
        "riding": None,
    }
    text = type_str.strip()
    if _is_leader(text):
        morale, leadership = _parse_leader(text)
        base.update(kind="leader", morale=morale, leadership=leadership)
        return base
    if _is_squad(text):
        fp, rng, morale = (int(p) for p in text.split("-"))
        base.update(kind="squad", firepower=fp, range=rng, morale=morale)
        return base
    # A support weapon or a vehicle: draw a weapon chit and print its name.
    base.update(kind="sw", type=text)
    return base


def _is_leader(text: str) -> bool:
    """A leader type is two integers joined by a plus or a minus, e.g. 9-1 or 8-0 or 10-2."""
    if text.startswith("-"):
        return False
    for sign in ("+", "-"):
        if sign in text[1:]:
            head, tail = text[1:].split(sign, 1)
            return (text[0] + head).lstrip("-").isdigit() and tail.isdigit() and "-" not in tail
    return False


def _parse_leader(text: str) -> tuple[int, int]:
    for sign in ("+", "-"):
        if sign in text[1:]:
            head, tail = text[1:].split(sign, 1)
            morale = int(text[0] + head)
            leadership = int(tail) if sign == "+" else -int(tail)
            return morale, leadership
    raise ValueError(f"{text!r} is not a leader type")


def _is_squad(text: str) -> bool:
    """A squad type is three integers joined by minus, e.g. 4-6-7 or 6-2-8."""
    parts = text.split("-")
    return len(parts) == 3 and all(p.isdigit() for p in parts)


def _side_colour(side: dict[str, Any]) -> tuple[int, int, int]:
    return theme.NATIONAL.get(side.get("nationality", "german"), theme.NATIONAL["german"])


def _emblem(surface: pygame.Surface, side: dict[str, Any], cx: int, cy: int, radius: int) -> None:
    """The side emblem, a simple project shape and not Avalon Hill art.

    A German side takes a plain cross, a Russian or Soviet side takes a five point star, and
    an American side takes a star inside a roundel. Each is drawn from a few points, so no
    printed emblem is copied (SR-07, DR-01).
    """
    nationality = side.get("nationality", "german")
    ink = theme.CARD_INK
    if nationality == "german":
        arm = radius
        thick = max(3, radius // 3)
        pygame.draw.rect(surface, ink, pygame.Rect(cx - thick // 2, cy - arm, thick, arm * 2))
        pygame.draw.rect(surface, ink, pygame.Rect(cx - arm, cy - thick // 2, arm * 2, thick))
    elif nationality == "american":
        pygame.draw.circle(surface, ink, (cx, cy), radius, 3)
        _star(surface, cx, cy, int(radius * 0.7), theme.CARD_RED, ink)
    else:  # russian and any other side draw a red star
        _star(surface, cx, cy, radius, theme.CARD_RED, ink)


def _star(surface: pygame.Surface, cx: int, cy: int, radius: int, fill: tuple[int, int, int], line: tuple[int, int, int]) -> None:
    """A five point star from ten points, the project's own shape."""
    import math

    points = []
    for i in range(10):
        angle = -math.pi / 2 + i * math.pi / 5
        r = radius if i % 2 == 0 else radius * 0.42
        points.append((cx + r * math.cos(angle), cy + r * math.sin(angle)))
    pygame.draw.polygon(surface, fill, points)
    pygame.draw.polygon(surface, line, points, 2)


def _wrap(text: str, font: pygame.font.Font, width: int) -> list[str]:
    """Wrap one paragraph to a pixel width, greedy by word."""
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split()
        if not words:
            lines.append("")
            continue
        line = words[0]
        for word in words[1:]:
            if font.size(line + " " + word)[0] <= width:
                line += " " + word
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def _blit_paragraph(surface: pygame.Surface, text: str, font: pygame.font.Font, x: int, y: int, width: int, colour: tuple[int, int, int], line_gap: int = 4) -> int:
    for line in _wrap(text, font, width):
        label = font.render(line, True, colour)
        surface.blit(label, (x, y))
        y += font.get_height() + line_gap
    return y


def _rule(surface: pygame.Surface, x: int, y: int, width: int) -> None:
    pygame.draw.line(surface, theme.CARD_RULE, (x, y), (x + width, y), 1)


def _board_diagram(surface: pygame.Surface, scenario: dict[str, Any], fonts: dict[str, pygame.font.Font], x: int, y: int, width: int) -> int:
    """The board configuration: a small rectangle shaded on the played band, with a north arrow.

    `board_columns` names a band of columns, so the diagram shades that fraction of the
    rectangle. When the scenario has no band, the whole board is played and the whole
    rectangle is shaded.
    """
    heading = fonts["heading"].render("Board Configuration", True, theme.CARD_INK)
    surface.blit(heading, (x, y))
    y += heading.get_height() + 8
    box_w, box_h = width - 90, 70
    box = pygame.Rect(x, y, box_w, box_h)
    pygame.draw.rect(surface, theme.CARD_PAPER_EDGE, box)
    columns = scenario.get("board_columns")
    cols = scenario.get("board_generator", {}).get("cols", 33) or 33
    if columns and len(columns) == 2:
        lo, hi = columns
        left = x + int(box_w * (lo / cols))
        span = max(6, int(box_w * ((hi - lo + 1) / cols)))
        pygame.draw.rect(surface, theme.CARD_SHADE, pygame.Rect(left, y, span, box_h))
        note = f"Only columns {lo} to {hi} of the board are used."
    else:
        pygame.draw.rect(surface, theme.CARD_SHADE, box)
        note = "The whole board is used."
    pygame.draw.rect(surface, theme.CARD_INK, box, 2)
    # The north arrow to the right of the box.
    ax = x + box_w + 34
    ay = box.centery
    pygame.draw.line(surface, theme.CARD_INK, (ax, ay + 22), (ax, ay - 18), 3)
    pygame.draw.polygon(surface, theme.CARD_INK, [(ax, ay - 26), (ax - 7, ay - 12), (ax + 7, ay - 12)])
    label = fonts["small"].render("N", True, theme.CARD_INK)
    surface.blit(label, (ax - label.get_width() // 2, ay + 24))
    y += box_h + 6
    y = _blit_paragraph(surface, note, fonts["small"], x, y, width, theme.CARD_INK)
    return y


def _turn_chart(surface: pygame.Surface, scenario: dict[str, Any], fonts: dict[str, pygame.font.Font], x: int, y: int, width: int) -> int:
    """The turn record chart: numbered boxes and END, with the two side labels.

    The two labels come from `setup_order` and `first_mover`: who sets up first and who
    moves first. They are the words of the scenario, capitalized for the card.
    """
    heading = fonts["heading"].render("Turn Record Chart", True, theme.CARD_INK)
    surface.blit(heading, (x, y))
    y += heading.get_height() + 8
    setup_order = scenario.get("setup_order") or []
    first = scenario.get("first_mover", "")
    label_w = 220
    first_setup = setup_order[0] if setup_order else ""
    lines = []
    if first_setup:
        lines.append(f"{first_setup.capitalize()} sets up first")
    if first:
        lines.append(f"{first.capitalize()} moves first")
    ly = y
    for text in lines:
        label = fonts["subheading"].render(text, True, theme.CARD_INK)
        surface.blit(label, (x, ly))
        ly += label.get_height() + 6
    # The numbered track to the right of the labels.
    turns = int(scenario.get("turns", 0) or 0)
    track_x = x + label_w
    boxes = turns + 1  # the game turns plus END
    box_w = min(58, (width - label_w) // max(1, boxes))
    box_h = 46
    for i in range(boxes):
        rect = pygame.Rect(track_x + i * box_w, y, box_w - 4, box_h)
        pygame.draw.rect(surface, theme.CARD_PAPER, rect)
        pygame.draw.rect(surface, theme.CARD_INK, rect, 2)
        text = "END" if i == turns else str(i + 1)
        font = fonts["subheading"] if i == turns else fonts["count"]
        label = font.render(text, True, theme.CARD_INK)
        surface.blit(label, (rect.centerx - label.get_width() // 2, rect.centery - label.get_height() // 2))
    return max(ly, y + box_h) + 4


def _terrain_words(value: Any) -> str:
    kinds = [value] if isinstance(value, str) else list(value)
    # The card has two lines for a set up area, so the two building kinds are one word.
    if "stone_building" in kinds and "wooden_building" in kinds:
        kinds = ["buildings"] + [k for k in kinds if k not in ("stone_building", "wooden_building")]
    words = [str(k).replace("_", " ") for k in kinds]
    if len(words) <= 2:
        return " or ".join(words)
    return ", ".join(words[:-1]) + f", or {words[-1]}"


def _group_label(group: dict[str, Any]) -> str:
    """The set up area of one group, in the words of the scenario.

    A group names a zone, a band of columns, and a rank by building size. The card says the
    rank in plain words, because the printed board layout is not in this repository (DR-06).
    The zone `columns` is a band of hex columns, and not a march column: the card said "In a
    columns", and the owner read it as an order to set up on a road in a column.
    """
    area = group.get("area", {})
    zone = str(area.get("zone", ""))
    if zone == "stone_building":
        rank = area.get("rank")
        ordinals = {0: "largest", 1: "second largest", 2: "third largest", 3: "fourth largest", 4: "fifth largest"}
        size = "a" if rank is None else "the " + ordinals.get(rank, str(rank) + "th")
        return f"In {size} stone building"
    if zone == "edge":
        text = f"Within {int(area.get('depth', 1))} hexes of the {area.get('side', 'west')} edge"
    else:
        text = f"Anywhere {band_text(area)}"
    if area.get("terrain") is not None:
        text += f", in {_terrain_words(area['terrain'])}"
    if area.get("not_terrain") is not None:
        text += f", not in {_terrain_words(area['not_terrain'])}"
    if area.get("road") is not None:
        text += ", on a road" if area["road"] else ", off the roads"
    return text


GROUP_COLS = 3        # how many group cells sit across the block, like the 1977 card
CELL_UNIT_STEP = COUNTER + 20
TITLE_LINES = 2       # the group title wraps into at most this many lines
TITLE_H = TITLE_LINES * 17 + 6  # the reserved height of the title above the counters


def _group_rows(group: dict[str, Any], cell_w: int) -> int:
    """How many counter rows one group needs inside its cell of width `cell_w`."""
    per_row = max(1, cell_w // CELL_UNIT_STEP)
    units = len(group.get("units", []))
    return max(1, (units + per_row - 1) // per_row)


def _draw_group(surface: pygame.Surface, group: dict[str, Any], nationality: str, fonts: dict[str, pygame.font.Font], x: int, y: int, cell_w: int, start_index: int) -> int:
    """Draw one group cell: a title, then its units as mini-counters that wrap in the cell.

    A unit with a count of more than one draws one counter and prints the count in red below
    it, the way the original groups a stack under one figure. Returns the next unit index.
    """
    lines = _wrap(_group_label(group), fonts["cell"], cell_w)[:TITLE_LINES]
    ty = y
    for line in lines:
        label = fonts["cell"].render(line, True, theme.CARD_INK)
        surface.blit(label, (x, ty))
        ty += 17
    unit_top = y + TITLE_H
    per_row = max(1, cell_w // CELL_UNIT_STEP)
    index = start_index
    for i, unit in enumerate(group.get("units", [])):
        row, col = divmod(i, per_row)
        ccx = x + col * CELL_UNIT_STEP + COUNTER // 2
        row_top = unit_top + row * (COUNTER + 30)
        ccy = row_top + COUNTER // 2
        name = unit.get("name")
        count = int(unit.get("count", 1) or 1)
        udict = _unit_dict(unit["type"], name, index)
        udict["nationality"] = nationality
        index += 1
        _counter(surface, udict, ccx, ccy, COUNTER, fonts["chit"], fonts["chit"])
        below = row_top + COUNTER + 2
        if name:
            nlabel = fonts["small"].render(name, True, theme.CARD_INK)
            surface.blit(nlabel, (ccx - nlabel.get_width() // 2, below))
            below += 13
        if count > 1:
            clabel = fonts["count"].render(str(count), True, theme.CARD_RED)
            surface.blit(clabel, (ccx - clabel.get_width() // 2, below))
    return index


def _oob_height(side: dict[str, Any], cell_w: int) -> int:
    """The pixel height one side block needs, from its group grid."""
    groups = side.get("groups", [])
    rows = (len(groups) + GROUP_COLS - 1) // GROUP_COLS
    # Each grid row is as tall as its tallest group cell.
    total = 20
    for r in range(rows):
        cells = groups[r * GROUP_COLS:(r + 1) * GROUP_COLS]
        tall = max((_group_rows(g, cell_w) for g in cells), default=1)
        total += TITLE_H + tall * (COUNTER + 30) + 8
    return total


def _order_of_battle(surface: pygame.Surface, side: dict[str, Any], fonts: dict[str, pygame.font.Font], x: int, y: int, width: int) -> int:
    """One side block: the emblem at the left, then the groups in a grid of cells.

    The block frames the side and draws the emblem at the left. Each group is a cell with a
    title and its units. The grid holds GROUP_COLS group cells across, the way the original
    card sets several groups side by side. Returns the y below the block.
    """
    emblem_col = 76
    content_x = x + emblem_col
    content_w = width - emblem_col - 12
    cell_w = content_w // GROUP_COLS
    height = _oob_height(side, cell_w)
    frame = pygame.Rect(x, y, width, height)
    pygame.draw.rect(surface, theme.CARD_INK, frame, 2)
    _emblem(surface, side, x + 38, y + height // 2 - 12, 24)
    label = fonts["subheading"].render(side.get("side", "").capitalize(), True, theme.CARD_INK)
    surface.blit(label, (x + 38 - label.get_width() // 2, y + height // 2 + 18))
    groups = side.get("groups", [])
    index = 0
    row_y = y + 12
    for r in range((len(groups) + GROUP_COLS - 1) // GROUP_COLS):
        cells = groups[r * GROUP_COLS:(r + 1) * GROUP_COLS]
        tall = max((_group_rows(g, cell_w) for g in cells), default=1)
        for c, group in enumerate(cells):
            index = _draw_group(surface, group, side.get("nationality", "german"), fonts, content_x + c * cell_w, row_y, cell_w - 8, index)
        row_y += TITLE_H + tall * (COUNTER + 30) + 8
    return y + height


def render_card(scenario: dict[str, Any]) -> pygame.Surface:
    """Render one scenario document to a card surface.

    The caller passes the parsed scenario JSON. This function reads only its own fields and
    draws the whole card. It starts and initializes pygame font if the caller has not.
    """
    if not pygame.get_init():
        pygame.init()
    if not pygame.font.get_init():
        pygame.font.init()
    fonts = _fonts()
    surface = pygame.Surface((CARD_WIDTH, CARD_HEIGHT))
    surface.fill(theme.CARD_PAPER)
    pygame.draw.rect(surface, theme.CARD_INK, surface.get_rect(), 3)

    inner = CARD_WIDTH - 2 * MARGIN
    # The scenario number sits on its own line at the upper left, then the centered title
    # sits below it, so the two never overlap on a long title.
    number = _scenario_number(scenario)
    top = MARGIN
    if number:
        num = fonts["scenario"].render(number, True, theme.CARD_RED)
        surface.blit(num, (MARGIN, top))
        top += num.get_height() + 4
    title = fonts["title"].render(scenario.get("title", "").upper(), True, theme.CARD_INK)
    surface.blit(title, (CARD_WIDTH // 2 - title.get_width() // 2, top))

    y = top + title.get_height() + 20
    _rule(surface, MARGIN, y, inner)
    y += 12

    # Two columns under the title: the situation on the left, the board diagram on the right.
    left_w = int(inner * 0.56)
    right_x = MARGIN + left_w + 24
    right_w = inner - left_w - 24
    # The situation is the text for the players. The notes are the project's record of
    # where the scenario comes from, so a scenario with no situation shows them instead.
    situation = scenario.get("situation") or scenario.get("notes", "")
    left_bottom = _blit_paragraph(surface, situation, fonts["body"], MARGIN, y, left_w, theme.CARD_INK)
    right_y = _board_diagram(surface, scenario, fonts, right_x, y, right_w)
    right_y = _rules_introduced(surface, scenario, fonts, right_x, right_y + 14, right_w)

    y = max(left_bottom, right_y) + 16
    _rule(surface, MARGIN, y, inner)
    y += 14

    y = _turn_chart(surface, scenario, fonts, MARGIN, y, inner)
    y += 12
    _rule(surface, MARGIN, y, inner)
    y += 14

    # The order of battle blocks, one per side, stacked. Each block sizes itself to its
    # groups, so a side with more groups gets a taller block and nothing overlaps.
    sides = scenario.get("sides", [])
    for side in sides:
        y = _order_of_battle(surface, side, fonts, MARGIN, y, inner) + 10

    _rule(surface, MARGIN, y, inner)
    y += 14
    y = _victory(surface, scenario, fonts, MARGIN, y, inner)
    _special_rules(surface, scenario, fonts, MARGIN, y + 10, inner)
    return surface


def _scenario_number(scenario: dict[str, Any]) -> str:
    """The scenario number from the id, e.g. s01_guards_counterattack gives Scenario 1."""
    ident = str(scenario.get("id", ""))
    digits = "".join(ch for ch in ident.split("_")[0] if ch.isdigit())
    return f"Scenario {int(digits)}" if digits else ""


def _rules_introduced(surface: pygame.Surface, scenario: dict[str, Any], fonts: dict[str, pygame.font.Font], x: int, y: int, width: int) -> int:
    rules = scenario.get("rules_used") or []
    if not rules:
        return y
    nums = [int(r) for r in rules]
    text = f"Rules Introduced: Sections {min(nums)} to {max(nums)}"
    heading = fonts["subheading"].render("Rules Introduced", True, theme.CARD_INK)
    surface.blit(heading, (x, y))
    y += heading.get_height() + 4
    return _blit_paragraph(surface, f"Sections {min(nums)} to {max(nums)}.", fonts["body"], x, y, width, theme.CARD_INK)


def _victory(surface: pygame.Surface, scenario: dict[str, Any], fonts: dict[str, pygame.font.Font], x: int, y: int, width: int) -> int:
    heading = fonts["heading"].render("Victory Conditions", True, theme.CARD_INK)
    surface.blit(heading, (x, y))
    y += heading.get_height() + 6
    for item in scenario.get("victory", []):
        note = item.get("note")
        if note:
            y = _blit_paragraph(surface, note, fonts["body"], x, y, width, theme.CARD_INK, line_gap=3)
            y += 4
    return y


def _special_rules(surface: pygame.Surface, scenario: dict[str, Any], fonts: dict[str, pygame.font.Font], x: int, y: int, width: int) -> int:
    """Special rules: the list of switches the scenario sets, in its own words.

    The original card holds a special rules block. The project's own special rules are the
    scenario switches, so the card names each switch and its value. A scenario with no switch
    prints nothing.
    """
    switches = scenario.get("switches") or {}
    if not switches:
        return y
    heading = fonts["heading"].render("Special Rules", True, theme.CARD_INK)
    surface.blit(heading, (x, y))
    y += heading.get_height() + 6
    for key, value in switches.items():
        text = f"{key.replace('_', ' ').capitalize()}: {value}."
        y = _blit_paragraph(surface, text, fonts["body"], x, y, width, theme.CARD_INK, line_gap=2)
    return y


def save_card(scenario: dict[str, Any], path: Path) -> Path:
    """Render the scenario and write the card PNG to `path`."""
    surface = render_card(scenario)
    path.parent.mkdir(parents=True, exist_ok=True)
    pygame.image.save(surface, str(path))
    return path
