"""`sl-cli window`: the game in a window of its own, on Windows and on Unix.

With no address the command starts a host inside the same process and connects the window
to it over the loopback address. With `--connect` the window joins a host that is already
running, which is the LAN game of rule set FR-33. With no computer opponent the game is hot
seat: the window plays the two sides. `--agent v7` gives one side to a computer opponent,
and `--agents v4,v1` gives it both. `--agent easy`, `normal`, or `hard` names the
opponent by difficulty (`DIFFICULTY`). Each game saves to `--save-dir`, and `--resume FILE`
goes on with a saved game. `--lan` gives one seat to each connection.

The window needs the `desktop` extra:

    pip install -e ".[desktop]"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from slcli.play import build_engine, make_agent
from slhost.server import Host

WATCHABLE_DELAY = 0.4

# The difficulty names of `--agent`, from the weakest to the strongest computer opponent:
# v5 (the doctrine of fire), v6 (the attack on a schedule), and v7 (the odds).
DIFFICULTY = {"easy": "v5", "normal": "v6", "hard": "v7"}


def agent_name(name: str) -> str:
    """An agent name, with a difficulty name turned into its agent."""
    return DIFFICULTY.get(name.strip().lower(), name.strip())


class DesktopNotInstalled(Exception):
    """The 2D game library is not installed, and the window cannot open without it."""

    def __init__(self) -> None:
        super().__init__(
            "the desktop window needs pygame-ce. Install it with: pip install -e \".[desktop]\""
        )


def load_window():
    """Import the window late, so `sl-cli --help` works with no game library installed."""
    try:
        import pygame
    except ImportError as exc:  # the boundary of an optional dependency
        raise DesktopNotInstalled() from exc
    if not hasattr(pygame, "display"):  # pragma: no cover - a broken install
        raise DesktopNotInstalled()
    from slwindow.app import Window

    return Window


def connect_or_start(args: Any, title: str = "Squad Leader Expeditionem"):
    """The host a window talks to: the one at `--connect`, or one this process starts.

    The two windows (`sl-cli window` and `sl-cli window3d`) take the same options and use
    this one function, so a game plays the same in each. Return the embedded host (or
    None), the address, the room code, and the caption of the window.
    """
    if args.connect:
        url = str(args.connect)
        room_code = str(args.room_code or "")
        return None, url, room_code, f"{title} - {url}"
    from slcli.host_cmd import read_resume
    from slhost import savegame

    read_resume(args)
    engine = build_engine(args.scenario, args.board)
    agents = {}
    recorded: dict[str, str] = {}
    if args.agents:
        names = [agent_name(name) for name in args.agents.split(",")]
        if len(names) != 2:
            raise ValueError(f"--agents takes two names, and {args.agents!r} has {len(names)}")
        for seat, name in enumerate(names):
            agents[seat] = make_agent(name, engine, args.seed, seat)
            recorded[str(seat)] = name
    elif args.agent:
        seat = getattr(args, "_agent_seat", None)
        if seat is None:
            seat = engine.scenario.side_index(args.agent_side) if args.agent_side else 1
        agents[seat] = make_agent(agent_name(args.agent), engine, args.seed, seat)
        recorded[str(seat)] = agent_name(args.agent)
    delay = args.agent_delay
    if delay is None:
        delay = WATCHABLE_DELAY if args.agents else 0.0
    host = Host(
        engine,
        seed=args.seed,
        hot_seat=not args.lan,
        room_code=args.room_code,
        agents=agents,
        agent_delay=delay,
        traces=args.traces,
        save_dir=None if (args.no_save or args.resume) else Path(args.save_dir),
        save_header={"board": args.board, "agents": recorded},
    )
    if args.resume:
        count = host.resume_from(args.resume)
        print(f"resumed {args.resume}: {count} commands, each hash the same as the record")
    if host.game.save is not None:
        print(f"the game saves to {host.game.save.path}; go on with it: --resume {host.game.save.path}")
    from slwindow.embedded import start

    embedded = start(host)
    print(f"scenario {engine.scenario.id} on board {engine.board.name}")
    for seat, agent in agents.items():
        print(f"player {seat} ({engine.scenario.players()[seat]}) is the computer opponent {agent.name} v{agent.version}")
    if len(agents) == 2:
        print(f"the two computer opponents play by themselves, {delay} s between commands")
    elif not agents:
        mode = "LAN: one seat for each connection" if args.lan else "hot seat: this window plays the two sides"
        print(mode)
    if args.lan:
        print(f"the room code is {embedded.room_code}")
    print(f"the window talks to a host inside this process at {embedded.url}")
    return embedded, embedded.url, embedded.room_code, f"{title} - {engine.scenario.title}"


def finish(embedded: Any, args: Any) -> None:
    """Write the traces of the game and stop the host this process started."""
    if embedded is None:
        return
    if args.traces:
        path = embedded.host.game.write_traces(Path(args.traces))
        if path is not None:
            print(f"{len(embedded.host.game.traces.records)} trace records in {path}")
    embedded.stop()


def run(args: Any) -> int:
    Window = load_window()
    from slwindow.client import HostClient

    embedded, url, room_code, caption = connect_or_start(args)
    client = HostClient(url, room_code)
    client.start()
    window = Window(client, size=(args.width, args.height), caption=caption)
    try:
        window.run()
    finally:
        client.stop()
        finish(embedded, args)
    return 0


def add_play_options(p: Any) -> None:
    """The options of a game, the same for the two windows."""
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--board", default=None)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--connect", default=None, help="the address of a host that already runs, as ws://host:port/")
    p.add_argument("--room-code", default=None, help="the room code of that host, or a code for the host this starts")
    p.add_argument("--lan", action="store_true", help="one seat for each connection instead of hot seat")
    p.add_argument("--agent", default=None, help="give one side to a computer opponent")
    p.add_argument("--agents", default=None, help="give each side to a computer opponent, as two names: v1,v2")
    p.add_argument("--agent-side", default=None, help="the side name the computer opponent holds")
    p.add_argument(
        "--agent-delay",
        type=float,
        default=None,
        help=f"seconds between two commands of a game that plays itself. The default is {WATCHABLE_DELAY} with --agents",
    )
    p.add_argument("--traces", default=None, help="directory for the trace records of the game (FR-60)")
    from slhost.savegame import DEFAULT_DIRECTORY

    p.add_argument("--save-dir", default=str(DEFAULT_DIRECTORY), help="the directory of the save files; each game is <game_id>.jsonl")
    p.add_argument("--no-save", action="store_true", help="do not write a save file")
    p.add_argument("--resume", default=None, help="a save file: play its commands again, check each hash, and go on with the game")


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("window", help="play or watch the game in a window of its own, with no browser")
    add_play_options(p)
    p.add_argument("--width", type=int, default=1400)
    p.add_argument("--height", type=int, default=860)
    p.set_defaults(func=run)
