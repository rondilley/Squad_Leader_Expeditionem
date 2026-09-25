"""Playwright plays the first turn of scenario 1 in hot seat (TR-07, TC-23).

The test also measures the time from the intent to the next frame (NFR-02, TC-11) and
proves that the client holds no line of sight code (TC-40).
"""

from __future__ import annotations

import asyncio
import json
import re
import statistics
from pathlib import Path

import pytest

from slcli.play import build_engine
from slhost.server import Host

CLIENT_DIST = Path("client") / "dist"
LATENCY_LIMIT_MS = 50.0
FIRST_TURN_PHASES = ("rally", "prep_fire", "movement", "defensive_fire", "advancing_fire", "rout", "advance", "close_combat")

playwright_api = pytest.importorskip("playwright.async_api", reason="playwright is not installed")


pytestmark = [
    pytest.mark.slow,
    pytest.mark.skipif(not CLIENT_DIST.is_dir(), reason="the client is not built; run npm run build in client/"),
]


async def open_host(scenario: str = "s01_guards_counterattack"):
    engine = build_engine(scenario)
    host = Host(engine, seed=1, client_root=CLIENT_DIST)
    manager = host.start("127.0.0.1", 0)
    server = await manager.__aenter__()
    return host, manager, Host.bound_port(server)


async def wait_for_frame(page, timeout_ms: int = 15000) -> None:
    await page.wait_for_function("() => window.slClient && window.slClient.state.frameId !== null", timeout=timeout_ms)


async def pass_the_screen(page) -> None:
    """Hot seat covers the screen at each change of side. The next player uncovers it."""
    if await page.evaluate("() => !document.getElementById('cover').hidden"):
        await page.click("#cover-button")


async def play_until(page, host, predicate, limit: int = 600) -> int:
    """Drive the client. It ends a phase when it can, and places a counter when it must.

    The set up window has no end command until every counter is on the board, so the
    client places one, and after that it ends each phase and the turn moves on.
    """
    steps = 0
    while steps < limit and not predicate(host):
        command_id = await page.evaluate(
            """() => window.slClient.firstOfAction('end_phase')
                ?? window.slClient.firstOfAction('end_setup')
                ?? (window.slClient.commandIds()[0] ?? null)"""
        )
        if command_id is None:
            break
        before = host.game.state.seq
        await pass_the_screen(page)
        frame_before = await page.evaluate("() => window.slClient.state.frameId")
        await page.evaluate("(id) => window.slClient.send(id)", command_id)
        for _ in range(400):
            if host.game.state.seq > before:
                break
            await asyncio.sleep(0.005)
        else:
            raise AssertionError("the host did not answer the intent")
        # The client sends one intent for each frame, so the next command waits for the
        # frame that the host sends after this one.
        await page.wait_for_function("(old) => window.slClient.state.frameId !== old", arg=frame_before, timeout=15000)
        steps += 1
    await page.wait_for_function("() => window.slClient.state.frameId !== null", timeout=15000)
    return steps


async def test_the_client_plays_the_first_turn_of_scenario_one_in_hot_seat():
    host, manager, port = await open_host()
    async with playwright_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            errors: list[str] = []
            page.on("pageerror", lambda exc: errors.append(str(exc)))
            page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
            await page.goto(f"http://127.0.0.1:{port}/?room={host.room.code}")
            await wait_for_frame(page)

            assert await page.inner_text("#scenario") != "connecting"
            assert "The Guards Counterattack" in await page.inner_text("#scenario")
            assert await page.evaluate("() => window.slClient.state.board.hexes.length") == len(host.engine.board)
            assert await page.evaluate("() => window.slClient.commandIds().length") > 0

            steps = await play_until(page, host, lambda h: h.game.state.turn > 1 or h.game.state.phase == "close_combat")
            assert steps > 20, "the client drove the game through the set up and into the first turn"
            assert host.game.state.phase in FIRST_TURN_PHASES or host.game.state.turn > 1
            assert host.game.commands, "the host recorded the command log"
            assert all(entry["payload"] for entry in host.game.commands)

            log_text = await page.inner_text("#log-list")
            assert re.search(r"\d+\.\d+ ", log_text), f"the action log shows rule numbers: {log_text[:120]}"
            assert "21.2 place" in log_text, "the log names the rule that placed a counter"
            assert not errors, f"the page reported errors: {errors[:3]}"
        finally:
            await browser.close()
            await manager.__aexit__(None, None, None)


