"""PR-56, the orchard, and PR-57, the mill and the windmill (owner, 2026-10-17).

An orchard has the effects of a wheatfield of rule 44.2 in each season. A mill and a
windmill are buildings with a picture and a name of their own, and no rule of their own.
The generator puts them on a board only when the record asks for them, so each board that
a scenario already names stays the same.
"""

from __future__ import annotations

import pygame

from slboards import generator
from slcore import geometry, view
from slcore.los_cache import LosTable
from slcore.los_eval import evaluate
from slcore.rules import r11_terrain, r44_rural
from slcore.state import Board, Hex, default_polygons
from sldata.loaders import load_terrain, load_vehicle_movement
from slwindow import layout, render, theme

TERRAIN = load_terrain()
COLS = 10
ROWS = 10


def ref(text: str):
    return geometry.parse_hex_id(text)


def paint(**plan) -> Board:
    hexes = []
    for col in range(COLS):
        first = 0 if col & 1 else 1
        for row in range(first, ROWS + 1):
            kind = plan.get(geometry.hex_id(col, row), "open")
            hexes.append(Hex(col=col, row=row, terrain=kind, polygons=default_polygons(col, row, kind, TERRAIN)))
    return Board(COLS, ROWS, hexes, TERRAIN, name="orchard-fixture")


# ------------------------------------------------------------------ PR-56, the orchard


def test_an_orchard_has_the_terrain_row_of_a_wheatfield():
    orchard, wheat = TERRAIN["orchard"], TERRAIN["wheat"]
    assert (orchard.tem, orchard.mf_halves, orchard.los) == (wheat.tem, wheat.mf_halves, wheat.los)
    vehicle = load_vehicle_movement()
    for truck in (False, True):
        assert vehicle.terrain_cost("orchard", truck) == vehicle.terrain_cost("wheat", truck)


def test_fire_through_an_orchard_is_half_strength_in_each_season():
    board = paint(G4="orchard")
    traced = [ref("G4"), ref("G5")]
    assert r44_rural.halves_through_crop(board, ref("G3"), ref("G6"), traced, 8) == 4
    assert r44_rural.halves_through_crop(board, ref("G3"), ref("G6"), traced, 8, in_season=False) == 4


def test_fire_into_an_orchard_is_full_strength():
    board = paint(G5="orchard")
    assert r44_rural.halves_through_crop(board, ref("G3"), ref("G5"), [ref("G4")], 8) == 8


def test_the_halving_names_the_rule_of_each_kind_of_crop():
    board = paint(G4="orchard", G5="wheat")
    assert r44_rural.crop_rules(board, [ref("G4")]) == (r44_rural.RULE_PR_56,)
    assert r44_rural.crop_rules(board, [ref("G5")]) == (r44_rural.RULE_44_21,)
    assert r44_rural.crop_rules(board, [ref("G4"), ref("G5")]) == (r44_rural.RULE_44_21, r44_rural.RULE_PR_56)


def test_an_orchard_hinders_the_line_of_sight_as_a_wheatfield_does():
    for kind in ("wheat", "orchard"):
        board = paint(G5=kind)
        verdict = evaluate(board, LosTable(board), ref("G3"), ref("G7"))
        assert verdict.clear and verdict.hindrance == 1, kind


def test_an_orchard_is_not_open_ground():
    board = paint(G5="orchard")
    assert not r11_terrain.is_open_ground(board, ref("G5"))
    assert r11_terrain.moving_in_open_modifier(board, ref("G5")) == 0


def test_a_record_with_no_orchard_and_no_landmark_builds_the_board_it_built_before():
    """The orchard pass and the landmark pass draw nothing when the record does not ask."""
    params = generator.GeneratorParameters(seed=11, board_type="village")
    plain = generator.generate(params, TERRAIN)
    assert not any(h.terrain == "orchard" for h in plain)
    assert not any(h.building is not None and h.building.landmark for h in plain)
    assert "landmarks" not in params.to_dict()


