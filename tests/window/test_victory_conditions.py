"""The victory conditions during play: the violet hexes, the button, and the box.

The model (`slwindow.victorytext`, the overlay tones) reads the `objectives` of the frame.
The 2D window test drives the button and the keys against a host in the process.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slagents.base import decide  # noqa: E402
from slagents.registry import make_agent  # noqa: E402
from slcli.play import build_engine  # noqa: E402
from slhost.server import Host  # noqa: E402
from slwindow import overlay, panel, victorytext  # noqa: E402
from slwindow.app import Window  # noqa: E402
from slwindow.client import GameView, HostClient  # noqa: E402
from slwindow.embedded import start  # noqa: E402

from tests.window.test_window_play_v2 import key, step_with, wait_for  # noqa: E402

OFFICE = ["Z6", "AA6", "AA7", "BB6", "CC6"]
NOTE = "The Russians win if they end the game in control of 1 hex of the largest stone building in columns U to EE. Otherwise the Germans win."


def _view(person: int, held: list[str] | None = None, status: bool = True) -> GameView:
    record = {"side": 0, "side_name": "Russian", "kind": "hex_control", "note": NOTE, "hexes": OFFICE, "turns": 5}
    if status:
        record["status"] = {"count": len(held or []), "threshold": 1, "satisfied": bool(held), "detail": "d", "held": held or []}
    controllers = ("human", "computer") if person == 0 else ("computer", "human")
    return GameView(
        scenario={"players": ["allied", "axis"], "turns": 5},
        sides={"0": {"name": "Russian", "controller": controllers[0]}, "1": {"name": "German", "controller": controllers[1]}},
        turn=2,
        objectives=[record],
    )


def test_the_box_says_what_wins_and_where_the_person_is_now():
    lines = victorytext.lines(_view(0, held=["AA7"]))
    assert lines[0] == "turn 2 of 5: 3 more turns after this one."
    assert lines[1] == NOTE
    assert lines[2] == "You control 1 of the 5 violet hexes (AA7). You need 1 at the end of turn 5."
    german = victorytext.lines(_view(1, status=False))
    assert german[2] == "The violet hexes are the objective of the Russian side: Z6, AA6, AA7, BB6, CC6."


def test_the_objective_hexes_are_violet_and_strong_with_the_button():
    tracker = overlay.Tracker()
    snapshot = _view(0, held=["AA7"])
    snapshot.view = {"units": []}
    quiet = tracker.update(snapshot, 0.0).shades
    assert all(quiet[h] == overlay.TONE_OBJECTIVE for h in OFFICE if h != "AA7")
    assert quiet["AA7"] == overlay.TONE_OBJECTIVE_HELD
    strong = tracker.update(snapshot, 0.0, show_objectives=True).shades
    assert all(strong[h] == overlay.TONE_OBJECTIVE_ON for h in OFFICE if h != "AA7")
    assert strong["AA7"] == overlay.TONE_OBJECTIVE_HELD_ON


def test_the_button_and_ctrl_and_v_show_the_box_in_the_2d_window():
    engine = build_engine("lib01_grain_office")
    host = Host(engine, seed=1, agents={1: make_agent("v6", engine, 1, 1)})
    game = host.game
    first = make_agent("v1", engine, 1, 0)
    while game.state.phase != "movement":
        frame = engine.legal_commands(game.state)
        agent = first if frame.player == 0 else host.agents[1]
        game.apply(frame.frame_id, decide(agent, game.state, frame))
    embedded = start(host)
    client = HostClient(embedded.url, embedded.room_code, "test window")
    client.start()
    window = Window(client, size=(1300, 860), caption="test")
    try:
        snapshot = wait_for(client, lambda s: bool(s.legal) and s.board is not None and bool(s.objectives))
        step_with(window, snapshot)
        assert all(window.overlay.shades.get(h) == overlay.TONE_OBJECTIVE for h in OFFICE)
        button = next(rect for rect, index in window.rows if index == panel.OBJECTIVES_ROW)
        window.click(button.center, snapshot)
        assert window.state.show_objectives
        step_with(window, snapshot)
        assert all(window.overlay.shades.get(h) == overlay.TONE_OBJECTIVE_ON for h in OFFICE)
        assert "You control 0 of the 5 violet hexes. You need 1 at the end of turn 5." in victorytext.lines(snapshot)
        window.key(key(pygame.K_v, "v", pygame.KMOD_CTRL), snapshot)
        assert not window.state.show_objectives
        assert window.chooser.filter_text == "", "Ctrl and v types no filter text"
        window.key(key(pygame.K_v, "v", pygame.KMOD_CTRL), snapshot)
        window.key(key(pygame.K_ESCAPE), snapshot)
        assert not window.state.show_objectives, "Escape closes the box"
    finally:
        client.stop()
        embedded.stop()
        pygame.quit()
