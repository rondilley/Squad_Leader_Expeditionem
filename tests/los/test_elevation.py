"""Rule 43: the three levels of hills and what they do to the line of sight.

The board here is a bare 10 by 10 field. Each test paints the few hexes it needs, so the
level and the terrain of every other hex is the ground-level open field. Column G is an
even-index column, so a thread from G1 to G10 goes straight down G2 to G9 and each test
reads one rule on one straight line.
"""

from __future__ import annotations

import pytest

from slcore import geometry
from slcore.los_cache import LosTable
from slcore.los_eval import evaluate
from slcore.rules import r43_elevation
from slcore.state import Board, Building, Hex, default_polygons
from sldata.loaders import load_all_counters, load_hexsides, load_terrain

COLS = 10
ROWS = 10


def ref(text: str):
    return geometry.parse_hex_id(text)


def paint(**plan: tuple) -> Board:
    """A board where plan gives (terrain, elevation) or (terrain, elevation, building)."""
    terrain = load_terrain()
    hexes = []
    for col in range(COLS):
        first = 0 if col & 1 else 1
        for row in range(first, ROWS + 1):
            hid = geometry.hex_id(col, row)
            item = plan.get(hid, ("open", 0))
            kind = item[0]
            elevation = item[1]
            building = item[2] if len(item) > 2 else None
            hexes.append(
                Hex(
                    col=col,
                    row=row,
                    terrain=kind,
                    elevation=elevation,
                    building=building,
                    polygons=default_polygons(col, row, kind, terrain),
                )
            )
    return Board(COLS, ROWS, hexes, terrain, name="elevation-fixture")


def look(board: Board, firer: str, target: str):
    return evaluate(board, LosTable(board), ref(firer), ref(target))


# --------------------------------------------------------------- 43.7, the same level


def test_a_bare_crest_on_the_same_level_does_not_block():
    """Rule 43.7: a unit sees anything on its own level, whatever the equal crests do."""
    board = paint(G3=("open", 1), G5=("open", 1), G7=("open", 1))
    assert look(board, "G3", "G7").clear


def test_a_higher_crest_blocks_two_units_of_the_same_level():
    """Rule 43.3: a hill blocks the way a woods or a building does."""
    board = paint(G3=("open", 1), G5=("open", 2), G7=("open", 1))
    result = look(board, "G3", "G7")
    assert not result.clear
    assert result.rule_id == "43.3"
    assert result.blocking_hex == ref("G5")


# ------------------------------------------------- 43.4, the height advantage over woods


def test_level_one_is_not_high_enough_to_see_over_ground_woods():
    """Rule 43.4 names this case: level one is the height of woods on ground level."""
    board = paint(G3=("open", 1), G5=("woods", 0), G7=("open", 1))
    result = look(board, "G3", "G7")
    assert not result.clear
    assert result.rule_id == "43.4"
    assert result.blocking_hex == ref("G5")


def test_level_two_sees_over_ground_woods():
    board = paint(G3=("open", 2), G5=("woods", 0), G7=("open", 2))
    assert look(board, "G3", "G7").clear


def test_level_two_does_not_see_over_woods_on_a_level_one_hill():
    board = paint(G3=("open", 2), G5=("woods", 1), G7=("open", 2))
    assert not look(board, "G3", "G7").clear


# ------------------------------------------- 43.3, how far a ground unit sees into a hill


def test_ground_fire_reaches_the_first_hill_hex():
    """Rule 43.3: a ground unit fires into the initial crest line hexside of a level one hill."""
    board = paint(G5=("open", 1), G6=("open", 1), G7=("open", 1))
    assert look(board, "G3", "G5").clear


def test_ground_fire_does_not_penetrate_further_into_the_hill():
    board = paint(G5=("open", 1), G6=("open", 1), G7=("open", 1))
    result = look(board, "G3", "G7")
    assert not result.clear
    assert result.rule_id == "43.3"


# ----------------------------------------------------------------- 43.6 and 43.62, blind


def test_the_hex_behind_woods_is_blind_from_a_hill():
    """Rule 43.6: the thread clears the roof, and the ground behind it is still blind."""
    board = paint(G3=("open", 3), G4=("woods", 0))
    result = look(board, "G3", "G5")
    assert not result.clear
    assert result.rule_id == "43.6"
    assert result.blocking_hex == ref("G5")


