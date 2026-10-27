"""The boxes that the two windows draw over the board: the menu of a unit and the
"about this unit" box. Each one draws with pygame on a Surface and gives back the
rectangles a click can choose, so a test reads them with no window.

`slwindow.unitmenu` gives the rows of the menu, and `slwindow.unitinfo` gives the facts of
the about box. The 2D window blits a box on its surface, and the 3D window shows it as a
texture (`slwindow3d.tray.Overlay2D`). The boxes hold no rule (AR-06).
"""

from __future__ import annotations

from typing import Any, Sequence

from slwindow import counters as chit_counters
from slwindow import unitinfo, unitmenu

# The colours of the boxes and of the set up tray, in the tones of the side panel.
TRAY_BACK = (24, 27, 24, 236)
TRAY_LINE = (90, 96, 86)
TEXT = (232, 232, 222)
TEXT_DIM = (150, 152, 144)
SELECTED = (250, 214, 92)

# The width of the about box.
ABOUT_WIDTH = 460


def draw_about(surface: Any, unit: dict[str, Any], font: Any, small: Any, view: dict[str, Any] | None = None) -> None:
    """The "about this unit" box: the counter picture, the title, and the facts."""
    import pygame

    width, height = surface.get_size()
    surface.fill(TRAY_BACK)
    pygame.draw.rect(surface, TRAY_LINE, surface.get_rect(), 2, border_radius=6)
    tile = 72
    picture = pygame.Surface((tile, tile), pygame.SRCALPHA)
    if unit.get("kind") == "vehicle":
        chit_counters._vehicle(picture, unit, tile / 2, tile / 2, tile / chit_counters.VEHICLE_SCALE, small, small, shadow=False)
    else:
        chit_counters._counter(picture, unit, tile / 2, tile / 2, tile, small, small, shadow=False)
    surface.blit(picture, (12, 12))
    title = font.render(unitinfo.title(unit), True, SELECTED)
    surface.blit(title, (tile + 24, 14))
    y = 14 + title.get_height() + 6
    for line in unitinfo.facts(unit, view):
        for part in _wrap(line, small, width - tile - 36):
            text = small.render(part, True, TEXT)
            surface.blit(text, (tile + 24, y))
            y += text.get_height() + 2
    hint = small.render("Right click, Escape, or a click closes this box.", True, TEXT_DIM)
    surface.blit(hint, (12, height - hint.get_height() - 8))


def about_height(unit: dict[str, Any], font: Any, small: Any, width: int, view: dict[str, Any] | None = None) -> int:
    """The height the box needs for this unit."""
    lines = sum(len(_wrap(line, small, width - 72 - 36)) for line in unitinfo.facts(unit, view))
    return max(110, 14 + font.get_linesize() + 6 + lines * (small.get_linesize() + 2) + small.get_linesize() + 20)


def _wrap(text: str, font: Any, width: int) -> list[str]:
    words = text.split()
    lines: list[str] = []
    line = ""
    for word in words:
        trial = f"{line} {word}".strip()
        if line and font.size(trial)[0] > width:
            lines.append(line)
            line = word
        else:
            line = trial
    if line:
        lines.append(line)
    return lines or [""]


# ------------------------------------------------------------------------ the menu

WIDTH = 520
PAD = 12
# A row a click can choose has a light band under the pointer.
ROW_BAND = (52, 58, 50)
HEADER_TEXT = (196, 200, 186)
COMMAND_TEXT = (240, 238, 228)


def _lines(row: unitmenu.MenuRow, small: Any, width: int) -> list[str]:
    return _wrap(row.text, small, width - 2 * PAD - 8) or [""]


def menu_height(title: str, rows: Sequence[unitmenu.MenuRow], font: Any, small: Any, width: int = WIDTH) -> int:
    height = PAD + font.get_linesize() + 6
    for row in rows:
        height += len(_lines(row, small, width)) * (small.get_linesize() + 2) + (6 if row.kind == unitmenu.ROW_HEADER else 2)
    return height + PAD


def chosen(row: unitmenu.MenuRow) -> bool:
    """A row that a click plays: a command, the box of the unit, or the undo."""
    return row.kind in (unitmenu.ROW_COMMAND, unitmenu.ROW_ABOUT, unitmenu.ROW_UNDO) and not (
        row.kind == unitmenu.ROW_UNDO and row.text.startswith("Undo:")
    )


