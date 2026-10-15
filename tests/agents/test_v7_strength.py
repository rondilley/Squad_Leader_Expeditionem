"""Slice 7 of the 2026-09-23 review: the five v7 features, each behind a parameter.

Each test reads a feature on a real state of scenario 1 with the real engine:
- mass: two targets and a spare, the spare with the smaller share, and no step into a
  beaten hex before the group goes.
- advance_take: a hex next to the target that the defender sees earns no bonus.
- rally_points: each group has a rally leader, and a rout goes to a hex no enemy sees
  when the frame offers one.
- lookahead: the agent applies its best moves to the player state and plays a full game.
- the tree search: the macro of each player turn is the same on the same seed, and the
  agent plays a full game.
"""

from __future__ import annotations

import pytest

from slagents.base import decide
from slcli.play import build_engine, make_agent, play_game
from slcore import geometry, player_state
from slcore.game import PHASE_MOVEMENT, PHASE_ROUT
from slcore.rules.r11_terrain import is_open_ground
from slagents.scripted.v7 import MASS_HOLD, ScriptedV7, parameters_of_name

SCENARIO = "s01_guards_counterattack"
RUSSIAN = 0


@pytest.fixture(scope="module")
def engine():
    return build_engine(SCENARIO)


def _play_until(engine, agents, stop, seed: int = 9001, limit: int = 6000):
    state = engine.new_game(seed)
    for _ in range(limit):
        if state.game_over:
            break
        frame = engine.legal_commands(state)
        if stop(state, frame):
            return state, frame
        chosen = frame.by_id(decide(agents[frame.player], state, frame))
        state, _ = engine.apply(state, chosen.command, frame)
    raise AssertionError("the game did not reach the state the test wants")


def test_each_feature_is_a_parameter_and_only_step_two_is_on_by_default():
    base = parameters_of_name("v7:soviet")
    assert not base.mass and not base.rally_points
    assert base.advance_take and not base.open_moves, "step 2 won on the measure, so it is on"
    assert base.lookahead == 0 and base.search_iterations == 0
    defence = parameters_of_name("v7:german", defending=True)
    assert not defence.advance_take and defence.open_moves, "the defence record keeps the play it was measured with"
    on = parameters_of_name("v7:soviet[mass=1,advance_take=1,rally_points=1,lookahead=3,search_iterations=2]")
    assert on.mass and on.advance_take and on.rally_points and on.lookahead == 3 and on.search_iterations == 2


def test_mass_takes_two_targets_and_a_spare(engine):
    plain = ScriptedV7(engine, RUSSIAN, parameters_of_name("v7:soviet"))
    massed = ScriptedV7(engine, RUSSIAN, parameters_of_name("v7:soviet[mass=1]"))
    # Scenario 1: a swing of two buildings. The margin and one spare is three.
    assert massed.targets_wanted == 3
    assert plain.targets_wanted > massed.targets_wanted
    targets = [("a", ((0, 0),)), ("b", ((1, 0),)), ("c", ((2, 0),))]
    rooms = massed._target_rooms(targets, 12)
    assert rooms["c"] < rooms["a"] and rooms["a"] == rooms["b"]
    assert sum(rooms.values()) >= 12


def test_mass_holds_a_beaten_step_until_the_group_goes(engine):
    agent = ScriptedV7(engine, RUSSIAN, parameters_of_name("v7:soviet[mass=1]"))
    state, frame = _play_until(
        engine,
        (agent, make_agent("v7:german", engine, 9001, 1)),
        lambda s, f: f.player == RUSSIAN and f.phase == PHASE_MOVEMENT,
    )
    known = player_state.for_player(state, RUSSIAN)
    agent._refresh_routes(known)
    agent._refresh_objectives(known)
    held = 0
    for lc in frame.commands:
        if lc.command.action != "move" or lc.command.hex is None:
            continue
        unit = known.units[lc.command.units[0]]
        exposure = agent._exposure(known, unit, lc.command.hex, True)
        level = agent._press_level(known, unit.id, unit.hex)
        _, hold = agent._mass_exposure(known, unit, lc.command.hex, exposure, level)
        if level < 2 and exposure * 100 > agent.v7.stage_loss * 1296:
            assert hold == MASS_HOLD
            held += 1
    assert held > 0, "the first Movement Phase has a beaten step to hold back"


