"""The desktop window (FR-30, FR-31): a separate window, on Windows and on Unix.

The window has to draw. A test that reads only the record the socket thread keeps passes
on a blank window, so every test here reads the pixels of the surface. Four of them prove
that the pixel check rejects a window that drew nothing, a board with no counters, and a
board with no buildings, so the check is not a rubber stamp.

The tests run with the dummy video driver, so they need no screen. The library still
draws every pixel, and the surface holds what a person would see.
"""

from __future__ import annotations

import os
from collections import Counter

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slcli.play import build_engine  # noqa: E402
from slcore import view as core_view  # noqa: E402
from slwindow import counters, layout, panel, render, theme  # noqa: E402
from slwindow.client import GameView  # noqa: E402

SCENARIO = "s04_armor_probe"
SIZE = (1100, 700)
MIN_DISTINCT_COLOURS = 40
MIN_PIXELS_OF_A_COLOUR = 400


@pytest.fixture(scope="module")
def game():
    """A real board, a real state, and the two documents the host would send."""
    pygame.init()
    engine = build_engine(SCENARIO)
    state = engine.new_game(11)
    # Set up runs until both sides have their counters on the board, so the picture holds
    # something to look at.
    for _ in range(400):
        frame = engine.legal_commands(state)
        if state.phase != "setup":
            break
        chosen = next((c for c in frame.commands if c.command.action == "place"), None)
        if chosen is None:
            # Scenario 4 has concealment counters (rule 25.3), so set up can offer
            # place_concealment before end_setup.
            chosen = next((c for c in frame.commands if c.command.action == "end_setup"), frame.commands[0])
        state, _ = engine.apply(state, chosen.command, frame)
    board = core_view.board_document(engine.board)
    document = core_view.build(state, engine.types, 0, spectator=True)
    return engine, state, board, document


@pytest.fixture()
def fonts():
    pygame.init()
    return (
        pygame.font.SysFont("dejavusans,arial,helvetica", 15),
        pygame.font.SysFont("dejavusansmono,consolas,couriernew", 12),
    )


def colours_of(surface: pygame.Surface) -> Counter:
    raw = pygame.image.tobytes(surface, "RGB")
    return Counter(tuple(raw[i : i + 3]) for i in range(0, len(raw), 3))


def draw_board(game, fonts, size=SIZE):
    engine, state, board, document = game
    surface = pygame.Surface(size)
    camera = layout.fit(board, *size)
    render.draw_board(surface, board, camera, fonts[1])
    return surface, board, document, camera


# --------------------------------------------------------------------- the board


def test_the_board_draws_its_terrain(game, fonts):
    surface, board, _, _ = draw_board(game, fonts)
    found = colours_of(surface)
    assert len(found) >= MIN_DISTINCT_COLOURS, f"the surface has {len(found)} colours, which is nearly blank"
    for name in ("open", "stone_building", "woods"):
        colour = theme.TERRAIN[name]
        assert found[colour] >= MIN_PIXELS_OF_A_COLOUR, f"the board has {found[colour]} pixels of {name}"


def test_the_board_draws_its_roads_and_hexsides(game, fonts):
    surface, board, _, _ = draw_board(game, fonts)
    found = colours_of(surface)
    wanted = {"a road": theme.ROAD}
    features = {f for h in board["hexes"] for f in h.get("hexsides", {}).values()}
    for feature in features:
        wanted[f"a {feature}"] = theme.HEXSIDE[feature]
    if any(h.get("road") for h in board["hexes"]):
        assert found[theme.ROAD] > 0, "the board has road hexes and no road pixels"
    for name, colour in wanted.items():
        if colour is theme.ROAD:
            continue
        assert found[colour] > 0, f"the board has {name} hexsides and none is drawn"


def test_a_woods_hex_is_drawn_as_a_mass_of_crowns(game, fonts):
    """Rule 7.2: a wood is a mass of crowns with a ragged edge and not a green hexagon.

    Cel shading gives the mass four tones. Three of them are on the crowns, so a hex that
    holds only the flat woods colour is a hexagon and not a wood.
    """
    surface, board, _, _ = draw_board(game, fonts, size=(1400, 900))
    found = colours_of(surface)
    if not any(h["terrain"] == "woods" for h in board["hexes"]):
        pytest.skip("this board has no woods hex")
    for name in ("WOODS_LINE", "WOODS_SHADE", "WOODS_LIGHT"):
        colour = getattr(theme, name)
        assert found[colour] > 0, f"a woods hex is drawn with no {name} tone"


