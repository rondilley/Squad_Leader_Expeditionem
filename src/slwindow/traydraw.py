"""The set up tray of the two windows: the pygame drawing, with no game library.

While the side of the person sets up, a tray along the bottom of the board shows a picture
of each counter of that side (`slwindow.setup` is the model, `slwindow.traycontrol` is what
a click does). A click on a counter selects it, and the overlay shades each hex where it
can go; a click on a shaded hex places it. A drag of a counter to a shaded hex places it
too. A counter that is on the board is in the tray too, and a click on it (or on its
counter on the board) takes it back to the tray, so the person can place it again. A
button ends the set up, and a button gives the side to the set up helper.

The drawing functions take a pygame Surface and give back the rectangles of a click, so a
test reads them with no window. The 2D window blits the tray on its surface, and the 3D
window shows it as a texture (`slwindow3d.tray.Overlay2D`). The window holds no rule
(AR-06): the tray shows what the legal list and the view say.
"""

from __future__ import annotations

import math
from typing import Any, Sequence

from slwindow import counters as chit_counters
from slwindow import setup

# The colours of the tray are the colours of the boxes. The about box is in that module,
# because the 2D window shows it too.
from slwindow.boxes import SELECTED, TEXT, TEXT_DIM, TRAY_BACK, TRAY_LINE, about_height, draw_about  # noqa: F401

# The line that says why a hex refused the counter.
REFUSED = (255, 128, 108)
BUTTON = (58, 64, 56)
BUTTON_ON = (46, 104, 58)
BUTTON_TEXT = (240, 238, 228)

# The header has two lines: the count of the set up, and what to do with the selection.
HEADER_HEIGHT = 52
BUTTON_HEIGHT = 24
TILE_GAP = 10
LABEL_HEIGHT = 16
MAX_TILE = 64
MIN_TILE = 34
# The tray takes at most this share of the window height.
MAX_SHARE = 0.42

ACTION_UNIT = "unit"
ACTION_FINISH = "finish"
ACTION_AUTO = "auto"
ACTION_ABOUT = "about"


