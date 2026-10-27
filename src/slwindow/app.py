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
  at, and the track it moved on, and the command list narrows to the commands of that
  unit. With no click the focus is the unit that acted last, so a game of two computer
  opponents shows the options of the unit that plays.
- a click on a shaded hex of the unit in focus: the list narrows to the commands of the
  unit that name that hex, and when one is left the window plays it (slice 8)
- the pointer over a hex: the line of sight from the focus unit to that hex, as shaded
  hexes. The host answers the question (FR-34), and the window has no LOS geometry.
- a click on a vehicle: shade the wedge of its covered arc (rule 29.4)
- the options of a unit of the person's side in focus, from the host (`options_request`,
  `slhost.options`): in the Movement Phase the pale blue hexes that the unit, or a vehicle,
  can get to with its remaining movement factors, and in a fire phase the hexes in its
  range (orange) and in its long range (pale orange) with a clear line of sight. A click on
  a pale blue hex moves the unit there by the path of lowest cost (`move_to`), one legal
  step at a time.
- Tab and Shift and Tab: move down and up the command list by one row, and the two page
  keys by one page. The wheel over the list scrolls it. The list scrolls, so each legal
  command has a row (H7).
- Enter, or a click on a row of the list: play that command
- typing: narrow the list. Escape clears what was typed, then the board choice, then the
  focus.
- a right click on a unit, or Ctrl and Space with a unit in focus: the menu of the unit
  (`slwindow.unitmenu`), with its commands of this phase in groups, the commands of the
  side, About this unit, and Undo. A click on a row chooses it. Escape, a click off the
  menu, or a right click closes it.
- the Undo button of the panel, or Ctrl and z: ask the host to take back the last command
- the set up tray (`slwindow.traydraw`, `slwindow.traycontrol`, the same as in the 3D
  window): while the side of the person sets up, a click on a counter of the tray shades
  the hexes where it can go, and a click on one places it. A drag of a counter from the
  tray or the board to a shaded hex places it too. A click on a placed counter takes it
  back to the tray. The tray says why a hex refused a counter. A right click on a counter
  in the set up opens the "about this unit" box.
- Ctrl and a: ask the host to set up the side of this person ("set up for me")
- the "Victory conditions" button of the panel, or Ctrl and v: the box of the victory
  conditions (`slwindow.victorytext`) and the strong violet of their hexes. The violet
  hexes are always on the map; a hex that the person's side controls is green.
- the end of the game: a box says "You won." or "You lost." (`slwindow.endgame`), until
  Escape or a click. The panel gives the turn and the turns that are left.
- Ctrl and s: write a picture of the window to the watch directory
- Ctrl and f, or the Home key: fit the whole board in the window
- Ctrl and q, or the close button: leave

The keys follow one policy (H7, `slwindow.choice`). For a person who holds a seat a plain
letter or digit always goes to the filter, so a shortcut never takes a letter of the
filter. With Ctrl a letter is always its shortcut. A watcher types no filter, so for a
watcher the plain letters s, f, and q are shortcuts too. The plus and the minus keys zoom
while the filter is empty, and they go to the filter after a letter.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pygame

from slwindow import boxes, counters, endgame, marks, panel, render, theme, traydraw, unitmenu, victorytext
from slwindow import setup as setup_model
from slwindow.choice import Chooser, is_watcher
from slwindow.client import HostClient
from slwindow.layout import Camera, fit, hex_at
from slwindow.traycontrol import SetupTrayControl
from slwindow.overlay import Tracker, hexes_of, next_focus, position_of, unit_ids, units_in

TITLE = "Squad Leader Expeditionem"
DEFAULT_SIZE = (1400, 860)
FRAMES_EACH_SECOND = 30
PAN_STEP = 60.0
ZOOM_IN = 1.12
ZOOM_OUT = 1 / ZOOM_IN
# A press that moves the pointer less than this is a click and not a drag.
DRAG_SLOP = 4
# The picture of a dragged counter of the set up, and its place up and to the right of the
# pointer, so the marked hex under the pointer stays in view.
CARRY_SIZE = 56
CARRY_GAP = 14
WATCH_DIRECTORY = "SQUAD_LEADER_WATCH_DIR"
DEFAULT_WATCH = Path("background") / "watch"


