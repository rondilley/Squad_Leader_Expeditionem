"""`sl-cli window3d`: the board in a 3D window of its own, on Windows and on Unix.

The 3D window is a new consumer of the same host protocol the pygame window reads. It sends
intents and it applies no rule (AR-06). It draws the board as hex prisms that the elevation
of each hex lifts, so a hill stands up.

The 3D window is for play (H2). It takes the options of `sl-cli window`: with no address
it starts a host inside the same process and connects to it. With no computer opponent the
game is hot seat, and the window plays the two sides. `--agent v7` gives one side to a
computer opponent (`--agent-side` names it), `--agents v4,v1` watches a game of two
computer opponents, `--lan` gives one seat to each connection, and `--connect ws://...`
with `--room-code` joins a host that already runs.
<<<<<<< Updated upstream
=======

Before the game the window shows the scenario card (`slwindow3d/briefing.py`), and the
host starts the game when the person presses Begin; `--no-briefing` skips the card. The
window plays the sounds of fire and movement through OpenAL; `--mute` loads no audio
library, and Ctrl and m turns the sound off and on.
>>>>>>> Stashed changes

With `--screenshot PATH` it renders one board offscreen, writes the PNG, and exits. That is
the path a test and a verification run take, and it needs no display.

The 3D window needs the `view3d` extra:

    pip install -e ".[view3d]"
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from slagents.base import decide
from slcli.play import build_engine, make_agent



class View3DNotInstalled(Exception):
    """The 3D view library is not installed, and the 3D window cannot open without it."""

    def __init__(self) -> None:
        super().__init__(
            "the 3D window needs panda3d. Install it with: pip install -e \".[view3d]\""
        )


def _load_offscreen():
    """Import Panda3D with the offscreen window type set, for a screenshot with no display."""
    try:
        from panda3d.core import loadPrcFileData
    except ImportError as exc:  # the boundary of an optional dependency
        raise View3DNotInstalled() from exc
    loadPrcFileData("", "window-type offscreen")
    loadPrcFileData("", "win-size 1200 860")
    loadPrcFileData("", "audio-library-name null")
    from slwindow3d.app import Board3DApp

    return Board3DApp


def _load_interactive(args: Any = None):
    """Import Panda3D for an open window."""
    try:
        import panda3d.core  # noqa: F401
    except ImportError as exc:  # the boundary of an optional dependency
        raise View3DNotInstalled() from exc
    from panda3d.core import loadPrcFileData

    width = getattr(args, "width", None) or 1500
    height = getattr(args, "height", None) or 950
<<<<<<< Updated upstream
    loadPrcFileData("", "audio-library-name null")
=======
    # The sounds play through OpenAL. With `--mute` the window loads no audio library.
    audio = "null" if getattr(args, "mute", False) else "p3openal_audio"
    loadPrcFileData("", f"audio-library-name {audio}")
>>>>>>> Stashed changes
    loadPrcFileData("", f"win-size {int(width)} {int(height)}")
    loadPrcFileData(
        "",
        "window-title Squad Leader Expeditionem - 3D board "
        "(click pick, enter play, ctrl+t 2D/3D, drag pan, wheel zoom, right-drag tilt, ctrl+q quit)",
    )
    from slwindow3d.app import Board3DApp

    return Board3DApp


def _synthesize_hill(board_doc: dict[str, Any]) -> bool:
    """Add a hill to a flat board, so the 3D extrusion is visible. Return True if it did.

    A city scenario ships no elevation, and a flat board shows no hill. For a screenshot
    that must show the 3D effect, this raises a dome in the middle of the board, the same
    way the prototype does. It touches only the board document the view holds, not the core.
    """
    hexes = board_doc["hexes"]
    if any(h.get("elevation") for h in hexes):
        return False
    root_three = math.sqrt(3.0)
    cx0 = sum(h["center"][0] for h in hexes) / len(hexes)
    cy0 = sum(h["center"][1] for h in hexes) / len(hexes)
    for h in hexes:
        distance = math.hypot(h["center"][0] - cx0, (h["center"][1] - cy0) * root_three)
        h["elevation"] = max(0, min(3, int((60 - distance) / 16)))
    return True


def _advance_state(engine: Any, seed: int, agents: dict[int, Any], steps: int):
    """Drive the engine forward a few commands with two agents, so units land on the board.

    This drives the core through its public functions the way the host does: it asks for the
    legal commands, an agent picks one, and the engine applies it. It reimplements no rule
    (AR-06). A screenshot at the start of a game shows an empty board, because setup places
    the units one command at a time.
    """
    state = engine.new_game(seed)
    for _ in range(max(0, steps)):
        if state.game_over:
            break
        frame = engine.legal_commands(state)
        if not frame.commands:
            break
        chosen = decide(agents[state.active], state, frame)
        legal = frame.by_id(chosen)
        if legal is None:
            break
        state, _ = engine.apply(state, legal.command, frame)
    return state


def _screenshot(args: Any) -> int:
    from slcore import view as core_view
    from slcore.view import board_document

    Board3DApp = _load_offscreen()
    engine = build_engine(args.scenario, args.board)
    board_doc = board_document(engine.board)
    # A spectator view holds each unit, so the screenshot shows the pieces on the board.
    agents = {seat: make_agent("v1", engine, args.seed, seat) for seat in (0, 1)}
    state = _advance_state(engine, args.seed, agents, args.advance)
    view_doc = core_view.build(state, engine.types, core_view.SPECTATOR, spectator=True)
    note = ""
    if args.hills:
        added = _synthesize_hill(board_doc)
        if added:
            note = " (elevation synthesized so the hill shows)"
    Board3DApp.render_screenshot(board_doc, str(args.screenshot), view_doc=view_doc)
    print(f"wrote {args.screenshot}{note}")
    return 0


<<<<<<< Updated upstream
=======
def briefing_document(scenario: str) -> dict[str, Any] | None:
    """The scenario JSON for the briefing card, or None for a scenario that has no file (a
    random scenario of Game Set IV is built from its seed)."""
    from slcli.cards_cmd import load_document
    from sldata.loaders import DataError

    try:
        return load_document(scenario)
    except DataError:
        return None


>>>>>>> Stashed changes
def _interactive(args: Any) -> int:
    """Play or watch in the 3D window (H2).

    The host comes from `window_cmd.connect_or_start`, the same function the 2D window
    uses, so the options and the game are the same in the two windows. The window sends
    intents and an undo through the same `HostClient` the 2D window uses.
    """
    from slcli.window_cmd import connect_or_start, finish
    from slwindow.client import HostClient

    Board3DApp = _load_interactive(args)
    embedded, url, room_code, _caption = connect_or_start(args, title="Squad Leader Expeditionem 3D")
    client = HostClient(url, room_code, display_name="3D window")
<<<<<<< Updated upstream
    client.start()
=======
    # The scenario card comes first, and the game starts on Begin. A window that joins a
    # host that already runs shows no card, because its game has started.
    briefing = None if (args.no_briefing or args.connect) else briefing_document(args.scenario)
    if briefing is None:
        client.start()
>>>>>>> Stashed changes
    board_doc = None
    if embedded is not None:
        from slcore.view import board_document

        board_doc = board_document(embedded.host.engine.board)
        if args.hills:
            _synthesize_hill(board_doc)
<<<<<<< Updated upstream
    app = Board3DApp(board_doc, client=client)
=======
    app = Board3DApp(
        board_doc,
        client=client,
        briefing=briefing,
        on_begin=client.start,
        sound=True,
        muted=bool(args.mute),
    )
>>>>>>> Stashed changes
    try:
        app.run()
    finally:
        client.stop()
        finish(embedded, args)
    return 0


def run(args: Any) -> int:
    if args.screenshot:
        return _screenshot(args)
    return _interactive(args)


def add_parser(subparsers: Any) -> None:
    from slcli.window_cmd import add_play_options

    p = subparsers.add_parser("window3d", help="play or watch the game in a 3D window with elevation")
    add_play_options(p)
    p.add_argument("--width", type=int, default=1500)
    p.add_argument("--height", type=int, default=950)
    p.add_argument("--screenshot", default=None, help="render one board offscreen to this PNG and exit")
    p.add_argument("--advance", type=int, default=260, help="drive this many setup commands before a screenshot, so pieces are on the board")
    p.add_argument("--hills", action="store_true", help="synthesize a hill on a flat board, so the 3D effect shows")
    p.add_argument("--no-briefing", action="store_true", help="start the game at once, with no scenario card first")
    p.add_argument("--mute", action="store_true", help="no sound: load no audio library")
    p.set_defaults(func=run)
