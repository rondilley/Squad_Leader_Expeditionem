"""The 3D window plays (H2): hot seat, against the computer, by keys, by the panel, and on
the board. And the board picture is the right way up (H8).

The window opens offscreen (`window-type offscreen`), so the tests need no display. A
host runs inside the process and the window joins it over a socket on the loopback
address, through the same `HostClient` the pygame window uses. The key tests send the
events of Panda3D through its messenger, which is the path a key press takes, and each
test reads the result in the state of the host.
"""

from __future__ import annotations

import argparse
import math
import time

import pytest

pytest.importorskip("panda3d")

from panda3d.core import loadPrcFileData  # noqa: E402

loadPrcFileData("", "window-type offscreen")
loadPrcFileData("", "win-size 320 240")
loadPrcFileData("", "audio-library-name null")

from direct.showbase.MessengerGlobal import messenger  # noqa: E402

from slcli.play import build_engine, make_agent  # noqa: E402
from slcore import geometry  # noqa: E402
from slhost.server import Host  # noqa: E402
from slwindow import choice, theme  # noqa: E402
from slwindow.choice import Chooser  # noqa: E402
from slwindow.client import STATUS_THINKING, GameView, HostClient  # noqa: E402
from slwindow.embedded import start  # noqa: E402

SCENARIO = "s01_guards_counterattack"
TIMEOUT = 30.0


def _grid(cols: int = 6, rows: int = 6, woods_rows: int = 2) -> dict:
    """A small board with the centres of the core: woods in the top rows, open below."""
    hexes = []
    for col in range(cols):
        for row in range(1, rows + 1):
            hexes.append(
                {
                    "id": geometry.hex_id(col, row),
                    "col": col,
                    "row": row,
                    "center": list(geometry.center(col, row)),
                    "terrain": "woods" if row <= woods_rows else "open",
                    "elevation": 0,
                }
            )
    return {"name": "grid", "cols": cols, "rows": rows, "hexes": hexes, "terrain": {}}


@pytest.fixture(scope="module")
def app():
    """One offscreen window for the module. Panda3D permits one ShowBase in a process, so
    the window of an earlier module is used again when there is one."""
    import builtins

    from slwindow3d.app import Board3DApp

    existing = getattr(builtins, "base", None)
    made = not isinstance(existing, Board3DApp)
    instance = Board3DApp(_grid()) if made else existing
    yield instance
    instance.client = None
    if made:
        instance.destroy()


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


def connect(app, host: Host):
    """Start the host, join it, and give the window the client, as `sl-cli window3d` does."""
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, "3D test")
    client.start()
    snapshot = wait_for(client, lambda s: s.board is not None and bool(s.frame_id))
    app.client = client
    app.chooser = Chooser()
    app.pinned = None
    app._last_frame_id = None
    app._hud_key = None
    app.set_board(snapshot.board)
    return embedded, client


def show(app, client: HostClient):
    snapshot = client.snapshot()
    app.show_snapshot(snapshot)
    return snapshot


# ------------------------------------------------------------- the orientation


def test_the_north_of_the_board_is_away_from_the_camera():
    """H8: the lattice y grows down the 2D board, so the world y turns its sign."""
    from slwindow import layout
    from slwindow3d.mesh import WORLD_CORNERS, _uv, hex_world

    top = hex_world(geometry.center(2, 1))
    bottom = hex_world(geometry.center(2, 6))
    assert top[1] > bottom[1], "row 1 is at the far side of the board, the top of the screen"
    area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(WORLD_CORNERS, WORLD_CORNERS[1:] + WORLD_CORNERS[:1]))
    assert area > 0, "the corners go counterclockwise seen from above, so each top looks up"
    board = _grid()
    camera = layout.fit(board, 400, 300)
    assert _uv(camera, 400, 300, *geometry.center(2, 1))[1] > _uv(camera, 400, 300, *geometry.center(2, 6))[1]


