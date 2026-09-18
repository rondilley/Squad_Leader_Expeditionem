"""The counter faces of RV-10 (FR-31, SR-07).

A counter prints what the 1977 counter prints, in the project's own art: two men and one
line of numbers for a squad, one man with the value up the side for a leader, an icon and
three lines for a weapon, a plan turned to the facing for a vehicle, and the back of each.
Each test here reads the pixels of a face, because a test that reads only the code path
passes on a blank chit.

The tests run with the dummy video driver, so they need no screen.
"""

from __future__ import annotations

import os
from collections import Counter
from typing import Any

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the desktop window needs the `desktop` extra")

from slcli.play import build_engine  # noqa: E402
from slcore import view as core_view  # noqa: E402
from slwindow import counters, silhouettes, theme  # noqa: E402

SIZE = 96
GROUND = (150, 168, 120)


def unit(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = dict(
        id=7, player=0, nationality="german", kind="squad", broken=False, berserk=False,
        prep_fired=False, moved=False, malfunction=False, dm=False, name="", firepower=4,
        range=6, morale=7, leadership=0, own=True, hex="A1", carrier=None, riding=None,
        type="4-6-7", elite=False,
    )
    base.update(fields)
    return base


def vehicle(**fields: Any) -> dict[str, Any]:
    base = unit(
        kind="vehicle", type="MkIVF2", vehicle_class="tank", facing=0, wreck=False,
        immobilized=False, crew_exposed=False, gun=75, movement_points=12, mg_ca=4, mg_360=2,
        open_top=False, transport_pp=0, gun_he_only=False, gun_low_velocity=False, survival=5,
    )
    base.update(fields)
    return base


@pytest.fixture(scope="module")
def fonts():
    pygame.init()
    font = pygame.font.SysFont("dejavusans,arial,helvetica", 15)
    return font, font


def draw(item: dict[str, Any], fonts, size: int = SIZE) -> pygame.Surface:
    """One counter on a plain ground, at the middle of a small surface."""
    side = int(size * 1.6)
    surface = pygame.Surface((side, side))
    surface.fill(GROUND)
    if item["kind"] == "vehicle":
        counters._vehicle(surface, item, side / 2, side / 2, size, *fonts)
    else:
        counters._counter(surface, item, side / 2, side / 2, size, *fonts)
    return surface


def colours(surface: pygame.Surface, box: pygame.Rect | None = None) -> Counter:
    region = surface if box is None else surface.subsurface(box)
    width, height = region.get_size()
    return Counter(region.get_at((x, y))[:3] for x in range(width) for y in range(height))


def face_of(surface: pygame.Surface, size: int = SIZE) -> pygame.Rect:
    side = surface.get_width()
    return pygame.Rect(int(side / 2 - size / 2), int(side / 2 - size / 2), size, size)


# ---------------------------------------------------------------------- the choice


def test_a_line_squad_walks_and_an_elite_squad_or_a_crew_runs():
    """RV-10 section 3: the pose of the men gives the type of the squad."""
    assert silhouettes.figure_for("squad") == "rifleman_walk"
    assert silhouettes.figure_for("squad", elite=True) == "runner_smg"
    assert silhouettes.figure_for("crew") == "runner_smg"
    assert silhouettes.figure_for("leader") == "leader_stand"


def test_each_weapon_of_the_counter_data_has_an_icon():
    """Each support weapon type of the three armies maps to an icon of its own class."""
    engine = build_engine("s04_armor_probe")
    seen = set()
    for key, t in engine.types.items():
        if t.kind != "sw":
            continue
        icon = silhouettes.icon_for(key.split(":")[-1], t.weapon_class)
        assert icon in silhouettes.ICONS, key
        seen.add(icon)
    assert {"mg_light", "mg_medium", "mg_heavy"} <= seen


def test_the_russian_men_face_right_and_the_other_men_face_left():
    assert "russian" in counters.FACES_RIGHT
    assert "german" not in counters.FACES_RIGHT and "american" not in counters.FACES_RIGHT


# ----------------------------------------------------------------------- the faces


def test_a_squad_prints_its_men_above_its_value_line(fonts):
    """RV-10 section 3: the men fill the top half of the face, the numbers the bottom third."""
    surface = draw(unit(), fonts)
    face = face_of(surface)
    top = colours(surface, pygame.Rect(face.left, face.top, face.width, face.height // 2))
    bottom = colours(surface, pygame.Rect(face.left, face.top + int(face.height * 0.6), face.width, int(face.height * 0.36)))
    assert top[theme.INK] > 40, "no men in the top half of the squad face"
    assert bottom[theme.INK] > 40, "no value line in the bottom of the squad face"


def test_a_leader_prints_its_value_up_the_right_edge(fonts):
    """RV-10 section 3: one man at the left, the value in large text up the right edge."""
    surface = draw(unit(kind="leader", morale=9, leadership=-1, name="Sgt Kelso", type="9-1"), fonts)
    face = face_of(surface)
    left = colours(surface, pygame.Rect(face.left, face.top, int(face.width * 0.42), face.height))
    right = colours(surface, pygame.Rect(face.left + int(face.width * 0.62), face.top, int(face.width * 0.34), face.height))
    assert left[theme.INK] > 40, "no man at the left of the leader face"
    assert right[theme.INK] > 40, "no value up the right edge of the leader face"


def test_a_weapon_prints_its_icon_at_the_left_and_its_lines_at_the_right(fonts):
    surface = draw(unit(kind="sw", type="LMG", firepower=2, range=8, breakdown=12, weapon_class="mg"), fonts)
    face = face_of(surface)
    left = colours(surface, pygame.Rect(face.left, face.top, int(face.width * 0.42), face.height))
    right = colours(surface, pygame.Rect(face.left + int(face.width * 0.44), face.top, int(face.width * 0.52), face.height))
    assert left[theme.INK] > 30, "no icon at the left of the weapon face"
    assert right[theme.INK] > 60, "no lines at the right of the weapon face"


def test_a_weapon_is_on_the_stock_of_its_army(fonts):
    """RV-10 section 2: a support weapon is not a colour of its own."""
    for army in ("german", "russian", "american"):
        surface = draw(unit(kind="sw", type="MMG", nationality=army, firepower=4, range=12, breakdown=12, weapon_class="mg"), fonts)
        assert colours(surface)[theme.NATIONAL[army]] > 500, army


def test_a_berserk_squad_is_on_the_red_stock(fonts):
    calm = colours(draw(unit(nationality="russian", type="4-4-7", range=4), fonts))
    mad = colours(draw(unit(nationality="russian", type="4-4-7", range=4, berserk=True), fonts))
    assert mad[theme.BERSERK] > 500 and calm[theme.BERSERK] == 0


# ------------------------------------------------------------------------ the backs


def test_a_broken_squad_turns_to_its_back_on_the_same_stock(fonts):
    """Rule 12 and RV-10 section 5: the same stock, the word, the number, the men down."""
    front = draw(unit(), fonts)
    back = draw(unit(broken=True), fonts)
    face = face_of(front)
    assert colours(back)[theme.NATIONAL["german"]] > 500, "the back left the stock of its army"
    top_front = colours(front, pygame.Rect(face.left, face.top, face.width, face.height // 3))
    top_back = colours(back, pygame.Rect(face.left, face.top, face.width, face.height // 3))
    assert top_front != top_back, "the back prints the same as the front"
    lower = colours(back, pygame.Rect(face.left, face.top + int(face.height * 0.56), face.width, int(face.height * 0.40)))
    assert lower[theme.INK] > 40, "no men down on the back"


def test_a_weapon_with_a_malfunction_shows_the_white_cross(fonts):
    """Rule 18.1 and RV-10 section 5: the icon below a white cross with R1 and X6."""
    sound = colours(draw(unit(kind="sw", type="LMG", firepower=2, range=8, breakdown=12, weapon_class="mg"), fonts))
    broken = colours(draw(unit(kind="sw", type="LMG", firepower=2, range=8, breakdown=12, weapon_class="mg", malfunction=True), fonts))
    assert sum(n for c, n in broken.items() if c[0] > 215 and c[1] > 210 and c[2] > 195) > 300, "no white cross"
    assert sum(n for c, n in sound.items() if c[0] > 215 and c[1] > 210 and c[2] > 195) < 60


def test_a_small_turned_counter_is_darker_than_its_front(fonts):
    """Below the symbol size a turned counter has no print, so its tone carries the state."""
    small = counters.SYMBOL_MIN - 2
    front = colours(draw(unit(), fonts, small))
    back = colours(draw(unit(broken=True), fonts, small))
    assert front[theme.NATIONAL["german"]] > 0
    assert back[theme.NATIONAL["german"]] == 0
    assert back[counters._darken(theme.NATIONAL["german"], theme.BACK_SHADE)] > 0


# --------------------------------------------------------------------- the vehicles


def test_a_closed_tank_is_a_dark_plan_with_a_turret_band(fonts):
    """Rule 28 and RV-10 section 7: a black plan, a white band round the turret."""
    found = colours(draw(vehicle(), fonts))
    assert found[theme.INK] > 400, "no dark plan"
    assert found[theme.TURRET_BAND] > 30, "no turret band"


def test_an_open_top_vehicle_is_a_light_plan(fonts):
    closed = colours(draw(vehicle(), fonts))
    open_top = colours(draw(vehicle(type="SdKfz251", vehicle_class="halftrack", open_top=True, gun=0, transport_pp=5, mg_ca=0, mg_360=4), fonts))
    assert open_top[theme.OPEN_TOP] > closed[theme.OPEN_TOP] + 300, "the open top plan is not light"


def test_the_plan_turns_to_the_facing(fonts):
    """Rule 29.4: the barrel lies along the spine, so the ink of the plan leans that way."""
    def ink_centre(facing: int) -> tuple[float, float]:
        surface = draw(vehicle(facing=facing, gun=0, movement_points=0, mg_ca=0, mg_360=0, type=""), fonts)
        face = face_of(surface, int(SIZE * counters.VEHICLE_SCALE))
        xs, ys, n = 0.0, 0.0, 0
        for x in range(face.left, face.right):
            for y in range(face.top, face.bottom):
                if surface.get_at((x, y))[:3] == theme.INK:
                    xs += x
                    ys += y
                    n += 1
        assert n > 0
        return xs / n - face.centerx, ys / n - face.centery

    # The movement points print at the top right in both, so the two centres are compared
    # with each other and not with the middle of the face.
    east_x, _ = ink_centre(0)
    west_x, _ = ink_centre(3)
    assert east_x - west_x > 1.0, (east_x, west_x)
    _, north_y = ink_centre(5)
    _, south_y = ink_centre(2)
    assert south_y - north_y > 1.0, (north_y, south_y)


def test_a_wreck_is_the_white_back_with_its_survival_number(fonts):
    found = colours(draw(vehicle(wreck=True), fonts))
    assert found[theme.MARKER] > 800, "the wreck is not on the white back"
    assert found[theme.WRECK] > 100, "no burnt out plan"


# ------------------------------------------------------------------------- the view


def test_the_view_gives_each_face_its_printed_fields():
    """The host sends what the front of the piece prints, and nothing else new (AR-09)."""
    engine = build_engine("s04_armor_probe")
    state = engine.new_game(3)
    document = core_view.build(state, engine.types, 0, spectator=True)
    assert document["nationalities"] == {"0": "german", "1": "russian"}
    kinds = {u["kind"]: u for u in document["units"]}
    assert "elite" in kinds["squad"] and "breakdown" not in kinds["squad"]
    assert "breakdown" in kinds["sw"] and "weapon_class" in kinds["sw"]
    for key in ("vehicle_class", "open_top", "transport_pp", "mg_ca", "mg_360", "gun_he_only", "gun_low_velocity", "survival"):
        assert key in kinds["vehicle"], key
    assert "elite" not in kinds["leader"]
