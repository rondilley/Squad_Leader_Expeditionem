"""Rules 5, 6, 21, and the state machine on the movement drill scenario."""

import pytest

from slcore import geometry
from slcore.commands import Command
from slcore.engine import Engine, IllegalCommand
from slcore.game import PHASE_ADVANCE, PHASE_MOVEMENT, PHASE_PREP_FIRE, PHASE_RALLY, PHASE_SETUP
from slcore.rules import r05_movement, r06_stacking
from slcli.play import build_engine


def ref(text):
    return geometry.parse_hex_id(text)


def ids(cmds):
    return {c.id for c in cmds}


@pytest.fixture(scope="module")
def engine() -> Engine:
    return build_engine("s00_movement_drill")


def apply_all(engine, state, commands):
    events = []
    for c in commands:
        state, ev = engine.apply(state, c)
        events.extend(ev)
    return state, events


def do_setup(engine, state, german=None, russian=None):
    """Place the German force, then the Russian force, and give the state at the first Rally window."""
    german = german or {"leader": "A1", "squads": ["A1", "A2", "A3"], "weapon": 0}
    russian = russian or {"leader": "I1", "squads": ["I1", "I2", "I3", "J1"], "weapon": 0}
    ger = [u for u in state.units if u.player == 1]
    rus = [u for u in state.units if u.player == 0]
    assert state.phase == PHASE_SETUP and state.active == 1
    cmds = []
    leader = [u for u in ger if u.kind == "leader"][0]
    squads = [u for u in ger if u.kind == "squad"]
    weapon = [u for u in ger if u.kind == "sw"][0]
    cmds.append(Command("place", (leader.id,), ref(german["leader"])))
    for u, h in zip(squads, german["squads"]):
        cmds.append(Command("place", (u.id,), ref(h)))
    cmds.append(Command("place_weapon", (squads[german["weapon"]].id,), weapon=weapon.id))
    cmds.append(Command("end_setup"))
    state, _ = apply_all(engine, state, cmds)
    assert state.phase == PHASE_SETUP and state.active == 0
    leader = [u for u in rus if u.kind == "leader"][0]
    squads = [u for u in rus if u.kind == "squad"]
    weapon = [u for u in rus if u.kind == "sw"][0]
    cmds = [Command("place", (leader.id,), ref(russian["leader"]))]
    for u, h in zip(squads, russian["squads"]):
        cmds.append(Command("place", (u.id,), ref(h)))
    cmds.append(Command("place_weapon", (squads[russian["weapon"]].id,), weapon=weapon.id))
    cmds.append(Command("end_setup"))
    state, events = apply_all(engine, state, cmds)
    assert state.phase == PHASE_RALLY and state.phasing == 0 and state.active == 0
    return state


def to_movement(engine, state):
    state, _ = engine.apply(state, Command("end_phase"))
    assert state.phase == PHASE_RALLY and state.active == 1
    state, _ = engine.apply(state, Command("end_phase"))
    assert state.phase == PHASE_PREP_FIRE and state.active == 0
    state, _ = engine.apply(state, Command("end_phase"))
    assert state.phase == PHASE_MOVEMENT and state.active == 0
    return state


def test_new_game_units_and_setup_list(engine):
    state = engine.new_game(1)
    assert len(state.units) == 11
    assert state.phase == PHASE_SETUP
    assert state.active == 1, "the German side sets up first"
    frame = engine.legal_commands(state)
    actions = {lc.command.action for lc in frame.commands}
    assert actions == {"place"}, "no carrier is on the board for place_weapon, and end_setup waits for all units"
    place_units = {lc.command.units[0] for lc in frame.commands}
    assert len(place_units) == 3, "PR-06: one leader, the lowest squad, and the weapon on the ground"
    hexes = {lc.command.hex for lc in frame.commands}
    assert hexes == {ref("A1"), ref("A2"), ref("A3"), ref("B1"), ref("B2")}


def test_setup_rejects_a_hex_outside_the_area(engine):
    state = engine.new_game(1)
    leader = [u for u in state.units if u.player == 1 and u.kind == "leader"][0]
    with pytest.raises(IllegalCommand):
        engine.apply(state, Command("place", (leader.id,), ref("E5")))


def test_setup_then_rally_windows_and_phases(engine):
    state = do_setup(engine, engine.new_game(1))
    assert state.turn == 1
    state = to_movement(engine, state)
    frame = engine.legal_commands(state)
    assert frame.sub_step == "move_window"
    assert Command("end_phase").id in frame.ids()


