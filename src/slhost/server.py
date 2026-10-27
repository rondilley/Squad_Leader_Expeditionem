"""The local WebSocket host (FR-36, FR-37, AR-06, AR-09), protocol version 2.

The host owns the authoritative state, applies each intent through the core, and gives
each player a view. It serves the built client over HTTP on the same port so that hot
seat needs one process and one address. `slhost.protocol` records the messages.

Every crossing of the trust boundary has a typed handler: a message that is not valid
gives an error with a code to that client and leaves the host up. A defect in the host
gives the code `internal` and the host stays up (S14).

What the host keeps from the clients (S1, AR-09): the state hash. A frame carries an
opaque token that the host makes for each connection, and the host keeps the map from
the token to the core frame.

The computer opponents play in a worker thread (H1). One task drives them, and one lock
keeps the game state to one writer at a time. The host sends a frame to each connection
after each computer command, so a watcher and the opponent see each move.
"""

from __future__ import annotations

import asyncio
import contextlib
import mimetypes
import secrets
import sys
import time
import traceback
from dataclasses import dataclass, field
from http import HTTPStatus
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterable

from websockets.asyncio.server import ServerConnection, serve
from websockets.datastructures import Headers
from websockets.exceptions import ConnectionClosed
from websockets.http11 import Request, Response

from slagents.base import decide
from slagents.tuned.traces import TraceWriter, board_source
from slcore import geometry, view
from slcore.commands import Command
from slcore.engine import Engine, IllegalCommand
from slcore.game import PHASE_MOVEMENT, PHASE_SETUP, State
from slcore.los_eval import evaluate as evaluate_los
from slhost import annotate, objectives, options, protocol, rooms, savegame
from slhost.protocol import ProtocolError

HUMAN_FAMILY = "human"
LOG_TAIL = 40
# The first frame of a connection holds at most this many lines of the history.
LOG_HISTORY = 4000
MAX_AGENT_COMMANDS = 4000
STRICT_LOS_PHASES = ("prep_fire", "defensive_fire", "advancing_fire")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8731

# S15: the limits of the host.
MAX_CONNECTIONS = 32
JOIN_DEADLINE_SECONDS = 10.0
MAX_QUEUE = 16
REQUEST_LIMIT = 30
REQUEST_WINDOW_SECONDS = 5.0

SOURCE_HUMAN = "human"
SOURCE_COMPUTER = "computer"
SOURCE_FORCED = "forced"
SOURCE_SETUP = "setup_helper"
# A step of a `move_to` route after its first step. An undo takes back the whole route, as
# it takes back a forced command with the command of the person before it.
SOURCE_ROUTE = "route"
# A log line the host writes, and not a rule of the core, has this rule ID.
HOST_RULE = "host"

STREAM_SPECTATOR = "spectator"

SETUP_AGENT = "v7"
# The commands of a set up block that a person may take back one unit at a time.
LIFT_ACTIONS = ("place", "place_weapon", "place_concealment")
TOKEN_BYTES = 16


def use_selector_loop() -> None:
    """The host uses the selector loop on Windows, as the LocalLLMPerf_AI sibling does.

    The proactor loop starved a socket library in that project. The policy is set in one
    place, and only on Windows.
    """
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


@dataclass
class LogStream:
    """The log lines of one viewer, with a `seq` that has no gap (S10).

    A line goes in when the host first reads it after the command that made it, and the
    check of what the viewer may see runs at that time. A line that goes in stays; a line
    that does not go in never comes later. So the stream shows no gap, and a line of a
    unit that dies later does not come back.
    """

    viewer: int
    spectator: bool
    lines: list[dict[str, Any]] = field(default_factory=list)
    cursor: int = 0


