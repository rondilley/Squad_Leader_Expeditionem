"""The scenario card renders for each scenario, has the right size, and is not blank.

The renderer runs offscreen (the dummy SDL driver), so the test needs no display. It checks
that the PNG is written, that it has the expected size, that some non-paper pixels exist
(the card is not blank), and that the title region is drawn. No Avalon Hill text or art is
in this test (SR-07).
"""

from __future__ import annotations

import json
import os
from importlib import resources

import pytest

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from slcards import card


def _scenario_names() -> list[str]:
    names = []
    for entry in resources.files("sldata").joinpath("scenarios").iterdir():
        if entry.name.endswith(".json"):
            names.append(entry.name[:-5])
    return sorted(names)


def _load(name: str) -> dict:
    ref = resources.files("sldata").joinpath(f"scenarios/{name}.json")
    with ref.open("r", encoding="utf-8") as fh:
        return json.load(fh)


SCENARIOS = _scenario_names()
FOUR = ["s01_guards_counterattack", "s02_tractor_works", "s03a_streets_of_stalingrad", "s04_armor_probe"]


@pytest.mark.parametrize("name", FOUR)
def test_card_renders(name: str) -> None:
    scenario = _load(name)
    surface = card.render_card(scenario)
    assert surface.get_size() == (card.CARD_WIDTH, card.CARD_HEIGHT)


@pytest.mark.parametrize("name", FOUR)
def test_card_not_blank(name: str) -> None:
    """Some pixels differ from the paper colour, so the card holds drawing."""
    scenario = _load(name)
    surface = card.render_card(scenario)
    paper = pygame.Color(*card.theme.CARD_PAPER)
    non_paper = 0
    # Sample a grid of pixels rather than every pixel, to stay fast.
    for x in range(0, card.CARD_WIDTH, 8):
        for y in range(0, card.CARD_HEIGHT, 8):
            colour = surface.get_at((x, y))
            if (colour.r, colour.g, colour.b) != (paper.r, paper.g, paper.b):
                non_paper += 1
    assert non_paper > 200, f"{name} looks blank: only {non_paper} non-paper pixels"


@pytest.mark.parametrize("name", FOUR)
def test_title_region_drawn(name: str) -> None:
    """The title band near the top holds ink, so the title is drawn."""
    scenario = _load(name)
    surface = card.render_card(scenario)
    paper = card.theme.CARD_PAPER
    band_top, band_bottom = card.MARGIN, card.MARGIN + 60
    ink_pixels = 0
    for x in range(card.MARGIN, card.CARD_WIDTH - card.MARGIN, 4):
        for y in range(band_top, band_bottom, 4):
            colour = surface.get_at((x, y))
            if (colour.r, colour.g, colour.b) != paper:
                ink_pixels += 1
    assert ink_pixels > 30, f"{name} has no title drawn: {ink_pixels} ink pixels in the band"


def test_write_png(tmp_path) -> None:
    scenario = _load("s01_guards_counterattack")
    path = tmp_path / "card_s01.png"
    card.save_card(scenario, path)
    assert path.exists()
    loaded = pygame.image.load(str(path))
    assert loaded.get_size() == (card.CARD_WIDTH, card.CARD_HEIGHT)


def test_every_scenario_renders() -> None:
    """No scenario in the data raises when it renders."""
    for name in SCENARIOS:
        card.render_card(_load(name))
