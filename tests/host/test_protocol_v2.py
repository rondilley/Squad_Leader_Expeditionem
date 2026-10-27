"""Protocol version 2 of the host, over real sockets with the real engine.

The findings of `docs/reports/2026-09-23_opus_review.md` that these tests hold:

- S1: the frame ID is a token for each connection, and no message holds the state hash.
- S8, S9, H3: seat tokens, reserved seats, no seat of a computer to a client, and any
  count of watchers of two computer opponents.
- S10: the `seq` of each viewer has no gap.
- S14, S15: a room code that is not ASCII, the error code `internal`, the message size,
  the join deadline, the connection cap, and the request rate.
- H1: the computer plays in a worker thread, so the host answers during its turn.
- H5, H6: `game_over` on each path, with its fields, and a code on each error.
"""

from __future__ import annotations

import asyncio
import json
import re

import pytest
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed

from slagents.base import RandomAgent
from slcli.play import build_engine, make_agent
from slhost import protocol, rooms, server
from slhost.rooms import Attempts
from slhost.server import Host

HEX64 = re.compile(r"[0-9a-f]{64}")


@pytest.fixture(scope="module")
def drill():
    return build_engine("s00_movement_drill")


class Client:
    """A test client that keeps every raw message it gets."""

    def __init__(self, socket, name: str = "tester") -> None:
        self.socket = socket
        self.name = name
        self.raw: list[str] = []
        self.player = -1
        self.token: str | None = None
        self.last: dict | None = None

    async def send(self, message: dict) -> None:
        await self.socket.send(protocol.dump(message))

    async def receive(self, timeout: float = 30.0) -> dict:
        text = await asyncio.wait_for(self.socket.recv(), timeout)
        self.raw.append(text)
        message = json.loads(text)
        if message["type"] == protocol.HOST_FRAME:
            self.last = message
        return message

    async def receive_until(self, kind: str, limit: int = 4000, timeout: float = 30.0) -> dict:
        for _ in range(limit):
            message = await self.receive(timeout)
            if message["type"] == kind:
                return message
        raise AssertionError(f"no {kind} message arrived for {self.name}")

    async def drain(self, quiet: float = 0.2) -> None:
        """Read until the host is quiet for a moment."""
        while True:
            try:
                await self.receive(quiet)
            except asyncio.TimeoutError:
                return

    async def join(self, code: str, token: str | None = None) -> dict:
        message = {"type": "join", "room_code": code, "display_name": self.name}
        if token:
            message["seat_token"] = token
        await self.send(message)
        answer = await self.receive()
        if answer["type"] == protocol.HOST_WELCOME:
            self.player = answer["player"]
            self.token = answer.get("seat_token")
        return answer


async def open_host(engine, **kwargs):
    host = Host(engine, seed=kwargs.pop("seed", 1), **kwargs)
    manager = host.start("127.0.0.1", 0)
    started = await manager.__aenter__()
    return host, manager, Host.bound_port(started)


def url(port: int) -> str:
    return f"ws://127.0.0.1:{port}"


# ------------------------------------------------------------------------ S1


