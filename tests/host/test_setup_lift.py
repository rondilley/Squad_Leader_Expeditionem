"""The setup pick up (`setup_lift`): a person takes a placed unit off the board again.

Rule 21.2 lets a side arrange its counters until it declares the set up complete. The host
plays the game again through the core without the place command of the unit, so the hash
of each command that stays is checked and the save file holds only legal commands.
"""

from __future__ import annotations

import pytest

from slcli.play import build_engine
from slcore import geometry
from slhost import protocol
from slhost.protocol import ProtocolError
from slhost.server import Host

from tests.host.test_play_flow import joined, open_host

SCENARIO = "lib01_grain_office"


def _place(game, unit_id: int, nth_hex: int = 0) -> str:
    """Place one unit through the legal list of the core, on the nth hex it offers."""
    frame = game.engine.legal_commands(game.state)
    options = [c for c in frame.commands if c.command.action == "place" and c.command.units[0] == unit_id]
    chosen = options[nth_hex]
    game.apply(frame.frame_id, chosen.id)
    return chosen.payload["hex"]


def _give(game, weapon_id: int) -> int:
    frame = game.engine.legal_commands(game.state)
    chosen = next(c for c in frame.commands if c.command.action == "place_weapon" and c.command.weapon == weapon_id)
    game.apply(frame.frame_id, chosen.id)
    return chosen.command.units[0]


def _end_setup(game) -> None:
    frame = game.engine.legal_commands(game.state)
    chosen = next(c for c in frame.commands if c.command.action == "end_setup")
    game.apply(frame.frame_id, chosen.id)


def _placed(game, unit_id: int) -> bool:
    return game.state.units[unit_id].hex is not None


def _axis_placed(game) -> None:
    """Place the five axis counters of the scenario, then end their set up."""
    for step in range(5):
        frame = game.engine.legal_commands(game.state)
        place = [c for c in frame.commands if c.command.action == "place"]
        game.apply(frame.frame_id, place[step * 7 % len(place)].id)
    _end_setup(game)


def test_a_lifted_unit_leaves_the_board_and_the_others_stay():
    game = Host(build_engine(SCENARIO), seed=1).game
    _place(game, 13, 0)
    leader_hex = game.state.units[13].hex
    _place(game, 14, 1)
    _place(game, 10, 2)
    assert game.lift(13, 1) == 1
    assert not _placed(game, 13)
    assert _placed(game, 14) and _placed(game, 10)
    assert len(game.commands) == 2
    # Each command that stayed is in the record with its own hash, so a replay agrees.
    assert game.engine.hash_state(game.replay_to(len(game.commands))) == game.engine.hash_state(game.state)
    # The unit can go back, to the same hex or to another.
    frame = game.engine.legal_commands(game.state)
    assert any(c.command.action == "place" and c.command.units[0] == 13 and c.command.hex == leader_hex for c in frame.commands)


def test_an_identical_counter_keeps_its_hex_when_the_lower_one_is_lifted():
    # PR-06 offers the lowest ID of each type, so the core offers ID 11 only after ID 10 is
    # on the board. The pick up of ID 10 must not take the second 4-6-7 off too.
    game = Host(build_engine(SCENARIO), seed=1).game
    _place(game, 10, 0)
    second_hex = _place(game, 11, 3)
    assert game.lift(10, 1) == 1
    on_board = [u for u in game.state.units if u.player == 1 and u.hex is not None]
    assert len(on_board) == 1, "one 4-6-7 stays on the board"
    assert on_board[0].type_key == "german:4-6-7"
    assert geometry.hex_id(*on_board[0].hex) == second_hex


def test_a_weapon_given_to_a_lifted_unit_comes_off_too():
    game = Host(build_engine(SCENARIO), seed=1).game
    _axis_placed(game)
    assert game.state.active == 0
    allied = [u for u in game.state.units if u.player == 0]
    leader = next(u for u in allied if u.type_key.endswith("10-3"))
    squad = next(u for u in allied if u.type_key.endswith("4-4-7"))
    weapon = next(u for u in allied if u.type_key.endswith("LMG"))
    _place(game, leader.id, 0)
    _place(game, squad.id, 4)
    carrier = _give(game, weapon.id)
    assert game.state.units[weapon.id].carrier == carrier
    left_out = game.lift(carrier, 0)
    assert left_out == 2, "the place of the carrier and the gift of the weapon"
    assert not _placed(game, carrier)
    assert game.state.units[weapon.id].hex is None and game.state.units[weapon.id].carrier is None
    other = leader.id if carrier == squad.id else squad.id
    assert _placed(game, other)


def test_only_a_unit_of_the_current_block_can_be_lifted():
    game = Host(build_engine(SCENARIO), seed=1).game
    _axis_placed(game)
    axis_unit = next(u.id for u in game.state.units if u.player == 1)
    with pytest.raises(ProtocolError):
        game.lift(axis_unit, 0)
    with pytest.raises(ProtocolError):
        game.lift(next(u.id for u in game.state.units if u.player == 0), 0)


async def test_the_setup_lift_message_sends_a_new_frame_and_refuses_a_bad_unit():
    engine = build_engine(SCENARIO)
    host, manager, port = await open_host(engine)
    try:
        socket, client = await joined(port, host.room.code)
        async with socket:
            frame = await client.until(protocol.HOST_FRAME)
            place = next(c for c in frame["legal_commands"] if c["action"] == "place")
            unit = place["payload"]["units"][0]
            await client.act(frame, place)
            await client.until(protocol.HOST_FRAME)
            await client.send({"type": "setup_lift", "unit": unit})
            after = await client.until(protocol.HOST_FRAME)
            assert not host.game.commands
            assert any(line["kind"] == "setup_lift" for line in after["log_tail"])
            assert any(c["action"] == "place" and c["payload"]["units"][0] == unit for c in after["legal_commands"])
            await client.send({"type": "setup_lift", "unit": "ten"})
            error = await client.until(protocol.HOST_ERROR)
            assert error["code"] == protocol.CODE_PROTOCOL
            await client.send({"type": "setup_lift", "unit": unit})
            error = await client.until(protocol.HOST_ERROR)
            assert error["code"] == protocol.CODE_ILLEGAL, "the unit is not on the board"
    finally:
        await manager.__aexit__(None, None, None)