def test_advance_take_gives_no_bonus_for_a_hex_the_defender_sees(engine):
    agent = ScriptedV7(engine, RUSSIAN, parameters_of_name("v7:soviet"))
    state, _ = _play_until(
        engine,
        (agent, make_agent("v7:german", engine, 9001, 1)),
        lambda s, f: f.player == RUSSIAN and f.phase == PHASE_MOVEMENT,
    )
    known = player_state.for_player(state, RUSSIAN)
    agent._refresh_routes(known)
    agent._refresh_objectives(known)
    checked = 0
    for target in set(agent.assignment.values()):
        for t in target:
            for near in engine.board.neighbors(t):
                if near in target:
                    continue
                bonus = agent._hidden_approach(known, near, target)
                assert bonus == (0 if agent._seen_by_enemy(known, near) else agent.v7.hidden_bonus)
                checked += 1
    assert checked > 0


def test_rally_points_give_each_group_a_leader_and_rout_out_of_sight(engine):
    agent = ScriptedV7(engine, RUSSIAN, parameters_of_name("v7:soviet[rally_points=1]"))
    german = make_agent("v7:german", engine, 9002, 1)

    def rout_window(state, frame):
        if frame.player != RUSSIAN or frame.phase != PHASE_ROUT:
            return False
        return any(lc.command.action == "rout" for lc in frame.commands)

    state, frame = _play_until(engine, (agent, german), rout_window, seed=9002)
    known = player_state.for_player(state, RUSSIAN)
    chosen = frame.by_id(agent.select(known, frame))
    assert agent.rally_leaders, "each group has a rally leader"
    for leader in agent.rally_leaders.values():
        assert known.units[leader].kind == "leader" and not known.units[leader].broken
    options = [lc for lc in frame.commands if lc.command.action == "rout" and lc.command.hex is not None]
    unseen = [lc for lc in options if not agent._seen_by_enemy(known, lc.command.hex)]
    if chosen.command.action == "rout" and unseen:
        assert not agent._seen_by_enemy(known, chosen.command.hex), "the rout goes out of sight when it can"
    if chosen.command.action == "stay":
        here = known.units[chosen.command.units[0]].hex
        assert not agent._seen_by_enemy(known, here) or not options, "a stay only in a hex no enemy sees"


def test_lookahead_plays_a_full_game(engine):
    record = play_game(engine, 11, (make_agent("v7:soviet[lookahead=3]", engine, 11, 0), make_agent("v7:german", engine, 11, 1)))
    assert record.result in ("russian", "german", "draw")
    assert engine.replay(11, [c["payload"] for c in record.commands]) == record.hashes


def test_the_tree_search_is_deterministic_and_plays_a_full_game(engine):
    name = "v7:soviet[search_iterations=2,search_commands=300]"
    first = make_agent(name, engine, 12, 0)
    record = play_game(engine, 12, (first, make_agent("v7:german", engine, 12, 1)))
    assert record.result in ("russian", "german", "draw")
    assert first.macro_log, "the search picked a macro in each own Movement Phase"
    names = {macro for macro, _ in ScriptedV7.MACROS}
    assert all(macro in names for _, macro in first.macro_log)
    second = make_agent(name, engine, 12, 0)
    again = play_game(engine, 12, (second, make_agent("v7:german", engine, 12, 1)))
    assert second.macro_log == first.macro_log and again.hashes == record.hashes


def test_step_two_ends_no_advance_in_open_ground_the_enemy_sees(engine):
    """Step 2: an advance goes to cover, to dead ground, or into the target (rule 4.7)."""
    from slcore.game import PHASE_ADVANCE
    from slcore.rules.r13_rout import is_cover

    seed = 9003
    agent = make_agent("v7", engine, seed, RUSSIAN)
    german = make_agent("v7:german", engine, seed, 1)
    state = engine.new_game(seed)
    advances = 0
    while not state.game_over:
        frame = engine.legal_commands(state)
        known = player_state.for_player(state, frame.player)
        if frame.player == RUSSIAN:
            chosen = frame.by_id(agent.select(known, frame))
            unit = known.units[chosen.command.units[0]] if chosen.command.units else None
            if (
                frame.phase == PHASE_ADVANCE
                and chosen.command.action == "advance"
                and len(frame.commands) > 1
                and not unit.berserk
            ):
                # A frame with one command is forced, and the agent has no choice there.
                # A berserk unit charges (rule 18.42, PR-37): the frame holds only the
                # steps of its charge, with no end of the phase.
                dst = chosen.command.hex
                target = agent.assignment.get(unit.id, ())
                assert dst in target or is_cover(engine.board, dst) or not agent._seen_by_enemy(known, dst), (
                    f"an advance to {geometry.hex_id(*dst)} ends in open ground the enemy sees"
                )
                advances += 1
        else:
            chosen = frame.by_id(german.select(known, frame))
        state, _ = engine.apply(state, chosen.command, frame)
    assert advances > 0