async def test_the_idle_seat_never_gets_the_state_hash():
    """S1: no message to the idle seat holds the core hash, or any 64 hex digits."""
    engine = build_engine("s01_guards_counterattack")
    host, manager, port = await open_host(engine, hot_seat=False)
    try:
        async with connect(url(port)) as a, connect(url(port)) as b:
            first, second = Client(a, "first"), Client(b, "second")
            await first.join(host.room.code)
            await second.join(host.room.code)
            by_player = {first.player: first, second.player: second}
            await first.drain()
            await second.drain()
            for _ in range(30):
                active = host.game.state.active
                actor = by_player[active]
                assert actor.last is not None and actor.last["legal_commands"]
                await actor.send(
                    {"type": "intent", "frame_id": actor.last["frame_id"], "command_id": actor.last["legal_commands"][0]["id"]}
                )
                await first.drain()
                await second.drain()
            await first.send({"type": "los_request", "from": "A1", "to": "B2"})
            await second.send({"type": "view_request"})
            await first.drain()
            await second.drain()
            hashes = {engine.hash_state(engine.new_game(1))} | {c["hash"] for c in host.game.commands}
            hashes.add(engine.hash_state(host.game.state))
            assert len(host.game.commands) >= 30
            for client in (first, second):
                assert client.raw
                for text in client.raw:
                    assert not HEX64.search(text), f"a message to {client.name} holds 64 hex digits"
                    for value in hashes:
                        assert value not in text
                        assert value[:32] not in text, "no part of the hash is a token"
                tokens = [json.loads(t)["frame_id"] for t in client.raw if json.loads(t)["type"] == "frame"]
                assert all(re.fullmatch(r"[0-9a-f]{32}", t) for t in tokens)
            ids_a = {json.loads(t)["frame_id"] for t in first.raw if json.loads(t)["type"] == "frame"}
            ids_b = {json.loads(t)["frame_id"] for t in second.raw if json.loads(t)["type"] == "frame"}
            assert not ids_a & ids_b, "each connection gets its own tokens"
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_token_of_another_connection_is_stale(drill):
    """S1: a token is good for the connection that got it, and for the newest frame only."""
    host, manager, port = await open_host(drill)
    try:
        async with connect(url(port)) as socket:
            client = Client(socket)
            await client.join(host.room.code)
            frame = await client.receive_until(protocol.HOST_FRAME)
            await client.send({"type": "intent", "frame_id": "f" * 32, "command_id": frame["legal_commands"][0]["id"]})
            error = await client.receive_until(protocol.HOST_ERROR)
            assert error["code"] == protocol.CODE_STALE_FRAME
            await client.send({"type": "view_request"})
            again = await client.receive_until(protocol.HOST_FRAME)
            assert again["frame_id"] == frame["frame_id"], "the same state keeps its token on one connection"
            assert not host.game.commands
    finally:
        await manager.__aexit__(None, None, None)


# ------------------------------------------------------------ S8, S9, H3


async def test_a_seat_of_the_computer_is_not_given_to_a_client():
    """S8: with --lan and a computer opponent, a second connection gets no seat."""
    engine = build_engine("s01_guards_counterattack")
    host, manager, port = await open_host(engine, hot_seat=False, agents={1: make_agent("v1", engine, 1, 1)})
    try:
        async with connect(url(port)) as a, connect(url(port)) as b:
            first, second = Client(a, "first"), Client(b, "second")
            welcome = await first.join(host.room.code)
            assert welcome["player"] == 0
            answer = await second.join(host.room.code)
            assert answer["type"] == protocol.HOST_ERROR
            assert answer["code"] == protocol.CODE_ROOM_FULL
            assert 1 not in host.room.seats, "the seat of the computer stays with the computer"
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_dropped_seat_is_held_for_its_token(drill):
    """S9: the other player cannot take a dropped seat, and the token gets it back."""
    host, manager, port = await open_host(drill, hot_seat=False)
    try:
        async with connect(url(port)) as b:
            second = Client(b, "second")
            async with connect(url(port)) as a:
                first = Client(a, "first")
                await first.join(host.room.code)
                assert re.fullmatch(r"[0-9a-f]{32}", first.token or "")
                await second.join(host.room.code)
                assert first.player == 0 and second.player == 1
                assert first.token != second.token
            await asyncio.sleep(0.2)
            async with connect(url(port)) as c:
                stranger = Client(c, "stranger")
                answer = await stranger.join(host.room.code)
                assert answer["type"] == protocol.HOST_ERROR and answer["code"] == protocol.CODE_ROOM_FULL
            async with connect(url(port)) as d:
                back = Client(d, "back")
                welcome = await back.join(host.room.code, first.token)
                assert welcome["type"] == protocol.HOST_WELCOME
                assert welcome["player"] == 0, "the token gives the same seat"
                assert welcome["seat_token"] == first.token
                # A second join with the same token takes the seat from a stale connection.
                async with connect(url(port)) as e:
                    again = Client(e, "again")
                    welcome = await again.join(host.room.code, first.token)
                    assert welcome["player"] == 0
                    error = await back.receive_until(protocol.HOST_ERROR)
                    assert error["code"] == protocol.CODE_SEAT
                    assert host.room.seats[0] != host.room.seats[1]
    finally:
        await manager.__aexit__(None, None, None)