def test_the_board_picture_is_the_right_way_up_in_the_window(app, tmp_path):
    """The woods of the top rows of the 2D board are at the top of the 3D picture."""
    from panda3d.core import Filename, PNMImage

    from slwindow3d.app import MODE_2D, Board3DApp

    board = _grid()
    out = tmp_path / "grid.png"
    Board3DApp.render_screenshot(board, str(out), frames=3, mode=MODE_2D)
    image = PNMImage()
    assert image.read(Filename.fromOsSpecific(str(out)))
    woods = theme.TERRAIN["woods"]
    ground = theme.TERRAIN["open"]
    width, height = image.getReadXSize(), image.getReadYSize()

    def woods_share(y0: int, y1: int) -> float:
        near = seen = 0
        for x in range(0, width * 2 // 3, 4):
            for y in range(y0, y1, 4):
                pixel = (image.getRed(x, y) * 255, image.getGreen(x, y) * 255, image.getBlue(x, y) * 255)
                to_woods = math.dist(pixel, woods)
                to_ground = math.dist(pixel, ground)
                if min(to_woods, to_ground) < 60:
                    seen += 1
                    near += to_woods < to_ground
        return near / max(1, seen)

    top = woods_share(0, height // 2)
    bottom = woods_share(height // 2, height)
    assert top > bottom + 0.2, (top, bottom)


# -------------------------------------------------------------------- play


@pytest.mark.slow
def test_a_person_plays_hot_seat_with_the_keys(app):
    """H2: Tab, Enter, and the typed filter reach the host through the 3D window."""
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=3)
    embedded, client = connect(app, host)
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal))
        show(app, client)
        mode = app.mode
        messenger.send("t")
        assert app.mode == mode, "for a seated person the plain letter t is a filter letter"
        messenger.send("keystroke", ["t"])
        assert app.chooser.filter_text == "t"
        messenger.send("backspace")
        assert app.chooser.filter_text == ""
        for _ in range(3):
            messenger.send("tab")
        chosen = app.chooser.selected(snapshot.legal, snapshot.view)
        assert app.chooser.position == 3
        before = len(host.game.commands)
        messenger.send("enter")
        later = wait_for(client, lambda s: s.frame_id != snapshot.frame_id)
        assert host.game.commands[before]["command_id"] == snapshot.legal[chosen]["id"]
        app.show_snapshot(later)
        assert app.chooser.position == 0, "a new frame puts the cursor back at the top"
    finally:
        client.stop()
        embedded.stop()


@pytest.mark.slow
def test_a_click_on_a_row_of_the_panel_plays_it(app):
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=3)
    embedded, client = connect(app, host)
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal))
        show(app, client)
        assert app._hud_rows, "the panel of the 3D window has rows to click"
        row, index = app._hud_rows[2]
        width, height = app._window_size()
        left = width - app._hud_width
        pointer = ((left + row.centerx) / width * 2.0 - 1.0, 1.0 - row.centery / height * 2.0)
        point = app.panel_point(pointer)
        assert point is not None and row.collidepoint(point)
        before = len(host.game.commands)
        assert app.click_panel(point)
        wait_for(client, lambda s: s.frame_id != snapshot.frame_id)
        assert host.game.commands[before]["command_id"] == snapshot.legal[index]["id"]
    finally:
        client.stop()
        embedded.stop()


def _to_movement(client: HostClient) -> GameView:
    end = time.monotonic() + 60.0
    while time.monotonic() < end:
        snapshot = wait_for(client, lambda s: bool(s.legal) or s.game_over)
        if snapshot.phase == "movement" and any(e["payload"]["action"] == "move" for e in snapshot.legal):
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
def test_a_click_on_a_unit_and_then_on_its_hex_option_moves_it_in_3d(app):
    """Slice 8 in the 3D window: the same board choice as the 2D window."""
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=3)
    embedded, client = connect(app, host)
    try:
        snapshot = _to_movement(client)
        app.show_snapshot(snapshot)
        counts: dict[tuple[int, str], int] = {}
        for entry in snapshot.legal:
            for unit_id in choice.unit_ids(entry):
                for hex_id in choice.hexes_of(entry):
                    counts[(unit_id, hex_id)] = counts.get((unit_id, hex_id), 0) + 1
        homes = {u["id"]: u["hex"] for u in snapshot.view["units"]}
        unit_id, destination = next(
            pair
            for pair, count in counts.items()
            if count == 1
            and homes.get(pair[0]) not in (None, pair[1])
            and any(e["payload"]["action"] == "move" and pair[0] in choice.unit_ids(e) and pair[1] in choice.hexes_of(e) for e in snapshot.legal)
        )
        for _ in range(8):
            app.click(homes[unit_id])
            if app.pinned == unit_id:
                break
        assert app.pinned == unit_id
        assert app.chooser.unit == unit_id, "the list narrows to the commands of the unit"
        app.show_snapshot(snapshot)
        assert app.indicators.overlay.shades.get(destination) == "move"
        before = len(host.game.commands)
        app.click(destination)
        wait_for(client, lambda s: s.frame_id != snapshot.frame_id)
        record = host.game.commands[before]
        assert record["payload"]["action"] == "move" and record["payload"]["hex"] == destination
    finally:
        client.stop()
        embedded.stop()


