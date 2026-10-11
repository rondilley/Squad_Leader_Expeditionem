"""A person plays a game in the 3D window, with the mouse only (slice 21, BC-01 path).

The parts are the real ones: the host runs inside the process, the window's `HostClient`
speaks the protocol over a WebSocket, and the window is the real `Board3DApp`, offscreen.
The test plays the side of the person only through the input a person has:

- a click on the board at a screen position, which goes through the lens of the window and
  the pick of `picking.py`, in the 2D camera and in the 3D camera;
- a press of a button of the list on the left or of the menu.

A scripted agent decides what the person plays, from the state of the host, so the game is
a real game and it ends. The test finds the clicks that play that decision, the way a person
does. A command that no click plays is a failure, not a skip.

The short test plays the set up and the first turns. The `gate` test plays a whole game to
its result: `pytest -m gate tests/window3d/test_play_input.py`.
"""

from __future__ import annotations

import time

import pytest

pytest.importorskip("panda3d")

from panda3d.core import Point2, Point3, loadPrcFileData  # noqa: E402

loadPrcFileData("", "window-type offscreen")
loadPrcFileData("", "win-size 320 240")
loadPrcFileData("", "audio-library-name null")

from slcli.play import build_engine, make_agent  # noqa: E402
from slcore.view import board_document  # noqa: E402
from slwindow3d.picking import world_xy  # noqa: E402
from slwindow3d.selection import MENU, SELECT, payload, reserve_units  # noqa: E402

pytest.importorskip("pygame")

SCENARIO = "s01_guards_counterattack"
SEED = 5
HUMAN = 0
WAIT_SECONDS = 20.0


@pytest.fixture(scope="module")
def app():
    """One offscreen window for the module. Panda3D allows one ShowBase in a process, so a
    window that another module left is used again."""
    import builtins

    from slwindow3d.app import Board3DApp

    existing = getattr(builtins, "base", None)
    if isinstance(existing, Board3DApp):
        yield existing
        return
    instance = Board3DApp(None)
    yield instance
    instance.destroy()


