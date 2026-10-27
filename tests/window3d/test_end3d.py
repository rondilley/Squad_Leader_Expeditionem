"""The box of the end of the game in the 3D window, offscreen, with a host in the process."""

from __future__ import annotations

import dataclasses

import pytest

pytest.importorskip("panda3d")

from tests.window3d.test_play3d import app, connect, wait_for  # noqa: E402,F401

from slcli.play import build_engine  # noqa: E402
from slhost.server import Host  # noqa: E402

SIDES = {"0": {"name": "Russian", "controller": "human"}, "1": {"name": "German", "controller": "computer"}}
OVER = {
    "result": 0,
    "winner_name": "Russian",
    "conditions": [],
    "cause": "the Russian side controls 1 hex of the building",
    "turn": 5,
    "casualties": {},
}


def _clean(app) -> None:
    """The window is shared with the tests after this one: close the end box, and take the
    set up tray and the panel of the frames of this test off the screen. A screenshot test
    after this one renders the whole window."""
    app.close_end()
    app.end_closed = False
    if app._tray is not None:
        app._tray.hide()
    app._tray_key = None
    if app._hud is not None:
        app._hud.destroy()
        app._hud = None
    app._hud_key = None


def test_the_end_box_opens_at_the_end_and_escape_closes_it(app):
    host = Host(build_engine("lib01_grain_office"), seed=1)
    embedded, client = connect(app, host)
    try:
        live = wait_for(client, lambda s: bool(s.legal))
        over = dataclasses.replace(live, game_over=True, over=OVER, sides=SIDES, turn=5)
        app.end_closed = False
        app.show_snapshot(over)
        assert app.end_open(), "the end box is on the screen"
        assert app._end_key[0].headline == "You won."
        app.escape()
        assert not app.end_open() and app.end_closed
        app.show_snapshot(over)
        assert not app.end_open(), "a closed end box stays closed"
    finally:
        _clean(app)
        client.stop()
        embedded.stop()
        app.client = None


def test_a_snapshot_of_a_game_that_is_not_over_closes_an_old_end_box(app):
    host = Host(build_engine("lib01_grain_office"), seed=1)
    embedded, client = connect(app, host)
    try:
        live = wait_for(client, lambda s: bool(s.legal))
        app.show_snapshot(dataclasses.replace(live, game_over=True, over=OVER, sides=SIDES, turn=5))
        assert app.end_open()
        # The next game in the same window: its first frame closes the box of the last one.
        app.show_snapshot(live)
        assert not app.end_open() and not app.end_closed
    finally:
        _clean(app)
        client.stop()
        embedded.stop()
        app.client = None


def test_the_victory_conditions_button_shows_the_box_and_the_strong_hexes(app):
    from slwindow import overlay
    from slwindow.panel import OBJECTIVES_ROW

    host = Host(build_engine("lib01_grain_office"), seed=1)
    embedded, client = connect(app, host)
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal) and bool(s.objectives))
        app.show_snapshot(snapshot)
        office = snapshot.objectives[0]["hexes"]
        assert app.indicators is not None
        assert all(app.indicators.overlay.shades.get(h) in (overlay.TONE_OBJECTIVE, overlay.TONE_SETUP) for h in office)
        assert any(index == OBJECTIVES_ROW for _rect, index in app._hud_rows), "the panel has the button"
        app.toggle_objectives()
        assert app.objectives_open(), "the box is on the screen"
        app.indicators.update(snapshot)
        assert all(app.indicators.overlay.shades.get(h) == overlay.TONE_OBJECTIVE_ON for h in office)
        app.escape()
        assert not app.show_objectives and not app.objectives_open()
    finally:
        if app.show_objectives:
            app.toggle_objectives()
        _clean(app)
        client.stop()
        embedded.stop()
        app.client = None
