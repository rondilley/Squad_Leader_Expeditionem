"""The options of a unit (`options_request`, `slhost.options`).

The window has no rule logic (AR-06), so the host says why a hex of the set up area
refuses a counter, which hexes a unit reaches in the rest of the Movement Phase, and the
field of fire of a unit in a fire phase. Each test compares the answer with the legal list
of the core, which stays the one source of a command.
"""

from __future__ import annotations

from slagents.base import decide
from slagents.registry import make_agent
from slcli.play import build_engine
from slcore import geometry
from slhost import options, protocol
from slhost.server import Host
from slwindow.overlay import setup_refusal

from tests.host.test_play_flow import joined, open_host

SCENARIO = "lib01_grain_office"


def _apply(game, test) -> None:
    frame = game.engine.legal_commands(game.state)
    chosen = next(c for c in frame.commands if test(c.command))
    game.apply(frame.frame_id, chosen.id)


def _end_axis_setup(game) -> None:
    """Place the axis counters with the v1 agent and end their set up."""
    agent = make_agent("v1", game.engine, 1, 1)
    while game.state.active == 1 and game.state.phase == "setup":
        frame = game.engine.legal_commands(game.state)
        game.apply(frame.frame_id, decide(agent, game.state, frame))


def _play_until(game, test, limit: int = 4000) -> None:
    agents = {p: make_agent("v1", game.engine, 1, p) for p in (0, 1)}
    for _ in range(limit):
        if test(game.state):
            return
        frame = game.engine.legal_commands(game.state)
        game.apply(frame.frame_id, decide(agents[frame.player], game.state, frame))
    raise AssertionError("the game did not reach the state of the test")


def test_a_full_hex_of_the_set_up_area_gives_the_limit_of_rule_6_1():
    game = Host(build_engine(SCENARIO), seed=1).game
    _end_axis_setup(game)
    state = game.state
    squads = [u.id for u in state.units if u.player == 0 and u.kind == "squad"]
    assert len(squads) >= 4
    _apply(game, lambda c: c.action == "place" and c.units == (squads[0],))
    here = game.state.units[squads[0]].hex
    for unit in squads[1:3]:
        _apply(game, lambda c, unit=unit: c.action == "place" and c.units == (unit,) and c.hex == here)
    fourth = next(u for u in squads[3:] if game.state.units[u].hex is None)
    answer = options.unit_options(game.engine, game.state, fourth)
    name = geometry.hex_id(*here)
    assert answer["kind"] == "setup" and answer["area"] == "in columns C to I"
    assert name in answer["full"]
    assert answer["why"][name] == f"{name} would hold 4 squads of yours. Rule 6.1 lets a hex hold 3."
    # Each hex of the area that the legal list does not name for the counter has a reason.
    frame = game.engine.legal_commands(game.state)
    offered = [c.command for c in frame.commands if c.command.action == "place" and c.command.units[0] == fourth]
    legal = {geometry.hex_id(*c.hex) for c in offered}
    assert name not in legal and not legal & set(answer["why"])


def test_a_counter_of_the_other_side_waits_for_its_set_up():
    game = Host(build_engine(SCENARIO), seed=1).game
    allied = next(u for u in game.state.units if u.player == 0)
    answer = options.unit_options(game.engine, game.state, allied.id)
    assert answer["later"].startswith("The other side sets up now.")
    assert setup_refusal(answer, "4-4-7", "C3") == answer["later"]


def test_a_weapon_with_no_carrier_in_a_hex_says_so():
    game = Host(build_engine(SCENARIO), seed=1).game
    _end_axis_setup(game)
    mmg = next(u for u in game.state.units if u.player == 0 and u.type_key.endswith(":MMG"))
    answer = options.unit_options(game.engine, game.state, mmg.id)
    assert answer["why"], "no unit of the side is on the board yet"
    assert all(text.startswith("No unit of yours in") for text in answer["why"].values())


def test_a_hex_outside_the_area_gives_the_area_of_the_card():
    answer = {"kind": "setup", "area": "in columns C to I", "why": {}, "full": [], "later": ""}
    assert setup_refusal(answer, "4-4-7", "Q5") == "Q5 is outside the set up area. The 4-4-7 sets up in columns C to I."
    assert setup_refusal(None, "4-4-7", "Q5") is None