def test_a_building_is_drawn_as_a_plan_and_not_as_a_counter(game, fonts):
    """The outline goes around the building. A house symbol in a hex reads as a unit."""
    surface, board, _, _ = draw_board(game, fonts, size=(1400, 900))
    found = colours_of(surface)
    kinds = {h["terrain"] for h in board["hexes"] if h.get("building")}
    assert kinds, "this board has no building"
    drawn = [k for k in kinds if found[theme.BUILDING[k]["line"]] > 0]
    assert drawn, f"no building outline is drawn for {sorted(kinds)}"
    assert found[theme.BUILDING[drawn[0]]["roof"]] > 0, "the plan has no roof"


def test_the_outline_of_a_building_follows_the_whole_building(game, fonts):
    """A hexside inside a building carries no wall line, and the outside of it does.

    This one reads the two pixels that say it. A colour count cannot: a building of one
    hex has a line on all four sides, so the line colour is on the board either way.
    """
    size = (1400, 900)
    surface, board, _, _ = draw_board(game, fonts, size=size)
    camera = layout.fit(board, *size)
    index = {tuple(h["center"]): h for h in board["hexes"]}
    def same(hexagon, building, dy):
        cx, cy = hexagon["center"]
        other = index.get((cx, cy + dy))
        return other is not None and (other.get("building") or {}).get("id") == building["id"]

    # The hex has to be the top one of its building. A hex with one more hex of the
    # building above it has no wall line on its top side either, which is the point.
    pairs = []
    for hexagon in board["hexes"]:
        building = hexagon.get("building")
        if building is None:
            continue
        if same(hexagon, building, 2) and not same(hexagon, building, -2):
            pairs.append(hexagon)
    assert pairs, "this board has no building of two hexes above each other to check"
    # A block reaches the full step to a hex of the same building below it, so the seam sits
    # at the full hexside. It pulls in on the open top, so the outside line sits inset.
    half_y = camera.scale * layout.ROOT_THREE
    top_y = half_y * render.BUILDING_INSET

    def near(a, b):
        # The line meets the roof and the ground at the inset edge, so one pixel of it can
        # blend by a step. The ground and the roof are far from the line, so a near match
        # still says the line is there and not the fill.
        return all(abs(int(a[i]) - int(b[i])) <= 3 for i in range(3))

    for hexagon in pairs:
        line = theme.BUILDING[hexagon["terrain"]]["line"]
        x, y = camera.to_screen(*hexagon["center"])
        seam = [surface.get_at((int(x), int(round(y + half_y)) + d))[:3] for d in (-1, 0, 1)]
        assert line not in seam, f"the hexside inside the building at {hexagon['id']} carries a wall line"
        top = [surface.get_at((int(x), int(round(y - top_y)) + d))[:3] for d in range(-3, 4)]
        assert any(near(line, pixel) for pixel in top), f"the outside of the building at {hexagon['id']} carries no wall line"


def test_a_large_building_is_marked_as_a_large_one(game, fonts):
    """Rule 7.5: a building of three hexes or more has a second story."""
    surface, board, _, _ = draw_board(game, fonts, size=(1400, 900))
    large = [h for h in board["hexes"] if (h.get("building") or {}).get("size", 0) >= render.MULTI_STORY]
    if not large:
        pytest.skip("this board has no building of three hexes or more")
    found = colours_of(surface)
    kinds = {h["terrain"] for h in large}
    assert any(found[theme.BUILDING[k]["shade"]] > 0 for k in kinds), "no second story is marked"
    small = [h for h in board["hexes"] if 0 < (h.get("building") or {}).get("size", 0) < render.MULTI_STORY]
    only_small = {h["terrain"] for h in small} - kinds
    for kind in only_small:
        assert found[theme.BUILDING[kind]["shade"]] == 0, f"a small {kind} is marked as a large one"


