"""The armor policy of the scripted agents (`slagents/scripted/armor.py`).

The owner watched the armor scenario and said: "The tanks do not move in a sane manner and
do not fire." The tanker drove each tank one hex at a time for a gain in hex distance and
stopped at the first building in the way, and v6 had no policy for a vehicle. These tests
play real games of scenario 4 and read what the tanks did.
"""

from __future__ import annotations

from collections import Counter, defaultdict

import pytest

from slagents.base import decide
from slcli.play import build_engine, make_agent
from slcore.rules import r30_vehicle_movement

SCENARIO = "s04_armor_probe"


def _play(first: str, second: str, seed: int):
    engine = build_engine(SCENARIO)
    state = engine.new_game(seed)
    agents = {0: make_agent(first, engine, seed, 0), 1: make_agent(second, engine, seed, 1)}
    played: Counter = Counter()
    paths: dict[int, list[str]] = defaultdict(list)
    count = 0
    while not state.game_over and count < 20000:
        frame = engine.legal_commands(state)
        chosen = frame.by_id(decide(agents[state.active], state, frame))
        played[(state.active, chosen.payload["action"])] += 1
        state, events = engine.apply(state, chosen.command, frame)
        for event in events:
            if event.kind == "vehicle_move":
                paths[event.data["unit"]].append(event.data["to"])
        count += 1
    return engine, state, played, paths


@pytest.mark.parametrize("first,second", [("v3", "v6"), ("v6", "v3")])
def test_each_side_drives_and_fires_its_tanks(first, second):
    for seed in (1, 2, 3):
        _, state, played, paths = _play(first, second, seed)
        assert state.game_over, f"seed {seed} did not end"
        for side in (0, 1):
            assert played[(side, "vehicle_move")] >= 3, f"side {side} did not drive (seed {seed})"
            assert played[(side, "afv_fire")] + played[(side, "afv_mg")] >= 1, f"side {side} did not fire (seed {seed})"


def test_the_tanks_do_not_drive_back_and_forth():
    reversals = moves = 0
    for seed in range(1, 6):
        _, _, _, paths = _play("v3", "v6", seed)
        for path in paths.values():
            moves += len(path)
            reversals += sum(1 for i in range(2, len(path)) if path[i] == path[i - 2])
    assert moves >= 40
    assert reversals <= 0.05 * moves, f"{reversals} reversals in {moves} moves"


def test_each_tank_fires_or_drives_on():
    """The old tanker stopped in front of the first building and never fired. Each German tank
    now fires, or drives at least three hexes along its route: a tank that reached a firing
    position early holds there and fires, which is right."""
    for seed in (1, 2):
        engine = build_engine(SCENARIO)
        state = engine.new_game(seed)
        agents = {0: make_agent("v3", engine, seed, 0), 1: make_agent("v6", engine, seed, 1)}
        fired: Counter = Counter()
        moved: Counter = Counter()
        while not state.game_over:
            frame = engine.legal_commands(state)
            chosen = frame.by_id(decide(agents[state.active], state, frame))
            state, events = engine.apply(state, chosen.command, frame)
            for event in events:
                if event.kind in ("to_hit", "afv_fire", "afv_mg_fire"):
                    fired[event.data["unit"]] += 1
                if event.kind == "vehicle_move":
                    moved[event.data["unit"]] += 1
        for unit in (u for u in state.units if u.is_vehicle and u.player == 0):
            if unit.immobilized or unit.wreck:
                continue  # rule 39.1 or a hit stopped it; that is the dice, not the policy
            assert fired[unit.id] > 0 or moved[unit.id] >= 3, f"tank {unit.id} neither fired nor drove on (seed {seed})"


def test_the_game_that_looped_ends_now():
    """Seed 3 of v3 against v6 looped with drop and pickup: a tank held a firing position in
    a hex with another vehicle (rule 30.8 keeps the phase open), and the infantry relief had
    no vehicle move. It ends now, and no vehicle ends a phase where it must leave."""
    engine, state, played, _ = _play("v3", "v6", 3)
    assert state.game_over
    assert played[(0, "drop")] < 20 and played[(0, "pickup")] < 20
    for vehicle in (u for u in state.units if u.is_vehicle):
        assert not r30_vehicle_movement.must_leave(state, vehicle)


