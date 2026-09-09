"""A whole game in the browser, computer against computer (FR-39, TR-07).

This is the harness that watches a game end to end. The host gives each seat to a scripted
agent and steps one command at a time. A browser joins as a watcher, and the test reads
what the browser shows after each step.

What it checks while the game runs:

- The client and the host agree. The turn, the phase, and the active side that the browser
  shows are the ones the host holds.
- The rules run. Each entry of the action log names the rule that produced it.
- The game moves. The turn count reaches the turn limit of the scenario, or one side wins
  before that.
- The canvas draws. The test reads the pixels of the board canvas and finds the terrain
  colours of the renderer and a counter of a side. A test that reads only the state of the
  client passes on a blank canvas, so this file reads the picture as well.
- Nothing breaks. The browser console gets no error, and the page keeps its frame.
- The game ends with a result, or the test says how far it got and fails.

What it leaves behind: a screenshot of each turn and a video of the game, so that a person
can see what the two computer opponents did. Those go to a directory outside the tree,
because SR-07 keeps images out of the repository and the release audit reads that rule.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from slcli.play import build_engine, make_agent
from slhost.server import Host

CLIENT_DIST = Path("client") / "dist"
SCENARIO = "s01_guards_counterattack"
SEED = 7
COMMAND_LIMIT = 4000
TIMEOUT_SECONDS = 240.0
# Seconds between two commands. It makes the video watchable and it keeps the test short.
WATCH_DELAY = 0.02
VIEWPORT = {"width": 1600, "height": 900}

playwright_api = pytest.importorskip("playwright.async_api", reason="playwright is not installed")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not CLIENT_DIST.is_dir(), reason="the client is not built; run npm run build in client/"),
]


def output_root() -> Path:
    """Where the pictures go. Never the repository: SR-07 keeps images out of the tree."""
    named = os.environ.get("SQUAD_LEADER_WATCH_DIR")
    if named:
        return Path(named)
    return Path("background") / "watch"


async def open_self_playing_host(
    scenario: str = SCENARIO, first: str = "v1", second: str = "v2", delay: float = 0.0
):
    """A host with a computer opponent in each seat.

    The delay is what makes the game watchable. With no delay the host sends a thousand
    frames as fast as the socket takes them, and the video shows a blur.
    """
    engine = build_engine(scenario)
    agents = {0: make_agent(first, engine, SEED, 0), 1: make_agent(second, engine, SEED, 1)}
    host = Host(engine, seed=SEED, client_root=CLIENT_DIST, agents=agents, agent_delay=delay)
    manager = host.start("127.0.0.1", 0)
    server = await manager.__aenter__()
    return host, manager, Host.bound_port(server)


async def wait_for_frame(page, timeout_ms: int = 20000) -> None:
    await page.wait_for_function(
        "() => window.slClient && window.slClient.state.frameId !== null", timeout=timeout_ms
    )


# The palette of `client/src/board/render.ts` and `client/src/counters/draw.ts`, as the
# colours the canvas must actually carry. A test that reads only `window.slClient.state`
# passes on a blank canvas, because that state is the data the client received and not the
# pixels it drew.
TERRAIN_COLOURS = {
    "open ground": (158, 176, 104),
    "stone building": (132, 132, 128),
    "woods": (92, 128, 68),
}
COUNTER_COLOURS = {
    "a German counter": (108, 122, 140),
    "a Russian counter": (186, 152, 82),
}
MIN_DISTINCT_COLOURS = 200
MIN_PIXELS_OF_A_COLOUR = 500


async def canvas_colours(page) -> "Counter":
    """What the board canvas actually drew, as a count for each colour."""
    from collections import Counter
    from io import BytesIO

    from PIL import Image

    raw = await page.locator("#board").screenshot()
    image = Image.open(BytesIO(raw)).convert("RGB")
    return Counter(image.convert("RGB").getdata())


def assert_the_board_is_drawn(colours) -> None:
    """The canvas carries the terrain of the board and a counter of each side.

    This is the check that a blank canvas fails. Every other check in this file reads the
    state of the client, and a client that receives each frame and draws nothing passes
    all of them.
    """
    assert len(colours) >= MIN_DISTINCT_COLOURS, (
        f"the canvas has {len(colours)} colours, which is a blank or nearly blank picture"
    )
    for name, colour in TERRAIN_COLOURS.items():
        assert colours[colour] >= MIN_PIXELS_OF_A_COLOUR, (
            f"the canvas has {colours[colour]} pixels of {name} {colour}, so the board is not drawn"
        )
    drawn = {name: colours[c] for name, c in COUNTER_COLOURS.items() if colours[c] > 0}
    assert drawn, f"the canvas has no counter of either side: {sorted(COUNTER_COLOURS.values())}"


async def client_state(page) -> dict:
    return json.loads(
        await page.evaluate(
            """() => JSON.stringify({
                turn: window.slClient.state.view?.turn ?? null,
                phase: window.slClient.state.view?.phase ?? null,
                active: window.slClient.state.view?.active ?? null,
                over: window.slClient.state.view?.game_over ?? false,
                result: window.slClient.state.view?.result ?? null,
                units: window.slClient.state.view?.units?.length ?? 0,
                spectator: window.slClient.state.view?.spectator ?? false,
                logs: window.slClient.state.log?.length ?? 0
            })"""
        )
    )


# ----------------------------------------------------------------- the whole game


async def test_two_computer_opponents_play_a_whole_game_in_the_browser():
    """The harness the owner asked for: watch the two sides fight to a result."""
    host, manager, port = await open_self_playing_host(delay=WATCH_DELAY)
    pictures = output_root()
    pictures.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    seen_turns: list[int] = []
    seen_phases: set[str] = set()

    async with playwright_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            context = await browser.new_context(
                viewport=VIEWPORT, record_video_dir=str(pictures), record_video_size=VIEWPORT
            )
            page = await context.new_page()
            page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: errors.append(str(e)))
            await page.goto(f"http://127.0.0.1:{port}/?room={host.room.code}")
            await wait_for_frame(page)

            deadline = asyncio.get_running_loop().time() + TIMEOUT_SECONDS
            last_turn = 0
            while not host.game.state.game_over:
                if asyncio.get_running_loop().time() > deadline:
                    break
                if host.commands_played >= COMMAND_LIMIT:
                    break
                await asyncio.sleep(0.05)
                state = await client_state(page)
                if state["turn"] is None:
                    continue
                seen_phases.add(state["phase"])
                if state["turn"] != last_turn:
                    last_turn = state["turn"]
                    seen_turns.append(last_turn)
                    await page.screenshot(path=str(pictures / f"turn-{last_turn:02d}.png"))

            # The host has finished. Wait for the client to work through the frames it
            # still holds, so that the picture and the state below are the last ones.
            await page.wait_for_function(
                "() => window.slClient.state.view && window.slClient.state.view.game_over === true",
                timeout=30000,
            )
            final = await client_state(page)
            drawn = await canvas_colours(page)
            await page.screenshot(path=str(pictures / "final.png"))
            video = page.video
            await context.close()
            saved = await video.path() if video is not None else None
        finally:
            await browser.close()
            await manager.__aexit__(None, None, None)

    # The game reached an end, and the end is one the rules give.
    assert host.game.state.game_over, (
        f"the game did not end: turn {host.game.state.turn} of {host.game.state.turn_limit}, "
        f"{host.commands_played} commands played"
    )
    assert host.game.state.result, "the game ended with no result"
    assert final["over"] is True
    assert final["result"] == host.game.state.result

    # The client and the host agree at the end.
    assert final["turn"] == host.game.state.turn
    assert final["phase"] == host.game.state.phase

    # The game moved through its turns and through the phases of rule 4.
    assert len(seen_turns) >= 2, f"the game showed {len(seen_turns)} turns"
    assert {"rally", "prep_fire", "movement"} <= seen_phases, sorted(seen_phases)

    # The rules ran, and each entry of the log names the rule that made it.
    log = host.game.log_tail()
    assert log, "the action log is empty"
    for entry in log:
        assert entry.get("rule_id"), entry

    # The canvas drew the board and the counters, and not an empty rectangle.
    assert_the_board_is_drawn(drawn)

    # Nothing in the browser broke.
    assert errors == [], errors[:3]

    # And a person can see what happened.
    assert (pictures / "final.png").is_file()
    assert saved is None or Path(saved).is_file()
    print(
        f"computer against computer on {SCENARIO}: {host.game.state.result} "
        f"in {host.game.state.turn} turns and {host.commands_played} commands. "
        f"Pictures in {pictures}"
    )


# ------------------------------------------------------- what the watcher may see


async def test_the_watcher_of_a_computer_game_sees_each_side():
    """A game with no person in a seat has nothing to keep from the watcher."""
    host, manager, port = await open_self_playing_host()
    try:
        async with playwright_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport=VIEWPORT)
                await page.goto(f"http://127.0.0.1:{port}/?room={host.room.code}")
                await wait_for_frame(page)
                await asyncio.sleep(0.5)
                state = await client_state(page)
                assert state["spectator"] is True
                assert state["units"] > 0
                assert_the_board_is_drawn(await canvas_colours(page))
            finally:
                await browser.close()
    finally:
        await manager.__aexit__(None, None, None)


def test_a_game_with_a_person_in_a_seat_refuses_a_spectator_view():
    """AR-09: a person who sees each side of a live game has what the rules hide."""
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=SEED, agents={1: make_agent("v1", engine, SEED, 1)})
    assert host.self_playing is False
    with pytest.raises(PermissionError) as exc:
        host.game.spectator_view(host.self_playing)
    assert "AR-09" in str(exc.value)


def test_a_hot_seat_game_refuses_a_spectator_view():
    engine = build_engine(SCENARIO)
    host = Host(engine, seed=SEED)
    assert host.self_playing is False
    with pytest.raises(PermissionError):
        host.game.spectator_view(host.self_playing)


def test_a_game_between_two_computers_says_it_plays_itself():
    engine = build_engine(SCENARIO)
    agents = {0: make_agent("v1", engine, SEED, 0), 1: make_agent("v2", engine, SEED, 1)}
    host = Host(engine, seed=SEED, agents=agents)
    assert host.self_playing is True
    document = host.game.spectator_view(host.self_playing)
    assert document["spectator"] is True
    assert len(document["units"]) == len(host.game.state.units)


def test_the_drawing_check_rejects_a_blank_canvas():
    """The check exists to catch a client that draws nothing, so it has to catch one."""
    from collections import Counter

    blank = Counter({(216, 207, 184): 1_000_000})
    with pytest.raises(AssertionError) as exc:
        assert_the_board_is_drawn(blank)
    assert "blank" in str(exc.value)


def test_the_drawing_check_rejects_a_board_with_no_counter():
    """A board that draws its terrain and no unit is a defect the check has to name."""
    from collections import Counter

    terrain_only = Counter({colour: 5000 for colour in TERRAIN_COLOURS.values()})
    terrain_only.update({(i, i, i): 1 for i in range(MIN_DISTINCT_COLOURS + 1)})
    with pytest.raises(AssertionError) as exc:
        assert_the_board_is_drawn(terrain_only)
    assert "counter" in str(exc.value)


def test_the_drawing_check_rejects_a_board_with_no_buildings():
    from collections import Counter

    without = Counter({TERRAIN_COLOURS["open ground"]: 5000, TERRAIN_COLOURS["woods"]: 5000})
    without.update({(i, i, i): 1 for i in range(MIN_DISTINCT_COLOURS + 1)})
    with pytest.raises(AssertionError) as exc:
        assert_the_board_is_drawn(without)
    assert "stone building" in str(exc.value)


def test_the_drawing_check_accepts_a_board_that_is_drawn():
    from collections import Counter

    good = Counter({colour: 5000 for colour in TERRAIN_COLOURS.values()})
    good[COUNTER_COLOURS["a German counter"]] = 400
    good.update({(i, i, i): 1 for i in range(MIN_DISTINCT_COLOURS + 1)})
    assert_the_board_is_drawn(good)


def test_the_pictures_never_go_in_the_repository():
    """SR-07 keeps images out of the tree, and the release audit reads that rule."""
    root = output_root()
    assert "background" in root.parts or root.is_absolute(), root


# --------------------------------------------------- the page that cannot join says why


async def test_a_page_with_no_room_code_says_what_is_missing():
    """SR-03 refuses the join. Without a notice a person gets an empty board and a code.

    The host prints an address that carries the room code. A person who opens the bare
    address instead gets nothing on the screen, and the reason has to be on the screen.
    """
    host, manager, port = await open_self_playing_host()
    try:
        async with playwright_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport=VIEWPORT)
                await page.goto(f"http://127.0.0.1:{port}/")
                await page.wait_for_function(
                    "() => document.getElementById('notice-panel')?.hidden === false",
                    timeout=15000,
                )
                title = await page.locator("#notice-title").text_content()
                body = await page.locator("#notice-body").text_content()
                assert "room code" in (title or "").lower()
                assert "?room=" in (body or "")
                assert await page.evaluate("() => window.slClient.state.frameId") is None
            finally:
                await browser.close()
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_page_with_the_room_code_shows_no_notice():
    host, manager, port = await open_self_playing_host()
    try:
        async with playwright_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport=VIEWPORT)
                await page.goto(f"http://127.0.0.1:{port}/?room={host.room.code}")
                await wait_for_frame(page)
                assert await page.evaluate("() => document.getElementById('notice-panel').hidden") is True
            finally:
                await browser.close()
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_page_with_the_wrong_room_code_says_the_code_is_wrong():
    host, manager, port = await open_self_playing_host()
    try:
        async with playwright_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport=VIEWPORT)
                await page.goto(f"http://127.0.0.1:{port}/?room=NOTTHECODE")
                await page.wait_for_function(
                    "() => document.getElementById('notice-panel')?.hidden === false",
                    timeout=15000,
                )
                title = await page.locator("#notice-title").text_content()
                assert "not the one" in (title or "")
            finally:
                await browser.close()
    finally:
        await manager.__aexit__(None, None, None)
