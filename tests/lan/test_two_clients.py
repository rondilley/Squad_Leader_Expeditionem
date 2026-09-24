"""Two clients on one host, one seat for each (TR-08, TC-12, TC-24, TC-27).

A LAN room gives seat 0 to the first client and seat 1 to the second, and each client acts
for its own side only. The tests here open two real WebSocket connections to a host on the
loopback address and play the set up of a scenario.

TC-12 measures the time from the intent of one client to the frame that reaches the other
client. TC-27 covers what the host refuses: a wrong room code, an origin the host did not
serve, a third client that wants a seat, and a flood of join tries.

How the tests read the two streams: the host sends one frame to each seat after each
command, and it sends the current frame again to each seat when a client joins. So a
client can hold a frame it has already read. Each client keeps the identities it has seen
and reads to the newest frame, which is the state the host holds.
"""

from __future__ import annotations

import asyncio
import json
import statistics
import time

import pytest
from websockets.asyncio.client import connect

from slcli.play import build_engine
from slhost import protocol
from slhost.rooms import Attempts
from slhost.server import Host

LATENCY_BUDGET_MS = 500.0
SETUP_LIMIT = 400
QUIET_SECONDS = 0.15


@pytest.fixture(scope="module")
def engine():
    return build_engine("s00_movement_drill")


class Client:
    """One LAN client. It holds one seat and speaks the host protocol."""

    def __init__(self, socket, name: str) -> None:
        self.socket = socket
        self.name = name
        self.player = -1
        self.seat = ""
        self.seen: set[str] = set()
        self.last: dict | None = None

    async def send(self, message: dict) -> None:
        await self.socket.send(protocol.dump(message))

    async def receive(self) -> dict:
        return json.loads(await self.socket.recv())

    async def receive_until(self, kind: str, limit: int = 8) -> dict:
        for _ in range(limit):
            message = await self.receive()
            if message["type"] == kind:
                return message
        raise AssertionError(f"no {kind} message arrived for {self.name}")

    async def join(self, code: str) -> dict:
        await self.send({"type": "join", "room_code": code, "display_name": self.name})
        welcome = await self.receive()
        if welcome["type"] == protocol.HOST_WELCOME:
            self.player = welcome["player"]
            self.seat = welcome["seat"]
        return welcome

    async def next_frame(self, timeout: float = 5.0) -> dict:
        """The next frame with an identity this client has not read."""

        async def read() -> dict:
            while True:
                message = await self.receive()
                if message["type"] != protocol.HOST_FRAME:
                    continue
                if message["frame_id"] in self.seen:
                    continue
                self.seen.add(message["frame_id"])
                self.last = message
                return message

        return await asyncio.wait_for(read(), timeout)

    async def newest_frame(self, timeout: float = 5.0) -> dict:
        """The newest frame this client can read, which is the state the host holds.

        A client that already read the newest frame keeps it, so two calls in sequence
        give the same frame and neither of them waits for a command that nobody sent.
        """
        if self.last is None:
            await self.next_frame(timeout)
        while True:
            try:
                await self.next_frame(QUIET_SECONDS)
            except asyncio.TimeoutError:
                assert self.last is not None
                return self.last

    async def act(self, frame: dict) -> None:
        """Send the first legal command of the frame."""
        await self.send(
            {
                "type": "intent",
                "frame_id": frame["frame_id"],
                "command_id": frame["legal_commands"][0]["id"],
            }
        )


async def open_host(engine, **kwargs):
    host = Host(engine, seed=1, hot_seat=False, **kwargs)
    manager = host.start("127.0.0.1", 0)
    server = await manager.__aenter__()
    return host, manager, Host.bound_port(server)


async def both_at_the_newest(first: Client, second: Client) -> dict:
    """Read the two streams to the same state and give that frame."""
    frame_a = await first.newest_frame()
    frame_b = await second.newest_frame()
    assert frame_a["frame_id"] == frame_b["frame_id"], "the two seats see the same state"
    return frame_a


