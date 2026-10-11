"""The fire animations on the live path, at the zoom the window opens with.

The owner watched two computers play and saw no animation. The effects did start; they were
a few pixels at the opening zoom and lasted 0.2 seconds. These tests take the path of the
live window (a host with two computer opponents, the window's client, the window) and read
the pixels at the opening camera distance.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("panda3d")
pytest.importorskip("pygame")

from panda3d.core import PNMImage, loadPrcFileData  # noqa: E402

loadPrcFileData("", "window-type offscreen")
loadPrcFileData("", "win-size 320 240")
loadPrcFileData("", "audio-library-name null")

from slcli.play import build_engine, make_agent  # noqa: E402
from slcore.view import board_document  # noqa: E402


@pytest.fixture(scope="module")
def app():
    import builtins

    from slwindow3d.app import Board3DApp

    existing = getattr(builtins, "base", None)
    if isinstance(existing, Board3DApp):
        yield existing
        return
    instance = Board3DApp(None)
    yield instance
    instance.destroy()


def test_two_computers_playing_start_fire_animations_in_the_window(app):
    from slhost.server import Host
    from slwindow.client import HostClient
    from slwindow.embedded import start

    engine = build_engine("s01_guards_counterattack")
    agents = {seat: make_agent("v1", engine, 2, seat) for seat in (0, 1)}
    host = Host(engine, seed=2, hot_seat=True, agents=agents, agent_delay=0.0)
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, display_name="watcher")
    app.set_board(board_document(engine.board))
    app._last_frame_id = None
    app._poll = client.snapshot
    if not app.taskMgr.hasTaskNamed("poll-task"):
        app.taskMgr.add(app._poll_task, "poll-task")
    effects = app.indicators.effects
    started = []
    original = effects.launch

    def counting(shot, key="", now=None):
        made = original(shot, key, now)
        if made:
            started.append(shot.kind)
        return made

    effects.launch = counting
    client.start()
    try:
        deadline = time.monotonic() + 40.0
        while not started and time.monotonic() < deadline:
            app.taskMgr.step()
            time.sleep(0.002)
        assert started, "two computers played and no fire animation started in the window"
        # The animation is on the screen at the zoom the window opens with.
        app.reset_view()
        app.taskMgr.step()
        assert effects.zoom > 1.0
    finally:
        effects.launch = original
        app.taskMgr.remove("poll-task")
        app._poll = None
        client.stop()
        embedded.stop()
        effects.clear()


def _screen_span(app, centre, length_world: float, window_width: int = 1500) -> float:
    """The length in pixels, in a window this wide, of a world segment of this length that
    lies across the screen at `centre`, seen through the window's lens."""
    from panda3d.core import Point2, Point3

    a = Point3(centre[0] - length_world / 2.0, centre[1], centre[2])
    b = Point3(centre[0] + length_world / 2.0, centre[1], centre[2])
    lens = app.cam.node().getLens()
    pa, pb = Point2(), Point2()
    assert lens.project(app.cam.getRelativePoint(app.render, a), pa)
    assert lens.project(app.cam.getRelativePoint(app.render, b), pb)
    return abs(pb.x - pa.x) / 2.0 * window_width


def test_a_tracer_is_thin_but_visible_at_the_opening_zoom(app):
    """The owner saw no animation when a tracer was a few pixels long and lived 0.2 s, and
    then found the tracers too wide and crude when each grew with the zoom. A tracer at the
    zoom the window opens with must be a fine line: one to three and a half pixels wide and
    at least twenty pixels long, in a window 1500 pixels wide."""
    from slwindow3d.effects import zoom_for
    from slwindow3d.firekinds import MG, RIFLE, Shot

    engine = build_engine("s04_armor_probe")
    app.set_board(board_document(engine.board))
    app.reset_view()
    app._place_camera()
    effects = app.indicators.effects
    effects.zoom = zoom_for(app.distance)
    try:
        for kind, size in ((MG, 3), (MG, 1), (RIFLE, 1)):
            effects.clear()
            effects.launch(Shot(kind, "D3", "J3", size, True, "german"), key=f"{kind}{size}", now=0.0)
            effects.step(0.1)
            tracers = [p for p in effects.particles if p.stretch > 3.0 and not p.node.isHidden()]
            assert tracers, f"no {kind} tracer in flight"
            for p in tracers:
                width = p.radius(0.5) * effects.zoom
                centre = p.path(0.5)
                width_px = _screen_span(app, centre, width)
                length_px = _screen_span(app, centre, width * p.stretch)
                assert 1.0 <= width_px <= 3.5, f"{kind} tracer is {width_px:.1f} pixels wide"
                assert length_px >= 20.0, f"{kind} tracer is {length_px:.1f} pixels long"
    finally:
        effects.clear()
