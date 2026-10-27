"""The set up tray of the pygame window, with a host in the process.

The person holds the two seats (hot seat), so the window shows the tray for the side that
sets up. The tests drive the window with the events a person makes, and read the result in
the state of the host. The logic is the same as in the 3D window (`slwindow.traycontrol`).
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slcli.play import build_engine  # noqa: E402
from slcore import geometry  # noqa: E402
from slhost.server import Host  # noqa: E402
from slwindow import setup, traydraw  # noqa: E402
from slwindow.app import Window  # noqa: E402
from slwindow.client import HostClient  # noqa: E402
from slwindow.embedded import start  # noqa: E402

from tests.window.test_window_play_v2 import step_with, wait_for  # noqa: E402

SCENARIO = "lib01_grain_office"
SIZE = (1300, 900)


@pytest.fixture()
def tray_game():
    host = Host(build_engine(SCENARIO), seed=1)
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, "test window")
    client.start()
    window = Window(client, size=SIZE, caption="test")
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal) and s.board is not None)
        step_with(window, snapshot)
        yield host, client, window, snapshot
    finally:
        client.stop()
        embedded.stop()
        pygame.quit()


def _hex_of(host, unit_id: int) -> str | None:
    unit = host.game.state.units[unit_id]
    return None if unit.hex is None else geometry.hex_id(*unit.hex)


def _pixel_of(window: Window, snapshot, hex_id: str) -> tuple[int, int]:
    hexagon = next(h for h in snapshot.board["hexes"] if h["id"] == hex_id)
    x, y = window.state.camera.to_screen(*hexagon["center"])
    return int(x), int(y)


def _tile(window: Window, unit_id: int) -> tuple[int, int]:
    rect = next(r for r, action, unit in window._tray_hits if action == traydraw.ACTION_UNIT and unit == unit_id)
    return window.tray_rect.left + rect.centerx, window.tray_rect.top + rect.centery


def _button(window: Window, action: str) -> tuple[int, int]:
    rect = next(r for r, kind, _unit in window._tray_hits if kind == action)
    return window.tray_rect.left + rect.centerx, window.tray_rect.top + rect.centery


def _press(window: Window, snapshot, position, button: int = 1) -> None:
    window.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=button, pos=position), snapshot)


def _release(window: Window, snapshot, position, button: int = 1) -> None:
    window.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, button=button, pos=position), snapshot)


def _move(window: Window, snapshot, start, end) -> None:
    rel = (end[0] - start[0], end[1] - start[1])
    window.handle(pygame.event.Event(pygame.MOUSEMOTION, pos=end, rel=rel, buttons=(1, 0, 0)), snapshot)


def _click(window: Window, snapshot, position) -> None:
    _press(window, snapshot, position)
    _release(window, snapshot, position)


def _new_frame(window: Window, client, snapshot):
    snapshot = wait_for(client, lambda s, old=snapshot.frame_id: s.frame_id != old)
    step_with(window, snapshot)
    return snapshot


def test_a_counter_of_the_tray_goes_on_a_shaded_hex_and_comes_back(tray_game):
    host, client, window, snapshot = tray_game
    assert window.in_setup() and window.tray_rect is not None, "the tray is on the window"
    units = [unit for _rect, action, unit in window._tray_hits if action == traydraw.ACTION_UNIT]
    assert units == [13, 10, 11, 12, 14]
    # A click on the second 4-6-7 selects the counter that the legal list names.
    _click(window, snapshot, _tile(window, 11))
    assert window.state.pinned == 11
    step_with(window, snapshot)
    targets = setup.targets(snapshot.legal, 10, snapshot.view)
    assert targets and all(window.overlay.shades.get(h) == "setup" for h in targets)
    hex_id = sorted(targets)[0]
    _click(window, snapshot, _pixel_of(window, snapshot, hex_id))
    snapshot = _new_frame(window, client, snapshot)
    assert _hex_of(host, 10) == hex_id
    assert window.state.pinned == 11, "the selection goes on to the next identical counter"
    # A click on the placed counter takes it back to the tray.
    window.state.pinned = None
    _click(window, snapshot, _pixel_of(window, snapshot, hex_id))
    snapshot = _new_frame(window, client, snapshot)
    assert _hex_of(host, 10) is None and not host.game.commands


def test_a_drag_from_the_tray_places_the_counter_and_a_refused_drop_says_why(tray_game):
    host, client, window, snapshot = tray_game
    start_at = _tile(window, 13)
    _press(window, snapshot, start_at)
    # The answer of the host gives the cause of a refused hex.
    step_with(window, snapshot)
    snapshot = wait_for(client, lambda s: 13 in s.options)
    step_with(window, snapshot)
    outside = "C3"
    end = _pixel_of(window, snapshot, outside)
    _move(window, snapshot, start_at, end)
    _release(window, snapshot, end)
    assert window.refusal == (13, outside)
    assert window.refusal_text() == (
        "C3 is outside the set up area. The 9-2 sets up in the largest stone building in columns U to EE."
    )
    assert not host.game.commands
    # A drag to a shaded hex places it.
    target = sorted(setup.targets(snapshot.legal, 13, snapshot.view))[0]
    _press(window, snapshot, _tile(window, 13))
    end = _pixel_of(window, snapshot, target)
    _move(window, snapshot, _tile(window, 13), end)
    _release(window, snapshot, end)
    _new_frame(window, client, snapshot)
    assert _hex_of(host, 13) == target
    assert window.refusal is None


def test_set_up_for_me_places_and_ends_the_set_up_of_the_side(tray_game):
    host, client, window, snapshot = tray_game
    side = host.game.state.active
    _click(window, snapshot, _button(window, traydraw.ACTION_AUTO))
    wait_for(client, lambda s: host.game.state.active != side)
    actions = [c["payload"]["action"] for c in host.game.commands]
    assert actions == ["place"] * 5 + ["end_setup"]


def test_the_finish_button_ends_the_set_up_when_each_counter_is_on_the_board():
    host = Host(build_engine(SCENARIO), seed=1)
    game = host.game
    side = game.state.active
    for step in range(5):
        frame = game.engine.legal_commands(game.state)
        place = [c for c in frame.commands if c.command.action == "place"]
        game.apply(frame.frame_id, place[step * 7 % len(place)].id)
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, "test window")
    client.start()
    window = Window(client, size=SIZE, caption="test")
    try:
        snapshot = wait_for(client, lambda s: setup.can_finish(s.legal) is not None and s.board is not None)
        step_with(window, snapshot)
        assert game.state.active == side, "the host does not end the set up for the person"
        _click(window, snapshot, _button(window, traydraw.ACTION_FINISH))
        wait_for(client, lambda s: game.state.active != side)
        assert game.commands[-1]["payload"]["action"] == "end_setup"
    finally:
        client.stop()
        embedded.stop()
        pygame.quit()