def test_the_reach_of_a_unit_holds_each_step_of_the_legal_list():
    game = Host(build_engine(SCENARIO), seed=1).game
    _play_until(game, lambda s: s.phase == "movement" and not s.game_over)
    frame = game.engine.legal_commands(game.state)
    steps: dict[int, set[str]] = {}
    for legal in frame.commands:
        if legal.command.action == "move":
            steps.setdefault(legal.command.units[0], set()).add(geometry.hex_id(*legal.command.hex))
    assert steps, "a unit of the attacker can move"
    for unit_id, hexes in steps.items():
        answer = options.unit_options(game.engine, game.state, unit_id)
        assert answer["kind"] == "move" and answer["left"] > 0
        assert hexes <= set(answer["reach"]), "each next step is a hex the unit reaches"
        assert all(0 < cost <= answer["left"] for cost in answer["reach"].values())
        assert len(answer["reach"]) > len(hexes), "the reach goes past the next step"


def test_a_unit_with_no_move_has_no_reach():
    game = Host(build_engine(SCENARIO), seed=1).game
    _play_until(game, lambda s: s.phase == "movement" and not s.game_over)
    defender = next(u for u in game.state.units if u.player != game.state.active and u.hex is not None)
    assert options.unit_options(game.engine, game.state, defender.id)["reach"] == {}


def test_the_field_of_fire_holds_each_legal_target_of_the_unit():
    game = Host(build_engine(SCENARIO), seed=1).game
    _play_until(
        game,
        lambda s: s.phase == "defensive_fire"
        and any(c.command.action == "group_add" for c in game.engine.legal_commands(s).commands),
    )
    frame = game.engine.legal_commands(game.state)
    targets: dict[int, set[str]] = {}
    for legal in frame.commands:
        if legal.command.action == "group_add":
            targets.setdefault(legal.command.units[0], set()).add(geometry.hex_id(*legal.command.hex))
    for unit_id, hexes in targets.items():
        answer = options.unit_options(game.engine, game.state, unit_id)
        field = set(answer["normal"]) | set(answer["long"])
        assert hexes <= field, "a legal target is in the field of fire"
        assert not set(answer["normal"]) & set(answer["long"])
    strict = options.unit_options(game.engine, game.state, next(iter(targets)), strict_los=True)
    assert strict["strict"] and not strict["normal"] and not strict["long"]


def test_a_leader_has_no_field_of_its_own():
    game = Host(build_engine(SCENARIO), seed=1).game
    _play_until(game, lambda s: s.phase == "prep_fire")
    leader = next(u for u in game.state.units if u.player == game.state.active and u.kind == "leader" and u.hex is not None)
    answer = options.unit_options(game.engine, game.state, leader.id)
    assert not answer["normal"] and "directs the fire" in answer["note"]


async def test_the_host_answers_an_options_request_for_the_frame_of_the_connection():
    host, manager, port = await open_host(build_engine(SCENARIO))
    try:
        socket, client = await joined(port, host.room.code)
        async with socket:
            frame = await client.until(protocol.HOST_FRAME)
            unit = next(u for u in host.game.state.units if u.player == host.game.state.active)
            await client.send({"type": "options_request", "unit": unit.id})
            answer = await client.until(protocol.HOST_OPTIONS_RESULT)
            assert answer["unit"] == unit.id and answer["frame_id"] == frame["frame_id"]
            assert answer["result"]["kind"] == "setup" and answer["result"]["area"]
            await client.send({"type": "options_request", "unit": 10_000})
            error = await client.until(protocol.HOST_ERROR)
            assert "no unit" in error["message"]
    finally:
        await manager.__aexit__(None, None, None)


