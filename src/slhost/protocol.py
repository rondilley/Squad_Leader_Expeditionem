"""The host protocol, version 2 (ARCHITECTURE section 8).

The client sends `join`, `intent`, `view_request`, `los_request`, `undo`,
`auto_setup`, `setup_lift`, `options_request`, and `move_to`. The host sends `welcome`, `frame`,
`error`, `los_result`, `options_result`, and `game_over`.
Each message is one JSON object with a `type` field.

The client sends intents only. It never sends a state hash (DR-04), and it never gets
one (S1). The frame ID in a frame is an opaque token of 32 hex digits. The host makes a
new token for each connection and each new frame, and it keeps the map from the token to
the core frame. The token has no relation to the state hash. The client sends it back in
`intent.frame_id`, and the host refuses a token that is not the newest one it gave to
that connection (code `stale_frame`).

Version 2 of the messages:

- `welcome`: `player`, `seat`, `board`, `scenario`, `strict_los`, and `you` (the player
  index, or -1 for a watcher), `sides` ({"0": {"name", "controller"}, "1": ...}, where the
  controller is `human`, `computer`, or `remote`), and `seat_token` (32 hex digits) for a
  client that holds a player seat. A watcher gets no token.
- `join`: `room_code`, `display_name`, and an optional `seat_token`. A join with the
  token of a seat gets that seat back, and the host closes an old connection that still
  holds it. A seat whose connection dropped stays reserved for its token.
- `frame`: `player`, `view`, `frame_id`, `active`, `phase`, `sub_step`, `turn`,
  `legal_commands`, `log_tail`, and `status` (`your_turn`, `waiting`,
  `computer_thinking`, `game_over`), `auto_applied` (the labels of the commands the host
  applied for this person because the frame had one legal command), `can_undo`, and
  `phase_text` (a short project text for the phase), and `objectives` (`slhost.objectives`:
  the victory conditions, their hexes, and the status of the viewer's own conditions).
  Each legal entry has `id`, `action`, `payload`, `label`, `units` ([{"id", "name"}]),
  `hexes` (the hex names the command touches), and `odds` (when the host option is on and
  the actor can see the target). The odds are integers out of 1296.
- `log_tail`: the lines this connection has not had yet. The first frame of a connection
  holds the history of its viewer. `seq` counts the lines of one viewer with no gap, so a
  client merges by `seq` and keeps the whole history. Each line has `names` (unit ID to
  a unit name such as "4-4-7 #3 (D4)") and `sides` (player index to side name).
- `error`: `rule_id`, `message`, and `code` (see ERROR_CODES). A client does not connect
  again after a code in TERMINAL_CODES. `rate_limited` refuses a join or a connection;
  `request_limited` answers a question over the limit of a connection, and the session
  continues.
- `game_over`: `result` (the winner index or null), `winner_name`, `outcome` (the core
  result text), `cause`, `conditions`, `turn`, and `casualties` for each side.
- `undo`: no fields. The host takes back the last command of the person at the screen
  when that command rolled no die and showed no hidden information.
- `auto_setup`: no fields. The host sets up the side of the person with the v7 agent.
- `setup_lift`: `unit`. While the side of the person sets up, the host takes that placed
  unit off the board again, so the person can place it in a different hex. A weapon
  given to the unit comes off the board with it.
- `options_request`: `unit`, a unit of a side that the connection holds. The host answers
  with `options_result`: `unit`, `frame_id` (the token of the frame the answer is for),
  and `result` (`slhost.options`): in the set up the area and the reason that each
  refused hex of it gives, in the Movement Phase the hexes the unit can reach, and in a
  fire phase the hexes in its range with a clear line of sight.
- `move_to`: `frame_id`, `unit`, and `hex`. In the Movement Phase the host moves the unit
  (or the stack it moves with) to that hex by the cheapest path of `options_request`.
  Each step is a command of the legal list at that time, applied as an intent. The move
  stops at the first step that is not legal, and the host sends an error that says where.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

CLIENT_JOIN = "join"
CLIENT_INTENT = "intent"
CLIENT_VIEW_REQUEST = "view_request"
CLIENT_LOS_REQUEST = "los_request"
CLIENT_UNDO = "undo"
CLIENT_AUTO_SETUP = "auto_setup"
CLIENT_SETUP_LIFT = "setup_lift"
CLIENT_OPTIONS_REQUEST = "options_request"
CLIENT_MOVE_TO = "move_to"
CLIENT_MESSAGES = (
    CLIENT_JOIN,
    CLIENT_INTENT,
    CLIENT_VIEW_REQUEST,
    CLIENT_LOS_REQUEST,
    CLIENT_UNDO,
    CLIENT_AUTO_SETUP,
    CLIENT_SETUP_LIFT,
    CLIENT_OPTIONS_REQUEST,
    CLIENT_MOVE_TO,
)

HOST_WELCOME = "welcome"
HOST_FRAME = "frame"
HOST_ERROR = "error"
HOST_LOS_RESULT = "los_result"
HOST_OPTIONS_RESULT = "options_result"
HOST_GAME_OVER = "game_over"

STATUS_YOUR_TURN = "your_turn"
STATUS_WAITING = "waiting"
STATUS_COMPUTER = "computer_thinking"
STATUS_GAME_OVER = "game_over"

CODE_ROOM_CODE = "room_code"
CODE_ROOM_FULL = "room_full"
CODE_RATE_LIMITED = "rate_limited"
# Too many questions (a line of sight, the options of a unit, a view) from one connection in
# a short time. The session goes on: the client asks again a moment later. It is not
# `rate_limited`, which refuses a join or a connection and ends the session.
CODE_REQUEST_LIMITED = "request_limited"
CODE_ORIGIN = "origin"
CODE_SEAT = "seat"
CODE_ILLEGAL = "illegal"
CODE_STALE_FRAME = "stale_frame"
CODE_PROTOCOL = "protocol"
CODE_UNDO_REFUSED = "undo_refused"
CODE_INTERNAL = "internal"
ERROR_CODES = (
    CODE_ROOM_CODE,
    CODE_ROOM_FULL,
    CODE_RATE_LIMITED,
    CODE_REQUEST_LIMITED,
    CODE_ORIGIN,
    CODE_SEAT,
    CODE_ILLEGAL,
    CODE_STALE_FRAME,
    CODE_PROTOCOL,
    CODE_UNDO_REFUSED,
    CODE_INTERNAL,
)
# After one of these the host closes the socket, and a new try gets the same answer.
TERMINAL_CODES = (CODE_ROOM_CODE, CODE_RATE_LIMITED, CODE_ORIGIN, CODE_ROOM_FULL)

MAX_MESSAGE_BYTES = 64 * 1024

PROTOCOL_VERSION = 2

# The controller of a side in `welcome.sides`.
CONTROLLER_HUMAN = "human"
CONTROLLER_COMPUTER = "computer"
CONTROLLER_REMOTE = "remote"
CONTROLLERS = (CONTROLLER_HUMAN, CONTROLLER_COMPUTER, CONTROLLER_REMOTE)

# The two seat names in `welcome.seat` that a client reads. A player seat has the name of
# its side. `slhost.rooms` has the same values, and tests/arch compares them.
SEAT_HOT_SEAT = "hot_seat"
SEAT_PLAYER = "player"
SEAT_WATCHER = "watcher"
SEATS = (SEAT_HOT_SEAT, SEAT_PLAYER, SEAT_WATCHER)

HOST_MESSAGES = (HOST_WELCOME, HOST_FRAME, HOST_ERROR, HOST_LOS_RESULT, HOST_OPTIONS_RESULT, HOST_GAME_OVER)
STATUSES = (STATUS_YOUR_TURN, STATUS_WAITING, STATUS_COMPUTER, STATUS_GAME_OVER)

# The field names of each message: the fields a message always has, and the fields it can
# have. The builders below give these fields, and the client types have the same names.
# `tools/make_protocol_schema.py` writes this table and the lists above into the schema
# file that the client build reads.
CLIENT_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    CLIENT_JOIN: {"required": ("type", "room_code"), "optional": ("display_name", "seat_token")},
    CLIENT_INTENT: {"required": ("type", "frame_id", "command_id"), "optional": ()},
    CLIENT_VIEW_REQUEST: {"required": ("type",), "optional": ()},
    CLIENT_LOS_REQUEST: {"required": ("type", "from", "to"), "optional": ()},
    CLIENT_UNDO: {"required": ("type",), "optional": ()},
    CLIENT_AUTO_SETUP: {"required": ("type",), "optional": ()},
    CLIENT_SETUP_LIFT: {"required": ("type", "unit"), "optional": ()},
    CLIENT_OPTIONS_REQUEST: {"required": ("type", "unit"), "optional": ()},
    CLIENT_MOVE_TO: {"required": ("type", "frame_id", "unit", "hex"), "optional": ()},
}
HOST_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    HOST_WELCOME: {
        "required": ("type", "player", "you", "seat", "board", "scenario", "strict_los", "sides"),
        "optional": ("seat_token",),
    },
    HOST_FRAME: {
        "required": (
            "type",
            "player",
            "view",
            "frame_id",
            "active",
            "phase",
            "sub_step",
            "turn",
            "legal_commands",
            "log_tail",
            "status",
            "auto_applied",
            "can_undo",
            "phase_text",
        ),
        "optional": ("objectives",),
    },
    HOST_ERROR: {"required": ("type", "rule_id", "message", "code"), "optional": ()},
    HOST_LOS_RESULT: {"required": ("type", "from", "to", "result"), "optional": ()},
    HOST_OPTIONS_RESULT: {"required": ("type", "unit", "frame_id", "result"), "optional": ()},
    HOST_GAME_OVER: {
        "required": ("type", "result", "winner_name", "outcome", "cause", "conditions", "turn", "casualties"),
        "optional": (),
    },
}


def schema() -> dict[str, Any]:
    """The shared protocol schema as one JSON document.

    This module is the one source of the message names, the codes, the statuses, and
    the field names. `tools/make_protocol_schema.py` writes this document for the client
    build, and a test makes it again and compares it with the file.
    """
    return {
        "version": PROTOCOL_VERSION,
        "max_message_bytes": MAX_MESSAGE_BYTES,
        "client_messages": {name: name for name in CLIENT_MESSAGES},
        "host_messages": {name: name for name in HOST_MESSAGES},
        "statuses": {name: name for name in STATUSES},
        "error_codes": {name: name for name in ERROR_CODES},
        "terminal_codes": list(TERMINAL_CODES),
        "controllers": {name: name for name in CONTROLLERS},
        "seats": {name: name for name in SEATS},
        "client_fields": {
            name: {key: list(value) for key, value in fields.items()} for name, fields in CLIENT_FIELDS.items()
        },
        "host_fields": {
            name: {key: list(value) for key, value in fields.items()} for name, fields in HOST_FIELDS.items()
        },
    }


class ProtocolError(Exception):
    """A message from a client is not valid. The host answers with an error and stays up."""

    def __init__(self, rule_id: str, message: str, code: str = CODE_PROTOCOL) -> None:
        super().__init__(message)
        self.rule_id = rule_id
        self.message = message
        self.code = code


@dataclass(frozen=True)
class ClientMessage:
    type: str
    data: dict[str, Any]

    def require(self, key: str) -> Any:
        if key not in self.data:
            raise ProtocolError("protocol", f"the {self.type} message needs a {key} field")
        return self.data[key]


def byte_length(raw: str | bytes) -> int:
    """The length of a message on the wire, in bytes. A character can be four bytes."""
    if isinstance(raw, bytes):
        return len(raw)
    return len(raw.encode("utf-8", errors="surrogatepass"))


def parse(raw: str | bytes) -> ClientMessage:
    """Parse one client message. This is a trust boundary, so every error is typed."""
    if byte_length(raw) > MAX_MESSAGE_BYTES:
        raise ProtocolError("protocol", f"a message may not be longer than {MAX_MESSAGE_BYTES} bytes")
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProtocolError("protocol", f"the message is not valid JSON: {exc}") from exc
    except RecursionError as exc:
        raise ProtocolError("protocol", "the message is nested too deep") from exc
    if not isinstance(data, dict):
        raise ProtocolError("protocol", "a message must be a JSON object")
    kind = data.get("type")
    if kind not in CLIENT_MESSAGES:
        raise ProtocolError("protocol", f"unknown message type {kind!r}")
    return ClientMessage(str(kind), data)


def dump(message: dict[str, Any]) -> str:
    return json.dumps(message, separators=(",", ":"))


def welcome(
    player: int,
    seat: str,
    board: dict[str, Any],
    scenario: dict[str, Any],
    strict_los: bool = False,
    sides: dict[str, dict[str, str]] | None = None,
    seat_token: str | None = None,
) -> dict[str, Any]:
    """The first message. `strict_los` is the host flag. The client shows it and does not choose it."""
    message: dict[str, Any] = {
        "type": HOST_WELCOME,
        "player": player,
        "you": player,
        "seat": seat,
        "board": board,
        "scenario": scenario,
        "strict_los": strict_los,
        "sides": sides or {},
    }
    if seat_token is not None:
        message["seat_token"] = seat_token
    return message


def frame_message(
    player: int,
    view: dict[str, Any],
    frame: dict[str, Any],
    log_tail: list[dict[str, Any]],
    frame_token: str,
    status: str = STATUS_WAITING,
    auto_applied: list[str] | None = None,
    can_undo: bool = False,
    phase_text: str = "",
    objectives: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """One frame for one connection. `frame_token` is the opaque token of this connection."""
    message = {
        "type": HOST_FRAME,
        "player": player,
        "view": view,
        "frame_id": frame_token,
        "active": frame["player"],
        "phase": frame["phase"],
        "sub_step": frame["sub_step"],
        "turn": frame["turn"],
        "legal_commands": frame["commands"],
        "log_tail": log_tail,
        "status": status,
        "auto_applied": list(auto_applied or []),
        "can_undo": can_undo,
        "phase_text": phase_text,
    }
    if objectives is not None:
        message["objectives"] = objectives
    return message


def error_message(rule_id: str, message: str, code: str = CODE_PROTOCOL) -> dict[str, Any]:
    return {"type": HOST_ERROR, "rule_id": rule_id, "message": message, "code": code}


def los_result_message(from_hex: str, to_hex: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"type": HOST_LOS_RESULT, "from": from_hex, "to": to_hex, "result": result}


def options_result_message(unit: int, frame_token: str, result: dict[str, Any]) -> dict[str, Any]:
    return {"type": HOST_OPTIONS_RESULT, "unit": unit, "frame_id": frame_token, "result": result}


def game_over_message(
    result: int | None,
    cause: str,
    winner_name: str = "",
    outcome: str = "",
    conditions: list[dict[str, Any]] | None = None,
    turn: int = 0,
    casualties: dict[str, dict[str, int]] | None = None,
) -> dict[str, Any]:
    """The end of the game (H5). `result` is the winner index, or None for no winner."""
    return {
        "type": HOST_GAME_OVER,
        "result": result,
        "winner_name": winner_name,
        "outcome": outcome,
        "cause": cause,
        "conditions": list(conditions or []),
        "turn": turn,
        "casualties": dict(casualties or {}),
    }
