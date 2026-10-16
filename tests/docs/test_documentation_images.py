"""The pictures in the documentation are this project's own output (SR-07, TC-29).

`docs/images/` is the one directory of the tree that holds an image. The rule that keeps a
scan out of it is not a promise in a document: this file makes each picture again from
`tools/make_docs_images.py` and compares it with the file in the tree. A picture that a
person put there by hand does not pass.

The comparison reads the flat colours of the terrain. Those come from a polygon fill and a
rectangle fill, so they do not move with the font that the machine has. The text of the hex
labels and of the panel covers a few of those pixels, so the count has a small tolerance.
A scan or a photograph of anything is nowhere near that tolerance.

A game picture is a render of the 3D window, with light and shade, so it has no flat colour
to count. Its comparison is the mean difference of each pixel from the picture in the tree.
"""

from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

pygame = pytest.importorskip("pygame", reason="the pictures need the `desktop` extra")

from slwindow import theme  # noqa: E402

import tools.make_docs_images as maker  # noqa: E402

IMAGES = Path("docs") / "images"
MANIFEST = IMAGES / "MANIFEST.json"
# One percent. The text of the labels is the only thing that moves with the machine.
TOLERANCE = 0.01
# The mean difference of a channel, of 255, that the board area of a game picture may have.
# The edges of the render move with the graphics driver of the machine. On the machine that
# made the pictures, a new render differs by 0.0, and the 2D and the 3D picture by 11.3.
RENDER_TOLERANCE = 2.5
# The board area is left of the panel. The panel is the same in the 2D and the 3D picture.
BOARD_WIDTH = 1440 - 360

BOARDS = [spec for spec in maker.PICTURES if not spec.scenario]
GAMES = [spec for spec in maker.PICTURES if spec.scenario]

pytestmark = pytest.mark.skipif(not MANIFEST.is_file(), reason="the pictures are not made")


def flat_colours() -> tuple[tuple[int, int, int], ...]:
    """The colours that come from a fill, and not from a letter or an edge."""
    out = [theme.GROUND, theme.GRAIN, theme.WOODS, theme.SHELLHOLE, theme.ROAD, theme.PAPER]
    out.extend(theme.HILL)
    for tones in theme.BUILDING.values():
        out.extend((tones["roof"], tones["body"]))
    return tuple(out)


def counts(surface: pygame.Surface) -> Counter:
    raw = pygame.image.tobytes(surface, "RGB")
    return Counter(tuple(raw[i : i + 3]) for i in range(0, len(raw), 3))


@pytest.fixture(scope="module")
def manifest() -> dict:
    return json.loads(MANIFEST.read_text(encoding="utf-8"))


def test_the_manifest_names_every_image_in_the_directory(manifest):
    named = {image["file"] for image in manifest["images"]}
    there = {p.name for p in IMAGES.glob("*") if p.suffix.lower() != ".json"}
    assert named == there, f"the manifest and the directory do not agree: {named ^ there}"


def test_each_entry_says_what_made_it(manifest):
    for image in manifest["images"]:
        assert image["tool"] == "tools/make_docs_images.py"
        assert image["shows"].strip(), f"{image['file']} says nothing about what it shows"
        assert image["width"] > 0 and image["height"] > 0
        if "scenario" in image:
            assert image["commands"] > 0 and image["agent"]
        else:
            assert image["board_type"] and image["board_seed"]


def test_the_tool_names_the_same_pictures_as_the_manifest(manifest):
    assert [p.name for p in maker.PICTURES] == [image["file"] for image in manifest["images"]]


def mean_difference(a: pygame.Surface, b: pygame.Surface) -> float:
    """The mean absolute difference of the RGB channels of the board areas of two pictures."""
    area = (0, 0, BOARD_WIDTH, a.get_height())
    raw_a = pygame.image.tobytes(a.subsurface(area), "RGB")
    raw_b = pygame.image.tobytes(b.subsurface(area), "RGB")
    assert len(raw_a) == len(raw_b)
    return sum(abs(x - y) for x, y in zip(raw_a, raw_b)) / len(raw_a)


@pytest.fixture(scope="module")
def renders() -> dict[str, pygame.Surface]:
    """Each game picture, made one time: Panda3D permits one window in a process."""
    pytest.importorskip("panda3d", reason="the game pictures need the `view3d` extra")
    import builtins

    # An earlier 3D test can leave its window open at its own size, and Panda3D permits one.
    left = getattr(builtins, "base", None)
    if left is not None:
        left.destroy()
    pygame.init()
    pygame.font.init()
    try:
        yield {spec.name: maker.make(spec) for spec in GAMES}
    finally:
        # The 3D tests make their own window at their own size in this process.
        maker.close_board3d_app()


@pytest.mark.parametrize("spec", GAMES, ids=lambda s: s.name)
def test_the_game_picture_in_the_tree_is_what_the_3d_window_draws(spec, renders):
    fresh = renders[spec.name]
    on_disk = pygame.image.load(str(IMAGES / spec.name)).convert(fresh)
    assert on_disk.get_size() == fresh.get_size() == (spec.width, spec.height)
    gap = mean_difference(fresh, on_disk)
    assert gap <= RENDER_TOLERANCE, f"{spec.name} differs from what the 3D window draws by {gap:.2f} of 255"


def test_the_render_check_says_no_to_a_picture_that_the_code_did_not_draw(renders):
    """The 2D and the 3D camera show one position, so they are the nearest wrong picture."""
    plan, board = (renders[spec.name] for spec in GAMES[:2])
    assert mean_difference(plan, board) > 3 * RENDER_TOLERANCE


@pytest.mark.parametrize("spec", BOARDS, ids=lambda s: s.name)
def test_the_picture_in_the_tree_is_what_the_code_draws(spec):
    """Make the picture again and compare it with the file that the documentation shows."""
    pygame.init()
    pygame.font.init()
    fresh = maker.make(spec)
    on_disk = pygame.image.load(str(IMAGES / spec.name)).convert(fresh)
    assert on_disk.get_size() == fresh.get_size() == (spec.width, spec.height)
    here, there = counts(fresh), counts(on_disk)
    total = spec.width * spec.height
    for colour in flat_colours():
        if here[colour] < total * 0.001:
            continue
        gap = abs(here[colour] - there[colour])
        assert gap <= max(64, here[colour] * TOLERANCE), (
            f"{spec.name} has {there[colour]} pixels of {colour} and the code draws {here[colour]}"
        )


def test_the_check_says_no_to_a_picture_that_the_code_did_not_draw():
    """The comparison has to be able to reject, or it proves nothing."""
    pygame.init()
    spec = maker.PICTURES[0]
    fresh = counts(maker.make(spec))
    other = counts(maker.make(maker.PICTURES[1]))
    ground = theme.GROUND
    assert abs(fresh[ground] - other[ground]) > max(64, fresh[ground] * TOLERANCE), (
        "two different boards give the same count of open ground, so the check proves nothing"
    )