async def test_many_watchers_see_two_computer_opponents():
    """H3: each client of a game between two computers is a watcher, with no limit."""
    engine = build_engine("s01_guards_counterattack")
    agents = {0: make_agent("v1", engine, 1, 0), 1: make_agent("v1", engine, 1, 1)}
    host, manager, port = await open_host(engine, agents=agents, agent_delay=0.05)
    try:
        sockets = [await connect(url(port)) for _ in range(4)]
        try:
            clients = [Client(s, f"watcher {i}") for i, s in enumerate(sockets)]
            for client in clients:
                welcome = await client.join(host.room.code)
                assert welcome["type"] == protocol.HOST_WELCOME
                assert welcome["seat"] == "watcher" and welcome["you"] == -1
                assert "seat_token" not in welcome
                assert {s["controller"] for s in welcome["sides"].values()} == {"computer"}
            for client in clients:
                frame = await client.receive_until(protocol.HOST_FRAME)
                assert frame["view"]["spectator"] is True
                assert frame["status"] in (protocol.STATUS_COMPUTER, protocol.STATUS_GAME_OVER)
        finally:
            for s in sockets:
                await s.close()
    finally:
        await manager.__aexit__(None, None, None)


# ----------------------------------------------------------------------- S10


def test_each_viewer_reads_a_log_with_no_gap():
    """S10: the `seq` of each viewer counts its own lines, so a hidden line leaves no gap.

    Scenario 2 has concealment, so each side makes lines the other side must not read.
    The frames are the ones the host sends to each seat after each command.
    """
    engine = build_engine("s02_tractor_works")
    host = Host(engine, seed=4, hot_seat=False, auto_forced=False, odds=False)
    host.room.take("c0", "one")
    host.room.take("c1", "two")
    agents = (RandomAgent(4, 0), RandomAgent(5, 1))
    got: dict[int, list[dict]] = {0: [], 1: []}
    for _ in range(500):
        state = host.game.state
        if state.game_over:
            break
        for viewer in (0, 1):
            got[viewer].extend(host.outbound_frame(f"c{viewer}", viewer)["log_tail"])
        frame = engine.legal_commands(state)
        host.game.apply(frame.frame_id, agents[frame.player].select(state, frame))
    for viewer in (0, 1):
        got[viewer].extend(host.outbound_frame(f"c{viewer}", viewer)["log_tail"])
    total = len(host.game.log)
    for viewer in (0, 1):
        seqs = [line["seq"] for line in got[viewer]]
        assert seqs == list(range(len(seqs))), f"the log of player {viewer} has a gap"
        assert len(seqs) < total, "the viewer does not get every line, so the test has hidden lines"
    assert len(got[0]) != len(got[1])


async def test_a_hot_seat_frame_log_has_no_gap(drill):
    """S10 over a socket: the lines of one viewer come in order with no gap."""
    host, manager, port = await open_host(drill)
    try:
        async with connect(url(port)) as socket:
            client = Client(socket)
            await client.join(host.room.code)
            lines: dict[int, list[int]] = {}
            frame = await client.receive_until(protocol.HOST_FRAME)
            for _ in range(40):
                lines.setdefault(frame["player"], []).extend(e["seq"] for e in frame["log_tail"])
                if not frame["legal_commands"]:
                    break
                await client.send({"type": "intent", "frame_id": frame["frame_id"], "command_id": frame["legal_commands"][0]["id"]})
                frame = await client.receive_until(protocol.HOST_FRAME)
            assert lines
            for seqs in lines.values():
                assert seqs == list(range(len(seqs)))
            named = [e for e in host.game.log_tail_for(0) if e.get("names")]
            assert named and all("#" in n or " " in n for e in named for n in e["names"].values())
    finally:
        await manager.__aexit__(None, None, None)


# ------------------------------------------------------------------ S14, S15