@dataclass
class WindowState:
    camera: Camera = field(default_factory=Camera)
    selected_hex: str | None = None
    fitted: bool = False
    arc_for: int | None = None
    # The unit a person put in focus with a click, or None for the unit that acted last.
    pinned: int | None = None
    pointer_hex: str | None = None
    shots: int = 0
    dragging: bool = False
    drag_from: tuple[int, int] = (0, 0)
    dragged: int = 0
    # The menu of a unit (`slwindow.unitmenu`): the unit, the pixel it opened at, and the
    # rectangle and the rows of the box in the last frame.
    menu_unit: int | None = None
    menu_at: tuple[int, int] = (0, 0)
    menu_rect: pygame.Rect | None = None
    menu_hits: list = field(default_factory=list)
    # The unit of the "about this unit" box, and the rectangle of the box.
    about_unit: int | None = None
    about_rect: pygame.Rect | None = None
    # The box of the end of the game, and whether the person closed it.
    end_rect: pygame.Rect | None = None
    end_closed: bool = False
    # The "Victory conditions" button: the box and the strong tones of the objective hexes.
    show_objectives: bool = False


def watch_directory() -> Path:
    """SR-07 keeps pictures out of the tree, so a screen shot goes outside it."""
    named = os.environ.get(WATCH_DIRECTORY)
    return Path(named) if named else DEFAULT_WATCH


