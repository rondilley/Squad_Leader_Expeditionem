"""The protocol client of the desktop window.

The window is a consumer of the core in the same way the browser client is. It sends
intents and it applies no rule (AR-06). The socket runs an asyncio loop on a thread of its
own, and the drawing loop reads a small record that the thread updates under a lock.

Every boundary error is typed and carries the address, so a window that cannot reach a
host says why instead of drawing an empty board.
"""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.asyncio.client import connect

CONNECT_TIMEOUT = 10.0
STOP_TIMEOUT = 5.0
MAX_LOG = 400


class HostUnreachable(Exception):
    """The window could not reach the host, or the host closed the connection."""

    def __init__(self, url: str, cause: str) -> None:
        super().__init__(f"the host at {url} is not reachable: {cause}")
        self.url = url
        self.cause = cause


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


def _merge_log(log: list[dict[str, Any]], tail: list[dict[str, Any]]) -> None:
    """Add the entries of a tail that the log does not hold yet.

    The host sends the newest entries again with each frame, each with its `seq`. The log
    keeps each entry one time, in order. A tail with no `seq` (an older host) is appended
    whole.
    """
    last = int(log[-1]["seq"]) if log and "seq" in log[-1] else -1
    for entry in tail:
        seq = entry.get("seq")
        if seq is None or int(seq) > last:
            log.append(entry)
            if seq is not None:
                last = int(seq)


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
            loop.call_soon_threadsafe(closing.set)
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
        self._outbox = asyncio.Queue()
        self._closing = asyncio.Event()
        try:
            connection = await asyncio.wait_for(connect(self.url, max_size=1 << 20), CONNECT_TIMEOUT)
        except (OSError, asyncio.TimeoutError, websockets.exceptions.WebSocketException) as exc:
            raise HostUnreachable(self.url, str(exc) or type(exc).__name__) from exc
        async with connection:
            with self.lock:
                self.state.connected = True
            await connection.send(
                json.dumps({"type": "join", "room_code": self.room_code, "display_name": self.display_name})
            )
            sender = asyncio.create_task(self._send_loop(connection))
            reader = asyncio.create_task(self._read_loop(connection))
            closing = asyncio.create_task(self._closing.wait())
            try:
                await asyncio.wait({reader, closing}, return_when=asyncio.FIRST_COMPLETED)
                if reader.done():
                    reader.result()
            finally:
                for task in (sender, reader, closing):
                    task.cancel()
                await asyncio.gather(sender, reader, closing, return_exceptions=True)

    async def _read_loop(self, connection: Any) -> None:
        try:
            async for raw in connection:
                self._receive(json.loads(raw))
                if self._stop.is_set():
                    return
        except websockets.exceptions.ConnectionClosed as exc:
            if self._stop.is_set():
                return
            raise HostUnreachable(self.url, f"the host closed the connection: {exc}") from exc

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
                state.board = message["board"]
                state.scenario = message["scenario"]
                state.player = int(message["player"])
                state.seat = str(message["seat"])
                state.notice = ""
            elif kind == "frame":
                state.view = message["view"]
                state.frame_id = str(message["frame_id"])
                state.active = int(message["active"])
                state.phase = str(message["phase"])
                state.sub_step = str(message["sub_step"])
                state.turn = int(message["turn"])
                state.legal = list(message["legal_commands"])
                _merge_log(state.log, message.get("log_tail", []))
                del state.log[:-MAX_LOG]
                state.frames += 1
                state.notice = ""
            elif kind == "los_result":
                result = message.get("result")
                if isinstance(result, dict):
                    state.los[(str(message.get("from")), str(message.get("to")))] = result
            elif kind == "error":
                state.notice = f"rule {message.get('rule_id', '')}: {message.get('message', '')}"
            elif kind == "game_over":
                state.game_over = True
                state.result = str(message.get("result", ""))
                state.result_cause = str(message.get("cause", ""))

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
            )

    def send_intent(self, frame_id: str, command_id: str) -> None:
        """The window sends an intent and never a state (DR-04)."""
        self._put({"type": "intent", "frame_id": frame_id, "command_id": command_id})

    def request_los(self, from_hex: str, to_hex: str) -> None:
        """Ask the host for a line of sight (FR-34). The window has no LOS geometry of its
        own (AR-06), so the answer is the only source of the overlay."""
        self._put({"type": "los_request", "from": from_hex, "to": to_hex})

    def _put(self, message: dict[str, Any]) -> None:
        loop = self._loop
        outbox = self._outbox
        if loop is None or outbox is None:
            return
        loop.call_soon_threadsafe(outbox.put_nowait, message)
