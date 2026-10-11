"""Short animations of fire, one for each kind of weapon (see `firekinds.py`).

Each effect is a few small flat discs on the board that move, grow, and fade over a fraction
of a second: tracers for rifles, submachine guns, and machine guns; a stream of flame; a
rocket on a low arc with a smoke trail; a muzzle flash, a shell, and an impact for a tank
gun; a flash, a dust ring, and debris for a demolition charge; smoke that grows and stays;
grenade flashes for close combat; dust and flashes for an overrun. The colours are the
muted ones of the indicators, and each size is in world units (a hex is four units across).

The motion is for the eye only. The result of a fire is the event's, and the window draws it
as the result label of `indicators.py`. The random offsets of the tracers and puffs come
from a generator seeded by the event, so one event always draws the same way. Nothing here
reads a rule (AR-06).
"""

from __future__ import annotations

import colorsys
import math
import random
import time
import zlib
from dataclasses import dataclass
from typing import Any, Callable

from panda3d.core import (
    Geom,
    GeomNode,
    GeomTriangles,
    GeomVertexData,
    GeomVertexFormat,
    GeomVertexWriter,
    NodePath,
)

from slwindow3d.firekinds import BLAST, FLAME, GRENADES, GUN, MG, OVERRUN, RIFLE, ROCKET, SMG, SMOKE, Shot

Point = tuple[float, float, float]

# The height of the effects over the hex face, and the reach of a random offset in a hex.
LIFT = 0.15
# The sizes above are right for a camera this far from the board (a close view of a few
# hexes). The window opens with the whole board in view, two to four times farther, and
# there a tracer was a few pixels: the owner saw no animation. The window sets `zoom` from
# its camera distance on each frame, and each particle is that much larger, so an effect
# keeps its size on the screen. The motion is slower than real fire, so the eye catches it.
REFERENCE_DISTANCE = 25.0
MAX_ZOOM = 5.0
TIME_SCALE = 1.6
SPREAD = 0.8
DISC_STEPS = 14

# The tracer colours of a unit whose army the view does not name.
TRACER_RIFLE = (1.0, 0.9, 0.48)
TRACER_SMG = (1.0, 0.8, 0.4)
TRACER_MG = (1.0, 0.48, 0.26)
# The tracer of each army, from the owner (2026-10-10): American and British tracers were
# most often red; German and Russian tracers were most often green, and some were white or
# yellow. A machine gun tracer is a little deeper than a rifle tracer of the same colour.
TRACER_RED = (1.0, 0.27, 0.2)
TRACER_GREEN = (0.42, 1.0, 0.36)
TRACER_PALE = ((1.0, 0.97, 0.88), (1.0, 0.9, 0.42))  # white, yellow
TRACER_BY_ARMY = {"american": TRACER_RED, "british": TRACER_RED, "german": TRACER_GREEN, "russian": TRACER_GREEN}
# The share of the green rounds that are white or yellow, so a German or a Russian burst has
# a few pale rounds in it.
PALE_SHARE = 0.2
TRACER_LIGHTNESS = {"rifle": 0.64, "smg": 0.62, "mg": 0.58}


def tracer_colour(army: str, weapon: str, rng: random.Random | None = None) -> tuple[float, float, float]:
    """The colour of one tracer round of this army and weapon (rifle, smg, or mg). With a
    generator, a German or a Russian round is white or yellow at the rate PALE_SHARE."""
    base = TRACER_BY_ARMY.get(str(army).lower())
    if base is None:
        return {"rifle": TRACER_RIFLE, "smg": TRACER_SMG}.get(weapon, TRACER_MG)
    if base is TRACER_GREEN and rng is not None and rng.random() < PALE_SHARE:
        return TRACER_PALE[rng.randrange(len(TRACER_PALE))]
    hue, _, saturation = colorsys.rgb_to_hls(*base)
    return colorsys.hls_to_rgb(hue, TRACER_LIGHTNESS.get(weapon, 0.66), saturation)