class Session:
    """The host, the client, and the window for one game, and the clicks of the person."""

    def __init__(self, app, seed: int, scenario: str = SCENARIO, agent: str = "v1") -> None:
        from slhost.server import Host
        from slwindow.client import HostClient
        from slwindow.embedded import start
        from slwindow3d.play import PlayInput

        self.engine = build_engine(scenario, None)
        self.opponent = make_agent(agent, self.engine, seed, 1 - HUMAN)
        self.decider = make_agent(agent, self.engine, seed + 1, HUMAN)
        self.host = Host(self.engine, seed=seed, hot_seat=True, agents={1 - HUMAN: self.opponent})
        self.embedded = start(self.host)
        self.client = HostClient(self.embedded.url, self.embedded.room_code, display_name="test person")
        self.client.start()
        self.app = app
        app.set_board(board_document(self.engine.board))
        app._last_frame_id = None
        app._last_notice = ""
        app._poll = self.client.snapshot
        if not app.taskMgr.hasTaskNamed("poll-task"):
            app.taskMgr.add(app._poll_task, "poll-task")
        self.sent: list[str] = []

        def send(frame_id: str, command_id: str) -> None:
            self.sent.append(command_id)
            self.client.send_intent(frame_id, command_id)

        if app.play is not None:
            app.play.close_menu()
            for row in app.play.rows:
                row.destroy()
        app.play = PlayInput(app, send, self.client.request_los)
        app._last_los = None
        self.board = board_document(self.engine.board)
        self.tops = {h["id"]: h for h in self.board["hexes"]}
        self.clicks = 0
        self.buttons = 0

    def person_commands(self) -> list[str]:
        """The command IDs the host applied for the person, after the last intent got there."""
        deadline = time.monotonic() + WAIT_SECONDS
        while True:
            applied = [c["command_id"] for c in self.host.game.commands if c["player"] == HUMAN]
            if len(applied) >= len(self.sent) or time.monotonic() > deadline:
                return applied
            self.app.taskMgr.step()
            time.sleep(0.002)

    def close(self) -> None:
        self.app.taskMgr.remove("poll-task")
        self.app._poll = None
        self.client.stop()
        self.embedded.stop()

    # ------------------------------------------------------------------ waiting

    def wait_for_turn(self) -> bool:
        """Step the window until it holds a frame to choose from, or the game ends."""
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            self.app.taskMgr.step()
            play = self.app.play
            snapshot = play.snapshot
            if snapshot is not None and getattr(snapshot, "game_over", False):
                return False
            if play.my_turn() and snapshot.frame_id == self.client.snapshot().frame_id:
                return True
            time.sleep(0.002)
        raise AssertionError(f"no frame came in {WAIT_SECONDS} s; the banner says {self.app.play.banner_text()!r}")

    # ------------------------------------------------------------------ the person

    def screen_point(self, hex_id: str) -> tuple[float, float]:
        """The mouse position of the centre of a hex top, through the lens of the window.

        When the hex is off the screen, the camera centres on it first, the way a person
        pans the board to a hex they cannot see."""
        app = self.app
        hexagon = self.tops[hex_id]
        from slwindow3d.mesh import HEIGHT_PER_LEVEL

        world = Point3(
            *world_xy(hexagon["center"][0], hexagon["center"][1]),
            int(hexagon.get("elevation", 0) or 0) * HEIGHT_PER_LEVEL,
        )
        for attempt in range(2):
            app._place_camera()
            camera_point = app.cam.getRelativePoint(app.render, world)
            screen = Point2()
            if app.cam.node().getLens().project(camera_point, screen) and abs(screen.x) < 0.95 and abs(screen.y) < 0.95:
                return screen.x, screen.y
            app.target = world
        raise AssertionError(f"hex {hex_id} is not on the screen after the camera centred on it")

    def click(self, hex_id: str) -> str:
        self.clicks += 1
        x, y = self.screen_point(hex_id)
        picked = self.app.pick_at(x, y)
        assert picked == hex_id, f"a click on the centre of {hex_id} picked {picked} in mode {self.app.mode}"
        return self.app.play.click_board(x, y)

    def press_row(self, wanted) -> None:
        """Press the button of the list on the left that holds this entry."""
        for row in self.app.play.rows:
            try:
                args = row["extraArgs"]
            except KeyError:  # the label that says how many rows the list does not show
                continue
            if args and args[0] == wanted:
                self.buttons += 1
                row["command"](*args)
                return
        labels = [label for label, _ in self.app.play.list_entries]
        raise AssertionError(f"no button on the left holds {wanted}; the list is {labels[:25]}")

    def press_menu(self, choice) -> None:
        """Press the menu button for a command, or for a unit id to select."""
        command = choice
        for button in self.app.play.menu:
            args = button["extraArgs"]
            if args and args[0] == choice:
                self.buttons += 1
                button["command"](*args)
                return
        raise AssertionError(f"the menu has no button for {payload(command) if isinstance(command, dict) else command}")

    def play_one(self) -> None:
        """Ask the decider for a command, and play it with clicks and buttons."""
        state = self.host.game.state
        frame = self.engine.legal_commands(state)
        chosen = self.decider.select(state, frame)
        play = self.app.play
        command = next(c for c in play.legal if c["id"] == chosen)
        body = payload(command)
        units = [int(u) for u in body.get("units", [])]
        view = play.view
        on_board = {int(u["id"]): u.get("hex") for u in view["units"]}
        # Select a unit of the command: from the list when it is on no hex, else by clicks
        # on its hex until the stack gives that unit.
        if units and play.selection.unit not in units:
            waiting = reserve_units(play.legal, view)
            placed = [u for u in units if u in waiting]
            if placed:
                self.press_row(("reserve", placed[0]))
            else:
                first = next(u for u in units if on_board.get(u))
                for _ in range(len(view["units"]) + 1):
                    kind = self.click(on_board[first])
                    if kind == MENU and first in [b["extraArgs"][0] for b in play.menu if b["extraArgs"] and isinstance(b["extraArgs"][0], int)]:
                        self.press_menu(first)
                        kind = SELECT
                    if kind == SELECT and play.selection.unit in units:
                        break
                else:
                    raise AssertionError(f"no click on {on_board[first]} selects a unit of {body}")
        if body.get("hex"):
            before = len(self.sent)
            self.click(str(body["hex"]))
            if len(self.sent) == before:
                self.press_menu(command)
            assert len(self.sent) == before + 1, f"the clicks for {body} sent {len(self.sent) - before} commands"
        else:
            self.press_row(("command", command))
        assert self.sent and self.sent[-1] == chosen, f"the clicks for {body} sent {self.sent[-1:]}"