def test_a_blind_hex_that_reaches_the_height_of_the_obstacle_is_seen():
    """Rule 43.6 again: the same hex, raised to the height of the woods it stands behind."""
    board = paint(G3=("open", 3), G4=("woods", 0), G5=("open", 1))
    assert look(board, "G3", "G5").clear


def test_a_large_building_blinds_the_second_hex_behind_it():
    """Rule 43.62: three hexes or more, so the blind zone is two hexes and not one.

    The thread runs from a level three hex over a building on ground level to a level one
    hex two hexes behind it. The building is large, so that second hex is still blind.
    """
    big = Building("B9", "stone", 3)
    board = paint(
        G3=("open", 3),
        G4=("stone_building", 0, big),
        H4=("stone_building", 0, big),
        H5=("stone_building", 0, big),
        G6=("open", 1),
    )
    result = look(board, "G3", "G6")
    assert not result.clear
    assert result.rule_id == "43.62"
    assert result.blocking_hex == ref("G6")


def test_a_small_building_leaves_the_second_hex_in_sight():
    """The same thread over a building of two hexes, whose blind zone is one hex (rule 7.4)."""
    small = Building("B8", "wooden", 2)
    board = paint(
        G3=("open", 3),
        G4=("wooden_building", 0, small),
        H4=("wooden_building", 0, small),
        G6=("open", 1),
    )
    assert look(board, "G3", "G6").clear


def test_a_bare_crest_opens_no_blind_zone():
    """Rule 43.61: a crest line makes no blind hex when the firer is on the same hill."""
    board = paint(G3=("open", 2), G4=("open", 2), G5=("open", 1), G6=("open", 1))
    assert look(board, "G4", "G6").clear


# --------------------------------------------------------------------- 43.8, symmetry


def test_the_line_of_sight_is_symmetric_on_a_hill_board():
    """Rule 43.8: whenever A sees B, B sees A."""
    plan = {}
    for col in range(3, 8):
        for row in range(2, 9):
            hid = geometry.hex_id(col, row)
            far = abs(col - 5) + abs(row - 5)
            plan[hid] = ("woods" if (col + row) % 7 == 0 else "open", max(0, 3 - far))
    board = paint(**plan)
    table = LosTable(board)
    refs = [r for r in board.order if (r[0] + r[1]) % 2 == 0]
    seen = {True: 0, False: 0}
    for a in refs:
        for b in refs:
            if a >= b:
                continue
            forward = evaluate(board, table, a, b).clear
            assert forward == evaluate(board, table, b, a).clear
            seen[forward] += 1
    # The board must give both answers, or the test says nothing about the rule.
    assert seen[True] and seen[False]


# ------------------------------------------------------ the ground-level board is rule 7


def test_a_board_without_hills_never_reaches_rule_43():
    board = paint(G5=("woods", 0))
    result = look(board, "G3", "G7")
    assert not result.clear
    assert result.rule_id.startswith("7.")
    assert not r43_elevation.in_play(board, [ref("G3"), ref("G5"), ref("G7")])


# ---------------------------------------------------------------- 43.15 and 43.21


def test_a_bare_hill_hex_is_open_ground_for_combat():
    """Rule 43.15: the level does not change the terrain effects modifier."""
    board = paint(G5=("open", 2))
    assert board.terrain[board.hex(ref("G5")).terrain].tem == 0


def test_moving_up_a_crest_line_costs_double():
    """Rules 43.21 and 5.53."""
    from slcore.rules.r05_movement import MoveContext, entry_cost_halves

    board = paint(G5=("open", 1))
    ctx = MoveContext(board, board.terrain, load_hexsides(), load_all_counters()["german"])
    up, rules = entry_cost_halves(ctx, ref("G4"), ref("G5"))
    flat, _ = entry_cost_halves(ctx, ref("G3"), ref("G4"))
    assert up == flat * 2
    assert "5.53" in rules


@pytest.mark.parametrize("kinds,expected", [(frozenset(), 0), (frozenset({"woods"}), 1)])
def test_symbol_height_needs_a_crossed_symbol(kinds, expected):
    board = paint(G5=("woods", 0))
    assert r43_elevation.symbol_height(board, ref("G5"), kinds) == expected