def zoom_for(distance: float) -> float:
    """The size factor of the effects for a camera at this distance from its target."""
    return max(1.0, min(MAX_ZOOM, float(distance) / REFERENCE_DISTANCE))


# The colours of the other effects, RGB. The alpha of each particle comes from its own curve.
DUST = (0.74, 0.69, 0.60)
FLAME_CORE = (1.0, 0.86, 0.38)
FLAME_EDGE = (0.95, 0.42, 0.14)
FLASH = (1.0, 0.92, 0.62)
SMOKE_GREY = (0.86, 0.86, 0.83)
TRAIL_GREY = (0.70, 0.70, 0.67)
SHELL = (1.0, 0.96, 0.82)


@dataclass
class Particle:
    node: NodePath
    start: float
    end: float
    path: Callable[[float], Point]
    radius: Callable[[float], float]
    alpha: Callable[[float], float]
    colour: tuple[float, float, float]
    # A streak is this many times longer than it is wide, along its heading in degrees.
    stretch: float = 1.0
    heading: float = 0.0


def _disc_template() -> GeomNode:
    """A flat white disc of radius 1. Each particle is a copy with its own colour scale."""
    vdata = GeomVertexData("disc", GeomVertexFormat.getV3c4(), Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    colour = GeomVertexWriter(vdata, "color")
    vertex.addData3(0, 0, 0)
    colour.addData4(1, 1, 1, 1)
    for i in range(DISC_STEPS):
        angle = 2.0 * math.pi * i / DISC_STEPS
        vertex.addData3(math.cos(angle), math.sin(angle), 0)
        colour.addData4(1, 1, 1, 1)
    tris = GeomTriangles(Geom.UHStatic)
    for i in range(DISC_STEPS):
        tris.addVertices(0, 1 + i, 1 + (i + 1) % DISC_STEPS)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("disc")
    node.addGeom(geom)
    return node


def _streak_template() -> GeomNode:
    """A flat white quad one unit long on x and one unit wide on y, centred on the origin. A
    tracer is a copy, turned to its line of flight and scaled to its length and width."""
    vdata = GeomVertexData("streak", GeomVertexFormat.getV3c4(), Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    colour = GeomVertexWriter(vdata, "color")
    for x, y in ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5)):
        vertex.addData3(x, y, 0)
        colour.addData4(1, 1, 1, 1)
    tris = GeomTriangles(Geom.UHStatic)
    tris.addVertices(0, 1, 2)
    tris.addVertices(0, 2, 3)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("streak")
    node.addGeom(geom)
    return node


def _tracer_template() -> GeomNode:
    """A thin line one unit long, its head at the origin and its tail at x = -1. The head is
    opaque and the tail fades to nothing, the way a tracer round reads to the eye: a bright
    point that draws a short fading line behind it. The colour scale gives it its colour."""
    vdata = GeomVertexData("tracer", GeomVertexFormat.getV3c4(), Geom.UHStatic)
    vertex = GeomVertexWriter(vdata, "vertex")
    colour = GeomVertexWriter(vdata, "color")
    # Three pairs of points from the head back: opaque, half, and clear.
    for x, alpha in ((0.0, 1.0), (-0.3, 0.55), (-1.0, 0.0)):
        for y in (-0.5, 0.5):
            vertex.addData3(x, y, 0)
            colour.addData4(1, 1, 1, alpha)
    tris = GeomTriangles(Geom.UHStatic)
    # Counterclockwise as seen from above, so the face is not culled as a back face.
    for base in (0, 2):
        tris.addVertices(base, base + 3, base + 2)
        tris.addVertices(base, base + 1, base + 3)
    geom = Geom(vdata)
    geom.addPrimitive(tris)
    node = GeomNode("tracer")
    node.addGeom(geom)
    return node


def _line(a: Point, b: Point, arc: float = 0.0) -> Callable[[float], Point]:
    def at(u: float) -> Point:
        return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u, a[2] + (b[2] - a[2]) * u + arc * 4.0 * u * (1.0 - u))

    return at