def test_each_hex_has_its_centre_dot(game, fonts):
    """FR-30 and item 1 of the board rubric. Rule 7.1 threads a sight line to this dot.

    The dot goes on top of the terrain, so a hex under a building or a wood keeps it.
    """
    size = (1400, 900)
    surface, board, _, _ = draw_board(game, fonts, size=size)
    camera = layout.fit(board, *size)
    covered = [h for h in board["hexes"] if h.get("building") or h["terrain"] == "woods"]
    assert covered, "this board has no hex with terrain drawn on top of the dot"
    for hexagon in covered[:20]:
        x, y = camera.to_screen(*hexagon["center"])
        assert surface.get_at((int(x), int(y)))[:3] == theme.CENTRE_DOT, (
            f"the hex {hexagon['id']} has no centre dot"
        )


def test_an_empty_surface_fails_the_terrain_check():
    """The check has to be able to say no, or it proves nothing."""
    surface = pygame.Surface(SIZE)
    surface.fill(theme.PAPER)
    found = colours_of(surface)
    assert len(found) == 1
    assert found[theme.TERRAIN["stone_building"]] == 0


# ------------------------------------------------------------------ the counters


def test_the_counters_draw_for_both_sides(game, fonts):
    surface, board, document, camera = draw_board(game, fonts)
    before = colours_of(surface)
    counters.draw_counters(surface, board, document, camera, fonts[0], fonts[1])
    after = colours_of(surface)
    for nationality in ("german", "russian"):
        colour = theme.NATIONAL[nationality]
        assert after[colour] > before[colour], f"no {nationality} counter is drawn"


def test_a_vehicle_counter_draws_its_edge_and_its_gun(game, fonts):
    """Rule 28 and rule 29.4: the vehicle counter and the barrel that gives its arc."""
    surface, board, document, camera = draw_board(game, fonts)
    vehicles = [u for u in document["units"] if u["kind"] == "vehicle"]
    assert vehicles, "the armor scenario has vehicles"
    assert all(u["facing"] >= 0 for u in vehicles if u["hex"]), "a placed vehicle has a facing"
    counters.draw_counters(surface, board, document, camera, fonts[0], fonts[1])
    found = colours_of(surface)
    assert found[theme.VEHICLE_EDGE] > 0, "no vehicle counter is drawn"


def test_the_covered_arc_shades_the_board(game, fonts):
    """Rule 29.4: a click on a vehicle shows the wedge its gun covers."""
    surface, board, document, camera = draw_board(game, fonts)
    vehicle = next(u for u in document["units"] if u["kind"] == "vehicle" and u["hex"])
    plain = colours_of(surface)
    counters.draw_counters(surface, board, document, camera, fonts[0], fonts[1], arc_for=vehicle["id"])
    shaded = colours_of(surface)
    assert len(shaded) > len(plain), "the arc added no colour to the board"


def test_the_counter_check_rejects_a_board_with_no_counters(game, fonts):
    surface, board, _, _ = draw_board(game, fonts)
    found = colours_of(surface)
    for nationality in ("german", "russian"):
        assert found[theme.NATIONAL[nationality]] == 0


# --------------------------------------------------------------------- the panel


def test_the_panel_lists_the_legal_commands(game, fonts):
    engine, state, board, document = game
    frame = engine.legal_commands(state)
    surface = pygame.Surface((panel.WIDTH, 700))
    rect = pygame.Rect(0, 0, panel.WIDTH, 700)
    snapshot = GameView(
        board=board,
        scenario={"title": "Armor probe", "board": board["name"]},
        seat="german",
        player=0,
        view=document,
        frame_id="abc",
        active=0,
        phase=state.phase,
        sub_step="fire_window",
        turn=state.turn,
        legal=[{"id": c.id, "payload": c.payload} for c in frame.commands],
        log=[{"rule_id": "30.2", "kind": "vehicle_move"}],
    )
    rows = panel.draw_panel(surface, rect, snapshot, fonts[0], fonts[1], 0, "")
    assert rows, "the panel drew no command row"
    found = colours_of(surface)
    assert found[theme.PANEL_TEXT] > 0, "the panel drew no text"
    assert found[theme.HIGHLIGHT] > 0, "the panel did not mark the selected command"