def tray_height(count: int, width: int, window_height: int) -> tuple[int, int]:
    """The height of the tray and the size of a counter tile for this many counters. The
    tiles get smaller until the tray fits in `MAX_SHARE` of the window."""
    tile = MAX_TILE
    limit = int(window_height * MAX_SHARE)
    while True:
        per_row = max(1, (width - TILE_GAP) // (tile + TILE_GAP))
        rows = max(1, math.ceil(count / per_row))
        height = HEADER_HEIGHT + rows * (tile + LABEL_HEIGHT + TILE_GAP) + TILE_GAP
        if height <= limit or tile <= MIN_TILE:
            # The smallest tiles take the height they need, so no counter is left out.
            return height, tile
        tile -= 4


def _button(pygame: Any, surface: Any, font: Any, text: str, right: int, on: bool) -> Any:
    label = font.render(text, True, BUTTON_TEXT if on else TEXT_DIM)
    rect = pygame.Rect(0, 5, label.get_width() + 20, BUTTON_HEIGHT)
    rect.right = right
    pygame.draw.rect(surface, BUTTON_ON if on else BUTTON, rect, border_radius=4)
    surface.blit(label, (rect.x + 10, rect.y + (rect.height - label.get_height()) // 2))
    return rect


def draw_tray(
    surface: Any,
    items: Sequence[setup.TrayItem],
    selected: int | None,
    finish: bool,
    font: Any,
    small: Any,
    tile: int = MAX_TILE,
    labels: dict[int, str] | None = None,
    hint: str | None = None,
    refusal: str | None = None,
) -> list[tuple[Any, str, int | None]]:
    """Draw the tray on the whole surface, with counter tiles of this size (see
    `tray_height`). `labels` is the text below each counter and `hint` the line of what to
    do (`slwindow.setup.item_label` and `hint`). `refusal` is the reason the last hex
    refused the counter (`slwindow.overlay.setup_refusal`), and it takes the place of the
    hint. Return the click rectangles, each with its action and its unit ID (or None)."""
    import pygame

    width, height = surface.get_size()
    surface.fill(TRAY_BACK)
    pygame.draw.line(surface, TRAY_LINE, (0, 0), (width, 0), 2)
    hits: list[tuple[Any, str, int | None]] = []
    placed, total = setup.counts(items)
    right = width - TILE_GAP
    finish_rect = _button(pygame, surface, font, "Finish set up", right, finish)
    hits.append((finish_rect, ACTION_FINISH, None))
    auto_rect = _button(pygame, surface, font, "Set up for me", finish_rect.left - TILE_GAP, True)
    hits.append((auto_rect, ACTION_AUTO, None))
    about_on = selected is not None and selected != setup.CONCEALMENT
    about_rect = _button(pygame, surface, font, "About this unit", auto_rect.left - TILE_GAP, about_on)
    hits.append((about_rect, ACTION_ABOUT, None))
    if hint is None:
        hint = "Click or drag a counter to a shaded hex."
    header = font.render(f"Set up: {placed} of {total} on the board.", True, TEXT)
    clip = pygame.Rect(TILE_GAP, 0, max(0, about_rect.left - 2 * TILE_GAP), HEADER_HEIGHT)
    surface.set_clip(clip)
    surface.blit(header, (TILE_GAP, 5 + (BUTTON_HEIGHT - header.get_height()) // 2))
    surface.set_clip(None)
    if refusal:
        line = small.render(f"Not there: {refusal}", True, REFUSED)
    else:
        line = small.render(hint, True, SELECTED if selected is not None else TEXT_DIM)
    surface.blit(line, (TILE_GAP, 5 + BUTTON_HEIGHT + 3))

    per_row = max(1, (width - TILE_GAP) // (tile + TILE_GAP))
    for index, item in enumerate(items):
        row, column = divmod(index, per_row)
        x = TILE_GAP + column * (tile + TILE_GAP)
        y = HEADER_HEIGHT + TILE_GAP // 2 + row * (tile + LABEL_HEIGHT + TILE_GAP)
        if y + tile > height:
            break
        rect = pygame.Rect(x, y, tile, tile)
        _tile(pygame, surface, item, rect, tile, small)
        if selected is not None and item.unit_id == selected:
            pygame.draw.rect(surface, SELECTED, rect.inflate(6, 6), 3, border_radius=6)
        if labels is not None and item.unit_id in labels:
            label = labels[item.unit_id]
        elif item.placed:
            label = f"in {item.hex}"
        elif item.offered is None:
            label = "later"
        else:
            label = "to place"
        colour = TEXT if label == "to place" else TEXT_DIM
        text = small.render(label, True, colour)
        surface.blit(text, (x + (tile - text.get_width()) // 2, y + tile + 1))
        hits.append((rect, ACTION_UNIT, item.unit_id))
    return hits


def _tile(pygame: Any, surface: Any, item: setup.TrayItem, rect: Any, tile: int, small: Any) -> None:
    """The counter picture of one item. A placed counter is dim, so the ones to place
    stand out."""
    picture = pygame.Surface((tile, tile), pygame.SRCALPHA)
    centre = tile / 2.0
    if item.unit is None:
        pygame.draw.rect(picture, (70, 70, 64), picture.get_rect(), border_radius=6)
        mark = small.render("?", True, TEXT)
        picture.blit(mark, ((tile - mark.get_width()) // 2, (tile - mark.get_height()) // 2))
    elif item.unit.get("kind") == "vehicle":
        chit_counters._vehicle(picture, item.unit, centre, centre, tile / chit_counters.VEHICLE_SCALE, small, small, shadow=False)
    else:
        chit_counters._counter(picture, item.unit, centre, centre, tile, small, small, shadow=False)
    if item.placed or item.offered is None:
        picture.set_alpha(110)
    surface.blit(picture, rect.topleft)


def draw_carried(surface: Any, unit: dict[str, Any] | None, small: Any) -> None:
    """The counter that the person drags from the tray or from the board to a hex."""
    import pygame

    tile = surface.get_width()
    _tile(pygame, surface, setup.TrayItem(setup.CONCEALMENT if unit is None else int(unit["id"]), unit, False, 0), surface.get_rect(), tile, small)
    pygame.draw.rect(surface, SELECTED, surface.get_rect(), 2, border_radius=6)
