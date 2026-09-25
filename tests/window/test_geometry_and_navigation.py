"""The shape of a hex on the screen, and moving around the board.

The window drew every hexagon squashed for one slice: the camera multiplied the y value of
the lattice by the square root of three over two, and the constant is the square root of
three. `test_every_side_of_a_hexagon_is_the_same_length` is the measurement that finds it.
"""

from __future__ import annotations

import math
import os
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slcore import geometry  # noqa: E402
from slwindow import layout, render  # noqa: E402
from slwindow.app import PAN_STEP, Window  # noqa: E402
from slwindow.client import GameView, HostClient  # noqa: E402


def sides(points):
    return [math.dist(points[i], points[(i + 1) % len(points)]) for i in range(len(points))]


def a_window(size=(400, 300)) -> Window:
    pygame.init()
    return Window(HostClient("ws://127.0.0.1:1/", "none"), size=size, caption="test")


def press(key: int, mod: int = 0) -> pygame.event.Event:
    return pygame.event.Event(pygame.KEYDOWN, key=key, unicode="", mod=mod)


# --------------------------------------------------------------------- the shape


@pytest.mark.parametrize("scale", (4.0, 12.0, 37.5))
def test_every_side_of_a_hexagon_is_the_same_length(scale: float):
    camera = layout.Camera(scale=scale)
    for ref in ((0, 0), (3, 7), (12, 2)):
        points = layout.hex_corners(geometry.center(*ref), camera)
        lengths = sides(points)
        assert max(lengths) - min(lengths) < 1e-9, f"the sides are {lengths}"
        assert abs(lengths[0] - 2 * scale) < 1e-9, "a side is two units of the lattice"


def test_every_vertex_of_a_hexagon_is_the_same_distance_from_its_centre():
    camera = layout.Camera(scale=20.0)
    centre = camera.to_screen(*geometry.center(4, 4))
    points = layout.hex_corners(geometry.center(4, 4), camera)
    far = [math.dist(centre, p) for p in points]
    assert max(far) - min(far) < 1e-9, f"the vertices are {far} from the centre"


def test_two_hexes_that_touch_are_drawn_touching():
    camera = layout.Camera(scale=16.0)
    for direction in range(6):
        here = (4, 4)
        there = geometry.neighbor(*here, direction)
        a = camera.to_screen(*geometry.center(*here))
        b = camera.to_screen(*geometry.center(*there))
        # Two hexes that touch have their centres two short radii apart, and a short
        # radius is the square root of three times the scale.
        assert abs(math.dist(a, b) - 2 * layout.ROOT_THREE * camera.scale) < 1e-9


def test_the_window_uses_the_same_constant_as_the_browser_client():
    source = Path("client/src/board/geometry.ts").read_text(encoding="utf-8")
    assert "export const ROOT_THREE = Math.sqrt(3);" in source
    assert abs(layout.ROOT_THREE - math.sqrt(3)) < 1e-12


# ---------------------------------------------------------------- zoom and scroll


def test_zoom_holds_the_point_under_the_pointer():
    camera = layout.Camera(scale=10.0, offset_x=100.0, offset_y=50.0)
    anchor = (321.0, 214.0)
    before = camera.to_lattice(*anchor)
    for factor in (1.12, 1.12, 1 / 1.12, 0.5, 2.0):
        camera = camera.zoomed(factor, anchor)
        after = camera.to_lattice(*anchor)
        assert abs(after[0] - before[0]) < 1e-9
        assert abs(after[1] - before[1]) < 1e-9


def test_zoom_stops_at_the_two_limits():
    camera = layout.Camera(scale=layout.DEFAULT_SCALE)
    for _ in range(80):
        camera = camera.zoomed(1.2, (0.0, 0.0))
    assert camera.scale == layout.MAX_SCALE
    for _ in range(80):
        camera = camera.zoomed(1 / 1.2, (0.0, 0.0))
    assert camera.scale == layout.MIN_SCALE