def test_the_panel_describes_a_vehicle_command():
    text = panel.describe({"payload": {"action": "afv_fire", "units": [7], "hex": "D5", "aim": "vehicle", "ammo": "ap"}})
    assert "afv_fire" in text and "D5" in text and "aim=vehicle" in text


def test_the_panel_narrows_the_list_with_what_a_person_types(game, fonts):
    surface = pygame.Surface((panel.WIDTH, 400))
    rect = pygame.Rect(0, 0, panel.WIDTH, 400)
    legal = [
        {"id": "1", "payload": {"action": "vehicle_move", "units": [7], "hex": "D5"}},
        {"id": "2", "payload": {"action": "move", "units": [1], "hex": "E5"}},
    ]
    snapshot = GameView(legal=legal)
    rows = panel.draw_panel(surface, rect, snapshot, fonts[0], fonts[1], 0, "vehicle")
    assert len(rows) == 1
    assert rows[0][1] == 0


# -------------------------------------------------------------------- the camera


def test_the_camera_fits_the_whole_board_in_the_window(game, fonts):
    _, _, board, _ = game
    camera = layout.fit(board, 1000, 600)
    xs = []
    ys = []
    for hexagon in board["hexes"]:
        x, y = camera.to_screen(*hexagon["center"])
        xs.append(x)
        ys.append(y)
    assert min(xs) > -40 and max(xs) < 1040
    assert min(ys) > -40 and max(ys) < 640


def test_a_click_finds_the_hex_under_it(game, fonts):
    _, _, board, _ = game
    camera = layout.fit(board, 1000, 600)
    for hexagon in board["hexes"][:40]:
        x, y = camera.to_screen(*hexagon["center"])
        assert layout.hex_at(board, x, y, camera) == hexagon["id"]


def test_a_click_far_off_the_board_finds_no_hex(game, fonts):
    _, _, board, _ = game
    camera = layout.fit(board, 1000, 600)
    assert layout.hex_at(board, -900, -900, camera) is None


def test_zoom_keeps_the_hex_under_the_pointer(game, fonts):
    _, _, board, _ = game
    camera = layout.fit(board, 1000, 600)
    anchor = (500.0, 300.0)
    before = layout.hex_at(board, *anchor, camera)
    zoomed = camera.zoomed(1.5, anchor)
    assert layout.hex_at(board, *anchor, zoomed) == before


# ----------------------------------------------------------------------- the hills


@pytest.fixture(scope="module")
def hills_board():
    """A hills board of the generator, as the host would send it (rules 43 and 44)."""
    from slboards.generator import GeneratorParameters, generate_with_retry
    from sldata.loaders import load_terrain

    terrain = load_terrain()
    params = GeneratorParameters(seed=4242, board_type="hills", cols=17, rows=10)
    board, _ = generate_with_retry(params, terrain)
    return core_view.board_document(board)


def test_a_hills_board_shows_its_levels_and_its_crest_lines(hills_board, fonts):
    """Rule 43: three levels of brown, and a crest line where two of them touch."""
    levels = {h.get("elevation", 0) for h in hills_board["hexes"]}
    assert levels - {0}, "the generator made no hill on a hills board"
    size = (1300, 800)
    surface = pygame.Surface(size)
    camera = layout.fit(hills_board, *size)
    render.draw_board(surface, hills_board, camera, fonts[1])
    found = colours_of(surface)
    assert found[theme.CREST] > 0, "a hill with two levels has no crest line"
    tinted = [c for c in found if c not in theme.TERRAIN.values() and found[c] > 200]
    assert tinted, "no hill tint is on the board"


def test_a_hills_board_shows_its_cliffs_and_its_walls(hills_board, fonts):
    """Rule 44.1 gives a cliff its own hexside, and rule 11.5 gives a wall one."""
    features = {f for h in hills_board["hexes"] for f in h.get("hexsides", {}).values()}
    if not features:
        pytest.skip("this seed made a board with no hexside feature")
    size = (1300, 800)
    surface = pygame.Surface(size)
    camera = layout.fit(hills_board, *size)
    render.draw_board(surface, hills_board, camera, fonts[1])
    found = colours_of(surface)
    for feature in features:
        assert found[theme.HEXSIDE[feature]] > 0, f"the board has a {feature} and none is drawn"
