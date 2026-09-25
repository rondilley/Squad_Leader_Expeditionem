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
