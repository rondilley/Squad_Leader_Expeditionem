"""Make the pictures that the documentation shows (FR-30, SR-07).

Each picture is the output of this project's own code. The board comes from the generator
with a seed that this file names, and the drawing comes from `slwindow.render` and
`slwindow.counters`, the same code that the desktop window runs. Nothing here reads a scan,
a photograph, or any other file that a person made.

`docs/images/MANIFEST.json` records what each picture shows and the numbers that made it.
The release audit reads that manifest. An image in `docs/images/` that the manifest does
not name is a finding, and an image anywhere outside `background/` is a finding (TC-29).
`tests/docs/test_documentation_images.py` makes each picture again and compares it with the
one in the tree, so a picture that a person put there by hand does not pass.

Run it with the venv active:

    python tools/make_docs_images.py
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pygame  # noqa: E402

from slboards.generator import GeneratorParameters, generate_with_retry  # noqa: E402
from slcli.play import build_engine, make_agent  # noqa: E402
from slcore import view as core_view  # noqa: E402
from sldata.loaders import load_terrain  # noqa: E402
from slwindow import layout, panel, theme  # noqa: E402
from slwindow.app import Window  # noqa: E402
from slwindow.client import GameView, HostClient  # noqa: E402
from slwindow.render import draw_board  # noqa: E402

OUTPUT = ROOT / "docs" / "images"
MANIFEST = OUTPUT / "MANIFEST.json"
TOOL = "tools/make_docs_images.py"


@dataclass(frozen=True)
class Picture:
    """One picture, and everything that decides what it holds."""

    name: str
    shows: str
    width: int
    height: int
    board_type: str = ""
    board_seed: int = 0
    cols: int = 0
    rows: int = 0
    scenario: str = ""
    game_seed: int = 0
    agent: str = ""
    commands: int = 0

    def entry(self) -> dict[str, Any]:
        out: dict[str, Any] = {"file": self.name, "shows": self.shows, "tool": TOOL}
        out["width"] = self.width
        out["height"] = self.height
        if self.scenario:
            out["scenario"] = self.scenario
            out["game_seed"] = self.game_seed
            out["agent"] = self.agent
            out["commands"] = self.commands
        else:
            out["board_type"] = self.board_type
            out["board_seed"] = self.board_seed
            out["cols"] = self.cols
            out["rows"] = self.rows
        return out


PICTURES = (
    Picture(
        name="board_village.png",
        shows="A village board: the woods mass, the building plans, the roads, a hill with its "
        "crest line, the grain fields, and the wall and hedge hexsides",
        width=1440,
        height=900,
        board_type="village",
        board_seed=20260909,
        cols=17,
        rows=10,
    ),
    Picture(
        name="board_city.png",
        shows="A city board: blocks of stone buildings, each with the wall line of one building "
        "and the panel lines of its hexes",
        width=1440,
        height=900,
        board_type="city",
        board_seed=101,
        cols=17,
        rows=10,
    ),
    Picture(
        name="board_hills.png",
        shows="A hills board: three levels of brown, the crest lines of rule 43.2, and the cliff "
        "hexsides of rule 44.1",
        width=1440,
        height=900,
        board_type="hills",
        board_seed=4242,
        cols=17,
        rows=10,
    ),
    Picture(
        name="window_armor_probe.png",
        shows="The desktop window in turn 4 of scenario 4: the board, the counters of the two "
        "sides with their vehicles, and the panel with the legal commands and the action log",
        width=1440,
        height=900,
        scenario="s04_armor_probe",
        game_seed=21,
        agent="v3",
        commands=245,
    ),
)


def board_picture(spec: Picture) -> pygame.Surface:
    """One board, drawn the way the window draws it, with no counters and no panel."""
    board, _ = generate_with_retry(
        GeneratorParameters(seed=spec.board_seed, board_type=spec.board_type, cols=spec.cols, rows=spec.rows),
        load_terrain(),
    )
    document = core_view.board_document(board)
    surface = pygame.Surface((spec.width, spec.height))
    small = pygame.font.SysFont("dejavusansmono,consolas,couriernew", 12)
    draw_board(surface, document, layout.fit(document, spec.width, spec.height), small)
    return surface


def window_picture(spec: Picture) -> pygame.Surface:
    """The whole window, from the same `Window.draw` that the application runs.

    The two seats play with the scripted agent the spec names, so the picture holds a real
    position of a real game and not a set up that this file arranged.
    """
    engine = build_engine(spec.scenario)
    state = engine.new_game(spec.game_seed)
    agents = {
        0: make_agent(spec.agent, engine, spec.game_seed, 0),
        1: make_agent(spec.agent, engine, spec.game_seed, 1),
    }
    frame = engine.legal_commands(state)
    log: list[dict[str, Any]] = []
    for _ in range(spec.commands):
        if state.game_over or not frame.commands:
            break
        chosen = agents[state.active].select(state, frame)
        legal = frame.by_id(chosen)
        if legal is None:
            raise RuntimeError(f"the agent {spec.agent} gave an ID that is not in the frame")
        state, events = engine.apply(state, legal.command, frame)
        log.extend(e.to_dict() for e in events)
        frame = engine.legal_commands(state)
    window = Window(HostClient("ws://127.0.0.1:1/", "none"), size=(spec.width, spec.height), caption=spec.name)
    snapshot = GameView(
        board=core_view.board_document(engine.board),
        scenario={"title": engine.scenario.title, "board": engine.board.name, "turns": engine.scenario.turns},
        seat="axis",
        player=0,
        view=core_view.build(state, engine.types, 0, spectator=True),
        frame_id=frame.frame_id,
        active=state.active,
        phase=state.phase,
        sub_step=frame.sub_step,
        turn=state.turn,
        legal=[{"id": c.id, "payload": c.payload} for c in frame.commands],
        log=log[-12:],
        connected=True,
    )
    window.fit_board(snapshot)
    window.draw(snapshot)
    return window.surface


def make(spec: Picture) -> pygame.Surface:
    return window_picture(spec) if spec.scenario else board_picture(spec)


def main() -> int:
    pygame.init()
    pygame.font.init()
    OUTPUT.mkdir(parents=True, exist_ok=True)
    entries = []
    for spec in PICTURES:
        surface = make(spec)
        path = OUTPUT / spec.name
        pygame.image.save(surface, str(path))
        entries.append(spec.entry())
        print(f"{path.relative_to(ROOT)} {surface.get_size()} {path.stat().st_size} bytes")
    MANIFEST.write_text(
        json.dumps(
            {
                "provenance": (
                    "Each picture is the output of this project's own code. The board comes from "
                    "the generator with the seed below, and the drawing comes from slwindow. No "
                    "scan and no photograph is in any of them (SR-07)."
                ),
                "tool": TOOL,
                "images": entries,
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{MANIFEST.relative_to(ROOT)} names {len(entries)} pictures")
    # The panel width is part of the window picture, so a change to it changes the shape.
    print(f"the panel is {panel.WIDTH} px wide, and the ground is {theme.GROUND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
