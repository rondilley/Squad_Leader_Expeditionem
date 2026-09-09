"""The desktop window against a real host: two computer opponents fight where you can see it.

The window starts a host inside the same process, joins it over a socket on the loopback
address, and draws each frame the host sends. The test reads the pixels of the window, so a
window that receives every frame and draws nothing fails.

The whole path runs here: the core, the host, the protocol, the socket, the client thread,
the camera, the board renderer, the counters, and the panel.
"""

from __future__ import annotations

import os
import time
from collections import Counter

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slcli.play import build_engine, make_agent  # noqa: E402
from slhost.server import Host  # noqa: E402
from slwindow import theme  # noqa: E402
from slwindow.app import Window  # noqa: E402
from slwindow.client import HostClient, HostUnreachable  # noqa: E402
from slwindow.embedded import start  # noqa: E402

SCENARIO = "s04_armor_probe"
SIZE = (900, 600)
JOIN_TIMEOUT = 15.0
MIN_DISTINCT_COLOURS = 40
MIN_PIXELS_OF_A_COLOUR = 200


def pump(window: Window, seconds: float) -> None:
    """Run the drawing loop for a while, the way the real window runs it."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        window.step()


def colours_of(surface: pygame.Surface) -> Counter:
    raw = pygame.image.tobytes(surface, "RGB")
    return Counter(tuple(raw[i : i + 3]) for i in range(0, len(raw), 3))


def wait_for(client: HostClient, test, timeout: float = JOIN_TIMEOUT):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        snapshot = client.snapshot()
        if test(snapshot):
            return snapshot
        if client.error is not None:
            raise client.error
        time.sleep(0.05)
    raise AssertionError(f"the host did not answer inside {timeout} seconds: {client.snapshot()}")


@pytest.fixture()
def watched_game():
    """A host with two computer opponents and a window that watches them."""
    engine = build_engine(SCENARIO)
    agents = {0: make_agent("v1", engine, 5, 0), 1: make_agent("v2", engine, 5, 1)}
    host = Host(engine, seed=5, agents=agents, agent_delay=0.0)
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, "test window")
    client.start()
    window = Window(client, size=SIZE, caption="test")
    try:
        yield engine, host, client, window
    finally:
        client.stop()
        embedded.stop()
        pygame.quit()


@pytest.mark.slow
def test_the_window_draws_the_board_and_the_counters_of_a_live_game(watched_game):
    engine, host, client, window = watched_game
    wait_for(client, lambda s: s.board is not None and s.view is not None)
    pump(window, 1.0)
    found = colours_of(window.surface)
    assert len(found) >= MIN_DISTINCT_COLOURS, f"the window has {len(found)} colours, which is nearly blank"
    for name in ("open", "stone_building"):
        colour = theme.TERRAIN[name]
        assert found[colour] >= MIN_PIXELS_OF_A_COLOUR, f"the window shows {found[colour]} pixels of {name}"
    drawn = {n: found[theme.NATIONAL[n]] for n in ("german", "russian") if found[theme.NATIONAL[n]] > 0}
    assert drawn, "the window shows no counter of either side"
    assert found[theme.PANEL] > 0, "the window shows no panel"


@pytest.mark.slow
def test_the_game_moves_on_while_the_window_watches(watched_game):
    engine, host, client, window = watched_game
    wait_for(client, lambda s: s.view is not None)
    first = client.snapshot()
    pump(window, 3.0)
    later = wait_for(client, lambda s: s.frames > first.frames + 3, timeout=20.0)
    assert later.frames > first.frames, "the host sent no new frame"
    assert host.commands_played > 0, "the two computer opponents played nothing"
    assert later.log, "the window received no action log"


@pytest.mark.slow
def test_the_window_shows_the_vehicles_of_the_armor_scenario(watched_game):
    engine, host, client, window = watched_game
    snapshot = wait_for(client, lambda s: s.view is not None and any(u["kind"] == "vehicle" for u in s.view["units"]))
    vehicles = [u for u in snapshot.view["units"] if u["kind"] == "vehicle"]
    assert len(vehicles) == 6
    pump(window, 1.0)
    found = colours_of(window.surface)
    assert found[theme.VEHICLE_EDGE] > 0, "no vehicle counter is drawn"


@pytest.mark.slow
def test_a_click_on_a_vehicle_shows_its_covered_arc(watched_game):
    engine, host, client, window = watched_game
    snapshot = wait_for(
        client,
        lambda s: s.view is not None and any(u["kind"] == "vehicle" and u["hex"] for u in s.view["units"]),
    )
    window.step()
    vehicle = next(u for u in snapshot.view["units"] if u["kind"] == "vehicle" and u["hex"])
    board = snapshot.board
    centre = next(h["center"] for h in board["hexes"] if h["id"] == vehicle["hex"])
    position = window.state.camera.to_screen(*centre)
    window.click((int(position[0]), int(position[1])), snapshot)
    assert window.state.arc_for == vehicle["id"], "a click on a vehicle picks it"
    assert window.state.selected_hex == vehicle["hex"], "a click picks the hex under it"
    window.step()
    # The arc shading itself is measured in `test_the_covered_arc_shades_the_board`, where
    # the board does not change between the two pictures. Here the two computer opponents
    # keep playing, so this test proves the click reaches the renderer and it still draws.
    found = colours_of(window.surface)
    assert found[theme.TERRAIN["open"]] > 0 and found[theme.VEHICLE_EDGE] > 0


def test_a_window_with_no_host_says_so_and_does_not_draw_a_board():
    """A boundary error is typed and named, and never a blank board with no cause."""
    client = HostClient("ws://127.0.0.1:1/", "none", "test window")
    client.start()
    end = time.monotonic() + 15.0
    while time.monotonic() < end and client.error is None:
        time.sleep(0.05)
    client.stop()
    assert isinstance(client.error, HostUnreachable), client.error
    assert "127.0.0.1:1" in str(client.error)
    assert client.snapshot().board is None


@pytest.fixture()
def hot_seat_game():
    """A host with no computer opponent, so a person at the window holds both seats."""
    engine = build_engine("s04_armor_probe")
    host = Host(engine, seed=5)
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, "test window")
    client.start()
    window = Window(client, size=SIZE, caption="test")
    try:
        yield engine, host, client, window
    finally:
        client.stop()
        embedded.stop()
        pygame.quit()


@pytest.mark.slow
def test_a_person_at_the_window_can_play_a_command(hot_seat_game):
    """The window sends an intent, the host applies it, and the next frame comes back.

    This is the path a person uses. Everything else in this file watches a game that two
    computer opponents play, and a window that can only watch is not a window to play in.
    """
    engine, host, client, window = hot_seat_game
    snapshot = wait_for(client, lambda s: s.legal and s.frame_id)
    window.step()
    before = host.game.state.seq
    rows = window.rows
    assert rows, "the panel drew no command row for a person to click"
    row, index = rows[0]
    window.click((row.centerx, row.centery), snapshot)
    later = wait_for(client, lambda s: s.frame_id != snapshot.frame_id, timeout=20.0)
    assert host.game.state.seq > before, "the host applied no command"
    assert later.legal, "the host sent no new legal list"
    window.step()
    found = colours_of(window.surface)
    assert found[theme.TERRAIN["open"]] > 0, "the window stopped drawing after the command"


@pytest.mark.slow
def test_the_window_refuses_a_command_the_host_did_not_send(hot_seat_game):
    """AR-06: the window sends an identity from the legal list and never one of its own."""
    engine, host, client, window = hot_seat_game
    snapshot = wait_for(client, lambda s: s.legal and s.frame_id)
    before = host.game.state.seq
    window.send(len(snapshot.legal) + 5, snapshot)
    window.step()
    assert host.game.state.seq == before, "the window sent something that was not on the list"
