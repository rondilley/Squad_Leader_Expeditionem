"""The host command: one command starts the host and shows the address to open (OP-01)."""

from __future__ import annotations

import asyncio
import webbrowser
from pathlib import Path
from typing import Any

from slcli.play import build_engine, make_agent
from slhost.server import DEFAULT_HOST, DEFAULT_PORT, Host, use_selector_loop

CLIENT_BUILD = Path("client") / "dist"


WATCHABLE_DELAY = 0.25


def run(args: Any) -> int:
    use_selector_loop()
    engine = build_engine(args.scenario, args.board)
    root = Path(args.client) if args.client else CLIENT_BUILD
    agents = {}
    if args.agents:
        # The fourth play mode: computer against computer. Each seat goes to an agent, and
        # the browser is a watcher.
        names = [name.strip() for name in args.agents.split(",")]
        if len(names) != 2:
            raise ValueError(f"--agents takes two names, and {args.agents!r} has {len(names)}")
        for seat, name in enumerate(names):
            agents[seat] = make_agent(name, engine, args.seed, seat)
    elif args.agent:
        seat = engine.scenario.side_index(args.agent_side) if args.agent_side else 1
        agents[seat] = make_agent(args.agent, engine, args.seed, seat)
    # A game that plays itself runs as fast as the socket takes it. That gives a result and
    # shows no game, so a person who watches gets a pause between two commands.
    agent_delay = args.agent_delay
    if agent_delay is None:
        agent_delay = WATCHABLE_DELAY if args.agents else 0.0
    host = Host(
        engine,
        seed=args.seed,
        hot_seat=not args.lan,
        room_code=args.room_code,
        client_root=root if root.is_dir() else None,
        allowed_origins=tuple(args.origin) if args.origin else (),
        strict_los=args.strict_los,
        agents=agents,
        agent_delay=agent_delay,
        traces=args.traces,
    )
    url = f"http://{args.address}:{args.port}/?room={host.room.code}"
    print(f"scenario {engine.scenario.id} on board {engine.board.name}")
    for seat, agent in agents.items():
        print(f"player {seat} ({engine.scenario.players()[seat]}) is the scripted agent {agent.name} v{agent.version}")
    if agents and len(agents) == 2:
        print(f"the two computer opponents play by themselves, {agent_delay} s between commands")
    print(f"room code {host.room.code}")
    print(f"open {url}")
    if host.client_root is None:
        print("the client is not built; run 'npm install' and 'npm run build' in client/")
    if args.open_browser:
        webbrowser.open(url)
    try:
        asyncio.run(host.run(args.address, args.port))
    except KeyboardInterrupt:
        print("host stopped")
    if args.traces:
        path = host.game.write_traces(Path(args.traces))
        if path is not None:
            print(f"{len(host.game.traces.records)} trace records in {path}")
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("host", help="start the local host and serve the browser client")
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--board", default=None)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--address", default=DEFAULT_HOST)
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--lan", action="store_true", help="two browsers on one network, one seat for each")
    p.add_argument("--room-code", default=None, help="use this room code instead of a new one")
    p.add_argument("--client", default=None, help="the directory of the built client")
    p.add_argument("--origin", action="append", help="an allowed WebSocket origin; repeat for more")
    p.add_argument("--agent", default=None, choices=("random", "v0", "v1", "v2", "v3", "v4", "v5", "v6"), help="give one side to a computer opponent (FR-39)")
    p.add_argument(
        "--agents",
        default=None,
        help="give each side to a computer opponent, as two names: v1,v2. The browser watches",
    )
    p.add_argument(
        "--agent-delay",
        type=float,
        default=None,
        help="seconds between two commands of a game that plays itself. The default is "
        f"{WATCHABLE_DELAY} with --agents, which is slow enough for a person to follow",
    )
    p.add_argument("--agent-side", default=None, help="the side name the computer opponent holds; the second side by default")
    p.add_argument("--strict-los", action="store_true", help="answer a line of sight question only in a fire phase (rule 19.3)")
    p.add_argument("--traces", default=None, help="directory for the trace records of the game (FR-60)")
    p.add_argument("--open-browser", action="store_true", help="open the address in a browser")
    p.set_defaults(func=run)
