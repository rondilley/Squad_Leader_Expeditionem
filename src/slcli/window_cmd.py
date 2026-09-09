"""`sl-cli window`: the game in a window of its own, on Windows and on Unix.

With no address the command starts a host inside the same process and connects the window
to it over the loopback address. With `--connect` the window joins a host that is already
running, which is the LAN game of rule set FR-33.

The window needs the `desktop` extra:

    pip install -e ".[desktop]"
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from slcli.play import build_engine, make_agent
from slhost.server import Host

WATCHABLE_DELAY = 0.4


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


def run(args: Any) -> int:
    Window = load_window()
    from slwindow.client import HostClient

    embedded = None
    if args.connect:
        url = str(args.connect)
        room_code = str(args.room_code or "")
        caption = f"Squad Leader AI - {url}"
    else:
        engine = build_engine(args.scenario, args.board)
        agents = {}
        if args.agents:
            names = [name.strip() for name in args.agents.split(",")]
            if len(names) != 2:
                raise ValueError(f"--agents takes two names, and {args.agents!r} has {len(names)}")
            for seat, name in enumerate(names):
                agents[seat] = make_agent(name, engine, args.seed, seat)
        elif args.agent:
            seat = engine.scenario.side_index(args.agent_side) if args.agent_side else 1
            agents[seat] = make_agent(args.agent, engine, args.seed, seat)
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
        )
        from slwindow.embedded import start

        embedded = start(host)
        url = embedded.url
        room_code = embedded.room_code
        caption = f"Squad Leader AI - {engine.scenario.title}"
        print(f"scenario {engine.scenario.id} on board {engine.board.name}")
        for seat, agent in agents.items():
            print(f"player {seat} ({engine.scenario.players()[seat]}) is the computer opponent {agent.name} v{agent.version}")
        if len(agents) == 2:
            print(f"the two computer opponents play by themselves, {delay} s between commands")
        print(f"the window talks to a host inside this process at {url}")

    client = HostClient(url, room_code)
    client.start()
    window = Window(client, size=(args.width, args.height), caption=caption)
    try:
        window.run()
    finally:
        client.stop()
        if embedded is not None:
            if args.traces:
                path = embedded.host.game.write_traces(Path(args.traces))
                if path is not None:
                    print(f"{len(embedded.host.game.traces.records)} trace records in {path}")
            embedded.stop()
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("window", help="play or watch the game in a window of its own, with no browser")
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--board", default=None)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--width", type=int, default=1400)
    p.add_argument("--height", type=int, default=860)
    p.add_argument("--connect", default=None, help="the address of a host that already runs, as ws://host:port/")
    p.add_argument("--room-code", default=None, help="the room code of that host, or a code for the host this starts")
    p.add_argument("--lan", action="store_true", help="one seat for each connection instead of hot seat")
    p.add_argument("--agent", default=None, choices=("random", "v0", "v1", "v2", "v3"), help="give one side to a computer opponent")
    p.add_argument("--agents", default=None, help="give each side to a computer opponent, as two names: v1,v2")
    p.add_argument("--agent-side", default=None, help="the side name the computer opponent holds")
    p.add_argument(
        "--agent-delay",
        type=float,
        default=None,
        help=f"seconds between two commands of a game that plays itself. The default is {WATCHABLE_DELAY} with --agents",
    )
    p.add_argument("--traces", default=None, help="directory for the trace records of the game (FR-60)")
    p.set_defaults(func=run)