def test_a_counter_threat_puts_a_stand_in_below_each_enemy_counter():
    """Scenario 4: the Russian squads set up below concealment counters. Without
    `counter_threat` the German attacker sees no enemy and so no threat, and it crossed
    the open street into their fire (2026-10-14). With it, each enemy counter that covers
    no unit the player sees holds one stand-in squad, and the threat model reads it."""
    s04 = build_engine("s04_armor_probe")
    axis = 0
    plain = ScriptedV7(s04, axis, parameters_of_name("v7"))
    wary = ScriptedV7(s04, axis, parameters_of_name("v7[counter_threat=1]"))
    agents = (make_agent("v7", s04, 7000001, 0), make_agent("v7", s04, 7000001, 1))
    state, _frame = _play_until(s04, agents, lambda st, fr: st.phase == PHASE_MOVEMENT and fr.player == axis, seed=7000001)
    known = player_state.for_player(state, axis)
    counters = sorted({c.hex for c in known.concealment if c.player != axis and c.hex is not None})
    masked = [u for u in known.player_units(1 - axis) if u.kind == "squad" and u.hex is None and not u.eliminated]
    assert counters and masked, "the Russian squads are below counters at the start"
    assert not [u for u in plain._seen_enemies(known) if u.is_infantry], "the attacker sees no Russian infantry"

    threat_state, enemies = wary._threat(known)
    stand_ins = [u for u in enemies if u.hex in counters]
    assert len(stand_ins) == min(len(counters), len(masked))
    assert len({u.hex for u in stand_ins}) == len(stand_ins), "one stand-in for each counter"
    assert all(threat_state.units[u.id].hex == u.hex and not u.broken for u in stand_ins)
    assert plain._threat(known) == (known, plain._seen_enemies(known)), "without the parameter the model reads what it sees"
    # The open hexes next to a counter: the plain record sees no threat there, and the
    # wary record sees a fire group and a chance of loss.
    reference = wary._reference_unit(known)
    near = [
        h
        for c in counters
        for h in s04.board.neighbors(c)
        if is_open_ground(s04.board, h) and h not in counters
    ]
    assert near
    assert all(not plain._enemy_groups(known, h) for h in near)
    assert any(wary._enemy_groups(known, h) and wary._loss(known, reference, h, True) > 0 for h in near)
    assert any(wary._seen_by_enemy(known, h) for h in near)


def _s04_axis_movement():
    """Scenario 4 at the first German Movement Phase, as the German player knows it."""
    s04 = build_engine("s04_armor_probe")
    agents = (make_agent("v7", s04, 7000001, 0), make_agent("v7", s04, 7000001, 1))
    state, _frame = _play_until(s04, agents, lambda st, fr: st.phase == PHASE_MOVEMENT and fr.player == 0, seed=7000001)
    return s04, player_state.for_player(state, 0)


def test_a_leader_with_the_stack_moves_forward_only_with_a_squad():
    """Rule 15.6: a leader gives its rating to the morale checks of the units in its hex.
    The 9-2 of scenario 4 ran ahead alone while its squads broke in the open without it
    (2026-10-14). With `leader_with_stack` a step into a hex with an own squad earns
    `leader_bonus`, and a step forward alone earns no progress."""
    from slcore.units import KIND_LEADER

    s04, known = _s04_axis_movement()
    on = ScriptedV7(s04, 0, parameters_of_name("v7[leader_with_stack=1]"))
    off = ScriptedV7(s04, 0, parameters_of_name("v7"))
    leader = next(u for u in known.player_units(0) if u.kind == KIND_LEADER and u.hex is not None)
    squad = next(u for u in known.player_units(0) if u.kind == "squad" and u.hex is not None and u.hex != leader.hex)
    empty = [h for h in s04.board.neighbors(leader.hex) if not known.infantry_in(h)]
    assert empty
    dst = empty[0]
    joined = known.with_unit(squad.with_(hex=dst))
    assert on._company(joined, leader, dst) == 1 and on._company(known, leader, dst) == 0

    def value(agent, state):
        agent._refresh_routes(state)
        agent._refresh_objectives(state)
        return agent._step_score(state, leader.id, leader.hex, dst, {})[1]

    lift_on = value(on, joined) - value(on, known)
    lift_off = value(off, joined) - value(off, known)
    assert lift_on - lift_off >= on.v7.leader_bonus
    assert on._stand_value(known.with_unit(squad.with_(hex=leader.hex)), leader.id, {}) - on._stand_value(known, leader.id, {}) >= on.v7.leader_bonus