async def test_move_to_plays_each_step_of_the_path_through_the_core():
    host, manager, port = await open_host(build_engine(SCENARIO))
    try:
        _play_until(host.game, lambda s: s.phase == "movement" and not s.game_over)
        state = host.game.state
        frame = host.game.engine.legal_commands(state)
        mover = next(c.command.units[0] for c in frame.commands if c.command.action == "move")
        _ids, _left, paths = options.move_paths(host.game.engine, state, state.units[mover])
        target, path = max(paths.items(), key=lambda item: (len(item[1]), item[0]))
        assert len(path) >= 2, "a far hex, past the next step"
        name = geometry.hex_id(*target)
        before = len(host.game.commands)
        socket, client = await joined(port, host.room.code)
        async with socket:
            frame = await client.until(protocol.HOST_FRAME)
            await client.send({"type": "move_to", "frame_id": "0" * 32, "unit": mover, "hex": name})
            stale = await client.until(protocol.HOST_ERROR)
            assert stale["code"] == protocol.CODE_STALE_FRAME
            await client.send({"type": "move_to", "frame_id": frame["frame_id"], "unit": mover, "hex": name})
            await client.until(protocol.HOST_FRAME)
            assert host.game.state.units[mover].hex == target
            steps = host.game.commands[before:]
            assert len(steps) == len(path), "one command of the core for each hex"
            assert all(c["payload"]["action"] == "move" for c in steps)
            assert any(line.get("kind") == "move_to" and line["data"]["steps"] == len(path) for line in host.game.log)
            # One undo takes back the whole route (hot seat), when no die rolled in it.
            assert all(c["quiet"] for c in steps), "a move rolls no die"
            start = state.units[mover].hex
            await client.send({"type": "undo"})
            await client.until(protocol.HOST_FRAME)
            assert len(host.game.commands) == before
            assert host.game.state.units[mover].hex == start
            await client.send({"type": "move_to", "frame_id": client.last["frame_id"], "unit": mover, "hex": name})
            await client.until(protocol.HOST_FRAME)
            assert host.game.state.units[mover].hex == target
            # A hex the unit cannot get to is refused, and nothing moves.
            frame = client.last
            await client.send({"type": "move_to", "frame_id": frame["frame_id"], "unit": mover, "hex": "A1"})
            error = await client.until(protocol.HOST_ERROR)
            assert "cannot get to A1" in error["message"]
            assert host.game.state.units[mover].hex == target
    finally:
        await manager.__aexit__(None, None, None)


def test_the_reach_of_a_vehicle_is_the_hexes_its_route_gets_to_through_the_core():
    game = Host(build_engine("s04_armor_probe"), seed=1).game
    agents = {p: make_agent("v7", game.engine, 1, p) for p in (0, 1)}

    def vehicles_move(state) -> bool:
        if state.phase != "movement":
            return False
        frame = game.engine.legal_commands(state)
        return any(c.command.action == "vehicle_move" for c in frame.commands)

    for _ in range(4000):
        if vehicles_move(game.state):
            break
        frame = game.engine.legal_commands(game.state)
        game.apply(frame.frame_id, decide(agents[frame.player], game.state, frame))
    state = game.state
    frame = game.engine.legal_commands(state)
    vehicle = state.units[next(c.command.units[0] for c in frame.commands if c.command.action == "vehicle_move")]
    answer = options.unit_options(game.engine, state, vehicle.id)
    assert answer["kind"] == "move" and answer["rule_id"] == "30.2" and answer["left"] > 0
    first = {
        geometry.hex_id(*c.command.hex)
        for c in frame.commands
        if c.command.action == "vehicle_move" and c.command.units == (vehicle.id,)
    }
    # Rule 30.8: a hex of another vehicle of the side is a hex to go through, not to stop in.
    crowded = {
        geometry.hex_id(*u.hex) for u in state.units if u.is_vehicle and u.id != vehicle.id and u.hex is not None and not u.wreck
    }
    assert crowded & first, "the test state has a hex to go through"
    assert first - crowded <= set(answer["reach"]), "each first step of the legal list is in the reach"
    assert not crowded & set(answer["reach"])
    assert len(answer["reach"]) > len(first)
    for name in sorted(answer["reach"], key=lambda h: (-answer["reach"][h], h))[:12]:
        target = geometry.parse_hex_id(name)
        here = state
        for step in options.route(game.engine, state, vehicle, target):
            step_frame, legal = options.route_step(game.engine, here, step)
            assert legal is not None, f"each step to {name} is in the legal list"
            here, _ = game.engine.apply(here, legal.command, step_frame)
        assert here.units[vehicle.id].hex == target or here.units[vehicle.id].immobilized
