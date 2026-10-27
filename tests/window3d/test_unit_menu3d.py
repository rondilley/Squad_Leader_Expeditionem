"""The menu of a unit and the Undo button of the 3D window, offscreen, with a host in the
process. The person holds the two seats (hot seat)."""

from __future__ import annotations

import pytest

pytest.importorskip("panda3d")

from tests.window3d.test_play3d import app, connect, show, wait_for  # noqa: E402,F401

from slagents.base import decide  # noqa: E402
from slagents.registry import make_agent  # noqa: E402
from slcli.play import build_engine  # noqa: E402
from slhost.server import Host  # noqa: E402
from slwindow import unitmenu  # noqa: E402
from slwindow.panel import UNDO_ROW  # noqa: E402

SCENARIO = "lib01_grain_office"


def _to_a_fire(host) -> int:
    """Play with v1 to a fire phase where a unit of the side can fire. Return that unit."""
    game = host.game
    agents = {p: make_agent("v1", game.engine, 1, p) for p in (0, 1)}
    for _ in range(4000):
        frame = game.engine.legal_commands(game.state)
        if game.state.phase in ("prep_fire", "defensive_fire") and game.state.fire_group is None:
            fire = [c for c in frame.commands if c.command.action == "group_add"]
            if fire:
                return fire[0].command.units[0]
        game.apply(frame.frame_id, decide(agents[frame.player], game.state, frame))
    raise AssertionError("no fire phase with a target")


def _centre(rect) -> tuple[int, int]:
    return (rect.x + rect.width // 2, rect.y + rect.height // 2)


def test_the_menu_plays_a_fire_command_and_the_undo_button_takes_it_back(app):
    host = Host(build_engine(SCENARIO), seed=1)
    firer = _to_a_fire(host)
    embedded, client = connect(app, host)
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal))
        app.show_snapshot(snapshot)
        app.open_menu(firer)
        assert app.menu_unit == firer and app.pinned == firer
        assert app._menu is not None and app._menu.rect is not None, "the menu is on the screen"
        rows = app.menu_rows()
        assert unitmenu.MenuRow(unitmenu.ROW_HEADER, "Fire") in rows
        fire = next(rect for rect, row in app._menu_hits if row.kind == unitmenu.ROW_COMMAND and " fires " in row.text)
        before = len(host.game.commands)
        assert app.click_menu(_centre(fire))
        assert app.menu_unit is None, "a choice closes the menu"
        snapshot = wait_for(client, lambda s, before=snapshot.frame_id: s.frame_id != before)
        app.show_snapshot(snapshot)
        assert len(host.game.commands) == before + 1
        assert host.game.commands[-1]["payload"]["action"] in ("group_add", "group_add_weapon")

        # The fire group is not resolved yet, so the Undo button takes the add back.
        snapshot = wait_for(client, lambda s: s.can_undo)
        app.show_snapshot(snapshot)
        undo = next(rect for rect, index in app._hud_rows if index == UNDO_ROW)
        assert app.click_panel(_centre(undo))
        wait_for(client, lambda s: s.frame_id != snapshot.frame_id)
        assert len(host.game.commands) == before

        # Escape closes the menu before it clears anything else.
        app.show_snapshot(client.snapshot())
        app.open_menu(firer)
        app.escape()
        assert app.menu_unit is None and app.pinned == firer
    finally:
        client.stop()
        embedded.stop()
        app.client = None
