"""Tactical action indicators drawn over the 3D board.

The 3D window (see `app.py`) shows the board and the counters. This module adds the tactical
overlay a watcher wants: whose turn it is, where a unit can move and where it moved, who
fires at what, and the line of the fire. It reads the same snapshot the window already polls
from the host client (AR-06): the active player, the phase, the units of the view, the legal
command list, and the tail of the action log. It adds no rule and no rule table; it draws.

Two kinds of overlay:

- The action overlay is the newest events of the log. A fire draws a bright line from each
  firer to its target and a ring on the target coloured by the result. A move draws an arrow
  from the source hex to the destination and a ring on the destination. An action lingers for
  a short time (`ACTION_LINGER`) so it reads at speed, then a per-frame sweep removes it.
- The frame overlay rebuilds each frame from the current snapshot. It is the low-alpha active
  side markers under the acting player's units, and the toggleable options overlay: the
  destinations a unit can move to, or the targets a unit can fire at.

The colours of a result come from the event kinds the core emits (grep `src/slcore/rules/`):
an `eliminated` or a `broken` outcome is red, a pin or a failed morale check is orange, and no
effect is grey.

Robustness is the rule here: the live game must never crash because of an overlay bug. The
whole update runs inside a try/except that prints a short warning and returns, and every
rebuild clears its old nodes first, so a bug leaks no nodes and kills no window.
"""

from __future__ import annotations

import json
import time
from typing import Any

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    LineSegs,
    NodePath,
    TextNode,
    TransparencyAttrib,
)

from slwindow3d.mesh import HEIGHT_PER_LEVEL, hex_world

# How long an action (a fire or a move) stays on the board, in seconds. Long enough that the
# eye reads it while a computer-versus-computer game runs at speed.
ACTION_LINGER = 1.8

# The overlay floats a little above the top of the counters, so a line and a ring read over
# the board and the pieces and do not fight the counter art for the same pixels.
LIFT = 1.4
RING_LIFT = 0.25

# The radius of a hex highlight ring, in world units. A hex is two units across its short
# radius, so a ring near this size fills the hex and reads from far away.
RING_RADIUS = 1.7
RING_SEGMENTS = 28

# The colours. RGBA, each channel from zero to one.
COLOR_FIRE = (1.0, 0.9, 0.15, 1.0)
COLOR_RESULT_RED = (0.98, 0.18, 0.12, 0.95)
COLOR_RESULT_ORANGE = (1.0, 0.6, 0.08, 0.95)
COLOR_RESULT_GREY = (0.75, 0.75, 0.78, 0.85)
COLOR_MOVE = (0.3, 0.75, 1.0, 1.0)
COLOR_ACTIVE = (0.25, 1.0, 0.45, 0.5)
COLOR_OPTION_MOVE = (0.3, 0.75, 1.0, 0.42)
COLOR_OPTION_FIRE = (1.0, 0.9, 0.2, 0.42)

# The width of each kind of line, in WORLD units (not pixels). A pixel-wide line vanishes when
# the camera pulls back to show the whole board, so a line is a flat ribbon of real width that
# stays visible at any zoom.
WIDTH_FIRE = 0.55
WIDTH_MOVE = 0.6
WIDTH_OPTION = 0.28
# The width of the ring band of a highlight, in world units.
RING_BAND = 0.35
# Kept for callers; the value is no longer a pixel thickness.
THICK_FIRE = WIDTH_FIRE
THICK_MOVE = WIDTH_MOVE
THICK_OPTION = WIDTH_OPTION

# The high bin so the overlay draws after the board and the counters and reads over them.
OVERLAY_BIN = 60

# A move or a stack move that names one source and one destination.
_MOVE_EVENTS = {"move", "advance", "stack_move"}

# The result kinds that mean a unit is gone or broken (red), and the ones that mean it is only
# pinned or held (orange). Anything else after a fire is no effect (grey).
_RESULT_RED = {"eliminated", "broken", "weapon_eliminated", "berserk"}
_RESULT_ORANGE = {"malfunction", "abandon_weapon"}

# The command actions of the fire families and the move families, for the options overlay.
_FIRE_ACTIONS = {"group_add", "group_add_weapon", "group_fire", "ft_fire", "afv_fire", "afv_mg", "at_fire", "afv_attack", "cc_afv", "cc_attack"}
_MOVE_ACTIONS = {"move", "stack_move", "advance", "vehicle_move", "sewer_move"}


def result_color(kinds: set[str]) -> tuple[float, float, float, float]:
    """The colour of a fire target ring from the result kinds that follow the fire."""
    if kinds & _RESULT_RED:
        return COLOR_RESULT_RED
    if kinds & _RESULT_ORANGE:
        return COLOR_RESULT_ORANGE
    return COLOR_RESULT_GREY


