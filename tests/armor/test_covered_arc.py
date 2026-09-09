"""Rule 29.4, the covered arc, and rule 33.5, the target facing.

Both are geometry on the exact integer lattice, so the tests read properties and not one
worked example. A mapping from a spine to the wrong pair of hexsides breaks a property.
"""

from __future__ import annotations

from slcore import geometry
from slcore.rules import r28_vehicles as r28

ORIGIN = (4, 4)
FACINGS = tuple(range(6))
DIRECTIONS = tuple(range(6))


def step(start, direction, count):
    ref = start
    for _ in range(count):
        ref = geometry.neighbor(*ref, direction)
    return ref


def test_a_covered_arc_holds_the_two_neighbours_beside_the_spine():
    """Rule 29.4: the arc is the hexside to the right and to the left of the gun barrel."""
    for facing in FACINGS:
        inside = [d for d in DIRECTIONS if r28.in_covered_arc(ORIGIN, facing, geometry.neighbor(*ORIGIN, d))]
        assert sorted(inside) == sorted(r28.arc_directions(facing)), facing


def test_the_vehicle_hex_is_in_its_own_arc():
    for facing in FACINGS:
        assert r28.in_covered_arc(ORIGIN, facing, ORIGIN)


def test_the_six_arcs_of_a_hex_cover_every_hex_and_share_only_their_edges():
    """Every hex is in one arc or in two, and never in none of them."""
    board_hexes = [(c, r) for c in range(9) for r in range(9)]
    for ref in board_hexes:
        count = sum(1 for f in FACINGS if r28.in_covered_arc(ORIGIN, f, ref))
        assert count >= 1, f"{ref} is in no covered arc"
        assert count <= 6, ref
    # A hex straight along a direction sits on the edge of two arcs.
    shared = step(ORIGIN, 1, 3)
    assert sum(1 for f in FACINGS if r28.in_covered_arc(ORIGIN, f, shared)) == 2


def test_an_arc_reaches_as_far_as_the_hexes_go():
    """Rule 29.4: the two hexsides are extended to the limit of the line of sight."""
    for facing in FACINGS:
        left, right = r28.arc_directions(facing)
        for distance in (1, 3, 8):
            assert r28.in_covered_arc(ORIGIN, facing, step(ORIGIN, left, distance))
            assert r28.in_covered_arc(ORIGIN, facing, step(ORIGIN, right, distance))


def test_a_hex_behind_the_vehicle_is_never_in_the_arc():
    for facing in FACINGS:
        left, right = r28.arc_directions(facing)
        behind = (left + 3) % 6
        assert not r28.in_covered_arc(ORIGIN, facing, step(ORIGIN, behind, 2))


def test_facing_towards_puts_the_target_in_the_arc():
    for col in range(9):
        for row in range(9):
            ref = (col, row)
            if ref == ORIGIN:
                continue
            facing = r28.facing_towards(ORIGIN, ref)
            assert r28.in_covered_arc(ORIGIN, facing, ref), (ref, facing)


# ------------------------------------------------------------------ the target facing


def test_one_hexside_is_crossed_from_a_neighbour():
    """The line of sight from a hex next door crosses the hexside between them."""
    for d in DIRECTIONS:
        firer = geometry.neighbor(*ORIGIN, d)
        assert r28.crossed_hexsides(ORIGIN, firer) == (d,)


def test_two_hexsides_are_crossed_along_a_spine():
    """Rule 33.5: the line of sight can run exactly along a hex spine of the target."""
    firer = geometry.neighbor(*geometry.neighbor(*ORIGIN, 1), 2)
    sides = r28.crossed_hexsides(ORIGIN, firer)
    assert len(sides) == 2
    assert set(sides) == {1, 2}


def test_the_facing_classes_split_the_six_hexsides_two_two_and_two():
    for facing in FACINGS:
        classes = [r28.facing_class(facing, d) for d in DIRECTIONS]
        assert classes.count(r28.FRONT) == 2, facing
        assert classes.count(r28.REAR) == 2, facing
        assert classes.count(r28.SIDE) == 2, facing


def test_the_front_of_a_vehicle_is_the_arc_its_gun_covers():
    for facing in FACINGS:
        left, right = r28.arc_directions(facing)
        assert r28.facing_class(facing, left) == r28.FRONT
        assert r28.facing_class(facing, right) == r28.FRONT
        assert r28.facing_class(facing, (left + 3) % 6) == r28.REAR
        assert r28.facing_class(facing, (right + 3) % 6) == r28.REAR


def test_a_shot_from_the_front_and_a_shot_from_the_rear_read_different_rows():
    """Two firers on opposite sides of one vehicle read the front and the rear."""
    for facing in FACINGS:
        left, _ = r28.arc_directions(facing)
        ahead = geometry.neighbor(*ORIGIN, left)
        behind = geometry.neighbor(*ORIGIN, (left + 3) % 6)
        front = [r28.facing_class(facing, d) for d in r28.crossed_hexsides(ORIGIN, ahead)]
        rear = [r28.facing_class(facing, d) for d in r28.crossed_hexsides(ORIGIN, behind)]
        assert front == [r28.FRONT], facing
        assert rear == [r28.REAR], facing
