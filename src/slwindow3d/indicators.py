"""The tactical overlay of the 3D window: the drawing of `slwindow.overlay` in Panda3D.

The model is the one the 2D window draws (`slwindow.marks`), so a watcher sees one
overlay in the two windows. This module turns it into flat geometry on the hex tops:

- A shade is a translucent hexagon a little above the top of its hex, in the tone of the
  model. The tones are quiet, the way a pencil wash sits on a field map.
- A tracer is a narrow dashed ribbon from the firer to the target, in the tone of the fire
  phase, and it stops short of the two counters.
- A burst is a few short spokes on the target hex in the tone of the result.
- A ghost is a translucent card with a dark outline on the track hex where the defensive
  fire catches a moved unit (rule 16.1). The counter itself stays at its end hex.
- The focus is a thin line round one hex.

The overlay reads what the host sends and nothing else. It applies no rule and it holds no
rule table (AR-06). The line of sight it shades is the host's answer to `los_request`.

Robustness is the rule here: the live game must never crash because of an overlay bug.
The update runs inside a try/except that prints a short warning and returns, and each
rebuild clears the old nodes first, so a bug leaks no nodes and kills no window.
"""

from __future__ import annotations

import math
import time
from typing import Any, Callable, Sequence

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
    TransparencyAttrib,
)

from slcore.geometry import VERTEX_OFFSETS
from slwindow import theme
from slwindow.overlay import (
    RESULT_BROKEN,
    RESULT_CHECK,
    RESULT_KILL,
    TONE_MOVE,
    TONE_TARGET,
    TONE_TRACK,
    Overlay,
    Tracker,
)
from slwindow3d.mesh import HEIGHT_PER_LEVEL, ROOT_THREE, hex_world

# The heights above the top of a hex, in world units. A shade lies on the ground under the
# counters. A mark floats over the counters, and the depth test is off for the whole
# overlay, so a mark reads where a counter is in front of it.
SHADE_LIFT = 0.03
MARK_LIFT = 0.6
# A shade pulls in from the hex corners by this share, so the grid line stays visible.
SHADE_INSET = 0.94
# The width of a tracer and of a spoke, in world units. A hex is four units wide.
TRACER_WIDTH = 0.09
SPOKE_WIDTH = 0.07
FOCUS_WIDTH = 0.12
# A tracer starts and stops this far from the centres of the two hexes.
TRACER_CLEAR = 1.3
DASH = (0.55, 0.30)
SPOKE_LENGTH = 0.95
SPOKE_INNER = 0.35
SPOKE_TURN = 15.0
SPOKES = {RESULT_KILL: 12, RESULT_BROKEN: 8, RESULT_CHECK: 6}
SPOKES_DEFAULT = 6
GHOST_SIZE = 2.1
# The high bin, so the overlay draws after the board and the counters.
OVERLAY_BIN = 60
# The shades of the options of the focus unit, which the `o` key hides.
_OPTION_TONES = {TONE_MOVE, TONE_TARGET, TONE_TRACK}


def rgba(colour: Sequence[int], alpha: float | None = None) -> tuple[float, float, float, float]:
    """A theme colour as the floats Panda3D wants. A four-part colour carries its alpha."""
    a = colour[3] / 255.0 if len(colour) > 3 and alpha is None else (1.0 if alpha is None else alpha)
    return (colour[0] / 255.0, colour[1] / 255.0, colour[2] / 255.0, a)


