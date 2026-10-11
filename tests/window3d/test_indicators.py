"""Tests for the tactical action indicators of the 3D window.

They need the `view3d` extra. Without panda3d the whole module is skipped, the same way the
other 3D window tests skip without it. The window opens offscreen (`window-type offscreen`),
so the test needs no display.

The test builds a small board and a constructed snapshot (a simple namespace) with a move
event and a fire event, calls the overlay update, and asserts it runs without error and that
the indicator root gains children.
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

from slwindow3d.indicators import (  # noqa: E402
    COLOR_RESULT_GREY,
    COLOR_RESULT_ORANGE,
    COLOR_RESULT_RED,
    result_color,
)


def _board():
    """A tiny flat board with three hexes in a row, ids A1, A2, A3."""
    hexes = []
    for i in range(3):
        hexes.append(
            {
                "id": f"A{i + 1}",
                "col": i,
                "row": 0,
                "center": [i * 6, 0],
                "terrain": "open",
                "elevation": 0,
            }
        )
    return {"name": "tiny", "cols": 3, "rows": 1, "hexes": hexes, "terrain": {}}


def _snapshot(board, log):
    """A snapshot namespace like the host client gives: active side, phase, view, legal, log."""
    view = {
        "units": [
            {"id": 1, "player": 0, "hex": "A1", "kind": "squad"},
            {"id": 2, "player": 1, "hex": "A3", "kind": "squad"},
        ]
    }
    # The shape the host sends: an id and a payload for each entry.
    legal = [
        {"id": "c1", "payload": {"action": "move", "units": [1], "hex": "A2"}},
        {"id": "c2", "payload": {"action": "group_add", "units": [1], "hex": "A3"}},
    ]
    return SimpleNamespace(
        board=board,
        view=view,
        frame_id="f1",
        active=0,
        phase="movement",
        legal=legal,
        log=log,
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


def test_result_color_maps_the_kinds():
    assert result_color({"eliminated"}) == COLOR_RESULT_RED
    assert result_color({"broken"}) == COLOR_RESULT_RED
    assert result_color({"malfunction"}) == COLOR_RESULT_ORANGE
    assert result_color({"morale_pass"}) == COLOR_RESULT_GREY
    assert result_color(set()) == COLOR_RESULT_GREY


def test_update_draws_move_and_fire_offscreen(app):
    board = _board()
    app.set_board(board)
    app.indicators.clear()
    # The first log read only seeds the seen set (a watcher joining mid-game does not replay the
    # past), so prime with an empty log the way a game does at its start; then the events below
    # are new and draw.
    app.indicators.update(_snapshot(board, []))
    assert app.indicators.action_root.getNumChildren() == 0
    try:
        assert app.indicators is not None
        log = [
            {"rule_id": "5.5", "kind": "move", "data": {"unit": 1, "from": "A1", "to": "A2"}},
            {
                "rule_id": "10.6",
                "kind": "fire",
                "data": {
                    "target": "A3",
                    "members": [{"unit": 1, "weapon": None, "halves": 4}],
                    "firepower": 4,
                    "column": "4",
                    "phase": "prep_fire",
                },
            },
            {"rule_id": "12.3", "kind": "broken", "data": {"unit": 2}},
        ]
        snapshot = _snapshot(board, log)
        # The unit moved to A2, so the view reflects that when the fire is drawn.
        snapshot.view["units"][0]["hex"] = "A2"
        app.indicators.update(snapshot)
        # The overlay must have gained nodes: the frame layer (active markers, options) and
        # the action layer (the move arrow and the fire line).
        assert app.indicator_root.getNumChildren() > 0
        assert app.indicators.action_root.getNumChildren() >= 2  # one move node, one fire node
        assert app.indicators.frame_root.getNumChildren() > 0
        # A second update with the same log adds no new action (the tail is already seen).
        before = app.indicators.action_root.getNumChildren()
        app.indicators.update(snapshot)
        assert app.indicators.action_root.getNumChildren() == before
        # The render frame must not raise with the overlay in the scene.
        for _ in range(2):
            app.graphicsEngine.renderFrame()
    finally:
        app.indicators.clear()


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
    # A malformed snapshot (a log entry with no data) must not raise into the poll task.
    bad = SimpleNamespace(active=0, phase="fire", view={"units": []}, legal=[], log=[{"kind": "fire"}])
    app.indicators.update(bad)
    app.indicators.update(None)


def test_options_overlay_draws_from_the_legal_list_the_host_sends(app):
    """The host sends each legal entry as an id and a payload. The options overlay read the
    action from the top of the entry, found none, and drew nothing in a live game."""
    board = _board()
    app.indicators.set_board(board)
    try:
        snapshot = _snapshot(board, [])
        # A window that plays starts with the overlay off; this test reads it on.
        app.indicators.options = True
        app.indicators.update(snapshot)
        with_options = app.indicators.frame_root.getNumChildren()
        app._toggle_options()
        app.indicators.update(snapshot)
        without_options = app.indicators.frame_root.getNumChildren()
        app._toggle_options()
        # One ring for the move to A2 and one line for the fire at A3.
        assert with_options - without_options == 2
    finally:
        app.indicators.clear()


def test_a_hex_outline_lies_inside_its_hex_and_marks_no_disc_over_the_counter(app):
    """The board style: an outline is a thin band just inside the hex edge. Its inner edge
    is far from the centre, so the counter and the terrain in the middle stay in view."""
    import math

    from panda3d.core import GeomVertexReader

    from slwindow3d.indicators import HEX_RADIUS, WIDTH_OUTLINE

    board = _board()
    app.indicators.set_board(board)
    try:
        node = app.indicators._hex_outline(app.indicators.frame_root, "A2", (1, 1, 1, 1), WIDTH_OUTLINE)
        assert node is not None
        cx, cy, _ = app.indicators._ground("A2")
        geom = node.node().getGeom(0)
        reader = GeomVertexReader(geom.getVertexData(), "vertex")
        distances = []
        while not reader.isAtEnd():
            v = reader.getData3()
            distances.append(math.hypot(v.x - cx, v.y - cy))
        assert max(distances) <= HEX_RADIUS + 1e-6
        # The inner edge of the band is more than three quarters of the way out.
        assert min(distances) > HEX_RADIUS * 0.75
    finally:
        app.indicators.clear()


def test_the_result_word_of_a_fire_comes_from_its_events():
    from slwindow3d.indicators import result_words

    def result(code):
        return {"kind": "fire_result", "data": {"result": code}}

    assert result_words([result("-")]) == "no effect"
    assert result_words([result("M")]) == "MC"
    assert result_words([result("1"), result("2")]) == "MC+2"
    assert result_words([result("2"), {"kind": "broken", "data": {}}]) == "BROKEN"
    assert result_words([result("KIA"), {"kind": "eliminated", "data": {}}]) == "KIA"
    assert result_words([]) == ""


def test_each_kind_of_fire_animates_and_leaves_no_node_behind(app):
    """Each kind starts its particles, moves them, and removes each one at its end."""
    from slwindow3d.firekinds import BLAST, FLAME, GRENADES, GUN, MG, OVERRUN, RIFLE, ROCKET, SMG, SMOKE, Shot

    board = _board()
    app.indicators.set_board(board)
    effects = app.indicators.effects
    try:
        counts = {}
        for kind in (RIFLE, SMG, MG, FLAME, ROCKET, GUN, BLAST, SMOKE, GRENADES, OVERRUN):
            made = effects.launch(Shot(kind, "A1", "A3", 2, True), key=kind, now=0.0)
            assert made > 0, f"{kind} made no particle"
            counts[kind] = made
            # The same event draws the same way.
            effects.clear()
            assert effects.launch(Shot(kind, "A1", "A3", 2, True), key=kind, now=0.0) == made
            assert effects.step(0.05) > 0
            app.graphicsEngine.renderFrame()
            assert effects.step(30.0) == 0
            assert effects.root.getNumChildren() == 0
        # A machine gun fires more rounds than rifles, and an HMG more than an LMG.
        assert counts[MG] > counts[RIFLE]
        light = effects.launch(Shot(MG, "A1", "A3", 1), key="l", now=0.0)
        effects.clear()
        heavy = effects.launch(Shot(MG, "A1", "A3", 3), key="h", now=0.0)
        effects.clear()
        assert heavy > light
        # A shot with no target hex on the board draws nothing.
        assert effects.launch(Shot(RIFLE, "A1", "Z99"), now=0.0) == 0
    finally:
        app.indicators.clear()
