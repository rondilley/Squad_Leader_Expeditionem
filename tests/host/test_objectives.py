"""The victory conditions in each frame (`slhost.objectives`).

The owner found that a person cannot see during play what wins the game. Each frame gives
the conditions of the scenario, their hexes, and the present count of the viewer's own
conditions. The count of the other side's conditions stays out, so it gives no fact of a
hidden unit (AR-09).
"""

from __future__ import annotations

from slagents.base import decide
from slagents.registry import make_agent
from slcli.play import build_engine
from slcore import geometry
from slhost import annotate, objectives, protocol
from slhost.server import Host

from tests.host.test_play_flow import joined, open_host

SCENARIO = "lib01_grain_office"
OFFICE = ["Z6", "AA6", "AA7", "BB6", "CC6"]


def test_each_side_gets_the_hexes_and_only_its_own_side_gets_the_count():
    engine = build_engine(SCENARIO)
    state = engine.new_game(1)
    sides = annotate.side_names(engine)
    russian = objectives.document(engine, state, 0, sides)
    german = objectives.document(engine, state, 1, sides)
    assert len(russian) == 1 and russian[0]["side"] == 0 and russian[0]["side_name"] == "Russian"
    assert sorted(russian[0]["hexes"]) == sorted(OFFICE)
    assert russian[0]["note"].startswith("The Russians win if they end the game in control of 1 hex")
    assert russian[0]["status"] == {
        "count": 0,
        "threshold": 1,
        "satisfied": False,
        "detail": "controls 0 of 5 hexes, and needs 1 (PR-16)",
        "held": [],
    }
    assert sorted(german[0]["hexes"]) == sorted(OFFICE)
    assert "status" not in german[0], "the count of the other side's condition stays out (AR-09)"
    watcher = objectives.document(engine, state, -1, sides, spectator=True)
    assert "status" in watcher[0]


def test_the_count_follows_the_hexes_that_the_side_holds():
    host = Host(build_engine(SCENARIO), seed=1)
    game = host.game
    agents = {p: make_agent("v7", game.engine, 1, p) for p in (0, 1)}
    for _ in range(6000):
        state = game.state
        found = objectives.document(game.engine, state, 0, game.sides)[0]["status"]
        if found["count"] > 0:
            break
        if state.game_over:
            raise AssertionError("v7 did not take a hex of the office in this game")
        frame = game.engine.legal_commands(state)
        game.apply(frame.frame_id, decide(agents[frame.player], state, frame))
    held = found["held"]
    assert found["count"] == len(held) > 0 and set(held) <= set(OFFICE)
    for hex_id in held:
        units = game.state.infantry_in(geometry.parse_hex_id(hex_id))
        assert all(u.player == 0 for u in units)


def test_the_conditions_of_other_scenarios_name_their_hexes():
    sides = {0: "a", 1: "b"}
    for name, kinds in (
        ("s01_guards_counterattack", ["building_swing", "unbroken_squad_ratio"]),
        ("s02_tractor_works", ["hex_control", "hex_control", "sole_occupant", "sole_occupant"]),
        ("lib12_the_long_front", ["building_count"]),
    ):
        engine = build_engine(name)
        found = objectives.document(engine, engine.new_game(1), 0, sides, spectator=True)
        assert [r["kind"] for r in found] == kinds
        assert any(r["hexes"] for r in found), name


async def test_each_frame_holds_the_objectives():
    host, manager, port = await open_host(build_engine(SCENARIO))
    try:
        socket, client = await joined(port, host.room.code)
        async with socket:
            frame = await client.until(protocol.HOST_FRAME)
            assert sorted(frame["objectives"][0]["hexes"]) == sorted(OFFICE)
    finally:
        await manager.__aexit__(None, None, None)
