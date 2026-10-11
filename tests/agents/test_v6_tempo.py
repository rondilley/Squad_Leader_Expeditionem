"""Agent v6: the tempo agent. The attacker keeps to a schedule and it does not freeze.

The first gauntlet (2026-09-12) found that agents v4 and v5 as the attacker of scenario 1
move on turn 1 and then stand for the rest of the game, so a random defender beats them.
The tests here read each behavior that v6 changes, on real states of a real game:
- v6 gives a legal command in each frame, and v6 against v6 replays to the same hash (TR-02).
- The attacker moves after turn 1. The frozen attacker is the defect this agent corrects.
- The side with a positional victory condition has the deadline, the other side does not.
- A pressed unit stays out of the prep fire groups, so it keeps its move (rule 8.1).
- The plan divides the force among the nearest targets, and a taken building keeps a garrison.
- The defender of scenario 1 holds its own buildings, not the Russian ones.
- The route field prefers a covered approach to a street a machine gun covers.
- A step into a hex over the stacking limit is not in the list (rule 6.1).
"""

from __future__ import annotations

from collections import Counter

import pytest

from slcli.play import build_engine, make_agent, play_game
from slcore import geometry
from slcore.game import PHASE_MOVEMENT, PHASE_PREP_FIRE
from slcore.rules import r06_stacking
from slcore.rules.r13_rout import is_cover
from slagents.scripted.v6 import ScriptedV6, UnknownNation, profile_for, with_parameters

SCENARIO = "s01_guards_counterattack"


def _play_until(engine, agents, stop):
    """Play until stop(state, frame) is true, and give that state and frame."""
    state = engine.new_game(5)
    steps = 0
    while not state.game_over and steps < 5000:
        frame = engine.legal_commands(state)
        if stop(state, frame):
            return state, frame
        chosen = agents[state.active].select(state, frame)
        state, _ = engine.apply(state, frame.by_id(chosen).command, frame)
        steps += 1
    raise AssertionError("the game did not reach the state the test wants")


def test_v6_plays_a_full_game_and_replays():
    engine = build_engine(SCENARIO)
    record = play_game(engine, 7, (make_agent("v6", engine, 7, 0), make_agent("v6", engine, 7, 1)))
    assert record.hashes, "the game produced a hash sequence"
    again = engine.replay(7, [c["payload"] for c in record.commands])
    assert again == record.hashes, "v6 against v6 is deterministic (TR-02)"


def test_v6_gives_a_legal_command_in_each_frame_of_a_game():
    engine = build_engine(SCENARIO)
    agents = (make_agent("v6", engine, 3, 0), make_agent("v6", engine, 3, 1))
    state = engine.new_game(3)
    steps = 0
    while not state.game_over and steps < 5000:
        frame = engine.legal_commands(state)
        chosen = agents[state.active].select(state, frame)
        assert frame.by_id(chosen) is not None, "the chosen id is in the frame"
        state, _ = engine.apply(state, frame.by_id(chosen).command)
        steps += 1
    assert steps > 0


def test_the_attacker_moves_after_turn_one():
    """The frozen attacker: v5 as the Russian moves on turn 1 and then stands. v6 moves on."""
    engine = build_engine(SCENARIO)
    moves_by_turn: dict[str, Counter] = {}
    for kind in ("v5", "v6"):
        counts: Counter = Counter()
        for seed in (20260912, 20260913, 20260914):
            record = play_game(engine, seed, (make_agent(kind, engine, seed, 0), make_agent("random", engine, seed, 1)))
            turn = 0
            player = None
            for e in record.events:
                if e["kind"] == "phase":
                    # The phase event carries the turn and the phasing player.
                    turn = e["data"]["turn"]
                    player = e["data"]["phasing"]
                if e["kind"] in ("move", "advance") and player == 0 and turn >= 2:
                    counts[turn] += 1
        moves_by_turn[kind] = counts
    v5_later = sum(moves_by_turn["v5"].values())
    v6_later = sum(moves_by_turn["v6"].values())
    assert v6_later > v5_later * 3, f"v6 moves after turn 1 ({v6_later}) and v5 does not ({v5_later})"
    assert all(moves_by_turn["v6"][t] > 0 for t in (2, 3, 4, 5)), "v6 moves on each turn after the first"


