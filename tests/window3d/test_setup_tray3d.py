"""The set up tray and the "about this unit" box of the 3D window, offscreen.

A host runs in the process, and the window joins it through the `HostClient`, as in
`test_play3d.py`. The person holds the two seats (hot seat), so the window shows the tray
for the side that sets up. Each test reads the result in the state of the host.
"""

from __future__ import annotations

import pytest

pytest.importorskip("panda3d")

from tests.window3d.test_play3d import app, connect, show, wait_for  # noqa: E402,F401

from slcli.play import build_engine  # noqa: E402
from slcore import geometry  # noqa: E402
from slhost.server import Host  # noqa: E402
from slwindow import setup  # noqa: E402
from slwindow3d import tray  # noqa: E402

SCENARIO = "lib01_grain_office"


def _hex_of(host, unit_id: int) -> str | None:
    unit = host.game.state.units[unit_id]
    return None if unit.hex is None else geometry.hex_id(*unit.hex)


def _new_frame(app, client, before: str):
    snapshot = wait_for(client, lambda s: s.frame_id != before)
    app.show_snapshot(snapshot)
    return snapshot


def test_a_counter_of_the_tray_goes_on_a_shaded_hex_and_comes_back(app):
    host = Host(build_engine(SCENARIO), seed=1)
    embedded, client = connect(app, host)
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal))
        app.show_snapshot(snapshot)
        assert app.in_setup()
        assert app._tray is not None and app._tray.rect is not None, "the tray is on the screen"
        units = [hit for hit in app._tray_hits if hit[1] == tray.ACTION_UNIT]
        assert [hit[2] for hit in units] == [13, 10, 11, 12, 14]

        # A click on the second 4-6-7 selects the counter that the legal list names.
        app.pick_tray(11)
        assert app.pinned == 11
        targets = setup.targets(snapshot.legal, 10)
        assert app.indicators is not None
        app.indicators.pinned = app.pinned
        shades = app.indicators.update(snapshot).shades
        assert targets and all(shades.get(h) == "setup" for h in targets), "each hex of the legal list is shaded"

        hex_id = sorted(targets)[0]
        app.click(hex_id)
        snapshot = _new_frame(app, client, snapshot.frame_id)
        assert _hex_of(host, 10) == hex_id
        # The selection goes on to the next identical counter.
        assert app.pinned == 11

        # A click on the placed counter takes it back to the tray.
        app.pinned = None
        app.click(hex_id)
        snapshot = _new_frame(app, client, snapshot.frame_id)
        assert _hex_of(host, 10) is None and not host.game.commands
        assert app.pinned == 10
    finally:
        client.stop()
        embedded.stop()
        app.client = None


def test_the_finish_button_ends_the_set_up_when_each_counter_is_on_the_board(app):
    host = Host(build_engine(SCENARIO), seed=1)
    embedded, client = connect(app, host)
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal))
        app.show_snapshot(snapshot)
        assert app.finish_setup() is False, "no end of the set up while a counter is off the board"
        for _ in range(5):
            item = next(i for i in app.tray_items() if not i.placed)
            app.pick_tray(item.unit_id)
            targets = setup.targets(snapshot.legal, item.offered)
            app.click(sorted(targets)[-1])
            snapshot = _new_frame(app, client, snapshot.frame_id)
        assert setup.can_finish(snapshot.legal) is not None
        finish = next(rect for rect, action, _ in app._tray_hits if action == tray.ACTION_FINISH)
        assert app.click_tray(finish.center)
        snapshot = wait_for(client, lambda s: s.active == 0)
        app.show_snapshot(snapshot)
        assert host.game.commands[-1]["payload"]["action"] == "end_setup"
    finally:
        client.stop()
        embedded.stop()
        app.client = None


def test_a_counter_dragged_from_the_tray_goes_on_the_hex_of_the_drop(app):
    host = Host(build_engine(SCENARIO), seed=1)
    embedded, client = connect(app, host)
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal))
        app.show_snapshot(snapshot)
        app.pick_tray(13)
        app.begin_carry(13, (0.0, 0.0))
        app._show_carried(56)
        assert app._carried is not None and app._carried.rect is not None, "the counter follows the pointer"
        hex_id = sorted(setup.targets(snapshot.legal, 13))[-1]
        assert app.drop(hex_id)
        assert app._carried.rect is None, "the picture goes at the drop"
        snapshot = _new_frame(app, client, snapshot.frame_id)
        assert _hex_of(host, 13) == hex_id
        # A drop on a hex that is not shaded places nothing.
        app.pick_tray(10)
        app.begin_carry(10, (0.0, 0.0))
        assert not app.drop(hex_id if hex_id not in setup.targets(snapshot.legal, 10) else "Z99")
        assert _hex_of(host, 10) is None
    finally:
        client.stop()
        embedded.stop()
        app.client = None


def test_a_press_a_move_and_a_release_of_the_mouse_drag_a_counter_to_a_hex(app, monkeypatch):
    host = Host(build_engine(SCENARIO), seed=1)
    embedded, client = connect(app, host)
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal))
        app.show_snapshot(snapshot)
        width, height = app._window_size()
        left, top = app._tray.rect[0], app._tray.rect[1]
        tile = next(rect for rect, action, unit_id in app._tray_hits if action == tray.ACTION_UNIT and unit_id == 13)
        # The pointer is in the -1 to 1 space of the window, as the mouse watcher gives it.
        place = {"pointer": ((left + tile.centerx) / width * 2 - 1, 1 - (top + tile.centery) / height * 2)}
        monkeypatch.setattr(app, "_pointer", lambda: place["pointer"])
        hex_id = sorted(setup.targets(snapshot.legal, 13))[0]
        monkeypatch.setattr(app, "hex_under_pointer", lambda: hex_id)
        app._drag_start("mouse1")
        assert app._carry == 13 and app.pinned == 13
        place["pointer"] = (0.0, 0.2)
        app._follow_carry()
        assert app._carried is not None and app._carried.rect is not None
        app._drag_stop("mouse1")
        assert app._carry is None
        snapshot = _new_frame(app, client, snapshot.frame_id)
        assert _hex_of(host, 13) == hex_id
    finally:
        client.stop()
        embedded.stop()
        app.client = None


