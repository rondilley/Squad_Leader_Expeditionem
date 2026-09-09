"""Rule 44, the rural terrain types of Game Set II.

Three terrain types, and each one gets its own board here. A rule that says what a
wheatfield does to fire is tested on a board with a wheatfield on the line, and not on a
game that may or may not put one there.
"""

from __future__ import annotations

import pytest

from slcore import geometry
from slcore.rules import r11_terrain, r44_rural
from slcore.state import Board, Hex, default_polygons
from sldata.loaders import load_terrain

TERRAIN = load_terrain()
COLS = 10
ROWS = 10


def ref(text: str):
    return geometry.parse_hex_id(text)


def paint(**plan) -> Board:
    """A board where plan gives (terrain, elevation) or (terrain, elevation, hexsides)."""
    hexes = []
    for col in range(COLS):
        first = 0 if col & 1 else 1
        for row in range(first, ROWS + 1):
            hid = geometry.hex_id(col, row)
            item = plan.get(hid, ("open", 0))
            kind, elevation = item[0], item[1]
            sides = list(item[2]) if len(item) > 2 else [None] * 6
            hexes.append(
                Hex(
                    col=col,
                    row=row,
                    terrain=kind,
                    elevation=elevation,
                    hexsides=tuple(sides),
                    polygons=default_polygons(col, row, kind, TERRAIN),
                )
            )
    return Board(COLS, ROWS, hexes, TERRAIN, name="rural-fixture")


def with_cliff(a: str, direction: int, **plan) -> Board:
    """A board with a cliff hexside between one hex and its neighbour."""
    board = paint(**plan)
    here = ref(a)
    there = geometry.neighbor(here[0], here[1], direction)
    hexes = []
    for h in board:
        sides = list(h.hexsides)
        if h.ref == here:
            sides[direction] = "cliff"
        if h.ref == there:
            sides[(direction + 3) % 6] = "cliff"
        hexes.append(
            Hex(
                col=h.col,
                row=h.row,
                terrain=h.terrain,
                elevation=h.elevation,
                hexsides=tuple(sides),
                polygons=h.polygons,
            )
        )
    return Board(COLS, ROWS, hexes, TERRAIN, name="cliff-fixture")


# ---------------------------------------------------------------- 44.2, wheatfields


def test_fire_into_a_wheatfield_hex_is_full_strength():
    """Rule 44.21: a unit sees into a wheatfield hex, so it fires into it normally."""
    board = paint(G5=("wheat", 0))
    assert r44_rural.halves_through_crop(board, ref("G3"), ref("G5"), [ref("G4")], 8) == 8


def test_fire_through_a_wheatfield_hex_is_half_strength():
    """Rule 44.21: the thread crosses two hexsides of the crop, which is more than one."""
    board = paint(G4=("wheat", 0))
    assert r44_rural.halves_through_crop(board, ref("G3"), ref("G6"), [ref("G4"), ref("G5")], 8) == 4


def test_a_height_advantage_takes_the_halving_away():
    """Rule 44.21 and 44.22: a unit above the crop is not affected at all."""
    board = paint(G3=("open", 1), G4=("wheat", 0))
    traced = [ref("G4"), ref("G5")]
    assert r44_rural.halves_through_crop(board, ref("G3"), ref("G6"), traced, 8) == 8


def test_a_unit_on_the_level_of_the_crop_takes_the_halving():
    board = paint(G3=("open", 1), G4=("wheat", 1), G5=("open", 1), G6=("open", 1))
    traced = [ref("G4"), ref("G5")]
    assert r44_rural.halves_through_crop(board, ref("G3"), ref("G6"), traced, 8) == 4


def test_a_thread_with_no_crop_is_not_halved():
    board = paint()
    assert r44_rural.halves_through_crop(board, ref("G3"), ref("G6"), [ref("G4"), ref("G5")], 8) == 8


def test_out_of_season_a_wheatfield_hex_is_open_ground():
    """Rule 44.24."""
    board = paint(G4=("wheat", 0))
    traced = [ref("G4"), ref("G5")]
    assert r44_rural.halves_through_crop(board, ref("G3"), ref("G6"), traced, 8, in_season=False) == 8


def test_the_season_switch_reads_the_scenario():
    """Rule 44.24. With no switch the crop stands, because year one plays in October."""
    assert r44_rural.wheat_in_season({})
    assert r44_rural.wheat_in_season({"wheat_season": "in"})
    assert not r44_rural.wheat_in_season({"wheat_season": "out"})