def _still(p: Point, drift: float = 0.0) -> Callable[[float], Point]:
    return lambda u: (p[0], p[1], p[2] + drift * u)


def _grow(r0: float, r1: float) -> Callable[[float], float]:
    return lambda u: r0 + (r1 - r0) * u


def _fade(a0: float, a1: float = 0.0) -> Callable[[float], float]:
    return lambda u: a0 + (a1 - a0) * u


def _hold_then_fade(a0: float) -> Callable[[float], float]:
    return lambda u: a0 * (1.0 - u * u)


class Effects:
    """The running animations. Call `launch` for each shot and `step` on each frame."""

    def __init__(self, parent: NodePath, ground: Callable[[Any], Point | None]) -> None:
        self.root = parent.attachNewNode("effects")
        self._ground = ground
        self._template = _disc_template()
        self._streak = _streak_template()
        self._tracer = _tracer_template()
        self.particles: list[Particle] = []
        # The size factor of the camera distance (see REFERENCE_DISTANCE).
        self.zoom = 1.0
        self._launch_now = 0.0

    # ------------------------------------------------------------------ the frame

    def step(self, now: float | None = None) -> int:
        """Move each particle to its place at this time, and remove the ones that ended.
        Return how many are still running."""
        now = time.monotonic() if now is None else now
        kept: list[Particle] = []
        for p in self.particles:
            if now >= p.end:
                p.node.removeNode()
                continue
            kept.append(p)
            if now < p.start:
                p.node.hide()
                continue
            u = (now - p.start) / max(1e-6, p.end - p.start)
            p.node.show()
            p.node.setPos(*p.path(u))
            r = max(0.001, p.radius(u)) * self.zoom
            p.node.setScale(r * p.stretch, r, 1.0)
            p.node.setColorScale(*p.colour, max(0.0, min(1.0, p.alpha(u))))
        self.particles = kept
        return len(kept)

    def clear(self) -> None:
        for p in self.particles:
            p.node.removeNode()
        self.particles = []

    # ------------------------------------------------------------------ the shots

    def launch(self, shot: Shot, key: str = "", now: float | None = None) -> int:
        """Start the animation of one shot. Return how many particles it made."""
        now = time.monotonic() if now is None else now
        self._launch_now = now
        target = self._lifted(shot.target)
        if target is None:
            return 0
        source = self._lifted(shot.source)
        rng = random.Random(zlib.crc32(f"{key}|{shot.kind}|{shot.source}|{shot.target}".encode()))
        before = len(self.particles)
        draw = {
            RIFLE: self._rifle,
            SMG: self._smg,
            MG: self._mg,
            FLAME: self._flame,
            ROCKET: self._rocket,
            GUN: self._gun,
            BLAST: self._blast,
            SMOKE: self._smoke,
            GRENADES: self._grenades,
            OVERRUN: self._overrun,
        }.get(shot.kind)
        if draw is None:
            return 0
        draw(now, source, target, shot, rng)
        return len(self.particles) - before

    def _lifted(self, hex_id: Any) -> Point | None:
        point = self._ground(hex_id) if hex_id is not None else None
        if point is None:
            return None
        return (point[0], point[1], point[2] + LIFT)

    def _add(
        self, start: float, duration: float, path, radius, alpha, colour, stretch: float = 1.0, toward: Point | None = None, tracer: bool = False
    ) -> None:
        """One particle. With `toward` it is a streak `stretch` times longer than wide, turned
        along the line from its start point to `toward`. With `tracer` the streak is the thin
        line with a fading tail (`_tracer_template`), its head on the path."""
        # The pace of the effect: each time is TIME_SCALE times longer from the launch.
        start = self._launch_now + (start - self._launch_now) * TIME_SCALE
        duration *= TIME_SCALE
        if tracer:
            template = self._tracer
        else:
            template = self._streak if stretch != 1.0 else self._template
        node = self.root.attachNewNode(template.makeCopy())
        heading = 0.0
        if toward is not None:
            origin = path(0.0)
            heading = math.degrees(math.atan2(toward[1] - origin[1], toward[0] - origin[0]))
            node.setH(heading)
        node.hide()
        self.particles.append(Particle(node, start, start + duration, path, radius, alpha, colour, stretch, heading))

    @staticmethod
    def _near(p: Point, rng: random.Random, spread: float = SPREAD) -> Point:
        angle = rng.uniform(0.0, 2.0 * math.pi)
        reach = rng.uniform(0.0, spread)
        return (p[0] + reach * math.cos(angle), p[1] + reach * math.sin(angle), p[2])

    def _tracers(
        self, now, source, target, rng, rounds, spacing, travel, width, length, colour, alpha=1.0, impact_every=1, flicker=False
    ) -> None:
        """Tracer rounds: thin lines `width` wide and `length` long (world units at a close
        view), each with a bright head and a fading tail, along the line of fire; a small
        faint kick of dust where a round lands; with `flicker`, a small muzzle flicker at the
        gun for each round. `colour` is a colour, or a function of the generator that gives
        the colour of each round."""
        if source is None:
            source = self._near(target, rng, 2.5)
        for i in range(rounds):
            start = now + i * spacing + rng.uniform(0.0, spacing * 0.3)
            end_point = self._near(target, rng)
            round_colour = colour(rng) if callable(colour) else colour
            self._add(
                start, travel, _line(source, end_point), _grow(width, width), _fade(alpha, alpha * 0.8),
                round_colour, length / width, end_point, tracer=True,
            )
            if flicker:
                self._add(start, 0.05, _still(source), _grow(0.09, 0.04), _fade(0.9), FLASH)
            if i % impact_every == 0:
                self._add(start + travel, 0.4, _still(end_point), _grow(0.04, 0.22), _fade(0.45), DUST)

    def _rifle(self, now, source, target, shot, rng) -> None:
        # Rifle rounds carried few tracers: two faint short lines.
        self._tracers(
            now, source, target, rng, rounds=2, spacing=0.18, travel=0.12, width=0.028, length=0.8,
            colour=lambda r: tracer_colour(shot.army, "rifle", r), alpha=0.6,
        )

    def _smg(self, now, source, target, shot, rng) -> None:
        self._tracers(
            now, source, target, rng, rounds=4, spacing=0.07, travel=0.1, width=0.026, length=0.55,
            colour=lambda r: tracer_colour(shot.army, "smg", r), alpha=0.65, impact_every=2,
        )

    def _mg(self, now, source, target, shot, rng) -> None:
        # A tracer every few rounds of a belt: four to six lines a burst, LMG to HMG.
        size = max(1, int(shot.size))
        self._tracers(
            now, source, target, rng, rounds=3 + size, spacing=0.07, travel=0.13,
            width=0.032 + 0.005 * size, length=0.9, colour=lambda r: tracer_colour(shot.army, "mg", r),
            alpha=0.95, impact_every=2, flicker=True,
        )

    def _flame(self, now, source, target, shot, rng) -> None:
        if source is None:
            source = self._near(target, rng, 2.0)
        for i in range(16):
            start = now + i * 0.035
            colour = FLAME_CORE if i % 2 == 0 else FLAME_EDGE
            end_point = self._near(target, rng, 0.5)
            self._add(start, 0.36, _line(source, end_point, 0.15), _grow(0.1, 0.55), _fade(0.9, 0.3), colour)
        for i in range(8):
            start = now + 0.35 + rng.uniform(0.0, 0.6)
            colour = FLAME_CORE if i % 2 == 0 else FLAME_EDGE
            self._add(start, 0.3, _still(self._near(target, rng, 1.0), 0.4), _grow(0.2, 0.75), _fade(0.8), colour)

    def _rocket(self, now, source, target, shot, rng) -> None:
        if source is None:
            source = self._near(target, rng, 3.0)
        aim = target if shot.hit else self._near(target, rng, 1.4)
        flight = 0.45 if shot.size < 2 else 0.6
        path = _line(source, aim, 1.0)
        self._add(now, flight, path, _grow(0.14, 0.14), _fade(1.0, 1.0), SHELL, 3.0, aim)
        for k in range(12):
            u = k / 12.0
            self._add(now + flight * u, 0.8, _still(path(u)), _grow(0.1, 0.45), _fade(0.6), TRAIL_GREY)
        self._impact(now + flight, aim, big=shot.hit)

    def _gun(self, now, source, target, shot, rng) -> None:
        if source is not None:
            self._add(now, 0.12, _still(source), _grow(0.55, 0.1), _fade(1.0), FLASH)
            self._add(now, 0.9, _still(source, 0.4), _grow(0.2, 0.75), _fade(0.5), SMOKE_GREY)
        else:
            source = self._near(target, rng, 3.0)
        aim = target if shot.hit else self._near(target, rng, 1.6)
        self._add(now, 0.2, _line(source, aim), _grow(0.05, 0.05), _fade(1.0, 0.9), SHELL, 0.9 / 0.05, aim, tracer=True)
        self._impact(now + 0.18, aim, big=shot.hit)

    def _impact(self, at: float, where: Point, big: bool) -> None:
        reach = 1.3 if big else 0.6
        self._add(at, 0.28, _still(where), _grow(0.3, reach), _fade(1.0), FLASH)
        self._add(at, 1.0, _still(where), _grow(0.4, reach * 1.4), _fade(0.6), DUST)

    def _blast(self, now, source, target, shot, rng) -> None:
        scale = 0.6 + 0.2 * max(1, int(shot.size))
        self._add(now, 0.3, _still(target), _grow(0.3, 1.8 * scale), _fade(1.0), FLASH)
        self._add(now + 0.05, 1.4, _still(target, 0.3), _grow(0.5, 2.3 * scale), _fade(0.65), DUST)
        for k in range(10):
            angle = 2.0 * math.pi * k / 10.0 + rng.uniform(-0.2, 0.2)
            reach = rng.uniform(1.2, 2.2) * scale
            end_point = (target[0] + reach * math.cos(angle), target[1] + reach * math.sin(angle), target[2])
            self._add(now, 0.6, _line(target, end_point, 0.8), _grow(0.07, 0.05), _fade(1.0, 0.2), DUST)

    def _smoke(self, now, source, target, shot, rng) -> None:
        delay = 0.0
        if source is not None:
            # A smoke round or a smoke grenade on a low arc, then the cloud.
            delay = 0.4
            self._add(now, delay, _line(source, target, 0.8), _grow(0.08, 0.08), _fade(1.0, 1.0), SMOKE_GREY)
        for _ in range(7):
            start = now + delay + rng.uniform(0.0, 0.8)
            self._add(start, 2.8, _still(self._near(target, rng, 1.0), 0.3), _grow(0.3, 1.2), _hold_then_fade(0.55), SMOKE_GREY)

    def _grenades(self, now, source, target, shot, rng) -> None:
        for _ in range(4 + 2 * max(1, int(shot.size))):
            start = now + rng.uniform(0.0, 0.9)
            where = self._near(target, rng, 1.2)
            self._add(start, 0.18, _still(where), _grow(0.1, 0.45), _fade(1.0), FLASH)
            self._add(start, 0.6, _still(where, 0.2), _grow(0.15, 0.6), _fade(0.5), DUST)

    def _overrun(self, now, source, target, shot, rng) -> None:
        self._add(now, 1.0, _still(target), _grow(0.5, 2.0), _fade(0.6), DUST)
        for _ in range(3):
            start = now + rng.uniform(0.0, 0.5)
            self._add(start, 0.22, _still(self._near(target, rng, 1.0)), _grow(0.2, 0.7), _fade(1.0), FLASH)
