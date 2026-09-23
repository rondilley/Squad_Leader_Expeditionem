"""The local WebSocket host (FR-36, FR-37, AR-06, AR-09).

The host owns the authoritative state, applies each intent through the core, and gives
each player a view. It serves the built client over HTTP on the same port so that hot
seat needs one process and one address.

Every crossing of the trust boundary has a typed handler: a message that is not valid
gives an error to that client and leaves the host up.
"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
import mimetypes
import sys
import time
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from typing import Any, Iterable

from websockets.asyncio.server import ServerConnection, serve
from websockets.exceptions import ConnectionClosed
from websockets.datastructures import Headers
from websockets.http11 import Request, Response

from slcore import geometry, view
from slcore.commands import Command
from slcore.engine import Engine, IllegalCommand
from slagents.tuned.traces import TraceWriter, board_source
from slcore.game import State
from slcore.los_eval import evaluate as evaluate_los
from slcore import view
from slhost import protocol, rooms
from slhost.protocol import ProtocolError

HUMAN_FAMILY = "human"
LOG_TAIL = 40
MAX_AGENT_COMMANDS = 4000
STRICT_LOS_PHASES = ("prep_fire", "defensive_fire", "advancing_fire")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8731


def use_selector_loop() -> None:
    """The host uses the selector loop on Windows, as the LocalLLMPerf_AI sibling does.

    The proactor loop starved a socket library in that project. The policy is set in one
    place, and only on Windows.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@dataclass
class Game:
    """One game on the host: the authoritative state and the action log."""

    engine: Engine
    state: State
    log: list[dict[str, Any]] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    traces: TraceWriter | None = None
    agent_names: dict[int, tuple[str, str]] = field(default_factory=dict)

    def frame(self) -> dict[str, Any]:
        return self.engine.legal_commands(self.state).to_dict()

    def _actor(self, player: int) -> SimpleNamespace:
        """Who made this decision: a computer opponent by name, or the person at the seat."""
        name, version = self.agent_names.get(player, (HUMAN_FAMILY, "0"))
        return SimpleNamespace(name=name, version=version)

    def spectator_view(self, both_are_computers: bool) -> dict[str, Any]:
        """Each unit of each side, for a watcher of a game between two computer opponents.

        The guard is the argument. A game where a person holds a seat never builds this
        document, because a full view in that game would break AR-09.
        """
        if not both_are_computers:
            raise PermissionError(
                "a spectator view is for a game between two computer opponents only, "
                "because a person who sees each side of a live game breaks AR-09"
            )
        return view.build(self.state, self.engine.types, view.SPECTATOR, spectator=True)

    def view_for(self, player: int) -> dict[str, Any]:
        return view.build(self.state, self.engine.types, player)

    def log_tail(self) -> list[dict[str, Any]]:
        """The newest entries of the log, each with its `seq` in the whole log.

        The host sends the tail again with each frame. The number lets a client merge the
        tails into one log with no entry twice, and lets an overlay find the entries it
        has not drawn.
        """
        start = max(0, len(self.log) - LOG_TAIL)
        return [{**entry, "seq": start + i} for i, entry in enumerate(self.log[start:])]

    def apply(self, frame_id: str, command_id: str) -> list[dict[str, Any]]:
        """Apply one intent. Raises IllegalCommand or ProtocolError, and never both."""
        frame = self.engine.legal_commands(self.state)
        if frame.frame_id != frame_id:
            raise ProtocolError("DR-04", "the frame ID does not belong to the current state; use the frame the host just sent")
        legal = frame.by_id(command_id)
        if legal is None:
            raise IllegalCommand(frame.sub_step, f"command {command_id} is not in the legal list")
        before = self.state
        self.state, events = self.engine.apply(self.state, legal.command, frame)
        entries = [e.to_dict() for e in events]
        if self.traces is not None:
            # FR-60: a hot seat game and a LAN game give traces in the same shape as a
            # headless game. The record is the view of the player that acted (SR-09).
            self.traces.add(self.engine, before, frame, self._actor(frame.player), legal.id, events)
            if self.state.game_over:
                self.traces.finish(self.state.result)
        self.log.extend(entries)
        self.commands.append(
            {
                "seq": self.state.seq,
                "player": frame.player,
                "phase": frame.phase,
                "frame_id": frame.frame_id,
                "command_id": legal.id,
                "payload": legal.payload,
                "hash": self.engine.hash_state(self.state),
            }
        )
        return entries

    def write_traces(self, root: Path) -> Path | None:
        """The trace file of this game, when the host was started with a trace directory."""
        if self.traces is None or not self.traces.records:
            return None
        return self.traces.write(root, f"traces_{self.traces.game_id}.json")


