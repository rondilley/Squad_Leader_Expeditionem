"""Make the pictures that the documentation shows (FR-30, SR-07).

Each picture is the output of this project's own code. The board comes from the generator
with a seed that this file names. A board picture comes from `slwindow.render`, and a game
picture comes from the 3D window (`slwindow3d`, the MVP front end) in its 2D or its 3D camera
mode, with the counter cards that a player sees. Nothing here reads a scan, a photograph, or
any other file that a person made. The game pictures need the `view3d` extra.

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
import math
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
from slagents.base import decide  # noqa: E402
from slagents.registry import build_engine, make_agent  # noqa: E402
from slcore import view as core_view  # noqa: E402
from sldata.loaders import load_terrain  # noqa: E402
from slwindow import counters, layout, theme  # noqa: E402
from slwindow.client import GameView  # noqa: E402
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
    # The camera mode of the 3D window for a game picture: "2d" (from above) or "3d".
    mode: str = ""

    def entry(self) -> dict[str, Any]:
        out: dict[str, Any] = {"file": self.name, "shows": self.shows, "tool": TOOL}
        out["width"] = self.width
        out["height"] = self.height
        if self.scenario:
            out["scenario"] = self.scenario
            out["game_seed"] = self.game_seed
            out["agent"] = self.agent
            out["commands"] = self.commands
            out["window"] = "slwindow3d"
            out["camera"] = self.mode
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
        name="window3d_plan.png",
        shows="The 3D window in its 2D camera mode, in turn 3 of scenario 4: the board from "
        "above, the counter cards of the two sides with their vehicles, and the panel with the "
        "legal commands and the action log",
        width=1440,
        height=900,
        scenario="s04_armor_probe",
        game_seed=21,
        agent="v3",
        commands=245,
        mode="2d",
    ),
    Picture(
        name="window3d_board.png",
        shows="The 3D window in its 3D camera mode, at the same position: the hex prisms, the "
        "buildings, and the counter cards seen from the south",
        width=1440,
        height=900,
        scenario="s04_armor_probe",
        game_seed=21,
        agent="v3",
        commands=245,
        mode="3d",
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
    small = counters.system_font("dejavusansmono,consolas,couriernew", 12)
    draw_board(surface, document, layout.fit(document, spec.width, spec.height), small)
    return surface


def game_snapshot(spec: Picture) -> GameView:
    """The snapshot of the host at the position of the spec, the input of each window.

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
        chosen = decide(agents[state.active], state, frame)
        legal = frame.by_id(chosen)
        if legal is None:
            raise RuntimeError(f"the agent {spec.agent} gave an ID that is not in the frame")
        state, events = engine.apply(state, legal.command, frame)
        log.extend(e.to_dict() for e in events)
        frame = engine.legal_commands(state)
    return GameView(
        board=core_view.board_document(engine.board),
        scenario={"title": engine.scenario.title, "board": engine.board.name, "turns": engine.scenario.turns, "players": list(engine.scenario.players())},
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


def board3d_app(width: int, height: int) -> Any:
    """The one offscreen 3D window of this process (Panda3D permits one ShowBase).

    The window type, the size, and the null audio go in before the first import of Panda3D,
    the same way `sl-cli window3d --screenshot` does it, so it needs no display.
    """
    import builtins

    from panda3d.core import loadPrcFileData

    existing = getattr(builtins, "base", None)
    if existing is None:
        _PRC_PAGES.extend(
            loadPrcFileData("", line)
            for line in ("window-type offscreen", f"win-size {width} {height}", "audio-library-name null")
        )
        from slwindow3d.app import Board3DApp

        existing = Board3DApp()
        _OWN_APP.append(existing)
    size = (existing.win.getXSize(), existing.win.getYSize())
    if size != (width, height):
        raise RuntimeError(f"the offscreen 3D window is {size}; each 3D picture must be {width} x {height}")
    return existing


# The settings and the window that `board3d_app` made, so `close_board3d_app` can take them
# back. A test process that makes these pictures also runs the 3D tests at their own size.
_PRC_PAGES: list[Any] = []
_OWN_APP: list[Any] = []


def close_board3d_app() -> None:
    """Close the window that `board3d_app` made, and unload its settings."""
    from panda3d.core import unloadPrcFile

    while _OWN_APP:
        _OWN_APP.pop().destroy()
    while _PRC_PAGES:
        unloadPrcFile(_PRC_PAGES.pop())


def frame_board(app: Any, board: dict[str, Any], mode: str) -> None:
    """Point the camera at the whole board, in the part of the window left of the panel."""
    from slwindow3d.app import FLAT_PITCH, MODE_2D, PANEL_WIDTH
    from slwindow3d.mesh import hex_world

    points = [hex_world(h["center"]) for h in board["hexes"]]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    width, height = app.win.getXSize(), app.win.getYSize()
    board_share = (width - PANEL_WIDTH) / width
    aspect = width / height
    # A hex is about 2 units across, so a margin of 4 on each side keeps the outer row in.
    across = (max(xs) - min(xs) + 8.0) / (aspect * board_share)
    down = max(ys) - min(ys) + 8.0
    app.mode = mode
    app.heading = 0.0
    if mode == MODE_2D:
        app.pitch = FLAT_PITCH
        app.distance = max(across, down)
        world_per_pixel = app.distance * aspect / width
    else:
        app.pitch = THREE_D_PITCH
        app.distance = max(across, down) * THREE_D_DISTANCE
        # The lens has a horizontal field of 45 degrees, so this is the scale at the target.
        world_per_pixel = 2.0 * app.distance * math.tan(math.radians(22.5)) / width
    centre_x = (min(xs) + max(xs)) / 2.0 + PANEL_WIDTH / 2.0 * world_per_pixel
    centre_y = (min(ys) + max(ys)) / 2.0
    app.target = type(app.target)(centre_x, centre_y, 0)
    app._place_camera()


# The 3D picture looks down at the board from the south, near the angle of the video.
THREE_D_PITCH = -48.0
THREE_D_DISTANCE = 1.9


def window3d_picture(spec: Picture) -> pygame.Surface:
    """The 3D window, from the same `Board3DApp.show_snapshot` that the game runs: the board,
    the counter cards, and the panel with the legal commands and the action log."""
    snapshot = game_snapshot(spec)
    app = board3d_app(spec.width, spec.height)
    # A new snapshot with the same frame as the last picture would not load its counters.
    app._last_frame_id = None
    app._hud_key = None
    app.set_board(snapshot.board)
    app.show_snapshot(snapshot)
    frame_board(app, snapshot.board, spec.mode)
    for _ in range(3):
        app.graphicsEngine.renderFrame()
    texture = app.win.getScreenshot()
    raw = bytes(texture.getRamImageAs("RGB"))
    # Panda3D gives the rows from the bottom up.
    return pygame.transform.flip(pygame.image.frombuffer(raw, (spec.width, spec.height), "RGB"), False, True).copy()


def make(spec: Picture) -> pygame.Surface:
    """One picture, printed with the font of the library, so it is the same on each system."""
    before = counters.BUNDLED_FONT
    counters.BUNDLED_FONT = True
    counters._FONTS.clear()
    try:
        return window3d_picture(spec) if spec.scenario else board_picture(spec)
    finally:
        counters.BUNDLED_FONT = before
        counters._FONTS.clear()


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
                    "the generator with the seed below. A board drawing comes from slwindow, and a "
                    "game picture comes from the 3D window, slwindow3d. No "
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
    # The panel width is part of the game picture, so a change to it changes the shape.
    from slwindow3d.app import PANEL_WIDTH

    print(f"the 3D panel is {PANEL_WIDTH} px wide, and the ground is {theme.GROUND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