def test_the_base_of_fire_makes_an_enemy_counter_a_target_of_the_tanks():
    """In scenario 4 the Russian infantry sets up below counters. Without `base_of_fire`
    the tanks saw no infantry, so no hex near the village was a firing position, and they
    drove and fired after the move. With it, a counter is an enemy infantry position."""
    from slagents.scripted.armor import ArmorParameters, ArmorPolicy

    s04, known = _s04_axis_movement()
    on = ArmorPolicy(s04, 0, ArmorParameters(base_of_fire=True))
    off = ArmorPolicy(s04, 0, ArmorParameters())
    counters = {c.hex for c in known.concealment if c.player == 1 and c.hex is not None}
    assert counters and not off._enemy_counters(known)
    assert set(on._enemy_counters(known)) == counters - {u.hex for u in off._enemies(known)}
    assert set(on._enemy_infantry(known)) >= set(on._enemy_counters(known))
    positions = on.firing_positions(known)
    near_a_counter = [h for h in positions if any(geometry.distance(h, c) <= on.params.fire_range for c in counters)]
    assert near_a_counter, "a hex in range of a counter is a firing position"
    assert all(min(geometry.distance(h, c) for c in counters) >= on.params.escorted_standoff for h in positions)
    # Without it, the tanks go to firing positions next to the hidden Russian infantry,
    # inside the reach of its anti-tank weapons.
    assert any(min(geometry.distance(h, c) for c in counters) < off.params.escorted_standoff for h in off.firing_positions(known))
    assert parameters_of_name("v7[tank_base_of_fire=1]").tank_base_of_fire


def test_the_covered_approach_hops_across_the_open_alone():
    """With `open_moves` false and the stand-ins of `counter_threat`, each open hex near
    the Russians of scenario 4 is seen, and v7 held each step into one: the attack stood
    still (2026-10-14). With `covered_approach` a single unit may hop into a seen open hex
    when it can go on to cover nearer the target in the same move, and a second unit does
    not join it there, because one shot breaks each unit of a hex."""
    from slcore.rules.r13_rout import is_cover

    s04, known = _s04_axis_movement()
    on = ScriptedV7(s04, 0, parameters_of_name("v7[counter_threat=1,covered_approach=1]"))
    strict = ScriptedV7(s04, 0, parameters_of_name("v7[counter_threat=1]"))
    for agent in (on, strict):
        agent._refresh_routes(known)
        agent._refresh_objectives(known)
    hops = []
    for unit in known.player_units(0):
        if unit.kind != "squad" or unit.hex is None:
            continue
        target = on.assignment.get(unit.id, on.open_objectives)
        for dst in s04.board.neighbors(unit.hex):
            if is_cover(s04.board, dst) or known.infantry_in(dst) or not on._seen_by_enemy(known, dst):
                continue
            if on._hop(known, unit, dst, target):
                hops.append((unit, dst))
    assert hops, "a squad of the start has a hop across a seen open hex"
    unit, dst = hops[0]
    lifted = on._step_score(known, unit.id, unit.hex, dst, {})[1] - strict._step_score(known, unit.id, unit.hex, dst, {})[1]
    assert lifted >= MASS_HOLD // 2, "the hop is not held"
    friend = next(u for u in known.player_units(0) if u.kind == "squad" and u.hex is not None and u.id != unit.id)
    joined = known.with_unit(friend.with_(hex=dst))
    alone = on._step_score(known, unit.id, unit.hex, dst, {})[1]
    on._refresh_routes(joined)
    stacked = on._step_score(joined, unit.id, unit.hex, dst, {})[1]
    assert alone - stacked >= MASS_HOLD // 2, "no second unit joins a seen open hex"
