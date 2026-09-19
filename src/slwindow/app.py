"""The desktop window (FR-30, FR-31) with a 2D game library and no browser.

The window opens on Windows and on Unix, because the library ships a wheel for each. It
draws the board document and the view document that the host sends, it lists the legal
commands of the frame, and it sends an intent when a person picks one. It applies no rule
and it holds no rule table (AR-06).

Move around the board:

- the wheel: change the size of the board about the pointer
- the plus and the minus keys: change the size about the middle of the window
- a drag with any mouse button: move the board
- the four arrow keys: move the board
- f or the Home key: fit the whole board in the window

Play:

- a click on a hex: put the top unit of the hex in focus, and a second click takes the
  next unit of the stack. The overlay shades where that unit can move, what it can fire
  at, and the track it moved on. With no click the focus is the unit that acted last, so
  a game of two computer opponents shows the options of the unit that plays.
- the pointer over a hex: the line of sight from the focus unit to that hex, as shaded
  hexes. The host answers the question (FR-34), and the window has no LOS geometry.
- a click on a vehicle: shade the wedge of its covered arc (rule 29.4)
- Tab and Shift and Tab, or the two page keys: move down and up the command list
- Enter, or a click on a row of the list: play that command
- typing: narrow the list, and Escape clears what was typed, then the focus
- s: write a picture of the window to the watch directory
- q or the close button: leave
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pygame

from slwindow import counters, marks, panel, render, theme
from slwindow.client import HostClient
from slwindow.layout import Camera, fit, hex_at
from slwindow.overlay import Tracker, next_focus, position_of

TITLE = "Squad Leader Expeditionem"
DEFAULT_SIZE = (1400, 860)
FRAMES_EACH_SECOND = 30
PAN_STEP = 60.0
ZOOM_IN = 1.12
ZOOM_OUT = 1 / ZOOM_IN
# A press that moves the pointer less than this is a click and not a drag.
DRAG_SLOP = 4
WATCH_DIRECTORY = "SQUAD_LEADER_WATCH_DIR"
DEFAULT_WATCH = Path("background") / "watch"


@dataclass
class WindowState:
    camera: Camera = field(default_factory=Camera)
    selected_hex: str | None = None
    selected_command: int = 0
    filter_text: str = ""
    fitted: bool = False
    arc_for: int | None = None
    # The unit a person put in focus with a click, or None for the unit that acted last.
    pinned: int | None = None
    pointer_hex: str | None = None
    shots: int = 0
    dragging: bool = False
    drag_from: tuple[int, int] = (0, 0)
    dragged: int = 0


def watch_directory() -> Path:
    """SR-07 keeps pictures out of the tree, so a screen shot goes outside it."""
    named = os.environ.get(WATCH_DIRECTORY)
    return Path(named) if named else DEFAULT_WATCH


class Window:
    """The window and its loop. `step` runs one frame, so a test can drive it headless."""

    def __init__(self, client: HostClient, size: tuple[int, int] = DEFAULT_SIZE, caption: str = TITLE) -> None:
        pygame.init()
        pygame.display.set_caption(caption)
        self.surface = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("dejavusans,arial,helvetica", 15)
        self.small = pygame.font.SysFont("dejavusansmono,consolas,couriernew", 12)
        self.client = client
        self.state = WindowState()
        self.rows: list[tuple[pygame.Rect, int]] = []
        self.running = True
        self.tracker = Tracker()
        self.overlay = self.tracker.update(None, 0.0)
        # The pairs the window asked the host about, so each question goes out one time.
        self.asked_los: set[tuple[str, str]] = set()
        self._board_seen: dict[str, Any] | None = None

    # ---------------------------------------------------------------------- the loop

    def run(self, limit: float | None = None) -> None:
        started = time.monotonic()
        while self.running:
            self.step()
            if limit is not None and time.monotonic() - started >= limit:
                break
        pygame.quit()

    def step(self) -> None:
        snapshot = self.client.snapshot()
        for event in pygame.event.get():
            self.handle(event, snapshot)
        self.draw(snapshot)
        pygame.display.flip()
        self.clock.tick(FRAMES_EACH_SECOND)

    # -------------------------------------------------------------------- the events

    def handle(self, event: pygame.event.Event, snapshot: Any) -> None:
        if event.type == pygame.QUIT:
            self.running = False
            return
        if event.type == pygame.VIDEORESIZE:
            self.surface = pygame.display.set_mode((event.w, event.h), pygame.RESIZABLE)
            self.state.fitted = False
            return
        if event.type == pygame.MOUSEWHEEL:
            anchor = pygame.mouse.get_pos()
            factor = ZOOM_IN if event.y > 0 else ZOOM_OUT
            self.state.camera = self.state.camera.zoomed(factor, anchor)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 2, 3):
            self.state.dragging = True
            self.state.drag_from = event.pos
            self.state.dragged = 0
            return
        if event.type == pygame.MOUSEMOTION:
            if self.state.dragging:
                self.state.dragged += abs(event.rel[0]) + abs(event.rel[1])
                self.state.camera = self.state.camera.panned(event.rel[0], event.rel[1])
            else:
                self.state.pointer_hex = self.hex_under(event.pos, snapshot)
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2, 3):
            was_drag = self.state.dragged > DRAG_SLOP
            self.state.dragging = False
            if event.button == 1 and not was_drag:
                # A press that did not move the pointer is a click, and a click picks.
                self.click(self.state.drag_from, snapshot)
            return
        if event.type == pygame.KEYDOWN:
            self.key(event, snapshot)

    def click(self, position: tuple[int, int], snapshot: Any) -> None:
        for row, index in self.rows:
            if row.collidepoint(position):
                self.state.selected_command = index
                self.send(index, snapshot)
                return
        if snapshot.board is None or position[0] >= self.board_rect().width:
            return
        self.state.selected_hex = hex_at(snapshot.board, position[0], position[1], self.state.camera)
        self.state.arc_for = self.vehicle_in(snapshot, self.state.selected_hex)
        self.state.pinned = self.next_in_focus(snapshot, self.state.selected_hex)

    def hex_under(self, position: tuple[int, int], snapshot: Any) -> str | None:
        if snapshot.board is None or position[0] >= self.board_rect().width:
            return None
        return hex_at(snapshot.board, position[0], position[1], self.state.camera)

    def next_in_focus(self, snapshot: Any, hex_id: str | None) -> int | None:
        """The unit a click puts in focus (`overlay.next_focus`, the same in 3D)."""
        return next_focus(snapshot.view, hex_id, self.state.pinned)

    @staticmethod
    def vehicle_in(snapshot: Any, hex_id: str | None) -> int | None:
        """Rule 29.4: a click on a vehicle shows the arc its gun covers."""
        if hex_id is None or snapshot.view is None:
            return None
        for unit in snapshot.view["units"]:
            if position_of(unit) == hex_id and unit["kind"] == "vehicle" and not unit.get("wreck"):
                return int(unit["id"])
        return None

    def key(self, event: pygame.event.Event, snapshot: Any) -> None:
        key = event.key
        if key == pygame.K_q and not self.state.filter_text:
            self.running = False
            return
        if key == pygame.K_ESCAPE and not self.state.filter_text:
            self.state.pinned = None
            self.state.selected_hex = None
            self.state.arc_for = None
            return
        if key == pygame.K_ESCAPE:
            self.state.filter_text = ""
            return
        if key == pygame.K_BACKSPACE:
            self.state.filter_text = self.state.filter_text[:-1]
            return
        if key in (pygame.K_f, pygame.K_HOME):
            self.fit_board(snapshot)
            return
        if key == pygame.K_s:
            self.save_picture(snapshot)
            return
        if key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
            self.state.camera = self.state.camera.zoomed(ZOOM_IN, self.board_centre())
            return
        if key in (pygame.K_MINUS, pygame.K_KP_MINUS):
            self.state.camera = self.state.camera.zoomed(ZOOM_OUT, self.board_centre())
            return
        if key == pygame.K_LEFT:
            self.state.camera = self.state.camera.panned(PAN_STEP, 0)
            return
        if key == pygame.K_RIGHT:
            self.state.camera = self.state.camera.panned(-PAN_STEP, 0)
            return
        if key == pygame.K_UP:
            self.state.camera = self.state.camera.panned(0, PAN_STEP)
            return
        if key == pygame.K_DOWN:
            self.state.camera = self.state.camera.panned(0, -PAN_STEP)
            return
        if key == pygame.K_PAGEUP or (key == pygame.K_TAB and event.mod & pygame.KMOD_SHIFT):
            self.state.selected_command = max(0, self.state.selected_command - 1)
            return
        if key in (pygame.K_PAGEDOWN, pygame.K_TAB):
            last = max(0, len(snapshot.legal) - 1)
            self.state.selected_command = min(last, self.state.selected_command + 1)
            return
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.send(self.state.selected_command, snapshot)
            return
        if event.unicode and event.unicode.isprintable() and key != pygame.K_TAB:
            self.state.filter_text += event.unicode

    def send(self, index: int, snapshot: Any) -> None:
        if not snapshot.legal or index >= len(snapshot.legal) or not snapshot.frame_id:
            return
        command = snapshot.legal[index]
        self.client.send_intent(snapshot.frame_id, str(command["id"]))

    # --------------------------------------------------------------------- the frame

    def board_rect(self) -> pygame.Rect:
        width, height = self.surface.get_size()
        return pygame.Rect(0, 0, max(1, width - panel.WIDTH), height)

    def board_centre(self) -> tuple[float, float]:
        rect = self.board_rect()
        return (rect.width / 2, rect.height / 2)

    def fit_board(self, snapshot: Any) -> None:
        if snapshot.board is None:
            return
        rect = self.board_rect()
        self.state.camera = fit(snapshot.board, rect.width, rect.height)
        self.state.fitted = True

    def draw(self, snapshot: Any) -> None:
        self.surface.fill(theme.PAPER)
        rect = self.board_rect()
        if snapshot.board is None:
            self.waiting(snapshot)
        else:
            if not self.state.fitted:
                self.fit_board(snapshot)
            board_surface = self.surface.subsurface(rect)
            render.draw_board(board_surface, snapshot.board, self.state.camera, self.small)
            self.overlay = self.update_overlay(snapshot)
            marks.draw_shades(board_surface, snapshot.board, self.state.camera, self.overlay)
            if snapshot.view is not None:
                counters.draw_counters(
                    board_surface,
                    snapshot.board,
                    snapshot.view,
                    self.state.camera,
                    self.font,
                    self.small,
                    self.state.arc_for,
                )
            marks.draw_marks(board_surface, snapshot.board, snapshot.view, self.state.camera, self.overlay, self.small)
        width, height = self.surface.get_size()
        side = pygame.Rect(width - panel.WIDTH, 0, panel.WIDTH, height)
        self.rows = panel.draw_panel(
            self.surface, side, snapshot, self.font, self.small, self.state.selected_command, self.state.filter_text
        )

    def update_overlay(self, snapshot: Any):
        """The tactical overlay of this frame, and the line of sight questions it raises.

        The model comes from `slwindow.overlay`. Each pair of hexes it has no answer for
        goes to the host as one `los_request`, one time (FR-34, TC-40).
        """
        if snapshot.board is not self._board_seen:
            self._board_seen = snapshot.board
            self.tracker.reset()
            self.asked_los = set()
        overlay = self.tracker.update(
            snapshot, time.monotonic(), self.state.pinned, self.state.pointer_hex, snapshot.los
        )
        for pair in overlay.los_wanted:
            if pair not in self.asked_los:
                self.asked_los.add(pair)
                self.client.request_los(*pair)
        return overlay

    def waiting(self, snapshot: Any) -> None:
        lines = [
            "waiting for the host",
            f"address {self.client.url}",
            snapshot.notice or ("connected" if snapshot.connected else "connecting"),
        ]
        y = 60
        for text in lines:
            label = self.font.render(text, True, theme.INK)
            self.surface.blit(label, (48, y))
            y += 28

    def save_picture(self, snapshot: Any) -> None:
        """SR-07: a picture of the board goes outside the repository."""
        directory = watch_directory()
        directory.mkdir(parents=True, exist_ok=True)
        self.state.shots += 1
        name = f"window-turn{snapshot.turn}-{self.state.shots:03d}.png"
        pygame.image.save(self.surface, str(directory / name))
