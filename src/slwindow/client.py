"""The protocol client of the two desktop windows (the pygame window and the 3D window).

The window is a consumer of the core in the same way the browser client is. It sends
intents and it applies no rule (AR-06). The socket runs an asyncio loop on a thread of its
own, and the drawing loop reads a small record that the thread updates under a lock.

Every boundary error is typed and carries the address, so a window that cannot reach a
host says why instead of drawing an empty board.

Protocol version 2 (the host module docstring has the full list). Each new field is
optional on read, so the client works with a host of version 1 too:

- `frame_id` is an opaque token. The client echoes it in the intent and compares it only
  for equality with the last one.
- `welcome` can carry `seat_token`. The client keeps it in memory, never on disk and never
  in the view it draws, and sends it again in the `join` of a reconnect, so the seat comes
  back to it.
- When a connection that had a `welcome` drops, the client connects again with a pause
  that grows. It does not connect again after an error with a terminal code (`room_code`,
  `rate_limited`, `origin`, `room_full`), or after an error and a close before a welcome.
- `frame` can carry `status`, `auto_applied`, and the legal list as `legal` (version 2) or
  `legal_commands` (version 1), and the log as `log` or `log_tail`. The log merges by `seq`.
- `error` can carry `code`, and the notice has one text for each code.
- `game_over` can carry `winner_name`, `conditions`, `turn`, and `casualties`.
- `frame` can carry `can_undo` and `phase_text`. The host keeps one log stream for each
  viewer, so the client keeps one log for each value of `frame.player`.
- The client can send `undo` and `auto_setup`.
"""

from __future__ import annotations

import asyncio
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.asyncio.client import connect

CONNECT_TIMEOUT = 10.0
STOP_TIMEOUT = 5.0
MAX_LOG = 400
# The pauses before each try to connect again after a drop. Ten tries is less than the
# limit of join tries a host gives one address in a minute (SR-03).
RECONNECT_DELAYS = (0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 5.0, 5.0, 5.0, 5.0)

STATUS_YOUR_TURN = "your_turn"
STATUS_WAITING = "waiting"
STATUS_THINKING = "computer_thinking"
STATUS_GAME_OVER = "game_over"

# An error with one of these codes ends the session: the client does not connect again.
TERMINAL_CODES = frozenset({"room_code", "rate_limited", "origin", "room_full"})

# The questions the client sends in one window of time: a line of sight and the options of
# a unit. The host takes 30 in 5 seconds from a connection (SR-03), so the client keeps
# below that. A question over the budget does not go, and the window asks it again later.
QUESTION_LIMIT = 24
QUESTION_WINDOW_SECONDS = 5.0

# One text for each error code of the host. The message of the host follows it.
ERROR_TEXT = {
    "room_code": "the room code is not correct. Start the window again with the correct --room-code",
    "room_full": "the room is full. Each seat of this game has a player",
    "rate_limited": "the host refused too many join tries from this address. Wait one minute",
    "request_limited": "the window asked the host too many questions. It asks again in a moment",
    "origin": "the host refused the origin of this connection",
    "seat": "this seat does not act now",
    "illegal": "the host refused the command",
    "stale_frame": "the command was for an old frame. Choose again from the new list",
    "protocol": "the host refused a message",
    "undo_refused": "no undo is possible now",
    "internal": "the host had an internal error",
}

STATUS_TEXT = {
    STATUS_YOUR_TURN: "your turn",
    STATUS_WAITING: "waiting for the other side",
    STATUS_THINKING: "the computer decides",
    STATUS_GAME_OVER: "the game is over",
}


class HostUnreachable(Exception):
    """The window could not reach the host, or the host closed the connection."""

    def __init__(self, url: str, cause: str) -> None:
        super().__init__(f"the host at {url} is not reachable: {cause}")
        self.url = url
        self.cause = cause


class SessionRefused(Exception):
    """The host refused the session with a terminal error, so the client stops."""

    def __init__(self, url: str, code: str, message: str) -> None:
        super().__init__(f"the host at {url} refused the session: {message}")
        self.url = url
        self.code = code
        self.message = message


