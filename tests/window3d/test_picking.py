"""Tests for the hex pick of the 3D window: a ray against the hex prisms.

`slwindow3d.picking` imports no part of Panda3D, so these tests run with no window. The
test of the pick through the real lens of the window is in `test_play_input.py`.
"""

from __future__ import annotations

import math

from slcli.play import build_engine
from slcore.view import board_document
from slwindow3d.picking import hex_corners, pick_hex, world_xy

HEIGHT = 0.6
THICKNESS = 0.35


def _row(elevations):
    """One row of hexes, side by side along x, one for each elevation in the list."""
    hexes = []
    for i, level in enumerate(elevations):
        hexes.append({"id": f"H{i}", "center": [i * 6, 0], "terrain": "open", "elevation": level})
    return {"hexes": hexes}


def _down_at(x, y):
    return (x, y, 50.0), (0.0, 0.0, -1.0)


def test_a_ray_straight_down_on_each_hex_centre_picks_that_hex():
    board = board_document(build_engine("s01_guards_counterattack", None).board)
    for hexagon in board["hexes"]:
        origin, direction = _down_at(*world_xy(hexagon["center"][0], hexagon["center"][1]))
        assert pick_hex(board, origin, direction, HEIGHT, THICKNESS) == hexagon["id"]


def test_a_ray_near_a_corner_picks_the_hex_that_holds_the_point():
    board = _row([0, 0])
    corners = hex_corners(board["hexes"][0])
    # A point a little inside the east corner of the first hex, and a little outside it.
    east_x, east_y = max(corners)
    inside = pick_hex(board, *_down_at(east_x - 0.05, east_y), HEIGHT, THICKNESS)
    outside = pick_hex(board, *_down_at(east_x + 0.05, east_y), HEIGHT, THICKNESS)
    assert inside == "H0"
    assert outside is None


def test_a_ray_that_misses_the_board_picks_nothing():
    board = _row([0, 1, 2])
    assert pick_hex(board, (100.0, 100.0, 50.0), (0.0, 0.0, -1.0), HEIGHT, THICKNESS) is None
    # A ray that points up never gets to the board.
    assert pick_hex(board, (0.0, 0.0, 50.0), (0.0, 0.0, 1.0), HEIGHT, THICKNESS) is None


def test_the_top_of_a_raised_hex_is_picked_at_its_elevation():
    board = _row([3])
    top_z = 3 * HEIGHT
    # A shallow ray that reaches the hex centre at its top z, from the west.
    target = (0.0, 0.0, top_z)
    direction = (1.0, 0.0, -0.2)
    origin = tuple(t - d * 10 for t, d in zip(target, direction))
    assert pick_hex(board, origin, direction, HEIGHT, THICKNESS) == "H0"


def test_the_side_of_a_hill_hides_the_low_hex_behind_it():
    # H0 is level 0 at x=0, H1 is a level 4 hill at x=6, H2 is level 0 at x=12. A flat ray
    # from the east at a height below the hill top, aimed at the top of H0, hits the side of
    # H1 first. Without the side faces it would pass through the hill.
    board = _row([0, 4, 0])
    z = 4 * HEIGHT * 0.5
    origin = (30.0, 0.0, z)
    target = (0.0, 0.0, 0.0)
    direction = tuple(t - o for t, o in zip(target, origin))
    length = math.sqrt(sum(d * d for d in direction))
    direction = tuple(d / length for d in direction)
    assert pick_hex(board, origin, direction, HEIGHT, THICKNESS) == "H1"


def test_the_nearest_top_wins_over_a_top_behind_it():
    # The ray goes down at a slant over two hexes at the same level. It enters the board top
    # only once, at the first hex it reaches.
    board = _row([1, 1])
    z = HEIGHT
    target = (6.0, 0.0, z)
    direction = (0.3, 0.0, -1.0)
    origin = tuple(t - d * 20 for t, d in zip(target, direction))
    assert pick_hex(board, origin, direction, HEIGHT, THICKNESS) == "H1"


def test_north_is_at_the_top_of_the_world_and_the_corners_go_counterclockwise():
    """Row 1 is north of row 2 on the 2D board, so it has the higher world y. A mirror of the
    board reads each hex label backwards."""
    board = board_document(build_engine("s01_guards_counterattack", None).board)
    by_id = {h["id"]: h for h in board["hexes"]}
    north = world_xy(*by_id["A1"]["center"])
    south = world_xy(*by_id["A2"]["center"])
    assert north[1] > south[1]
    corners = hex_corners(by_id["A1"])
    area = sum(corners[i][0] * corners[(i + 1) % 6][1] - corners[(i + 1) % 6][0] * corners[i][1] for i in range(6))
    assert area > 0