def test_the_side_with_the_positional_condition_has_the_deadline():
    engine = build_engine(SCENARIO)
    russian = ScriptedV6(engine, 0)
    german = ScriptedV6(engine, 1)
    assert russian.has_deadline, "the Russians must take buildings by the end (building_swing)"
    assert not german.has_deadline, "the Germans win when the Russians do not"
    assert russian.targets_wanted == 3, "the swing margin is 2, so the plan aims at 3 buildings"


def test_the_defender_holds_its_own_buildings():
    """v1 sends the German toward the Russian buildings. v6's German holds the German ones."""
    engine = build_engine(SCENARIO)
    german_v1 = make_agent("v1", engine, 1, 1)
    german_v6 = ScriptedV6(engine, 1)
    agents = (make_agent("v6", engine, 5, 0), german_v6)
    state, _frame = _play_until(engine, agents, lambda s, f: s.active == 0 and f.phase == PHASE_MOVEMENT and s.turn == 1)
    russian_hexes = {u.hex for u in state.player_units(0) if u.hex is not None}
    german_hexes = {u.hex for u in state.player_units(1) if u.hex is not None}
    # The set up puts each side in its own buildings, and the objectives of the v6 German
    # are hexes of the buildings the Russian condition names, which is where the Germans stand.
    assert german_hexes, "the game starts with the Germans on the board"
    assert any(h in german_v6.objectives for h in german_hexes), "the v6 German objectives are the German buildings"
    assert not any(h in german_v6.objectives for h in russian_hexes), "and not the Russian buildings"
    assert any(h in german_v1.objectives for h in russian_hexes), "v1 aims the German at the Russian buildings"


def test_a_pressed_unit_stays_out_of_the_prep_fire_groups():
    """Rule 8.1: a unit that fires in the Prep Fire Phase cannot move. A pressed unit keeps its move."""
    engine = build_engine(SCENARIO)
    # A margin so large that each Russian unit with a distance to go is pressed from turn 1.
    agent = ScriptedV6(engine, 0, with_parameters(schedule_margin=20))
    agents = (agent, make_agent("random", engine, 5, 1))
    state, frame = _play_until(engine, agents, lambda s, f: s.active == 0 and f.phase == PHASE_PREP_FIRE and s.turn == 1)
    by_action: dict[str, list] = {}
    for lc in frame.commands:
        by_action.setdefault(lc.command.action, []).append(lc)
    adds = by_action.get("group_add", [])
    assert adds, "the Russians have a target to fire at on turn 1"
    agent._refresh_routes(state)
    agent._refresh_objectives(state)
    pressed_units = {lc.command.units[0] for lc in adds if agent._maneuver_unit(state, lc.command.units[0])}
    assert pressed_units, "some unit with a target is pressed"
    chosen = agent.select(state, frame)
    lc = frame.by_id(chosen)
    assert lc is not None
    if lc.command.action in ("group_add", "group_add_weapon"):
        assert lc.command.units[0] not in pressed_units, "a pressed unit does not join a prep fire group"


def test_the_plan_divides_the_force_among_the_nearest_targets():
    engine = build_engine(SCENARIO)
    agent = ScriptedV6(engine, 0)
    agents = (agent, make_agent("random", engine, 5, 1))
    state, _frame = _play_until(engine, agents, lambda s, f: s.active == 0 and f.phase == PHASE_MOVEMENT and s.turn == 1)
    agent._refresh_routes(state)
    agent._refresh_objectives(state)
    targets = Counter(agent.assignment.values())
    assert len(targets) == agent.targets_wanted, "three targets get a share"
    shares = sorted(targets.values())
    assert shares[-1] - shares[0] <= 1, f"the shares are equal within one unit: {shares}"
    for unit_id, hexes in agent.assignment.items():
        assert all(h in agent.objectives for h in hexes), "each target is an objective building"
        assert state.units[unit_id].player == 0


def test_a_taken_building_keeps_one_garrison():
    """After the Russians take a building, one squad inside it measures its gain to that building."""
    engine = build_engine(SCENARIO)
    agent = ScriptedV6(engine, 0)
    agents = (agent, make_agent("random", engine, 5, 1))
    from slcore.rules import victory

    enemy = victory.group_buildings(engine.scenario, engine.board, ["g_kelso", "g_pollack", "g_wetzelberge", "g_hamblen", "g_hieken"])

    def taken(s, f):
        return s.active == 0 and any(victory.controlled_by(s, engine.board, b, 0) for b in enemy)

    state, _frame = _play_until(engine, agents, taken)
    agent._refresh_routes(state)
    agent._refresh_objectives(state)
    building = next(b for b in enemy if victory.controlled_by(state, engine.board, b, 0))
    hexes = victory.buildings_on(engine.board)[building]
    garrison = [uid for uid, target in agent.assignment.items() if target == hexes]
    assert len(garrison) == 1, "one unit holds the taken building"
    assert state.units[garrison[0]].hex in hexes, "and it stands inside it"
    assert not any(h in agent.open_objectives for h in hexes), "the taken building is not an open objective"