@dataclass
class GameView:
    """What the window draws. The socket thread writes it and the drawing loop reads it."""

    board: dict[str, Any] | None = None
    scenario: dict[str, Any] | None = None
    seat: str = ""
    player: int = -1
    view: dict[str, Any] | None = None
    frame_id: str = ""
    active: int = -1
    phase: str = ""
    sub_step: str = ""
    turn: int = 0
    legal: list[dict[str, Any]] = field(default_factory=list)
    log: list[dict[str, Any]] = field(default_factory=list)
    notice: str = ""
    game_over: bool = False
    result: str = ""
    result_cause: str = ""
    connected: bool = False
    frames: int = 0
    # The answers of the host to `los_request`, by the pair of hex ids (FR-34). The board
    # does not change during a game, so an answer holds for the game.
    los: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    # The answers of the host to `options_request` for this frame, by unit id. A new frame
    # clears them, because a move or a placement changes them.
    options: dict[int, dict[str, Any]] = field(default_factory=dict)
    # Protocol version 2. Each field has a value that a version 1 host also gives.
    status: str = ""
    sides: dict[str, dict[str, Any]] = field(default_factory=dict)
    you: int = -1
    auto_applied: list[str] = field(default_factory=list)
    error_code: str = ""
    errors: int = 0
    # The fields of the `game_over` message: result, winner_name, conditions, turn,
    # casualties, and the cause of a version 1 host.
    over: dict[str, Any] = field(default_factory=dict)
    reconnecting: bool = False
    # The count of welcomes. A new session means that the questions the window asked
    # before (a line of sight) have no answer on the way.
    session: int = 0
    strict_los: bool = False
    # The host says when an undo can go (hot seat and against the computer), and gives a
    # short text of the phase.
    can_undo: bool = False
    phase_text: str = ""
    # The victory conditions of the frame (`slhost.objectives`).
    objectives: list[dict[str, Any]] = field(default_factory=list)


def _merge_log(log: list[dict[str, Any]], tail: list[dict[str, Any]]) -> None:
    """Add the entries of a tail that the log does not hold yet.

    The host sends each entry with its `seq`, and it can send an entry again (a tail, or
    the frames after a reconnect). The log keeps each entry one time, in the order of
    `seq`. A tail with no `seq` (an older host) is appended whole.
    """
    last = int(log[-1]["seq"]) if log and "seq" in log[-1] else -1
    for entry in tail:
        seq = entry.get("seq")
        if seq is None or int(seq) > last:
            log.append(entry)
            if seq is not None:
                last = int(seq)


def status_of(state: GameView) -> str:
    """The status of the frame. A version 1 host sends none, so the window reads it from
    the frame: a legal list is a turn, and no legal list is a wait."""
    if state.game_over:
        return STATUS_GAME_OVER
    if state.status:
        return state.status
    if state.legal:
        return STATUS_YOUR_TURN
    return STATUS_WAITING


def error_text(code: str, message: str) -> str:
    """The text of one error of the host, with the text of its code first."""
    lead = ERROR_TEXT.get(code, "")
    if lead and message:
        return f"{lead} ({message})"
    return lead or message


