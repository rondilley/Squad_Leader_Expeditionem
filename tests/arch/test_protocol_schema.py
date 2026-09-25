"""The shared protocol schema (Slice 9 item 5).

`slhost.protocol` is the one source of the protocol names. The tool
`tools/make_protocol_schema.py` writes the schema file and the TypeScript module that
the client imports. These tests make the files again and compare them. They also examine
that the client protocol file has no hand copy of a name and that the builders of the
host give the field names of the schema.
"""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

from slhost import protocol, rooms

ROOT = Path(__file__).resolve().parents[2]
CLIENT_PROTOCOL = ROOT / "client" / "src" / "net" / "protocol.ts"
CLIENT_SOCKET = ROOT / "client" / "src" / "net" / "socket.ts"


def load_tool():
    spec = importlib.util.spec_from_file_location("make_protocol_schema", ROOT / "tools" / "make_protocol_schema.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def schema_values() -> set[str]:
    doc = protocol.schema()
    values: set[str] = set()
    for key in ("client_messages", "host_messages", "statuses", "error_codes", "controllers", "seats"):
        values.update(doc[key].values())
    values.update(doc["terminal_codes"])
    return values


def test_schema_json_is_current():
    tool = load_tool()
    text = tool.json_text()
    assert tool.JSON_PATH.read_text(encoding="utf-8") == text, "run python tools/make_protocol_schema.py"
    assert json.loads(text) == json.loads(json.dumps(protocol.schema()))


def test_schema_module_of_client_is_current():
    if not CLIENT_PROTOCOL.exists():
        pytest.skip("the client tree is not in this checkout")
    tool = load_tool()
    assert tool.TS_PATH.read_text(encoding="utf-8") == tool.ts_text(), "run python tools/make_protocol_schema.py"


def test_check_mode_finds_a_stale_file(tmp_path):
    tool = load_tool()
    good = tmp_path / "good.json"
    bad = tmp_path / "bad.json"
    missing = tmp_path / "missing.json"
    good.write_text(tool.json_text(), encoding="utf-8")
    bad.write_text("{}\n", encoding="utf-8")
    files = {good: tool.json_text(), bad: tool.json_text(), missing: tool.json_text()}
    assert tool.stale(files) == [bad, missing]


def string_literals(source: str) -> list[str]:
    """The string literals of a TypeScript text, with the comments removed."""
    code = re.sub(r"//[^\n]*", "", source)
    code = re.sub(r"/\*.*?\*/", "", code, flags=re.S)
    return re.findall(r'"([^"\\]*)"', code)


def test_client_protocol_has_no_hand_copied_names():
    if not CLIENT_PROTOCOL.exists():
        pytest.skip("the client tree is not in this checkout")
    names = schema_values()
    for path in (CLIENT_PROTOCOL, CLIENT_SOCKET):
        copies = sorted(set(string_literals(path.read_text(encoding="utf-8"))) & names)
        assert copies == [], f"{path.name} has a hand copy of a protocol name: {copies}"
    text = CLIENT_PROTOCOL.read_text(encoding="utf-8")
    assert 'from "./protocol_schema"' in text
    assert "SCHEMA.terminal_codes" in text


def test_literal_scan_finds_a_copy():
    sample = 'export type S = "your_turn" | "waiting"; // "room_code" in a comment\n'
    assert sorted(set(string_literals(sample)) & schema_values()) == ["waiting", "your_turn"]


def test_builders_give_the_schema_fields():
    doc = protocol.schema()["host_fields"]

    def keys_ok(name: str, message: dict) -> None:
        required = set(doc[name]["required"])
        allowed = required | set(doc[name]["optional"])
        assert required <= set(message), (name, required - set(message))
        assert set(message) <= allowed, (name, set(message) - allowed)

    keys_ok(protocol.HOST_WELCOME, protocol.welcome(0, "hot_seat", {}, {}))
    keys_ok(protocol.HOST_WELCOME, protocol.welcome(0, "german", {}, {}, seat_token="0" * 32))
    frame = {"player": 0, "phase": "rally", "sub_step": "", "turn": 1, "commands": []}
    keys_ok(protocol.HOST_FRAME, protocol.frame_message(0, {}, frame, [], "0" * 32))
    keys_ok(protocol.HOST_ERROR, protocol.error_message("SR-03", "text"))
    keys_ok(protocol.HOST_LOS_RESULT, protocol.los_result_message("A1", "A2", {}))
    keys_ok(protocol.HOST_GAME_OVER, protocol.game_over_message(None, "turns"))


def test_schema_lists_match_the_constants():
    doc = protocol.schema()
    assert tuple(doc["client_messages"]) == protocol.CLIENT_MESSAGES
    assert tuple(doc["error_codes"]) == protocol.ERROR_CODES
    assert set(doc["terminal_codes"]) <= set(doc["error_codes"])
    assert set(doc["client_fields"]) == set(protocol.CLIENT_MESSAGES)
    assert set(doc["host_fields"]) == set(protocol.HOST_MESSAGES)
    # The room module has its own copy of the seat names; they must agree.
    assert rooms.SEAT_HOT_SEAT == protocol.SEAT_HOT_SEAT
    assert rooms.SEAT_WATCHER == protocol.SEAT_WATCHER


def test_parse_accepts_each_client_message_of_the_schema():
    for name, fields in protocol.schema()["client_fields"].items():
        message = {key: "x" for key in fields["required"]}
        message["type"] = name
        parsed = protocol.parse(json.dumps(message))
        assert parsed.type == name
        for key in fields["required"]:
            parsed.require(key)
