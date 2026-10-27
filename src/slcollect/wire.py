"""The upload request between the packaged game and the collector.

    POST /v1/games
    X-SL-Key:   the name of the player's key
    X-SL-Time:  the time of the request, in whole seconds since 1970 (UTC)
    X-SL-Nonce: 32 random hex digits
    X-SL-Mac:   HMAC-SHA256 with the key of "POST\\n/v1/games\\n<time>\\n<nonce>\\n<SHA-256 of the body>"
    body:       {"package": <version>, "game": [<header>, <command line>, ...]}

    GET /v1/ping   gives {"service": SERVICE, "protocol": PROTOCOL}, with no key.

The key never goes on the wire. The time and the nonce stop a second send of a request that
was seen: the collector refuses a time more than `SKEW_SECONDS` from its clock and a nonce
that it has in its memory. The MAC covers the hash of the body, so a change of one byte of
the game makes the request false.

The game lines are the lines of the save file (`slhost.savegame`), the header first.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from typing import Any

SERVICE = "squad-leader-collector"
PROTOCOL = 1
PATH_GAMES = "/v1/games"
PATH_PING = "/v1/ping"
HEADER_KEY = "X-SL-Key"
HEADER_TIME = "X-SL-Time"
HEADER_NONCE = "X-SL-Nonce"
HEADER_MAC = "X-SL-Mac"
# The largest body that the collector reads. A long game of four boards is about 1 MB.
MAX_BODY = 8 * 1024 * 1024
# The largest count of command lines in one game.
MAX_LINES = 50_000
SKEW_SECONDS = 600
KEY_NAME_CHARS = frozenset("abcdefghijklmnopqrstuvwxyz0123456789-_.")
MAX_KEY_NAME = 64


class WireError(ValueError):
    """A request or an answer that does not agree with the protocol."""


def valid_key_name(name: Any) -> bool:
    return isinstance(name, str) and 0 < len(name) <= MAX_KEY_NAME and set(name) <= KEY_NAME_CHARS


def body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def message(method: str, path: str, stamp: str, nonce: str, body: bytes) -> bytes:
    return "\n".join((method, path, stamp, nonce, body_hash(body))).encode("ascii")


def mac_of(secret: bytes, method: str, path: str, stamp: str, nonce: str, body: bytes) -> str:
    return hmac.new(secret, message(method, path, stamp, nonce, body), hashlib.sha256).hexdigest()


def signed_headers(name: str, secret: bytes, body: bytes, now: float | None = None) -> dict[str, str]:
    """The headers of a POST of `body` to `PATH_GAMES` with this key."""
    stamp = str(int(time.time() if now is None else now))
    nonce = secrets.token_hex(16)
    return {
        HEADER_KEY: name,
        HEADER_TIME: stamp,
        HEADER_NONCE: nonce,
        HEADER_MAC: mac_of(secret, "POST", PATH_GAMES, stamp, nonce, body),
        "Content-Type": "application/json",
    }


def encode_upload(lines: list[dict[str, Any]], package: str) -> bytes:
    return json.dumps({"package": package, "game": lines}, sort_keys=True, separators=(",", ":")).encode("utf-8")


def decode_upload(body: bytes) -> tuple[str, list[dict[str, Any]]]:
    """The package version and the game lines of an upload body. Each error is a `WireError`."""
    try:
        data = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise WireError(f"the body is not JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise WireError("the body is not an object")
    package = data.get("package")
    game = data.get("game")
    if not isinstance(package, str) or len(package) > 64:
        raise WireError("the body has no package version")
    if not isinstance(game, list) or not game:
        raise WireError("the body has no game lines")
    if len(game) > MAX_LINES + 1:
        raise WireError(f"the game has more than {MAX_LINES} command lines")
    if not all(isinstance(line, dict) for line in game):
        raise WireError("a game line is not an object")
    return package, game
