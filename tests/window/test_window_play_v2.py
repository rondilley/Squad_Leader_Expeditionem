"""The pygame window plays against a real host (H7, protocol version 2, slice 8).

Each test starts a host inside the process, joins it over a socket on the loopback
address, and drives the window with the events a person makes: a key, a click on a row,
a click on the board. The host applies the command, so a test reads the result in the
authoritative state and not in a record the window keeps.
"""

from __future__ import annotations

import asyncio
import os
import time

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slcli.play import build_engine, make_agent  # noqa: E402
from slhost.server import Host  # noqa: E402
from slwindow import choice, panel  # noqa: E402
from slwindow.app import Window  # noqa: E402
from slwindow.client import STATUS_GAME_OVER, HostClient, SessionRefused  # noqa: E402
from slwindow.embedded import start  # noqa: E402

SCENARIO = "s01_guards_counterattack"
SIZE = (1000, 900)
TIMEOUT = 30.0


def wait_for(client: HostClient, test, timeout: float = TIMEOUT):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        snapshot = client.snapshot()
        if test(snapshot):
            return snapshot
        if client.error is not None:
            raise client.error
        time.sleep(0.02)
    raise AssertionError(f"the host did not answer inside {timeout} seconds: {client.snapshot().notice}")


def key(code: int, text: str = "", mod: int = 0) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=code, unicode=text, mod=mod)


def type_text(window: Window, snapshot, text: str) -> None:
    for letter in text:
        window.key(key(pygame.key.key_code(letter) if letter.isalnum() else pygame.K_SPACE, letter), snapshot)


@pytest.fixture()
def hot_seat():
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=3)
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


def ready(client: HostClient):
    return wait_for(client, lambda s: bool(s.legal) and bool(s.frame_id))


def step_with(window: Window, snapshot) -> None:
    """One frame of the window on this snapshot, the way `Window.step` draws it."""
    window.chooser.sync(snapshot.frame_id, snapshot.legal)
    window.draw(snapshot)


# ------------------------------------------------------------------ the list


@pytest.mark.slow
def test_the_list_scrolls_and_a_row_far_down_the_list_plays(hot_seat):
    """H7: the list has no cap of 18 rows. Each legal command has a row a person reaches."""
    engine, host, client, window = hot_seat
    snapshot = ready(client)
    assert len(snapshot.legal) > 40, "the set up frame of scenario 1 has a long list"
    step_with(window, snapshot)
    for _ in range(40):
        window.key(key(pygame.K_TAB), snapshot)
    step_with(window, snapshot)
    chosen = window.chooser.selected(snapshot.legal, snapshot.view)
    assert window.chooser.position == 40
    row = next(r for r, index in window.rows if index == chosen)
    before = len(host.game.commands)
    window.click(row.center, snapshot)
    wait_for(client, lambda s: s.frame_id != snapshot.frame_id)
    assert len(host.game.commands) > before
    assert host.game.commands[before]["command_id"] == snapshot.legal[chosen]["id"]


@pytest.mark.slow
def test_enter_plays_the_row_of_the_filtered_list(hot_seat):
    """H7: Enter reads the list a person sees after a filter, not the full list."""
    engine, host, client, window = hot_seat
    snapshot = ready(client)
    step_with(window, snapshot)
    last = snapshot.legal[-1]
    hex_id = choice.hexes_of(last)[0]
    type_text(window, snapshot, hex_id.lower())
    assert window.chooser.filter_text == hex_id.lower()
    chosen = window.chooser.selected(snapshot.legal, snapshot.view)
    assert chosen is not None and chosen != 0
    assert hex_id.lower() in choice.row_text(snapshot.legal[chosen], snapshot.view).lower()
    before = len(host.game.commands)
    window.key(key(pygame.K_RETURN), snapshot)
    wait_for(client, lambda s: s.frame_id != snapshot.frame_id)
    assert host.game.commands[before]["command_id"] == snapshot.legal[chosen]["id"]


@pytest.mark.slow
def test_a_new_frame_puts_the_cursor_back_at_the_top(hot_seat):
    engine, host, client, window = hot_seat
    snapshot = ready(client)
    step_with(window, snapshot)
    for _ in range(5):
        window.key(key(pygame.K_TAB), snapshot)
    assert window.chooser.position == 5
    window.key(key(pygame.K_RETURN), snapshot)
    later = wait_for(client, lambda s: s.frame_id != snapshot.frame_id and bool(s.legal))
    step_with(window, later)
    assert window.chooser.position == 0


