"""The side panel of the desktop windows: the scenario, the status, the commands, the log.

The panel lists the legal commands that the host sent and nothing else. A command the host
did not send is not on the list, so the window cannot invent one (AR-06).

The pygame window draws the panel on its surface, and the 3D window draws it to a texture,
so the two windows have one panel. The list scrolls: the panel draws the rows that fit and
moves them so the cursor stays on the screen (H7). The log shows the dice, the modifiers,
the units, and the hexes of each entry, the same fields as the browser log (FR-06). After
the end of the game the panel shows the result, the conditions, and the losses of each
side (the `game_over` message of protocol version 2).
"""

from __future__ import annotations

from typing import Any

import pygame

from slwindow import choice, endgame, logtext, theme
from slwindow.client import STATUS_GAME_OVER, STATUS_TEXT, STATUS_THINKING, STATUS_YOUR_TURN, status_of

WIDTH = 320
PAD = 12
LINE = 18
LOG_LINES = 12
# The fewest command rows the panel keeps, even in a short window.
MIN_ROWS = 3
# The index of the Undo button among the click rows. No legal index is negative.
UNDO_ROW = -1
UNDO_HEIGHT = 24
# The index of the "Victory conditions" button among the click rows.
OBJECTIVES_ROW = -2


def draw_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    state: Any,
    font: pygame.font.Font,
    small: pygame.font.Font,
    selected: int | None,
    filter_text: str,
    chooser: choice.Chooser | None = None,
    undo_button: bool = False,
    objectives_on: bool | None = None,
) -> list[tuple[pygame.Rect, int]]:
    """Draw the panel and give back the clickable command rows, each with its legal index.

    With `undo_button` the panel has an Undo button under the status, and its click row
    has the index `UNDO_ROW`. With `objectives_on` (True or False, not None) the panel has
    the "Victory conditions" button, bright while it is on, with the index `OBJECTIVES_ROW`. The button is bright when the host says that an undo can go
    (`can_undo`), and dim when it cannot.

    `selected` is the legal index under the cursor. A window gives its `Chooser`, which
    holds the filter, the board narrowing, and the scroll. With no chooser the panel
    narrows by `filter_text` only and scrolls to the selected row.
    """
    if chooser is None:
        chooser = choice.Chooser()
        chooser.filter_text = filter_text
        chooser.frame_id = str(getattr(state, "frame_id", ""))
        rows_seen = chooser.visible(state.legal, state.view)
        for position, (index, _entry) in enumerate(rows_seen):
            if index == selected:
                chooser.position = position
    pygame.draw.rect(surface, theme.PANEL, rect)
    pygame.draw.line(surface, theme.PANEL_RULE, rect.topleft, rect.bottomleft, 2)
    y = rect.top + PAD
    title = state.scenario.get("title", "") if state.scenario else "waiting for the host"
    y = _line(surface, rect, y, title, font, theme.PANEL_TEXT)
    if state.board:
        turns = state.scenario.get("turns", "?") if state.scenario else "?"
        y = _line(surface, rect, y, f"board {state.board.get('name', '')}, {turns} turns", small, theme.PANEL_DIM)
    y = _line(surface, rect, y, f"seat: {_seat_text(state)}", small, theme.PANEL_DIM)
    y = _line(surface, rect, y, endgame.turn_text(state), small, theme.HIGHLIGHT if not state.game_over else theme.PANEL_DIM)
    y = _line(surface, rect, y, f"phase: {state.phase} / {state.sub_step}", small, theme.PANEL_DIM)
    y = _line(surface, rect, y, f"acts now: {_actor_text(state)}", small, theme.PANEL_DIM)
    y = _line(surface, rect, y, _status_line(state), small, _status_colour(state))
    phase_text = str(getattr(state, "phase_text", "") or "")
    if phase_text and not state.game_over:
        y = _wrapped(surface, rect, y, phase_text, small, theme.PANEL_DIM)
    if state.game_over:
        y = _end_panel(surface, rect, y, state, font, small)
    if state.notice:
        y = _wrapped(surface, rect, y, state.notice, small, theme.SELECT)
    applied = list(getattr(state, "auto_applied", []) or [])
    if applied:
        y = _wrapped(surface, rect, y, "applied for you: " + "; ".join(applied), small, theme.PANEL_DIM)
    undo_rect = None
    if undo_button and not state.game_over:
        on = bool(getattr(state, "can_undo", False))
        text = "Undo the last command (Ctrl and z)" if on else "Undo: nothing to take back now"
        label = small.render(text, True, theme.PANEL_TEXT if on else theme.PANEL_DIM)
        undo_rect = pygame.Rect(rect.left + PAD, y + 4, label.get_width() + 20, UNDO_HEIGHT)
        pygame.draw.rect(surface, theme.UNDO_ON if on else theme.PANEL_RULE, undo_rect, border_radius=4)
        surface.blit(label, (undo_rect.left + 10, undo_rect.top + (UNDO_HEIGHT - label.get_height()) // 2))
        y = undo_rect.bottom + 4
    objectives_rect = None
    if objectives_on is not None:
        text = "Victory conditions (Ctrl and v)"
        label = small.render(text, True, theme.PANEL_TEXT)
        objectives_rect = pygame.Rect(rect.left + PAD, y + 2, label.get_width() + 20, UNDO_HEIGHT)
        pygame.draw.rect(surface, theme.OBJECTIVES_ON if objectives_on else theme.OBJECTIVES_OFF, objectives_rect, border_radius=4)
        surface.blit(label, (objectives_rect.left + 10, objectives_rect.top + (UNDO_HEIGHT - label.get_height()) // 2))
        y = objectives_rect.bottom + 4
    y += 6
    pygame.draw.line(surface, theme.PANEL_RULE, (rect.left + PAD, y), (rect.right - PAD, y), 1)
    y += 8

    rows: list[tuple[pygame.Rect, int]] = []
    if chooser.filter_text:
        y = _line(surface, rect, y, f"find: {chooser.filter_text}", small, theme.HIGHLIGHT)
    if chooser.unit is not None or chooser.hex is not None:
        y = _line(surface, rect, y, f"board choice: {_narrow_text(chooser, state)}", small, theme.HIGHLIGHT)
    commands = chooser.visible(state.legal, state.view)
    y = _line(surface, rect, y, f"legal commands: {len(commands)} of {len(state.legal)}", small, theme.PANEL_DIM)
    log_top = rect.bottom - PAD - LINE * (LOG_LINES + 1) - 8
    # One line above the rows and one below them say how many rows are off the screen.
    # They always hold their place, so the count of rows does not change with the scroll.
    space = max(MIN_ROWS, (log_top - y) // LINE - 2)
    chooser.page_rows = space
    if commands:
        chooser.position = min(chooser.position, len(commands) - 1)
    chooser.keep_visible()
    chooser.scroll = max(0, min(chooser.scroll, max(0, len(commands) - space)))
    if chooser.scroll > 0:
        _line(surface, rect, y, f"{chooser.scroll} more above", small, theme.PANEL_DIM)
    y += LINE
    shown = commands[chooser.scroll : chooser.scroll + space]
    limit = rect.width - 2 * PAD - 8
    for index, command in shown:
        row = pygame.Rect(rect.left + PAD, y, rect.width - 2 * PAD, LINE)
        if index == selected:
            pygame.draw.rect(surface, theme.PANEL_RULE, row)
        colour = theme.HIGHLIGHT if index == selected else theme.PANEL_TEXT
        label = small.render(_fit(choice.row_text(command, state.view), small, limit), True, colour)
        surface.blit(label, (row.left + 4, row.top + 2))
        rows.append((row, index))
        y += LINE
    below = len(commands) - chooser.scroll - len(shown)
    if below > 0:
        y = _line(surface, rect, y, f"{below} more below (Tab, the page keys, the wheel)", small, theme.PANEL_DIM)

    # The buttons come after the command rows, so the first row is the first command.
    if undo_rect is not None and getattr(state, "can_undo", False):
        rows.append((undo_rect, UNDO_ROW))
    if objectives_rect is not None:
        rows.append((objectives_rect, OBJECTIVES_ROW))

    y = max(y + 8, log_top)
    pygame.draw.line(surface, theme.PANEL_RULE, (rect.left + PAD, y), (rect.right - PAD, y), 1)
    y += 6
    y = _line(surface, rect, y, "action log", small, theme.PANEL_DIM)
    lines: list[str] = []
    for entry in state.log[-LOG_LINES:]:
        lines.extend(_wrap(logtext.line(entry, state.view), small, rect.width - 2 * PAD))
    for text in lines[-LOG_LINES:]:
        y = _line(surface, rect, y, text, small, theme.PANEL_TEXT)
    return rows


def _status_line(state: Any) -> str:
    if getattr(state, "reconnecting", False):
        return "status: the connection dropped, the window connects again"
    status = status_of(state)
    text = f"status: {STATUS_TEXT.get(status, status.replace('_', ' '))}"
    if getattr(state, "can_undo", False):
        text += "   (Ctrl and z: undo)"
    return text


def _status_colour(state: Any) -> tuple[int, int, int]:
    status = status_of(state)
    if status in (STATUS_YOUR_TURN, STATUS_GAME_OVER):
        return theme.HIGHLIGHT
    if status == STATUS_THINKING:
        return theme.SELECT
    return theme.PANEL_DIM


def side_name(state: Any, player: Any) -> str:
    """The name of a side, from the welcome (version 2) or from the scenario."""
    return endgame.side_name(state, player)


def end_lines(state: Any) -> list[str]:
    """The text of the end panel: "game over: you lost", then the lines of
    `endgame.summary` (the side that wins, the turn, the conditions, the losses)."""
    found = endgame.summary(state)
    head = found.headline.rstrip(".")
    lines = [f"game over: {head[:1].lower() + head[1:]}"]
    lines.extend(found.lines)
    return lines


def _end_panel(surface: pygame.Surface, rect: pygame.Rect, y: int, state: Any, font: pygame.font.Font, small: pygame.font.Font) -> int:
    lines = end_lines(state)
    y = _line(surface, rect, y, lines[0], font, theme.HIGHLIGHT)
    for text in lines[1:]:
        y = _wrapped(surface, rect, y, text, small, theme.PANEL_TEXT)
    return y


def _narrow_text(chooser: choice.Chooser, state: Any) -> str:
    parts = []
    if chooser.unit is not None:
        name = next(
            (u.get("name") for u in (state.view or {}).get("units", []) if u.get("id") == chooser.unit),
            None,
        )
        parts.append(f"{name} [{chooser.unit}]" if name else f"unit {chooser.unit}")
    if chooser.hex is not None:
        parts.append(f"hex {chooser.hex}")
    return ", ".join(parts) + " (Escape clears)"


def _seat_text(state: Any) -> str:
    """A watcher of a game between two computer opponents holds no seat (AR-09)."""
    view = state.view or {}
    if view.get("spectator"):
        return "watching, computer against computer"
    sides = getattr(state, "sides", None) or {}
    if isinstance(sides, dict) and sides:
        parts = []
        for key in sorted(sides):
            record = sides[key]
            if isinstance(record, dict):
                parts.append(f"{record.get('name', key)} {record.get('controller', '')}".strip())
        if parts:
            return f"{state.seat or 'waiting'} ({'; '.join(parts)})"
    return state.seat or "waiting"


def _actor_text(state: Any) -> str:
    view = state.view or {}
    name = side_name(state, state.active)
    if view.get("spectator"):
        return name
    return "you" if state.active == state.player and state.legal else name


def describe(command: dict[str, Any]) -> str:
    """One line for one command, from its payload and nothing else."""
    return choice.describe(command)


def _fit(text: str, font: pygame.font.Font, limit: int) -> str:
    """Cut a text to the width of the panel, with three dots at the cut."""
    if font.size(text)[0] <= limit:
        return text
    while text and font.size(text + "...")[0] > limit:
        text = text[:-1]
    return text + "..."


def _wrap(text: str, font: pygame.font.Font, limit: int) -> list[str]:
    """Break a text into lines of the panel width. A second line starts two spaces in."""
    out: list[str] = []
    line = ""
    for word in text.split():
        trial = f"{line} {word}" if line else word
        if font.size(trial)[0] > limit and line:
            out.append(line)
            line = f"  {word}"
        else:
            line = trial
    if line:
        out.append(line)
    return out


def _line(
    surface: pygame.Surface,
    rect: pygame.Rect,
    y: int,
    text: str,
    font: pygame.font.Font,
    colour: tuple[int, int, int],
) -> int:
    label = font.render(text, True, colour)
    surface.blit(label, (rect.left + PAD, y))
    return y + label.get_height() + 2


def _wrapped(
    surface: pygame.Surface,
    rect: pygame.Rect,
    y: int,
    text: str,
    font: pygame.font.Font,
    colour: tuple[int, int, int],
) -> int:
    words = text.split()
    line = ""
    limit = rect.width - 2 * PAD
    for word in words:
        trial = f"{line} {word}".strip()
        if font.size(trial)[0] > limit and line:
            y = _line(surface, rect, y, line, font, colour)
            line = word
        else:
            line = trial
    if line:
        y = _line(surface, rect, y, line, font, colour)
    return y