@pytest.mark.slow
def test_a_person_plays_against_the_computer_in_3d(app):
    """H2: a human side and a computer side. The window shows the computer think."""
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=3, agents={1: make_agent("v1", engine, 3, 1)}, agent_delay=0.05)
    embedded, client = connect(app, host)
    statuses: set[str] = set()
    try:
        end = time.monotonic() + 90.0
        human_after_computer = False
        while time.monotonic() < end:
            snapshot = show(app, client)
            statuses.add(snapshot.status)
            if snapshot.game_over:
                break
            players = [record.get("player") for record in host.game.commands]
            # The computer played after the person played, and the list came back.
            computer_played = 0 in players and 1 in players[players.index(0):]
            if snapshot.legal:
                if computer_played:
                    human_after_computer = True
                    break
                ending = next(
                    (i for i, e in enumerate(snapshot.legal) if e["payload"]["action"] in ("end_phase", "end_setup")),
                    0,
                )
                app.chooser.point_at(ending, snapshot.legal, snapshot.view)
                messenger.send("enter")
                wait_for(client, lambda s: s.frame_id != snapshot.frame_id or s.errors > snapshot.errors)
            else:
                time.sleep(0.01)
        assert human_after_computer, "the computer played its side and the person got the list back"
        assert STATUS_THINKING in statuses, statuses
        assert {record["player"] for record in host.game.commands} == {0, 1}
    finally:
        client.stop()
        embedded.stop()


# ---------------------------------------------------------------- the panel


def test_the_panel_draws_again_at_the_end_of_the_game_with_the_same_frame(app):
    """H8: the panel redraw was keyed on the frame ID only, so the end did not show."""
    board = _grid()
    app.client = None
    app.set_board(board)
    playing = GameView(board=board, view={"units": []}, frame_id="f1", legal=[], scenario={"title": "t", "players": ["russian", "german"]})
    app._hud_key = None
    app.show_snapshot(playing)
    first = app._hud
    assert first is not None
    ended = GameView(
        board=board,
        view={"units": []},
        frame_id="f1",
        legal=[],
        scenario={"title": "t", "players": ["russian", "german"]},
        game_over=True,
        over={"result": 1, "winner_name": "German", "conditions": [], "turn": 6, "casualties": {"0": {"squads": 3}}},
    )
    app.show_snapshot(ended)
    assert app._hud is not first, "the panel drew again for the end of the game"
    assert app._hud_key[2] is True


# ---------------------------------------------------------------- the command


def _parse(*words: str):
    from slcli.window3d_cmd import add_parser

    parser = argparse.ArgumentParser()
    add_parser(parser.add_subparsers(dest="command"))
    return parser.parse_args(["window3d", *words])


def test_the_3d_command_takes_the_play_options_of_the_2d_window():
    args = _parse("--agent", "v1", "--agent-side", "german", "--connect", "ws://127.0.0.1:9/", "--room-code", "abc", "--lan")
    assert (args.agent, args.agent_side, args.connect, args.room_code, args.lan) == ("v1", "german", "ws://127.0.0.1:9/", "abc", True)


@pytest.mark.slow
def test_the_3d_command_starts_a_host_with_one_computer_side(capsys):
    from slcli.window_cmd import connect_or_start, finish

    args = _parse("--agent", "v1")
    embedded, url, room_code, caption = connect_or_start(args, title="Squad Leader Expeditionem 3D")
    try:
        assert set(embedded.host.agents) == {1}, "the computer takes side 1 by default"
        assert embedded.host.room.hot_seat
        assert url.startswith("ws://127.0.0.1:") and room_code
        assert "3D" in caption
    finally:
        finish(embedded, args)
    hot = _parse()
    embedded, _url, _code, _caption = connect_or_start(hot)
    try:
        assert embedded.host.agents == {} and embedded.host.room.hot_seat
    finally:
        finish(embedded, hot)
    assert "hot seat" in capsys.readouterr().out
