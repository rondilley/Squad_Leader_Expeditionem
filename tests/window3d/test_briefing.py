"""The scenario briefing before the game: the card, Begin, and no game until then."""

from __future__ import annotations

import pytest

pytest.importorskip("panda3d")
pytest.importorskip("pygame")

from panda3d.core import loadPrcFileData  # noqa: E402

loadPrcFileData("", "window-type offscreen")
loadPrcFileData("", "win-size 320 240")
loadPrcFileData("", "audio-library-name null")

from slcli import window3d_cmd  # noqa: E402


@pytest.fixture(scope="module")
def app():
    import builtins

    from slwindow3d.app import Board3DApp

    existing = getattr(builtins, "base", None)
    if isinstance(existing, Board3DApp):
        yield existing
        return
    instance = Board3DApp(None)
    yield instance
    instance.destroy()


def test_the_briefing_document_is_the_scenario_with_its_situation():
    doc = window3d_cmd.briefing_document("s01_guards_counterattack")
    assert doc is not None
    assert doc["id"] == "s01_guards_counterattack"
    assert doc["situation"].startswith("Stalingrad, October 1942.")
    # The situation is for the players: it names no requirement and no file of the project.
    assert "FR-" not in doc["situation"] and "docs/" not in doc["situation"]
    # A random scenario of Game Set IV has no file, so it has no card.
    assert window3d_cmd.briefing_document("random:5") is None


@pytest.mark.parametrize(
    "scenario", ["s01_guards_counterattack", "s02_tractor_works", "s03a_streets_of_stalingrad", "s04_armor_probe"]
)
def test_each_mvp_scenario_has_a_situation_for_the_players(scenario):
    doc = window3d_cmd.briefing_document(scenario)
    assert doc is not None and len(doc.get("situation", "")) > 100
    assert f"{doc['turns']} turns" in doc["situation"].lower().replace("five", "5").replace("six", "6").replace(
        "seven", "7"
    ).replace("eight", "8")


def test_the_card_is_on_the_screen_and_begin_starts_the_game_one_time(app):
    from slwindow3d.briefing import Briefing

    started = []
    briefing = Briefing(app, window3d_cmd.briefing_document("s01_guards_counterattack"), lambda: started.append(1))
    app.briefing = briefing
    try:
        assert briefing.open
        assert not briefing.backdrop.isEmpty()
        app.graphicsEngine.renderFrame()
        # A click on the card is not a click on the board.
        app._dragged = 0.0
        app._drag_stop("mouse1")
        assert started == []
        briefing.begin()
        briefing.begin()
        assert started == [1]
        assert not briefing.open
    finally:
        app.briefing = None


def test_the_command_has_a_switch_to_skip_the_card():
    import argparse

    parser = argparse.ArgumentParser()
    window3d_cmd.add_parser(parser.add_subparsers())
    assert parser.parse_args(["window3d", "--no-briefing"]).no_briefing is True
    assert parser.parse_args(["window3d"]).no_briefing is False


def test_the_card_and_its_button_draw_over_the_status_panel(app):
    """The status panel on the right is made again with each frame. The briefing must stay
    over it, with its Begin button in view and first for a click."""
    from panda3d.core import PNMImage

    from slcli.play import build_engine
    from slwindow.client import GameView
    from slcore.view import board_document
    from slwindow3d.briefing import BRIEFING_BIN, Briefing

    engine = build_engine("s01_guards_counterattack")
    app.set_board(board_document(engine.board))
    briefing = Briefing(app, window3d_cmd.briefing_document("s01_guards_counterattack"), lambda: None)
    app.briefing = briefing
    try:
        # A status panel made after the card, as a new frame makes it.
        snapshot = GameView()
        app._update_hud(snapshot)
        assert briefing.backdrop.getBinName() == BRIEFING_BIN
        assert app._hud is not None and app._hud.getBinName() != BRIEFING_BIN
        app.graphicsEngine.renderFrame()
        app.graphicsEngine.renderFrame()
        image = PNMImage()
        assert app.win.getScreenshot(image)
        # The pixel at the centre of the Begin button has the colour of the button.
        point = app.aspect2d.getRelativePoint(briefing.button, (0, 0, 0))
        aspect = app.getAspectRatio()
        x = int((point.x / aspect + 1.0) * 0.5 * image.getXSize())
        y = int((1.0 - (point.z + 1.0) * 0.5) * image.getYSize())
        red, green, blue = image.getRed(x, y), image.getGreen(x, y), image.getBlue(x, y)
        assert red > green + 0.1 and red > blue + 0.1, f"the pixel of the button is {red:.2f} {green:.2f} {blue:.2f}"
    finally:
        briefing.begin()
        app.briefing = None
        # The window is shared by the tests of this process; the panel goes with the test.
        if app._hud is not None:
            app._hud.destroy()
            app._hud = None
            app._hud_key = None