def test_the_route_field_prefers_cover_to_a_covered_street():
    """The safe route field costs more for an open hex under fire than for a covered one under the same fire."""
    engine = build_engine(SCENARIO)
    agent = ScriptedV6(engine, 0)
    agents = (agent, make_agent("random", engine, 5, 1))
    state, _frame = _play_until(engine, agents, lambda s, f: s.active == 0 and f.phase == PHASE_MOVEMENT and s.turn == 1)
    agent._refresh_routes(state)
    agent._refresh_objectives(state)
    board = engine.board
    threatened_open = [h.ref for h in board if h.terrain == "open" and agent._threat(state, h.ref, agent._threat_map) >= 8]
    threatened_cover = [h.ref for h in board if is_cover(board, h.ref) and agent._threat(state, h.ref, agent._threat_map) >= 8]
    assert threatened_open and threatened_cover, "the Germans see open hexes and covered hexes"
    open_risk = min(agent._hex_risk(state, h) for h in threatened_open)
    cover_risk = max(agent._hex_risk(state, h) for h in threatened_cover if agent._threat(state, h, agent._threat_map) < 16)
    assert open_risk > 0, "an open hex under one squad of fire has a risk"
    for h in threatened_open:
        same_cover = [c for c in threatened_cover if agent._threat(state, c, agent._threat_map) == agent._threat(state, h, agent._threat_map)]
        for c in same_cover:
            assert agent._hex_risk(state, h) > agent._hex_risk(state, c), "the same fire costs more in the open"
    target = agent.objectives
    safe = agent._route_field(state, target, safe=True)
    fast = agent._route_field(state, target, safe=False)
    assert all(safe[h] >= fast[h] for h in fast), "the safe route is never cheaper than the fastest one"
    assert any(safe[h] > fast[h] for h in fast), "and it pays for the cover somewhere"


def test_a_step_over_the_stacking_limit_is_not_in_the_list():
    engine = build_engine(SCENARIO)
    agent = ScriptedV6(engine, 0)
    agents = (agent, make_agent("random", engine, 5, 1))
    state, frame = _play_until(engine, agents, lambda s, f: s.active == 0 and f.phase == PHASE_MOVEMENT and s.turn == 1)
    # Each move in the frame that would put its destination over the limit is one the agent skips.
    over = [
        lc
        for lc in frame.commands
        if lc.command.action in ("move", "stack_move")
        and lc.command.hex is not None
        and r06_stacking.rule_6_1_overstacked(state, engine.types, lc.command.hex, 0, extra_ids=tuple(lc.command.units))
    ]
    for lc in over:
        assert agent._would_overstack(state, lc.command.hex, lc.command.units)
    chosen = frame.by_id(agent.select(state, frame))
    assert chosen is not None
    if chosen.command.action in ("move", "stack_move"):
        assert not agent._would_overstack(state, chosen.command.hex, chosen.command.units)


def test_the_nation_profiles_load_and_british_is_not_defined():
    for nation in ("german", "soviet", "american"):
        assert profile_for(nation).schedule_margin >= 1
    assert profile_for("soviet").schedule_margin > profile_for("american").schedule_margin, "the Soviet profile presses first"
    with pytest.raises(UnknownNation):
        profile_for("british")


def test_with_parameters_changes_one_named_field():
    p = with_parameters(route_risk=5)
    assert p.route_risk == 5
    assert p.aggression == 2, "the other fields keep the default"


def test_v6_plays_a_side_that_has_no_objective_hex():
    """Scenario 2 gives one side no objective hex. The route cost of v6 took the minimum
    distance to an empty set of targets and raised ValueError in the Movement Phase. The
    game is the one the parameter sweep of 2026-10-10 found."""
    engine = build_engine("s02_tractor_works")
    attacker = ScriptedV6(engine, 0, with_parameters(schedule_margin=1, threat_aversion=0, route_risk=4, aggression=3))
    defender = ScriptedV6(engine, 1)
    record = play_game(engine, 90000, (attacker, defender))
    assert record.result