class Indicators:
    """The tactical overlay of the 3D window.

    Build it with the parent `render` NodePath. Call `set_board` when the window builds a
    board, so the overlay turns a hex id into a world point. Call `update` with each
    snapshot, and `sweep` each frame, so a mark that lingered past its time goes.
    """

    def __init__(self, parent: NodePath, ask_los: Callable[[str, str], None] | None = None) -> None:
        self.root: NodePath = parent.attachNewNode("indicators")
        self.shade_root: NodePath = self.root.attachNewNode("shades")
        self.mark_root: NodePath = self.root.attachNewNode("marks")
        self._style(self.root)
        self.enabled = True
        self.options = True
        self.tracker = Tracker()
        self.overlay = Overlay()
        self._tops: dict[str, tuple[float, float, float]] = {}
        self._key: tuple | None = None
        self._snapshot: Any = None
        self._ask_los = ask_los
        self._asked: set[tuple[str, str]] = set()
        # The window sets these: the unit a person clicked, and the hex under the pointer.
        self.pinned: int | None = None
        self.pointer_hex: str | None = None

    # ------------------------------------------------------------------ setup

    def _style(self, node: NodePath) -> None:
        """No light, alpha on, and a high fixed bin with the depth test off, so a mark
        shows even where a counter is in front of it."""
        node.setLightOff()
        node.setTransparency(TransparencyAttrib.MAlpha)
        node.setBin("fixed", OVERLAY_BIN)
        node.setDepthTest(False)
        node.setDepthWrite(False)

    def set_board(self, board_doc: dict[str, Any] | None) -> None:
        """Build the hex id to world point map from the board document."""
        self._tops = {}
        # A new board is a new game, so the marks of the last one go.
        self.tracker.reset()
        self._asked = set()
        self._key = None
        if not board_doc:
            return
        for hexagon in board_doc.get("hexes", []):
            wx, wy = hex_world(hexagon["center"])
            wz = int(hexagon.get("elevation", 0) or 0) * HEIGHT_PER_LEVEL
            self._tops[hexagon["id"]] = (wx, wy, wz)

    def _top(self, hex_id: Any) -> tuple[float, float, float] | None:
        return None if hex_id is None else self._tops.get(str(hex_id))

    # ---------------------------------------------------------------- toggles

    def toggle(self) -> bool:
        """Show or hide the whole overlay. Return the new state."""
        self.enabled = not self.enabled
        if self.enabled:
            self.root.show()
        else:
            self.root.hide()
        return self.enabled

    def toggle_options(self) -> bool:
        """Show or hide the options of the focus unit. Return the new state."""
        self.options = not self.options
        self._key = None
        return self.options

    def clear(self) -> None:
        """Remove every overlay node. The next update rebuilds from the snapshot."""
        self.shade_root.node().removeAllChildren()
        self.mark_root.node().removeAllChildren()
        self._key = None

    # ------------------------------------------------------------- the update

    def update(self, snapshot: Any, now: float | None = None) -> Overlay:
        """Read a snapshot, build the model, and draw it when it changed. Never raise."""
        self._snapshot = snapshot
        try:
            return self._update(snapshot, time.monotonic() if now is None else now)
        except Exception as error:  # never let an overlay bug kill the game window
            print(f"indicators: skipped a frame after an error: {error!r}")
            return self.overlay

    def sweep(self, now: float | None = None) -> None:
        """Each frame: let a mark that lingered past its time go. Never raise."""
        if self._snapshot is not None:
            self.update(self._snapshot, now)

    def _update(self, snapshot: Any, now: float) -> Overlay:
        if snapshot is None or not self._tops:
            return self.overlay
        los = getattr(snapshot, "los", None)
        overlay = self.tracker.update(
            snapshot, now, self.pinned, self.pointer_hex, los if isinstance(los, dict) else None
        )
        if self._ask_los is not None:
            for pair in overlay.los_wanted:
                if pair not in self._asked:
                    self._asked.add(pair)
                    self._ask_los(*pair)
        self.overlay = overlay
        key = (overlay.key(), self.options)
        if key == self._key:
            return overlay
        self._key = key
        self._draw(overlay, snapshot)
        return overlay

    # ------------------------------------------------------------ the drawing

    def _draw(self, overlay: Overlay, snapshot: Any) -> None:
        self.shade_root.node().removeAllChildren()
        self.mark_root.node().removeAllChildren()
        for hex_id, tone in overlay.shades.items():
            if not self.options and tone in _OPTION_TONES:
                continue
            colour = theme.SHADE.get(tone)
            top = self._top(hex_id)
            if colour is None or top is None:
                continue
            self._hexagon(self.shade_root, top, SHADE_LIFT, rgba(colour), SHADE_INSET)
        view = getattr(snapshot, "view", None) or {}
        units = {int(u["id"]): u for u in view.get("units", []) if "id" in u}
        for ghost in overlay.ghosts:
            top = self._top(ghost.hex)
            unit = units.get(ghost.unit)
            if top is not None and unit is not None:
                self._ghost(top, unit)
        for tracer in overlay.tracers:
            source = self._top(tracer.source)
            target = self._top(tracer.target)
            if source is None or target is None:
                continue
            colour = rgba(theme.TRACER.get(tracer.kind, theme.TRACER["other"]))
            self._tracer(source, target, colour)
        for burst in overlay.bursts:
            top = self._top(burst.hex)
            if top is not None:
                self._burst(top, burst.result)
        if overlay.focus_hex:
            top = self._top(overlay.focus_hex)
            if top is not None:
                self._outline(top, rgba(theme.SELECT))

    def _quad(self, parent: NodePath, corners, colour) -> NodePath:
        """A flat two-triangle quad from four world corners, in one flat colour."""
        vdata = GeomVertexData("quad", GeomVertexFormat.getV3c4(), Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        cwriter = GeomVertexWriter(vdata, "color")
        for corner in corners:
            vertex.addData3(*corner)
            cwriter.addData4(*colour)
        tris = GeomTriangles(Geom.UHStatic)
        tris.addVertices(0, 1, 2)
        tris.addVertices(0, 2, 3)
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("quad")
        node.addGeom(geom)
        return parent.attachNewNode(node)

    def _hexagon(self, parent: NodePath, top, lift: float, colour, inset: float) -> NodePath:
        """A flat hexagon on the top of one hex, as a fan of six triangles."""
        cx, cy, cz = top
        z = cz + lift
        vdata = GeomVertexData("hexagon", GeomVertexFormat.getV3c4(), Geom.UHStatic)
        vertex = GeomVertexWriter(vdata, "vertex")
        cwriter = GeomVertexWriter(vdata, "color")
        vertex.addData3(cx, cy, z)
        cwriter.addData4(*colour)
        for ox, oy in VERTEX_OFFSETS:
            vertex.addData3(cx + ox * inset, cy + oy * ROOT_THREE * inset, z)
            cwriter.addData4(*colour)
        tris = GeomTriangles(Geom.UHStatic)
        for i in range(6):
            tris.addVertices(0, 1 + i, 1 + (i + 1) % 6)
        geom = Geom(vdata)
        geom.addPrimitive(tris)
        node = GeomNode("hexagon")
        node.addGeom(geom)
        return parent.attachNewNode(node)

    def _ribbon(self, parent: NodePath, a, b, colour, width: float) -> NodePath:
        """A flat band of world `width` from a to b."""
        ax, ay, az = a
        bx, by, bz = b
        dx, dy = bx - ax, by - ay
        length = math.hypot(dx, dy) or 0.001
        px = -dy / length * (width / 2.0)
        py = dx / length * (width / 2.0)
        return self._quad(
            parent,
            [(ax + px, ay + py, az), (ax - px, ay - py, az), (bx - px, by - py, bz), (bx + px, by + py, bz)],
            colour,
        )

    def _dashed(self, parent: NodePath, a, b, colour, width: float) -> None:
        ax, ay, az = a
        bx, by, bz = b
        dx, dy, dz = bx - ax, by - ay, bz - az
        length = math.hypot(dx, dy)
        if length < 0.05:
            return
        mark, gap = DASH
        at = 0.0
        while at < length:
            stop = min(length, at + mark)
            share_a, share_b = at / length, stop / length
            self._ribbon(
                parent,
                (ax + dx * share_a, ay + dy * share_a, az + dz * share_a),
                (ax + dx * share_b, ay + dy * share_b, az + dz * share_b),
                colour,
                width,
            )
            at = stop + gap

    def _tracer(self, source, target, colour) -> None:
        sx, sy, sz = source
        tx, ty, tz = target
        dx, dy = tx - sx, ty - sy
        length = math.hypot(dx, dy)
        if length <= TRACER_CLEAR * 2:
            return
        ux, uy = dx / length, dy / length
        a = (sx + ux * TRACER_CLEAR, sy + uy * TRACER_CLEAR, sz + MARK_LIFT)
        b = (tx - ux * TRACER_CLEAR, ty - uy * TRACER_CLEAR, tz + MARK_LIFT)
        self._dashed(self.mark_root, a, b, colour, TRACER_WIDTH)

    def _burst(self, top, result: str) -> None:
        cx, cy, cz = top
        z = cz + MARK_LIFT
        colour = rgba(theme.BURST.get(result, theme.BURST["none"]))
        halo = rgba(theme.BURST_HALO)
        count = SPOKES.get(result, SPOKES_DEFAULT)
        node = self.mark_root.attachNewNode("burst")
        spokes = []
        for i in range(count):
            angle = math.radians(SPOKE_TURN + 360.0 * i / count)
            spokes.append(
                (
                    (cx + math.cos(angle) * SPOKE_INNER, cy + math.sin(angle) * SPOKE_INNER, z),
                    (cx + math.cos(angle) * SPOKE_LENGTH, cy + math.sin(angle) * SPOKE_LENGTH, z),
                )
            )
        # A pale stroke under the tone, so the mark reads on a counter of any stock.
        for width, tone in ((SPOKE_WIDTH * 2.2, halo), (SPOKE_WIDTH, colour)):
            for inner, outer in spokes:
                self._ribbon(node, inner, outer, tone, width)
        self._hexagon(node, (cx, cy, z), 0.0, halo, 0.11)
        self._hexagon(node, (cx, cy, z), 0.001, colour, 0.08)

    def _outline(self, top, colour) -> None:
        cx, cy, cz = top
        z = cz + MARK_LIFT
        corners = [(cx + ox * SHADE_INSET, cy + oy * ROOT_THREE * SHADE_INSET, z) for ox, oy in VERTEX_OFFSETS]
        node = self.mark_root.attachNewNode("focus")
        for a, b in zip(corners, corners[1:] + corners[:1]):
            self._ribbon(node, a, b, colour, FOCUS_WIDTH)

    def _ghost(self, top, unit: dict[str, Any]) -> None:
        """A translucent card on the track hex, with the outline of a counter."""
        cx, cy, cz = top
        z = cz + SHADE_LIFT * 2
        stock = theme.NATIONAL.get(str(unit.get("nationality", "")), theme.MARKER)
        half = GHOST_SIZE / 2.0
        node = self.mark_root.attachNewNode("ghost")
        corners = [(cx - half, cy - half, z), (cx + half, cy - half, z), (cx + half, cy + half, z), (cx - half, cy + half, z)]
        self._quad(node, corners, rgba(stock, theme.GHOST_FILL_ALPHA / 255.0))
        line = rgba(theme.GHOST_LINE, theme.GHOST_LINE_ALPHA / 255.0)
        for a, b in zip(corners, corners[1:] + corners[:1]):
            self._dashed(node, a, b, line, SPOKE_WIDTH)
