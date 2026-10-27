"""The collector: an HTTP server that keeps the games that people played.

    sl-cli collect serve --data DIR --keys collect_keys.key.txt --port 5170

For each `POST /v1/games` the collector checks the key, the time, the nonce, and the MAC
(`wire`), plays the game again (`verify`), and writes it:

    DIR/games/<game_id>.jsonl        a game whose replay gives each recorded hash
    DIR/unverified/<game_id>.jsonl   a game whose replay does not (another package version)
    DIR/index.jsonl                  one line for each kept upload

A game that a player resumed comes again with more lines. The collector keeps the longer
file when the older one is the start of it. The key store is read again when its file
changes, so a new key needs no restart.

The server is plain HTTP. On a LAN the MAC is sufficient, because a game has no secret. An
Internet collector must have TLS in front of it (a reverse proxy), so that the key name and
the address of a player do not go on the network in clear text.
"""

from __future__ import annotations

import hmac
import json
import os
import re
import threading
import time
from collections import deque
from dataclasses import asdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from slcollect import keys as keystore
from slcollect import wire
from slcollect.verify import GameRejected, Verifier

DEFAULT_PORT = 5170
# The uploads of one key in `RATE_WINDOW` seconds.
RATE_LIMIT = 30
RATE_WINDOW = 60.0
# The replays at one time. A replay of a long game takes seconds of processor time.
REPLAYS_AT_ONCE = 2
GAME_ID = re.compile(r"^[A-Za-z0-9_.-]{1,160}$")


