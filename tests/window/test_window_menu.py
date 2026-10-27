"""The menu of a unit and the Undo button of the pygame window, with a host in the process.

The person holds the two seats (hot seat). The test plays with v1 to a fire phase, then
drives the window with the events a person makes: a right click on a counter, a click on a
row of the menu, and a click on the Undo button. The host applies each command, so the
test reads the result in the authoritative state.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slagents.base import decide  # noqa: E402
from slagents.registry import make_agent  # noqa: E402
from slcli.play import build_engine  # noqa: E402
from slcore import geometry  # noqa: E402
from slhost.server import Host  # noqa: E402
from slwindow import panel, unitmenu  # noqa: E402
from slwindow.app import Window  # noqa: E402
from slwindow.client import HostClient  # noqa: E402
from slwindow.embedded import start  # noqa: E402

from tests.window.test_window_play_v2 import key, step_with, wait_for  # noqa: E402

SCENARIO = "lib01_grain_office"
SIZE = (1200, 900)


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


@pytest.fixture()
def fire_game():
    host = Host(build_engine(SCENARIO), seed=1)
    firer = _to_a_fire(host)
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, "test window")
    client.start()
    window = Window(client, size=SIZE, caption="test")
    try:
        yield host, firer, client, window
    finally:
        client.stop()
        embedded.stop()
        pygame.quit()


def _pixel_of(window: Window, snapshot, hex_id: str) -> tuple[int, int]:
    hexagon = next(h for h in snapshot.board["hexes"] if h["id"] == hex_id)
    x, y = window.state.camera.to_screen(*hexagon["center"])
    return int(x), int(y)


def _centre_in(window: Window, rect) -> tuple[int, int]:
    box = window.state.menu_rect
    return (box.left + rect.x + rect.width // 2, box.top + rect.y + rect.height // 2)


def test_a_right_click_opens_the_menu_and_a_row_plays_its_command(fire_game):
    host, firer, client, window = fire_game
    snapshot = wait_for(client, lambda s: bool(s.legal) and s.board is not None)
    step_with(window, snapshot)
    here = geometry.hex_id(*host.game.state.units[firer].hex)
    window.state.pinned = firer
    window.right_click(_pixel_of(window, snapshot, here), snapshot)
    assert window.state.menu_unit == firer and window.state.pinned == firer
    step_with(window, snapshot)
    assert window.state.menu_rect is not None, "the menu is on the window"
    assert unitmenu.MenuRow(unitmenu.ROW_HEADER, "Fire") in window.menu_rows(snapshot)
    fire = next(rect for rect, row in window.state.menu_hits if row.kind == unitmenu.ROW_COMMAND and " fires " in row.text)
    before = len(host.game.commands)
    window.click(_centre_in(window, fire), snapshot)
    assert window.state.menu_unit is None, "a choice closes the menu"
    snapshot = wait_for(client, lambda s, old=snapshot.frame_id: s.frame_id != old and s.can_undo)
    assert len(host.game.commands) == before + 1
    assert host.game.commands[-1]["payload"]["action"] in ("group_add", "group_add_weapon")

    # The Undo button of the panel takes the add back: no die rolled.
    step_with(window, snapshot)
    undo = next(rect for rect, index in window.rows if index == panel.UNDO_ROW)
    window.click(undo.center, snapshot)
    wait_for(client, lambda s, old=snapshot.frame_id: s.frame_id != old)
    assert len(host.game.commands) == before


def test_ctrl_and_space_opens_the_menu_and_about_shows_the_unit(fire_game):
    host, firer, client, window = fire_game
    snapshot = wait_for(client, lambda s: bool(s.legal) and s.board is not None)
    step_with(window, snapshot)
    window.state.pinned = firer
    window.key(key(pygame.K_SPACE, " ", pygame.KMOD_CTRL), snapshot)
    assert window.state.menu_unit == firer
    assert window.chooser.filter_text == "", "the space of Ctrl and Space is no filter text"
    step_with(window, snapshot)
    about = next(rect for rect, row in window.state.menu_hits if row.kind == unitmenu.ROW_ABOUT)
    window.click(_centre_in(window, about), snapshot)
    assert window.state.about_unit == firer and window.state.menu_unit is None
    step_with(window, snapshot)
    assert window.state.about_rect is not None, "the about box is on the window"
    window.key(key(pygame.K_ESCAPE), snapshot)
    assert window.state.about_unit is None and window.state.pinned == firer, "Escape closes the box first"


def _answer(window: Window, client, snapshot, unit_id: int):
    """Draw a frame so the overlay asks for the options, wait for the answer, and draw it."""
    step_with(window, snapshot)
    snapshot = wait_for(client, lambda s: unit_id in s.options)
    step_with(window, snapshot)
    return snapshot


def test_a_unit_in_focus_shades_its_field_of_fire(fire_game):
    host, firer, client, window = fire_game
    snapshot = wait_for(client, lambda s: bool(s.legal) and s.board is not None)
    window.state.pinned = firer
    snapshot = _answer(window, client, snapshot, firer)
    answer = snapshot.options[firer]
    assert answer["kind"] == "fire" and answer["normal"]
    shades = window.overlay.shades
    assert any(shades.get(h) == "field" for h in answer["normal"])
    targets = {c["payload"]["hex"] for c in snapshot.legal if firer in c["payload"].get("units", []) and c["payload"].get("hex")}
    assert targets and all(shades.get(h) == "target" for h in targets), "a legal target keeps its strong tone"


@pytest.fixture()
def move_game():
    host = Host(build_engine(SCENARIO), seed=1)
    game = host.game
    agents = {p: make_agent("v1", game.engine, 1, p) for p in (0, 1)}
    while game.state.phase != "movement":
        frame = game.engine.legal_commands(game.state)
        game.apply(frame.frame_id, decide(agents[frame.player], game.state, frame))
    frame = game.engine.legal_commands(game.state)
    mover = next(c.command.units[0] for c in frame.commands if c.command.action == "move")
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, "test window")
    client.start()
    window = Window(client, size=SIZE, caption="test")
    try:
        yield host, mover, client, window
    finally:
        client.stop()
        embedded.stop()
        pygame.quit()


def test_a_click_on_a_pale_blue_hex_moves_the_unit_there(move_game):
    host, mover, client, window = move_game
    snapshot = wait_for(client, lambda s: bool(s.legal) and s.board is not None)
    window.state.pinned = mover
    snapshot = _answer(window, client, snapshot, mover)
    reach = snapshot.options[mover]["reach"]
    steps = {c["payload"]["hex"] for c in snapshot.legal if c["payload"].get("action") == "move" and c["payload"]["units"] == [mover]}
    shades = window.overlay.shades
    assert all(shades.get(h) == "move" for h in steps)
    far = max(set(reach) - steps, key=lambda h: (reach[h], h))
    assert shades.get(far) == "reach"
    before = len(host.game.commands)
    window.click(_pixel_of(window, snapshot, far), snapshot)
    wait_for(client, lambda s: next(u for u in s.view["units"] if u["id"] == mover).get("hex") == far)
    assert geometry.hex_id(*host.game.state.units[mover].hex) == far
    assert len(host.game.commands) - before >= 2, "a far hex is more than one step"
