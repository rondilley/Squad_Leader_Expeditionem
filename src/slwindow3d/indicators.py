"""Tactical indicators drawn over the 3D board, in the manner of a printed wargame.

The 3D window (see `app.py`) shows the board and the counters. This module adds what a
player or a watcher reads from the table: whose turn it is, where a unit can go and where it
went, who fired at what and with what result, and the line of sight. It reads the snapshot
the window already polls from the host client (AR-06). It adds no rule; it draws.

The style is that of the board and not of a cartoon. A hex is marked by a thin outline on
its edge, sometimes with a faint tint, so the counter and the terrain inside stay in view. A
line of sight is a thin taut thread from centre dot to centre dot, the way rule 7.1 traces it
with a string. A fire is its animation (`effects.py`), then a faint dark narrow line and a short
result word on the target hex (KIA, MC+1, no effect). A move is a thin path with a small arrowhead. Each width is in world units, so a
line keeps its width on the board when the camera pulls back and does not vanish.

Two kinds of overlay:

- The action overlay is the newest events of the log. It lingers for a short time
  (`ACTION_LINGER`) so it reads at speed, then a sweep removes it.
- The frame overlay rebuilds each frame: a faint outline on the hexes of the side that acts,
  and the toggleable options overlay (`o`): faint outlines on the hexes a unit can move to,
  and on the hexes it can fire at.

The colour of a result comes from the event kinds the core emits: an `eliminated` or a
`broken` outcome is red, a pin or a failed morale check is amber, and no effect is grey.

Robustness is the rule here: the live game must never crash because of an overlay bug. The
whole update runs inside a try/except that prints a short warning and returns, and every
rebuild clears its old nodes first.
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

from slwindow3d.effects import Effects
from slwindow3d.firekinds import shots_for
from slwindow3d.mesh import HEIGHT_PER_LEVEL, hex_world

# How long an action (a fire or a move) stays on the board, in seconds. Long enough that the
# eye reads it while a computer-versus-computer game runs at speed.
ACTION_LINGER = 1.8

# The overlay lies just over the top of each hex. The depth test is off for it, so it reads
# over the counters; a small lift keeps it off the hex face, and a low one keeps it on its hex
# when the 3D camera tilts.
LIFT = 0.06
# The text of a result sits a little higher, so it reads over a counter.
TEXT_LIFT = 0.4

# The hex outline: its distance in from the hex edge, as a share of the hex radius, and the
# hex radius of the lattice (a vertex is two units from the centre).
HEX_RADIUS = 2.0
OUTLINE_INSET = 0.06

# The colours. RGBA, each channel from zero to one. A muted palette, near the inks of a
# printed board: ivory, slate blue, brick red, amber, and grey.
# The fire line: the animation of the fire (`effects.py`) shows the shot, so the line that
# stays after it is only a faint dark trace of who fired at what (owner, 2026-10-10: no
# medium yellow line and no dot).
COLOR_FIRE = (0.12, 0.11, 0.09, 0.45)
COLOR_RESULT_RED = (0.80, 0.16, 0.12, 0.95)
COLOR_RESULT_ORANGE = (0.92, 0.62, 0.18, 0.95)
COLOR_RESULT_GREY = (0.78, 0.78, 0.74, 0.85)
COLOR_MOVE = (0.62, 0.78, 0.95, 0.9)
COLOR_ACTIVE = (0.96, 0.92, 0.75, 0.28)
COLOR_OPTION_MOVE = (0.62, 0.78, 0.95, 0.4)
COLOR_OPTION_FIRE = (0.85, 0.30, 0.22, 0.4)
# The play input: the selected unit, and the hexes a click can send it to or fire it at.
COLOR_SELECTED = (1.0, 0.97, 0.86, 0.98)
COLOR_TARGET_MOVE = (0.62, 0.78, 0.95, 0.9)
COLOR_TARGET_FIRE = (0.85, 0.22, 0.16, 0.92)
# A faint tint inside a target outline, so a target reads at a glance.
TINT_MOVE = (0.62, 0.78, 0.95, 0.12)
TINT_FIRE = (0.85, 0.22, 0.16, 0.12)
# The line of sight answer of the host: the thread, and the part past the blocking hex.
COLOR_LOS_CLEAR = (0.97, 0.96, 0.90, 0.95)
COLOR_LOS_BLOCKED = (0.85, 0.18, 0.14, 0.95)

# The widths, in WORLD units (a hex is four units across). Thin, like ink on the board.
WIDTH_FIRE = 0.04
WIDTH_MOVE = 0.10
WIDTH_OPTION = 0.07
WIDTH_LOS = 0.08
WIDTH_OUTLINE = 0.12
WIDTH_SELECTED = 0.18
WIDTH_ACTIVE = 0.07
# Kept for callers that read the old names.
THICK_FIRE = WIDTH_FIRE
THICK_MOVE = WIDTH_MOVE
THICK_OPTION = WIDTH_OPTION
RING_RADIUS = HEX_RADIUS
RING_BAND = WIDTH_OUTLINE

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
        # The selection layer of the play input. It rebuilds on each click and each frame,
        # and the toggles of the watcher overlay do not hide it.
        self.selection_root: NodePath = parent.attachNewNode("selection")
        # The line of sight answer the person asked for with the `l` key.
        self.los_root: NodePath = parent.attachNewNode("los")
        self._style(self.root)
        self._style(self.selection_root)
        self._style(self.los_root)
        self.enabled = True
        self.options = True
        self._tops: dict[str, tuple[float, float, float]] = {}
        self._hexes: dict[str, dict[str, Any]] = {}
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
        # The animations of fire, one kind for each weapon (`effects.py`). They hang under the
        # overlay root, so the `i` key hides them with the rest.
        self.effects = Effects(self.root, self._ground)
        # Called with the new events of each frame and the units of the view (the window
        # gives it to the sound board).
        self.on_new_events = None

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
        self._hexes = {}
        self.effects.clear()
        # A new board is a new game, so forget the events of the last one.
        self._seen_keys = set()
        self._primed = False
        if not board_doc:
            return
        for hexagon in board_doc.get("hexes", []):
            wx, wy = hex_world(hexagon["center"])
            wz = int(hexagon.get("elevation", 0) or 0) * HEIGHT_PER_LEVEL
            self._tops[hexagon["id"]] = (wx, wy, wz)
            self._hexes[hexagon["id"]] = hexagon

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
        self.effects.clear()

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
        units_by_id = {u.get("id"): u for u in units}
        self._ingest_log(log, unit_hex, units_by_id)

    def sweep(self) -> None:
        """Remove any lingering action that has passed its time. Call it each frame."""
        try:
            now = time.monotonic()
            self.effects.step(now)
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
        """A faint thin outline on each hex of the side that acts, so a watcher sees whose
        turn it is without the marker taking the eye from the action."""
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
            self._hex_outline(self.frame_root, hex_id, COLOR_ACTIVE, WIDTH_ACTIVE)

    # ------------------------------------------------------------------ the options

    def _draw_options(self, legal: list[dict[str, Any]], unit_hex: dict[Any, Any], active: Any, phase: str) -> None:
        """The faint overlay of what the side that acts can do this frame: an outline on each
        hex a unit can move to, and an outline on each hex a unit can fire at. One node for
        each legal entry, so a watcher can count the options."""
        for entry in legal:
            # The host sends each entry as {"id": ..., "payload": {...}}.
            command = entry.get("payload", entry)
            action = command.get("action")
            target = command.get("hex")
            if action in _MOVE_ACTIONS:
                self._hex_outline(self.frame_root, target, COLOR_OPTION_MOVE, WIDTH_OPTION)
            elif action in _FIRE_ACTIONS:
                self._hex_outline(self.frame_root, target, COLOR_OPTION_FIRE, WIDTH_OPTION)

    # ---------------------------------------------------------------- the selection

    def show_selection(self, selected_hex: str | None, move_hexes, fire_hexes) -> None:
        """The play input: an ivory outline on the hex of the selected unit, a slate blue
        outline and tint on each hex a click moves it to, and a brick red outline and tint on
        each hex a click fires it at."""
        self.selection_root.node().removeAllChildren()
        for hex_id in move_hexes:
            node = self.selection_root.attachNewNode("move-target")
            self._hex_fill(node, hex_id, TINT_MOVE)
            self._hex_outline(node, hex_id, COLOR_TARGET_MOVE, WIDTH_OUTLINE)
        for hex_id in fire_hexes:
            node = self.selection_root.attachNewNode("fire-target")
            self._hex_fill(node, hex_id, TINT_FIRE)
            self._hex_outline(node, hex_id, COLOR_TARGET_FIRE, WIDTH_OUTLINE)
        if selected_hex is not None:
            self._hex_outline(self.selection_root, selected_hex, COLOR_SELECTED, WIDTH_SELECTED)

    def show_los(self, answer: dict[str, Any] | None) -> None:
        """The host's line of sight answer, as a thread from centre dot to centre dot (rule
        7.1). A clear line is one ivory thread. A blocked line is ivory to the blocking hex and
        red past it, with a red outline on the blocking hex. None removes it."""
        self.los_root.node().removeAllChildren()
        if not answer:
            return
        a = self._ground(answer.get("from"))
        b = self._ground(answer.get("to"))
        if a is None or b is None:
            return
        blocking_id = answer.get("blocking_hex")
        blocking = self._ground(blocking_id)
        if answer.get("clear") or blocking is None:
            colour = COLOR_LOS_CLEAR if answer.get("clear") else COLOR_LOS_BLOCKED
            self._ribbon(self.los_root, a, b, colour, WIDTH_LOS)
        else:
            self._ribbon(self.los_root, a, blocking, COLOR_LOS_CLEAR, WIDTH_LOS)
            self._ribbon(self.los_root, blocking, b, COLOR_LOS_BLOCKED, WIDTH_LOS)
            self._hex_outline(self.los_root, blocking_id, COLOR_LOS_BLOCKED, WIDTH_OUTLINE)
        self._dot(self.los_root, a, COLOR_LOS_CLEAR)
        self._dot(self.los_root, b, COLOR_LOS_CLEAR if answer.get("clear") else COLOR_LOS_BLOCKED)

    # ------------------------------------------------------------------ the log

    @staticmethod
    def _event_key(event: dict[str, Any]) -> str:
        """A content key of one event, so a re-sent event is not read as new."""
        return f"{event.get('rule_id')}|{event.get('kind')}|{json.dumps(event.get('data', {}), sort_keys=True, default=str)}"

    def _ingest_log(
        self, log: list[dict[str, Any]], unit_hex: dict[Any, Any], units_by_id: dict[Any, Any] | None = None
    ) -> None:
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
        if self.on_new_events is not None:
            self.on_new_events(new_events, units_by_id or {})
        # The animation of each new fire, by its kind of weapon.
        for event in new_events:
            for shot in shots_for(event, units_by_id or {}):
                self.effects.launch(shot, key=self._event_key(event))
        # A fire event and the result events that follow it in the same batch are one action:
        # the result colours the target ring. Walk the new tail and group each fire with the
        # results that come after it until the next fire or move.
        i = 0
        n = len(new_events)
        while i < n:
            event = new_events[i]
            kind = event.get("kind")
            if kind == "fire":
                following: list[dict[str, Any]] = []
                j = i + 1
                while j < n and new_events[j].get("kind") not in {"fire"} | _MOVE_EVENTS:
                    following.append(new_events[j])
                    j += 1
                self._add_fire(event, unit_hex, following)
                i = j
            elif kind in _MOVE_EVENTS:
                self._add_move(event)
                i += 1
            else:
                i += 1

    def _add_fire(self, event: dict[str, Any], unit_hex: dict[Any, Any], following: list[dict[str, Any]]) -> None:
        """A faint dark narrow line from each firer to the target (the animation shows the
        shot itself), an outline on the target in the colour of the result, and the result as
        a short word on the target hex."""
        data = event.get("data", {})
        target_id = data.get("target")
        target = self._ground(target_id)
        if target is None:
            return
        kinds = {str(e.get("kind")) for e in following}
        colour = result_color(kinds)
        node = self.action_root.attachNewNode("fire")
        for member in data.get("members", []):
            src = self._ground(unit_hex.get(member.get("unit")))
            if src is not None:
                self._ribbon(node, src, target, COLOR_FIRE, WIDTH_FIRE)
        self._hex_outline(node, target_id, colour, WIDTH_OUTLINE)
        words = result_words(following)
        if words:
            self._text(node, target_id, words, colour)
        self._active_nodes.append((time.monotonic() + ACTION_LINGER, node))

    def _add_move(self, event: dict[str, Any]) -> None:
        """A thin path from the source hex to the destination, with a small arrowhead, and a
        thin outline on the destination."""
        data = event.get("data", {})
        src = self._ground(data.get("from"))
        dst = self._ground(data.get("to"))
        if src is None or dst is None:
            return
        node = self.action_root.attachNewNode("move")
        self._arrow(node, src, dst, COLOR_MOVE, WIDTH_MOVE)
        self._hex_outline(node, data.get("to"), COLOR_MOVE, WIDTH_ACTIVE)
        self._active_nodes.append((time.monotonic() + ACTION_LINGER, node))

    # ------------------------------------------------------------------ the drawing

    def _ground(self, hex_id: Any) -> tuple[float, float, float] | None:
        """The centre of a hex top, just over its face."""
        if hex_id is None:
            return None
        placed = self._tops.get(str(hex_id))
        if placed is None:
            return None
        return (placed[0], placed[1], placed[2] + LIFT)

    def _corners(self, hex_id: Any, shrink: float) -> list[tuple[float, float, float]] | None:
        """The six corners of a hex top, pulled in toward its centre by `shrink` world units."""
        from slwindow3d.picking import hex_corners

        hexagon = self._hexes.get(str(hex_id)) if hex_id is not None else None
        centre = self._ground(hex_id)
        if hexagon is None or centre is None:
            return None
        cx, cy, z = centre
        scale = max(0.0, (HEX_RADIUS - shrink) / HEX_RADIUS)
        return [(cx + (x - cx) * scale, cy + (y - cy) * scale, z) for x, y in hex_corners(hexagon)]

    def _hex_outline(self, parent: NodePath, hex_id: Any, color, width: float) -> NodePath | None:
        """A thin band just inside the edge of a hex, in one colour: the way a player marks a
        hex on the board, and not a disc over the counter."""
        outer = self._corners(hex_id, HEX_RADIUS * OUTLINE_INSET)
        inner = self._corners(hex_id, HEX_RADIUS * OUTLINE_INSET + width)
        if outer is None or inner is None:
            return None
        vdata = GeomVertexData("outline", GeomVertexFormat.getV3c4(), Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        cwriter = GeomVertexWriter(vdata, "color")
        tris = GeomTriangles(Geom.UHStatic)
        for i in range(6):
            j = (i + 1) % 6
            base = i * 4
            for point in (outer[i], outer[j], inner[j], inner[i]):
                vertex.addData3(*point)
                cwriter.addData4(*color)
            tris.addVertices(base, base + 1, base + 2)
            tris.addVertices(base, base + 2, base + 3)
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("outline")
        node.addGeom(geom)
        return parent.attachNewNode(node)

    def _hex_fill(self, parent: NodePath, hex_id: Any, color) -> NodePath | None:
        """A faint tint over a whole hex."""
        corners = self._corners(hex_id, HEX_RADIUS * OUTLINE_INSET)
        centre = self._ground(hex_id)
        if corners is None or centre is None:
            return None
        vdata = GeomVertexData("tint", GeomVertexFormat.getV3c4(), Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        cwriter = GeomVertexWriter(vdata, "color")
        for point in [centre] + corners:
            vertex.addData3(*point)
            cwriter.addData4(*color)
        tris = GeomTriangles(Geom.UHStatic)
        for i in range(6):
            tris.addVertices(0, 1 + i, 1 + (i + 1) % 6)
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("tint")
        node.addGeom(geom)
        return parent.attachNewNode(node)

    def _quad(self, parent: NodePath, corners, color) -> NodePath:
        """A flat two-triangle quad from four world corners, in one flat colour."""
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
        """A thin flat band of world `width` from a to b: a line that keeps its width on the
        board at any zoom."""
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
        return self._ribbon(parent, a, b, color, width)

    def _dot(self, parent: NodePath, centre, color, radius: float = 0.22) -> NodePath:
        """A small filled dot: the centre dot of a hex, where a thread starts or ends."""
        import math

        cx, cy, cz = centre
        vdata = GeomVertexData("dot", GeomVertexFormat.getV3c4(), Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        cwriter = GeomVertexWriter(vdata, "color")
        vertex.addData3(cx, cy, cz)
        cwriter.addData4(*color)
        steps = 12
        for i in range(steps):
            angle = 2.0 * math.pi * i / steps
            vertex.addData3(cx + radius * math.cos(angle), cy + radius * math.sin(angle), cz)
            cwriter.addData4(*color)
        tris = GeomTriangles(Geom.UHStatic)
        for i in range(steps):
            tris.addVertices(0, 1 + i, 1 + (i + 1) % steps)
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("dot")
        node.addGeom(geom)
        return parent.attachNewNode(node)

    def _arrow(self, parent: NodePath, a, b, color, width: float) -> NodePath:
        """A thin line from a to b with a small arrowhead that stops short of the centre of b,
        so the head does not cover the counter."""
        import math

        node = parent.attachNewNode("arrow")
        ax, ay, az = a
        bx, by, bz = b
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy) or 0.001
        ux, uy = dx / length, dy / length
        stop = min(0.9, length * 0.25)
        tip_x, tip_y = bx - ux * stop, by - uy * stop
        head = min(0.7, length * 0.3)
        base_x, base_y = tip_x - ux * head, tip_y - uy * head
        self._ribbon(node, a, (base_x, base_y, bz), color, width)
        half = head * 0.45
        left = (base_x - uy * half, base_y + ux * half, bz)
        right = (base_x + uy * half, base_y - ux * half, bz)
        self._quad(node, [(tip_x, tip_y, bz), left, right, (tip_x, tip_y, bz)], color)
        return node

    def _text(self, parent: NodePath, hex_id: Any, text: str, color) -> NodePath | None:
        """A short word flat on the lower part of a hex, in a small type, the way a player
        writes a result on a note: it does not cover the counter in the centre."""
        centre = self._ground(hex_id)
        if centre is None:
            return None
        node = TextNode("result")
        node.setText(text)
        node.setAlign(TextNode.ACenter)
        node.setTextColor(*color)
        # A small dark label behind the word, like a marker on the board, so the word reads
        # over the art of a counter.
        node.setCardColor(0.08, 0.08, 0.07, 0.78)
        node.setCardAsMargin(0.18, 0.18, 0.08, 0.06)
        node.setCardDecal(True)
        path = parent.attachNewNode(node)
        path.setScale(0.42)
        path.setPos(centre[0], centre[1] - HEX_RADIUS * 0.72, centre[2] + TEXT_LIFT)
        # The text lies flat on the board, so it reads from the tilted 3D camera too.
        path.setP(-90)
        return path


def result_words(following: list[dict[str, Any]]) -> str:
    """The short result of one fire, from the events that follow it: the worst IFT result
    on the hex, and BROKEN or KIA when a unit broke or died. Each word is a word of the
    events (AR-06)."""
    kinds = {str(e.get("kind")) for e in following}
    if "eliminated" in kinds:
        return "KIA" if any(str((e.get("data") or {}).get("result")) == "KIA" for e in following) else "ELIM"
    if "broken" in kinds:
        return "BROKEN"
    results = [str((e.get("data") or {}).get("result")) for e in following if e.get("kind") == "fire_result"]
    if not results:
        return ""
    for code in results:
        if code == "KIA":
            return "KIA"
    numbers = sorted((int(c) for c in results if c.isdigit()), reverse=True)
    if numbers:
        return f"MC+{numbers[0]}"
    if "M" in results:
        return "MC"
    return "no effect"
