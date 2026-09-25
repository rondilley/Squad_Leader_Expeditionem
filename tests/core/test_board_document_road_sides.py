"""The board document carries the road hexsides of generator version 8 (PR-50).

The three board drawings read `road_sides` from the document the host sends. A board of
generator version 7 has no road hexsides, so its document has no such key.
"""

from __future__ import annotations

from slboards.generator import GeneratorParameters, generate
from slcore import geometry
from slcore.view import board_document
from sldata.loaders import load_terrain


def _document(version: int) -> dict:
    params = GeneratorParameters.from_dict(
        {"seed": 11, "board_type": "village", "cols": 16, "rows": 10, "version": version}
    )
    return board_document(generate(params, load_terrain()))


def test_a_version_8_document_carries_the_road_sides_in_the_order_of_the_hex():
    terrain = load_terrain()
    params = GeneratorParameters.from_dict({"seed": 11, "board_type": "village", "cols": 16, "rows": 10, "version": 8})
    board = generate(params, terrain)
    doc = board_document(board)
    with_sides = [item for item in doc["hexes"] if "road_sides" in item]
    assert with_sides, "a version 8 village board has a road with named hexsides"
    for item in with_sides:
        hex_ref = geometry.parse_hex_id(item["id"])
        assert item["road_sides"] == list(board.hex(hex_ref).road_sides)
        assert all(isinstance(d, int) and 0 <= d < 6 for d in item["road_sides"])


def test_a_version_7_document_has_no_road_sides():
    doc = _document(7)
    assert any(item.get("road") for item in doc["hexes"]), "the version 7 board has a road"
    assert not any("road_sides" in item for item in doc["hexes"])


def test_the_document_is_the_same_on_each_call():
    assert _document(8) == _document(8)
