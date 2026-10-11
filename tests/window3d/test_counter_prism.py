"""The 3D counter body: a rounded-square prism that sits on top of its hex (feedback).

The counter is a die-cut chit with a real thickness. Its body is a rounded-square prism, so
its cut edge follows the rounded top and a single counter already shows an edge. A stack of
counters in one hex is a messy heap: each counter a thickness higher than the last, and each
with a small side offset and turn from a hash of its id, so the heap is deterministic and
holds no random number (SR-07, DR-01).

These tests need the `view3d` extra. Without panda3d the whole module is skipped, the same
way the other 3D test does.
"""

from __future__ import annotations

import pytest

pytest.importorskip("panda3d")

from panda3d.core import GeomNode, GeomVertexReader, NodePath  # noqa: E402

from slwindow3d import counters as c3d  # noqa: E402


def _unit(uid, kind="squad", nat="russian", typ="4-4-7"):
    return {
        "id": uid,
        "kind": kind,
        "nationality": nat,
        "type": typ,
        "firepower": 4,
        "range": 4,
        "morale": 7,
        "leadership": 0,
        "broken": False,
        "prep_fired": False,
        "moved": False,
        "malfunction": False,
        "wreck": False,
        "immobilized": False,
        "crew_exposed": False,
        "facing": -1,
        "gun": 0,
        "movement_points": 0,
        "hex": "H11",
        "carrier": None,
    }


def _z_range(node: GeomNode):
    geom = node.getGeom(0)
    reader = GeomVertexReader(geom.getVertexData(), "vertex")
    zs = []
    while not reader.isAtEnd():
        zs.append(reader.getData3().getZ())
    return min(zs), max(zs)


def _xy_extent(node: GeomNode):
    geom = node.getGeom(0)
    reader = GeomVertexReader(geom.getVertexData(), "vertex")
    xs, ys = [], []
    while not reader.isAtEnd():
        p = reader.getData3()
        xs.append(p.getX())
        ys.append(p.getY())
    return max(xs) - min(xs), max(ys) - min(ys)


def test_the_prism_sits_on_top_of_the_hex():
    """The body bottom is at z 0 and the top a thickness above, so one counter shows an edge."""
    node = c3d._prism_node(c3d.CARD_SIZE, c3d.COUNTER_THICKNESS, c3d._EDGE_RGBA)
    low, high = _z_range(node)
    assert low == pytest.approx(0.0), "the counter body sinks below the hex top"
    assert high == pytest.approx(c3d.COUNTER_THICKNESS), "the counter body has no thickness above the hex"


def test_the_footprint_is_rounded_not_a_sharp_square():
    """A rounded-square footprint stays inside the square by one corner radius on each side."""
    outline = c3d._rounded_outline(c3d.CARD_SIZE, c3d.CARD_SIZE * c3d.CORNER_FRAC)
    half = c3d.CARD_SIZE / 2.0
    r = c3d.CARD_SIZE * c3d.CORNER_FRAC
    corner = (half, half)
    # No outline point reaches the sharp corner of the square: the die-cut rounds it off.
    nearest = min((abs(x - corner[0]) + abs(y - corner[1])) for x, y in outline)
    assert nearest > r * 0.3, "the footprint has a sharp corner where the chit is rounded"
    # The footprint still fills nearly the whole card in width and height.
    dx, dy = _xy_extent(node=c3d._prism_node(c3d.CARD_SIZE, c3d.COUNTER_THICKNESS, c3d._EDGE_RGBA))
    assert dx == pytest.approx(c3d.CARD_SIZE, abs=1e-6)
    assert dy == pytest.approx(c3d.CARD_SIZE, abs=1e-6)


def test_the_corner_radius_matches_the_2d_chit():
    """The 3D prism and the 2D chit use one corner fraction, so their edges agree."""
    from slwindow import counters as chit

    assert c3d.CORNER_FRAC == chit.CHIT_RADIUS_FRAC


def test_the_bottom_counter_is_square_and_centred():
    """A lone counter (stack index 0) has no jitter, so it is not askew on its hex."""
    dx, dy, twist = c3d._jitter_of(4242, 0)
    assert (dx, dy, twist) == (0.0, 0.0, 0.0)


def test_a_stack_is_a_deterministic_messy_heap():
    """Each counter above the base takes a side offset and a turn, stable from its id."""
    a = c3d._jitter_of(101, 1)
    b = c3d._jitter_of(101, 2)
    # A counter higher in the stack sits differently, so the heap is not a straight tower.
    assert a != b, "two counters of the stack take the same pose"
    # The offset and the turn stay within their bounds.
    for dx, dy, twist in (a, b):
        assert abs(dx) <= c3d.JITTER and abs(dy) <= c3d.JITTER
        assert abs(twist) <= c3d.TWIST
        assert twist != 0.0, "a counter above the base has no turn, so the heap is a staircase"
    # The same id gives the same pose in a second call: no random number is in the picture.
    assert c3d._jitter_of(101, 1) == a


def test_a_stack_climbs_a_thickness_for_each_counter():
    """Each counter of a hex is a thickness higher than the one below it."""
    root = NodePath("root")
    heights = []
    for index in range(4):
        node = c3d.add_counter(root, _unit(300 + index), 0.0, 0.0, 0.0, stack_index=index)
        heights.append(node.getZ())
    for lower, higher in zip(heights, heights[1:]):
        assert higher > lower, "a counter of the stack does not sit above the one below it"
        assert higher - lower == pytest.approx(c3d.COUNTER_THICKNESS * 1.02), "the stack step is not one thickness"


def test_a_counter_still_draws_after_pygame_quit():
    """The 2D window calls `pygame.quit()` when it closes, and that makes each font invalid.
    The font caches of the counter drawing kept the old fonts, so the next machine gun
    counter raised 'Invalid font' in the poll task of the 3D window."""
    pygame = c3d._ensure_pygame()
    machine_gun = _unit(9001, kind="weapon", typ="MMG")
    c3d._texture_cache.clear()
    assert c3d.counter_texture(machine_gun) is not None
    before = c3d.font_generation()
    pygame.quit()
    # Another part of the process initializes pygame again; the kept fonts are still invalid.
    pygame.init()
    c3d._texture_cache.clear()
    texture = c3d.counter_texture(_unit(9002, kind="weapon", typ="LMG"))
    assert texture is not None
    assert c3d.font_generation() == before + 1
