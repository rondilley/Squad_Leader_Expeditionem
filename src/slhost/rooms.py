"""Room codes and player slots (SR-03).

A room code has 128 bits of entropy from `secrets`. The host gives the slots itself, so
a client cannot name the side it wants. Hot seat has one client that holds both seats.

This is convenience for a trusted party on a trusted network. It is not a guarantee
against a hostile machine on the same network, and `docs/REQUIREMENTS.md` says so.
"""

from __future__ import annotations

import hmac
import secrets
import time
from dataclasses import dataclass, field

from slhost.protocol import SEAT_HOT_SEAT, SEAT_PLAYER, SEAT_WATCHER  # noqa: F401 (the seat kinds have one source)

CODE_BITS = 128
CODE_BYTES = CODE_BITS // 8

DEFAULT_MAX_TRIES = 10
DEFAULT_WINDOW_SECONDS = 60.0
# The table of join tries drops the addresses with no try in the window when it is this long.
PRUNE_AT = 256


def new_room_code() -> str:
    """A join credential with 128 bits of entropy (SR-03)."""
    return secrets.token_hex(CODE_BYTES)


def code_matches(expected: str, given: str) -> bool:
    """A comparison whose time does not depend on how much of the code is correct.

    The comparison is on bytes (S14). `hmac.compare_digest` refuses a text that is not
    ASCII, and a join with such a code closed the socket with an internal error.
    """
    if not isinstance(given, str):
        return False
    return hmac.compare_digest(
        expected.encode("utf-8", errors="replace"), given.encode("utf-8", errors="replace")
    )


def new_seat_token() -> str:
    """The credential of one seat (S9). A reconnect with it gets the same seat back."""
    return secrets.token_hex(CODE_BYTES)


@dataclass
class Attempts:
    """A count of join tries for each address, so a wrong code cannot be searched."""

    max_tries: int = DEFAULT_MAX_TRIES
    window_seconds: float = DEFAULT_WINDOW_SECONDS
    _hits: dict[str, list[float]] = field(default_factory=dict)

    def allow(self, address: str, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        if len(self._hits) >= PRUNE_AT:
            self.prune(moment)
        hits = [t for t in self._hits.get(address, []) if moment - t < self.window_seconds]
        hits.append(moment)
        self._hits[address] = hits
        return len(hits) <= self.max_tries

    def prune(self, now: float) -> None:
        """Remove each address whose tries are all out of the window (S15)."""
        for address in [a for a, hits in self._hits.items() if not hits or now - hits[-1] >= self.window_seconds]:
            del self._hits[address]

    def reset(self, address: str) -> None:
        self._hits.pop(address, None)


@dataclass
class RateLimit:
    """A count of requests of one connection in a moving window (S15)."""

    max_requests: int
    window_seconds: float
    _hits: list[float] = field(default_factory=list)

    def allow(self, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        self._hits = [t for t in self._hits if moment - t < self.window_seconds]
        if len(self._hits) >= self.max_requests:
            return False
        self._hits.append(moment)
        return True


@dataclass
class Room:
    """One game. In hot seat one client holds the two seats.

    A seat has a token (S9). The first join that takes a seat gets the token, and a join
    with the token gets the same seat back. A seat whose connection dropped stays
    reserved for its token, so the other player cannot take it with the room code.
    A seat that a computer opponent holds is never given to a client (S8).
    """

    code: str
    hot_seat: bool = True
    seats: dict[int, str] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)
    tokens: dict[int, str] = field(default_factory=dict)
    computer_seats: frozenset[int] = frozenset()
    watchers_only: bool = False

    def open_seat(self) -> int | None:
        """The next seat to give, or None when the room is full.

        A seat with a token is not open, also when no connection holds it now.
        """
        if self.watchers_only:
            return None
        if self.hot_seat:
            return 0 if 0 not in self.seats and 0 not in self.tokens else None
        for player in (0, 1):
            if player in self.computer_seats:
                continue
            if player not in self.seats and player not in self.tokens:
                return player
        return None

    def seat_of_token(self, token: str) -> int | None:
        """The seat this token holds, or None. The comparison is on bytes."""
        for player, held in self.tokens.items():
            if code_matches(held, token):
                return player
        return None

    def take(self, connection_id: str, display_name: str, token: str | None = None) -> tuple[int, str]:
        """Give a seat. With the token of a seat, give that seat back to this connection."""
        kind = SEAT_HOT_SEAT if self.hot_seat else SEAT_PLAYER
        if token:
            player = self.seat_of_token(token)
            if player is not None:
                self.seats[player] = connection_id
                self.names[player] = display_name
                return player, kind
        player = self.open_seat()
        if player is None:
            return -1, SEAT_WATCHER
        self.seats[player] = connection_id
        self.names[player] = display_name
        self.tokens[player] = new_seat_token()
        return player, kind

    def token_of(self, player: int) -> str | None:
        return self.tokens.get(player)

    def holder(self, player: int) -> str | None:
        return self.seats.get(player)

    def release(self, connection_id: str) -> None:
        """The connection is gone. Its seat stays reserved for the token of the seat."""
        for player, held in list(self.seats.items()):
            if held == connection_id:
                del self.seats[player]
                self.names.pop(player, None)

    def controls(self, connection_id: str, player: int) -> bool:
        """In hot seat one client acts for the two sides. In LAN a client acts for its seat."""
        if self.hot_seat:
            return connection_id in self.seats.values()
        return self.seats.get(player) == connection_id


def origin_allowed(origin: str | None, allowed: tuple[str, ...], bound: str | None = None) -> bool:
    """The host examines the WebSocket origin (SR-03).

    A message with no origin comes from a tool, not from a browser, and the room code is
    its credential. `bound` is the address the server bound, in the form `host:port`.
    It is not the Host header from the client. A browser origin is valid on the
    `--origin` list, or when it is that bound address. Any other origin is refused.
    """
    if origin is None:
        return True
    if origin in allowed:
        return True
    if bound:
        return origin in (f"http://{bound}", f"https://{bound}")
    return False
