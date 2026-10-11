"""The 3D window (a Panda3D consumer of the host protocol).

The window reads a board document and a view document from a `HostClient`, exactly the way
the pygame window does, and it holds no rule and no rule table (AR-06). It builds the board
as hex prisms (see `mesh.py`) and it puts a counter card on each hex top (see
`counters.py`).

Two camera modes:

- MODE_2D looks straight down through an orthographic lens, a flat plan of the board with
  no tilt.
- MODE_3D looks at the board through a perspective lens tilted about 55 degrees, so a hill
  stands up and a slope shades.

The `t` key or Tab toggles the two modes. The camera orbits a target point, which is the
centre of the board.

Ctrl and t toggles the two modes at any time. For a watcher the `t` key does it too, and
Tab does it while the frame has no legal list.

Move around:

- a mouse drag, or the four arrow keys: pan the target
- the wheel over the board, or the plus and minus keys: zoom (dolly in 3D, film size in 2D)
- a right drag, or the bracket keys: tilt and turn (3D only)
- Ctrl and r: reset the view
- Ctrl and i: show or hide the tactical overlay (the shaded hexes, the tracers, the bursts)
- Ctrl and o: show or hide the options of the unit in focus (where it can move, what it can
  fire at)
- Ctrl and m: sound on or off (`audio.py`; `--mute` starts with no audio library)

Before the game the window shows the scenario card (`briefing.py`), and the game starts
when the person presses Begin, Space, or Enter. Each fire has its animation by the weapon
and the army (`effects.py`), and each fire and move has its sound (`sounds.py`).

Play (H2), the same as the 2D window, through the same `HostClient` and `Chooser`:

- a click on a hex: put the top unit of the hex in focus, and a second click takes the
  next unit of the stack. The command list narrows to the commands of that unit, and the
  overlay shades where it can move and what it can fire at. With no click the focus is
  the unit that acted last.
- a click on a shaded hex of the unit in focus: the list narrows to the commands of the
  unit that name that hex, and when one is left the window plays it
- the pointer over a hex: the line of sight from the focus unit to that hex, as shaded
  hexes, from the answer of the host (FR-34). The hex under the pointer comes from a ray
  through the lens against the flat tops of the hexes (`mesh.hex_on_ray`).
- the panel on the right: a click on a row plays it, and the wheel over it scrolls it
- Tab and Shift and Tab: move down and up the list, and the two page keys by one page
- Enter: play the command under the cursor
- typing: narrow the list. Escape clears what was typed, then the board choice, then the
  focus.
- Ctrl and z: ask the host to take back the last command (undo)
- Ctrl and a: ask the host to set up the side of this person ("set up for me")
- Ctrl and q: leave

The keys follow the policy of `slwindow.choice` (H7): for a person who holds a seat a
plain letter goes to the filter, and with Ctrl a letter is always its shortcut. A watcher
types no filter, so for a watcher the plain letters t, r, i, o, and q are shortcuts too,
as they were before.

The window opens on Windows and on Unix, because Panda3D ships a wheel for each. A test or a
screenshot uses the offscreen path (`render_screenshot`), which needs no display.
"""

from __future__ import annotations

import math
import sys
from typing import Any

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    AmbientLight,
    DirectionalLight,
    Filename,
    NodePath,
    OrthographicLens,
    PerspectiveLens,
    Point2,
    Point3,
    TextNode,
    Vec3,
)

from slwindow.choice import Chooser, is_watcher
from slwindow.overlay import next_focus, position_of
from slwindow3d import counters as counter3d
from slwindow3d.indicators import Indicators
from slwindow3d.mesh import HEIGHT_PER_LEVEL, THICKNESS, build_board_geom, build_textured_board, hex_on_ray, hex_world

# The 2D board art is drawn to a texture of this pixel size, then mapped onto the hex tops.
# It is large, so the woods, the buildings, and the roads stay crisp when the camera is close.
BOARD_TEX_W = 2600
BOARD_TEX_H = 1600

MODE_2D = "2d"
MODE_3D = "3d"

