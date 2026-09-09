from slcore.commands import Command, canonical_bytes, command_id
from slcore.frame import make_frame


def test_canonical_bytes_sorted_keys_no_white_space():
    c = Command("move", units=(7,), hex=(2, 4))
    assert canonical_bytes(c.payload()) == b'{"action":"move","hex":"C4","units":[7]}'
    assert c.id == command_id(c.payload())
    assert len(c.id) == 16


def test_unit_order_does_not_change_the_id():
    a = Command("stack_move", units=(3, 1, 2), hex=(0, 1))
    b = Command("stack_move", units=(1, 2, 3), hex=(0, 1))
    assert a.id == b.id


def test_payload_round_trip():
    c = Command("pickup", units=(4,), weapon=9)
    again = Command.from_payload(c.payload())
    assert again == c
    e = Command("end_phase")
    assert Command.from_payload(e.payload()) == e


def test_golden_ids_agree_with_the_javascript_encoder():
    """Ten payloads with the bytes and IDs from a JavaScript encoder. A Rust port runs the same table."""
    import json
    from pathlib import Path

    doc = json.loads((Path(__file__).parent / "golden_command_ids.json").read_text(encoding="utf-8"))
    assert len(doc["rows"]) == 10
    for row in doc["rows"]:
        assert canonical_bytes(row["payload"]).decode("ascii") == row["canonical"]
        assert command_id(row["payload"]) == row["id"], row
        assert Command.from_payload(row["payload"]).id == row["id"]


def test_frame_drops_duplicate_ids_and_finds_by_id():
    frame = make_frame("f", 0, "movement", "move_window", 1, [Command("end_phase"), Command("end_phase"), Command("move", (1,), (0, 2))])
    assert len(frame.commands) == 2
    assert frame.by_id(Command("end_phase").id) is not None
    assert frame.by_id("nope") is None