class HostClient:
    """A connection to one host, driven from a thread of its own."""

    def __init__(self, url: str, room_code: str, display_name: str = "desktop window") -> None:
        self.url = url
        self.room_code = room_code
        self.display_name = display_name
        self.state = GameView()
        self.lock = threading.Lock()
        self.error: Exception | None = None
        self._outbox: "asyncio.Queue[dict[str, Any]] | None" = None
        self._closing: "asyncio.Event | None" = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        # The seat token of protocol version 2. It stays in memory and goes only to the
        # host that gave it, in the join of a reconnect.
        self._seat_token: str | None = None
        self._terminal: SessionRefused | None = None
        self._welcomed = False
        self._error_here = False
        # The times of the questions of the last `QUESTION_WINDOW_SECONDS`.
        self._questions: list[float] = []
        # The frame the last intent went for. A second intent for the same frame waits for
        # a new frame or an error, so a double click sends one intent.
        self._sent_for: str | None = None
        # The newest messages the window sent, for the status line and for a test.
        self.sent: deque[dict[str, Any]] = deque(maxlen=200)
        # One log for each viewer of the frames (see `_receive`).
        self._logs: dict[int, list[dict[str, Any]]] = {}
        self.reconnects = 0

    # ------------------------------------------------------------------ the thread

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="sl-window-socket", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Ask the session to finish, then wait for the thread.

        The loop is closed from inside its own thread when the session ends, so `stop`
        checks before it touches it: a session that already failed left a closed loop.
        """
        self._stop.set()
        loop = self._loop
        closing = self._closing
        if loop is not None and closing is not None and not loop.is_closed():
            try:
                loop.call_soon_threadsafe(closing.set)
            except RuntimeError:
                # The loop closed between the check and the call.
                pass
        thread = self._thread
        if thread is not None:
            thread.join(timeout=STOP_TIMEOUT)

    def _run(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._session())
        except Exception as exc:  # the socket boundary, so every error is caught and shown
            self.error = exc
            with self.lock:
                self.state.notice = str(exc)
                self.state.connected = False
                self.state.reconnecting = False
        finally:
            self._drain(loop)
            loop.close()

    @staticmethod
    def _drain(loop: asyncio.AbstractEventLoop) -> None:
        """Cancel what is left and let it finish, so nothing runs after the loop closes."""
        pending = [task for task in asyncio.all_tasks(loop) if not task.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
        loop.run_until_complete(loop.shutdown_asyncgens())

    async def _session(self) -> None:
        """Connect, and connect again after a drop, until the window stops.

        The first connection gets no second try: a window that never reached its host says
        so at once. After a session that had a welcome, a drop starts the tries of
        `RECONNECT_DELAYS`. A terminal error stops the tries.
        """
        self._outbox = asyncio.Queue()
        self._closing = asyncio.Event()
        attempt = 0
        while True:
            welcomes = self.state.session
            try:
                await self._connect_once()
                return
            except HostUnreachable as exc:
                if self.state.session > welcomes:
                    # The last connection had a welcome, so the count of tries starts again.
                    attempt = 0
                if self._stop.is_set():
                    return
                if self._terminal is not None:
                    raise self._terminal from exc
                if not self._welcomed:
                    raise
                if attempt >= len(RECONNECT_DELAYS):
                    raise HostUnreachable(
                        self.url, f"no answer after {attempt} tries to connect again: {exc.cause}"
                    ) from exc
                delay = RECONNECT_DELAYS[attempt]
                attempt += 1
                with self.lock:
                    self.state.connected = False
                    self.state.reconnecting = True
                    self.state.notice = (
                        f"the connection to the host dropped. Try {attempt} of "
                        f"{len(RECONNECT_DELAYS)} to connect again in {delay:g} s"
                    )
                try:
                    await asyncio.wait_for(self._closing.wait(), delay)
                    return
                except asyncio.TimeoutError:
                    pass

    async def _connect_once(self) -> None:
        assert self._outbox is not None and self._closing is not None
        try:
            connection = await asyncio.wait_for(connect(self.url, max_size=1 << 22), CONNECT_TIMEOUT)
        except (OSError, asyncio.TimeoutError, websockets.exceptions.WebSocketException) as exc:
            raise HostUnreachable(self.url, str(exc) or type(exc).__name__) from exc
        # An intent of the connection before is for a frame that is gone.
        while not self._outbox.empty():
            self._outbox.get_nowait()
        self._error_here = False
        welcomed_here = [False]
        async with connection:
            with self.lock:
                self.state.connected = True
            join: dict[str, Any] = {"type": "join", "room_code": self.room_code, "display_name": self.display_name}
            if self._seat_token:
                join["seat_token"] = self._seat_token
            await connection.send(json.dumps(join))
            sender = asyncio.create_task(self._send_loop(connection))
            reader = asyncio.create_task(self._read_loop(connection, welcomed_here))
            closing = asyncio.create_task(self._closing.wait())
            try:
                await asyncio.wait({reader, closing}, return_when=asyncio.FIRST_COMPLETED)
                if reader.done():
                    reader.result()
            finally:
                for task in (sender, reader, closing):
                    task.cancel()
                await asyncio.gather(sender, reader, closing, return_exceptions=True)

    async def _read_loop(self, connection: Any, welcomed_here: list[bool]) -> None:
        try:
            async for raw in connection:
                try:
                    message = json.loads(raw)
                except json.JSONDecodeError as exc:
                    raise HostUnreachable(self.url, f"the host sent a message that is not JSON: {exc}") from exc
                if not isinstance(message, dict):
                    continue
                if message.get("type") == "welcome":
                    welcomed_here[0] = True
                self._receive(message)
                if self._stop.is_set():
                    return
        except websockets.exceptions.ConnectionClosed as exc:
            if self._stop.is_set():
                return
            if not welcomed_here[0] and self._error_here and self._terminal is None:
                # A version 1 host sends an error with no code and closes before a welcome
                # for a wrong room code and for a full room. Another try gets the same.
                with self.lock:
                    notice = self.state.notice
                self._terminal = SessionRefused(self.url, "", notice)
            raise HostUnreachable(self.url, f"the host closed the connection: {exc}") from exc
        if not self._stop.is_set():
            raise HostUnreachable(self.url, "the host closed the connection")

    async def _send_loop(self, connection: Any) -> None:
        assert self._outbox is not None
        while True:
            message = await self._outbox.get()
            await connection.send(json.dumps(message))

    # ------------------------------------------------------------------ the messages

    def _receive(self, message: dict[str, Any]) -> None:
        kind = message.get("type")
        with self.lock:
            state = self.state
            if kind == "welcome":
                state.board = message.get("board")
                state.scenario = message.get("scenario")
                state.player = int(message.get("player", -1))
                state.seat = str(message.get("seat", ""))
                token = message.get("seat_token")
                if isinstance(token, str) and token:
                    self._seat_token = token
                sides = message.get("sides")
                state.sides = dict(sides) if isinstance(sides, dict) else {}
                state.you = int(message.get("you", state.player))
                state.strict_los = bool(message.get("strict_los", False))
                if self._welcomed:
                    self.reconnects += 1
                self._welcomed = True
                state.session += 1
                state.reconnecting = False
                state.connected = True
                state.notice = ""
                # The answers of the host in the last session do not come now.
                state.los = {}
            elif kind == "frame":
                state.view = message.get("view")
                frame_id = str(message.get("frame_id", ""))
                if frame_id != state.frame_id:
                    state.options = {}
                state.frame_id = frame_id
                state.active = int(message.get("active", -1))
                state.phase = str(message.get("phase", ""))
                state.sub_step = str(message.get("sub_step", ""))
                state.turn = int(message.get("turn", 0))
                legal = message.get("legal", message.get("legal_commands", []))
                state.legal = list(legal) if isinstance(legal, list) else []
                # The host keeps one log stream for each viewer, and hot seat shows the view
                # of the side that acts, so the client keeps one log for each value of
                # `frame.player` and merges each by its own `seq`.
                viewer = int(message.get("player", state.player))
                log = self._logs.setdefault(viewer, [])
                tail = message.get("log", message.get("log_tail", []))
                _merge_log(log, tail if isinstance(tail, list) else [])
                del log[:-MAX_LOG]
                state.log = log
                state.status = str(message.get("status") or "")
                state.can_undo = bool(message.get("can_undo", False))
                state.phase_text = str(message.get("phase_text") or "")
                objectives = message.get("objectives")
                state.objectives = list(objectives) if isinstance(objectives, list) else []
                applied = message.get("auto_applied")
                if isinstance(applied, list) and applied:
                    state.auto_applied = [str(a) for a in applied]
                elif state.legal:
                    state.auto_applied = []
                if isinstance(state.view, dict) and state.view.get("game_over"):
                    state.game_over = True
                state.frames += 1
                state.notice = ""
                state.error_code = ""
                self._sent_for = None
            elif kind == "los_result":
                result = message.get("result")
                if isinstance(result, dict):
                    state.los[(str(message.get("from")), str(message.get("to")))] = result
            elif kind == "options_result":
                result = message.get("result")
                unit = message.get("unit")
                # An answer for an old frame does not hold for this one.
                if isinstance(result, dict) and isinstance(unit, int) and str(message.get("frame_id", "")) == state.frame_id:
                    state.options[unit] = result
            elif kind == "error":
                code = str(message.get("code") or "")
                text = error_text(code, str(message.get("message", "")))
                rule = message.get("rule_id")
                state.notice = f"rule {rule}: {text}" if rule and not code else text
                state.error_code = code
                state.errors += 1
                self._error_here = True
                self._sent_for = None
                if code in TERMINAL_CODES:
                    self._terminal = SessionRefused(self.url, code, text)
            elif kind == "game_over":
                state.game_over = True
                state.status = STATUS_GAME_OVER
                result = message.get("result")
                state.result = "" if result is None else str(result)
                state.result_cause = str(message.get("cause", "") or "")
                state.over = {key: value for key, value in message.items() if key != "type"}

    def snapshot(self) -> GameView:
        """A copy of what the socket thread has, for one frame of drawing."""
        with self.lock:
            state = self.state
            return GameView(
                board=state.board,
                scenario=state.scenario,
                seat=state.seat,
                player=state.player,
                view=state.view,
                frame_id=state.frame_id,
                active=state.active,
                phase=state.phase,
                sub_step=state.sub_step,
                turn=state.turn,
                legal=list(state.legal),
                log=list(state.log),
                notice=state.notice,
                game_over=state.game_over,
                result=state.result,
                result_cause=state.result_cause,
                connected=state.connected,
                frames=state.frames,
                los=dict(state.los),
                options=dict(state.options),
                status=state.status,
                sides=dict(state.sides),
                you=state.you,
                auto_applied=list(state.auto_applied),
                error_code=state.error_code,
                errors=state.errors,
                over=dict(state.over),
                reconnecting=state.reconnecting,
                session=state.session,
                strict_los=state.strict_los,
                can_undo=state.can_undo,
                phase_text=state.phase_text,
                objectives=list(state.objectives),
            )

    def send_intent(self, frame_id: str, command_id: str) -> bool:
        """The window sends an intent and never a state (DR-04).

        The frame ID is the opaque token of the host, echoed as it came. One intent goes
        for one frame: a second one waits for a new frame or an error, so a double click
        does not send two. Return True when the intent went out.
        """
        if not frame_id:
            return False
        with self.lock:
            if self._sent_for == frame_id:
                return False
            self._sent_for = frame_id
        return self._put({"type": "intent", "frame_id": frame_id, "command_id": command_id})

    def send_move_to(self, frame_id: str, unit_id: int, hex_id: str) -> bool:
        """Ask the host to move a unit to a far hex of its reach (`move_to`). The host plays
        the single steps through the core. One message goes for one frame, as an intent."""
        if not frame_id:
            return False
        with self.lock:
            if self._sent_for == frame_id:
                return False
            self._sent_for = frame_id
        return self._put({"type": "move_to", "frame_id": frame_id, "unit": int(unit_id), "hex": hex_id})

    def send_undo(self) -> bool:
        """Ask the host to take back the last command of this side (slice 8). The host
        decides whether it can, and answers with a frame or an `undo_refused` error."""
        with self.lock:
            self._sent_for = None
        return self._put({"type": "undo"})

    def send_auto_setup(self) -> bool:
        """Ask the host to set up the side of this person ("set up for me", slice 8)."""
        with self.lock:
            self._sent_for = None
        return self._put({"type": "auto_setup"})

    def send_setup_lift(self, unit_id: int) -> bool:
        """Ask the host to take a placed unit of this side off the board again while the
        side sets up, so the person can place it in a different hex."""
        with self.lock:
            self._sent_for = None
        return self._put({"type": "setup_lift", "unit": int(unit_id)})

    def _question_allowed(self) -> bool:
        """True when one more question fits in the budget of `QUESTION_WINDOW_SECONDS`."""
        now = time.monotonic()
        with self.lock:
            asked = [t for t in self._questions if now - t < QUESTION_WINDOW_SECONDS]
            if len(asked) >= QUESTION_LIMIT:
                self._questions = asked
                return False
            asked.append(now)
            self._questions = asked
            return True

    def request_los(self, from_hex: str, to_hex: str) -> bool:
        """Ask the host for a line of sight (FR-34). The window has no LOS geometry of its
        own (AR-06), so the answer is the only source of the overlay. Return False when the
        question did not go (the budget is full), so the window asks it again later."""
        if not self._question_allowed():
            return False
        return self._put({"type": "los_request", "from": from_hex, "to": to_hex})

    def request_options(self, unit_id: int) -> bool:
        """Ask the host for the options of one unit of this side (`slhost.options`): why a
        hex refuses it in the set up, where it can go, and where it can fire. Return False
        when the question did not go (the budget is full), so the window asks it again."""
        if not self._question_allowed():
            return False
        return self._put({"type": "options_request", "unit": int(unit_id)})

    def _put(self, message: dict[str, Any]) -> bool:
        loop = self._loop
        outbox = self._outbox
        if loop is None or outbox is None or loop.is_closed():
            return False
        try:
            loop.call_soon_threadsafe(outbox.put_nowait, message)
        except RuntimeError:
            # The loop closed between the check and the call.
            return False
        self.sent.append(message)
        return True