@dataclass
class Game:
    """One game on the host: the authoritative state and the action log."""

    engine: Engine
    state: State
    log: list[dict[str, Any]] = field(default_factory=list)
    commands: list[dict[str, Any]] = field(default_factory=list)
    traces: TraceWriter | None = None
    agent_names: dict[int, tuple[str, str]] = field(default_factory=dict)
    save: savegame.SaveFile | None = None
    seed: int = 0
    switches: dict[str, str] = field(default_factory=dict)
    names: annotate.Names = field(default_factory=annotate.Names)
    streams: dict[str, LogStream] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.sides = annotate.side_names(self.engine)

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

    # ------------------------------------------------------------- log streams

    def stream(self, key: str, viewer: int, spectator: bool = False) -> LogStream:
        """The stream of one viewer, brought up to the end of the log."""
        stream = self.streams.get(key)
        if stream is None:
            stream = LogStream(viewer, spectator)
            self.streams[key] = stream
        stream.viewer = viewer
        stream.cursor = min(stream.cursor, len(self.log))
        for entry in self.log[stream.cursor :]:
            if spectator or view.event_visible(self.state, entry, viewer):
                shown = annotate.dress_line(entry, self.state, self.names, view.SPECTATOR if spectator else viewer, self.sides)
                shown["seq"] = len(stream.lines)
                stream.lines.append(shown)
        stream.cursor = len(self.log)
        return stream

    def log_tail(self) -> list[dict[str, Any]]:
        """The newest lines of the full log, for a spectator of two computer opponents."""
        return self.stream(STREAM_SPECTATOR, view.SPECTATOR, spectator=True).lines[-LOG_TAIL:]

    def log_tail_for(self, viewer: int, spectator: bool = False) -> list[dict[str, Any]]:
        """The newest lines this viewer may read. `seq` counts the lines of this viewer."""
        if spectator:
            return self.log_tail()
        return self.stream(f"p{viewer}", viewer).lines[-LOG_TAIL:]

    # ----------------------------------------------------------------- applying

    def _seen_by(self, state: State, player: int) -> tuple[Any, ...]:
        """What one player sees of the other side: the units and the concealment counters."""
        units = tuple(
            (u.id, u.hex, u.broken)
            for u in state.units
            if u.player != player and view.visible_to(state, u, player)
        )
        counters = tuple(sorted((c.hex, c.player) for c in state.concealment if c.player != player))
        return units, counters

    def apply(self, frame_id: str, command_id: str, source: str = SOURCE_HUMAN) -> list[dict[str, Any]]:
        """Apply one command of the current core frame. Raises IllegalCommand or ProtocolError."""
        frame = self.engine.legal_commands(self.state)
        if frame.frame_id != frame_id:
            raise ProtocolError(
                "DR-04",
                "the frame ID does not belong to the current state; use the frame the host just sent",
                protocol.CODE_STALE_FRAME,
            )
        legal = frame.by_id(command_id)
        if legal is None:
            raise IllegalCommand(frame.sub_step, f"command {command_id} is not in the legal list")
        before = self.state
        log_start = len(self.log)
        traces_before = len(self.traces.records) if self.traces is not None else 0
        self.state, events = self.engine.apply(self.state, legal.command, frame)
        entries = [e.to_dict() for e in events]
        if self.traces is not None:
            # FR-60: a hot seat game and a LAN game give traces in the same shape as a
            # headless game. The record is the view of the player that acted (SR-09).
            self.traces.add(self.engine, before, frame, self._actor(frame.player), legal.id, events, after=self.state)
            if self.state.game_over:
                self.traces.finish(self.state.result)
        self.log.extend(entries)
        # An undo may take back a command that rolled no die and showed the player
        # nothing new of the other side (slice 8).
        quiet = (
            before.rng == self.state.rng
            and not any(e.get("kind") in ("unconcealed", "concealed") for e in entries)
            and self._seen_by(before, frame.player) == self._seen_by(self.state, frame.player)
        )
        record = {
            "seq": self.state.seq,
            "player": frame.player,
            "phase": frame.phase,
            "frame_id": frame.frame_id,
            "command_id": legal.id,
            "payload": legal.payload,
            "hash": self.engine.hash_state(self.state),
            "source": source,
            "quiet": quiet,
            "log_start": log_start,
            "traces_before": traces_before,
        }
        self.commands.append(record)
        if self.save is not None:
            self.save.append(save_line(record))
        return entries

    def replay_to(self, count: int) -> State:
        """A new game with the same seed and the first `count` commands, each hash checked."""
        state = self.engine.new_game(self.seed, self.switches or None)
        for index, record in enumerate(self.commands[:count]):
            state, _ = self.engine.apply(state, Command.from_payload(record["payload"]))
            if self.engine.hash_state(state) != record["hash"]:
                raise savegame.SaveFileError(
                    f"the replay of command {index} gives a hash that is not the recorded hash"
                )
        return state

    def take_back(self, count: int, state: State) -> None:
        """Drop the last `count` commands, their log lines, and their trace records."""
        first = self.commands[len(self.commands) - count]
        del self.commands[len(self.commands) - count :]
        del self.log[first["log_start"] :]
        if self.traces is not None:
            del self.traces.records[first["traces_before"] :]
        self.state = state
        for stream in self.streams.values():
            stream.cursor = min(stream.cursor, len(self.log))
        if self.save is not None:
            self.save.rewrite([save_line(record) for record in self.commands])

    def setup_block(self, player: int) -> int:
        """The index of the first command of the set up block of this player that ends the
        command list: the place commands it gave since the last command of anyone else."""
        start = len(self.commands)
        for record in reversed(self.commands):
            action = str(record["payload"].get("action", ""))
            if record["player"] != player or record["phase"] != PHASE_SETUP or action not in LIFT_ACTIONS:
                break
            start -= 1
        return start

    def lift(self, unit_id: int, player: int) -> int:
        """Take a unit of the set up block of this player off the board (the setup pick up).

        The host plays the game again from the seed to the first command that placed the
        unit, and then plays each later command of the block again through the core. A
        command that is not legal now is left out, so its unit is off the board too: a
        weapon given to the unit, for example. Rule 21.2 with PR-06 offers the lowest ID of
        each type, so a place of an identical counter that is not legal now takes the place
        command of the frame with the same hex, the same facing, and a unit of the same type
        and group. The host applies only commands of the legal list of the core (AR-06).
        Return how many commands were left out.
        """
        start = self.setup_block(player)
        block = self.commands[start:]

        def names_unit(record: dict[str, Any]) -> bool:
            payload = record["payload"]
            if payload.get("action") == "place_weapon":
                return payload.get("weapon") == unit_id
            return payload.get("action") == "place" and (payload.get("units") or [None])[0] == unit_id

        first = next((start + i for i, record in enumerate(block) if names_unit(record)), None)
        if first is None:
            raise ProtocolError("21.2", f"unit {unit_id} was not placed in this set up", protocol.CODE_ILLEGAL)
        later = [record for record in self.commands[first + 1 :] if not names_unit(record)]
        restored = self.replay_to(first)
        self.take_back(len(self.commands) - first, restored)
        left_out = 1
        for record in later:
            frame = self.engine.legal_commands(self.state)
            if frame.player != player:
                left_out += 1
                continue
            legal = frame.by_id(record["command_id"]) or self._same_kind(frame, record["payload"])
            if legal is None:
                left_out += 1
                continue
            self.apply(frame.frame_id, legal.id, record["source"])
        return left_out

    def _same_kind(self, frame: Any, payload: dict[str, Any]) -> Any:
        """The place command of the frame that does what this one did with an identical
        counter (PR-06): the same hex and facing, and a unit of the same type and group."""
        if payload.get("action") != "place" or not payload.get("units"):
            return None
        units = self.state.units
        wanted = units[int(payload["units"][0])]
        for legal in frame.commands:
            command = legal.command
            if command.action != "place" or not command.units or legal.payload.get("hex") != payload.get("hex"):
                continue
            if dict(command.extra).get("facing") != payload.get("facing"):
                continue
            other = units[command.units[0]]
            if other.type_key == wanted.type_key and other.group == wanted.group:
                return legal
        return None

    def write_traces(self, root: Path) -> Path | None:
        """The trace file of this game, when the host was started with a trace directory."""
        if self.traces is None or not self.traces.records:
            return None
        return self.traces.write(root, f"traces_{self.traces.game_id}.json")


