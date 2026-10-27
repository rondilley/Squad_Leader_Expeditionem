"""The launcher of the packaged game: the consent, the menu, and the game command line.

The window runs on the dummy video driver, so no window opens on the desktop. No test starts
a game process.
"""

from __future__ import annotations

import os
import socket

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the launcher needs the `desktop` extra")

from slcli.main import build_parser  # noqa: E402
from slcollect import settings as player_settings  # noqa: E402
from slwindow import launcher  # noqa: E402


@pytest.fixture(autouse=True)
def player_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("SL_DATA_DIR", str(tmp_path / "player"))
    return tmp_path / "player"


def _parse(argv: list[str]):
    return build_parser().parse_args(argv)


def test_the_menu_has_the_library_with_the_first_mover_first():
    found = launcher.entries()
    assert [e.scenario for e in found][:2] == ["lib01_grain_office", "lib02_pump_house"]
    assert len(found) == 12
    assert found[0].sides == (("allied", "Russian"), ("axis", "German"))
    assert found[1].sides[0] == ("axis", "German")


def test_the_game_command_gives_the_computer_the_other_side(tmp_path):
    found = launcher.entries()
    choice = launcher.Choice(scenario=0, side=1, opponent="hard", view="window3d")
    argv = launcher.game_argv(choice, found, 77, tmp_path, base=[])
    args = _parse(argv)
    assert args.command == "window3d" and args.scenario == "lib01_grain_office"
    assert args.agent == "hard" and args.agent_side == "allied", "the person has the axis side"
    assert args.seed == 77 and args.save_dir == str(tmp_path)


def test_the_game_command_of_hot_seat_and_of_the_lan(tmp_path):
    found = launcher.entries()
    hot = _parse(launcher.game_argv(launcher.Choice(opponent="hotseat", view="window"), found, 5, tmp_path, base=[]))
    assert hot.command == "window" and hot.agent is None and not hot.lan
    host = _parse(launcher.game_argv(launcher.Choice(opponent="lan_host", host_code="ab12"), found, 5, tmp_path, base=[]))
    assert host.lan and host.lan_port == launcher.LAN_PORT and host.room_code == "ab12"
    join = _parse(launcher.game_argv(launcher.Choice(opponent="lan_join", address=" 10.0.0.7 ", room_code="cd34"), found, 5, tmp_path, base=[]))
    assert join.connect == f"ws://10.0.0.7:{launcher.LAN_PORT}/" and join.room_code == "cd34"


def test_the_first_start_asks_one_time_and_the_menu_keeps_the_choice(player_dir):
    window = launcher.Launcher()
    try:
        window.draw()
        assert "consent_yes" in window.rects and "play" not in window.rects, "the first start asks first"
        window.click(window.rects["consent_no"].center)
        assert player_settings.load_settings().consent is False
        window.draw()
        assert "play" in window.rects
        window.click(window.rects["scenario_next"].center)
        window.click(window.rects["side_1"].center)
        window.click(window.rects["opponent_hotseat"].center)
        window.click(window.rects["view_window"].center)
        assert (window.choice.scenario, window.choice.side, window.choice.opponent, window.choice.view) == (1, 1, "hotseat", "window")
        window.click(window.rects["send_toggle"].center)
        assert player_settings.load_settings().consent is True
        window.click(window.rects["opponent_lan_join"].center)
        window.draw()
        window.click(window.rects["address"].center)
        for char in "10.1.2.3":
            window.key(pygame.event.Event(pygame.KEYDOWN, key=0, unicode=char))
        assert window.choice.address == "10.1.2.3"
        window.play()
        assert window.game is None and "room code" in window.log[-1], "a join needs the address and the code"
    finally:
        pygame.quit()
    assert launcher.Launcher.__name__  # the module stays importable after quit


def test_a_lan_host_takes_a_connection_on_its_port():
    from slagents.registry import build_engine
    from slhost.server import Host
    from slwindow.embedded import start

    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    host = Host(build_engine("s01_guards_counterattack"), seed=1, hot_seat=False)
    embedded = start(host, "0.0.0.0", port)
    try:
        assert embedded.port == port
        with socket.create_connection(("127.0.0.1", port), timeout=5):
            pass
    finally:
        embedded.stop()