async def test_a_room_code_that_is_not_ascii_gets_an_answer(drill):
    """S14: the comparison is on bytes, so the host answers and does not close with 1011."""
    host, manager, port = await open_host(drill)
    try:
        async with connect(url(port)) as socket:
            client = Client(socket)
            answer = await client.join("é" * 32)
            assert answer["type"] == protocol.HOST_ERROR
            assert answer["code"] == protocol.CODE_ROOM_CODE
        async with connect(url(port)) as socket:
            client = Client(socket)
            await client.send({"type": "join", "room_code": 12345})
            answer = await client.receive()
            assert answer["code"] == protocol.CODE_ROOM_CODE
    finally:
        await manager.__aexit__(None, None, None)
    assert rooms.code_matches("abc", "abc")
    assert not rooms.code_matches("abc", "ébc")
    assert not rooms.code_matches("abc", "\ud800")


async def test_a_host_defect_gives_the_code_internal_and_the_host_stays_up(drill, tmp_path):
    """S14: an error that is not a protocol error gives `internal`, and the socket stays open.

    The defect here is real: the save file of the game is a directory, so the write fails.
    """
    host, manager, port = await open_host(drill, save_dir=tmp_path)
    try:
        path = host.game.save.path
        path.unlink()
        path.mkdir()
        async with connect(url(port)) as socket:
            client = Client(socket)
            await client.join(host.room.code)
            frame = await client.receive_until(protocol.HOST_FRAME)
            await client.send({"type": "intent", "frame_id": frame["frame_id"], "command_id": frame["legal_commands"][0]["id"]})
            error = await client.receive_until(protocol.HOST_ERROR)
            assert error["code"] == protocol.CODE_INTERNAL
            await client.send({"type": "view_request"})
            assert (await client.receive_until(protocol.HOST_FRAME))["type"] == protocol.HOST_FRAME
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_message_over_the_size_limit_closes_the_socket(drill):
    """S15: the server reads no more than the limit, and it closes with 1009."""
    host, manager, port = await open_host(drill)
    try:
        async with connect(url(port), max_size=None) as socket:
            await socket.send("x" * (protocol.MAX_MESSAGE_BYTES + 10))
            with pytest.raises(ConnectionClosed) as exc:
                for _ in range(4):
                    await asyncio.wait_for(socket.recv(), 5)
            assert exc.value.rcvd is not None and exc.value.rcvd.code == 1009
    finally:
        await manager.__aexit__(None, None, None)


def test_the_size_check_counts_bytes_and_not_characters():
    """S15: a text of 30,000 characters of 3 bytes each is 90,000 bytes."""
    with pytest.raises(protocol.ProtocolError):
        protocol.parse('{"type":"join","x":"' + "€" * 30000 + '"}')


async def test_a_socket_that_does_not_join_is_closed(drill, monkeypatch):
    monkeypatch.setattr(server, "JOIN_DEADLINE_SECONDS", 0.3)
    host, manager, port = await open_host(drill)
    try:
        async with connect(url(port)) as socket:
            with pytest.raises(ConnectionClosed):
                for _ in range(4):
                    await asyncio.wait_for(socket.recv(), 5)
    finally:
        await manager.__aexit__(None, None, None)


async def test_the_count_of_connections_has_a_cap(drill, monkeypatch):
    monkeypatch.setattr(server, "MAX_CONNECTIONS", 2)
    host, manager, port = await open_host(drill)
    try:
        async with connect(url(port)) as a, connect(url(port)) as b, connect(url(port)) as c:
            answer = json.loads(await asyncio.wait_for(c.recv(), 5))
            assert answer["type"] == protocol.HOST_ERROR
            assert answer["code"] == protocol.CODE_RATE_LIMITED
            assert len(host.connections) == 2
            del a, b
    finally:
        await manager.__aexit__(None, None, None)