def test_the_orchards_change_only_the_hexes_of_the_orchards():
    plain = generator.generate(generator.GeneratorParameters(seed=11, board_type="village"), TERRAIN)
    params = generator.GeneratorParameters(seed=11, board_type="village", style=(("orchards", 2),))
    with_orchards = generator.generate(params, TERRAIN)
    changed = [h.ref for h in with_orchards if h != plain.hex(h.ref)]
    assert changed and all(with_orchards.hex(r).terrain == "orchard" for r in changed)
    assert all(plain.hex(r).terrain == "open" and not plain.hex(r).road for r in changed)
    roads = {h.ref for h in plain if h.road}
    # Each orchard is a row beside a road: one hex of each row touches a road.
    rows = _rows(set(changed))
    assert len(rows) >= 1 and all(len(r) >= 3 for r in rows)
    assert all(any(n in roads for h in r for n in geometry.neighbors(*h)) for r in rows)


def _rows(hexes: set) -> list[set]:
    out = []
    left = set(hexes)
    while left:
        stack, group = [left.pop()], set()
        while stack:
            h = stack.pop()
            group.add(h)
            for n in geometry.neighbors(*h):
                if n in left:
                    left.discard(n)
                    stack.append(n)
        out.append(group)
    return out


# ------------------------------------------------------- PR-57, the mill and the windmill


def test_a_landmark_goes_on_the_building_of_its_rank_in_its_band():
    mill = generator.Landmark("mill", 0, 20, 30)
    params = generator.GeneratorParameters(seed=7, board_type="city", landmarks=(mill,))
    board = generator.generate(params, TERRAIN)
    marked = {h.building.id for h in board if h.building is not None and h.building.landmark == "mill"}
    stone = {}
    for h in board:
        if h.building is not None and h.terrain == "stone_building" and 20 <= h.col <= 30:
            stone.setdefault(h.building.id, []).append(h.ref)
    largest = sorted(stone.items(), key=lambda item: (-len(item[1]), sorted(item[1])[0]))[0][0]
    assert marked == {largest}
    assert generator.GeneratorParameters.from_dict(params.to_dict()) == params


def test_a_landmark_changes_no_hex_but_its_building_record():
    plain = generator.generate(generator.GeneratorParameters(seed=7, board_type="city"), TERRAIN)
    mill = generator.Landmark("mill", 0, 20, 30)
    marked = generator.generate(generator.GeneratorParameters(seed=7, board_type="city", landmarks=(mill,)), TERRAIN)
    for h in marked:
        before = plain.hex(h.ref)
        if h.building is not None and h.building.landmark:
            assert h.building.id == before.building.id and h.building.size == before.building.size
            assert h.terrain == before.terrain
        else:
            assert h == before


def test_the_board_document_carries_the_landmark_and_reads_it_back():
    mill = generator.Landmark("mill", 0, 20, 30)
    board = generator.generate(generator.GeneratorParameters(seed=7, board_type="city", landmarks=(mill,)), TERRAIN)
    again = Board.from_dict(board.to_dict(), TERRAIN)
    assert again.to_dict() == board.to_dict()
    drawn = view.board_document(board)
    assert any((h.get("building") or {}).get("landmark") == "mill" for h in drawn["hexes"])


# ------------------------------------------------------------------------ the pictures


def _picture(params) -> tuple[pygame.Surface, dict]:
    pygame.init()
    board = generator.generate(params, TERRAIN)
    document = view.board_document(board)
    surface = pygame.Surface((1400, 600))
    render.draw_board(surface, document, layout.fit(document, 1400, 600), pygame.font.SysFont("arial", 12))
    return surface, document


def _colours(surface: pygame.Surface) -> set:
    raw = pygame.image.tobytes(surface, "RGB")
    return {tuple(raw[i : i + 3]) for i in range(0, len(raw), 3)}


def test_the_window_draws_the_orchard_trees_and_the_two_landmarks():
    params = generator.GeneratorParameters(
        seed=11,
        board_type="village",
        style=(("orchards", 2),),
        landmarks=(generator.Landmark("mill", 0, 0, 32), generator.Landmark("windmill", 0, 0, 32)),
    )
    colours = _colours(_picture(params)[0])
    assert theme.ORCHARD_GROUND in colours and theme.ORCHARD_TREE in colours
    assert theme.LANDMARK["sail"] in colours and theme.LANDMARK["water"] in colours


def test_a_board_with_no_new_terrain_draws_none_of_its_colours():
    colours = _colours(_picture(generator.GeneratorParameters(seed=11, board_type="village"))[0])
    assert theme.ORCHARD_TREE not in colours and theme.LANDMARK["sail"] not in colours
