"""The host command: one command starts the host and shows the address to open (OP-01).

The host writes each game to `runs/games/<game_id>.jsonl` as it goes (slice 4), and
`--resume FILE` plays such a file again, checks each recorded hash, and goes on with it.
"""

from __future__ import annotations

import asyncio
import webbrowser
from pathlib import Path
from typing import Any

from slcli.play import build_engine, make_agent
from slhost import savegame
from slhost.server import DEFAULT_HOST, DEFAULT_PORT, Host, use_selector_loop

CLIENT_BUILD = Path("client") / "dist"


WATCHABLE_DELAY = 0.25


def read_resume(args: Any) -> dict[str, Any]:
    """With `--resume`, set the scenario, the seed, the board, the computer opponents, and
    the seats of the arguments from the header of the save file, and give the header. The
    two windows use it too."""
    header: dict[str, Any] = {}
    if getattr(args, "resume", None):
        header, _ = savegame.load(args.resume)
        args.scenario = str(header["scenario"])
        args.seed = int(header["seed"])
        args.board = header.get("board") or args.board
        if not args.agents and not args.agent and header.get("agents"):
            recorded = {int(seat): str(name) for seat, name in dict(header["agents"]).items()}
            if len(recorded) == 2:
                args.agents = f"{recorded[0]},{recorded[1]}"
            else:
                (seat, name), = recorded.items()
                args.agent = name
                args._agent_seat = seat
        if "hot_seat" in header:
            args.lan = not bool(header["hot_seat"])
    return header


def build_host(args: Any) -> Host:
    """The host the arguments name, with the game of the save file when there is one."""
    read_resume(args)
    engine = build_engine(args.scenario, args.board)
    root = Path(args.client) if args.client else CLIENT_BUILD
    agents = {}
    names: dict[str, str] = {}
    if args.agents:
        # The fourth play mode: computer against computer. Each seat goes to an agent, and
        # the browser is a watcher.
        listed = [name.strip() for name in args.agents.split(",")]
        if len(listed) != 2:
            raise ValueError(f"--agents takes two names, and {args.agents!r} has {len(listed)}")
        for seat, name in enumerate(listed):
            agents[seat] = make_agent(name, engine, args.seed, seat)
            names[str(seat)] = name
    elif args.agent:
        seat = getattr(args, "_agent_seat", None)
        if seat is None:
            seat = engine.scenario.side_index(args.agent_side) if args.agent_side else 1
        agents[seat] = make_agent(args.agent, engine, args.seed, seat)
        names[str(seat)] = args.agent
    # A game that plays itself runs as fast as the socket takes it. That gives a result and
    # shows no game, so a person who watches gets a pause between two commands.
    agent_delay = args.agent_delay
    if agent_delay is None:
        agent_delay = WATCHABLE_DELAY if args.agents else 0.0
    save_dir = None if (args.no_save or getattr(args, "resume", None)) else Path(args.save_dir)
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
        odds=not args.no_odds,
        auto_forced=not args.no_auto_forced,
        save_dir=save_dir,
        save_header={"board": args.board, "agents": names},
    )
    if getattr(args, "resume", None):
        count = host.resume_from(args.resume)
        print(f"resumed {args.resume}: {count} commands, each hash the same as the record")
    return host


def run(args: Any) -> int:
    use_selector_loop()
    host = build_host(args)
    engine = host.engine
    agents = host.agents
    url = f"http://{args.address}:{args.port}/?room={host.room.code}"
    print(f"scenario {engine.scenario.id} on board {engine.board.name}")
    for seat, agent in agents.items():
        print(f"player {seat} ({engine.scenario.players()[seat]}) is the scripted agent {agent.name} v{agent.version}")
    if agents and len(agents) == 2:
        print(f"the two computer opponents play by themselves, {host.agent_delay} s between commands")
    if host.game.save is not None:
        print(f"the game is saved to {host.game.save.path}")
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
    p.add_argument("--agent", default=None, help="give one side to a computer opponent (FR-39)")
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
    p.add_argument("--no-odds", action="store_true", help="do not give the odds with each legal command")
    p.add_argument(
        "--no-auto-forced",
        action="store_true",
        help="do not apply a command for a person when the frame has only that one",
    )
    p.add_argument(
        "--save-dir",
        default=str(savegame.DEFAULT_DIRECTORY),
        help="the directory of the save files; each game is <game_id>.jsonl",
    )
    p.add_argument("--no-save", action="store_true", help="do not write a save file")
    p.add_argument(
        "--resume",
        default=None,
        help="a save file: play its commands again, check each hash, and go on with the game",
    )
    p.set_defaults(func=run)
