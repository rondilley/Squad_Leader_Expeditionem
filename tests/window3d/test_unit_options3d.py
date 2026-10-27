"""The options of a unit in the 3D window, offscreen, with a host in the process.

The window asks the host `options_request` for the counter of the tray and for a pinned
unit of the person's side (`slhost.options`). The tray says why a hex refused a counter,
and the overlay shades the hexes a unit reaches in the Movement Phase and its field of
fire. The person holds the two seats (hot seat).
"""

from __future__ import annotations

import pytest

pytest.importorskip("panda3d")

from tests.window3d.test_play3d import app, connect, show, wait_for  # noqa: E402,F401

from slagents.base import decide  # noqa: E402
from slagents.registry import make_agent  # noqa: E402
from slcli.play import build_engine  # noqa: E402
from slcore import geometry  # noqa: E402
from slhost.server import Host  # noqa: E402

SCENARIO = "lib01_grain_office"


def _answer(app, client, unit_id: int):
    """Show the snapshot so the overlay asks, then wait for the answer and show it."""
    snapshot = show(app, client)
    snapshot = wait_for(client, lambda s: unit_id in s.options)
    app.show_snapshot(snapshot)
    return snapshot


def test_a_drop_outside_the_area_says_where_the_counter_sets_up(app):
    host = Host(build_engine(SCENARIO), seed=1)
    embedded, client = connect(app, host)
    try:
        wait_for(client, lambda s: bool(s.legal))
        show(app, client)
        app.pick_tray(10)
        _answer(app, client, 10)
        app.begin_carry(10)
        assert app.drop("C3") is False
        assert app.refusal == (10, "C3")
        assert app.refusal_text() == (
            "C3 is outside the set up area. The 4-6-7 sets up in the largest stone building in columns U to EE."
        )
        assert host.game.commands == [], "nothing went on the board"
        # A counter that goes on a shaded hex clears the reason.
        snapshot = show(app, client)
        target = sorted(h for h in app._tray_targets())[0]
        app.click(target)
        assert app.refusal is None
        app.show_snapshot(wait_for(client, lambda s: s.frame_id != snapshot.frame_id))
    finally:
        client.stop()
        embedded.stop()
        app.client = None


def test_a_pinned_unit_shows_each_hex_it_reaches_in_the_movement_phase(app):
    host = Host(build_engine(SCENARIO), seed=1)
    game = host.game
    agents = {p: make_agent("v1", game.engine, 1, p) for p in (0, 1)}
    while game.state.phase != "movement":
        frame = game.engine.legal_commands(game.state)
        game.apply(frame.frame_id, decide(agents[frame.player], game.state, frame))
    frame = game.engine.legal_commands(game.state)
    mover = next(c.command.units[0] for c in frame.commands if c.command.action == "move")
    steps = {geometry.hex_id(*c.command.hex) for c in frame.commands if c.command.action == "move" and c.command.units == (mover,)}
    embedded, client = connect(app, host)
    try:
        wait_for(client, lambda s: bool(s.legal))
        app.pinned = mover
        snapshot = _answer(app, client, mover)
        reach = set(snapshot.options[mover]["reach"])
        assert steps < reach
        assert app.indicators is not None
        app.indicators.pinned = mover
        shades = app.indicators.update(snapshot).shades
        assert all(shades.get(h) == "move" for h in steps), "the next steps keep the strong tone"
        assert all(shades.get(h) in ("reach", "move", "focus", "track") for h in reach)
        assert any(shades.get(h) == "reach" for h in reach - steps), "the hexes past the next step are shaded"

        # A click on a pale hex moves the unit there, one legal step at a time.
        far = max(reach - steps, key=lambda h: (snapshot.options[mover]["reach"][h], h))
        before = len(host.game.commands)
        app.click(far)
        wait_for(client, lambda s: next(u for u in s.view["units"] if u["id"] == mover).get("hex") == far)
        assert geometry.hex_id(*host.game.state.units[mover].hex) == far
        assert len(host.game.commands) - before >= 2, "a far hex is more than one step"
        assert app.pinned == mover, "the unit stays in focus for its next move"
    finally:
        client.stop()
        embedded.stop()
        app.client = None
