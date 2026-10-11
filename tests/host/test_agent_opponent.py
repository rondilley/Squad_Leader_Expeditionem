"""A human plays one side in the browser and a scripted agent plays the other (FR-39).

These tests use the host directly, with no browser, because the opponent is a host
concern. The browser suite covers the client.
"""

from __future__ import annotations

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


async def open_host(engine, agent_seat: int = 1):
    host = Host(engine, seed=1, agents={agent_seat: ScriptedV1(engine, agent_seat)})
    manager = host.start("127.0.0.1", 0)
    server = await manager.__aenter__()
    return host, manager, Host.bound_port(server)


async def receive_until(socket, kind: str, limit: int = 8) -> dict:
    for _ in range(limit):
        message = json.loads(await socket.recv())
        if message["type"] == kind:
            return message
    raise AssertionError(f"no {kind} message arrived")


async def test_the_computer_opponent_sets_up_before_the_person_sees_a_frame(engine):
    """The agent holds the side that sets up first, so its counters are on the board."""
    host, manager, port = await open_host(engine, agent_seat=1)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            await socket.send(protocol.dump({"type": "join", "room_code": host.room.code, "display_name": "person"}))
            await receive_until(socket, protocol.HOST_WELCOME)
            frame = await receive_until(socket, protocol.HOST_FRAME)
            assert frame["active"] == 0, "the person acts"
            assert frame["player"] == 0, "the view belongs to the person"
            german = [u for u in frame["view"]["units"] if u["player"] == 1]
            assert german and all(u["hex"] is not None for u in german), "the opponent placed its counters"
            assert host.game.commands, "the opponent's commands are in the log"
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_person_may_not_send_a_command_for_the_computer_side(engine):
    host, manager, port = await open_host(engine, agent_seat=1)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            await socket.send(protocol.dump({"type": "join", "room_code": host.room.code, "display_name": "person"}))
            await receive_until(socket, protocol.HOST_WELCOME)
            frame = await receive_until(socket, protocol.HOST_FRAME)
            # Drive the person's side until the opponent would act, then try to act for it.
            while host.game.state.active == 0 and not host.game.state.game_over:
                command = frame["legal_commands"][0]["id"]
                await socket.send(protocol.dump({"type": "intent", "frame_id": frame["frame_id"], "command_id": command}))
                frame = await receive_until(socket, protocol.HOST_FRAME)
                if host.game.state.active == 1:
                    break
            if host.game.state.active == 1:
                await socket.send(protocol.dump({"type": "intent", "frame_id": frame["frame_id"], "command_id": frame["legal_commands"][0]["id"]}))
                error = await receive_until(socket, protocol.HOST_ERROR)
                assert error["rule_id"] in ("FR-39", "DR-04")
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_game_against_the_computer_opponent_reaches_its_end(engine):
    """FR-39 and BC-01: the person plays one side and the game gives a result."""
    host, manager, port = await open_host(engine, agent_seat=1)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            await socket.send(protocol.dump({"type": "join", "room_code": host.room.code, "display_name": "person"}))
            await receive_until(socket, protocol.HOST_WELCOME)
            frame = await receive_until(socket, protocol.HOST_FRAME)
            steps = 0
            while not host.game.state.game_over and steps < 3000:
                commands = frame["legal_commands"]
                if not commands:
                    break
                ending = [c for c in commands if c["payload"]["action"] in ("end_phase", "end_setup")]
                chosen = (ending or commands)[0]["id"]
                await socket.send(protocol.dump({"type": "intent", "frame_id": frame["frame_id"], "command_id": chosen}))
                message = json.loads(await socket.recv())
                if message["type"] == protocol.HOST_FRAME:
                    frame = message
                elif message["type"] == protocol.HOST_ERROR:
                    raise AssertionError(f"the host refused a command: {message}")
                steps += 1
            assert host.game.state.game_over, f"the game did not end in {steps} commands"
            assert host.game.state.result
            assert any(c["player"] == 1 for c in host.game.commands), "the opponent played its side"
            assert any(c["player"] == 0 for c in host.game.commands), "the person played the other side"
    finally:
        await manager.__aexit__(None, None, None)


def test_the_host_names_the_human_seat(engine):
    host = Host(engine, seed=1, agents={1: ScriptedV1(engine, 1)})
    assert host.human_player() == 0
    plain = Host(engine, seed=1)
    assert plain.human_player() == plain.game.state.active


async def test_a_set_up_agent_places_the_persons_units_and_then_the_person_plays():
    """The person can give the set up of their own side to an agent. The first frame the
    person gets is after the Set Up Phase, with each of their units on a hex, and from that
    frame on the side is the person's."""
    engine = build_engine("s01_guards_counterattack")
    host = Host(
        engine,
        seed=4,
        agents={1: ScriptedV1(engine, 1)},
        setup_agents={0: ScriptedV1(engine, 0)},
    )
    manager = host.start("127.0.0.1", 0)
    server = await manager.__aenter__()
    port = Host.bound_port(server)
    try:
        async with connect(f"ws://127.0.0.1:{port}") as socket:
            await socket.send(protocol.dump({"type": "join", "room_code": host.room.code, "display_name": "person"}))
            await receive_until(socket, protocol.HOST_WELCOME)
            frame = await receive_until(socket, protocol.HOST_FRAME)
            assert frame["phase"] != "setup"
            assert frame["active"] == 0
            own = [u for u in frame["view"]["units"] if u["player"] == 0 and u.get("carrier") is None]
            assert own and all(u["hex"] is not None for u in own), "the set up agent placed each unit"
            placed_by_agent = [c for c in host.game.commands if c["player"] == 0 and c["phase"] == "setup"]
            assert placed_by_agent, "the agent's placements are in the command log"
            # After set up the side is the person's: the host waits for the person's intent.
            assert host.agent_now() is None
            command = frame["legal_commands"][0]["id"]
            await socket.send(protocol.dump({"type": "intent", "frame_id": frame["frame_id"], "command_id": command}))
            await receive_until(socket, protocol.HOST_FRAME)
            assert any(c["player"] == 0 and c["phase"] != "setup" and c["command_id"] == command for c in host.game.commands)
    finally:
        await manager.__aexit__(None, None, None)