async def test_view_and_line_of_sight_requests_have_a_rate_limit(drill):
    host, manager, port = await open_host(drill)
    try:
        async with connect(url(port)) as socket:
            client = Client(socket)
            await client.join(host.room.code)
            await client.drain()
            for index in range(server.REQUEST_LIMIT + 10):
                kind = "view_request" if index % 2 else "los_request"
                await client.send({"type": kind, "from": "A1", "to": "A4"})
            codes = []
            for _ in range(server.REQUEST_LIMIT + 10):
                message = await client.receive(5)
                if message["type"] == protocol.HOST_ERROR:
                    codes.append(message["code"])
            # The question limit is not the join limit: the session goes on (SR-03).
            assert set(codes) == {protocol.CODE_REQUEST_LIMITED}
            assert protocol.CODE_REQUEST_LIMITED not in protocol.TERMINAL_CODES
            assert len(codes) == 10
    finally:
        await manager.__aexit__(None, None, None)


def test_the_table_of_join_tries_drops_old_addresses():
    """S15: the table of tries does not grow with no limit."""
    attempts = Attempts(max_tries=3, window_seconds=10.0)
    for index in range(rooms.PRUNE_AT):
        attempts.allow(f"10.0.{index // 250}.{index % 250}", now=0.0)
    assert len(attempts._hits) == rooms.PRUNE_AT
    attempts.allow("192.168.0.1", now=100.0)
    assert len(attempts._hits) == 1


# ------------------------------------------------------------------------ H1


async def test_the_host_answers_while_the_computer_plays():
    """H1: the agent runs in a worker thread, so a request gets its answer at once.

    The v7 agent of scenario 1 needs a measurable time for its set up. The line of
    sight answer arrives while the frames still say `computer_thinking`.
    """
    engine = build_engine("s01_guards_counterattack")
    agent_side = engine.new_game(1).active
    host, manager, port = await open_host(
        engine, agents={agent_side: make_agent("v7", engine, 1, agent_side)}, agent_delay=0.05
    )
    try:
        async with connect(url(port)) as socket:
            client = Client(socket)
            await client.join(host.room.code)
            first = await client.receive_until(protocol.HOST_FRAME)
            assert first["status"] == protocol.STATUS_COMPUTER
            await client.send({"type": "los_request", "from": "A1", "to": "A4"})
            seen_before = 0
            while True:
                message = await client.receive()
                if message["type"] == protocol.HOST_LOS_RESULT:
                    break
                if message["type"] == protocol.HOST_FRAME:
                    seen_before += 1
            assert host.game.state.active == agent_side and not host.game.state.game_over, (
                "the answer came while the computer still played"
            )
            after = await client.receive_until(protocol.HOST_FRAME)
            assert after["status"] == protocol.STATUS_COMPUTER, "a frame after each computer command"
    finally:
        await manager.__aexit__(None, None, None)


# ------------------------------------------------------------------------ H5


async def test_a_watcher_who_joins_after_the_end_gets_game_over():
    """H5: a late joiner gets `game_over` with the result, the conditions, and the losses."""
    engine = build_engine("s01_guards_counterattack")
    agents = {0: make_agent("v1", engine, 7, 0), 1: make_agent("v1", engine, 7, 1)}
    host, manager, port = await open_host(engine, seed=7, agents=agents)
    try:
        result = await host.play_alone()
        assert host.game.state.game_over and result == host.game.state.result
        async with connect(url(port), max_size=None) as socket:
            client = Client(socket)
            await client.join(host.room.code)
            frame = await client.receive_until(protocol.HOST_FRAME)
            assert frame["status"] == protocol.STATUS_GAME_OVER
            assert frame["log_tail"], "the late joiner gets the history"
            over = await client.receive_until(protocol.HOST_GAME_OVER)
            players = list(engine.scenario.players())
            expected = players.index(host.game.state.result) if host.game.state.result in players else None
            assert over["result"] == expected
            assert over["outcome"] == host.game.state.result
            assert over["turn"] == host.game.state.turn
            assert over["conditions"], "the conditions of the game end line"
            if expected is not None:
                assert over["winner_name"] == players[expected].title()
            total = sum(sum(side.values()) for side in over["casualties"].values())
            assert total > 0, "a game of scenario 1 has losses"
            assert "player 0" not in over["cause"] and "player 1" not in over["cause"]
    finally:
        await manager.__aexit__(None, None, None)