def _report_task(task: asyncio.Task) -> None:
    """A computer turn that stops with an error says so on the error stream."""
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        print(f"host: the computer opponent stopped: {error!r}", file=sys.stderr)
        traceback.print_exception(error, file=sys.stderr)


def save_line(record: dict[str, Any]) -> dict[str, Any]:
    """The line of one command in the save file."""
    return {
        "player": record["player"],
        "payload": record["payload"],
        "command_id": record["command_id"],
        "hash": record["hash"],
        "source": record["source"],
    }


@dataclass
class Connection:
    """One socket, and what the host keeps for it."""

    id: str
    socket: ServerConnection | None
    address: str
    player: int = -1
    seat: str = ""
    joined: bool = False
    token: str = ""
    token_hash: str = ""
    sent: dict[str, int] = field(default_factory=dict)
    game_over_sent: bool = False
    requests: rooms.RateLimit = field(default_factory=lambda: rooms.RateLimit(REQUEST_LIMIT, REQUEST_WINDOW_SECONDS))


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
        odds: bool = True,
        auto_forced: bool = True,
        save_dir: str | Path | None = None,
        save_header: dict[str, Any] | None = None,
    ) -> None:
        self.engine = engine
        self.seed = seed
        self.agents: dict[int, Any] = dict(agents or {})
        self.trace_root = Path(traces) if traces else None
        self.game = Game(engine, engine.new_game(seed), seed=seed)
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
        # FR-39 with the fourth play mode of the vision: computer against computer. With a
        # seat for each computer opponent, nobody plays, and a watcher sees the whole board.
        self.self_playing = len(self.agents) >= 2
        self.room = rooms.Room(
            code=room_code or rooms.new_room_code(),
            hot_seat=hot_seat,
            computer_seats=frozenset(self.agents),
            watchers_only=self.self_playing,
        )
        self.attempts = rooms.Attempts()
        self.client_root = client_root
        self.allowed_origins = allowed_origins
        self.strict_los = strict_los
        self.odds = odds
        self.auto_forced = auto_forced
        self.connections: dict[str, Connection] = {}
        self._detached: dict[str, Connection] = {}
        self.latencies: list[float] = []
        self.agent_delay = float(agent_delay)
        self.commands_played = 0
        self.solo_task: asyncio.Task | None = None
        self.agent_task: asyncio.Task | None = None
        self.lock = asyncio.Lock()
        self.pending_auto: dict[int, list[str]] = {0: [], 1: []}
        self.setup_helpers: dict[int, Any] = {}
        self._legal_cache: tuple[State, int, bool, list[dict[str, Any]]] | None = None
        self._spectator_cache: tuple[State, dict[str, Any]] | None = None
        if save_dir is not None:
            header = {
                "game_id": f"{engine.scenario.id}-{seed}-{time.strftime('%Y%m%dT%H%M%S', time.gmtime())}-{secrets.token_hex(3)}",
                "seed": seed,
                "scenario": engine.scenario.id,
                "board_name": engine.board.name,
                "switches": {},
                "hot_seat": hot_seat,
                "agents": {},
                **(save_header or {}),
            }
            self.game.save = savegame.SaveFile.create(Path(save_dir), header)

    # ----------------------------------------------------------- save and resume

    def resume_from(self, path: str | Path) -> int:
        """Apply the commands of a save file and check each recorded hash.

        The game goes on in the same file. Gives the count of commands applied.
        """
        header, lines = savegame.load(path)
        if int(header["seed"]) != self.seed or header["scenario"] != self.engine.scenario.id:
            raise savegame.SaveFileError(
                f"the save file is scenario {header['scenario']} seed {header['seed']}, "
                f"and this host plays {self.engine.scenario.id} seed {self.seed}"
            )
        self.game.save = None
        for index, line in enumerate(lines):
            frame = self.engine.legal_commands(self.game.state)
            command_id = str(line.get("command_id") or Command.from_payload(line["payload"]).id)
            if frame.by_id(command_id) is None:
                raise savegame.SaveFileError(f"command {index} of the save file is not legal in the replay")
            self.game.apply(frame.frame_id, command_id, str(line.get("source", SOURCE_HUMAN)))
            if self.game.commands[-1]["hash"] != line["hash"]:
                raise savegame.SaveFileError(
                    f"command {index} of the save file gives a hash that is not the recorded hash"
                )
        self.game.save = savegame.SaveFile(Path(path), header, list(lines))
        return len(lines)

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

    async def handle(self, socket: ServerConnection) -> None:
        connection_id = f"c{id(socket)}-{secrets.token_hex(4)}"
        address = socket.remote_address[0] if socket.remote_address else "unknown"
        origin = socket.request.headers.get("Origin") if socket.request else None
        # The address this socket is bound to. A client Host header is not this address.
        local = socket.local_address
        bound = f"{local[0]}:{local[1]}" if local else None
        if not rooms.origin_allowed(origin, self.allowed_origins, bound):
            await self._send(socket, protocol.error_message("SR-03", "the origin is not allowed", protocol.CODE_ORIGIN))
            await socket.close()
            return
        if len(self.connections) >= MAX_CONNECTIONS:
            await self._send(
                socket,
                protocol.error_message("SR-03", "the host has too many connections", protocol.CODE_RATE_LIMITED),
            )
            await socket.close()
            return
        connection = Connection(connection_id, socket, address)
        self.connections[connection_id] = connection
        deadline = asyncio.create_task(self._join_deadline(connection))
        try:
            async for raw in socket:
                await self.on_message(connection, raw)
        except ConnectionClosed:
            pass
        finally:
            deadline.cancel()
            self.connections.pop(connection_id, None)
            self.room.release(connection_id)

    async def _join_deadline(self, connection: Connection) -> None:
        """S15: a socket that does not join in time is closed."""
        await asyncio.sleep(JOIN_DEADLINE_SECONDS)
        if not connection.joined and connection.socket is not None:
            await self._send(
                connection.socket,
                protocol.error_message("SR-03", "join in the first seconds of a connection", protocol.CODE_PROTOCOL),
            )
            await connection.socket.close()

    async def on_message(self, connection: Connection, raw: str | bytes) -> None:
        try:
            message = protocol.parse(raw)
        except ProtocolError as exc:
            await self.send(connection, protocol.error_message(exc.rule_id, exc.message, exc.code))
            return
        try:
            if message.type == protocol.CLIENT_JOIN:
                await self.on_join(connection, message)
                return
            if not connection.joined:
                raise ProtocolError("SR-03", f"join before you send {message.type}", protocol.CODE_SEAT)
            if message.type == protocol.CLIENT_INTENT:
                await self.on_intent(connection, message)
            elif message.type == protocol.CLIENT_VIEW_REQUEST:
                self._limit(connection)
                async with self.lock:
                    await self.send(connection, self.frame_for(connection))
            elif message.type == protocol.CLIENT_LOS_REQUEST:
                self._limit(connection)
                await self.on_los_request(connection, message)
            elif message.type == protocol.CLIENT_UNDO:
                await self.on_undo(connection)
            elif message.type == protocol.CLIENT_AUTO_SETUP:
                await self.on_auto_setup(connection)
            elif message.type == protocol.CLIENT_SETUP_LIFT:
                await self.on_setup_lift(connection, message)
            elif message.type == protocol.CLIENT_MOVE_TO:
                await self.on_move_to(connection, message)
            elif message.type == protocol.CLIENT_OPTIONS_REQUEST:
                self._limit(connection)
                await self.on_options_request(connection, message)
        except ProtocolError as exc:
            await self.send(connection, protocol.error_message(exc.rule_id, exc.message, exc.code))
        except IllegalCommand as exc:
            await self.send(connection, protocol.error_message(exc.rule_id, exc.message, protocol.CODE_ILLEGAL))
        except ConnectionClosed:
            raise
        except Exception as exc:  # noqa: BLE001 - the boundary: a host defect must not close the socket (S14)
            print(f"host: internal error on {message.type}: {exc!r}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)
            await self.send(
                connection,
                protocol.error_message("host", f"the host could not answer the {message.type} message", protocol.CODE_INTERNAL),
            )

    def _limit(self, connection: Connection) -> None:
        if not connection.requests.allow():
            raise ProtocolError("SR-03", "too many requests from this connection; wait a few seconds", protocol.CODE_REQUEST_LIMITED)

    async def on_join(self, connection: Connection, message: protocol.ClientMessage) -> None:
        if not self.attempts.allow(connection.address):
            await self.send(
                connection,
                protocol.error_message("SR-03", "too many join tries from this address", protocol.CODE_RATE_LIMITED),
            )
            await self._close(connection)
            return
        code = message.data.get("room_code", "")
        if not isinstance(code, str) or not rooms.code_matches(self.room.code, code):
            await self.send(connection, protocol.error_message("SR-03", "the room code is not correct", protocol.CODE_ROOM_CODE))
            await self._close(connection)
            return
        if connection.joined:
            raise ProtocolError("SR-03", "this connection already joined", protocol.CODE_SEAT)
        self.attempts.reset(connection.address)
        name = str(message.data.get("display_name", ""))[:40]
        token = message.data.get("seat_token")
        token = token if isinstance(token, str) and token else None
        async with self.lock:
            player, seat = self.room.take(connection.id, name, token)
            if player < 0 and not self.self_playing:
                await self.send(connection, protocol.error_message("SR-03", "the room is full", protocol.CODE_ROOM_FULL))
                await self._close(connection)
                return
            # A join with the token of a seat takes it back from a stale connection.
            for other in list(self.connections.values()):
                if other is connection or not other.joined or other.player != player or player < 0:
                    continue
                other.joined = False
                other.player = -1
                await self.send(
                    other,
                    protocol.error_message("SR-03", "another connection took this seat with its token", protocol.CODE_SEAT),
                )
                # The old socket can be dead, and its close can wait for a time out, so
                # the close does not hold the lock.
                asyncio.create_task(self._close(other))
            connection.joined = True
            connection.player = player
            connection.seat = seat
            await self.send(
                connection,
                protocol.welcome(
                    player,
                    seat,
                    view.board_document(self.engine.board),
                    self.scenario_document(),
                    self.strict_los,
                    sides=self.sides_document(connection),
                    seat_token=self.room.token_of(player) if player >= 0 else None,
                ),
            )
            if not self.self_playing and self._apply_forced():
                # A forced command changed the state, so every seat gets the new frame.
                await self.send_frames()
            else:
                await self.send(connection, self.frame_for(connection))
            await self._announce_game_over()
        self._start_agents()

    async def on_intent(self, connection: Connection, message: protocol.ClientMessage) -> None:
        token = str(message.require("frame_id"))
        command_id = str(message.require("command_id"))
        async with self.lock:
            active = self.game.state.active
            if active in self.agents:
                raise ProtocolError("FR-39", f"the {self.side_name(active)} side is a computer opponent", protocol.CODE_SEAT)
            if not self.room.controls(connection.id, active):
                raise ProtocolError("SR-03", "this connection does not hold the seat that acts now", protocol.CODE_SEAT)
            if not connection.token or token != connection.token or connection.token_hash != self._core_hash():
                raise ProtocolError(
                    "DR-04",
                    "the frame ID is not the newest frame the host sent; use the frame the host just sent",
                    protocol.CODE_STALE_FRAME,
                )
            started = time.perf_counter()
            self.game.apply(connection.token_hash, command_id, SOURCE_HUMAN)
            self._apply_forced()
            await self.send_frames()
            self.latencies.append(time.perf_counter() - started)
            await self._announce_game_over()
        self._start_agents()

    # ----------------------------------------------------------- computer turns

    def _start_agents(self) -> None:
        """Start the one task that plays the computer sides, when a computer side acts."""
        state = self.game.state
        if state.game_over or state.active not in self.agents:
            return
        if self.self_playing:
            if self.solo_task is None or self.solo_task.done():
                self.solo_task = asyncio.create_task(self.play_alone())
                self.solo_task.add_done_callback(_report_task)
            return
        if self.agent_task is None or self.agent_task.done():
            self.agent_task = asyncio.create_task(self._drive_agents())
            self.agent_task.add_done_callback(_report_task)

    async def _drive_agents(self, limit: int = MAX_AGENT_COMMANDS) -> int:
        """H1: a side that a computer holds plays in a worker thread, one command at a time.

        The frame goes to each connection after each command, with the status
        `computer_thinking`, so the other side and a watcher see each move.
        """
        played = 0
        while played < limit:
            async with self.lock:
                state = self.game.state
                if state.game_over or state.active not in self.agents:
                    break
            frame = await asyncio.to_thread(self.engine.legal_commands, state)
            if not frame.commands:
                raise RuntimeError(f"no legal command in {state.phase} for the computer opponent")
            agent = self.agents[state.active]
            chosen = await asyncio.to_thread(decide, agent, state, frame)
            async with self.lock:
                if self.game.state is not state:
                    continue
                self.game.apply(frame.frame_id, chosen, SOURCE_COMPUTER)
                self.commands_played += 1
                if not self.self_playing:
                    self._apply_forced()
                await self.send_frames()
                await self._announce_game_over()
            played += 1
            if self.agent_delay:
                await asyncio.sleep(self.agent_delay)
        return played

    def _apply_forced(self) -> int:
        """Slice 8: a frame of a person's side with one legal command is applied for them.
        The end of the set up is not: the person says when the set up is complete.

        The label goes to the person in the next frame (`auto_applied`), and the log has a
        line for it. The lock is held by the caller.
        """
        if not self.auto_forced or self.self_playing:
            return 0
        applied = 0
        while applied < MAX_AGENT_COMMANDS:
            state = self.game.state
            if state.game_over or state.active in self.agents:
                break
            frame = self.engine.legal_commands(state)
            if len(frame.commands) != 1:
                break
            only = frame.commands[0]
            if only.command.action == "end_setup":
                # A side arranges its counters until it says the set up is complete (rule
                # 21.2), and the person may still pick a counter up, so the host waits.
                break
            text = annotate.command_label(state, only, self.game.names, frame.player)
            self.game.apply(frame.frame_id, only.id, SOURCE_FORCED)
            self.game.log.append(
                {"rule_id": HOST_RULE, "kind": "forced_command", "data": {"label": text, "player": frame.player}}
            )
            self.pending_auto.setdefault(frame.player, []).append(text)
            applied += 1
        return applied

    def run_agents(self) -> int:
        """FR-39 with no event loop: a computer side plays until a person acts again.

        The host itself uses `_drive_agents`, which runs the agent in a thread. This is
        for a caller with no loop, such as a test. A game that plays itself does not use it.
        """
        if self.self_playing:
            return 0
        played = 0
        while not self.game.state.game_over and self.game.state.active in self.agents and played < MAX_AGENT_COMMANDS:
            frame = self.engine.legal_commands(self.game.state)
            if not frame.commands:
                raise RuntimeError(f"no legal command in {self.game.state.phase} for the computer opponent")
            agent = self.agents[self.game.state.active]
            chosen = decide(agent, self.game.state, frame)
            self.game.apply(frame.frame_id, chosen, SOURCE_COMPUTER)
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
        chosen = decide(agent, self.game.state, frame)
        self.game.apply(frame.frame_id, chosen, SOURCE_COMPUTER)
        self.commands_played += 1
        return True

    async def play_alone(self, limit: int = MAX_AGENT_COMMANDS) -> str:
        """Play a game between two computer opponents, and show each command.

        The agents choose in a worker thread. The task sends the new frame to each
        watcher after each command and waits. The wait is what makes the game
        watchable; a test sets it to zero and a person sets it to a fraction of a second.
        """
        remaining = max(0, limit - self.commands_played)
        await self._drive_agents(remaining)
        if self.game.state.game_over:
            async with self.lock:
                await self._announce_game_over()
            return str(self.game.state.result)
        return "no_result"

    # --------------------------------------------------------- undo and set up

    async def on_undo(self, connection: Connection) -> None:
        """Slice 8: take back the last command of the person at the screen.

        Hot seat and a game against the computer only. The commands taken back are the
        last command of a person and the forced commands after it. Each must be quiet: no
        die rolled, and the player saw nothing new of the other side. The host plays the
        seed and the commands before them again and checks each hash.
        """
        async with self.lock:
            if not self.room.hot_seat or self.self_playing:
                raise ProtocolError("host", "undo is for hot seat and for a game against the computer", protocol.CODE_UNDO_REFUSED)
            state = self.game.state
            if state.game_over:
                raise ProtocolError("host", "the game is over", protocol.CODE_UNDO_REFUSED)
            if state.active in self.agents:
                raise ProtocolError("host", "the computer is playing its side", protocol.CODE_UNDO_REFUSED)
            if not self.room.controls(connection.id, state.active):
                raise ProtocolError("SR-03", "this connection does not hold the seat that acts now", protocol.CODE_UNDO_REFUSED)
            count = self.undo_count()
            if count == 0:
                raise ProtocolError(
                    "host",
                    "there is no command to take back: the last command rolled a die, showed something of the "
                    "other side, or was not yours",
                    protocol.CODE_UNDO_REFUSED,
                )
            keep = len(self.game.commands) - count
            try:
                restored = await asyncio.to_thread(self.game.replay_to, keep)
            except savegame.SaveFileError as exc:
                raise ProtocolError("host", f"the replay for the undo failed: {exc}", protocol.CODE_UNDO_REFUSED) from exc
            player = self.game.commands[keep]["player"]
            self.game.take_back(count, restored)
            self.game.log.append(
                {"rule_id": HOST_RULE, "kind": "undo", "data": {"commands": count, "player": player}}
            )
            self.pending_auto = {0: [], 1: []}
            await self.send_frames()

    def undo_count(self) -> int:
        """How many commands an undo takes back now, or 0 when it may not."""
        commands = self.game.commands
        active = self.game.state.active
        count = 0
        for record in reversed(commands):
            if not record.get("quiet"):
                return 0
            count += 1
            if record["source"] in (SOURCE_FORCED, SOURCE_ROUTE):
                continue
            if record["source"] in (SOURCE_HUMAN, SOURCE_SETUP) and record["player"] == active:
                return count
            return 0
        return 0

    async def on_auto_setup(self, connection: Connection) -> None:
        """Slice 8: the v7 agent sets up the side of the person who asks."""
        async with self.lock:
            state = self.game.state
            player = state.active
            if state.phase != PHASE_SETUP or state.game_over:
                raise ProtocolError("21.1", "the set up is over", protocol.CODE_ILLEGAL)
            if player in self.agents or not self.room.controls(connection.id, player):
                raise ProtocolError("SR-03", "this connection does not hold the side that sets up now", protocol.CODE_SEAT)
            helper = self.setup_helpers.get(player)
            if helper is None:
                from slagents.registry import make_agent

                helper = make_agent(SETUP_AGENT, self.engine, self.seed, player)
                self.setup_helpers[player] = helper
        placed = 0
        while placed < MAX_AGENT_COMMANDS:
            async with self.lock:
                state = self.game.state
                if state.game_over or state.phase != PHASE_SETUP or state.active != player:
                    break
            frame = await asyncio.to_thread(self.engine.legal_commands, state)
            if not frame.commands:
                break
            chosen = await asyncio.to_thread(decide, helper, state, frame)
            async with self.lock:
                if self.game.state is not state:
                    break
                self.game.apply(frame.frame_id, chosen, SOURCE_SETUP)
                placed += 1
                await self.send_frames()
        async with self.lock:
            self.game.log.append(
                {"rule_id": HOST_RULE, "kind": "setup_helper", "data": {"player": player, "commands": placed}}
            )
            self._apply_forced()
            await self.send_frames()
            await self._announce_game_over()
        self._start_agents()

    async def on_setup_lift(self, connection: Connection, message: protocol.ClientMessage) -> None:
        """Take a placed unit of the person off the board while the side sets up.

        A side arranges its counters until it declares the set up complete (rule 21.2), so
        the person may pick up a unit and place it again. `Game.lift` plays the game again
        through the core without the place command of the unit.
        """
        unit = message.require("unit")
        if not isinstance(unit, int) or isinstance(unit, bool):
            raise ProtocolError("protocol", "the setup_lift message needs a unit ID")
        async with self.lock:
            state = self.game.state
            player = state.active
            if state.phase != PHASE_SETUP or state.game_over:
                raise ProtocolError("21.1", "the set up is over", protocol.CODE_ILLEGAL)
            if player in self.agents or not self.room.controls(connection.id, player):
                raise ProtocolError("SR-03", "this connection does not hold the side that sets up now", protocol.CODE_SEAT)
            try:
                left_out = await asyncio.to_thread(self.game.lift, unit, player)
            except savegame.SaveFileError as exc:
                raise ProtocolError("host", f"the replay for the pick up failed: {exc}", protocol.CODE_ILLEGAL) from exc
            self.game.log.append(
                {"rule_id": HOST_RULE, "kind": "setup_lift", "data": {"unit": unit, "player": player, "commands": left_out}}
            )
            self.pending_auto = {0: [], 1: []}
            await self.send_frames()

    async def on_move_to(self, connection: Connection, message: protocol.ClientMessage) -> None:
        """Move a unit of the person to a hex it reaches in this Movement Phase.

        The path is the cheapest one of `options.route`, the path the pale shade of the
        window shows. A vehicle can pivot first (PR-30), and each of its steps names the
        facing to its next hex (rule 30.5). Each step is a command of the legal list at that time, and
        `Game.apply` applies it as an intent of the person, so the log, the save file, and
        an undo hold the single steps. The move stops when a step is not legal, for example
        when a hidden unit stops it (rule 42.5).
        """
        token = str(message.require("frame_id"))
        unit = message.require("unit")
        if not isinstance(unit, int) or isinstance(unit, bool):
            raise ProtocolError("protocol", "the move_to message needs a unit ID")
        try:
            target = geometry.parse_hex_id(str(message.require("hex")))
        except ValueError as exc:
            raise ProtocolError("protocol", f"a hex name is not valid: {exc}") from exc
        async with self.lock:
            state = self.game.state
            active = state.active
            if active in self.agents or not self.room.controls(connection.id, active):
                raise ProtocolError("SR-03", "this connection does not hold the seat that acts now", protocol.CODE_SEAT)
            if not connection.token or token != connection.token or connection.token_hash != self._core_hash():
                raise ProtocolError(
                    "DR-04",
                    "the frame ID is not the newest frame the host sent; use the frame the host just sent",
                    protocol.CODE_STALE_FRAME,
                )
            if state.phase != PHASE_MOVEMENT:
                raise ProtocolError("5.1", "a unit moves to a far hex only in the Movement Phase", protocol.CODE_ILLEGAL)
            if not 0 <= unit < len(state.units) or state.units[unit].player != active:
                raise ProtocolError("protocol", f"unit {unit} is not a unit of the side that moves", protocol.CODE_ILLEGAL)
            steps = options.route(self.engine, state, state.units[unit], target)
            name = geometry.hex_id(*target)
            if steps is None:
                raise ProtocolError("5.4", f"the unit cannot get to {name} in this phase", protocol.CODE_ILLEGAL)
            path = [step.hex for step in steps if step.hex is not None]
            done = 0
            applied = 0
            for step in steps:
                frame, legal = options.route_step(self.engine, self.game.state, step)
                if legal is None:
                    break
                self.game.apply(frame.frame_id, legal.id, SOURCE_HUMAN if applied == 0 else SOURCE_ROUTE)
                applied += 1
                if step.hex is None:
                    continue
                done += 1
                if self.game.state.phase != PHASE_MOVEMENT or self.game.state.units[unit].hex != step.hex:
                    break
            here = self.game.state.units[unit].hex
            self.game.log.append(
                {
                    "rule_id": HOST_RULE,
                    "kind": "move_to",
                    "data": {"unit": unit, "hex": name, "steps": done, "of": len(path), "player": active},
                }
            )
            self._apply_forced()
            await self.send_frames()
            await self._announce_game_over()
            if done < len(path):
                where = geometry.hex_id(*here) if here is not None else "its hex"
                await self.send(
                    connection,
                    protocol.error_message(
                        "5.4",
                        f"the move stopped in {where} after {done} of {len(path)} hexes: the next hex is not a legal step now",
                        protocol.CODE_ILLEGAL,
                    ),
                )
        self._start_agents()

    async def on_options_request(self, connection: Connection, message: protocol.ClientMessage) -> None:
        """The options of one unit of the person's side (`slhost.options`): why a hex refuses
        it in the set up, where it can go in the Movement Phase, and its field of fire."""
        unit = message.require("unit")
        if not isinstance(unit, int) or isinstance(unit, bool):
            raise ProtocolError("protocol", "the options_request message needs a unit ID")
        async with self.lock:
            state = self.game.state
            if not 0 <= unit < len(state.units):
                raise ProtocolError("protocol", f"no unit has the ID {unit}")
            owner = state.units[unit].player
            if not self.room.controls(connection.id, owner):
                # AR-09: the options of a unit tell where it is and what it sees.
                raise ProtocolError("SR-03", "this connection does not hold the side of that unit", protocol.CODE_SEAT)
            result = await asyncio.to_thread(options.unit_options, self.engine, state, unit, self.strict_los)
            await self.send(connection, protocol.options_result_message(unit, connection.token, result))

    async def on_los_request(self, connection: Connection, message: protocol.ClientMessage) -> None:
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

    def side_name(self, player: int) -> str:
        return self.game.sides.get(player, f"player {player}")

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

    def sides_document(self, connection: Connection | None = None) -> dict[str, dict[str, str]]:
        """The name and the controller of each side, as this connection sees them."""
        out: dict[str, dict[str, str]] = {}
        for player in (0, 1):
            if player in self.agents:
                controller = "computer"
            elif self.room.hot_seat:
                controller = "human"
            elif connection is not None and connection.player == player:
                controller = "human"
            else:
                controller = "remote"
            out[str(player)] = {"name": self.side_name(player), "controller": controller}
        return out

    async def _send(self, socket: ServerConnection, message: dict[str, Any]) -> None:
        try:
            await socket.send(protocol.dump(message))
        except ConnectionClosed:
            pass

    async def send(self, connection: Connection, message: dict[str, Any]) -> None:
        if connection.socket is not None:
            await self._send(connection.socket, message)

    async def _close(self, connection: Connection) -> None:
        if connection.socket is not None:
            with contextlib.suppress(ConnectionClosed):
                await connection.socket.close()

    async def broadcast(self, message: dict[str, Any]) -> None:
        for connection in list(self.connections.values()):
            if connection.joined:
                await self.send(connection, message)

    def _core_hash(self) -> str:
        return self.engine.hash_state(self.game.state)

    def _stream_of(self, player: int, spectator: bool) -> tuple[str, int, bool]:
        """The log stream a connection reads: its key, its viewer, and the spectator flag.

        Hot seat reads the stream of the side it shows, so each side has its own `seq`
        and a side does not keep the lines of the other side in its history. A client
        keeps one log for each value of `frame.player`.
        """
        if spectator or self.self_playing:
            return STREAM_SPECTATOR, view.SPECTATOR, True
        return f"p{player}", player, False

    def _legal_for(self, viewer: int) -> list[dict[str, Any]]:
        """The legal list of the current frame with its names, labels, hexes, and odds."""
        state = self.game.state
        cached = self._legal_cache
        if cached is not None and cached[0] is state and cached[1] == viewer and cached[2] == self.odds:
            return cached[3]
        frame = self.engine.legal_commands(state)
        entries = annotate.legal_entries(self.engine, state, frame, self.game.names, viewer, self.odds)
        self._legal_cache = (state, viewer, self.odds, entries)
        return entries

    def status_for(self, connection_id: str, player: int, spectator: bool) -> str:
        state = self.game.state
        if state.game_over:
            return protocol.STATUS_GAME_OVER
        if state.active in self.agents:
            return protocol.STATUS_COMPUTER
        if not spectator and self.room.controls(connection_id, state.active):
            return protocol.STATUS_YOUR_TURN
        return protocol.STATUS_WAITING

    def outbound_frame(self, connection_id: str, player: int, spectator: bool = False) -> dict[str, Any]:
        """The frame this connection may read (AR-09).

        Hot seat and a spectator keep the legal list. In a LAN room the list goes only
        to the connection that acts for the active seat. The other seat gets an empty
        list. The log tail is the lines of this viewer that the connection has not had.
        The frame ID is the token of this connection and never the state hash (S1).
        """
        connection = self.connections.get(connection_id)
        if connection is None:
            # A caller with no socket, such as a test that reads the frames of two seats.
            connection = self._detached.setdefault(connection_id, Connection(connection_id, None, "", player=player))
        core = self.engine.legal_commands(self.game.state)
        core_hash = core.frame_id
        if connection.token_hash != core_hash or not connection.token:
            connection.token = secrets.token_hex(TOKEN_BYTES)
            connection.token_hash = core_hash
        spectator = spectator or self.self_playing
        key, viewer, is_spectator = self._stream_of(player, spectator)
        stream = self.game.stream(key, viewer, is_spectator)
        start = connection.sent.get(key)
        if start is None:
            # The first frame of this stream on this connection holds the history. A line
            # that names a unit this viewer cannot see now stays out of it (AR-09).
            history = stream.lines[max(0, len(stream.lines) - LOG_HISTORY) :]
            tail = [line for line in history if is_spectator or view.event_visible(self.game.state, line, viewer)]
        else:
            tail = stream.lines[start:]
        connection.sent[key] = len(stream.lines)
        frame = {
            "player": core.player,
            "phase": core.phase,
            "sub_step": core.sub_step,
            "turn": core.turn,
        }
        status = self.status_for(connection_id, player, spectator)
        phase_text = annotate.phase_text(core.phase, core.sub_step)
        if spectator:
            # One document for each state, however many watchers there are (H3).
            cached = self._spectator_cache
            if cached is None or cached[0] is not self.game.state:
                cached = (self.game.state, self.game.spectator_view(True))
                self._spectator_cache = cached
            document = cached[1]
            return protocol.frame_message(
                view.SPECTATOR,
                document,
                {**frame, "commands": []},
                tail,
                connection.token,
                status,
                phase_text=phase_text,
                objectives=objectives.document(self.engine, self.game.state, view.SPECTATOR, self.game.sides, spectator=True),
            )
        acts = self.room.controls(connection_id, self.game.state.active) and self.game.state.active not in self.agents
        commands: list[dict[str, Any]] = []
        if acts:
            commands = self._legal_for(core.player)
            phase_text = annotate.fire_group_text(self.game.state) or phase_text
        auto: list[str] = []
        if self.room.hot_seat:
            for side in (0, 1):
                auto.extend(self.pending_auto.get(side, []))
                self.pending_auto[side] = []
        else:
            auto = list(self.pending_auto.get(player, []))
            self.pending_auto[player] = []
        can_undo = self.room.hot_seat and not self.self_playing and self.undo_count() > 0 and acts
        return protocol.frame_message(
            player,
            self.game.view_for(player),
            {**frame, "commands": commands},
            tail,
            connection.token,
            status,
            auto_applied=auto,
            can_undo=can_undo,
            phase_text=phase_text,
            objectives=objectives.document(self.engine, self.game.state, player, self.game.sides),
        )

    def frame_for(self, connection: Connection) -> dict[str, Any]:
        """The frame of one joined connection. The lock is held by the caller."""
        if self.self_playing:
            return self.outbound_frame(connection.id, view.SPECTATOR, spectator=True)
        if self.room.hot_seat:
            return self.outbound_frame(connection.id, self.human_player())
        return self.outbound_frame(connection.id, connection.player)

    async def send_frames(self) -> None:
        """One frame for each joined connection (AR-09). An unjoined socket gets none.

        Hot seat gets the view of the side that acts, and it keeps the legal list, because
        one client plays that side. A LAN seat gets its own view. The idle seat gets an
        empty legal list. A watcher of two computer opponents gets the spectator view.
        """
        for connection in list(self.connections.values()):
            if not connection.joined:
                continue
            await self.send(connection, self.frame_for(connection))

    def game_over_document(self) -> dict[str, Any]:
        state = self.game.state
        players = list(self.engine.scenario.players())
        winner = players.index(state.result) if state.result in players else None
        return protocol.game_over_message(
            winner,
            annotate.with_side_names(state.result_cause, self.game.sides),
            winner_name=self.side_name(winner) if winner is not None else "",
            outcome=state.result,
            conditions=annotate.game_end_conditions(self.game.log),
            turn=state.turn,
            casualties=annotate.casualties(state),
        )

    async def _announce_game_over(self) -> None:
        """H5: each joined connection gets `game_over` one time, on each path to the end."""
        if not self.game.state.game_over:
            return
        message = self.game_over_document()
        for connection in list(self.connections.values()):
            if connection.joined and not connection.game_over_sent:
                connection.game_over_sent = True
                await self.send(connection, message)

    # ------------------------------------------------------------------ server

    @contextlib.asynccontextmanager
    async def start(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        """Serve until the block ends. Port 0 asks the system for a free port."""
        async with serve(
            self.handle,
            host,
            port,
            process_request=self.serve_file,
            max_size=protocol.MAX_MESSAGE_BYTES,
            max_queue=MAX_QUEUE,
        ) as server:
            try:
                yield server
            finally:
                for task in (self.agent_task, self.solo_task):
                    if task is not None and not task.done():
                        task.cancel()
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await task

    @staticmethod
    def bound_port(server: Any) -> int:
        return int(next(iter(server.sockets)).getsockname()[1])

    async def run(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
        async with self.start(host, port) as server:
            await server.serve_forever()


def local_addresses(port: int) -> Iterable[str]:
    yield f"http://{DEFAULT_HOST}:{port}/"
