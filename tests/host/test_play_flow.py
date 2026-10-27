"""The play flow of the host (slice 4 and slice 8), over real sockets with the real engine.

- Undo in hot seat and against the computer, back to the last die roll only.
- "Set up for me": the v7 agent places the side of the person.
- A frame with one legal command is applied for the person, and the log says so.
- Each legal entry has a label with unit names, the hexes it touches, and its odds.
- The save file, and the resume that checks each hash.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

import pytest
from websockets.asyncio.client import connect

from slcli.host_cmd import add_parser, build_host
from slcli.play import build_engine, make_agent
from slcore.rules import r25_concealment
from slhost import annotate, protocol, savegame
from slhost.server import Host

SCENARIO = "s01_guards_counterattack"


class Client:
    def __init__(self, socket) -> None:
        self.socket = socket
        self.frames: list[dict] = []
        self.last: dict | None = None

    async def send(self, message: dict) -> None:
        await self.socket.send(protocol.dump(message))

    async def receive(self, timeout: float = 60.0) -> dict:
        message = json.loads(await asyncio.wait_for(self.socket.recv(), timeout))
        if message["type"] == protocol.HOST_FRAME:
            self.frames.append(message)
            self.last = message
        return message

    async def until(self, kind: str) -> dict:
        for _ in range(20000):
            message = await self.receive()
            if message["type"] == kind:
                return message
        raise AssertionError(f"no {kind}")

    async def my_turn(self) -> dict:
        """The next frame where this client acts, or the end of the game."""
        for _ in range(20000):
            message = await self.receive()
            if message["type"] == protocol.HOST_ERROR:
                raise AssertionError(f"the host sent an error: {message}")
            if message["type"] == protocol.HOST_FRAME and message["status"] in (
                protocol.STATUS_YOUR_TURN,
                protocol.STATUS_GAME_OVER,
            ):
                return message
        raise AssertionError("no turn")

    async def drain(self, quiet: float = 0.3) -> None:
        while True:
            try:
                await self.receive(quiet)
            except asyncio.TimeoutError:
                return

    async def act(self, frame: dict, command: dict) -> None:
        await self.send({"type": "intent", "frame_id": frame["frame_id"], "command_id": command["id"]})


async def open_host(engine, **kwargs):
    host = Host(engine, seed=kwargs.pop("seed", 1), **kwargs)
    manager = host.start("127.0.0.1", 0)
    started = await manager.__aenter__()
    return host, manager, Host.bound_port(started)


async def joined(port: int, code: str) -> tuple[object, Client]:
    socket = await connect(f"ws://127.0.0.1:{port}", max_size=None)
    client = Client(socket)
    await client.send({"type": "join", "room_code": code, "display_name": "person"})
    await client.until(protocol.HOST_WELCOME)
    return socket, client


# ----------------------------------------------------------------------- undo


async def test_undo_takes_back_a_quiet_command_and_checks_the_replay():
    engine = build_engine("s00_movement_drill")
    host, manager, port = await open_host(engine)
    try:
        socket, client = await joined(port, host.room.code)
        async with socket:
            frame = await client.until(protocol.HOST_FRAME)
            assert frame["can_undo"] is False
            await client.send({"type": "undo"})
            error = await client.until(protocol.HOST_ERROR)
            assert error["code"] == protocol.CODE_UNDO_REFUSED, "nothing to take back at the start"
            start_hash = engine.hash_state(host.game.state)
            place = next(c for c in frame["legal_commands"] if c["action"] == "place")
            await client.act(frame, place)
            after = await client.until(protocol.HOST_FRAME)
            assert host.game.commands[-1]["quiet"] is True
            assert after["can_undo"] is True
            await client.send({"type": "undo"})
            back = await client.until(protocol.HOST_FRAME)
            assert engine.hash_state(host.game.state) == start_hash
            assert not host.game.commands
            assert back["frame_id"] != frame["frame_id"], "a new token after the undo"
            assert any(line["kind"] == "undo" for line in back["log_tail"])
            await client.act(back, place)
            await client.until(protocol.HOST_FRAME)
            assert host.game.commands[0]["payload"] == place["payload"], "the game goes on after the undo"
    finally:
        await manager.__aexit__(None, None, None)


async def test_undo_is_refused_after_a_die_roll_and_in_a_lan_room():
    engine = build_engine(SCENARIO)
    host, manager, port = await open_host(engine, odds=False)
    try:
        socket, client = await joined(port, host.room.code)
        async with socket:
            frame = await client.until(protocol.HOST_FRAME)
            # Set up for both sides with the helper, then end phases until a die rolls.
            for _ in range(2):
                await client.send({"type": "auto_setup"})
                await client.drain()
            frame = client.last
            assert frame is not None and frame["phase"] != "setup"
            for _ in range(400):
                record = host.game.commands[-1]
                if record["source"] == "human" and not record["quiet"]:
                    break
                assert frame["status"] == protocol.STATUS_YOUR_TURN, "the game ended before a die rolled"
                commands = frame["legal_commands"]
                rolls = [c for c in commands if c["action"] in ("group_fire", "rally", "cc_attack")]
                shots = [c for c in commands if c["action"] == "group_add"]
                ending = [c for c in commands if c["action"] == "end_phase"]
                await client.act(frame, (rolls or shots or ending or commands)[0])
                frame = await client.my_turn()
            else:
                raise AssertionError("no command rolled a die")
            await client.send({"type": "undo"})
            error = await client.until(protocol.HOST_ERROR)
            assert error["code"] == protocol.CODE_UNDO_REFUSED
    finally:
        await manager.__aexit__(None, None, None)
    lan, manager, port = await open_host(build_engine("s00_movement_drill"), hot_seat=False)
    try:
        socket, client = await joined(port, lan.room.code)
        async with socket:
            await client.until(protocol.HOST_FRAME)
            await client.send({"type": "undo"})
            error = await client.until(protocol.HOST_ERROR)
            assert error["code"] == protocol.CODE_UNDO_REFUSED
    finally:
        await manager.__aexit__(None, None, None)


# ------------------------------------------------------------- set up for me


async def test_set_up_for_me_places_the_side_of_the_person():
    engine = build_engine(SCENARIO)
    person = 1 - engine.new_game(1).active
    computer = 1 - person
    host, manager, port = await open_host(engine, agents={computer: make_agent("v1", engine, 1, computer)})
    try:
        socket, client = await joined(port, host.room.code)
        async with socket:
            frame = await client.my_turn()
            assert frame["phase"] == "setup" and frame["active"] == person
            await client.send({"type": "auto_setup"})
            # A frame goes out after each placement, and the log line comes at the end.
            frame = await client.my_turn()
            while not any(line["kind"] == "setup_helper" for f in client.frames for line in f["log_tail"]):
                frame = await client.my_turn()
            if frame["status"] != protocol.STATUS_YOUR_TURN:
                frame = await client.my_turn()
            placed = [c for c in host.game.commands if c["source"] == "setup_helper"]
            assert placed and all(c["player"] == person for c in placed)
            assert all(u["hex"] is not None or u["carrier"] is not None for u in frame["view"]["units"] if u["player"] == person)
            assert frame["phase"] != "setup" or frame["active"] != person
            assert any(line["kind"] == "setup_helper" for f in client.frames for line in f["log_tail"])
    finally:
        await manager.__aexit__(None, None, None)


# ------------------------------------------------------------ forced commands


async def test_a_forced_command_is_applied_for_the_person_and_logged():
    engine = build_engine(SCENARIO)
    host, manager, port = await open_host(engine, odds=False)
    try:
        socket, client = await joined(port, host.room.code)
        async with socket:
            await client.until(protocol.HOST_FRAME)
            for _ in range(2):
                await client.send({"type": "auto_setup"})
                await client.drain()
            frame = client.last
            labels: list[str] = []
            for _ in range(300):
                if frame["status"] == protocol.STATUS_GAME_OVER:
                    break
                only_end = [c["action"] for c in frame["legal_commands"]] == ["end_setup"]
                assert len(frame["legal_commands"]) != 1 or only_end, "a frame with one command never reaches the person"
                labels.extend(frame["auto_applied"])
                if labels and host.game.state.turn > 1:
                    break
                commands = frame["legal_commands"]
                ending = [c for c in commands if c["action"] == "end_phase"]
                await client.act(frame, (ending or commands)[0])
                frame = await client.my_turn()
            forced = [c for c in host.game.commands if c["source"] == "forced"]
            assert forced, "the game had a frame with one command"
            assert labels, "the person was told which commands the host applied"
            assert any(line["kind"] == "forced_command" for line in host.game.log)
    finally:
        await manager.__aexit__(None, None, None)
    off = Host(engine, seed=1, auto_forced=False)
    assert off._apply_forced() == 0


# ------------------------------------------------------ names, labels, odds


def _to_fire_phase(seed: int = 3):
    """A game of scenario 1 at a frame with a fire command, played by the v7 agents."""
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=seed, auto_forced=False)
    agents = (make_agent("v7", engine, seed, 0), make_agent("v7", engine, seed, 1))
    for _ in range(3000):
        state = host.game.state
        frame = engine.legal_commands(state)
        if any(lc.command.action == "group_add" for lc in frame.commands):
            return engine, host, frame
        host.game.apply(frame.frame_id, agents[frame.player].select(state, frame))
    raise AssertionError("no fire frame")


def test_each_legal_entry_has_a_label_its_hexes_and_its_odds():
    engine, host, frame = _to_fire_phase()
    state = host.game.state
    entries = annotate.legal_entries(engine, state, frame, host.game.names, frame.player, True)
    fire = [e for e in entries if e["action"] == "group_add"]
    assert fire
    for entry in fire:
        assert entry["hexes"] == [entry["payload"]["hex"]]
        assert "#" in entry["label"] or entry["units"][0]["name"] in entry["label"]
        assert "(" in entry["units"][0]["name"], "the name has the hex"
        odds = entry.get("odds")
        assert odds is not None and odds["kind"] == "fire" and odds["of"] == 1296
        for key in ("result", "kia", "break"):
            assert isinstance(odds[key], int) and 0 <= odds[key] <= 1296
        assert odds["kia"] <= odds["result"]
        assert annotate.odds_text(odds).startswith("result ")
    end = next(e for e in entries if e["action"] == "end_phase")
    assert end["label"] == "end the phase" and end["hexes"] == [] and "odds" not in end
    plain = annotate.legal_entries(engine, state, frame, host.game.names, frame.player, False)
    assert all("odds" not in e for e in plain), "the host option turns the odds off"


def test_a_shot_at_a_concealed_hex_has_no_odds():
    """SR-09: the odds of a shot would name the units below the counter."""
    engine, host, frame = _to_fire_phase()
    shot = next(lc for lc in frame.commands if lc.command.action == "group_add")
    target = shot.command.hex
    enemy = 1 - frame.player
    concealed, _ = r25_concealment.add(host.game.state, enemy, target)
    calculator = annotate.FrameOdds(engine, concealed, frame.player)
    assert calculator.for_command(shot) is None
    open_view = annotate.FrameOdds(engine, host.game.state, frame.player)
    assert open_view.for_command(shot) is not None


def test_a_unit_name_is_the_type_a_number_and_the_hex():
    engine = build_engine(SCENARIO)
    state = engine.new_game(1)
    names = annotate.Names()
    squads = [u for u in state.player_units(0) if u.type_key.endswith("4-4-7")]
    assert names.base(state, squads[0].id) == "4-4-7 #1"
    assert names.base(state, squads[2].id) == "4-4-7 #3"
    leader = next(u for u in state.player_units(0) if u.kind == "leader")
    assert leader.name in names.base(state, leader.id)
    placed = state.with_unit(squads[2].with_(hex=(3, 3)))
    assert names.full(placed, squads[2].id) == "4-4-7 #3 (D3)"
    assert annotate.with_side_names("player 1 has no unit left", {0: "Russian", 1: "German"}) == "German has no unit left"


# ------------------------------------------------------------ save and resume


def _parse(*words: str):
    parser = argparse.ArgumentParser()
    add_parser(parser.add_subparsers(dest="command"))
    return parser.parse_args(["host", *words])


async def test_a_saved_game_resumes_with_each_hash_checked(tmp_path: Path):
    engine = build_engine("s00_movement_drill")
    host, manager, port = await open_host(engine, seed=5, save_dir=tmp_path, save_header={"board": None})
    try:
        socket, client = await joined(port, host.room.code)
        async with socket:
            frame = await client.until(protocol.HOST_FRAME)
            for _ in range(12):
                if not frame["legal_commands"]:
                    break
                await client.act(frame, frame["legal_commands"][0])
                frame = await client.my_turn()
    finally:
        await manager.__aexit__(None, None, None)
    path = host.game.save.path
    header, lines = savegame.load(path)
    assert header["seed"] == 5 and header["scenario"] == "s00_movement_drill"
    assert len(lines) == len(host.game.commands) >= 12
    again = Host(build_engine("s00_movement_drill"), seed=5)
    assert again.resume_from(path) == len(lines)
    assert again.engine.hash_state(again.game.state) == engine.hash_state(host.game.state)
    resumed = build_host(_parse("--resume", str(path), "--port", "0"))
    assert resumed.engine.hash_state(resumed.game.state) == engine.hash_state(host.game.state)
    assert resumed.game.save is not None and resumed.game.save.path == path, "the game goes on in the same file"

    rows = path.read_text(encoding="utf-8").splitlines()
    broken = json.loads(rows[3])
    broken["hash"] = "0" * 64
    rows[3] = json.dumps(broken)
    bad = tmp_path / "bad.jsonl"
    bad.write_text("\n".join(rows) + "\n", encoding="utf-8")
    with pytest.raises(savegame.SaveFileError):
        Host(build_engine("s00_movement_drill"), seed=5).resume_from(bad)
    with pytest.raises(savegame.SaveFileError):
        savegame.load(tmp_path / "missing.jsonl")


async def test_an_undo_writes_the_save_file_again(tmp_path: Path):
    engine = build_engine("s00_movement_drill")
    host, manager, port = await open_host(engine, save_dir=tmp_path)
    try:
        socket, client = await joined(port, host.room.code)
        async with socket:
            frame = await client.until(protocol.HOST_FRAME)
            for _ in range(3):
                await client.act(frame, frame["legal_commands"][0])
                frame = await client.my_turn()
            await client.send({"type": "undo"})
            await client.until(protocol.HOST_FRAME)
            _, lines = savegame.load(host.game.save.path)
            assert len(lines) == len(host.game.commands) == 2
    finally:
        await manager.__aexit__(None, None, None)
