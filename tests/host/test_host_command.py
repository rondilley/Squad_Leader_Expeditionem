"""The command line of the host, in the part that starts a game between two computers.

The browser harness in `tests/browser/test_computer_vs_computer.py` plays the game. This
file checks the wiring that gets there, and it needs no browser.
"""

from __future__ import annotations

import asyncio

import pytest

from slcli.host_cmd import add_parser
from slcli.play import build_engine, make_agent
from slhost.server import Host

SCENARIO = "s01_guards_counterattack"


def parse(*words: str):
    import argparse

    parser = argparse.ArgumentParser()
    add_parser(parser.add_subparsers(dest="command"))
    return parser.parse_args(["host", *words])


def test_the_command_takes_two_agents_and_a_delay():
    args = parse("--agents", "v1,v2", "--agent-delay", "0.25")
    assert args.agents == "v1,v2"
    assert args.agent_delay == 0.25


def test_the_delay_is_not_set_by_default():
    """The command resolves it: a watched game gets a pace, and any other game gets none."""
    from slcli.host_cmd import WATCHABLE_DELAY

    assert parse().agent_delay is None
    assert parse().agents is None
    assert WATCHABLE_DELAY > 0


def test_a_watched_game_gets_a_pace_a_person_can_follow():
    """A game that plays itself with no pause gives a result and shows no game."""
    from slcli.host_cmd import WATCHABLE_DELAY, run

    args = parse("--agents", "v1,v2", "--port", "0")
    seen = {}

    def fake_run(self, address, port):
        seen["delay"] = self.agent_delay
        raise KeyboardInterrupt

    import slhost.server as server_module

    original = server_module.Host.run
    server_module.Host.run = fake_run
    try:
        run(args)
    finally:
        server_module.Host.run = original
    assert seen["delay"] == WATCHABLE_DELAY


def test_a_named_delay_wins_over_the_default():
    args = parse("--agents", "v1,v2", "--agent-delay", "0")
    assert args.agent_delay == 0.0


def test_one_name_is_not_two_sides():
    """A game between two computers needs a name for each seat."""
    from slcli.host_cmd import run

    args = parse("--agents", "v1")
    with pytest.raises(ValueError) as exc:
        run(args)
    assert "two names" in str(exc.value)


def test_a_host_with_one_agent_does_not_play_itself():
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=2, agents={1: make_agent("v1", engine, 2, 1)})
    assert host.self_playing is False
    assert host.run_agents() >= 0


def test_a_host_with_two_agents_plays_itself():
    engine = build_engine(SCENARIO)
    agents = {0: make_agent("v1", engine, 2, 0), 1: make_agent("v2", engine, 2, 1)}
    host = Host(engine, seed=2, agents=agents)
    assert host.self_playing is True
    assert host.run_agents() == 0, "a game that plays itself uses play_alone and not run_agents"


def test_one_step_moves_the_game_on():
    engine = build_engine(SCENARIO)
    agents = {0: make_agent("v1", engine, 2, 0), 1: make_agent("v1", engine, 2, 1)}
    host = Host(engine, seed=2, agents=agents)
    before = host.game.state.seq
    assert host.step_once() is True
    assert host.game.state.seq > before
    assert host.commands_played == 1


@pytest.mark.slow
def test_a_game_that_plays_itself_reaches_a_result():
    """The same game the browser harness watches, without the browser."""
    engine = build_engine(SCENARIO)
    agents = {0: make_agent("v1", engine, 7, 0), 1: make_agent("v2", engine, 7, 1)}
    host = Host(engine, seed=7, agents=agents)

    result = asyncio.run(host.play_alone())
    assert host.game.state.game_over
    assert result == host.game.state.result
    assert result in ("german", "russian", "draw", "no_result")
    assert host.commands_played > 100
    assert host.game.state.turn >= 2


@pytest.mark.slow
def test_the_command_cap_stops_a_game_that_does_not_end():
    """A harness must stop, so the loop has a cap and it reports what it reached."""
    engine = build_engine(SCENARIO)
    agents = {0: make_agent("v1", engine, 7, 0), 1: make_agent("v2", engine, 7, 1)}
    host = Host(engine, seed=7, agents=agents)
    result = asyncio.run(host.play_alone(limit=20))
    assert result == "no_result"
    assert host.commands_played == 20
    assert not host.game.state.game_over
