"""`sl-cli farm`: the game farm (`slfarm`).

    sl-cli farm key --write farm.key.txt          a new key; copy the file to each host
    sl-cli farm serve --host 0.0.0.0 --slots 30   on each host
    sl-cli farm ping --remote tars,case,kipp,plex from the workstation

Then `sl-cli gauntlet` and `sl-cli evolve` take `--remote tars,case,kipp,plex`, and the hosts
play games of the run next to the local `--workers`.
"""

from __future__ import annotations

import asyncio
import os
from importlib import resources
from pathlib import Path
from typing import Any

from slfarm import protocol
from slfarm.client import parse_addresses, ping
from slfarm.server import FarmServer


def scenario_names() -> frozenset[str]:
    """The scenario ids of this tree: the files of `sldata/scenarios`."""
    folder = resources.files("sldata").joinpath("scenarios")
    return frozenset(entry.name[: -len(".json")] for entry in folder.iterdir() if entry.name.endswith(".json"))


def _env_main() -> Any:
    """The PPO worker loop when this host has the train extra (torch and numpy), else None:
    the server then plays game jobs only and refuses a PPO environment by name."""
    try:
        import numpy  # noqa: F401
        import torch  # noqa: F401
    except ImportError:
        return None
    from slagents.learned.workers import worker_main

    return worker_main


def _serve(args: Any) -> int:
    from slcli.gauntlet import _play_job

    key = protocol.read_key(args.key)
    server = FarmServer(key, _play_job, scenario_names(), args.slots, env_main=_env_main())
    try:
        asyncio.run(server.serve_forever(args.host, args.port))
    except KeyboardInterrupt:
        pass
    except OSError as exc:
        raise protocol.FarmError(f"cannot listen on {args.host}:{args.port}: {exc}") from exc
    finally:
        server.close()
    return 0


def _ping(args: Any) -> int:
    key = protocol.read_key(args.remote_key)
    rows = ping(parse_addresses(args.remote), key)
    print(f"this tree: code {protocol.code_hash()[:12]}")
    failed = 0
    for row in rows:
        if "error" in row:
            failed += 1
            print(f"  {row['address']:28s} ERROR {row['error']}")
        else:
            print(f"  {row['address']:28s} {row['slots']} slots, {row['busy']} busy, {row.get('envs', 0)} PPO workers, {row['seconds']} s")
    return 1 if failed else 0


def _key(args: Any) -> int:
    path = Path(args.write)
    if path.exists():
        raise protocol.FarmKeyError(f"{path} exists; remove it first, or keep it")
    if not path.name.endswith(".key.txt"):
        raise protocol.FarmKeyError(f"a key file name ends in .key.txt, so git does not record it; not {path.name}")
    path.write_text(protocol.new_key() + "\n", encoding="utf-8")
    print(f"wrote a new farm key to {path}; copy it to each host and keep it out of logs")
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("farm", help="the game farm: remote hosts that play games of a gauntlet or an evolution")
    sub = p.add_subparsers(dest="farm_command", required=True)

    serve = sub.add_parser("serve", help="play the games that an authenticated client sends")
    serve.add_argument("--host", default="127.0.0.1", help="the address to listen on; 0.0.0.0 for the LAN")
    serve.add_argument("--port", type=int, default=protocol.DEFAULT_PORT)
    serve.add_argument("--slots", type=int, default=max(1, (os.cpu_count() or 2) - 2), help="the worker processes that play games")
    serve.add_argument("--key", default="farm.key.txt", help="the file with the farm key")
    serve.set_defaults(func=_serve)

    check = sub.add_parser("ping", help="connect to each host and print its slots")
    check.add_argument("--remote", required=True, help="the hosts, as tars,case:5160")
    check.add_argument("--remote-key", default="farm.key.txt", help="the file with the farm key")
    check.set_defaults(func=_ping)

    key = sub.add_parser("key", help="write a new farm key file")
    key.add_argument("--write", default="farm.key.txt", help="the new key file, a name that ends in .key.txt")
    key.set_defaults(func=_key)