def _play(app, seed: int, limit: int | None, scenario: str = SCENARIO, agent: str = "v1") -> Session:
    session = Session(app, seed, scenario, agent)
    played = 0
    try:
        while session.wait_for_turn():
            # Change the camera now and then, so the clicks go through the 2D lens and the
            # tilted 3D lens.
            app.mode = "2d" if (played // 25) % 2 else "3d"
            session.play_one()
            played += 1
            if limit is not None and played >= limit:
                break
    except BaseException:
        session.close()
        raise
    return session


def test_a_person_sets_up_and_plays_the_first_turns_with_the_mouse(app):
    session = _play(app, SEED, limit=120)
    try:
        assert len(session.sent) == 120
        assert session.clicks > 120
        assert session.buttons > 0
        # The host played each of them: its command list holds the person's commands.
        assert session.person_commands() == session.sent
        assert session.app.play.banner_text()
        # The host sends the person's log with each frame. The client keeps each event
        # once: its log is the end of the person's log on the host, in order, with no event
        # twice and no gap.
        host_log = session.host.game.player_logs[HUMAN]
        # The host can hold the events of a frame the client has not read yet; wait for it.
        deadline = time.monotonic() + WAIT_SECONDS
        while time.monotonic() < deadline:
            client_log = session.client.snapshot().log
            if client_log and client_log[-1] == host_log[-1]:
                break
            session.app.taskMgr.step()
            time.sleep(0.002)
        client_log = session.client.snapshot().log
        assert client_log
        assert client_log == host_log[len(host_log) - len(client_log):]
    finally:
        session.close()


def test_the_l_key_shows_the_hosts_line_of_sight_from_the_selected_unit(app):
    """FR-34 in the 3D window: the host answers the line of sight, and the window draws it."""
    from slcore import geometry
    from slcore.los_eval import evaluate

    session = _play(app, SEED, limit=60)
    try:
        assert session.wait_for_turn()
        play = app.play
        view = play.view
        own = next(u for u in view["units"] if u.get("hex") and u.get("player") == HUMAN and u["kind"] == "squad")
        play.pick_reserve(int(own["id"]))
        target = next(h["id"] for h in session.board["hexes"] if h["id"] != own["hex"] and abs(h["col"] - int(geometry.parse_hex_id(own["hex"])[0])) >= 3)
        x, y = session.screen_point(target)
        assert play.request_los(x, y)
        deadline = time.monotonic() + WAIT_SECONDS
        while play.los is None and time.monotonic() < deadline:
            app.taskMgr.step()
            time.sleep(0.002)
        assert play.los is not None, "the host did not answer the line of sight"
        assert play.los["from"] == own["hex"] and play.los["to"] == target
        expected = evaluate(session.engine.board, session.engine.los, geometry.parse_hex_id(own["hex"]), geometry.parse_hex_id(target))
        assert play.los["clear"] == expected.clear
        assert play.preview_line_text().startswith(f"Line of sight {own['hex']} to {target}: ")
        assert app.indicators.los_root.getNumChildren() >= 1
        # A click on the board removes the answer.
        play.click_hex(None)
        assert play.los is None
        assert app.indicators.los_root.getNumChildren() == 0
    finally:
        session.close()


@pytest.mark.gate
@pytest.mark.parametrize(
    "scenario,agent",
    [
        (SCENARIO, "v1"),
        ("s02_tractor_works", "v2"),
        ("s03a_streets_of_stalingrad", "v2"),
        ("s04_armor_probe", "v3"),
    ],
)
def test_a_person_plays_a_whole_game_with_the_mouse_to_a_result(app, scenario, agent):
    session = _play(app, SEED + 1, limit=None, scenario=scenario, agent=agent)
    try:
        snapshot = session.client.snapshot()
        assert snapshot.game_over
        assert snapshot.result
        assert session.host.game.state.game_over
        assert session.person_commands() == session.sent
        assert session.app.play.banner_text() == f"Game over: {snapshot.result}"
        assert session.app._game_over_panel is not None, "the end-of-game screen did not open"
        print(
            f"{scenario}: a whole game from the mouse: {len(session.sent)} commands, {session.clicks} clicks, "
            f"{session.buttons} buttons, result {snapshot.result}: {snapshot.result_cause}"
        )
    finally:
        session.close()