def test_the_months_of_the_crop_are_june_to_october():
    """Rule 44.24."""
    assert [m for m in range(1, 13) if r44_rural.month_in_season(m)] == [6, 7, 8, 9, 10]


def test_a_unit_that_moved_in_a_wheatfield_takes_no_modifier():
    """Rule 44.23, which rule 16.5 already gives, because a wheatfield is not open ground."""
    board = paint(G5=("wheat", 0))
    assert r11_terrain.moving_in_open_modifier(board, ref("G5")) == 0


# ----------------------------------------------------------------- 44.3, shellholes


def test_a_unit_that_moved_in_a_shellhole_takes_minus_one():
    """Rule 44.32: the minus two of rule 16.5 becomes minus one."""
    board = paint(G5=("shellhole", 0))
    assert r11_terrain.moving_in_open_modifier(board, ref("G5")) == -1


def test_a_unit_that_moved_in_open_ground_takes_minus_two():
    """Rule 16.5 is unchanged where rule 44.32 does not reach."""
    board = paint()
    assert r11_terrain.moving_in_open_modifier(board, ref("G5")) == -2


def test_a_unit_that_moved_in_woods_takes_no_modifier():
    board = paint(G5=("woods", 0))
    assert r11_terrain.moving_in_open_modifier(board, ref("G5")) == 0


def test_a_shellhole_still_gives_its_terrain_modifier():
    """Rule 44.31 with the terrain table: plus one to the dice roll of the attacker."""
    board = paint(G5=("shellhole", 0))
    assert r11_terrain.target_hex_modifier(board, ref("G5")) == 1


# --------------------------------------------------------------------- 44.1, cliffs


def test_point_blank_fire_is_doubled_with_no_cliff():
    """Rule 9.1 in half factors: one factor becomes four halves."""
    board = paint()
    assert r44_rural.point_blank_halves(board, ref("G4"), ref("G5")) == 4


def test_point_blank_fire_over_a_cliff_is_tripled_for_the_higher_unit():
    """Rule 44.1."""
    board = with_cliff("G4", 3, G4=("open", 2))
    assert r44_rural.point_blank_halves(board, ref("G4"), ref("G5")) == 6


def test_the_lower_unit_over_a_cliff_keeps_the_doubling():
    """Rule 44.1: the fire of the lower unit stays at the doubling of rule 9.1."""
    board = with_cliff("G4", 3, G4=("open", 2))
    assert r44_rural.point_blank_halves(board, ref("G5"), ref("G4")) == 4


def test_a_cliff_hexside_is_between_the_two_hexes_it_separates():
    board = with_cliff("G4", 3, G4=("open", 2))
    assert r44_rural.cliff_between(board, ref("G4"), ref("G5"))
    assert r44_rural.cliff_between(board, ref("G5"), ref("G4"))
    assert not r44_rural.cliff_between(board, ref("G3"), ref("G4"))


def test_a_cliff_hexside_is_impassable():
    """Rule 44.1, which the hexside table already gives to the movement rule."""
    from slcore.rules.r05_movement import MoveContext, entry_cost_halves
    from sldata.loaders import load_all_counters, load_hexsides

    board = with_cliff("G4", 3, G4=("open", 2))
    ctx = MoveContext(board, board.terrain, load_hexsides(), load_all_counters()["german"])
    cost, rules = entry_cost_halves(ctx, ref("G4"), ref("G5"))
    assert cost is None
    assert "5.5" in rules


# --------------------------------------------------------- the rule reaches a game


def test_a_game_applies_the_rural_rules():
    """The fire resolution reads the season from the scenario switches."""
    from slcli.play import build_engine

    engine = build_engine("s01_guards_counterattack")
    assert engine.fire_ctx.wheat_in_season is True


def test_a_scenario_can_put_the_crop_out_of_season():
    from dataclasses import replace as replace_field

    from slcore.engine import Engine
    from sldata.loaders import (
        board_and_parameters,
        load_all_counters,
        load_hexsides,
        load_scenario,
        load_tables,
    )

    scenario = load_scenario("s01_guards_counterattack")
    winter = replace_field(scenario, switches=scenario.switches + (("wheat_season", "out"),))
    board, _ = board_and_parameters(winter, TERRAIN)
    engine = Engine(winter, board, TERRAIN, load_hexsides(), load_all_counters(), load_tables())
    assert engine.fire_ctx.wheat_in_season is False