class Indicators:
    """The tactical overlay of the 3D window.

    Build it with the parent `render` NodePath. Call `set_board` when the window builds a
    board, so the overlay can turn a hex id into a world point. Call `update` each frame from
    the poll task with the current snapshot; it draws the active side, the newest actions, and
    the options overlay. `sweep` removes an action that has lingered past its time.
    """

    def __init__(self, parent: NodePath) -> None:
        # One root for the whole overlay, so a single toggle hides all of it and a single
        # detach removes all of it. The action layer lingers; the frame layer rebuilds each
        # frame. They are separate children so a rebuild of one does not touch the other.
        self.root: NodePath = parent.attachNewNode("indicators")
        self.action_root: NodePath = self.root.attachNewNode("actions")
        self.frame_root: NodePath = self.root.attachNewNode("frame")
        self._style(self.root)
        self.enabled = True
        self.options = True
        self._tops: dict[str, tuple[float, float, float]] = {}
        # The host re-sends the last part of the log with every frame, and the client trims the
        # log to a fixed length, so a count of "how many events I have seen" is not reliable.
        # Instead each event that has become an action is remembered by its content, so a
        # re-sent event does not replay and a trimmed log does not lose the count.
        self._seen_keys: set[str] = set()
        # False until the first log is read. The first read seeds the seen set and draws nothing,
        # so the game does not replay its whole set-up as a burst of actions when a watcher joins.
        self._primed = False
        # The nodes of a lingering action and the time each one must go, so `sweep` removes it.
        self._active_nodes: list[tuple[float, NodePath]] = []

    # ------------------------------------------------------------------ setup

    def _style(self, node: NodePath) -> None:
        """Make the overlay read over the board: no light, alpha on, and a high fixed bin
        with the depth test off, so a line and a ring show even where a counter is in front."""
        node.setLightOff()
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.setBin("fixed", OVERLAY_BIN)
        node.setDepthTest(False)
        node.setDepthWrite(False)

    def set_board(self, board_doc: dict[str, Any] | None) -> None:
        """Build the hex id to world point map from the board document."""
        self._tops = {}
        # A new board is a new game, so forget the events of the last one.
        self._seen_keys = set()
        self._primed = False
        if not board_doc:
            return
        for hexagon in board_doc.get("hexes", []):
            wx, wy = hex_world(hexagon["center"])
            wz = int(hexagon.get("elevation", 0) or 0) * HEIGHT_PER_LEVEL
            self._tops[hexagon["id"]] = (wx, wy, wz)

    def _point(self, hex_id: Any) -> tuple[float, float, float] | None:
        """The world point at the top of a hex, lifted so the overlay floats over the pieces."""
        if hex_id is None:
            return None
        placed = self._tops.get(str(hex_id))
        if placed is None:
            return None
        return (placed[0], placed[1], placed[2] + LIFT)

    # ------------------------------------------------------------------ toggles

    def toggle(self) -> bool:
        """Show or hide the whole overlay. Return the new state."""
        self.enabled = not self.enabled
        if self.enabled:
            self.root.show()
        else:
            self.root.hide()
        return self.enabled

    def toggle_options(self) -> bool:
        """Show or hide only the options overlay. Return the new state."""
        self.options = not self.options
        return self.options

    def clear(self) -> None:
        """Remove every overlay node. The next update rebuilds from the snapshot."""
        self.action_root.node().removeAllChildren()
        self.frame_root.node().removeAllChildren()
        self._active_nodes = []

    # ------------------------------------------------------------------ the update

    def update(self, snapshot: Any) -> None:
        """Draw the overlay for the current snapshot. Never raise into the poll task.

        It reads the active player and the units, the legal list, and the tail of the log. It
        rebuilds the frame layer (active markers and options) each call, and it adds a
        lingering action for each new event of the log tail.
        """
        try:
            self._update(snapshot)
        except Exception as error:  # never let an overlay bug kill the game window
            print(f"indicators: skipped a frame after an error: {error!r}")

    def _update(self, snapshot: Any) -> None:
        if snapshot is None or not self._tops:
            return
        view = getattr(snapshot, "view", None) or {}
        units = view.get("units", []) if isinstance(view, dict) else []
        # A hex for each unit id, so a firer's hex comes from its id in a fire event member.
        unit_hex = {u.get("id"): u.get("hex") for u in units}
        active = getattr(snapshot, "active", -1)
        phase = str(getattr(snapshot, "phase", "") or "")
        legal = getattr(snapshot, "legal", []) or []
        log = getattr(snapshot, "log", []) or []

        self.frame_root.node().removeAllChildren()
        self._draw_active(units, active)
        if self.options:
            self._draw_options(legal, unit_hex, active, phase)
        self._ingest_log(log, unit_hex)

    def sweep(self) -> None:
        """Remove any lingering action that has passed its time. Call it each frame."""
        try:
            now = time.monotonic()
            kept: list[tuple[float, NodePath]] = []
            for expiry, node in self._active_nodes:
                if now >= expiry:
                    node.removeNode()
                else:
                    kept.append((expiry, node))
            self._active_nodes = kept
        except Exception as error:
            print(f"indicators: sweep skipped after an error: {error!r}")

    # ------------------------------------------------------------------ the active side

    def _draw_active(self, units: list[dict[str, Any]], active: Any) -> None:
        """A subtle low-alpha ring under each unit of the active player, so the watcher sees
        whose turn it is without the marker fighting the action for attention."""
        try:
            active_int = int(active)
        except (TypeError, ValueError):
            return
        drawn: set[str] = set()
        for unit in units:
            if unit.get("player") != active_int or unit.get("hex") is None:
                continue
            if unit.get("carrier") is not None:
                continue
            hex_id = str(unit.get("hex"))
            if hex_id in drawn:
                continue
            drawn.add(hex_id)
            point = self._point(hex_id)
            if point is not None:
                self._ring(self.frame_root, point, COLOR_ACTIVE, RING_RADIUS * 1.25, THICK_OPTION)

    # ------------------------------------------------------------------ the options

    def _draw_options(self, legal: list[dict[str, Any]], unit_hex: dict[Any, Any], active: Any, phase: str) -> None:
        """The faint overlay of what the active player can do this frame.

        In a phase with legal moves, a faint ring on each destination hex. In a phase with
        legal fire, a faint thin line from each firer to each target. It stays low-alpha, so
        the actual action (bright) stands out over it.
        """
        for command in legal:
            action = command.get("action")
            target = command.get("hex")
            if action in _MOVE_ACTIONS:
                point = self._point(target)
                if point is not None:
                    self._ring(self.frame_root, point, COLOR_OPTION_MOVE, RING_RADIUS, THICK_OPTION)
            elif action in _FIRE_ACTIONS:
                dst = self._point(target)
                if dst is None:
                    continue
                for uid in command.get("units", []):
                    src = self._point(unit_hex.get(uid))
                    if src is not None:
                        self._line(self.frame_root, src, dst, COLOR_OPTION_FIRE, THICK_OPTION)

    # ------------------------------------------------------------------ the log

    @staticmethod
    def _event_key(event: dict[str, Any]) -> str:
        """A content key of one event, so a re-sent event is not read as new."""
        return f"{event.get('rule_id')}|{event.get('kind')}|{json.dumps(event.get('data', {}), sort_keys=True, default=str)}"

    def _ingest_log(self, log: list[dict[str, Any]], unit_hex: dict[Any, Any]) -> None:
        """Turn the events that are new since the last frame into lingering actions.

        The host re-sends the last part of the log with each frame and the client trims the log
        to a fixed length, so a count of seen events is not reliable. An event becomes an action
        the first time its content is seen. The first read only seeds the seen set, so a watcher
        who joins mid-game does not see the whole past replayed at once.
        """
        keys = [self._event_key(event) for event in log]
        if not self._primed:
            self._seen_keys = set(keys)
            self._primed = True
            return
        new_events = [event for event, key in zip(log, keys) if key not in self._seen_keys]
        self._seen_keys.update(keys)
        if not new_events:
            return
        # A fire event and the result events that follow it in the same batch are one action:
        # the result colours the target ring. Walk the new tail and group each fire with the
        # results that come after it until the next fire or move.
        i = 0
        n = len(new_events)
        while i < n:
            event = new_events[i]
            kind = event.get("kind")
            if kind == "fire":
                following: set[str] = set()
                j = i + 1
                while j < n and new_events[j].get("kind") not in {"fire"} | _MOVE_EVENTS:
                    following.add(str(new_events[j].get("kind")))
                    j += 1
                self._add_fire(event, unit_hex, following)
                i = j
            elif kind in _MOVE_EVENTS:
                self._add_move(event)
                i += 1
            else:
                i += 1

    def _add_fire(self, event: dict[str, Any], unit_hex: dict[Any, Any], following: set[str]) -> None:
        """A bright fire line from each firer to the target, and a result ring on the target."""
        data = event.get("data", {})
        target = self._point(data.get("target"))
        if target is None:
            return
        node = self.action_root.attachNewNode("fire")
        members = data.get("members", [])
        for member in members:
            src = self._point(unit_hex.get(member.get("unit")))
            if src is not None:
                self._line(node, src, target, COLOR_FIRE, THICK_FIRE)
        self._ring(node, target, result_color(following), RING_RADIUS, THICK_FIRE)
        phase = data.get("phase")
        if phase:
            self._label(node, target, str(phase))
        self._active_nodes.append((time.monotonic() + ACTION_LINGER, node))

    def _add_move(self, event: dict[str, Any]) -> None:
        """An arrow from the source hex to the destination, and a ring on the destination."""
        data = event.get("data", {})
        src = self._point(data.get("from"))
        dst = self._point(data.get("to"))
        if src is None or dst is None:
            return
        node = self.action_root.attachNewNode("move")
        self._arrow(node, src, dst, COLOR_MOVE, THICK_MOVE)
        self._ring(node, dst, COLOR_MOVE, RING_RADIUS, THICK_MOVE)
        self._active_nodes.append((time.monotonic() + ACTION_LINGER, node))

    # ------------------------------------------------------------------ the drawing

    def _quad(self, parent: NodePath, corners, color) -> NodePath:
        """A flat two-triangle quad from four world corners, in one flat colour. World-space,
        so it stays the same size on the board and reads when the camera shows the whole map."""
        vdata = GeomVertexData("quad", GeomVertexFormat.getV3c4(), Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        cwriter = GeomVertexWriter(vdata, "color")
        for corner in corners:
            vertex.addData3(*corner)
            cwriter.addData4(*color)
        tris = GeomTriangles(Geom.UHStatic)
        tris.addVertices(0, 1, 2)
        tris.addVertices(0, 2, 3)
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("quad")
        node.addGeom(geom)
        return parent.attachNewNode(node)

    def _ribbon(self, parent: NodePath, a, b, color, width: float) -> NodePath:
        """A flat band of world `width` from a to b, on the plane between them."""
        import math

        ax, ay, az = a
        bx, by, bz = b
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy) or 0.001
        px = -dy / length * (width / 2.0)
        py = dx / length * (width / 2.0)
        corners = [
            (ax + px, ay + py, az),
            (ax - px, ay - py, az),
            (bx - px, by - py, bz),
            (bx + px, by + py, bz),
        ]
        return self._quad(parent, corners, color)

    def _line(self, parent: NodePath, a, b, color, width: float) -> NodePath:
        """A fire line, as a world-width ribbon so it reads at any zoom."""
        return self._ribbon(parent, a, b, color, width)

    def _arrow(self, parent: NodePath, a, b, color, width: float) -> NodePath:
        """A ribbon from a to b with a solid arrowhead at b."""
        import math

        node = parent.attachNewNode("arrow")
        ax, ay, az = a
        bx, by, bz = b
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy) or 0.001
        ux, uy = dx / length, dy / length
        head = min(1.8, length * 0.4)
        shaft_x, shaft_y = bx - ux * head, by - uy * head
        self._ribbon(node, a, (shaft_x, shaft_y, bz), color, width)
        half = width * 1.9
        left = (shaft_x - uy * half, shaft_y + ux * half, bz)
        right = (shaft_x + uy * half, shaft_y - ux * half, bz)
        # The head is a triangle (a degenerate quad, the tip repeated).
        self._quad(node, [(bx, by, bz), left, right, (bx, by, bz)], color)
        return node

    def _ring(self, parent: NodePath, center, color, radius: float, width: float) -> NodePath:
        """A hex highlight as a filled band (an annulus) of world width, so it reads from far.

        A thin outline vanishes when the camera pulls back; a filled band does not. The centre
        of the band is a hole, so the counter under it still shows."""
        import math

        cx, cy, cz = center
        z = cz + RING_LIFT
        band = max(0.3, width)
        inner = max(0.12, radius - band)
        vdata = GeomVertexData("ring", GeomVertexFormat.getV3c4(), Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        cwriter = GeomVertexWriter(vdata, "color")
        tris = GeomTriangles(Geom.UHStatic)
        segments = RING_SEGMENTS
        for i in range(segments):
            angle0 = 2.0 * math.pi * i / segments
            angle1 = 2.0 * math.pi * (i + 1) / segments
            base = i * 4
            for radius_at, angle in ((inner, angle0), (radius, angle0), (radius, angle1), (inner, angle1)):
                vertex.addData3(cx + radius_at * math.cos(angle), cy + radius_at * math.sin(angle), z)
                cwriter.addData4(*color)
            tris.addVertices(base, base + 1, base + 2)
            tris.addVertices(base, base + 2, base + 3)
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("ring")
        node.addGeom(geom)
        return parent.attachNewNode(node)

    def _label(self, parent: NodePath, center: tuple[float, float, float], text: str) -> NodePath:
        """A small flat text label above a target, so the watcher reads the fire phase."""
        node = TextNode("phase")
        node.setText(text)
        node.setAlign(TextNode.ACenter)
        node.setTextColor(*COLOR_FIRE)
        path = parent.attachNewNode(node)
        path.setScale(0.9)
        path.setPos(center[0], center[1], center[2] + 1.0)
        # The label lies flat on the board plane, so it reads from the tilted 3D camera.
        path.setP(-90)
        return path