def draw_menu(
    surface: Any,
    title: str,
    rows: Sequence[unitmenu.MenuRow],
    font: Any,
    small: Any,
    hover: int | None = None,
) -> list[tuple[Any, unitmenu.MenuRow]]:
    """Draw the menu on the whole surface. `hover` is the place of the row under the
    pointer. Return the rectangle of each row that a click can choose."""
    import pygame

    width, _height = surface.get_size()
    surface.fill(TRAY_BACK)
    pygame.draw.rect(surface, TRAY_LINE, surface.get_rect(), 2, border_radius=6)
    y = PAD
    surface.blit(font.render(title, True, TEXT), (PAD, y))
    y += font.get_linesize() + 6
    hits: list[tuple[Any, unitmenu.MenuRow]] = []
    for place, row in enumerate(rows):
        lines = _lines(row, small, width)
        height = len(lines) * (small.get_linesize() + 2)
        if row.kind == unitmenu.ROW_HEADER:
            y += 4
            if row.text:
                surface.blit(small.render(row.text.upper(), True, HEADER_TEXT), (PAD, y))
            else:
                pygame.draw.line(surface, TRAY_LINE, (PAD, y + height // 2), (width - PAD, y + height // 2), 1)
            y += height + 2
            continue
        rect = pygame.Rect(PAD - 4, y - 1, width - 2 * PAD + 8, height + 2)
        active = chosen(row)
        if active and place == hover:
            pygame.draw.rect(surface, ROW_BAND, rect, border_radius=3)
        colour = COMMAND_TEXT if active else TEXT_DIM
        if row.kind in (unitmenu.ROW_ABOUT, unitmenu.ROW_UNDO) and active:
            colour = SELECTED
        indent = PAD + (8 if row.kind == unitmenu.ROW_COMMAND else 0)
        for index, line in enumerate(lines):
            surface.blit(small.render(line, True, colour), (indent, y + index * (small.get_linesize() + 2)))
        if active:
            hits.append((rect, row))
        y += height + 2
    return hits


# ------------------------------------------------------------------- the end of a game

END_WIDTH = 560
WON = (120, 220, 120)
LOST = (240, 120, 100)


def end_height(summary: Any, font: Any, small: Any, width: int = END_WIDTH) -> int:
    lines = sum(len(_wrap(line, small, width - 2 * PAD)) for line in summary.lines)
    return PAD + font.get_linesize() * 2 + 10 + lines * (small.get_linesize() + 2) + small.get_linesize() + 2 * PAD


def draw_end(surface: Any, summary: Any, font: Any, small: Any) -> None:
    """The box of the end of the game: the headline in large text, then the lines."""
    import pygame

    width, height = surface.get_size()
    surface.fill(TRAY_BACK)
    pygame.draw.rect(surface, TRAY_LINE, surface.get_rect(), 2, border_radius=6)
    colour = WON if summary.headline.startswith("You won") else LOST if summary.headline.startswith("You lost") else SELECTED
    big = pygame.font.Font(None, max(28, font.get_linesize() * 2))
    head = big.render(summary.headline, True, colour)
    surface.blit(head, ((width - head.get_width()) // 2, PAD))
    y = PAD + head.get_height() + 10
    for line in summary.lines:
        for part in _wrap(line, small, width - 2 * PAD):
            surface.blit(small.render(part, True, TEXT), (PAD, y))
            y += small.get_linesize() + 2
    hint = small.render("Escape or a click closes this box.", True, TEXT_DIM)
    surface.blit(hint, (PAD, height - hint.get_height() - PAD // 2))


# ------------------------------------------------------------- the victory conditions

OBJECTIVES_WIDTH = 520
OBJECTIVES_TITLE = (200, 150, 245)


def objectives_height(lines: Sequence[str], font: Any, small: Any, width: int = OBJECTIVES_WIDTH) -> int:
    count = sum(len(_wrap(line, small, width - 2 * PAD)) for line in lines)
    return PAD + font.get_linesize() + 8 + count * (small.get_linesize() + 2) + len(lines) * 4 + small.get_linesize() + 2 * PAD


def draw_objectives(surface: Any, lines: Sequence[str], font: Any, small: Any) -> None:
    """The box of the victory conditions (`slwindow.victorytext`)."""
    import pygame

    width, height = surface.get_size()
    surface.fill(TRAY_BACK)
    pygame.draw.rect(surface, OBJECTIVES_TITLE, surface.get_rect(), 2, border_radius=6)
    surface.blit(font.render("Victory conditions", True, OBJECTIVES_TITLE), (PAD, PAD))
    y = PAD + font.get_linesize() + 8
    for index, line in enumerate(lines):
        colour = SELECTED if index == 0 else TEXT
        for part in _wrap(line, small, width - 2 * PAD):
            surface.blit(small.render(part, True, colour), (PAD, y))
            y += small.get_linesize() + 2
        y += 4
    hint = small.render("Ctrl and v, Escape, or the button closes this box.", True, TEXT_DIM)
    surface.blit(hint, (PAD, height - hint.get_height() - PAD // 2))