class Window(SetupTrayControl):
    """The window and its loop. `step` runs one frame, so a test can drive it headless."""

    def __init__(self, client: HostClient, size: tuple[int, int] = DEFAULT_SIZE, caption: str = TITLE) -> None:
        pygame.init()
        pygame.display.set_caption(caption)
        self.surface = pygame.display.set_mode(size, pygame.RESIZABLE)
        self.clock = pygame.time.Clock()
        self.font = counters.system_font("dejavusans,arial,helvetica", 15)
        self.small = counters.system_font("dejavusansmono,consolas,couriernew", 12)
        self.client = client
        self.state = WindowState()
        # The command list: the filter, the board choice, the cursor, and the scroll.
        self.chooser = Chooser()
        self.rows: list[tuple[pygame.Rect, int]] = []
        self.running = True
        self.tracker = Tracker()
        self.overlay = self.tracker.update(None, 0.0)
        # The pairs the window asked the host about, so each question goes out one time.
        self.asked_los: set[tuple[str, str]] = set()
        # The (frame id, unit) pairs the window asked the options of, so each goes one time.
        self.asked_options: set[tuple[str, int]] = set()
        self._board_seen: dict[str, Any] | None = None
        self._session_seen = 0
        # The set up tray (`slwindow.traycontrol`): the snapshot of this frame, the hex that
        # refused a counter, a drop that waits for the host, the counter that a press
        # carries and the travel of the pointer, and the tray of the last frame.
        self._snapshot: Any = None
        self._last_frame_id = ""
        self.refusal: tuple[int, str] | None = None
        self._pending_drop: tuple[int, str] | None = None
        self._placed_last = False
        self._carry: int | None = None
        self._carry_moved = 0
        self._carry_at: tuple[int, int] = (0, 0)
        self._tray_hits: list[tuple[pygame.Rect, str, int | None]] = []
        self.tray_rect: pygame.Rect | None = None
        self._tray_height = 0

    # ------------------------------------------------------- what the tray reads

    @property
    def pinned(self) -> int | None:
        return self.state.pinned

    @pinned.setter
    def pinned(self, value: int | None) -> None:
        self.state.pinned = value

    def _view(self) -> dict[str, Any] | None:
        return getattr(self._snapshot, "view", None)

    def _legal(self) -> list[dict[str, Any]]:
        return list(getattr(self._snapshot, "legal", None) or [])

    def _end_carry(self) -> None:
        self._carry = None

    def auto_setup(self) -> None:
        self.client.send_auto_setup()

    def show_about(self, unit: dict[str, Any] | None) -> None:
        self.close_boxes()
        self.state.about_unit = None if unit is None else int(unit["id"])

    def begin_carry(self, unit_id: int, position: tuple[int, int]) -> None:
        """A press on a counter of the set up starts a drag of it. A release with no travel
        is a click."""
        self._carry = unit_id
        self._carry_moved = 0
        self._carry_at = position

    def frame_seen(self, snapshot: Any) -> None:
        """Take the snapshot of this frame. On a new frame, go on to the next identical
        counter after a placement, and place a counter that was dropped before the host took
        it off the board."""
        self._snapshot = snapshot
        frame_id = str(getattr(snapshot, "frame_id", "") or "")
        if frame_id != self._last_frame_id:
            self._last_frame_id = frame_id
            self._follow_identical()
            self._apply_pending_drop()

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
        self.chooser.sync(snapshot.frame_id, snapshot.legal)
        self.frame_seen(snapshot)
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
            if anchor[0] >= self.board_rect().width:
                # The wheel over the panel scrolls the command list.
                self.chooser.scroll_by(-3 if event.y > 0 else 3, snapshot.legal, snapshot.view)
                return
            factor = ZOOM_IN if event.y > 0 else ZOOM_OUT
            self.state.camera = self.state.camera.zoomed(factor, anchor)
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and self.press_setup(event.pos, snapshot):
            return
        if event.type == pygame.MOUSEBUTTONDOWN and event.button in (1, 2, 3):
            self.state.dragging = True
            self.state.drag_from = event.pos
            self.state.dragged = 0
            return
        if event.type == pygame.MOUSEMOTION:
            if self._carry is not None:
                self._carry_moved += abs(event.rel[0]) + abs(event.rel[1])
                self._carry_at = event.pos
                self.state.pointer_hex = self.hex_under(event.pos, snapshot)
                return
            if self.state.dragging:
                self.state.dragged += abs(event.rel[0]) + abs(event.rel[1])
                self.state.camera = self.state.camera.panned(event.rel[0], event.rel[1])
            else:
                self.state.pointer_hex = self.hex_under(event.pos, snapshot)
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self._carry is not None:
            if self._carry_moved > DRAG_SLOP:
                self.drop(self.hex_under(event.pos, snapshot))
            else:
                self._end_carry()
            return
        if event.type == pygame.MOUSEBUTTONUP and event.button in (1, 2, 3):
            was_drag = self.state.dragged > DRAG_SLOP
            self.state.dragging = False
            if was_drag:
                return
            if event.button == 1:
                # A press that did not move the pointer is a click, and a click picks.
                self.click(self.state.drag_from, snapshot)
            elif event.button == 3:
                self.right_click(self.state.drag_from, snapshot)
            return
        if event.type == pygame.KEYDOWN:
            self.key(event, snapshot)

    def press_setup(self, position: tuple[int, int], snapshot: Any) -> bool:
        """A press of the left button while the side sets up: a counter or a button of the
        tray, or a counter of the side on the board, which the press picks up. Return True
        when the press was for the set up."""
        self._snapshot = snapshot
        if not self.in_setup() or self.state.menu_unit is not None or self.state.about_unit is not None:
            return False
        rect = self.tray_rect
        if rect is not None and rect.collidepoint(position):
            point = (position[0] - rect.left, position[1] - rect.top)
            for hit, action, unit_id in self._tray_hits:
                if hit.collidepoint(point):
                    self.tray_action(action, unit_id)
                    if action == traydraw.ACTION_UNIT and unit_id is not None:
                        self.begin_carry(unit_id, position)
                    break
            # A press on the tray never reaches the board.
            return True
        grabbed = self._grab_on_board(self.hex_under(position, snapshot))
        if grabbed is not None:
            # A press on a counter of this side picks it up. A release on a shaded hex
            # places it again, and a release with no travel leaves it in the tray.
            self.lift(grabbed)
            self.begin_carry(grabbed, position)
            return True
        return False

    def click(self, position: tuple[int, int], snapshot: Any) -> None:
        self._snapshot = snapshot
        if self.state.end_rect is not None:
            # A click closes the box of the end of the game, and does nothing else.
            self.close_end()
            return
        if self.state.menu_unit is not None:
            # A click on a row of the menu chooses it, and a click off the menu closes it.
            self.click_menu(position, snapshot)
            return
        if self.state.about_unit is not None:
            self.close_boxes()
            return
        for row, index in self.rows:
            if row.collidepoint(position):
                if index == panel.UNDO_ROW:
                    self.client.send_undo()
                    return
                if index == panel.OBJECTIVES_ROW:
                    self.toggle_objectives()
                    return
                self.chooser.point_at(index, snapshot.legal, snapshot.view)
                self.send(index, snapshot)
                return
        if snapshot.board is None or position[0] >= self.board_rect().width:
            return
        if self.tray_rect is not None and self.tray_rect.collidepoint(position):
            return
        self.state.selected_hex = hex_at(snapshot.board, position[0], position[1], self.state.camera)
        self.state.arc_for = self.vehicle_in(snapshot, self.state.selected_hex)
        if self.in_setup() and self._setup_click(self.state.selected_hex):
            return
        self.board_choice(snapshot, self.state.selected_hex)

    # ------------------------------------------------------------- the unit menu

    def right_click(self, position: tuple[int, int], snapshot: Any) -> None:
        """A right click: close an open box, else open the menu of the unit under the
        pointer. In a stack the unit in focus comes first, else the top unit."""
        if self.state.menu_unit is not None or self.state.about_unit is not None:
            self.close_boxes()
            return
        self._snapshot = snapshot
        if self.in_setup():
            # In the set up a right click opens the box of a counter of the tray or the board.
            units = {int(u["id"]): u for u in (snapshot.view or {}).get("units", []) or []}
            rect = self.tray_rect
            if rect is not None and rect.collidepoint(position):
                point = (position[0] - rect.left, position[1] - rect.top)
                for hit, action, unit_id in self._tray_hits:
                    if action == traydraw.ACTION_UNIT and unit_id in units and hit.collidepoint(point):
                        self.show_about(units[unit_id])
                return
            stack = units_in(snapshot.view, self.hex_under(position, snapshot))
            if stack:
                ids = [int(u["id"]) for u in stack]
                self.show_about(units[self.state.pinned if self.state.pinned in ids else ids[0]])
            return
        stack = units_in(snapshot.view, self.hex_under(position, snapshot))
        if not stack:
            return
        ids = [int(u["id"]) for u in stack]
        self.open_menu(self.state.pinned if self.state.pinned in ids else ids[0], position, snapshot)

    def menu_key(self, snapshot: Any) -> None:
        """Ctrl and Space: the menu of the unit in focus, else of the unit under the pointer."""
        if self.state.menu_unit is not None:
            self.close_boxes()
            return
        units = {int(u["id"]) for u in (snapshot.view or {}).get("units", []) or []}
        if self.state.pinned is not None and self.state.pinned in units:
            self.open_menu(self.state.pinned, pygame.mouse.get_pos(), snapshot)
        else:
            self.right_click(pygame.mouse.get_pos(), snapshot)

    def open_menu(self, unit_id: int, position: tuple[int, int], snapshot: Any) -> None:
        """Open the menu of a unit, and put the unit in focus, so the overlay shades its
        options and the list shows its commands."""
        self.close_boxes()
        self.state.menu_unit = unit_id
        self.state.menu_at = position
        self.state.pinned = unit_id
        if any(unit_id in unit_ids(entry) for entry in snapshot.legal or []):
            self.chooser.unit = unit_id
            self.chooser.hex = None
            self.chooser.position = 0
            self.chooser.scroll = 0

    def menu_rows(self, snapshot: Any) -> list[unitmenu.MenuRow]:
        if self.state.menu_unit is None:
            return []
        answers = getattr(snapshot, "options", None) or {}
        return unitmenu.rows(
            snapshot.view,
            snapshot.legal,
            self.state.menu_unit,
            str(getattr(snapshot, "phase_text", "") or ""),
            answers.get(self.state.menu_unit),
            bool(getattr(snapshot, "can_undo", False)),
        )

    def click_menu(self, position: tuple[int, int], snapshot: Any) -> bool:
        """A click with the menu open: play a command row, open the box of the unit, or
        undo. A click off the menu closes it. Return True when the click chose a row."""
        rect = self.state.menu_rect
        unit_id = self.state.menu_unit
        hits = list(self.state.menu_hits)
        self.close_boxes()
        if rect is None or not rect.collidepoint(position):
            return False
        point = (position[0] - rect.left, position[1] - rect.top)
        for row_rect, row in hits:
            if not row_rect.collidepoint(point):
                continue
            if row.kind == unitmenu.ROW_COMMAND and row.index is not None:
                self.chooser.point_at(row.index, snapshot.legal, snapshot.view)
                self.send(row.index, snapshot)
            elif row.kind == unitmenu.ROW_ABOUT:
                self.state.about_unit = unit_id
            elif row.kind == unitmenu.ROW_UNDO:
                self.client.send_undo()
            return True
        return False

    def close_boxes(self) -> None:
        self.state.menu_unit = None
        self.state.menu_rect = None
        self.state.menu_hits = []
        self.state.about_unit = None
        self.state.about_rect = None

    def draw_boxes(self, snapshot: Any) -> None:
        """Draw the open menu next to the pointer where it opened, or the about box at the
        top left of the board. A unit that left the view closes its box."""
        units = {int(u["id"]): u for u in (snapshot.view or {}).get("units", []) or []}
        board = self.board_rect()
        if self.state.menu_unit is not None:
            if self.state.menu_unit not in units:
                self.close_boxes()
                return
            rows = self.menu_rows(snapshot)
            title = unitmenu.title(snapshot.view, self.state.menu_unit)
            height = min(boxes.menu_height(title, rows, self.font, self.small), board.height - 16)
            box = pygame.Surface((boxes.WIDTH, height), pygame.SRCALPHA)
            self.state.menu_hits = boxes.draw_menu(box, title, rows, self.font, self.small)
            left = max(8, min(self.state.menu_at[0] + 12, board.width - boxes.WIDTH - 8))
            top = max(8, min(self.state.menu_at[1] - 12, board.height - height - 8))
            self.surface.blit(box, (left, top))
            self.state.menu_rect = pygame.Rect(left, top, boxes.WIDTH, height)
        elif self.state.about_unit is not None:
            unit = units.get(self.state.about_unit)
            if unit is None:
                self.close_boxes()
                return
            height = boxes.about_height(unit, self.font, self.small, boxes.ABOUT_WIDTH, snapshot.view)
            box = pygame.Surface((boxes.ABOUT_WIDTH, height), pygame.SRCALPHA)
            boxes.draw_about(box, unit, self.font, self.small, snapshot.view)
            self.surface.blit(box, (16, 16))
            self.state.about_rect = pygame.Rect(16, 16, boxes.ABOUT_WIDTH, height)

    def toggle_objectives(self) -> None:
        """The "Victory conditions" button: show or hide the box and the strong tones."""
        self.state.show_objectives = not self.state.show_objectives

    def draw_objectives(self, snapshot: Any) -> None:
        """The box of the victory conditions at the top left of the board, while it is on."""
        if not self.state.show_objectives or self.state.about_unit is not None:
            return
        found = victorytext.lines(snapshot)
        board = self.board_rect()
        width = min(boxes.OBJECTIVES_WIDTH, board.width - 32)
        height = boxes.objectives_height(found, self.font, self.small, width)
        box = pygame.Surface((width, height), pygame.SRCALPHA)
        boxes.draw_objectives(box, found, self.font, self.small)
        self.surface.blit(box, (16, 16))

    def close_end(self) -> None:
        self.state.end_closed = True
        self.state.end_rect = None

    def draw_end(self, snapshot: Any) -> None:
        """The box of the end of the game, in the middle of the board, until the person
        closes it (`slwindow.endgame`)."""
        self.state.end_rect = None
        if not snapshot.game_over:
            # A game that is not over (a new game in this window) opens the box again at its end.
            self.state.end_closed = False
            return
        if not getattr(snapshot, "over", None) or self.state.end_closed:
            return
        found = endgame.summary(snapshot)
        board = self.board_rect()
        width = min(boxes.END_WIDTH, board.width - 16)
        height = boxes.end_height(found, self.font, self.small, width)
        box = pygame.Surface((width, height), pygame.SRCALPHA)
        boxes.draw_end(box, found, self.font, self.small)
        left = (board.width - width) // 2
        top = max(8, (board.height - height) // 2)
        self.surface.blit(box, (left, top))
        self.state.end_rect = pygame.Rect(left, top, width, height)

    def board_choice(self, snapshot: Any, hex_id: str | None) -> None:
        """A click on the board: pin a unit, or choose a shaded hex of the pinned unit.

        The rules are `Chooser.board_click`, the same in the 3D window. A hex is a choice
        only because a legal entry of the host names it (AR-06). A pale blue hex of the
        pinned unit is a `move_to` of the host.
        """
        if self.move_to(snapshot, hex_id):
            return
        picked = self.chooser.board_click(snapshot.view, snapshot.legal, hex_id, self.state.pinned, next_focus)
        self.state.pinned = picked.pinned
        if picked.send is not None:
            self.send(picked.send, snapshot)

    def move_to(self, snapshot: Any, hex_id: str | None) -> bool:
        """A click on a pale (reach) hex of the pinned unit: the host moves the unit there
        by the path of lowest cost, one legal step at a time. A hex of the next step stays
        a command of the legal list, so the chooser plays it. Return True when sent."""
        unit_id = self.state.pinned
        if hex_id is None or unit_id is None:
            return False
        answer = (getattr(snapshot, "options", None) or {}).get(unit_id)
        if not answer or answer.get("kind") != "move" or hex_id not in (answer.get("reach") or {}):
            return False
        for entry in snapshot.legal or []:
            if unit_id in unit_ids(entry) and hex_id in hexes_of(entry):
                return False
        return bool(self.client.send_move_to(str(snapshot.frame_id or ""), unit_id, hex_id))

    def hex_under(self, position: tuple[int, int], snapshot: Any) -> str | None:
        """The hex at a pixel of the board. The panel and the tray are on no hex."""
        if snapshot.board is None or position[0] >= self.board_rect().width:
            return None
        if self.tray_rect is not None and self.tray_rect.collidepoint(position):
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
        control = bool(event.mod & pygame.KMOD_CTRL)
        text = event.unicode if isinstance(getattr(event, "unicode", None), str) else ""
        typing = not is_watcher(snapshot) and not control
        legal, view = snapshot.legal, snapshot.view
        if control or not typing:
            if key == pygame.K_q:
                self.running = False
                return
            if key == pygame.K_s:
                self.save_picture(snapshot)
                return
            if key == pygame.K_f:
                self.fit_board(snapshot)
                return
            if key == pygame.K_z and control:
                self.client.send_undo()
                return
            if key == pygame.K_a and control:
                self.client.send_auto_setup()
                return
            if key == pygame.K_SPACE and control:
                self.menu_key(snapshot)
                return
            if key == pygame.K_v and control:
                self.toggle_objectives()
                return
        if key == pygame.K_ESCAPE:
            if self.state.end_rect is not None:
                self.close_end()
                return
            if self.state.show_objectives:
                self.toggle_objectives()
                return
            if self.state.menu_unit is not None or self.state.about_unit is not None:
                self.close_boxes()
                return
            cleared = self.chooser.escape()
            if cleared == "unit" or not cleared:
                self.state.pinned = None
            if not cleared:
                self.state.selected_hex = None
                self.state.arc_for = None
            return
        if key == pygame.K_BACKSPACE:
            self.chooser.backspace()
            return
        if key == pygame.K_HOME:
            self.fit_board(snapshot)
            return
        if not self.chooser.filter_text or not typing:
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
        if key == pygame.K_TAB:
            self.chooser.move(-1 if event.mod & pygame.KMOD_SHIFT else 1, legal, view)
            return
        if key == pygame.K_PAGEUP:
            self.chooser.page(-1, legal, view)
            return
        if key == pygame.K_PAGEDOWN:
            self.chooser.page(1, legal, view)
            return
        if key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            index = self.chooser.selected(legal, view)
            if index is not None:
                self.send(index, snapshot)
            return
        if typing and text and text.isprintable():
            if text == " " and not self.chooser.filter_text:
                # A space starts no filter.
                return
            self.chooser.type(text)

    def send(self, index: int, snapshot: Any = None) -> bool:
        """Send the command at this index of the legal list, with the frame token as it
        came from the host. An index the list does not hold sends nothing (AR-06)."""
        snapshot = snapshot if snapshot is not None else self._snapshot
        if snapshot is None or not snapshot.legal or index < 0 or index >= len(snapshot.legal) or not snapshot.frame_id:
            return False
        command = snapshot.legal[index]
        sent = bool(self.client.send_intent(snapshot.frame_id, str(command["id"])))
        if sent and str(command.get("action", "")) in setup_model.PLACE_ACTIONS:
            self._placed_last = True
        return sent

    # --------------------------------------------------------------------- the frame

    def board_rect(self) -> pygame.Rect:
        width, height = self.surface.get_size()
        return pygame.Rect(0, 0, max(1, width - panel.WIDTH), height)

    def board_centre(self) -> tuple[float, float]:
        rect = self.board_rect()
        return (rect.width / 2, rect.height / 2)

    def fit_board(self, snapshot: Any) -> None:
        """Fit the board in the part of the window that the panel and the tray leave."""
        if snapshot.board is None:
            return
        rect = self.board_rect()
        self.state.camera = fit(snapshot.board, rect.width, max(1, rect.height - self._tray_height))
        self.state.fitted = True

    def tray_size(self) -> tuple[int, int]:
        """The height of the tray and the size of a counter tile in this frame, or (0, 0)
        when the side of the person does not set up."""
        if not self.in_setup():
            return 0, 0
        rect = self.board_rect()
        return traydraw.tray_height(len(self.tray_items()), rect.width, rect.height)

    def draw_tray(self) -> None:
        """The tray along the bottom of the board, and the counter that a drag carries."""
        height, tile = self.tray_size()
        if height == 0:
            self.tray_rect = None
            self._tray_hits = []
            return
        rect = self.board_rect()
        view, legal = self._view(), self._legal()
        items = self.tray_items()
        tray = pygame.Surface((rect.width, height), pygame.SRCALPHA)
        labels = {item.unit_id: setup_model.item_label(view, legal, item) for item in items}
        hint = setup_model.hint(view, legal, self.state.pinned)
        finish = setup_model.can_finish(legal) is not None
        self._tray_hits = traydraw.draw_tray(
            tray, items, self.state.pinned, finish, self.font, self.small, tile, labels, hint, self.refusal_text()
        )
        top = rect.height - height
        self.surface.blit(tray, (0, top))
        self.tray_rect = pygame.Rect(0, top, rect.width, height)
        if self._carry is not None and self._carry_moved > DRAG_SLOP:
            units = {int(u["id"]): u for u in (view or {}).get("units", []) or []}
            picture = pygame.Surface((CARRY_SIZE, CARRY_SIZE), pygame.SRCALPHA)
            traydraw.draw_carried(picture, units.get(self._carry), self.small)
            self.surface.blit(picture, (self._carry_at[0] + CARRY_GAP, self._carry_at[1] - CARRY_GAP - CARRY_SIZE))

    def draw(self, snapshot: Any) -> None:
        self.frame_seen(snapshot)
        height, _tile = self.tray_size()
        if height != self._tray_height:
            # The tray came or went, so the board fits the space it leaves.
            self._tray_height = height
            self.state.fitted = False
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
            self.surface,
            side,
            snapshot,
            self.font,
            self.small,
            self.chooser.selected(snapshot.legal, snapshot.view),
            self.chooser.filter_text,
            self.chooser,
            undo_button=not is_watcher(snapshot),
            objectives_on=self.state.show_objectives,
        )
        self.draw_tray()
        self.draw_objectives(snapshot)
        self.draw_boxes(snapshot)
        self.draw_end(snapshot)

    def update_overlay(self, snapshot: Any):
        """The tactical overlay of this frame, and the line of sight questions it raises.

        The model comes from `slwindow.overlay`. Each pair of hexes it has no answer for
        goes to the host as one `los_request`, one time (FR-34, TC-40).
        """
        if snapshot.board is not self._board_seen:
            self._board_seen = snapshot.board
            self.tracker.reset()
            self.asked_los = set()
            self.asked_options = set()
        if snapshot.session != self._session_seen:
            # A new session (a reconnect) has no answer on the way for an old question.
            self._session_seen = snapshot.session
            self.asked_los = set()
            self.asked_options = set()
        options = getattr(snapshot, "options", None)
        overlay = self.tracker.update(
            snapshot,
            time.monotonic(),
            self.state.pinned,
            self.state.pointer_hex,
            snapshot.los,
            options,
            show_objectives=self.state.show_objectives,
        )
        for pair in overlay.los_wanted:
            # A question that the client held back goes again in a later frame.
            if pair not in self.asked_los and self.client.request_los(*pair) is not False:
                self.asked_los.add(pair)
        if options is not None:
            # The options of a unit change with each frame, so the window asks again in each
            # frame, one time (`slhost.options`).
            for unit in overlay.options_wanted:
                key = (str(snapshot.frame_id or ""), unit)
                if key not in self.asked_options and self.client.request_options(unit) is not False:
                    self.asked_options.add(key)
        return overlay

    def waiting(self, snapshot: Any) -> None:
        lines = [
            "waiting for the host",
            f"address {self.client.url}",
            snapshot.notice or ("connected" if snapshot.connected else "connecting"),
        ]
        if self.client.error is not None:
            lines.append("the window does not try again. Close it with Ctrl and q")
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
