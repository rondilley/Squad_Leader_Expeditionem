"""`sl-cli window`: the command a person types.

The window itself has its own tests. This file checks the wiring that gets there, and it
opens no window: a stand-in Window records what the command built and stops at once.
"""

from __future__ import annotations

import argparse
import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slcli import window_cmd  # noqa: E402
from slcli.window_cmd import WATCHABLE_DELAY, DesktopNotInstalled, add_parser  # noqa: E402


def parse(*words: str):
    parser = argparse.ArgumentParser()
    add_parser(parser.add_subparsers(dest="command"))
    return parser.parse_args(["window", *words])


class FakeWindow:
    """A window that opens nothing and stops at once. The test reads what it was given."""

    made: list["FakeWindow"] = []

    def __init__(self, client, size, caption):
        self.client = client
        self.size = size
        self.caption = caption
        self.ran = False
        FakeWindow.made.append(self)

    def run(self):
        self.ran = True


@pytest.fixture()
def fake_window(monkeypatch):
    FakeWindow.made = []
    monkeypatch.setattr(window_cmd, "load_window", lambda: FakeWindow)
    return FakeWindow


def test_the_command_takes_a_scenario_two_agents_and_a_window_size():
    args = parse("--scenario", "s04_armor_probe", "--agents", "v3,v3", "--width", "1200", "--height", "700")
    assert args.scenario == "s04_armor_probe"
    assert args.agents == "v3,v3"
    assert (args.width, args.height) == (1200, 700)
    assert args.connect is None and args.agent_delay is None


def test_one_name_is_not_two_sides(fake_window):
    with pytest.raises(ValueError) as exc:
        window_cmd.run(parse("--agents", "v3"))
    assert "two names" in str(exc.value)


@pytest.mark.slow
def test_the_command_starts_a_host_and_opens_a_window(fake_window, capsys):
    """With no address the command runs a host in the same process (PR of AR-06)."""
    assert window_cmd.run(parse("--scenario", "s04_armor_probe", "--agents", "v3,v3")) == 0
    window = fake_window.made[-1]
    assert window.ran, "the command did not run the window"
    assert window.client.url.startswith("ws://127.0.0.1:")
    assert window.client.room_code, "the window got no room code for the host it started"
    assert "Armor probe" in window.caption
    printed = capsys.readouterr().out
    assert "s04_armor_probe" in printed
    assert "tanker" in printed, "the command did not name the computer opponents"
    assert f"{WATCHABLE_DELAY}" in printed, "the command did not name the pace"


@pytest.mark.slow
def test_the_command_joins_a_host_that_already_operates(fake_window):
    """`--connect` is the LAN game: the window joins and starts no host of its own."""
    assert window_cmd.run(parse("--connect", "ws://127.0.0.1:9/", "--room-code", "abc")) == 0
    window = fake_window.made[-1]
    assert window.client.url == "ws://127.0.0.1:9/"
    assert window.client.room_code == "abc"
    assert window.ran


def test_the_error_for_a_missing_library_says_how_to_install_it():
    error = DesktopNotInstalled()
    assert "pygame-ce" in str(error) and "desktop" in str(error)
