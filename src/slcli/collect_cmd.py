"""`sl-cli collect`: the collection of the games that people played (`slcollect`).

    sl-cli collect key add NAME          a key for one player; gives the player file
    sl-cli collect key revoke NAME       the collector refuses that key from now on
    sl-cli collect key list
    sl-cli collect serve --data DIR      the collector (on tars.uberadmin.com at first)
    sl-cli collect send                  send the saved games of this computer now
    sl-cli collect status --data DIR     the counts of the kept games

The key store is `collect_keys.key.txt` (the name keeps it out of the tree). Give the player
file (`collect.key.txt`) to the player, who puts it next to the game program or in the data
directory of the game.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from slcollect import keys as keystore
from slcollect import settings as player_settings

DEFAULT_STORE = "collect_keys.key.txt"


def _key(args: Any) -> int:
    store = Path(args.keys)
    if args.key_action in ("add", "revoke") and not args.name:
        raise ValueError(f"sl-cli collect key {args.key_action} needs the name of the key")
    if args.key_action == "add":
        key = keystore.add_key(store, args.name)
        out = Path(args.out) if args.out else Path("collect_players") / args.name / keystore.PLAYER_FILE
        keystore.write_player_file(out, key)
        print(f"the key {key.name} is in {store}")
        print(f"give the player the file {out}; it goes next to the game program or in the data directory of the game")
        print("copy the key store to the collector again, or run the collector on this store")
        return 0
    if args.key_action == "revoke":
        keystore.revoke_key(store, args.name)
        print(f"the key {args.name} is revoked in {store}; the collector refuses it when it reads the store again")
        return 0
    for name, entry in sorted(keystore.load_store(store).items()):
        state = "revoked" if entry.get("revoked") else "active"
        print(f"{name:24s} {state:8s} created {entry.get('created', '')}")
    return 0


def _serve(args: Any) -> int:
    from slcollect.server import make_server

    server = make_server(Path(args.data), Path(args.keys), args.bind, args.port)
    print(f"the collector listens on {args.bind}:{args.port}, data in {args.data}, keys in {args.keys}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


def _send(args: Any) -> int:
    from slcollect.client import send_pending

    found = Path(args.key) if args.key else player_settings.key_file()
    if found is None:
        print(f"no key file: put {keystore.PLAYER_FILE} in {player_settings.data_dir()} or give --key")
        return 1
    key = keystore.read_player_file(found)
    url = args.url or player_settings.collector_url(player_settings.load_settings())
    save_dir = Path(args.save_dir) if args.save_dir else player_settings.games_dir()
    report = send_pending(save_dir, url, key, player_settings.data_dir() / "sent.json", player_settings.package_version(), quiet_seconds=args.quiet)
    print(f"{url}: {report.text()}")
    for line in report.refused + report.errors:
        print(f"  {line}")
    return 0 if not report.stopped else 1


def _status(args: Any) -> int:
    index = Path(args.data) / "index.jsonl"
    rows = []
    if index.exists():
        rows = [json.loads(line) for line in index.read_text(encoding="utf-8").splitlines() if line.strip()]
    by_key = Counter(r["key"] for r in rows)
    by_scenario = Counter(r["scenario"] for r in rows)
    verified = sum(1 for r in rows if r.get("verified"))
    print(f"{len(rows)} uploads kept, {verified} verified, {sum(r.get('human_commands', 0) for r in rows)} decisions of a person")
    for name, n in sorted(by_key.items()):
        print(f"  key {name:24s} {n}")
    for name, n in sorted(by_scenario.items()):
        print(f"  scenario {name:28s} {n}")
    return 0


def run(args: Any) -> int:
    return {"key": _key, "serve": _serve, "send": _send, "status": _status}[args.collect_command](args)


def add_parser(subparsers: Any) -> None:
    from slcollect.server import DEFAULT_PORT

    p = subparsers.add_parser("collect", help="the collection of the games that people played, for the training")
    sub = p.add_subparsers(dest="collect_command", required=True)
    k = sub.add_parser("key", help="the keys of the players")
    k.add_argument("key_action", choices=("add", "revoke", "list"))
    k.add_argument("name", nargs="?", default="")
    k.add_argument("--keys", default=DEFAULT_STORE, help="the key store")
    k.add_argument("--out", default=None, help="the player file (default collect_players/NAME/collect.key.txt)")
    s = sub.add_parser("serve", help="run the collector")
    s.add_argument("--data", default="collected", help="the directory of the kept games")
    s.add_argument("--keys", default=DEFAULT_STORE)
    s.add_argument("--bind", default="0.0.0.0")
    s.add_argument("--port", type=int, default=DEFAULT_PORT)
    u = sub.add_parser("send", help="send the saved games of this computer to the collector")
    u.add_argument("--url", default=None)
    u.add_argument("--key", default=None, help="the player key file")
    u.add_argument("--save-dir", default=None, help="the save directory (default: the data directory of the game)")
    u.add_argument("--quiet", type=float, default=30.0, help="skip a file that changed in the last seconds")
    t = sub.add_parser("status", help="the counts of the kept games")
    t.add_argument("--data", default="collected")
    p.set_defaults(func=run)
