"""The play screen of the browser (slice 4 and slice 8), with a real host and Chromium.

- The page title, the phase strip, and the rule topic of a log line.
- "Set up for me", the hot seat cover, and the key E that ends a phase.
- The board path: click a unit, then a shaded hex, and the host applies the move.
- The odds on the commands, the keyboard path through the list, and undo.
- A terminal error code stops the reconnect (H6).
- The log text shows the morale modifier and the rally hex (H8).
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from slcli.play import build_engine, make_agent
from slhost.server import Host

CLIENT_DIST = Path("client") / "dist"
SCENARIO = "s01_guards_counterattack"
VIEWPORT = {"width": 1600, "height": 900}

playwright_api = pytest.importorskip("playwright.async_api", reason="playwright is not installed")

pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not CLIENT_DIST.is_dir(), reason="the client is not built; run npm run build in client/"),
]


async def open_host(**kwargs):
    engine = build_engine(kwargs.pop("scenario", SCENARIO))
    host = Host(engine, seed=kwargs.pop("seed", 1), client_root=CLIENT_DIST, **kwargs)
    manager = host.start("127.0.0.1", 0)
    server = await manager.__aenter__()
    return host, manager, Host.bound_port(server)


async def frame_ready(page) -> None:
    await page.wait_for_function("() => window.slClient && window.slClient.state.frameId !== null", timeout=20000)


async def uncover(page) -> None:
    if await page.evaluate("() => !document.getElementById('cover').hidden"):
        await page.click("#cover-button")


async def settle(page, host, quiet: float = 0.4) -> None:
    """Wait until the host applies nothing for a moment and the client has its frame."""
    last = -1
    while host.game.state.seq != last:
        last = host.game.state.seq
        await asyncio.sleep(quiet)
    await frame_ready(page)


async def set_up_both_sides(page, host) -> None:
    for _ in range(2):
        await uncover(page)
        await page.wait_for_selector("#setup-helper:not([hidden])", timeout=20000)
        await page.click("#setup-helper")
        await settle(page, host)
    await uncover(page)
    assert host.game.state.phase != "setup"


async def end_phases_until(page, host, phase: str, limit: int = 20) -> None:
    """Press E until the phase comes, and give the other side its turn with E too."""
    for _ in range(limit):
        await uncover(page)
        if host.game.state.phase == phase:
            return
        before = host.game.state.seq
        await page.keyboard.press("e")
        for _ in range(200):
            if host.game.state.seq != before:
                break
            await asyncio.sleep(0.01)
        await settle(page, host, 0.2)
    raise AssertionError(f"the game did not reach {phase}: {host.game.state.phase}")


async def test_the_page_has_the_title_and_the_phase_strip():
    host, manager, port = await open_host()
    try:
        async with playwright_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport=VIEWPORT)
                await page.goto(f"http://127.0.0.1:{port}/?room={host.room.code}")
                await frame_ready(page)
                assert await page.title() == "Squad Leader Expeditionem"
                current = page.locator("#phase-strip span.current")
                assert await current.count() == 1
                assert (await current.text_content()) == "setup"
                assert "set up area" in (await page.locator("#phase-text").text_content() or "")
                assert await page.locator("button.command").count() > 0, "each command is a button"
            finally:
                await browser.close()
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_person_plays_by_the_board_with_the_keys_and_the_helper():
    """Set up for me, the cover, E, the board path, the odds, the keyboard path, and undo."""
    host, manager, port = await open_host()
    errors: list[str] = []
    try:
        async with playwright_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport=VIEWPORT)
                page.on("pageerror", lambda exc: errors.append(str(exc)))
                await page.goto(f"http://127.0.0.1:{port}/?room={host.room.code}")
                await frame_ready(page)
                await set_up_both_sides(page, host)
                assert any(c["source"] == "setup_helper" for c in host.game.commands)
                await end_phases_until(page, host, "movement")
                await uncover(page)

                # The odds are on the move buttons.
                assert await page.locator("button.command .odds").count() > 0

                # The board path: click an own unit that can move, then a shaded hex.
                entry = await page.evaluate(
                    """() => {
                        const own = new Map(window.slClient.state.view.units.filter(u => u.own && u.hex).map(u => [u.id, u.hex]));
                        const moves = window.slClient.state.legal.filter(c => c.action === 'move');
                        for (const move of moves) {
                            const from = own.get(move.units[0].id);
                            const same = moves.filter(m => own.get(m.units[0].id) === from && m.hexes[0] === move.hexes[0]);
                            if (from && same.length === 1) { return {from, to: move.hexes[0], id: move.id}; }
                        }
                        return null;
                    }"""
                )
                assert entry is not None, "a move with one command for its hex"
                point = await page.evaluate("(h) => window.slClient.hexPoint(h)", entry["from"])
                await page.mouse.click(point[0], point[1])
                selected = await page.evaluate("() => window.slClient.state.selectedUnits.length")
                assert selected > 0, "the click selected the units of the hex"
                count = len(host.game.commands)
                point = await page.evaluate("(h) => window.slClient.hexPoint(h)", entry["to"])
                await page.mouse.click(point[0], point[1])
                for _ in range(200):
                    if len(host.game.commands) > count:
                        break
                    await asyncio.sleep(0.01)
                applied = host.game.commands[count]
                assert applied["source"] == "human"
                assert applied["payload"]["hex"] == entry["to"], "the host applied the move to the clicked hex"
                await settle(page, host, 0.2)

                # Undo takes it back.
                await page.wait_for_function("() => !document.getElementById('undo').disabled", timeout=10000)
                await page.click("#undo")
                for _ in range(200):
                    if len(host.game.commands) == count:
                        break
                    await asyncio.sleep(0.01)
                assert len(host.game.commands) == count, "undo took the move back"
                await settle(page, host, 0.2)

                # The keyboard path: an arrow key focuses a command, and Enter sends it.
                await page.keyboard.press("Escape")
                await page.keyboard.press("ArrowDown")
                focused = await page.evaluate("() => document.activeElement?.dataset.commandId ?? null")
                assert focused, "the arrow key focused a command button"
                count = len(host.game.commands)
                await page.keyboard.press("Enter")
                for _ in range(200):
                    if len(host.game.commands) > count:
                        break
                    await asyncio.sleep(0.01)
                assert host.game.commands[count]["command_id"] == focused

                # The rule ID of a log line has its topic as a tooltip.
                titles = await page.eval_on_selector_all("#log-list .rule", "els => els.map(e => e.title)")
                assert any(t.startswith("Rule ") for t in titles)
                assert not errors, errors[:3]
            finally:
                await browser.close()
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_double_click_sends_one_intent():
    host, manager, port = await open_host()
    try:
        async with playwright_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport=VIEWPORT)
                await page.goto(f"http://127.0.0.1:{port}/?room={host.room.code}")
                await frame_ready(page)
                await page.locator("button.command").first.dblclick()
                await asyncio.sleep(0.5)
                assert len([c for c in host.game.commands if c["source"] == "human"]) == 1
                assert await page.evaluate("() => window.slClient.state.lastError") is None, "no stale frame error"
            finally:
                await browser.close()
    finally:
        await manager.__aexit__(None, None, None)


async def test_a_terminal_error_stops_the_reconnect():
    """H6: after a wrong room code the page does not try again, so the address is not locked."""
    host, manager, port = await open_host()
    try:
        async with playwright_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport=VIEWPORT)
                await page.goto(f"http://127.0.0.1:{port}/?room=NOTTHECODE")
                await page.wait_for_function("() => document.getElementById('notice-panel')?.hidden === false", timeout=15000)
                await asyncio.sleep(3.0)
                assert await page.evaluate("() => window.slClient.stopped()") is True
                tries = sum(len(v) for v in host.attempts._hits.values())
                assert tries == 1, f"the page tried {tries} times"
            finally:
                await browser.close()
    finally:
        await manager.__aexit__(None, None, None)


async def test_the_log_text_shows_the_morale_modifier_and_the_rally_hex():
    """H8: a morale line shows its `modifier`, and a rally line shows its hex."""
    engine = build_engine(SCENARIO)
    agents = {0: make_agent("v1", engine, 7, 0), 1: make_agent("v1", engine, 7, 1)}
    host = Host(engine, seed=7, agents=agents, client_root=CLIENT_DIST)
    await host.play_alone()
    lines = host.game.stream("spectator", -1, spectator=True).lines
    morale = next(e for e in lines if e["kind"] in ("morale_pass", "broken") and e["data"].get("modifier"))
    rally = next((e for e in lines if e["kind"] in ("rallied", "rally_failed")), None)
    manager = host.start("127.0.0.1", 0)
    server = await manager.__aenter__()
    port = Host.bound_port(server)
    try:
        async with playwright_api.async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                page = await browser.new_page(viewport=VIEWPORT)
                await page.goto(f"http://127.0.0.1:{port}/?room={host.room.code}")
                await frame_ready(page)
                text = await page.evaluate("(e) => window.slClient.describe(e)", morale)
                assert f"modifier +{morale['data']['modifier']}" in text or f"modifier {morale['data']['modifier']}" in text
                assert morale["names"][str(morale["data"]["unit"])] in text, "the unit name, not the ID"
                if rally is not None:
                    text = await page.evaluate("(e) => window.slClient.describe(e)", rally)
                    assert f"at {rally['data']['hex']}" in text
                logs = await page.evaluate("() => window.slClient.state.log.length")
                assert logs == len(lines), "the late joiner has the whole history"
            finally:
                await browser.close()
    finally:
        await manager.__aexit__(None, None, None)
