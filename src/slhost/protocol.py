"""The host protocol (ARCHITECTURE section 8).

The client sends `join`, `intent`, `view_request`, and `los_request`. The host sends
`welcome`, `frame`, `error`, `los_result`, and `game_over`. Each message is one JSON
object with a `type` field.

The client sends intents only. It never sends a state hash (DR-04). The `intent`
message carries the frame ID that the host issued, so a stale client is refused.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

CLIENT_JOIN = "join"
CLIENT_INTENT = "intent"
CLIENT_VIEW_REQUEST = "view_request"
CLIENT_LOS_REQUEST = "los_request"
CLIENT_MESSAGES = (CLIENT_JOIN, CLIENT_INTENT, CLIENT_VIEW_REQUEST, CLIENT_LOS_REQUEST)

HOST_WELCOME = "welcome"
HOST_FRAME = "frame"
HOST_ERROR = "error"
HOST_LOS_RESULT = "los_result"
HOST_GAME_OVER = "game_over"

MAX_MESSAGE_BYTES = 64 * 1024


class ProtocolError(Exception):
    """A message from a client is not valid. The host answers with an error and stays up."""

    def __init__(self, rule_id: str, message: str) -> None:
        super().__init__(message)
        self.rule_id = rule_id
        self.message = message


@dataclass(frozen=True)
class ClientMessage:
    type: str
    data: dict[str, Any]

    def require(self, key: str) -> Any:
        if key not in self.data:
            raise ProtocolError("protocol", f"the {self.type} message needs a {key} field")
        return self.data[key]


def parse(raw: str | bytes) -> ClientMessage:
    """Parse one client message. This is a trust boundary, so every error is typed."""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    if len(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("protocol", f"a message may not be longer than {MAX_MESSAGE_BYTES} bytes")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError("protocol", f"the message is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ProtocolError("protocol", "a message must be a JSON object")
    kind = data.get("type")
    if kind not in CLIENT_MESSAGES:
        raise ProtocolError("protocol", f"unknown message type {kind!r}")
    return ClientMessage(str(kind), data)


def dump(message: dict[str, Any]) -> str:
    return json.dumps(message, separators=(",", ":"))


def welcome(player: int, seat: str, board: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    return {"type": HOST_WELCOME, "player": player, "seat": seat, "board": board, "scenario": scenario}


def frame_message(
    player: int,
    view: dict[str, Any],
    frame: dict[str, Any],
    log_tail: list[dict[str, Any]],
    fire_preview: dict[str, Any] | None = None,
    log_from: int | None = None,
) -> dict[str, Any]:
    """One frame for one player. `fire_preview` is the odds of the fire group that this
    player builds now; the host gives it only to that player (AR-09). `log_from` is the
    number in the whole log of the first entry of `log_tail`, so a client that keeps the
    log adds only the entries it does not have."""
    message = {
        "type": HOST_FRAME,
        "player": player,
        "view": view,
        "frame_id": frame["frame_id"],
        "active": frame["player"],
        "phase": frame["phase"],
        "sub_step": frame["sub_step"],
        "turn": frame["turn"],
        "legal_commands": frame["commands"],
        "log_tail": log_tail,
    }
    if fire_preview is not None:
        message["fire_preview"] = fire_preview
    if log_from is not None:
        message["log_from"] = int(log_from)
    return message


def error_message(rule_id: str, message: str) -> dict[str, Any]:
    return {"type": HOST_ERROR, "rule_id": rule_id, "message": message}


def los_result_message(from_hex: str, to_hex: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"type": HOST_LOS_RESULT, "from": from_hex, "to": to_hex, "result": result}


def game_over_message(result: str, cause: str) -> dict[str, Any]:
    return {"type": HOST_GAME_OVER, "result": result, "cause": cause}
