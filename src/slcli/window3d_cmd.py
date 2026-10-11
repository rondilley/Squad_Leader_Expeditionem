"""`sl-cli window3d`: the board in a 3D window of its own, on Windows and on Unix.

The 3D window is a new consumer of the same host protocol the pygame window reads. It sends
intents and it applies no rule (AR-06). It draws the board as hex prisms that the elevation
of each hex lifts, so a hill stands up.

The command starts a host inside the same process and connects the window to it, the same
way `sl-cli window` does. With `--agent v6` a person plays one side with the mouse against
the computer opponent v6 (`--agent-side` names the side the computer holds). With no agent a
person plays both sides in hot seat. With `--agents v4,v1` the window watches a game of two
computer opponents and takes no input.

With `--screenshot PATH` it renders one board offscreen, writes the PNG, and exits. That is
the path a test and a verification run take, and it needs no display.

The 3D window needs the `play` extra (Panda3D, and pygame-ce for the counter art):

    pip install -e ".[play]"
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from slcli.play import build_engine, make_agent

WATCHABLE_DELAY = 0.4

# The difficulty names of the computer opponent, for a person who does not know the agent
# versions. The gauntlet of 2026-10-10 on the four MVP scenarios (scenarios 1, 2, 3A, and
# 4, 160 games each) ranks v6.1 first (65.0 percent), v3 second (62.8), v1 third (60.6),
# and v5 fourth (42.2), so easy is v5, normal is v3, and hard is v6.
DIFFICULTY = {"easy": "v5", "normal": "v3", "hard": "v6"}


class View3DNotInstalled(Exception):
    """The 3D view library is not installed, and the 3D window cannot open without it."""

    def __init__(self) -> None:
        super().__init__(
            "the 3D window needs panda3d and pygame-ce. Install them with: pip install -e \".[play]\""
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


def _load_interactive(muted: bool = False):
    """Import Panda3D for an open window."""
    try:
        import panda3d.core  # noqa: F401
    except ImportError as exc:  # the boundary of an optional dependency
        raise View3DNotInstalled() from exc
    from panda3d.core import loadPrcFileData

    # The sound effects play through OpenAL, the audio library of the Panda3D wheel. With
    # `--mute` the window loads no audio library, so a machine with no sound device opens it.
    loadPrcFileData("", "audio-library-name null" if muted else "audio-library-name p3openal_audio")
    loadPrcFileData("", "win-size 1500 950")
    loadPrcFileData("", "window-title Squad Leader AI - 3D board (t=2D/3D, drag=pan, wheel=zoom, right-drag=tilt, r=reset, q=quit)")
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


def build_host(args: Any) -> tuple[Any, Any, dict[str, Any]]:
    """The engine, the host, and the save record of the game this command plays.

    With `--resume FILE` the scenario, the board, the seed, and the computer opponents come
    from the save file, and the saved command log plays again on the new host (each hash is
    checked). Otherwise they come from the options. The host holds no rule; the core applies
    each command (AR-06).
    """
    from slhost import saves
    from slhost.server import Host

    saved = None
    if args.resume:
        saved = saves.read_save(Path(args.resume))
        args.scenario = saved["scenario"]
        args.board = saved.get("board")
        args.seed = int(saved["seed"])
    engine = build_engine(args.scenario, args.board)
    opponents: dict[int, str] = {}
    if saved is not None:
        opponents = {int(seat): str(name) for seat, name in saved.get("opponents", {}).items()}
    elif args.agents:
        names = [name.strip() for name in args.agents.split(",")]
        if len(names) != 2:
            raise ValueError(f"--agents takes two names, and {args.agents!r} has {len(names)}")
        opponents = dict(enumerate(names))
    elif args.agent:
        seat = engine.scenario.side_index(args.agent_side) if args.agent_side else 1
        opponents = {seat: DIFFICULTY.get(args.agent, args.agent)}
    agents = {seat: make_agent(name, engine, args.seed, seat) for seat, name in opponents.items()}
    delay = args.agent_delay
    if delay is None:
        delay = WATCHABLE_DELAY if len(agents) >= 2 else 0.0
    # `--auto-setup` gives the set up of each side a person plays to an agent.
    setup_agents = {}
    if args.auto_setup:
        for seat in range(len(engine.scenario.players())):
            if seat not in agents:
                setup_agents[seat] = make_agent(args.auto_setup, engine, args.seed, seat)
    host = Host(engine, seed=args.seed, hot_seat=True, agents=agents, agent_delay=delay, setup_agents=setup_agents)
    if saved is not None:
        played = saves.replay_into(host, saved)
        print(f"resumed {args.resume}: {played} commands played again, each hash agrees")
    record = {"scenario": args.scenario, "board": args.board, "seed": args.seed, "opponents": opponents}
    return engine, host, record


def briefing_document(scenario: str) -> dict[str, Any] | None:
    """The scenario JSON for the briefing card, or None for a scenario that has no file (a
    random scenario of Game Set IV is built from its seed)."""
    from slcli.cards_cmd import load_document
    from sldata.loaders import DataError

    try:
        return load_document(scenario)
    except DataError:
        return None


def save_path(args: Any, record: dict[str, Any]) -> Path:
    """Where the autosave goes: `--save`, or the resumed file, or one file for each
    scenario and seed under `runs/saves/`, which git does not record."""
    if args.save:
        return Path(args.save)
    if args.resume:
        return Path(args.resume)
    return Path("runs") / "saves" / f"{record['scenario']}-seed{record['seed']}.json"


def _interactive(args: Any) -> int:
    from slcore.view import board_document
    from slhost import saves
    from slwindow.client import HostClient
    from slwindow.embedded import start

    Board3DApp = _load_interactive(args.mute)
    engine, host, record = build_host(args)
    agents = host.agents
    embedded = start(host)
    print(f"scenario {engine.scenario.id} on board {engine.board.name}")
    players = engine.scenario.players()
    for seat, agent in agents.items():
        print(f"player {seat} ({players[seat]}) is the computer opponent {agent.name} v{agent.version}")
    human = [players[seat] for seat in range(len(players)) if seat not in agents]
    if human:
        print(f"you play {' and '.join(human)}: click a unit, then click a ring")
        if host.setup_agents:
            print(f"the computer opponent {args.auto_setup} places your units in the Set Up Phase")
    print(f"the 3D window talks to a host inside this process at {embedded.url}")
    target = save_path(args, record)

    def autosave() -> None:
        # A game that a person plays is saved after each new frame, so a crash or a closed
        # window loses nothing. A game of two computers is not saved.
        if len(agents) >= 2:
            return
        try:
            saves.write_save(
                target,
                saves.save_document(host, record["scenario"], record["board"], record["seed"], record["opponents"]),
            )
        except saves.SaveError as exc:
            print(f"autosave failed: {exc}")

    if human and len(agents) < 2:
        print(f"the game saves itself to {target}; resume it with: sl-cli window3d --resume {target}")
    client = HostClient(embedded.url, embedded.room_code, display_name="3D window")
    board_doc = board_document(engine.board)
    # The scenario card goes on the screen first. The window joins the host only when the
    # person begins, so no game, not even one of two computers, starts behind the card.
    briefing = None if args.no_briefing else briefing_document(record["scenario"])
    if args.hills:
        _synthesize_hill(board_doc)
    # A window that holds a seat sends intents. A window that watches two computers does not.
    send = client.send_intent if len(agents) < 2 else None
    person_side = human[0] if len(human) == 1 else None
    app = Board3DApp(
        board_doc,
        poll=client.snapshot,
        send=send,
        on_frame=autosave,
        person_side=person_side,
        ask_los=client.request_los,
        briefing=briefing,
        on_begin=client.start,
        sound=not args.mute,
    )
    try:
        app.run()
    finally:
        autosave()
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
    p.add_argument(
        "--agent",
        default=None,
        help="give one side to a computer opponent, and play the other side: easy (v5), normal (v3), hard (v6), or an agent name",
    )
    p.add_argument("--agent-side", default=None, help="the side name the computer opponent holds; the default is the second side")
    p.add_argument("--agents", default=None, help="give each side to a computer opponent, as two names: v4,v1")
    p.add_argument(
        "--auto-setup",
        nargs="?",
        const="v6",
        default=None,
        help="a computer opponent places the units of your side in set up (v6 when no name is given)",
    )
    p.add_argument(
        "--agent-delay",
        type=float,
        default=None,
        help=f"seconds between two commands of a game that plays itself. The default is {WATCHABLE_DELAY} with --agents",
    )
    p.add_argument("--mute", action="store_true", help="no sound effects and no audio library; with sound on, the m key mutes and unmutes")
    p.add_argument("--no-briefing", action="store_true", help="start the game at once, with no scenario card first")
    p.add_argument("--resume", default=None, help="resume the game in this save file (the scenario, board, seed, and opponents come from it)")
    p.add_argument("--save", default=None, help="the autosave file; the default is runs/saves/<scenario>-seed<seed>.json")
    p.add_argument("--screenshot", default=None, help="render one board offscreen to this PNG and exit")
    p.add_argument("--advance", type=int, default=260, help="drive this many setup commands before a screenshot, so pieces are on the board")
    p.add_argument("--hills", action="store_true", help="synthesize a hill on a flat board, so the 3D effect shows")
    p.set_defaults(func=run)
