"""The side panel of the desktop window: the scenario, the turn, the log, and the commands.

The panel lists the legal commands that the host sent and nothing else. A command the host
did not send is not on the list, so the window cannot invent one (AR-06).
"""

from __future__ import annotations

from typing import Any, Sequence

import pygame

from slwindow import theme
from slwindow.logtext import log_text, unit_names

WIDTH = 320
PAD = 12
LINE = 18
LOG_LINES = 12
# The events that say how the game moves on, not what happened to a unit. The log leaves
# them out so that the lines with dice stay in view.
QUIET_KINDS = frozenset({"group_add", "group_leader", "track_return", "track_return_end", "turn_start"})
MAX_COMMANDS = 18


def draw_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    state: Any,
    font: pygame.font.Font,
    small: pygame.font.Font,
    selected: int,
    filter_text: str,
    show_commands: bool = True,
) -> list[tuple[pygame.Rect, int]]:
    """Draw the panel and give back the clickable command rows.

    With show_commands False the panel draws no command list (the 3D window has its own
    buttons), and the action log takes the space."""
    pygame.draw.rect(surface, theme.PANEL, rect)
    pygame.draw.line(surface, theme.PANEL_RULE, rect.topleft, rect.bottomleft, 2)
    y = rect.top + PAD
    title = state.scenario.get("title", "") if state.scenario else "waiting for the host"
    y = _line(surface, rect, y, title, font, theme.PANEL_TEXT)
    if state.board:
        turns = state.scenario.get("turns", "?") if state.scenario else "?"
        y = _line(surface, rect, y, f"board {state.board.get('name', '')}, {turns} turns", small, theme.PANEL_DIM)
    y = _line(surface, rect, y, f"seat: {_seat_text(state)}", small, theme.PANEL_DIM)
    y = _line(surface, rect, y, f"turn {state.turn}   {state.phase} / {state.sub_step}", small, theme.PANEL_DIM)
    y = _line(surface, rect, y, f"acts now: {_actor_text(state)}", small, theme.PANEL_DIM)
    if state.game_over:
        y = _line(surface, rect, y, f"result: {state.result}", font, theme.HIGHLIGHT)
        y = _line(surface, rect, y, state.result_cause, small, theme.PANEL_DIM)
    if state.notice:
        y = _wrapped(surface, rect, y, state.notice, small, theme.SELECT)
    y += 6
    pygame.draw.line(surface, theme.PANEL_RULE, (rect.left + PAD, y), (rect.right - PAD, y), 1)
    y += 8

    rows: list[tuple[pygame.Rect, int]] = []
    if not show_commands:
        _draw_log(surface, rect, y, state, small, max(LOG_LINES, (rect.bottom - y - PAD) // LINE - 1))
        return rows
    if filter_text:
        y = _line(surface, rect, y, f"find: {filter_text}", small, theme.HIGHLIGHT)
    commands = _matching(state.legal, filter_text)
    y = _line(surface, rect, y, f"legal commands: {len(commands)} of {len(state.legal)}", small, theme.PANEL_DIM)
    for index, command in commands[:MAX_COMMANDS]:
        row = pygame.Rect(rect.left + PAD, y, rect.width - 2 * PAD, LINE)
        if index == selected:
            pygame.draw.rect(surface, theme.PANEL_RULE, row)
        colour = theme.HIGHLIGHT if index == selected else theme.PANEL_TEXT
        label = small.render(describe(command), True, colour)
        surface.blit(label, (row.left + 4, row.top + 2))
        rows.append((row, index))
        y += LINE
    if len(commands) > MAX_COMMANDS:
        y = _line(surface, rect, y, f"and {len(commands) - MAX_COMMANDS} more", small, theme.PANEL_DIM)

    y = max(y + 8, rect.bottom - PAD - LINE * (LOG_LINES + 1))
    _draw_log(surface, rect, y, state, small, LOG_LINES)
    return rows


def _draw_log(surface: pygame.Surface, rect: pygame.Rect, y: int, state: Any, small: pygame.font.Font, lines: int) -> None:
    """The action log: one line for each event, with its rule, dice, modifier, and result
    (BC-04). A line that does not fit the panel wraps."""
    pygame.draw.line(surface, theme.PANEL_RULE, (rect.left + PAD, y), (rect.right - PAD, y), 1)
    y += 6
    y = _line(surface, rect, y, "action log", small, theme.PANEL_DIM)
    names = unit_names(state.view)
    texts = [log_text(entry, names) for entry in state.log if entry.get("kind") not in QUIET_KINDS]
    for text in texts[-lines:]:
        if y > rect.bottom - PAD - LINE:
            break
        y = _wrapped(surface, rect, y, text, small, theme.PANEL_TEXT)


def _seat_text(state: Any) -> str:
    """A watcher of a game between two computer opponents holds no seat (AR-09)."""
    view = state.view or {}
    if view.get("spectator"):
        return "watching, computer against computer"
    return state.seat or "waiting"


def _actor_text(state: Any) -> str:
    view = state.view or {}
    sides = (state.scenario or {}).get("players", [])
    name = sides[state.active] if 0 <= state.active < len(sides) else f"side {state.active}"
    if view.get("spectator"):
        return name
    return "you" if state.active == state.player else name


def _matching(legal: Sequence[dict[str, Any]], filter_text: str) -> list[tuple[int, dict[str, Any]]]:
    rows = list(enumerate(legal))
    if not filter_text:
        return rows
    needle = filter_text.lower()
    return [(i, c) for i, c in rows if needle in describe(c).lower()]


def describe(command: dict[str, Any]) -> str:
    """One line for one command, from its payload and nothing else."""
    payload = command.get("payload", command)
    parts = [str(payload.get("action", "?"))]
    if payload.get("units"):
        parts.append("u" + ",".join(str(u) for u in payload["units"]))
    if payload.get("hex"):
        parts.append(str(payload["hex"]))
    if payload.get("weapon") is not None:
        parts.append(f"w{payload['weapon']}")
    for key in ("facing", "aim", "ammo", "armament", "vehicle"):
        if payload.get(key) is not None:
            parts.append(f"{key}={payload[key]}")
    return " ".join(parts)


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