def test_the_route_avoids_ground_that_needs_the_breakdown_die():
    """Rule 39.1: a hex that needs the breakdown die costs the route more, so over many games
    the tanks enter such hexes less than the shortest route would."""
    from slagents.scripted.armor import BREAKDOWN_PENALTY

    assert BREAKDOWN_PENALTY > 0
    engine = build_engine(SCENARIO)
    breakdowns = 0
    vehicle_moves = 0
    for seed in range(1, 6):
        state = engine.new_game(seed)
        agents = {0: make_agent("v3", engine, seed, 0), 1: make_agent("v6", engine, seed, 1)}
        while not state.game_over:
            frame = engine.legal_commands(state)
            chosen = frame.by_id(decide(agents[state.active], state, frame))
            state, events = engine.apply(state, chosen.command, frame)
            for event in events:
                if event.kind == "breakdown_roll":
                    breakdowns += 1
                if event.kind == "vehicle_move":
                    vehicle_moves += 1
    assert vehicle_moves >= 40
    assert breakdowns <= 0.02 * vehicle_moves, f"{breakdowns} breakdown rolls in {vehicle_moves} moves"


@pytest.mark.parametrize("seed", [1, 2, 3])
def test_each_german_vehicle_of_v7_drives_and_fires(seed):
    """The owner watched v7 against v6 on scenario 4: "Two of the tanks on the AXIS side
    appear to move once, then never move again during the game and never fire." The route
    compared only the cost from the next hex, so a step into a wood looked free, and two
    MkIVs drove into the woods on turn 1 and broke down (rule 39.1). Then an assault gun
    whose route went through the hex of its own tank stood for four turns. Each German
    vehicle now drives on and fires, and none enters ground that needs the breakdown die."""
    engine = build_engine(SCENARIO)
    state = engine.new_game(seed)
    agents = {0: make_agent("v7", engine, seed, 0), 1: make_agent("v6", engine, seed, 1)}
    fired: Counter = Counter()
    moved: Counter = Counter()
    breakdowns: Counter = Counter()
    while not state.game_over:
        frame = engine.legal_commands(state)
        chosen = frame.by_id(decide(agents[state.active], state, frame))
        state, events = engine.apply(state, chosen.command, frame)
        for event in events:
            if event.kind in ("to_hit", "afv_fire", "afv_mg_fire"):
                fired[event.data["unit"]] += 1
            if event.kind == "vehicle_move":
                moved[event.data["unit"]] += 1
            if event.kind == "breakdown_roll":
                breakdowns[event.data["unit"]] += 1
    german = [u for u in state.units if u.is_vehicle and u.player == 0]
    assert len(german) == 3
    for unit in german:
        assert breakdowns[unit.id] == 0, f"vehicle {unit.id} took the breakdown die (seed {seed})"
        assert moved[unit.id] >= 5, f"vehicle {unit.id} drove {moved[unit.id]} hexes (seed {seed})"
        assert fired[unit.id] > 0, f"vehicle {unit.id} never fired (seed {seed})"


def test_a_step_pays_for_the_ground_it_enters():
    """The cost of a step into a wood is its entry cost and the risk of rule 39.1, and the
    risk of a German vehicle (a 5 or a 6) is twice that of a Russian one (a 6)."""
    from slagents.scripted.armor import BREAKDOWN_PENALTY, ArmorPolicy

    engine = build_engine(SCENARIO)
    state = engine.new_game(1)
    board = engine.board
    wood = next(h for h in board.order if board.hex(h).terrain == "woods")
    src = next(n for n in board.neighbors(wood) if board.hex(n).terrain == "open")
    from slcore.rules.r28_vehicles import facing_towards

    risk = {}
    for player in (0, 1):
        vehicle = next(u for u in state.units if u.is_vehicle and u.player == player)
        probe = vehicle.with_(hex=src, facing=facing_towards(src, wood))
        entry = r30_vehicle_movement.entry_cost_halves(engine.vehicle_ctx, state, probe, wood)[0]
        risk[player] = ArmorPolicy(engine, player)._step_cost(state, probe, src, wood) - entry
    assert risk == {0: 2 * BREAKDOWN_PENALTY, 1: BREAKDOWN_PENALTY}