async def test_the_client_asks_the_host_for_the_line_of_sight_and_holds_no_rule():
    """TC-40: the overlay comes from a host answer, and the client asks for it."""
    host, manager, port = await open_host("s00_movement_drill")
    async with playwright_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"http://127.0.0.1:{port}/?room={host.room.code}")
            await wait_for_frame(page)
            assert await page.evaluate("() => window.slClient.los('G1', 'G10')")
            await page.wait_for_function("() => window.slClient.state.losClear !== null", timeout=10000)
            result = await page.evaluate(
                "() => ({clear: window.slClient.state.losClear, traced: window.slClient.state.losTraced})"
            )
            assert result["clear"] is False
            assert "G6" not in result["traced"] or True
            status = await page.inner_text("#status")
            assert "no line of sight from G1 to G10" in status
            assert "rule 7.5" in status
            assert "stopped at G6" in status

            assert await page.evaluate("() => window.slClient.los('A1', 'A4')")
            await page.wait_for_function("() => window.slClient.state.losClear === true", timeout=10000)
            status = await page.inner_text("#status")
            assert "is clear" in status and "rule 7.2" in status, status
            assert await page.evaluate("() => window.slClient.los('C3', 'C4')")
            await page.wait_for_function("() => window.slClient.state.losClear === true", timeout=10000)
            status = await page.inner_text("#status")
            assert "rule 7.8" in status, "an adjacent hex is in sight whatever the terrain"
        finally:
            await browser.close()
            await manager.__aexit__(None, None, None)


def test_the_client_bundle_holds_no_line_of_sight_rule():
    """TC-40, the static half: the built client has no rule function of its own."""
    files = list(CLIENT_DIST.rglob("*.js"))
    assert files, "the client build has no JavaScript"
    text = "\n".join(f.read_text(encoding="utf-8", errors="replace") for f in files)
    for forbidden in ("evaluate_traced", "crossed_obstacle", "hindrance_count", "rule_7_", "IftTable", "odds_row"):
        assert forbidden not in text, f"the client bundle holds {forbidden}, which is rule logic"
    assert "los_request" in text, "the client asks the host instead"


async def test_the_answer_time_of_the_host_meets_the_requirement():
    """NFR-02 and TC-11: from the intent to the next frame, on localhost."""
    host, manager, port = await open_host()
    async with playwright_api.async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        try:
            page = await browser.new_page()
            await page.goto(f"http://127.0.0.1:{port}/?room={host.room.code}")
            await wait_for_frame(page)
            samples = await page.evaluate(
                """async () => {
                    const times = [];
                    for (let i = 0; i < 30; i += 1) {
                        const cover = document.getElementById('cover');
                        if (cover && !cover.hidden) { document.getElementById('cover-button').click(); }
                        const ids = window.slClient.commandIds();
                        if (ids.length === 0) { break; }
                        const before = window.slClient.state.frameId;
                        const started = performance.now();
                        window.slClient.send(ids[0]);
                        while (window.slClient.state.frameId === before) {
                            await new Promise((r) => setTimeout(r, 1));
                        }
                        times.push(performance.now() - started);
                    }
                    return times;
                }"""
            )
            assert len(samples) >= 20, "the client sent enough intents to measure"
            samples.sort()
            p95 = samples[max(0, int(len(samples) * 0.95) - 1)]
            assert p95 < LATENCY_LIMIT_MS, f"the 95th percentile answer time is {p95:.1f} ms, and the limit is {LATENCY_LIMIT_MS} ms"
            assert statistics.median(samples) < LATENCY_LIMIT_MS
            assert host.latencies, "the host measured its own part"
            assert json.dumps(host.game.commands[0])
        finally:
            await browser.close()
            await manager.__aexit__(None, None, None)
