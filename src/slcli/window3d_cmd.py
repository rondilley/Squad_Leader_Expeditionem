"""`sl-cli window3d`: the board in a 3D window of its own, on Windows and on Unix.

The 3D window is a new consumer of the same host protocol the pygame window reads. It sends
intents and it applies no rule (AR-06). It draws the board as hex prisms that the elevation
of each hex lifts, so a hill stands up.

With no address the command starts a host inside the same process and connects the window
to it, the same way `sl-cli window` does. With `--agents v4,v1` it starts an embedded host
and watches a game of two computer opponents.

With `--screenshot PATH` it renders one board offscreen, writes the PNG, and exits. That is
the path a test and a verification run take, and it needs no display.

The 3D window needs the `view3d` extra:

    pip install -e ".[view3d]"
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from slcli.play import build_engine, make_agent

WATCHABLE_DELAY = 0.4


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


def _load_interactive():
    """Import Panda3D for an open window."""
    try:
        import panda3d.core  # noqa: F401
    except ImportError as exc:  # the boundary of an optional dependency
        raise View3DNotInstalled() from exc
    from panda3d.core import loadPrcFileData

    loadPrcFileData("", "audio-library-name null")
    loadPrcFileData("", "win-size 1500 950")
    loadPrcFileData("", "window-title Squad Leader Expeditionem - 3D board (t=2D/3D, drag=pan, wheel=zoom, right-drag=tilt, r=reset, q=quit)")
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
        chosen = agents[state.active].select(state, frame)
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


def _interactive(args: Any) -> int:
    from slcore.view import board_document
    from slhost.server import Host
    from slwindow.client import HostClient
    from slwindow.embedded import start

    Board3DApp = _load_interactive()
    engine = build_engine(args.scenario, args.board)
    agents = {}
    if args.agents:
        names = [name.strip() for name in args.agents.split(",")]
        if len(names) != 2:
            raise ValueError(f"--agents takes two names, and {args.agents!r} has {len(names)}")
        for seat, name in enumerate(names):
            agents[seat] = make_agent(name, engine, args.seed, seat)
    delay = args.agent_delay
    if delay is None:
        delay = WATCHABLE_DELAY if args.agents else 0.0
    host = Host(engine, seed=args.seed, hot_seat=True, agents=agents, agent_delay=delay)
    embedded = start(host)
    print(f"scenario {engine.scenario.id} on board {engine.board.name}")
    for seat, agent in agents.items():
        print(f"player {seat} is the computer opponent {agent.name} v{agent.version}")
    print(f"the 3D window talks to a host inside this process at {embedded.url}")
    client = HostClient(embedded.url, embedded.room_code, display_name="3D window")
    client.start()
    board_doc = board_document(engine.board)
    if args.hills:
        _synthesize_hill(board_doc)
    app = Board3DApp(board_doc, poll=client.snapshot, ask_los=client.request_los)
    try:
        app.run()
    finally:
        client.stop()
        embedded.stop()
    return 0


def run(args: Any) -> int:
    if args.screenshot:
        return _screenshot(args)
    return _interactive(args)


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("window3d", help="show the board in a 3D window with elevation")
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--board", default=None)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--agents", default=None, help="give each side to a computer opponent, as two names: v4,v1")
    p.add_argument(
        "--agent-delay",
        type=float,
        default=None,
        help=f"seconds between two commands of a game that plays itself. The default is {WATCHABLE_DELAY} with --agents",
    )
    p.add_argument("--screenshot", default=None, help="render one board offscreen to this PNG and exit")
    p.add_argument("--advance", type=int, default=260, help="drive this many setup commands before a screenshot, so pieces are on the board")
    p.add_argument("--hills", action="store_true", help="synthesize a hill on a flat board, so the 3D effect shows")
    p.set_defaults(func=run)