def test_movement_costs_open_woods_building_wall_and_road(engine):
    ctx = engine.move_ctx
    assert r05_movement.entry_cost_halves(ctx, ref("A1"), ref("A2"))[0] == 2
    assert r05_movement.entry_cost_halves(ctx, ref("E1"), ref("E2"))[0] == 4, "woods"
    assert r05_movement.entry_cost_halves(ctx, ref("G7"), ref("G8"))[0] == 4, "wooden building"
    cost, rules = r05_movement.entry_cost_halves(ctx, ref("F5"), ref("F6"))
    assert cost == 4 and "5.51" in rules, "open ground across a wall costs 1 + 1 MF"
    cost, rules = r05_movement.entry_cost_halves(ctx, ref("A5"), ref("A6"))
    assert cost == 1 and "5.52" in rules, "road hex from a road hex costs one half"
    assert r05_movement.entry_cost_halves(ctx, ref("A4"), ref("A5"))[0] == 2, "road hex from a non-road hex costs 1 MF"
    assert r05_movement.entry_cost_halves(ctx, ref("A1"), ref("A3"))[0] is None


def test_squad_moves_four_hexes_then_stops(engine):
    state = do_setup(engine, engine.new_game(1), russian={"leader": "I1", "squads": ["I2", "I3", "I3", "J1"], "weapon": 1})
    state = to_movement(engine, state)
    squad = [u for u in state.units if u.player == 0 and u.kind == "squad" and u.hex == ref("I2")][0]
    path = ["H2", "G2", "F2", "F1"]
    for h in path:
        cmd = Command("move", (squad.id,), ref(h))
        frame = engine.legal_commands(state)
        assert cmd.id in frame.ids(), h
        state, events = engine.apply(state, cmd)
        assert events[0].rule_id == "5.5"
    u = state.units[squad.id]
    assert u.hex == ref("F1") and u.mf_used == 8 and u.moved and u.track == tuple(ref(h) for h in path)
    frame = engine.legal_commands(state)
    assert not any(lc.command.action == "move" and lc.command.units == (squad.id,) for lc in frame.commands), "4 MF spent"


def test_leader_bonus_and_stack_lock(engine):
    state = do_setup(engine, engine.new_game(1), russian={"leader": "I2", "squads": ["I2", "I3", "I3", "J1"], "weapon": 1})
    state = to_movement(engine, state)
    leader = [u for u in state.units if u.player == 0 and u.kind == "leader"][0]
    squad = [u for u in state.units if u.player == 0 and u.kind == "squad" and u.hex == ref("I2")][0]
    frame = engine.legal_commands(state)
    stack = Command("stack_move", (leader.id, squad.id), ref("H2"))
    assert stack.id in frame.ids()
    state, events = engine.apply(state, stack)
    assert events[0].rule_id == "5.44"
    frame = engine.legal_commands(state)
    solo_for_squad = [lc for lc in frame.commands if lc.command.action == "move" and lc.command.units == (squad.id,)]
    assert not solo_for_squad, "PR-05: a squad in a stack moves only with its leader"
    solo_for_leader = [lc for lc in frame.commands if lc.command.action == "move" and lc.command.units == (leader.id,)]
    assert not solo_for_leader
    for h in ["G2", "F2", "E2", "D1"]:
        cmd = Command("stack_move", (leader.id, squad.id), ref(h))
        assert cmd.id in engine.legal_commands(state).ids(), h
        state, _ = engine.apply(state, cmd)
    assert state.units[squad.id].mf_used == 12, "4 MF plus the 2 MF bonus: four open hexes and one woods hex"
    assert state.units[leader.id].mf_used == 12
    assert not any(lc.command.action == "stack_move" for lc in engine.legal_commands(state).commands)


