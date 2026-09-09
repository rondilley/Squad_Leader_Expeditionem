"""TC-38: a shuffled legal list changes nothing, because the log holds payloads and IDs."""

import random

from slagents.base import RandomAgent
from slcore.commands import Command
from slcore.frame import DecisionFrame
from slcli.play import build_engine, play_game


def shuffled(frame: DecisionFrame, rng: random.Random) -> DecisionFrame:
    commands = list(frame.commands)
    rng.shuffle(commands)
    return DecisionFrame(frame.frame_id, frame.player, frame.phase, frame.sub_step, frame.turn, tuple(commands))


def test_replay_after_a_shuffle_of_each_frame():
    engine = build_engine("s00_movement_drill")
    for seed in range(1, 8):
        record = play_game(engine, seed, (RandomAgent(seed, 0), RandomAgent(seed, 1)))
        rng = random.Random(seed)
        state = engine.new_game(seed)
        hashes = []
        for logged in record.commands:
            frame = shuffled(engine.legal_commands(state), rng)
            assert frame.frame_id == logged["frame_id"]
            legal = frame.by_id(logged["command_id"])
            assert legal is not None, "the ID finds the command whatever the list sequence"
            assert legal.payload == logged["payload"]
            state, _ = engine.apply(state, legal.command)
            hashes.append(engine.hash_state(state))
        assert hashes == record.hashes


def test_id_is_a_function_of_the_payload_only():
    a = Command.from_payload({"action": "move", "units": [3], "hex": "B2"})
    b = Command.from_payload({"hex": "B2", "action": "move", "units": [3]})
    assert a.id == b.id
