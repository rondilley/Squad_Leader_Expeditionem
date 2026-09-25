"""A human plays one side in the browser and a scripted agent plays the other (FR-39).

These tests use the host directly, with no browser, because the opponent is a host
concern. The browser suite covers the client.

The computer plays in a worker thread (H1), so the person gets a frame after each
computer command with the status `computer_thinking`, and a frame with `your_turn` when
the person acts again.
"""

from __future__ import annotations

import asyncio
import json

import pytest
from websockets.asyncio.client import connect

from slagents.scripted.v1 import ScriptedV1
from slcli.play import build_engine
from slhost import protocol
from slhost.server import Host


@pytest.fixture(scope="module")
def engine():
    return build_engine("s00_movement_drill")


async def open_host(engine, agent_seat: int = 1, **kwargs):
    host = Host(engine, seed=1, agents={agent_seat: ScriptedV1(engine, agent_seat)}, **kwargs)
    manager = host.start("127.0.0.1", 0)
    server = await manager.__aenter__()
    return host, manager, Host.bound_port(server)


async def receive_until(socket, kind: str, limit: int = 400) -> dict:
    for _ in range(limit):
        message = json.loads(await asyncio.wait_for(socket.recv(), 30))
        if message["type"] == kind:
            return message
    raise AssertionError(f"no {kind} message arrived")


async def my_turn(socket, seen: list[str] | None = None) -> dict:
    """Read frames until the person acts. Each status goes into `seen`."""
    for _ in range(5000):
        message = json.loads(await asyncio.wait_for(socket.recv(), 30))
        if message["type"] == protocol.HOST_ERROR:
            raise AssertionError(f"the host sent an error: {message}")
        if message["type"] != protocol.HOST_FRAME:
            continue
        if seen is not None:
            seen.append(message["status"])
        if message["status"] in (protocol.STATUS_YOUR_TURN, protocol.STATUS_GAME_OVER):
            return message
    raise AssertionError("the person never got a turn")


async def join(socket, host) -> dict:
    await socket.send(protocol.dump({"type": "join", "room_code": host.room.code, "display_name": "person"}))
    return await receive_until(socket, protocol.HOST_WELCOME)


async def test_the_computer_opponent_sets_up_before_the_person_acts(engine):
    """The agent holds the side that sets up first, so its counters are on the board."""
    host, manager, port = await open_host(engine, agent_seat=1)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            welcome = await join(socket, host)
            assert welcome["sides"]["1"]["controller"] == "computer"
            assert welcome["sides"]["0"]["controller"] == "human"
            statuses: list[str] = []
            frame = await my_turn(socket, statuses)
            assert frame["active"] == 0, "the person acts"
            assert frame["player"] == 0, "the view belongs to the person"
            assert protocol.STATUS_COMPUTER in statuses, "the person saw the computer turn go by"
            german = [u for u in frame["view"]["units"] if u["player"] == 1]
            assert german and all(u["hex"] is not None for u in german), "the opponent placed its counters"
            assert host.game.commands, "the opponent's commands are in the log"
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_computer_frame_has_no_legal_list(engine):
    """AR-09: the legal list of the computer side does not go to the person."""
    host, manager, port = await open_host(engine, agent_seat=1)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            await join(socket, host)
            for _ in range(200):
                message = json.loads(await asyncio.wait_for(socket.recv(), 30))
                if message["type"] != protocol.HOST_FRAME:
                    continue
                if message["status"] == protocol.STATUS_COMPUTER:
                    assert message["legal_commands"] == []
                if message["status"] == protocol.STATUS_YOUR_TURN:
                    assert message["legal_commands"]
                    break
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_person_may_not_send_a_command_for_the_computer_side(engine):
    """FR-39: while the computer plays, an intent of the person is refused with code seat."""
    host, manager, port = await open_host(engine, agent_seat=1, agent_delay=0.3)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            await join(socket, host)
            for _ in range(200):
                message = json.loads(await asyncio.wait_for(socket.recv(), 30))
                if message["type"] == protocol.HOST_FRAME and message["status"] == protocol.STATUS_COMPUTER:
                    break
            else:
                raise AssertionError("no computer turn")
            await socket.send(
                protocol.dump({"type": "intent", "frame_id": message["frame_id"], "command_id": "0" * 16})
            )
            error = await receive_until(socket, protocol.HOST_ERROR)
            assert error["rule_id"] == "FR-39"
            assert error["code"] == protocol.CODE_SEAT
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_game_against_the_computer_opponent_reaches_its_end(engine):
    """FR-39, BC-01, and H5: the person plays one side, and the game gives a result."""
    host, manager, port = await open_host(engine, agent_seat=1)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            await join(socket, host)
            frame = await my_turn(socket)
            steps = 0
            over = None
            while steps < 3000:
                if frame["status"] == protocol.STATUS_GAME_OVER:
                    break
                commands = frame["legal_commands"]
                ending = [c for c in commands if c["payload"]["action"] in ("end_phase", "end_setup")]
                chosen = (ending or commands)[0]["id"]
                await socket.send(protocol.dump({"type": "intent", "frame_id": frame["frame_id"], "command_id": chosen}))
                frame = await my_turn(socket)
                steps += 1
            over = await receive_until(socket, protocol.HOST_GAME_OVER)
            assert host.game.state.game_over, f"the game did not end in {steps} commands"
            assert host.game.state.result
            assert over["outcome"] == host.game.state.result
            assert over["turn"] == host.game.state.turn
            assert set(over["casualties"]) == {"0", "1"}
            assert set(over["casualties"]["0"]) == {"squads", "leaders", "vehicles"}
            assert isinstance(over["conditions"], list)
            assert any(c["player"] == 1 for c in host.game.commands), "the opponent played its side"
            assert any(c["player"] == 0 for c in host.game.commands), "the person played the other side"
    finally:
        await manager.__aexit__(None, None, None)


def test_the_host_names_the_human_seat(engine):
    host = Host(engine, seed=1, agents={1: ScriptedV1(engine, 1)})
    assert host.human_player() == 0
    plain = Host(engine, seed=1)
    assert plain.human_player() == plain.game.state.active