@pytest.mark.slow
def test_a_double_click_sends_one_intent(hot_seat):
    """H8: the second click of a double click finds the intent of the first on its way."""
    engine, host, client, window = hot_seat
    snapshot = ready(client)
    step_with(window, snapshot)
    row, _index = window.rows[0]
    before = len(host.game.commands)
    window.click(row.center, snapshot)
    window.click(row.center, snapshot)
    wait_for(client, lambda s: s.frame_id != snapshot.frame_id)
    time.sleep(0.3)
    assert len(host.game.commands) == before + 1
    assert client.snapshot().errors == 0, "the second click reached the host as a stale intent"


def test_a_plain_letter_goes_to_the_filter_and_ctrl_makes_it_a_shortcut():
    """H7: the policy of the keys. For a seated person f, s, and q are filter letters."""
    pygame.init()
    window = Window(HostClient("ws://127.0.0.1:1/", "none"), size=(500, 400), caption="test")
    try:
        from slwindow.client import GameView

        snapshot = GameView(player=0, you=0, seat="hot_seat", legal=[{"id": "a", "payload": {"action": "fire", "hex": "B2"}}])
        camera = window.state.camera
        window.key(key(pygame.K_f, "f"), snapshot)
        window.key(key(pygame.K_q, "q"), snapshot)
        assert window.chooser.filter_text == "fq"
        assert window.running, "a filter letter does not close the window"
        assert window.state.camera == camera, "a filter letter does not fit the board"
        window.key(key(pygame.K_MINUS, "-"), snapshot)
        assert window.chooser.filter_text == "fq-", "after a letter the minus key goes to the filter"
        window.key(key(pygame.K_q, "q", pygame.KMOD_LCTRL), snapshot)
        assert not window.running, "Ctrl and q is always the shortcut"
        waiting = GameView(player=1, you=1, seat="player", legal=[])
        window.running = True
        window.key(key(pygame.K_q, "q"), waiting)
        assert window.running, "a seated person who types while the other side acts does not close the window"
        watcher = GameView(seat="watcher", view={"units": [], "spectator": True})
        window.key(key(pygame.K_q, "q"), watcher)
        assert not window.running, "for a watcher the plain letter is the shortcut"
    finally:
        pygame.quit()


# ------------------------------------------------------------ the board choice


def _to_movement(client: HostClient, host: Host) -> object:
    """Set up the two sides with the host helper and end the phases to a movement frame."""
    end = time.monotonic() + 60.0
    while time.monotonic() < end:
        snapshot = wait_for(client, lambda s: bool(s.legal) or s.game_over)
        if snapshot.phase == "movement" and any(e.get("action") == "move" for e in snapshot.legal):
            return snapshot
        if snapshot.phase == "setup":
            client.send_auto_setup()
            wait_for(client, lambda s: s.phase != "setup" or s.active != snapshot.active)
            continue
        ending = next((i for i, e in enumerate(snapshot.legal) if e["payload"]["action"] in ("end_phase", "end_setup")), 0)
        client.send_intent(snapshot.frame_id, snapshot.legal[ending]["id"])
        wait_for(client, lambda s: s.frame_id != snapshot.frame_id)
    raise AssertionError("the game did not reach a movement frame")


@pytest.mark.slow
def test_a_click_on_a_unit_then_on_a_shaded_hex_moves_it(hot_seat):
    """Slice 8: the board selection of the 2D window. The first click pins a unit and the
    overlay shades its options. A click on a shaded hex with one command plays it."""
    engine, host, client, window = hot_seat
    snapshot = _to_movement(client, host)
    window.fit_board(snapshot)
    step_with(window, snapshot)
    # A pair of a unit and a hex that exactly one entry names: a click there plays it. A
    # pair that more entries name (a move and a stack move) only narrows the list.
    counts: dict[tuple[int, str], int] = {}
    for entry in snapshot.legal:
        for unit_id in choice.unit_ids(entry):
            for hex_id in choice.hexes_of(entry):
                counts[(unit_id, hex_id)] = counts.get((unit_id, hex_id), 0) + 1
    homes = {u["id"]: u["hex"] for u in snapshot.view["units"]}
    unit_id, destination = next(
        pair
        for pair, count in counts.items()
        if count == 1 and homes.get(pair[0]) not in (None, pair[1])
        and any(e["payload"]["action"] == "move" and pair[1] in choice.hexes_of(e) and pair[0] in choice.unit_ids(e) for e in snapshot.legal)
    )
    unit = next(u for u in snapshot.view["units"] if u["id"] == unit_id)
    centres = {h["id"]: h["center"] for h in snapshot.board["hexes"]}

    def at(hex_id: str) -> tuple[int, int]:
        x, y = window.state.camera.to_screen(*centres[hex_id])
        return (int(x), int(y))

    for _ in range(8):
        window.click(at(unit["hex"]), snapshot)
        if window.state.pinned == unit_id:
            break
    assert window.state.pinned == unit_id
    overlay = window.update_overlay(snapshot)
    assert overlay.shades.get(destination) == "move", "the destination of the pinned unit is shaded"
    shown = window.chooser.visible(snapshot.legal, snapshot.view)
    assert shown and all(unit_id in choice.unit_ids(e) or not choice.unit_ids(e) for _i, e in shown), "the list narrows to the unit"
    before = len(host.game.commands)
    window.click(at(destination), snapshot)
    wait_for(client, lambda s: s.frame_id != snapshot.frame_id)
    record = host.game.commands[before]
    assert record["payload"]["action"] == "move"
    assert record["payload"]["hex"] == destination and unit_id in record["payload"]["units"]


