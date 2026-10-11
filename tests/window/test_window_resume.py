"""The two windows save each game and go on with a saved game (`--resume`), and name the
computer opponent by difficulty (`--agent easy|normal|hard`)."""

from __future__ import annotations

import argparse

from slcli import window3d_cmd
from slcli.window_cmd import DIFFICULTY, agent_name, connect_or_start


def _args(*extra: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    window3d_cmd.add_parser(parser.add_subparsers())
    return parser.parse_args(["window3d", *extra])


def test_the_difficulty_names_are_agents():
    assert agent_name("easy") == DIFFICULTY["easy"] and agent_name("Hard ") == DIFFICULTY["hard"]
    assert agent_name("v3") == "v3"
    assert list(DIFFICULTY) == ["easy", "normal", "hard"]


def test_a_window_game_saves_and_resumes_with_the_same_hash(tmp_path):
    args = _args("--agents", "easy,v1", "--agent-delay", "0", "--save-dir", str(tmp_path), "--seed", "4")
    embedded, _, _, _ = connect_or_start(args)
    try:
        host = embedded.host
        assert [a.name for a in host.agents.values()] and host.game.save is not None
        for _ in range(40):
            assert host.step_once()
        path = host.game.save.path
        played = len(host.game.commands)
        final_hash = host.game.commands[-1]["hash"]
    finally:
        embedded.stop()
    resumed_args = _args("--resume", str(path), "--agent-delay", "0")
    embedded, _, _, _ = connect_or_start(resumed_args)
    try:
        host = embedded.host
        assert resumed_args.seed == 4 and resumed_args.agents == f"{DIFFICULTY['easy']},v1"
        assert len(host.game.commands) == played
        assert host.game.commands[-1]["hash"] == final_hash
    finally:
        embedded.stop()