async def test_two_clients_take_one_seat_each_and_play_a_turn(engine):
    """TR-08 and TC-24: the two clients play, and each one acts for its own side."""
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket_a, connect(f"ws://127.0.0.1:{port}") as socket_b:
            first, second = Client(socket_a, "first"), Client(socket_b, "second")
            await first.join(host.room.code)
            await second.join(host.room.code)
            assert {first.player, second.player} == {0, 1}, "one seat for each client"
            assert first.seat == "player" and second.seat == "player"
            by_player = {first.player: first, second.player: second}
            commands = 0
            while commands < SETUP_LIMIT:
                frame = await both_at_the_newest(first, second)
                if frame["phase"] != "setup":
                    break
                actor = by_player[frame["view"]["active"]]
                if not actor.last or not actor.last["legal_commands"]:
                    break
                await actor.act(actor.last)
                commands += 1
            assert commands > 0, "the clients placed their counters"
            assert host.game.state.phase != "setup", "the two sides completed set up"
            assert len(host.game.commands) == commands, "the host applied each intent one time"
            assert host.game.state.turn == 1, "the game reached the first player turn"
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_client_may_not_act_for_the_other_seat(engine):
    """SR-03: a client holds one seat, and the host refuses a command for the other."""
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket_a, connect(f"ws://127.0.0.1:{port}") as socket_b:
            first, second = Client(socket_a, "first"), Client(socket_b, "second")
            await first.join(host.room.code)
            await second.join(host.room.code)
            frame = await both_at_the_newest(first, second)
            active = frame["view"]["active"]
            actor = first if first.player == active else second
            idle = second if actor is first else first
            await idle.act(actor.last)
            error = await idle.receive_until(protocol.HOST_ERROR)
            assert error["rule_id"] == "SR-03"
            assert not host.game.commands, "the host applied no command"
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_third_client_gets_no_seat(engine):
    """SR-03: a LAN room has two seats, and a third connection watches."""
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as a, connect(f"ws://127.0.0.1:{port}") as b, connect(
            f"ws://127.0.0.1:{port}"
        ) as c:
            first, second, third = Client(a, "first"), Client(b, "second"), Client(c, "third")
            await first.join(host.room.code)
            await second.join(host.room.code)
            answer = await third.join(host.room.code)
            assert answer["type"] in (protocol.HOST_WELCOME, protocol.HOST_ERROR)
            if answer["type"] == protocol.HOST_WELCOME:
                assert answer["seat"] == "watcher", answer
                assert answer["player"] == -1
    finally:
        await manager.__aexit__(None, None, None)


async def test_the_time_from_one_client_to_the_other_is_inside_the_budget(engine):
    """TC-12 and NFR-07: the 95th percentile from an intent to the other client's frame."""
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket_a, connect(f"ws://127.0.0.1:{port}") as socket_b:
            first, second = Client(socket_a, "first"), Client(socket_b, "second")
            await first.join(host.room.code)
            await second.join(host.room.code)
            by_player = {first.player: first, second.player: second}
            samples: list[float] = []
            for _ in range(30):
                frame = await both_at_the_newest(first, second)
                if frame["phase"] != "setup":
                    break
                active = frame["view"]["active"]
                actor, watcher = by_player[active], by_player[1 - active]
                if not actor.last or not actor.last["legal_commands"]:
                    break
                started = time.perf_counter()
                await actor.act(actor.last)
                await watcher.next_frame()
                samples.append((time.perf_counter() - started) * 1000.0)
            assert len(samples) >= 10, f"the test needs a set of samples, and it took {len(samples)}"
            samples.sort()
            p95 = samples[int(len(samples) * 0.95) - 1]
            assert p95 < LATENCY_BUDGET_MS, f"the 95th percentile is {p95:.1f} ms, and the budget is {LATENCY_BUDGET_MS}"
            assert statistics.median(samples) < LATENCY_BUDGET_MS
    finally:
        await manager.__aexit__(None, None, None)


async def test_the_host_refuses_a_wrong_room_code_and_a_bad_origin(engine):
    """TC-27: two of the refusals, over a real connection."""
    host, manager, port = await open_host(engine)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            client = Client(socket, "wrong code")
            answer = await client.join("0" * 32)
            assert answer["type"] == protocol.HOST_ERROR
            assert answer["rule_id"] == "SR-03"
        with pytest.raises(Exception):
            async with connect(
                f"ws://127.0.0.1:{port}", additional_headers={"Origin": "http://not-this-host.example"}
            ) as socket:
                await Client(socket, "bad origin").join(host.room.code)
    finally:
        await manager.__aexit__(None, None, None)


def test_the_join_tries_of_one_address_are_limited():
    """TC-27: a wrong code cannot be searched from one address."""
    attempts = Attempts(max_tries=3, window_seconds=60.0)
    address = "10.0.0.5"
    assert [attempts.allow(address, now=i * 0.1) for i in range(3)] == [True, True, True]
    assert attempts.allow(address, now=0.4) is False
    assert attempts.allow("10.0.0.6", now=0.4) is True, "the limit is for one address"
    attempts.reset(address)
    assert attempts.allow(address, now=0.5) is True