def test_portage_penalty_pickup_and_drop(engine):
    state = do_setup(engine, engine.new_game(1), russian={"leader": "I1", "squads": ["I2", "I3", "I3", "J1"], "weapon": 0})
    state = to_movement(engine, state)
    squad = [u for u in state.units if u.player == 0 and u.kind == "squad" and u.hex == ref("I2")][0]
    mmg = [u for u in state.units if u.player == 0 and u.kind == "sw"][0]
    assert mmg.carrier == squad.id
    assert r05_movement.allowance_halves(engine.move_ctx, state, state.units[squad.id], False) == 6, "MMG is 4 points, 1 over the free 3, so 3 MF"
    frame = engine.legal_commands(state)
    drop = Command("drop", (squad.id,), weapon=mmg.id)
    assert drop.id in frame.ids()
    state, _ = engine.apply(state, drop)
    assert state.units[mmg.id].carrier is None and state.units[mmg.id].hex == ref("I2")
    frame = engine.legal_commands(state)
    pickup = Command("pickup", (squad.id,), weapon=mmg.id)
    assert pickup.id in frame.ids()
    leader = [u for u in state.units if u.player == 0 and u.kind == "leader"][0]
    state, _ = engine.apply(state, Command("move", (leader.id,), ref("I2")))
    frame = engine.legal_commands(state)
    assert Command("pickup", (leader.id,), weapon=mmg.id).id not in frame.ids(), "a leader alone cannot carry a MMG"
    state, _ = engine.apply(state, pickup)
    assert state.units[mmg.id].carrier == squad.id
    for h in ["H2", "G2", "F2"]:
        state, _ = engine.apply(state, Command("move", (squad.id,), ref(h)))
    assert state.units[mmg.id].hex == ref("F2"), "the weapon moves with its carrier"
    assert not any(lc.command.action == "move" and lc.command.units == (squad.id,) for lc in engine.legal_commands(state).commands), "3 MF with the MMG"


def test_stacking_limit_blocks_end_phase_and_placement(engine):
    state = engine.new_game(1)
    ger = [u for u in state.units if u.player == 1]
    leader = [u for u in ger if u.kind == "leader"][0]
    squads = [u for u in ger if u.kind == "squad"]
    cmds = [Command("place", (leader.id,), ref("A1"))] + [Command("place", (u.id,), ref("A1")) for u in squads]
    state, _ = apply_all(engine, state, cmds)
    assert r06_stacking.hex_load(state, engine.types, ref("A1"), 1) == (4, 3, 0)
    weapon = [u for u in ger if u.kind == "sw"][0]
    frame = engine.legal_commands(state)
    assert Command("place", (weapon.id,), ref("A1")).id in frame.ids(), "a weapon on the ground counts portage only"
    state2 = do_setup(engine, engine.new_game(1), russian={"leader": "I1", "squads": ["I2", "I2", "I2", "I3"], "weapon": 3})
    state2 = to_movement(engine, state2)
    third = [u for u in state2.units if u.player == 0 and u.kind == "squad" and u.hex == ref("I3")][0]
    frame = engine.legal_commands(state2)
    move_in = Command("move", (third.id,), ref("I2"))
    assert move_in.id in frame.ids(), "PR-04: a unit may pass through an over-limit hex with factors in reserve"
    state2, _ = engine.apply(state2, move_in)
    frame = engine.legal_commands(state2)
    assert r06_stacking.hex_load(state2, engine.types, ref("I2"), 0) == (4, 4, 4)
    assert Command("end_phase").id not in frame.ids(), "rule 6.3: no end of phase while a hex is over the limit"
    assert any(lc.command.action == "move" and lc.command.units == (third.id,) for lc in frame.commands)


def test_advance_phase_one_hex_and_turn_change(engine):
    state = do_setup(engine, engine.new_game(1))
    state = to_movement(engine, state)
    for _ in range(3):
        state, _ = engine.apply(state, Command("end_phase"))
    assert state.phase == "rout" and state.active == 0
    state, _ = engine.apply(state, Command("end_phase"))
    assert state.phase == "rout" and state.active == 1
    state, _ = engine.apply(state, Command("end_phase"))
    assert state.phase == PHASE_ADVANCE and state.active == 0
    squad = [u for u in state.units if u.player == 0 and u.kind == "squad" and u.hex == ref("I2")][0]
    state, events = engine.apply(state, Command("advance", (squad.id,), ref("H2")))
    assert events[0].rule_id == "4.7"
    assert not any(lc.command.action == "advance" and lc.command.units == (squad.id,) for lc in engine.legal_commands(state).commands)
    state, _ = engine.apply(state, Command("end_phase"))
    assert state.phase == "close_combat" and state.active == 0
    state, _ = engine.apply(state, Command("end_phase"))
    assert state.active == 1
    state, events = engine.apply(state, Command("end_phase"))
    assert state.phase == PHASE_RALLY and state.phasing == 1 and state.turn == 1
    assert any(e.rule_id == "4.9" for e in events)
    assert not state.units[squad.id].moved and state.units[squad.id].move_mode == ""


def test_game_ends_after_the_last_turn(engine):
    state = do_setup(engine, engine.new_game(2))
    count = 0
    while not state.game_over:
        state, _ = engine.apply(state, Command("end_phase"))
        count += 1
    assert state.turn == 4 and state.result == "no_result"
    assert count == 3 * 2 * 11, "11 windows for each player turn, 2 player turns, 3 turns"
    assert engine.legal_commands(state).commands == ()
