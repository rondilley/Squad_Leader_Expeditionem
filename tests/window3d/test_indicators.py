"""Tests for the tactical overlay of the 3D window (slice 22).

They need the `view3d` extra. Without panda3d the whole module is skipped, the same way the
other 3D window tests skip without it. The window opens offscreen (`window-type offscreen`),
so the test needs no display.

The overlay draws the model of `slwindow.overlay`, which `tests/window/test_overlay.py`
reads in full. The tests here prove the 3D drawing of that model: a shade, a tracer, a
burst, a ghost, and the focus each give nodes, the nodes go when the marks expire, the
line of sight question reaches the host, and a bad snapshot kills no window.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("panda3d")

from panda3d.core import loadPrcFileData  # noqa: E402

# The offscreen window type must be set before a ShowBase is built.
loadPrcFileData("", "window-type offscreen")
loadPrcFileData("", "win-size 320 240")
loadPrcFileData("", "audio-library-name null")

from slcore import geometry  # noqa: E402
from slwindow import overlay as model  # noqa: E402
from slwindow3d.indicators import Indicators, rgba  # noqa: E402


def _board():
    """A flat row of five hexes, A1 to E1, with the centres the core gives them."""
    hexes = []
    for col in range(5):
        hexes.append(
            {
                "id": geometry.hex_id(col, 1),
                "col": col,
                "row": 1,
                "center": list(geometry.center(col, 1)),
                "terrain": "open",
                "elevation": 0,
            }
        )
    return {"name": "row", "cols": 5, "rows": 1, "hexes": hexes, "terrain": {}}


def _unit(unit_id: int, player: int, hex_id: str, **extra):
    base = {
        "id": unit_id,
        "player": player,
        "hex": hex_id,
        "carrier": None,
        "kind": "squad",
        "name": "4-4-7",
        "nationality": "russian" if player == 0 else "german",
        "track": [],
        "returned_from": None,
    }
    base.update(extra)
    return base


def _snapshot(board, units, legal=(), log=(), los=None):
    view = {"units": list(units), "fire_group": None, "melee": []}
    return SimpleNamespace(
        board=board,
        view=view,
        frame_id="f1",
        active=0,
        phase="movement",
        legal=list(legal),
        log=list(log),
        los=los or {},
    )


@pytest.fixture(scope="module")
def app():
    """One offscreen window for the whole module. Panda3D allows only one ShowBase per
    process, so if another test module already built one (it leaves the instance on
    `builtins.base`), reuse it and give it the overlay; otherwise build one here and destroy
    it at the end."""
    import builtins

    from slwindow3d.app import Board3DApp

    existing = getattr(builtins, "base", None)
    if isinstance(existing, Board3DApp):
        existing.set_board(_board())
        yield existing
        return
    instance = Board3DApp(_board())
    yield instance
    instance.destroy()


def test_rgba_reads_the_theme_colours():
    assert rgba((255, 0, 0)) == (1.0, 0.0, 0.0, 1.0)
    assert rgba((0, 255, 0, 51)) == (0.0, 1.0, 0.0, 0.2)
    assert rgba((0, 0, 255), 0.5) == (0.0, 0.0, 1.0, 0.5)


def test_the_focus_and_its_options_give_shades_and_an_outline(app):
    board = _board()
    app.set_board(board)
    asked: list[tuple[str, str]] = []
    indicators = Indicators(app.render, ask_los=lambda a, b: asked.append((a, b)))
    indicators.set_board(board)
    try:
        units = [_unit(1, 0, "A1"), _unit(2, 1, "E1")]
        log = [{"seq": 0, "kind": "phase", "data": {}}]
        indicators.update(_snapshot(board, units, log=log), now=1.0)
        assert indicators.shade_root.getNumChildren() == 0, "the first read draws nothing"
        log.append({"seq": 1, "rule_id": "5.5", "kind": "move", "data": {"unit": 1, "from": "A1", "to": "B1"}})
        units[0]["hex"] = "B1"
        legal = [{"id": "m", "payload": {"action": "move", "units": [1], "hex": "C1"}}]
        overlay = indicators.update(_snapshot(board, units, legal=legal, log=log), now=2.0)
        assert overlay.focus == 1 and overlay.focus_hex == "B1"
        # A shade for the focus, for the track (A1 and B1), and for the move option (C1).
        assert indicators.shade_root.getNumChildren() >= 3
        assert indicators.mark_root.getNumChildren() >= 1, "the focus outline"
        # The options go with the `o` key, and the focus stays.
        indicators.toggle_options()
        indicators.update(_snapshot(board, units, legal=legal, log=log), now=2.1)
        assert indicators.shade_root.getNumChildren() == 1
        indicators.toggle_options()
        app.graphicsEngine.renderFrame()
    finally:
        indicators.root.removeNode()


def test_a_fire_gives_a_tracer_a_burst_and_a_line_of_sight_question(app):
    board = _board()
    app.set_board(board)
    asked: list[tuple[str, str]] = []
    indicators = Indicators(app.render, ask_los=lambda a, b: asked.append((a, b)))
    indicators.set_board(board)
    try:
        units = [_unit(1, 0, "A1"), _unit(2, 1, "E1")]
        indicators.update(_snapshot(board, units), now=1.0)
        log = [
            {
                "seq": 0,
                "rule_id": "10.6",
                "kind": "fire",
                "data": {"target": "E1", "members": [{"unit": 1, "weapon": None}], "phase": "prep_fire"},
            },
            {"seq": 1, "rule_id": "10.5", "kind": "fire_result", "data": {"result": "M", "units": [2]}},
            {"seq": 2, "rule_id": "12.3", "kind": "broken", "data": {"unit": 2}},
        ]
        overlay = indicators.update(_snapshot(board, units, log=log), now=2.0)
        assert len(overlay.tracers) == 1 and overlay.tracers[0].result == model.RESULT_BROKEN
        marks = indicators.mark_root.getNumChildren()
        assert marks >= 3, "the dashes of the tracer, the burst, and the focus outline"
        assert asked == [("A1", "E1")], "one line of sight question for the fire"
        # The answer of the host shades the hexes the line threads.
        los = {("A1", "E1"): {"clear": True, "traced": ["B1", "C1", "D1", "E1"], "blocking_hex": None}}
        answered = indicators.update(_snapshot(board, units, log=log, los=los), now=2.2)
        assert answered.shades["C1"] == model.TONE_LOS
        assert asked == [("A1", "E1")], "the question went out one time"
        # The same tail again adds nothing, and the marks go when their time is up.
        again = indicators.update(_snapshot(board, units, log=log, los=los), now=2.4)
        assert len(again.tracers) == 1
        indicators.sweep(now=2.0 + model.LINGER_BURST + 0.1)
        assert indicators.overlay.tracers == [] and indicators.overlay.bursts == []
        app.graphicsEngine.renderFrame()
    finally:
        indicators.root.removeNode()


def test_a_returned_unit_gives_a_ghost_on_the_track_hex(app):
    board = _board()
    app.set_board(board)
    indicators = Indicators(app.render)
    indicators.set_board(board)
    try:
        unit = _unit(1, 0, "B1", returned_from="D1", track=["B1", "C1", "D1"])
        overlay = indicators.update(_snapshot(board, [unit]), now=1.0)
        assert len(overlay.ghosts) == 1
        names = [indicators.mark_root.getChild(i).getName() for i in range(indicators.mark_root.getNumChildren())]
        assert "ghost" in names
        # The counter stands at its end hex and not at the track hex. The card reads the
        # whole face of the unit, so this is a unit document of the core.
        from slcore.view import UnitView

        squad = UnitView(
            id=1, player=0, type_key="russian:squad_447", kind="squad", hex=(1, 1), carrier=None,
            broken=False, berserk=False, prep_fired=False, moved=True, malfunction=False, dm=False,
            name="4-4-7", firepower=4, range=4, morale=7, leadership=0, own=True,
            track=((1, 1), (2, 1), (3, 1)), returned_from=(3, 1),
        ).to_dict()
        assert squad["hex"] == "B1" and squad["returned_from"] == "D1"
        app.load_view(None, {"units": [squad]})
        assert app.counter_root is not None and app.counter_root.getNumChildren() == 1
        card = app.counter_root.getChild(0)
        end_x = geometry.center(3, 1)[0]
        assert abs(card.getX() - end_x) < 0.6, (card.getX(), end_x)
        app.graphicsEngine.renderFrame()
    finally:
        indicators.root.removeNode()


def test_hex_on_ray_finds_the_top_the_ray_meets():
    """The pick with no window: a ray down on a hex finds it, and a hill in front of a
    lower hex hides it."""
    from slwindow3d.mesh import HEIGHT_PER_LEVEL, hex_on_ray, hex_world

    board = _board()
    board["hexes"][2]["elevation"] = 2
    cx, cy = hex_world(board["hexes"][1]["center"])
    assert hex_on_ray(board, (cx, cy, 50.0), (cx, cy, -50.0)) == "B1"
    # A ray that meets the level 0 plane in the footprint of the hill hex did not meet a
    # top there: the hill top is above it, and the ray meets that top first.
    hx, hy = hex_world(board["hexes"][2]["center"])
    assert hex_on_ray(board, (hx, hy, 50.0), (hx, hy, -50.0)) == "C1"
    # A slanted ray that passes the hill top and lands on the ground next to it.
    top = 2 * HEIGHT_PER_LEVEL
    assert hex_on_ray(board, (hx + 3.0, hy, top + 10.0), (hx + 3.0 - 0.001, hy, top - 10.0)) == "D1"
    # A ray off the board, and a ray parallel to the tops, find nothing.
    assert hex_on_ray(board, (cx, cy + 40.0, 50.0), (cx, cy + 40.0, -50.0)) is None
    assert hex_on_ray(board, (cx, cy, 5.0), (cx + 10.0, cy, 5.0)) is None


def test_a_click_pins_the_focus_and_the_pointer_asks_the_line_of_sight(app):
    """The click and the pointer of the 3D window, through the same model as the 2D one."""
    from types import SimpleNamespace as NS

    board = _board()
    app.set_board(board)
    asked: list[tuple[str, str]] = []
    indicators = Indicators(app.render, ask_los=lambda a, b: asked.append((a, b)))
    indicators.set_board(board)
    try:
        units = [_unit(1, 0, "A1"), _unit(3, 0, "A1"), _unit(2, 1, "E1")]
        snapshot = _snapshot(board, units)
        app._snapshot = snapshot
        # A click on the stack takes the top unit, a second click the next one, and a
        # click on an empty hex clears the pin.
        app.click("A1")
        assert app.pinned == 1
        app.click("A1")
        assert app.pinned == 3
        app.click("C1")
        assert app.pinned is None
        app.click("A1")
        app.clear_focus()
        assert app.pinned is None
        # The pin and the pointer reach the model: the focus is the pinned unit, and the
        # line of sight from it to the pointer hex is one question to the host.
        indicators.pinned = 1
        indicators.pointer_hex = "E1"
        overlay = indicators.update(snapshot, now=1.0)
        assert overlay.focus == 1 and overlay.focus_hex == "A1"
        assert asked == [("A1", "E1")]
        los = {("A1", "E1"): {"clear": False, "traced": ["B1", "C1", "D1", "E1"], "blocking_hex": "C1"}}
        answered = indicators.update(_snapshot(board, units, los=los), now=1.2)
        assert answered.shades["B1"] == model.TONE_LOS
        assert answered.shades["C1"] == model.TONE_LOS_BLOCKED
        assert "D1" not in answered.shades
        # The window holds the pin and the pointer, and the poll task hands them to the
        # overlay each frame.
        app.pinned = 1
        app.pointer_hex = "E1"
        # The counters of a frame need the whole face of a unit, so the poll gives a view
        # with no unit: the overlay is the thing under test here, not the cards.
        app._poll = lambda: NS(board=board, view={"units": []}, frame_id="f2", legal=[], log=[], los=los, active=0, phase="movement")
        app._last_frame_id = None
        app._poll_task(NS(cont=0))
        assert app.indicators is not None
        assert app.indicators.pinned == 1 and app.indicators.pointer_hex == "E1"
        app._poll = None
        app.graphicsEngine.renderFrame()
    finally:
        indicators.root.removeNode()


def test_toggles_hide_and_show(app):
    assert app.indicators is not None
    assert app.indicators.enabled is True
    app._toggle_indicators()
    assert app.indicators.enabled is False
    assert app.indicator_root.isHidden()
    app._toggle_indicators()
    assert app.indicators.enabled is True
    assert not app.indicator_root.isHidden()
    options_before = app.indicators.options
    app._toggle_options()
    assert app.indicators.options is (not options_before)
    app._toggle_options()  # leave it as it was for the other tests


def test_update_never_raises_on_bad_snapshot(app):
    assert app.indicators is not None
    bad = SimpleNamespace(active=0, phase="fire", view={"units": []}, legal=[], log=[{"kind": "fire"}])
    app.indicators.update(bad)
    app.indicators.update(None)
    app.indicators.update(SimpleNamespace(view="not a view"))
    app.indicators.sweep()