class Collector:
    """The state of the server: the keys, the nonces, the rates, and the data directory."""

    def __init__(self, data: Path, key_store: Path, scenarios: frozenset[str], log=print) -> None:
        self.data = Path(data)
        self.key_store = Path(key_store)
        self.verifier = Verifier(scenarios)
        self.log = log
        self._keys: dict[str, dict[str, Any]] = {}
        self._keys_mtime: float | None = None
        self._nonces: dict[str, float] = {}
        self._rates: dict[str, deque[float]] = {}
        self._lock = threading.Lock()
        self._store_lock = threading.Lock()
        self._replays = threading.BoundedSemaphore(REPLAYS_AT_ONCE)
        for part in ("games", "unverified"):
            (self.data / part).mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ the key

    def _secret(self, name: str) -> bytes | None:
        with self._lock:
            try:
                mtime = self.key_store.stat().st_mtime
            except OSError:
                mtime = None
            if mtime != self._keys_mtime:
                self._keys = keystore.load_store(self.key_store) if mtime is not None else {}
                self._keys_mtime = mtime
            return keystore.active_secret(self._keys, name)

    def authenticate(self, headers: Any, body: bytes, now: float | None = None) -> str:
        """The key name of a request whose MAC, time, and nonce are good, or a `PermissionError`."""
        now = time.time() if now is None else now
        name = headers.get(wire.HEADER_KEY)
        stamp = headers.get(wire.HEADER_TIME) or ""
        nonce = headers.get(wire.HEADER_NONCE) or ""
        mac = headers.get(wire.HEADER_MAC) or ""
        if not wire.valid_key_name(name):
            raise PermissionError("no key name")
        if not stamp.isdigit() or abs(int(stamp) - now) > wire.SKEW_SECONDS:
            raise PermissionError("the time of the request is not near the time of the collector")
        if not re.fullmatch(r"[0-9a-f]{32}", nonce):
            raise PermissionError("no nonce")
        secret = self._secret(name)
        if secret is None:
            raise PermissionError("the key is not known or it is revoked")
        expected = wire.mac_of(secret, "POST", wire.PATH_GAMES, stamp, nonce, body)
        if not hmac.compare_digest(expected, mac):
            raise PermissionError("the MAC is not correct")
        with self._lock:
            for old in [n for n, t in self._nonces.items() if now - t > 2 * wire.SKEW_SECONDS]:
                del self._nonces[old]
            if nonce in self._nonces:
                raise PermissionError("the nonce was used before")
            self._nonces[nonce] = now
            sent = self._rates.setdefault(name, deque())
            while sent and now - sent[0] > RATE_WINDOW:
                sent.popleft()
            if len(sent) >= RATE_LIMIT:
                raise OverflowError(f"more than {RATE_LIMIT} uploads in {int(RATE_WINDOW)} s")
            sent.append(now)
        return name

    # ---------------------------------------------------------------- the game

    def accept(self, name: str, body: bytes, address: str = "") -> tuple[int, dict[str, Any]]:
        """Check and keep one upload. Gives the HTTP status and the answer."""
        try:
            package, game = wire.decode_upload(body)
        except wire.WireError as exc:
            return HTTPStatus.BAD_REQUEST, {"error": str(exc)}
        header = game[0]
        game_id = str(header.get("game_id", "")) if isinstance(header, dict) else ""
        if not GAME_ID.match(game_id):
            return HTTPStatus.BAD_REQUEST, {"error": "the game has no valid game_id"}
        with self._replays:
            try:
                result = self.verifier.check(game)
            except GameRejected as exc:
                return HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)}
        folder = "games" if result.verified else "unverified"
        with self._store_lock:
            status, answer = self._store(folder, game_id, game)
            if status == HTTPStatus.OK and answer.get("stored"):
                record = {
                    "received": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "key": name,
                    "address": address,
                    "package": package,
                    "folder": folder,
                    **asdict(result),
                }
                with (self.data / "index.jsonl").open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(record, sort_keys=True) + "\n")
        answer.update({"verified": result.verified, "game_over": result.game_over, "reason": result.reason})
        self.log(
            f"upload {game_id} from {name}: {result.commands} commands, {result.human_commands} of a person, "
            f"{'verified' if result.verified else 'not verified: ' + result.reason}, {answer.get('note', 'kept')}"
        )
        return status, answer

    def _store(self, folder: str, game_id: str, game: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
        text = "".join(json.dumps(line, sort_keys=True, separators=(",", ":")) + "\n" for line in game)
        path = self.data / folder / f"{game_id}.jsonl"
        for other in ("games", "unverified"):
            old_path = self.data / other / f"{game_id}.jsonl"
            if not old_path.exists():
                continue
            old = old_path.read_text(encoding="utf-8")
            if old == text:
                return HTTPStatus.OK, {"stored": False, "game_id": game_id, "note": "the collector has this game"}
            if not text.startswith(old) or len(text) <= len(old):
                return HTTPStatus.CONFLICT, {"stored": False, "game_id": game_id, "error": "the collector has another game with this game_id"}
            old_path.unlink()
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        os.replace(temporary, path)
        return HTTPStatus.OK, {"stored": True, "game_id": game_id}


class Handler(BaseHTTPRequestHandler):
    server_version = "sl-collect/1"
    collector: Collector  # set on the class that `make_server` makes

    def _answer(self, status: int, data: dict[str, Any]) -> None:
        body = json.dumps(data, sort_keys=True).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - the name the standard library calls
        if self.path == wire.PATH_PING:
            self._answer(HTTPStatus.OK, {"service": wire.SERVICE, "protocol": wire.PROTOCOL})
        else:
            self._answer(HTTPStatus.NOT_FOUND, {"error": "no such path"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != wire.PATH_GAMES:
            self._answer(HTTPStatus.NOT_FOUND, {"error": "no such path"})
            return
        try:
            length = int(self.headers.get("Content-Length", ""))
        except ValueError:
            self._answer(HTTPStatus.LENGTH_REQUIRED, {"error": "no Content-Length"})
            return
        if length <= 0 or length > wire.MAX_BODY:
            self._answer(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": f"a body is 1 to {wire.MAX_BODY} bytes"})
            return
        body = self.rfile.read(length)
        try:
            name = self.collector.authenticate(self.headers, body)
        except PermissionError as exc:
            self._answer(HTTPStatus.UNAUTHORIZED, {"error": str(exc)})
            return
        except OverflowError as exc:
            self._answer(HTTPStatus.TOO_MANY_REQUESTS, {"error": str(exc)})
            return
        try:
            status, answer = self.collector.accept(name, body, self.client_address[0])
        except Exception as exc:  # a defect must not stop the server; the player sends again later
            self.collector.log(f"upload from {name} failed: {exc!r}")
            status, answer = HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "the collector could not keep the game"}
        self._answer(status, answer)

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002 - the standard library name
        self.collector.log(f"{self.client_address[0]} {format % args}")


def scenario_names() -> frozenset[str]:
    """The scenarios that the package can play: each scenario file of `sldata`."""
    from importlib import resources

    folder = resources.files("sldata").joinpath("scenarios")
    return frozenset(p.name[: -len(".json")] for p in folder.iterdir() if p.name.endswith(".json"))


def make_server(data: Path, key_store: Path, bind: str = "0.0.0.0", port: int = DEFAULT_PORT, log=print) -> ThreadingHTTPServer:
    collector = Collector(data, key_store, scenario_names(), log)
    handler = type("BoundHandler", (Handler,), {"collector": collector})
    server = ThreadingHTTPServer((bind, port), handler)
    server.daemon_threads = True
    return server
