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

CODE_BITS = 128
CODE_BYTES = CODE_BITS // 8
SEAT_HOT_SEAT = "hot_seat"
SEAT_PLAYER = "player"
SEAT_WATCHER = "watcher"

DEFAULT_MAX_TRIES = 10
DEFAULT_WINDOW_SECONDS = 60.0


def new_room_code() -> str:
    """A join credential with 128 bits of entropy (SR-03)."""
    return secrets.token_hex(CODE_BYTES)


def code_matches(expected: str, given: str) -> bool:
    """A comparison whose time does not depend on how much of the code is correct."""
    return hmac.compare_digest(expected, given)


@dataclass
class Attempts:
    """A count of join tries for each address, so a wrong code cannot be searched."""

    max_tries: int = DEFAULT_MAX_TRIES
    window_seconds: float = DEFAULT_WINDOW_SECONDS
    _hits: dict[str, list[float]] = field(default_factory=dict)

    def allow(self, address: str, now: float | None = None) -> bool:
        moment = time.monotonic() if now is None else now
        hits = [t for t in self._hits.get(address, []) if moment - t < self.window_seconds]
        hits.append(moment)
        self._hits[address] = hits
        return len(hits) <= self.max_tries

    def reset(self, address: str) -> None:
        self._hits.pop(address, None)


@dataclass
class Room:
    """One game. In hot seat one client holds the two seats."""

    code: str
    hot_seat: bool = True
    seats: dict[int, str] = field(default_factory=dict)
    names: dict[int, str] = field(default_factory=dict)

    def open_seat(self) -> int | None:
        """The next seat to give, or None when the room is full."""
        if self.hot_seat:
            return 0 if 0 not in self.seats else None
        for player in (0, 1):
            if player not in self.seats:
                return player
        return None

    def take(self, connection_id: str, display_name: str) -> tuple[int, str]:
        player = self.open_seat()
        if player is None:
            return -1, SEAT_WATCHER
        self.seats[player] = connection_id
        self.names[player] = display_name
        return player, SEAT_HOT_SEAT if self.hot_seat else SEAT_PLAYER

    def release(self, connection_id: str) -> None:
        for player, held in list(self.seats.items()):
            if held == connection_id:
                del self.seats[player]
                self.names.pop(player, None)

    def controls(self, connection_id: str, player: int) -> bool:
        """In hot seat one client acts for the two sides. In LAN a client acts for its seat."""
        if self.hot_seat:
            return connection_id in self.seats.values()
        return self.seats.get(player) == connection_id


def origin_allowed(origin: str | None, allowed: tuple[str, ...], host_header: str | None = None) -> bool:
    """The host examines the WebSocket origin (SR-03).

    A message with no origin comes from a tool, not from a browser, and the room code is
    its credential. A browser page that the host itself served has the same origin as
    the host, and it is allowed. Any other origin needs the `--origin` option.
    """
    if origin is None:
        return True
    if origin in allowed:
        return True
    if host_header:
        return origin in (f"http://{host_header}", f"https://{host_header}")
    return False
