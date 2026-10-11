"""Save a game and resume it: the command log plays again and each hash agrees.

The games are real: a person's side is played by a v1 agent through the host's own apply,
and the computer opponent is the host's agent. No part is a stand-in.
"""

from __future__ import annotations

import argparse
import json

import pytest

from slagents.scripted.v1 import ScriptedV1
from slcli import window3d_cmd
from slcli.play import build_engine
from slhost import saves
from slhost.server import Host

SCENARIO = "s01_guards_counterattack"


def _played_host(seed: int, commands: int) -> Host:
    """A host where a person (driven by v1) played this many commands against v1."""
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=seed, agents={1: ScriptedV1(engine, 1)})
    person = ScriptedV1(engine, 0)
    host.run_agents()
    played = 0
    while played < commands and not host.game.state.game_over:
        frame = engine.legal_commands(host.game.state)
        host.game.apply(frame.frame_id, person.select(host.game.state, frame))
        host.run_agents()
        played += 1
    return host


def _document(host: Host, seed: int) -> dict:
    return saves.save_document(host, SCENARIO, None, seed, {1: "v1"})


def test_a_resumed_game_has_the_same_state_hash_and_log(tmp_path):
    host = _played_host(seed=7, commands=80)
    path = saves.write_save(tmp_path / "game.json", _document(host, 7))
    document = saves.read_save(path)
    engine = build_engine(SCENARIO)
    resumed = Host(engine, seed=7, agents={1: ScriptedV1(engine, 1)})
    played = saves.replay_into(resumed, document)
    assert played == len(host.game.commands)
    assert engine.hash_state(resumed.game.state) == host.engine.hash_state(host.game.state)
    assert [c["command_id"] for c in resumed.game.commands] == [c["command_id"] for c in host.game.commands]
    # The resumed game goes on: the next legal frame is the same frame.
    assert engine.legal_commands(resumed.game.state).frame_id == host.engine.legal_commands(host.game.state).frame_id


def test_a_save_with_a_hash_that_does_not_agree_stops_resume(tmp_path):
    host = _played_host(seed=7, commands=30)
    document = _document(host, 7)
    document["commands"][12]["hash"] = "0" * len(document["commands"][12]["hash"])
    engine = build_engine(SCENARIO)
    resumed = Host(engine, seed=7, agents={1: ScriptedV1(engine, 1)})
    with pytest.raises(saves.SaveError, match="command 13"):
        saves.replay_into(resumed, document)


def test_a_save_with_another_seed_is_refused_at_the_first_command_that_differs():
    host = _played_host(seed=7, commands=30)
    document = _document(host, 7)
    engine = build_engine(SCENARIO)
    other = Host(engine, seed=8, agents={1: ScriptedV1(engine, 1)})
    with pytest.raises(saves.SaveError):
        saves.replay_into(other, document)


def test_resume_needs_a_new_game():
    host = _played_host(seed=7, commands=5)
    with pytest.raises(saves.SaveError, match="new game"):
        saves.replay_into(host, _document(host, 7))


@pytest.mark.parametrize(
    "content,cause",
    [("not json", "not JSON"), (json.dumps({"format": "other"}), "format"), (json.dumps({"format": saves.SAVE_FORMAT}), "has no")],
)
def test_a_bad_save_file_gives_a_save_error(tmp_path, content, cause):
    path = tmp_path / "bad.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(saves.SaveError, match=cause):
        saves.read_save(path)
    with pytest.raises(saves.SaveError, match="cannot read"):
        saves.read_save(tmp_path / "missing.json")


def _args(*argv: str):
    parser = argparse.ArgumentParser()
    window3d_cmd.add_parser(parser.add_subparsers())
    return parser.parse_args(["window3d", *argv])


def test_the_window_command_resumes_from_a_save_file(tmp_path):
    host = _played_host(seed=11, commands=60)
    path = saves.write_save(tmp_path / "game.json", saves.save_document(host, SCENARIO, None, 11, {1: "v1"}))
    args = _args("--resume", str(path), "--seed", "999", "--scenario", "s02_tractor_works")
    engine, resumed, record = window3d_cmd.build_host(args)
    assert record == {"scenario": SCENARIO, "board": None, "seed": 11, "opponents": {1: "v1"}}
    assert engine.hash_state(resumed.game.state) == host.engine.hash_state(host.game.state)
    assert set(resumed.agents) == {1}
    assert window3d_cmd.save_path(args, record) == path


def test_the_window_command_builds_an_opponent_and_a_set_up_agent():
    args = _args("--agent", "v6", "--auto-setup")
    engine, host, record = window3d_cmd.build_host(args)
    assert record["opponents"] == {1: "v6"}
    assert set(host.agents) == {1}
    assert set(host.setup_agents) == {0}
    assert window3d_cmd.save_path(args, record).as_posix() == f"runs/saves/{SCENARIO}-seed1.json"


def test_the_difficulty_names_give_the_agents():
    for name, agent in (("easy", "v5"), ("normal", "v3"), ("hard", "v6")):
        engine, host, record = window3d_cmd.build_host(_args("--agent", name))
        assert record["opponents"] == {1: agent}
        assert f"v{host.agents[1].version.split('.')[0]}" == agent