# -------------------------------------------------------------------- undo


@pytest.mark.slow
def test_ctrl_z_asks_the_host_to_take_back_a_quiet_command(hot_seat):
    engine, host, client, window = hot_seat
    snapshot = ready(client)
    place = next(i for i, e in enumerate(snapshot.legal) if e["payload"]["action"] == "place")
    client.send_intent(snapshot.frame_id, snapshot.legal[place]["id"])
    placed = wait_for(client, lambda s: s.frame_id != snapshot.frame_id and bool(s.legal))
    count = len(host.game.commands)
    assert placed.can_undo, "the host offers an undo after a quiet command"
    window.key(key(pygame.K_z, "z", pygame.KMOD_LCTRL), placed)
    wait_for(client, lambda s: s.frame_id != placed.frame_id)
    assert len(host.game.commands) == count - 1, "the host took the command back"
    assert window.chooser.filter_text == "", "Ctrl and z is not a filter letter"


# ------------------------------------------------------------ the session


@pytest.mark.slow
def test_a_dropped_seat_connects_again_and_gets_its_seat_back():
    """Protocol version 2: the client keeps the seat token in memory and sends it again."""
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=3, hot_seat=False)
    embedded = start(host)
    first = HostClient(embedded.url, embedded.room_code, "seat 0")
    second = HostClient(embedded.url, embedded.room_code, "seat 1")
    first.start()
    try:
        wait_for(first, lambda s: s.player == 0 and bool(s.frame_id))
        second.start()
        was = wait_for(second, lambda s: s.player == 1 and bool(s.frame_id))
        assert second._seat_token, "the host gave the seat a token"

        async def drop() -> None:
            for connection in list(host.connections.values()):
                if connection.player == 1 and connection.socket is not None:
                    await connection.socket.close()

        asyncio.run_coroutine_threadsafe(drop(), embedded.loop).result(10)
        back = wait_for(second, lambda s: s.session > was.session and bool(s.frame_id))
        assert second.reconnects == 1
        assert back.player == 1, "the seat came back to the token"
        assert second.error is None
    finally:
        second.stop()
        first.stop()
        embedded.stop()


def test_a_wrong_room_code_ends_the_session_with_no_second_try():
    """H6: a terminal code gets its own message and no reconnect."""
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=3)
    embedded = start(host)
    client = HostClient(embedded.url, "0" * 32, "wrong code")
    client.start()
    try:
        end = time.monotonic() + TIMEOUT
        while client.error is None and time.monotonic() < end:
            time.sleep(0.02)
        assert isinstance(client.error, SessionRefused), client.error
        assert client.error.code == "room_code"
        assert "room code" in client.snapshot().notice
        assert client.reconnects == 0
    finally:
        client.stop()
        embedded.stop()


# --------------------------------------------------------------- the end


@pytest.mark.slow
def test_the_panel_shows_the_result_the_conditions_and_the_losses_at_the_end():
    """H5 and slice 8: the end panel reads the `game_over` message of the host."""
    engine = build_engine(SCENARIO)
    agents = {0: make_agent("v1", engine, 3, 0), 1: make_agent("v1", engine, 3, 1)}
    host = Host(engine, seed=3, agents=agents, agent_delay=0.0)
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, "watcher")
    client.start()
    pygame.init()
    window = Window(client, size=SIZE, caption="test")
    try:
        over = wait_for(client, lambda s: s.game_over and bool(s.over), timeout=120.0)
        assert over.over.get("winner_name") or over.over.get("result") is None
        lines = panel.end_lines(over)
        assert lines[0].startswith("game over")
        # Two computer sides: a watcher reads the side that wins (`slwindow.endgame`).
        assert lines[0].startswith("game over: the ") and lines[0].endswith(" side wins"), lines
        assert any(line.startswith("The ") and " side, " in line for line in lines), lines
        assert any(line.startswith("Losses of the ") for line in lines), lines
        step_with(window, over)
        assert choice.Chooser().visible(over.legal) == [], "a game at its end offers no command"
        from slwindow.client import status_of

        assert status_of(over) == STATUS_GAME_OVER
    finally:
        client.stop()
        embedded.stop()
        pygame.quit()