def test_a_pan_moves_the_board_and_keeps_its_size():
    camera = layout.Camera(scale=14.0)
    moved = camera.panned(-40.0, 25.0)
    assert moved.scale == camera.scale
    assert (moved.offset_x, moved.offset_y) == (camera.offset_x - 40.0, camera.offset_y + 25.0)


def test_the_four_arrow_keys_move_the_board_in_four_directions():
    window = a_window()
    snapshot = GameView()
    start = window.state.camera
    moves = {
        pygame.K_LEFT: (PAN_STEP, 0.0),
        pygame.K_RIGHT: (-PAN_STEP, 0.0),
        pygame.K_UP: (0.0, PAN_STEP),
        pygame.K_DOWN: (0.0, -PAN_STEP),
    }
    for key, (dx, dy) in moves.items():
        window.state.camera = start
        window.key(press(key), snapshot)
        assert window.state.camera.offset_x == start.offset_x + dx, key
        assert window.state.camera.offset_y == start.offset_y + dy, key
    pygame.quit()


def test_a_drag_moves_the_board_and_is_not_a_click():
    window = a_window()
    snapshot = GameView()
    start = window.state.camera
    window.handle(pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=(50, 50)), snapshot)
    window.handle(
        pygame.event.Event(pygame.MOUSEMOTION, rel=(30, -20), pos=(80, 30), buttons=(1, 0, 0)), snapshot
    )
    window.handle(pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(80, 30)), snapshot)
    assert window.state.camera.offset_x == start.offset_x + 30
    assert window.state.camera.offset_y == start.offset_y - 20
    assert window.state.selected_hex is None, "a drag is not a click"
    pygame.quit()


def test_the_page_keys_move_the_command_cursor_and_the_arrows_do_not():
    window = a_window()
    snapshot = GameView(legal=[{"id": "a", "payload": {}}, {"id": "b", "payload": {}}])
    window.key(press(pygame.K_PAGEDOWN), snapshot)
    assert window.chooser.position == 1
    window.key(press(pygame.K_PAGEUP), snapshot)
    assert window.chooser.position == 0
    window.key(press(pygame.K_DOWN), snapshot)
    assert window.chooser.position == 0, "the arrow keys move the board and not the list"
    pygame.quit()


# ------------------------------------------------------------------- the roads


def road_board(seed: int = 101, board_type: str = "city") -> dict:
    from slboards.generator import GeneratorParameters, generate_with_retry
    from slcore import view as core_view
    from sldata.loaders import load_terrain

    board, _ = generate_with_retry(
        GeneratorParameters(seed=seed, board_type=board_type, cols=25, rows=10), load_terrain()
    )
    return core_view.board_document(board)


def test_a_road_that_goes_straight_through_a_hex_is_drawn():
    board = road_board()
    links = {frozenset(p) for p in render._road_links(board)}
    centres = {tuple(h["center"]) for h in board["hexes"] if h.get("road")}
    straight = 0
    for centre in centres:
        for dx, dy in render.STEPS:
            near = (centre[0] + dx, centre[1] + dy)
            back = (centre[0] - dx, centre[1] - dy)
            if near in centres and back in centres:
                straight += 1
                assert frozenset((centre, near)) in links, f"{centre} to {near} is a through road"
    assert straight > 20, "this board has too few through roads to prove anything"


def test_no_stroke_cuts_the_corner_of_a_junction():
    """A link between two road hexes that a third road hex joins is not drawn."""
    board = road_board()
    links = {frozenset(p) for p in render._road_links(board)}
    joined: dict[tuple, set] = {}
    for pair in links:
        a, b = tuple(pair)
        joined.setdefault(a, set()).add(b)
        joined.setdefault(b, set()).add(a)
    for pair in links:
        a, b = tuple(pair)
        through = [c for c in joined[a] if c != b and b in joined.get(c, ())]
        assert not through, f"{sorted(pair)} is drawn and {through[0]} already joins the two"


def test_every_road_hex_is_on_the_drawn_network():
    board = road_board()
    drawn = {ref for pair in render._road_links(board) for ref in pair}
    roads = {tuple(h["center"]) for h in board["hexes"] if h.get("road")}
    assert roads - drawn == set(), "a road hex is on the board and no stroke reaches it"
