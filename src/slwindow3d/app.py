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

Move around:

- a mouse drag, or the four arrow keys: pan the target
- the wheel, or the plus and minus keys: zoom (dolly in 3D, film size in 2D)
- a right drag, or the bracket keys: tilt and turn (3D only)
- r: reset the view
- i: show or hide the tactical overlay (the shaded hexes, the tracers, the bursts)
- o: show or hide the options of the unit in focus (where it can move, what it can fire at)

Play, the same as the 2D window:

- a click on a hex: put the top unit of the hex in focus, and a second click takes the
  next unit of the stack. With no click the focus is the unit that acted last.
- the pointer over a hex: the line of sight from the focus unit to that hex, as shaded
  hexes, from the answer of the host (FR-34). The hex under the pointer comes from a ray
  through the lens against the flat tops of the hexes (`mesh.hex_on_ray`).
- Escape: clear the focus. q: leave.

The window opens on Windows and on Unix, because Panda3D ships a wheel for each. A test or a
screenshot uses the offscreen path (`render_screenshot`), which needs no display.
"""

from __future__ import annotations

import math
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


class Board3DApp(ShowBase):
    """The 3D board window. Build it with a board document; feed it view documents."""

    def __init__(self, board_doc: dict[str, Any] | None = None, poll: Any = None, ask_los: Any = None) -> None:
        super().__init__()
        self.setBackgroundColor(*BACKGROUND)
        self.disableMouse()
        self.board_node: NodePath | None = None
        self.counter_root: NodePath | None = None
        self.indicator_root: NodePath | None = None
        self.indicators: Indicators | None = None
        self.board_doc: dict[str, Any] | None = None
        self._poll = poll
        # The overlay asks the host for a line of sight through this (FR-34, AR-06).
        self._ask_los = ask_los
        self._last_frame_id = None
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
        self._bind_keys()
        self._add_help_line()
        self.taskMgr.add(self._camera_task, "camera-task")
        if self._poll is not None:
            self.taskMgr.add(self._poll_task, "poll-task")

    def _add_help_line(self) -> None:
        """A small line at the bottom of the window that names the overlay keys, so a watcher
        finds the `i` and `o` toggles without the manual. It never raises."""
        try:
            from direct.gui.OnscreenText import OnscreenText

            OnscreenText(
                text="click focus  esc clear  t 2D/3D  drag pan  wheel zoom  r reset  i overlay  o options  q quit",
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
        self.accept("t", self.toggle_mode)
        self.accept("tab", self.toggle_mode)
        self.accept("r", self.reset_view)
        self.accept("arrow_left", self._pan, [-PAN_STEP, 0])
        self.accept("arrow_left-repeat", self._pan, [-PAN_STEP, 0])
        self.accept("arrow_right", self._pan, [PAN_STEP, 0])
        self.accept("arrow_right-repeat", self._pan, [PAN_STEP, 0])
        self.accept("arrow_up", self._pan, [0, PAN_STEP])
        self.accept("arrow_up-repeat", self._pan, [0, PAN_STEP])
        self.accept("arrow_down", self._pan, [0, -PAN_STEP])
        self.accept("arrow_down-repeat", self._pan, [0, -PAN_STEP])
        for key in ("+", "="):
            self.accept(key, self._zoom, [ZOOM_OUT])
        self.accept("-", self._zoom, [ZOOM_IN])
        self.accept("wheel_up", self._zoom, [ZOOM_OUT])
        self.accept("wheel_down", self._zoom, [ZOOM_IN])
        self.accept("[", self._tilt, [-TILT_STEP])
        self.accept("[-repeat", self._tilt, [-TILT_STEP])
        self.accept("]", self._tilt, [TILT_STEP])
        self.accept("]-repeat", self._tilt, [TILT_STEP])
        self.accept("i", self._toggle_indicators)
        self.accept("o", self._toggle_options)
        self.accept("q", self.userExit)
        self.accept("escape", self.clear_focus)
        for button in ("mouse1", "mouse3"):
            self.accept(button, self._drag_start, [button])
            self.accept(f"{button}-up", self._drag_stop, [button])

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

    # -------------------------------------------------------------------- the focus

    def clear_focus(self) -> None:
        """Escape: the focus goes back to the unit that acted last."""
        self.pinned = None

    def click(self, hex_id: str | None) -> None:
        """A click on a hex puts its top unit in focus, and a second click the next one.
        The choice is `overlay.next_focus`, the same as the 2D window."""
        view = getattr(self._snapshot, "view", None)
        self.pinned = next_focus(view, hex_id, self.pinned)

    def hex_under_pointer(self) -> str | None:
        """The hex the pointer is on: a ray through the lens against the hex tops."""
        if self.board_doc is None or not self.mouseWatcherNode.hasMouse():
            return None
        near, far = Point3(), Point3()
        pointer = Point2(self.mouseWatcherNode.getMouseX(), self.mouseWatcherNode.getMouseY())
        if not self.camLens.extrude(pointer, near, far):
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
        self._drag_button = button
        self._dragged = 0.0
        if self.mouseWatcherNode.hasMouse():
            self._drag_from = (self.mouseWatcherNode.getMouseX(), self.mouseWatcherNode.getMouseY())

    def _drag_stop(self, button: str) -> None:
        if self._drag_button != button:
            return
        self._drag_button = None
        # A press that did not move the pointer is a click, and a click picks a unit. The
        # pointer hex of this frame is the hex the press was on, and the panel on the right
        # is not on the board, so a click there picks nothing.
        if button == "mouse1" and self._dragged <= CLICK_SLOP:
            self.click(self.hex_under_pointer())

    def _camera_task(self, task: Any) -> int:
        self._apply_drag()
        self._place_camera()
        self.pointer_hex = None if self._drag_button is not None else self.hex_under_pointer()
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
        if self._drag_button is None or not self.mouseWatcherNode.hasMouse():
            return
        x = self.mouseWatcherNode.getMouseX()
        y = self.mouseWatcherNode.getMouseY()
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
        """Read a snapshot from the host client and rebuild the counters when it changes."""
        snapshot = self._poll()
        if snapshot is None:
            return task.cont
        self._snapshot = snapshot
        board = snapshot.board
        view = snapshot.view
        frame_id = snapshot.frame_id
        if board is not None and self.board_doc is None:
            self.set_board(board)
        if frame_id != self._last_frame_id:
            self._last_frame_id = frame_id
            # The board does not change during a game, so keep the one that is built and
            # update only the counters. A rebuild would draw the 2D board texture again,
            # which is slow and needless once a game is running.
            self.load_view(None, view)
            self._update_hud(snapshot)
        # The tactical overlay reads each snapshot, because the pointer moves, a line of
        # sight answer arrives, and a mark expires between two frames of the host. It
        # redraws only when its model changed, and it never raises.
        if self.indicators is not None:
            self.indicators.pinned = self.pinned
            self.indicators.pointer_hex = self.pointer_hex
            self.indicators.update(snapshot)
        return task.cont

    def _update_hud(self, snapshot: Any) -> None:
        """Draw the side panel of the pygame window (scenario, turn, phase, log, commands) to
        a texture and show it on the right of the 3D window, so the 3D view has the same play
        status the 2D window has. It reuses `slwindow.panel`, so there is one panel drawing."""
        from direct.gui.OnscreenImage import OnscreenImage
        from panda3d.core import TransparencyAttrib

        from slwindow import panel
        from slwindow3d.counters import _ensure_pygame, _surface_to_texture

        pygame = _ensure_pygame()
        win_w = self.win.getXSize() or 1500
        win_h = self.win.getYSize() or 950
        panel_w = 360
        if self._panel_font is None:
            self._panel_font = pygame.font.SysFont("dejavusans,arial,helvetica", 15)
            self._panel_small = pygame.font.SysFont("dejavusansmono,consolas,couriernew", 12)
        surface = pygame.Surface((panel_w, win_h))
        rect = pygame.Rect(0, 0, panel_w, win_h)
        try:
            panel.draw_panel(surface, rect, snapshot, self._panel_font, self._panel_small, -1, "")
        except Exception:
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
        app = cls(board_doc)
        app.mode = mode
        # Frame the whole board, but from a lower angle and a closer distance than a top-down
        # shot, so the height of a hill reads from the side of the board.
        app.distance = app.span * 1.2
        if mode == MODE_3D:
            app.pitch = -40.0
        if view_doc is not None:
            app.load_view(board_doc, view_doc)
        app._place_camera()
        for _ in range(max(1, frames)):
            app.graphicsEngine.renderFrame()
        app.win.saveScreenshot(Filename.fromOsSpecific(path))
        return path
