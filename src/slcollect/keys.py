"""The keys of the players: one store on the collector, one file for each player.

The store is a JSON file with the secret of each key, because the collector must make the
same HMAC. Its name ends in `.key.txt` (`collect_keys.key.txt`), so it is not recorded in the
tree. A player file is one line, `<name> <secret in hex>`, as `collect.key.txt` next to the
game or in the player's data directory.

A key that is revoked stays in the store, so the index of the games keeps its name.
"""

from __future__ import annotations

import json
import os
import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slcollect.wire import valid_key_name

STORE_FORMAT = "sl-collect-keys"
PLAYER_FILE = "collect.key.txt"


class KeyStoreError(ValueError):
    """A key store or a key file that cannot be read, or a key that is not valid."""


@dataclass(frozen=True)
class PlayerKey:
    name: str
    secret: bytes


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def load_store(path: str | Path) -> dict[str, dict[str, Any]]:
    """The keys of the store by name. A store that does not exist has no key."""
    source = Path(path)
    if not source.exists():
        return {}
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KeyStoreError(f"cannot read the key store {source}: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != STORE_FORMAT or not isinstance(data.get("keys"), dict):
        raise KeyStoreError(f"{source} is not a {STORE_FORMAT} store")
    return data["keys"]


def _write_store(path: Path, keys: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps({"format": STORE_FORMAT, "keys": keys}, indent=1, sort_keys=True), encoding="utf-8")
    os.replace(temporary, path)


def add_key(path: str | Path, name: str) -> PlayerKey:
    """A new key in the store. A name that is in the store already is an error."""
    if not valid_key_name(name):
        raise KeyStoreError(f"a key name has 1 to 64 of the characters a-z 0-9 - _ . and not {name!r}")
    store = Path(path)
    keys = load_store(store)
    if name in keys:
        raise KeyStoreError(f"the store has a key {name!r} already")
    secret = secrets.token_hex(32)
    keys[name] = {"secret": secret, "created": _now(), "revoked": False}
    _write_store(store, keys)
    return PlayerKey(name, bytes.fromhex(secret))


def revoke_key(path: str | Path, name: str) -> None:
    store = Path(path)
    keys = load_store(store)
    if name not in keys:
        raise KeyStoreError(f"the store has no key {name!r}")
    keys[name]["revoked"] = True
    keys[name]["revoked_at"] = _now()
    _write_store(store, keys)


def active_secret(keys: dict[str, dict[str, Any]], name: str) -> bytes | None:
    """The secret of a key that is in the store and not revoked, or None."""
    entry = keys.get(name)
    if not isinstance(entry, dict) or entry.get("revoked"):
        return None
    try:
        return bytes.fromhex(str(entry["secret"]))
    except (KeyError, ValueError):
        return None


def write_player_file(path: str | Path, key: PlayerKey) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(f"{key.name} {key.secret.hex()}\n", encoding="ascii")
    return target


def read_player_file(path: str | Path) -> PlayerKey:
    source = Path(path)
    try:
        first = source.read_text(encoding="ascii").strip().splitlines()[0]
    except (OSError, IndexError, UnicodeDecodeError) as exc:
        raise KeyStoreError(f"cannot read the key file {source}: {exc}") from exc
    parts = first.split()
    if len(parts) != 2 or not valid_key_name(parts[0]):
        raise KeyStoreError(f"the key file {source} is not one line '<name> <secret>'")
    try:
        secret = bytes.fromhex(parts[1])
    except ValueError as exc:
        raise KeyStoreError(f"the secret of the key file {source} is not hex") from exc
    if len(secret) < 16:
        raise KeyStoreError(f"the secret of the key file {source} is too short")
    return PlayerKey(parts[0], secret)
