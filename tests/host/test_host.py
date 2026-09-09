"""The host protocol end to end over a real WebSocket, with no browser.

These tests cover the join credential (SR-03), the frame identity (DR-04), the
per-player view (AR-09), the line of sight answer (FR-34), and the error handling at
the trust boundary.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from websockets.asyncio.client import connect

from slcore import geometry
from slhost import protocol
from slhost.rooms import Attempts, Room, new_room_code, origin_allowed
from slhost.server import Host
from slcli.play import build_engine


@pytest.fixture(scope="module")
def engine():
    return build_engine("s00_movement_drill")


class Client:
    """A small test client that speaks the host protocol."""

    def __init__(self, socket):
        self.socket = socket

    async def send(self, message: dict) -> None:
        await self.socket.send(protocol.dump(message))

    async def receive(self) -> dict:
        return json.loads(await self.socket.recv())

    async def receive_until(self, kind: str, limit: int = 8) -> dict:
        for _ in range(limit):
            message = await self.receive()
            if message["type"] == kind:
                return message
        raise AssertionError(f"no {kind} message arrived")

    async def join(self, code: str, name: str = "tester") -> dict:
        await self.send({"type": "join", "room_code": code, "display_name": name})
        return await self.receive()


async def open_host(engine, **kwargs):
    host = Host(engine, seed=1, **kwargs)
    manager = host.start("127.0.0.1", 0)
    server = await manager.__aenter__()
    port = Host.bound_port(server)
    return host, manager, port


async def test_a_client_joins_with_the_room_code_and_gets_a_frame(engine):
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            client = Client(socket)
            welcome = await client.join(host.room.code)
            assert welcome["type"] == protocol.HOST_WELCOME
            assert welcome["seat"] == "hot_seat"
            assert welcome["board"]["name"] == engine.board.name
            assert len(welcome["board"]["hexes"]) == len(engine.board)
            assert welcome["scenario"]["id"] == "s00_movement_drill"
            frame = await client.receive_until(protocol.HOST_FRAME)
            assert frame["phase"] == "setup"
            assert frame["legal_commands"], "the client gets the legal list"
            assert frame["frame_id"] == host.engine.hash_state(host.game.state)
            assert frame["view"]["units"], "the view holds the counters"
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_wrong_room_code_is_refused(engine):
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            client = Client(socket)
            answer = await client.join("0" * 32)
            assert answer["type"] == protocol.HOST_ERROR
            assert answer["rule_id"] == "SR-03"
    finally:
        await manager.__aexit__(None, None, None)


async def test_an_intent_applies_a_command_and_the_frame_moves_on(engine):
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            client = Client(socket)
            await client.join(host.room.code)
            frame = await client.receive_until(protocol.HOST_FRAME)
            first = frame["legal_commands"][0]
            await client.send({"type": "intent", "frame_id": frame["frame_id"], "command_id": first["id"]})
            second = await client.receive_until(protocol.HOST_FRAME)
            assert second["frame_id"] != frame["frame_id"]
            assert host.game.commands[0]["payload"] == first["payload"]
            assert host.game.commands[0]["hash"] == second["frame_id"]
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_stale_frame_id_is_refused(engine):
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            client = Client(socket)
            await client.join(host.room.code)
            frame = await client.receive_until(protocol.HOST_FRAME)
            command = frame["legal_commands"][0]["id"]
            await client.send({"type": "intent", "frame_id": frame["frame_id"], "command_id": command})
            await client.receive_until(protocol.HOST_FRAME)
            await client.send({"type": "intent", "frame_id": frame["frame_id"], "command_id": command})
            error = await client.receive_until(protocol.HOST_ERROR)
            assert error["rule_id"] == "DR-04"
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_command_id_that_is_not_legal_is_refused(engine):
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            client = Client(socket)
            await client.join(host.room.code)
            frame = await client.receive_until(protocol.HOST_FRAME)
            await client.send({"type": "intent", "frame_id": frame["frame_id"], "command_id": "0" * 16})
            error = await client.receive_until(protocol.HOST_ERROR)
            assert error["type"] == protocol.HOST_ERROR
    finally:
        await manager.__aexit__(None, None, None)


async def test_the_host_answers_a_line_of_sight_question(engine):
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            client = Client(socket)
            await client.join(host.room.code)
            await client.receive_until(protocol.HOST_FRAME)
            await client.send({"type": "los_request", "from": "G1", "to": "G10"})
            answer = await client.receive_until(protocol.HOST_LOS_RESULT)
            assert answer["from"] == "G1" and answer["to"] == "G10"
            assert answer["result"]["clear"] is False
            assert answer["result"]["rule_id"] == "7.5", "a multi-story building stops the line of sight"
            assert answer["result"]["blocking_hex"] == "G6"
            await client.send({"type": "los_request", "from": "A1", "to": "A4"})
            answer = await client.receive_until(protocol.HOST_LOS_RESULT)
            assert answer["result"]["clear"] is True
    finally:
        await manager.__aexit__(None, None, None)


async def test_strict_mode_refuses_a_line_of_sight_question_outside_a_fire_phase(engine):
    host, manager, port = await open_host(engine, strict_los=True)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            client = Client(socket)
            await client.join(host.room.code)
            await client.receive_until(protocol.HOST_FRAME)
            await client.send({"type": "los_request", "from": "A1", "to": "A4"})
            error = await client.receive_until(protocol.HOST_ERROR)
            assert error["rule_id"] == "19.3"
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_message_that_is_not_valid_leaves_the_host_up(engine):
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            client = Client(socket)
            await socket.send("{not json")
            error = await client.receive()
            assert error["rule_id"] == "protocol"
            await socket.send(protocol.dump({"type": "nonsense"}))
            error = await client.receive()
            assert error["rule_id"] == "protocol"
            await socket.send(protocol.dump({"type": "intent"}))
            error = await client.receive()
            assert error["rule_id"] == "protocol"
            welcome = await client.join(host.room.code)
            assert welcome["type"] == protocol.HOST_WELCOME, "the host still works"
    finally:
        await manager.__aexit__(None, None, None)


async def test_the_client_files_are_served_when_they_are_built(engine, tmp_path: Path):
    (tmp_path / "index.html").write_text("<h1>client</h1>", encoding="utf-8")
    host, manager, port = await open_host(engine, client_root=tmp_path)
    try:
        import asyncio
        import urllib.request

        def fetch(path: str) -> tuple[int, bytes]:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}") as response:
                return response.status, response.read()

        status, body = await asyncio.to_thread(fetch, "/")
        assert status == 200 and b"client" in body
        status, _ = await asyncio.to_thread(fetch, "/anything")
        assert status == 200, "an unknown path gives the page, so the client routes it"
    finally:
        await manager.__aexit__(None, None, None)


def test_a_room_code_has_the_entropy_the_requirement_asks_for():
    code = new_room_code()
    assert len(code) == 32, "128 bits as hexadecimal"
    assert code != new_room_code()
    room = Room(code=code, hot_seat=False)
    assert room.take("a", "one") == (0, "player")
    assert room.take("b", "two") == (1, "player")
    assert room.take("c", "three")[0] == -1, "the room is full"
    assert room.controls("a", 0) and not room.controls("a", 1)
    room.release("a")
    assert room.open_seat() == 0


def test_hot_seat_gives_one_client_the_two_seats():
    room = Room(code=new_room_code(), hot_seat=True)
    player, seat = room.take("a", "owner")
    assert (player, seat) == (0, "hot_seat")
    assert room.controls("a", 0) and room.controls("a", 1)
    assert room.take("b", "second")[0] == -1


def test_join_tries_are_limited_for_each_address():
    attempts = Attempts(max_tries=3, window_seconds=100.0)
    assert attempts.allow("1.2.3.4", now=0.0)
    assert attempts.allow("1.2.3.4", now=1.0)
    assert attempts.allow("1.2.3.4", now=2.0)
    assert not attempts.allow("1.2.3.4", now=3.0)
    assert attempts.allow("5.6.7.8", now=3.0), "another address is not affected"
    assert attempts.allow("1.2.3.4", now=200.0), "the window ends"


def test_the_origin_check():
    assert origin_allowed(None, ()), "a tool has no origin, and the room code is its credential"
    assert origin_allowed("http://localhost:8731", ("http://localhost:8731",))
    assert not origin_allowed("http://evil.example", ("http://localhost:8731",))
    assert origin_allowed("http://127.0.0.1:8731", (), "127.0.0.1:8731"), "the page the host served"
    assert not origin_allowed("http://evil.example", (), "127.0.0.1:8731")
