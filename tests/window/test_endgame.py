"""The end of a game and the turn count (`slwindow.endgame`), and the end box of the windows.

The owner read "game over: Axis wins" at the end of a game of `lib01_grain_office` and
did not see at once that it was a loss. The end now says "You won." or "You lost." for
the side of the person, with the names of the card, and the panel says how many turns
are left.
"""

from __future__ import annotations

import dataclasses
import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slcli.play import build_engine  # noqa: E402
from slhost import annotate  # noqa: E402
from slhost.server import Host  # noqa: E402
from slwindow import endgame, panel  # noqa: E402
from slwindow.app import Window  # noqa: E402
from slwindow.client import GameView, HostClient  # noqa: E402
from slwindow.embedded import start  # noqa: E402

from tests.window.test_window_play_v2 import key, step_with, wait_for  # noqa: E402

CONDITION = {
    "kind": "hex_control",
    "side": "allied",
    "count": 0,
    "threshold": 1,
    "satisfied": False,
    "detail": "controls 0 of 5 hexes, and needs 1 (PR-16)",
}


def _view(controllers: tuple[str, str], result: int | None = 1, turn: int = 6) -> GameView:
    return GameView(
        scenario={"players": ["allied", "axis"], "turns": 5},
        sides={"0": {"name": "Russian", "controller": controllers[0]}, "1": {"name": "German", "controller": controllers[1]}},
        game_over=True,
        turn=turn,
        over={
            "result": result,
            "winner_name": "" if result is None else ("Russian", "German")[result],
            "conditions": [CONDITION],
            "turn": turn,
            "casualties": {"0": {"squads": 1, "leaders": 0}, "1": {"squads": 0, "leaders": 0}},
        },
    )


def test_the_person_reads_you_lost_and_the_cause_in_the_names_of_the_card():
    found = endgame.summary(_view(("human", "computer")))
    assert found.headline == "You lost."
    assert found.lines[0] == "The German side wins. You played the Russian side."
    assert "The game ended after the last turn, turn 5." in found.lines
    assert "The Russian side, hex control: controls 0 of 5 hexes, and needs 1 (PR-16). It is not met." in found.lines
    assert "Losses of the Russian side: 1 squad, 0 leaders." in found.lines
    assert panel.end_lines(_view(("human", "computer")))[0] == "game over: you lost"


def test_a_win_a_watcher_two_people_and_no_winner():
    assert endgame.summary(_view(("human", "computer"), result=0)).headline == "You won."
    assert endgame.summary(_view(("computer", "computer"))).headline == "The German side wins."
    assert endgame.summary(_view(("human", "human"))).headline == "The German side wins."
    assert endgame.summary(_view(("human", "computer"), result=None)).headline == "The game ends with no winner."
    cause = dataclasses.replace(_view(("computer", "computer")), over={"result": 1, "winner_name": "German", "cause": "the other side has no unit left"})
    assert "The other side has no unit left." in endgame.summary(cause).lines


def test_the_turn_line_says_how_many_turns_are_left():
    view = GameView(scenario={"players": ["allied", "axis"], "turns": 5})
    assert endgame.turn_text(dataclasses.replace(view, turn=1)) == "turn 1 of 5: 4 more turns after this one"
    assert endgame.turn_text(dataclasses.replace(view, turn=4)) == "turn 4 of 5: 1 more turn after this one"
    assert endgame.turn_text(dataclasses.replace(view, turn=5)) == "turn 5 of 5: the last turn"
    assert endgame.turn_text(dataclasses.replace(view, turn=6)) == "turn 5 of 5: the last turn is complete"
    assert endgame.turn_text(GameView(turn=2)) == "turn 2"


def test_a_side_of_a_library_scenario_has_the_name_of_its_army():
    assert annotate.side_names(build_engine("lib01_grain_office")) == {0: "Russian", 1: "German"}
    assert annotate.side_names(build_engine("s01_guards_counterattack")) == {0: "Russian", 1: "German"}


def test_the_2d_window_shows_the_end_box_until_a_click_or_escape():
    host = Host(build_engine("lib01_grain_office"), seed=1)
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, "test window")
    client.start()
    window = Window(client, size=(1200, 860), caption="test")
    try:
        live = wait_for(client, lambda s: bool(s.legal) and s.board is not None)
        over = dataclasses.replace(live, game_over=True, turn=6, over=_view(("human", "computer")).over, sides=_view(("human", "computer")).sides)
        step_with(window, over)
        assert window.state.end_rect is not None, "the end box is on the window"
        window.click(window.state.end_rect.center, over)
        step_with(window, over)
        assert window.state.end_rect is None and window.state.end_closed, "a click closes it, and it stays closed"
        window.state.end_closed = False
        step_with(window, over)
        window.key(key(pygame.K_ESCAPE), over)
        assert window.state.end_rect is None
    finally:
        client.stop()
        embedded.stop()
        pygame.quit()