BACKGROUND = (0.52, 0.58, 0.42, 1.0)
DEFAULT_PITCH = -55.0
FLAT_PITCH = -90.0
MIN_PITCH = -89.0
MAX_PITCH = -12.0
PAN_STEP = 3.0
ZOOM_IN = 1.12
ZOOM_OUT = 1.0 / ZOOM_IN
TILT_STEP = 4.0
MIN_DISTANCE = 8.0
MAX_DISTANCE = 900.0
DRAG_PAN = 0.06
DRAG_TILT = 0.25
# A press that moves the pointer less than this (in the -1 to 1 film space) is a click.
CLICK_SLOP = 0.01
# The width of the side panel in pixels.
PANEL_WIDTH = 360
# The plain letters that are shortcuts while the frame has no legal list.
WATCH_LETTERS = ("t", "r", "i", "o", "q")


class Board3DApp(ShowBase):
    """The 3D board window. Build it with a board document; feed it view documents."""

    def __init__(
        self,
        board_doc: dict[str, Any] | None = None,
        poll: Any = None,
        ask_los: Any = None,
        client: Any = None,
        briefing: dict[str, Any] | None = None,
        on_begin: Any = None,
        sound: bool = False,
        muted: bool = False,
    ) -> None:
        super().__init__()
        self.setBackgroundColor(*BACKGROUND)
        self.disableMouse()
        self.board_node: NodePath | None = None
        self.counter_root: NodePath | None = None
        self.indicator_root: NodePath | None = None
        self.indicators: Indicators | None = None
        self.board_doc: dict[str, Any] | None = None
        # The client of the host (`slwindow.client.HostClient`). The window reads its
        # snapshot, asks it for a line of sight, and sends an intent or an undo through it.
        self.client = client
        if client is not None:
            poll = poll or client.snapshot
            ask_los = ask_los or client.request_los
        self._poll = poll
        # The overlay asks the host for a line of sight through this (FR-34, AR-06).
        self._ask_los = ask_los
        self._last_frame_id = None
        self._session_seen = 0
        # The command list: the filter, the board choice, the cursor, and the scroll.
        self.chooser = Chooser()
        self._hud_key: Any = None
        self._hud_rows: list[tuple[Any, int]] = []
        self._hud_width = PANEL_WIDTH
        self._hud = None
        self._panel_font = None
        self._panel_small = None
        self.target = Vec3(0, 0, 0)
        self.span = 40.0
        self.distance = 80.0
        self.heading = 0.0
        self.pitch = DEFAULT_PITCH
        self.mode = MODE_3D
        self._drag_button = None
        self._drag_from = (0, 0)
        self._dragged = 0.0
        # The hex under the pointer, and the unit a person clicked (the pin of the focus).
        self.pointer_hex: str | None = None
        self.pinned: int | None = None
        self._snapshot: Any = None
        self._add_lights()
        if board_doc is not None:
            self.set_board(board_doc)
        # The sounds of fire and movement (see `audio.py`), when the window has audio.
        self.sound_board = None
        if sound:
            from slwindow3d.audio import SoundBoard

            self.sound_board = SoundBoard(self, muted=muted)
            self._hook_sound()
        self._bind_keys()
        self._add_help_line()
        # The scenario card before the game (see `briefing.py`). `on_begin` starts the game
        # when the person closes it; with no briefing the caller starts the game at once.
        self.briefing = None
        if briefing is not None:
            from slwindow3d.briefing import Briefing

            self.briefing = Briefing(self, briefing, on_begin or (lambda: None))
        self.taskMgr.add(self._camera_task, "camera-task")
        if self._poll is not None:
            self.taskMgr.add(self._poll_task, "poll-task")

    def _add_help_line(self) -> None:
        """A small line at the bottom of the window that names the overlay keys, so a watcher
        finds the `i` and `o` toggles without the manual. It never raises."""
        try:
            from direct.gui.OnscreenText import OnscreenText

            OnscreenText(
                text="click pick  enter play  tab list  type find  esc clear  ctrl+z undo  "
                "ctrl+t 2D/3D  ctrl+r reset  ctrl+i overlay  ctrl+o options  ctrl+m sound  ctrl+q quit",
                parent=self.a2dBottomLeft,
                pos=(0.02, 0.04),
                scale=0.035,
                fg=(1, 1, 1, 0.85),
                align=TextNode.ALeft,
                mayChange=False,
            )
        except Exception as error:
            print(f"indicators: help line skipped after an error: {error!r}")

    # ------------------------------------------------------------------ the scene

    def _add_lights(self) -> None:
        ambient = AmbientLight("ambient")
        ambient.setColor((0.5, 0.5, 0.52, 1))
        self.render.setLight(self.render.attachNewNode(ambient))
        directional = DirectionalLight("sun")
        directional.setColor((0.9, 0.88, 0.8, 1))
        sun = self.render.attachNewNode(directional)
        # From above at an angle, so a slope of a hill takes light on one side and shade on
        # the other.
        sun.setHpr(-35, -55, 0)
        self.render.setLight(sun)

    def _board_texture(self, board_doc: dict[str, Any]):
        """Draw the full 2D board (woods, buildings, roads, fields, grid) to one texture.

        This reuses `slwindow.render`, the same code the pygame window draws with, so the 3D
        board shows the same detail and there is no second board drawing to keep in step. The
        camera it returns maps a lattice point to a pixel, which the mesh turns into a texture
        coordinate for the top of each hex.
        """
        from slwindow import layout
        from slwindow import render as board2d
        from slwindow3d.counters import _ensure_pygame, _surface_to_texture

        pygame = _ensure_pygame()
        surface = pygame.Surface((BOARD_TEX_W, BOARD_TEX_H))
        camera = layout.fit(board_doc, BOARD_TEX_W, BOARD_TEX_H)
        font = pygame.font.SysFont("dejavusansmono,consolas,couriernew", 20)
        board2d.draw_board(surface, board_doc, camera, font)
        texture = _surface_to_texture(surface, f"board2d-{board_doc.get('name', 'board')}")
        return texture, camera

    def set_board(self, board_doc: dict[str, Any]) -> None:
        """Build (or rebuild) the board prisms and centre the camera on them."""
        if self.board_node is not None:
            self.board_node.removeNode()
        self.board_doc = board_doc
        texture, camera = self._board_texture(board_doc)
        self.board_node = build_textured_board(board_doc, camera, texture, BOARD_TEX_W, BOARD_TEX_H)
        self.board_node.reparentTo(self.render)
        if self.counter_root is not None:
            self.counter_root.removeNode()
        self.counter_root = self.render.attachNewNode("counters")
        # The tactical overlay hangs under its own root, so a shaded hex, a tracer, and a
        # burst read over the board and the counters (see `indicators.py`).
        if self.indicator_root is not None:
            self.indicator_root.removeNode()
        self.indicators = Indicators(self.render, ask_los=self._ask_los)
        self.indicator_root = self.indicators.root
        self.indicators.set_board(board_doc)
        self._hook_sound()
        self.pinned = None
        xs = [h["center"][0] for h in board_doc["hexes"]]
        ys = [hex_world(h["center"])[1] for h in board_doc["hexes"]]
        if xs and ys:
            mx = (min(xs) + max(xs)) / 2.0
            my = (min(ys) + max(ys)) / 2.0
            self.span = max(max(xs) - min(xs), max(ys) - min(ys)) or 40.0
            self.target = Vec3(mx, my, 0)
            self.distance = self.span * 1.2

    # ----------------------------------------------------------------- the counters

    def load_view(self, board_doc: dict[str, Any] | None, view_doc: dict[str, Any] | None) -> None:
        """Rebuild the counter cards from the units of a view document.

        A unit sits on the top of its hex, at the elevation z of that hex. Several units in
        one hex step to the side and up.
        """
        if board_doc is not None and board_doc is not self.board_doc:
            self.set_board(board_doc)
        if self.counter_root is None:
            self.counter_root = self.render.attachNewNode("counters")
        else:
            self.counter_root.node().removeAllChildren()
        if view_doc is None or self.board_doc is None:
            return
        tops = {
            h["id"]: (
                hex_world(h["center"]),
                int(h.get("elevation", 0) or 0) * HEIGHT_PER_LEVEL,
            )
            for h in self.board_doc["hexes"]
        }
        stacks: dict[str, list[dict[str, Any]]] = {}
        for unit in view_doc.get("units", []):
            # Rule 16.1: a unit the defender returned to its track stays at its end hex,
            # and the overlay puts a ghost on the track hex (`slwindow.overlay`).
            here = position_of(unit)
            if here is None or unit.get("carrier") is not None:
                continue
            stacks.setdefault(here, []).append(unit)
        for hex_id, units in stacks.items():
            placed = tops.get(hex_id)
            if placed is None:
                continue
            (wx, wy), top_z = placed
            units.sort(key=lambda u: (u.get("kind") != "vehicle", u.get("id")))
            for index, unit in enumerate(units):
                counter3d.add_counter(self.counter_root, unit, wx, wy, top_z, index)

    # ------------------------------------------------------------------ the camera

    def _bind_keys(self) -> None:
        self.accept("arrow_left", self._pan, [-PAN_STEP, 0])
        self.accept("arrow_left-repeat", self._pan, [-PAN_STEP, 0])
        self.accept("arrow_right", self._pan, [PAN_STEP, 0])
        self.accept("arrow_right-repeat", self._pan, [PAN_STEP, 0])
        self.accept("arrow_up", self._pan, [0, PAN_STEP])
        self.accept("arrow_up-repeat", self._pan, [0, PAN_STEP])
        self.accept("arrow_down", self._pan, [0, -PAN_STEP])
        self.accept("arrow_down-repeat", self._pan, [0, -PAN_STEP])
        for key in ("+", "=", "shift-+", "shift-="):
            self.accept(key, self._zoom_key, [ZOOM_OUT])
        self.accept("-", self._zoom_key, [ZOOM_IN])
        self.accept("wheel_up", self._wheel, [ZOOM_OUT, -3])
        self.accept("wheel_down", self._wheel, [ZOOM_IN, 3])
        self.accept("[", self._tilt, [-TILT_STEP])
        self.accept("[-repeat", self._tilt, [-TILT_STEP])
        self.accept("]", self._tilt, [TILT_STEP])
        self.accept("]-repeat", self._tilt, [TILT_STEP])
        # The shortcuts. With Ctrl they work at any time. A plain letter is a shortcut only
        # for a watcher, else it goes to the filter (`_keystroke`).
        shortcuts = {
            "t": self.toggle_mode,
            "r": self.reset_view,
            "i": self._toggle_indicators,
            "o": self._toggle_options,
            "m": self.toggle_sound,
            "q": self.userExit,
        }
        for letter, action in shortcuts.items():
            self.accept(f"control-{letter}", action)
            self.accept(letter, self._watch_key, [action])
        self.accept("control-z", self.undo)
        self.accept("control-a", self.auto_setup)
        self.accept("escape", self.escape)
        self.accept("tab", self._tab, [1])
        self.accept("shift-tab", self._tab, [-1])
        self.accept("page_down", self._page, [1])
        self.accept("page_up", self._page, [-1])
        self.accept("enter", self.play_selected)
        self.accept("backspace", self._backspace)
        self.accept("backspace-repeat", self._backspace)
        self.accept("keystroke", self._keystroke)
        for button in ("mouse1", "mouse3"):
            self.accept(button, self._drag_start, [button])
            self.accept(f"{button}-up", self._drag_stop, [button])
        throwers = getattr(self, "buttonThrowers", None) or []
        for thrower in throwers:
            # The typed characters come as one `keystroke` event each, for the filter.
            thrower.node().setKeystrokeEvent("keystroke")

    # ------------------------------------------------------------ the command list

    def _legal(self) -> list[dict[str, Any]]:
        return list(getattr(self._snapshot, "legal", None) or [])

    def _view(self) -> dict[str, Any] | None:
        return getattr(self._snapshot, "view", None)

    def _watcher(self) -> bool:
        return self._snapshot is None or is_watcher(self._snapshot)

    def _watch_key(self, action: Any) -> None:
        """A plain letter is a shortcut only for a watcher, who types no filter."""
        if self._watcher():
            action()

    def _keystroke(self, text: str) -> None:
        """A typed character goes to the filter of a person who holds a seat. The plus
        and the minus keys zoom while the filter is empty, so they go to it only after a
        letter."""
        if self._watcher() or not isinstance(text, str) or len(text) != 1 or not text.isprintable():
            return
        if text in "+=-" and not self.chooser.filter_text:
            return
        self.chooser.type(text)

    def _zoom_key(self, factor: float) -> None:
        if not self._watcher() and self.chooser.filter_text:
            return
        self._zoom(factor)

    def _wheel(self, factor: float, rows: int) -> None:
        """The wheel over the panel scrolls the list. Over the board it zooms."""
        if self.pointer_in_panel():
            self.chooser.scroll_by(rows, self._legal(), self._view())
            return
        self._zoom(factor)

    def _tab(self, step: int) -> None:
        """Tab moves the cursor of the list. With no legal list it toggles the mode, as it
        did for a watcher before."""
        if self._legal():
            self.chooser.move(step, self._legal(), self._view())
        elif step > 0:
            self.toggle_mode()

    def _page(self, step: int) -> None:
        self.chooser.page(step, self._legal(), self._view())

    def _backspace(self) -> None:
        self.chooser.backspace()

    def escape(self) -> None:
        """Escape clears the typed text, then the board choice, then the focus."""
        cleared = self.chooser.escape()
        if cleared == "unit" or not cleared:
            self.pinned = None

    def play_selected(self) -> bool:
        """Enter: play the command under the cursor."""
        index = self.chooser.selected(self._legal(), self._view())
        return False if index is None else self.send(index)

    def send(self, index: int) -> bool:
        """Send the command at this index of the legal list with the frame token as it
        came from the host (DR-04). An index the list does not hold sends nothing."""
        snapshot = self._snapshot
        legal = self._legal()
        if self.client is None or snapshot is None or not getattr(snapshot, "frame_id", ""):
            return False
        if index < 0 or index >= len(legal):
            return False
        return bool(self.client.send_intent(snapshot.frame_id, str(legal[index]["id"])))

    def undo(self) -> None:
        """Ctrl and z: ask the host to take back the last command of this side."""
        if self.client is not None:
            self.client.send_undo()

    def auto_setup(self) -> None:
        """Ctrl and a: ask the host to set up the side of this person."""
        if self.client is not None:
            self.client.send_auto_setup()

    def toggle_mode(self) -> None:
        self.mode = MODE_2D if self.mode == MODE_3D else MODE_3D

    def _toggle_indicators(self) -> None:
        """The `i` key shows or hides the whole tactical overlay."""
        if self.indicators is not None:
            self.indicators.toggle()

    def _toggle_options(self) -> None:
        """The `o` key shows or hides only the options overlay (where a unit can move or fire)."""
        if self.indicators is not None:
            self.indicators.toggle_options()

    def _hook_sound(self) -> None:
        """Give the new log lines of the overlay to the sound board (a new board makes a
        new overlay, so this runs again then)."""
        board = getattr(self, "sound_board", None)
        if board is not None and self.indicators is not None:
            self.indicators.on_new_events = board.on_events

    def toggle_sound(self) -> None:
        """Ctrl and m: sound on or off."""
        if self.sound_board is not None:
            self.sound_board.toggle_mute()

    # -------------------------------------------------------------------- the focus

    def clear_focus(self) -> None:
        """The focus goes back to the unit that acted last."""
        self.pinned = None

    def click(self, hex_id: str | None) -> None:
        """A click on a hex: pin a unit, or choose a shaded hex of the pinned unit.

        The rules are `Chooser.board_click`, the same in the 2D window: the top unit of
        the hex goes in focus and a second click takes the next one, and a hex that a legal
        entry of the pinned unit names is a choice. A hex is a choice only because the host
        named it (AR-06).
        """
        picked = self.chooser.board_click(self._view(), self._legal(), hex_id, self.pinned, next_focus)
        self.pinned = picked.pinned
        if picked.send is not None:
            self.send(picked.send)

    def _pointer(self) -> tuple[float, float] | None:
        watcher = getattr(self, "mouseWatcherNode", None)
        if watcher is None or not watcher.hasMouse():
            return None
        return (watcher.getMouseX(), watcher.getMouseY())

    def _window_size(self) -> tuple[int, int]:
        return (self.win.getXSize() or 1500, self.win.getYSize() or 950)

    def panel_point(self, pointer: tuple[float, float] | None = None) -> tuple[int, int] | None:
        """The pixel of the panel picture under the pointer, or None off the panel. The
        pointer is in the -1 to 1 space of the window."""
        pointer = pointer if pointer is not None else self._pointer()
        if pointer is None:
            return None
        width, height = self._window_size()
        px = (pointer[0] + 1.0) / 2.0 * width
        py = (1.0 - pointer[1]) / 2.0 * height
        left = width - self._hud_width
        if px < left:
            return None
        return (int(px - left), int(py))

    def pointer_in_panel(self) -> bool:
        return self.panel_point() is not None

    def click_panel(self, point: tuple[int, int]) -> bool:
        """A click on a row of the panel plays that command."""
        for row, index in self._hud_rows:
            if row.collidepoint(point):
                self.chooser.point_at(index, self._legal(), self._view())
                return self.send(index)
        return False

    def hex_under_pointer(self) -> str | None:
        """The hex the pointer is on: a ray through the lens against the hex tops. The
        panel is not on the board, so the pointer over it is on no hex."""
        pointer = self._pointer()
        if self.board_doc is None or pointer is None or self.panel_point(pointer) is not None:
            return None
        near, far = Point3(), Point3()
        if not self.camLens.extrude(Point2(*pointer), near, far):
            return None
        near_world = self.render.getRelativePoint(self.cam, near)
        far_world = self.render.getRelativePoint(self.cam, far)
        return hex_on_ray(self.board_doc, near_world, far_world)

    def reset_view(self) -> None:
        self.pitch = DEFAULT_PITCH
        self.heading = 0.0
        self.distance = self.span * 1.2

    def _pan(self, dx: float, dy: float) -> None:
        angle = math.radians(self.heading)
        # Pan in the plane of the board, along the heading of the camera.
        right = Vec3(math.cos(angle), math.sin(angle), 0)
        forward = Vec3(-math.sin(angle), math.cos(angle), 0)
        scale = self.distance * 0.02
        self.target = self.target + right * (dx * scale) + forward * (dy * scale)

    def _zoom(self, factor: float) -> None:
        self.distance = max(MIN_DISTANCE, min(MAX_DISTANCE, self.distance * factor))

    def _tilt(self, delta: float) -> None:
        if self.mode == MODE_3D:
            self.pitch = max(MIN_PITCH, min(MAX_PITCH, self.pitch + delta))

    def _drag_start(self, button: str) -> None:
        if getattr(self, "briefing", None) is not None and self.briefing.open:
            # The scenario card is over the board, and a press on it is for the card.
            return
        pointer = self._pointer()
        if button == "mouse1" and pointer is not None:
            point = self.panel_point(pointer)
            if point is not None:
                # A press on the panel is a click on a row and never a drag of the board.
                self.click_panel(point)
                return
        self._drag_button = button
        self._dragged = 0.0
        if pointer is not None:
            self._drag_from = pointer

    def _drag_stop(self, button: str) -> None:
        if self._drag_button != button:
            return
        self._drag_button = None
        # A press that did not move the pointer is a click, and a click picks a unit or a
        # hex. The pointer hex of this frame is the hex the press was on.
        if button == "mouse1" and self._dragged <= CLICK_SLOP:
            self.click(self.hex_under_pointer())

    def _camera_task(self, task: Any) -> int:
        self._apply_drag()
        self._place_camera()
        self.pointer_hex = None if self._drag_button is not None else self.hex_under_pointer()
        if self.indicators is not None:
            # An animation keeps its size on the screen as the camera zooms (`effects.py`).
            from slwindow3d.effects import zoom_for

            self.indicators.effects.zoom = zoom_for(self.distance)
            self.indicators.sweep()
        return task.cont

    def _place_camera(self) -> None:
        pitch = FLAT_PITCH if self.mode == MODE_2D else self.pitch
        if self.mode == MODE_2D:
            lens = OrthographicLens()
            film = max(1.0, self.distance)
            aspect = self.getAspectRatio() or 1.0
            lens.setFilmSize(film * aspect, film)
            lens.setNearFar(-2000, 2000)
        else:
            lens = PerspectiveLens()
            lens.setFov(45)
            lens.setNearFar(0.5, 4000)
        self.cam.node().setLens(lens)
        radians_h = math.radians(self.heading)
        radians_p = math.radians(pitch)
        # Place the camera on a sphere around the target, at the current heading and pitch.
        horizontal = math.cos(radians_p)
        offset = Vec3(
            math.sin(radians_h) * horizontal,
            -math.cos(radians_h) * horizontal,
            -math.sin(radians_p),
        )
        self.camera.setPos(self.target + offset * self.distance)
        self.camera.lookAt(self.target)

    def _apply_drag(self) -> None:
        pointer = self._pointer()
        if self._drag_button is None or pointer is None:
            return
        x, y = pointer
        dx = x - self._drag_from[0]
        dy = y - self._drag_from[1]
        self._drag_from = (x, y)
        self._dragged += abs(dx) + abs(dy)
        if self._drag_button == "mouse1":
            # Left drag pans the target across the board plane.
            self._pan(-dx * self.distance * DRAG_PAN, -dy * self.distance * DRAG_PAN)
        elif self._drag_button == "mouse3" and self.mode == MODE_3D:
            # Right drag turns and tilts the camera around the target.
            self.heading = (self.heading + dx * 120.0 * DRAG_TILT) % 360.0
            self.pitch = max(MIN_PITCH, min(MAX_PITCH, self.pitch - dy * 120.0 * DRAG_TILT))

    # -------------------------------------------------------------------- the poll

    def _poll_task(self, task: Any) -> int:
        """Read a snapshot from the host client, and draw what changed."""
        snapshot = self._poll()
        if snapshot is None:
            return task.cont
        self.show_snapshot(snapshot)
        return task.cont

    def show_snapshot(self, snapshot: Any) -> None:
        """Take one snapshot: the board, the counters, the list, the overlay, the panel."""
        self._snapshot = snapshot
        board = snapshot.board
        view = snapshot.view
        frame_id = snapshot.frame_id
        if board is not None and self.board_doc is None:
            self.set_board(board)
        self.chooser.sync(str(frame_id or ""), list(getattr(snapshot, "legal", None) or []))
        session = getattr(snapshot, "session", 0)
        if session != self._session_seen:
            # A new session (a reconnect) has no answer on the way for an old question.
            self._session_seen = session
            if self.indicators is not None:
                self.indicators.forget_questions()
        if frame_id != self._last_frame_id:
            self._last_frame_id = frame_id
            # The board does not change during a game, so keep the one that is built and
            # update only the counters. A rebuild would draw the 2D board texture again,
            # which is slow and needless once a game is running.
            self.load_view(None, view)
        # The panel draws again when anything it shows changed: a frame, the end of the
        # game, a notice, the status, the list cursor, the filter, or the log (H8).
        key = self.hud_key(snapshot)
        if key != self._hud_key:
            self._hud_key = key
            self._update_hud(snapshot)
        # The tactical overlay reads each snapshot, because the pointer moves, a line of
        # sight answer arrives, and a mark expires between two frames of the host. It
        # redraws only when its model changed, and it never raises.
        if self.indicators is not None:
            self.indicators.pinned = self.pinned
            self.indicators.pointer_hex = self.pointer_hex
            self.indicators.update(snapshot)

    def hud_key(self, snapshot: Any) -> tuple:
        """A value that changes when the panel must draw again."""
        log = list(getattr(snapshot, "log", None) or [])
        last = log[-1].get("seq", len(log)) if log else -1
        chooser = self.chooser
        return (
            getattr(snapshot, "frame_id", ""),
            getattr(snapshot, "frames", 0),
            getattr(snapshot, "game_over", False),
            tuple(sorted((getattr(snapshot, "over", None) or {}).keys())),
            getattr(snapshot, "notice", ""),
            getattr(snapshot, "status", ""),
            getattr(snapshot, "errors", 0),
            getattr(snapshot, "connected", False),
            getattr(snapshot, "reconnecting", False),
            len(log),
            last,
            chooser.filter_text,
            chooser.position,
            chooser.scroll,
            chooser.unit,
            chooser.hex,
            self._window_size(),
        )

    def _update_hud(self, snapshot: Any) -> None:
        """Draw the side panel of the pygame window (scenario, status, commands, log) to a
        texture and show it on the right of the 3D window. It reuses `slwindow.panel`, so
        there is one panel drawing, and it keeps the rows for a click."""
        from direct.gui.OnscreenImage import OnscreenImage
        from panda3d.core import TransparencyAttrib

        from slwindow import panel
        from slwindow3d.counters import _ensure_pygame, _surface_to_texture

        pygame = _ensure_pygame()
        win_w, win_h = self._window_size()
        panel_w = self._hud_width
        if self._panel_font is None:
            self._panel_font = pygame.font.SysFont("dejavusans,arial,helvetica", 15)
            self._panel_small = pygame.font.SysFont("dejavusansmono,consolas,couriernew", 12)
        surface = pygame.Surface((panel_w, win_h))
        rect = pygame.Rect(0, 0, panel_w, win_h)
        legal = list(getattr(snapshot, "legal", None) or [])
        try:
            self._hud_rows = panel.draw_panel(
                surface,
                rect,
                snapshot,
                self._panel_font,
                self._panel_small,
                self.chooser.selected(legal, snapshot.view),
                self.chooser.filter_text,
                self.chooser,
            )
        except Exception as exc:  # a panel bug must not end the game window
            print(f"the 3D panel was not drawn: {exc!r}", file=sys.stderr)
            return
        texture = _surface_to_texture(surface, "hud")
        if self._hud is not None:
            self._hud.destroy()
        aspect = self.getAspectRatio() or (win_w / win_h)
        half_w = aspect * (panel_w / win_w)
        self._hud = OnscreenImage(image=texture, parent=self.aspect2d)
        self._hud.setTransparency(TransparencyAttrib.MAlpha)
        self._hud.setScale(half_w, 1, 1.0)
        self._hud.setPos(aspect - half_w, 0, 0)

    # --------------------------------------------------------------- the offscreen

    @classmethod
    def render_screenshot(
        cls,
        board_doc: dict[str, Any],
        path: str,
        view_doc: dict[str, Any] | None = None,
        frames: int = 3,
        mode: str = MODE_3D,
    ) -> str:
        """Build the scene offscreen, render a few frames, and save a PNG.

        The caller sets `window-type offscreen` before it imports Panda3D, so this needs no
        display. It is the path a test and a `--screenshot` run take.
        """
        import builtins

        # Panda3D permits one ShowBase in a process, so a second picture reuses the window.
        existing = getattr(builtins, "base", None)
        app = existing if isinstance(existing, cls) else cls(board_doc)
        if app.board_doc is not board_doc:
            app.set_board(board_doc)
        app.load_view(board_doc, view_doc)
        app.mode = mode
        # Frame the whole board, but from a lower angle and a closer distance than a top-down
        # shot, so the height of a hill reads from the side of the board.
        app.distance = app.span * 1.2
        if mode == MODE_3D:
            app.pitch = -40.0
        app._place_camera()
        for _ in range(max(1, frames)):
            app.graphicsEngine.renderFrame()
        app.win.saveScreenshot(Filename.fromOsSpecific(path))
        return path