class Host:
    def __init__(
        self,
        engine: Engine,
        seed: int,
        hot_seat: bool = True,
        room_code: str | None = None,
        client_root: Path | None = None,
        allowed_origins: tuple[str, ...] = (),
        strict_los: bool = False,
        agents: dict[int, Any] | None = None,
        traces: str | Path | None = None,
        agent_delay: float = 0.0,
    ) -> None:
        self.engine = engine
        self.agents: dict[int, Any] = dict(agents or {})
        self.trace_root = Path(traces) if traces else None
        self.game = Game(engine, engine.new_game(seed))
        if self.trace_root is not None:
            # FR-60: a hot seat game and a LAN game give traces of the same shape as a
            # headless game. The name of the file says which game it came from.
            self.game.traces = TraceWriter(
                game_id=f"{engine.scenario.id}-host-{seed}",
                board_source=board_source(engine),
            )
            self.game.agent_names = {
                seat: (getattr(agent, "name", "unknown"), str(getattr(agent, "version", "0")))
                for seat, agent in self.agents.items()
            }
        self.room = rooms.Room(code=room_code or rooms.new_room_code(), hot_seat=hot_seat)
        self.attempts = rooms.Attempts()
        self.client_root = client_root
        self.allowed_origins = allowed_origins
        self.strict_los = strict_los
        self.connections: dict[str, ServerConnection] = {}
        self.latencies: list[float] = []
        # FR-39 with the fourth play mode of the vision: computer against computer. With a
        # seat for each computer opponent, nobody plays, and a watcher sees the whole board.
        self.self_playing = len(self.agents) >= 2
        self.agent_delay = float(agent_delay)
        self.commands_played = 0
        self.solo_task: asyncio.Task | None = None

    # ------------------------------------------------------------ static files

    def serve_file(self, connection: ServerConnection, request: Request) -> Response | None:
        """Serve the built client. The WebSocket upgrade goes on untouched."""
        if request.headers.get("Upgrade", "").lower() == "websocket":
            return None
        if self.client_root is None:
            return connection.respond(HTTPStatus.NOT_FOUND, "no client is built; run npm run build in client/\n")
        path = request.path.split("?")[0]
        relative = "index.html" if path in ("/", "") else path.lstrip("/")
        target = (self.client_root / relative).resolve()
        try:
            target.relative_to(self.client_root.resolve())
        except ValueError:
            return connection.respond(HTTPStatus.FORBIDDEN, "outside the client directory\n")
        if not target.is_file():
            target = self.client_root / "index.html"
        if not target.is_file():
            return connection.respond(HTTPStatus.NOT_FOUND, "the client is not built\n")
        try:
            body = target.read_bytes()
        except OSError as exc:
            return connection.respond(HTTPStatus.INTERNAL_SERVER_ERROR, f"cannot read the client file: {exc}\n")
        kind = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        headers = Headers()
        headers["Content-Type"] = kind
        headers["Content-Length"] = str(len(body))
        headers["Cache-Control"] = "no-store"
        return Response(int(HTTPStatus.OK), "OK", headers, body)

    # ------------------------------------------------------------- connections

    async def handle(self, connection: ServerConnection) -> None:
        connection_id = f"c{id(connection)}"
        address = connection.remote_address[0] if connection.remote_address else "unknown"
        origin = connection.request.headers.get("Origin") if connection.request else None
        host_header = connection.request.headers.get("Host") if connection.request else None
        if not rooms.origin_allowed(origin, self.allowed_origins, host_header):
            await self.send(connection, protocol.error_message("SR-03", "the origin is not allowed"))
            await connection.close()
            return
        self.connections[connection_id] = connection
        try:
            async for raw in connection:
                await self.on_message(connection, connection_id, address, raw)
        except ConnectionClosed:
            pass
        finally:
            self.connections.pop(connection_id, None)
            self.room.release(connection_id)

    async def on_message(self, connection: ServerConnection, connection_id: str, address: str, raw: str | bytes) -> None:
        try:
            message = protocol.parse(raw)
        except ProtocolError as exc:
            await self.send(connection, protocol.error_message(exc.rule_id, exc.message))
            return
        try:
            if message.type == protocol.CLIENT_JOIN:
                await self.on_join(connection, connection_id, address, message)
            elif message.type == protocol.CLIENT_INTENT:
                await self.on_intent(connection, connection_id, message)
            elif message.type == protocol.CLIENT_VIEW_REQUEST:
                await self.send_frames()
            elif message.type == protocol.CLIENT_LOS_REQUEST:
                await self.on_los_request(connection, message)
        except ProtocolError as exc:
            await self.send(connection, protocol.error_message(exc.rule_id, exc.message))
        except IllegalCommand as exc:
            await self.send(connection, protocol.error_message(exc.rule_id, exc.message))

    async def on_join(self, connection: ServerConnection, connection_id: str, address: str, message: protocol.ClientMessage) -> None:
        if not self.attempts.allow(address):
            raise ProtocolError("SR-03", "too many join tries from this address")
        code = str(message.data.get("room_code", ""))
        if not rooms.code_matches(self.room.code, code):
            raise ProtocolError("SR-03", "the room code is not correct")
        self.attempts.reset(address)
        name = str(message.data.get("display_name", ""))[:40]
        player, seat = self.room.take(connection_id, name)
        if player < 0:
            raise ProtocolError("SR-03", "the room is full")
        await self.send(
            connection,
            protocol.welcome(player, seat, view.board_document(self.engine.board), self.scenario_document()),
        )
        if self.self_playing:
            # The watcher is here, so the two computer opponents start. One task for the
            # game, however many watchers connect.
            await self.send_frames()
            if self.solo_task is None or self.solo_task.done():
                self.solo_task = asyncio.create_task(self.play_alone())
            return
        self.run_agents()
        await self.send_frames()

    async def on_intent(self, connection: ServerConnection, connection_id: str, message: protocol.ClientMessage) -> None:
        frame_id = str(message.require("frame_id"))
        command_id = str(message.require("command_id"))
        active = self.game.state.active
        if active in self.agents:
            raise ProtocolError("FR-39", f"player {active} is a computer opponent")
        if not self.room.controls(connection_id, active):
            raise ProtocolError("SR-03", "this connection does not hold the seat that acts now")
        started = time.perf_counter()
        self.game.apply(frame_id, command_id)
        self.run_agents()
        await self.send_frames()
        self.latencies.append(time.perf_counter() - started)
        if self.game.state.game_over:
            await self.broadcast(protocol.game_over_message(self.game.state.result, self.game.state.result_cause))

    def run_agents(self) -> int:
        """FR-39: a side that a computer opponent holds plays until the human acts again.

        A game that plays itself does not use this. `play_alone` steps one command at a
        time, so that a watcher sees the game and not only its result.
        """
        if self.self_playing:
            return 0
        played = 0
        while not self.game.state.game_over and self.game.state.active in self.agents and played < MAX_AGENT_COMMANDS:
            frame = self.engine.legal_commands(self.game.state)
            if not frame.commands:
                raise RuntimeError(f"no legal command in {self.game.state.phase} for the computer opponent")
            agent = self.agents[self.game.state.active]
            chosen = agent.select(self.game.state, frame)
            self.game.apply(frame.frame_id, chosen)
            played += 1
        return played

    def step_once(self) -> bool:
        """One command from the computer opponent whose turn it is. False at the game end."""
        if self.game.state.game_over:
            return False
        frame = self.engine.legal_commands(self.game.state)
        if not frame.commands:
            raise RuntimeError(f"no legal command in {self.game.state.phase} for the computer opponent")
        agent = self.agents[self.game.state.active]
        chosen = agent.select(self.game.state, frame)
        self.game.apply(frame.frame_id, chosen)
        self.commands_played += 1
        return True

    async def play_alone(self, limit: int = MAX_AGENT_COMMANDS) -> str:
        """Play a game between two computer opponents, and show each command.

        The task steps one command, sends the new frame to each watcher, and waits. The
        wait is what makes the game watchable; a test sets it to zero and a person sets it
        to a fraction of a second.
        """
        while self.commands_played < limit and not self.game.state.game_over:
            self.step_once()
            await self.send_frames()
            if self.agent_delay:
                await asyncio.sleep(self.agent_delay)
        if self.game.state.game_over:
            await self.broadcast(
                protocol.game_over_message(self.game.state.result, self.game.state.result_cause)
            )
            return str(self.game.state.result)
        return "no_result"

    async def on_los_request(self, connection: ServerConnection, message: protocol.ClientMessage) -> None:
        """FR-34: the host answers the line of sight question, because the client has no rule logic."""
        if self.strict_los and self.game.state.phase not in STRICT_LOS_PHASES:
            raise ProtocolError("19.3", "in strict mode a line of sight check belongs to a fire phase")
        try:
            source = geometry.parse_hex_id(str(message.require("from")))
            target = geometry.parse_hex_id(str(message.require("to")))
        except ValueError as exc:
            raise ProtocolError("protocol", f"a hex name is not valid: {exc}") from exc
        if source not in self.engine.board or target not in self.engine.board:
            raise ProtocolError("3.5", "a hex is not on this board")
        result = evaluate_los(self.engine.board, self.engine.los, source, target)
        await self.send(
            connection,
            protocol.los_result_message(
                geometry.hex_id(*source),
                geometry.hex_id(*target),
                {
                    "clear": result.clear,
                    "rule_id": result.rule_id,
                    "traced": [geometry.hex_id(*h) for h in result.traced],
                    "hindrance": result.hindrance,
                    "blocking_hex": None if result.blocking_hex is None else geometry.hex_id(*result.blocking_hex),
                },
            ),
        )

    # --------------------------------------------------------------- messaging

    def human_player(self) -> int:
        """The side the person at the screen sees. With no computer opponent it is the active side."""
        active = self.game.state.active
        if active not in self.agents:
            return active
        for player in (0, 1):
            if player not in self.agents:
                return player
        return active

    def scenario_document(self) -> dict[str, Any]:
        scenario = self.engine.scenario
        return {
            "id": scenario.id,
            "title": scenario.title,
            "turns": scenario.turns,
            "sides": [s.side for s in scenario.sides],
            "players": list(scenario.players()),
            "notes": scenario.notes,
        }

    async def send(self, connection: ServerConnection, message: dict[str, Any]) -> None:
        try:
            await connection.send(protocol.dump(message))
        except ConnectionClosed:
            pass

    async def broadcast(self, message: dict[str, Any]) -> None:
        for connection in list(self.connections.values()):
            await self.send(connection, message)

    async def send_frames(self) -> None:
        """One view for each seated player (AR-09). Hot seat gets the view of the active side.

        With a computer opponent, the human seat keeps its own view even while the
        opponent acts, so no opponent-hidden state reaches it.
        """
        frame = self.game.frame()
        tail = self.game.log_tail()
        if self.self_playing:
            payload = protocol.frame_message(
                view.SPECTATOR, self.game.spectator_view(self.self_playing), frame, tail
            )
            await self.broadcast(payload)
            return
        if self.room.hot_seat:
            player = self.human_player()
            payload = protocol.frame_message(player, self.game.view_for(player), frame, tail)
            await self.broadcast(payload)
            return
        # A copy, because a client that leaves during the send changes the seat map.
        for player, connection_id in sorted(self.room.seats.items()):
            connection = self.connections.get(connection_id)
            if connection is None:
                continue
            payload = protocol.frame_message(player, self.game.view_for(player), frame, tail)
            await self.send(connection, payload)

    # ------------------------------------------------------------------ server

    @contextlib.asynccontextmanager
    async def start(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        """Serve until the block ends. Port 0 asks the system for a free port."""
        async with serve(self.handle, host, port, process_request=self.serve_file) as server:
            yield server

    @staticmethod
    def bound_port(server: Any) -> int:
        return int(next(iter(server.sockets)).getsockname()[1])

    async def run(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        async with self.start(host, port) as server:
            await server.serve_forever()


def local_addresses(port: int) -> Iterable[str]:
    yield f"http://{DEFAULT_HOST}:{port}/"