def test_a_counter_dragged_on_the_board_moves_to_the_hex_of_the_drop(app):
    host = Host(build_engine(SCENARIO), seed=1)
    embedded, client = connect(app, host)
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal))
        app.show_snapshot(snapshot)
        targets = sorted(setup.targets(snapshot.legal, 13))
        first, second = targets[0], targets[-1]
        app.pick_tray(13)
        app.click(first)
        snapshot = _new_frame(app, client, snapshot.frame_id)
        assert _hex_of(host, 13) == first
        app.pinned = None
        assert app._grab_on_board(first) == 13, "a press on the counter picks it up"
        # The press sends the pick up, and the drop comes before the host answers it.
        app.lift(13)
        app.begin_carry(13, (0.0, 0.0))
        assert app.drop(second)
        assert app._pending_drop == (13, second)
        snapshot = _new_frame(app, client, snapshot.frame_id)
        assert app._pending_drop is None
        snapshot = _new_frame(app, client, snapshot.frame_id)
        assert _hex_of(host, 13) == second
        # With a counter of the tray selected, a press on its shaded hex is a placement.
        app.pick_tray(10)
        shaded = sorted(setup.targets(snapshot.legal, 10))
        assert app._grab_on_board(shaded[0]) is None
    finally:
        client.stop()
        embedded.stop()
        app.client = None


@pytest.mark.parametrize("mode", ["2d", "3d"])
def test_the_pointer_finds_the_hex_that_the_picture_shows_under_it(app, monkeypatch, mode):
    """The lens of the camera changes each frame (the film offset of the panel and the
    tray), so the ray of the pointer goes through the lens that draws the picture."""
    from panda3d.core import Point2, Point3

    from slwindow3d.mesh import elevation_z, hex_world

    host = Host(build_engine(SCENARIO), seed=1)
    embedded, client = connect(app, host)
    # The offscreen window is 320 by 240 and the side panel is wider than that. A size of
    # the same shape gives the board a part of the window that the panel does not cover.
    monkeypatch.setattr(app, "_window_size", lambda: (1600, 1200))
    app._tray_key = None
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal))
        app.show_snapshot(snapshot)
        app.mode = mode
        app.reset_view()
        app._place_camera()
        lens = app.cam.node().getLens()
        assert lens.getFilmOffset() != (0, 0), "the tray moves the picture"
        place = {"pointer": (0.0, 0.0)}
        monkeypatch.setattr(app, "_pointer", lambda: place["pointer"])
        checked = 0
        for hexagon in snapshot.board["hexes"][::5]:
            wx, wy = hex_world(hexagon["center"])
            point = app.cam.getRelativePoint(app.render, Point3(wx, wy, elevation_z(int(hexagon.get("elevation", 0) or 0))))
            film = Point2()
            if not lens.project(point, film):
                continue
            place["pointer"] = (film[0], film[1])
            if app.panel_point() is not None or app._tray.point(app._pixel() or (-1, -1)) is not None:
                continue
            assert app.hex_under_pointer() == hexagon["id"]
            checked += 1
        assert checked >= 10
    finally:
        app.mode = "3d"
        client.stop()
        embedded.stop()
        app.client = None


def test_the_box_of_a_unit_opens_and_closes(app):
    host = Host(build_engine(SCENARIO), seed=1)
    embedded, client = connect(app, host)
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal))
        app.show_snapshot(snapshot)
        unit = next(u for u in snapshot.view["units"] if u["id"] == 13)
        app.show_about(unit)
        assert app.about_unit is unit
        assert app._about is not None and app._about.rect is not None
        app.escape()
        assert app.about_unit is None and app._about.rect is None
    finally:
        client.stop()
        embedded.stop()
        app.client = None


def test_a_machine_gun_dragged_onto_a_squad_goes_with_the_squad(app):
    host = Host(build_engine(SCENARIO), seed=1)
    embedded, client = connect(app, host)
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal))
        app.show_snapshot(snapshot)
        # The person holds the two seats: the Germans set up first, by the helper.
        app.auto_setup()
        snapshot = wait_for(client, lambda s: s.active == 0 and bool(s.legal))
        app.show_snapshot(snapshot)
        assert app.in_setup()
        app.pick_tray(8)
        assert app._tray_targets() == {}, "the MMG waits for the units"
        squad_hex = sorted(setup.targets(snapshot.legal, 3))[0]
        app.pick_tray(3)
        app.click(squad_hex)
        snapshot = _new_frame(app, client, snapshot.frame_id)
        app.pick_tray(8)
        assert set(app._tray_targets()) == {squad_hex}
        app.begin_carry(8, (0.0, 0.0))
        assert app.drop(squad_hex)
        snapshot = _new_frame(app, client, snapshot.frame_id)
        assert host.game.state.units[8].carrier == 3
        tile = next(rect for rect, action, unit_id in app._tray_hits if action == tray.ACTION_UNIT and unit_id == 8)
        assert tile is not None
    finally:
        client.stop()
        embedded.stop()
        app.client = None
