"""Agent v7: the doctrine agent. It trades on the odds (RV-9 table A).

Each test reads one behavior of v7 on a real state of a real game, or on the odds of the
core, and names the principle it serves:
- v7 gives a legal command in each frame, and v7 against v7 replays to the same hash (TR-02).
- The fire plan concentrates (P2): with several shooters at one hex it forms a group whose
  expected loss of the enemy is above the best single shot, and it stops at the size where
  a member adds less than its share.
- The leader is a target (P12): the worth of a hex with a minus two leader is above the
  worth of the same squads without one.
- The defender catches the mover in the open (P21): the odds of a group at an open track
  hex are above the odds at the stone building the mover ended in.
- The exposure of a move is the worst hex of the track (rule 16.1), so a step out of the
  open into cover takes nothing back.
- The urgency of a hex of progress grows as the turns pass (P17) and when the enemy is
  down (P18).
- An advance into a hex of broken enemies is a sure kill (rule 20.9, P18).
- The parameters of FR-44 come from text, and a wrong name is an error.
"""

from __future__ import annotations

import pytest

from slcli.play import build_engine, make_agent, play_game
from slcore import geometry
from slcore.game import PHASE_DEFENSIVE_FIRE, PHASE_MOVEMENT, PHASE_PREP_FIRE, FireGroup
from slcore.los_eval import evaluate as evaluate_los
from slcore.rules import r08_fire
from slcore.rules.r11_terrain import is_open_ground
from slcore.units import KIND_LEADER
from slagents.scripted import odds
from slagents.scripted.v7 import SQUAD, Parameters, ScriptedV7, UnknownNation, parameters_from_text, profile_for

SCENARIO = "s01_guards_counterattack"


def _play_until(engine, agents, stop, seed: int = 7, limit: int = 6000):
    """Play until stop(state, frame) is true, and give that state and frame."""
    state = engine.new_game(seed)
    steps = 0
    while not state.game_over and steps < limit:
        frame = engine.legal_commands(state)
        if stop(state, frame):
            return state, frame
        chosen = agents[state.active].select(state, frame)
        state, _ = engine.apply(state, frame.by_id(chosen).command, frame)
        steps += 1
    raise AssertionError("the game did not reach the state the test wants")


def _by_action(frame):
    out = {}
    for lc in frame.commands:
        out.setdefault(lc.command.action, []).append(lc)
    return out


@pytest.fixture(scope="module")
def engine():
    return build_engine(SCENARIO)


def test_v7_plays_a_full_game_and_replays(engine):
    record = play_game(engine, 7, (make_agent("v7", engine, 7, 0), make_agent("v7", engine, 7, 1)))
    assert record.hashes, "the game produced a hash sequence"
    again = engine.replay(7, [c["payload"] for c in record.commands])
    assert again == record.hashes, "v7 against v7 is deterministic (TR-02)"
    assert record.result in ("russian", "german")


def test_v7_gives_a_legal_command_in_each_frame_of_a_game(engine):
    agents = (make_agent("v7", engine, 3, 0), make_agent("v6", engine, 3, 1))
    state = engine.new_game(3)
    steps = 0
    while not state.game_over and steps < 6000:
        frame = engine.legal_commands(state)
        chosen = frame.by_id(agents[state.active].select(state, frame))
        assert chosen is not None, f"v7 gave an ID that is not in the frame in {state.phase}"
        state, _ = engine.apply(state, chosen.command, frame)
        steps += 1
    assert state.game_over


def test_the_fire_plan_concentrates_and_stops_at_the_share(engine):
    """P2: the group at one target beats the best single shot, and each member earns its share."""
    agents = (make_agent("v7", engine, 7, 0), make_agent("v7", engine, 7, 1))

    def three_adds_at_one_target(state, frame):
        if state.phase != PHASE_PREP_FIRE or state.fire_group is not None:
            return False
        by_target = agents[state.active]._adds_by_target(_by_action(frame))
        return any(len(adds) >= 3 for adds in by_target.values())

    state, frame = _play_until(engine, agents, three_adds_at_one_target)
    agent = agents[state.active]
    by_target = agent._adds_by_target(_by_action(frame))
    target, adds = max(by_target.items(), key=lambda kv: len(kv[1]))
    plan = agent._plan_for(state, target, adds, state.phase)
    assert plan is not None
    singles = [odds.shot(engine, state, FireGroup(target, (agent._member_of(lc),), None), state.phase).value for lc in adds]
    assert plan.raw >= max(singles), "the plan is worth at least the best single shot"
    if len(plan.members) > 1:
        assert plan.raw > max(singles), "a group of two or more beats the best single shot"
    # Each member of the plan earns its share: the plan with one member fewer is worth less
    # by at least the share, or the plan is one member.
    share = SQUAD * agent.v7.overkill_share // 100
    if len(plan.members) > 1:
        smaller = FireGroup(target, tuple(agent._member_of(lc) for lc in plan.members[:-1]), None)
        assert plan.raw - odds.shot(engine, state, smaller, state.phase).value >= share


def test_a_hex_with_a_leader_is_worth_more_to_fire_at(engine):
    """P12: the odds value the leader above a squad, so the plan prefers the leader's hex."""
    state = engine.new_game(7)
    types = engine.types
    leader = min((u for u in state.units if u.kind == KIND_LEADER and u.player == 1), key=lambda u: types[u.type_key].leadership)
    squad = next(u for u in state.units if u.kind == "squad" and u.player == 1)
    assert odds.unit_value(types, leader) > odds.unit_value(types, squad)
    assert types[leader.type_key].leadership <= -1


def test_the_defender_catches_the_mover_in_the_open(engine):
    """P21: a group at the open track hex of a mover is worth more than at its stone building."""
    agents = (make_agent("v6", engine, 7, 0), make_agent("v7", engine, 7, 1))

    def open_track_return(state, frame):
        if state.phase != PHASE_DEFENSIVE_FIRE or state.fire_group is not None:
            return False
        for lc in _by_action(frame).get("track_return", []):
            end_hexes = {state.units[u].hex for u in lc.command.units}
            if is_open_ground(engine.board, lc.command.hex) and all(
                engine.board.hex(h).building is not None for h in end_hexes if h is not None
            ):
                return True
        return False

    state, frame = _play_until(engine, agents, open_track_return)
    agent = agents[1]
    by_action = _by_action(frame)
    adds = by_action.get("group_add", []) + by_action.get("group_add_weapon", [])
    shooters = sorted({agent._member_of(lc) for lc in adds}, key=lambda m: (m[0], -1 if m[1] is None else m[1]))
    if not shooters:
        pytest.skip("no shooter in this window")
    for lc in by_action["track_return"]:
        end_hexes = {state.units[u].hex for u in lc.command.units}
        if not is_open_ground(engine.board, lc.command.hex) or not all(engine.board.hex(h).building is not None for h in end_hexes):
            continue
        movers = [state.units[u] for u in lc.command.units]
        stay = max(agent._best_hypothetical(state, h, shooters) for h in end_hexes)
        moved = {u.id: u.with_(hex=lc.command.hex, returned_from=u.hex) for u in movers}
        there = agent._best_hypothetical(state.with_units(moved), lc.command.hex, shooters)
        if there == 0 and stay == 0:
            continue
        # Rule 16.5 gives minus two in the open, and rule 11.1 gives plus three in stone.
        assert there >= stay, (there, stay, geometry.hex_id(*lc.command.hex))
        return
    pytest.skip("the shooters had no line to the open track hex")


def test_the_exposure_of_a_move_is_the_worst_hex_of_the_track(engine):
    """Rule 16.1: a step out of the open into cover keeps the exposure of the open hex."""
    agents = (make_agent("v7", engine, 7, 0), make_agent("v6", engine, 7, 1))

    def mover_with_open_track(state, frame):
        if state.phase != PHASE_MOVEMENT or state.active != 0:
            return False
        return any(
            u.player == 0 and u.hex is not None and any(is_open_ground(engine.board, h) for h in u.track)
            for u in state.units
        )

    state, _frame = _play_until(engine, agents, mover_with_open_track)
    agent = agents[0]
    unit = next(u for u in state.units if u.player == 0 and u.hex is not None and any(is_open_ground(engine.board, h) for h in u.track))
    open_hex = next(h for h in unit.track if is_open_ground(engine.board, h))
    covered = [h for h in engine.board.neighbors(unit.hex) if engine.board.hex(h).building is not None]
    if not covered:
        pytest.skip("no covered neighbour")
    exposure = agent._exposure(state, unit, covered[0], True)
    assert exposure >= agent._loss(state, unit, open_hex, True)
    assert exposure >= agent._loss(state, unit, covered[0], True)


def test_urgency_grows_as_the_turns_pass_and_when_the_enemy_is_down(engine):
    agent = ScriptedV7(engine, 0)
    state = engine.new_game(7)
    # Put the units on the board, so a unit has a hex and a route.
    for _ in range(300):
        if state.phase != "setup":
            break
        frame = engine.legal_commands(state)
        chosen = next((c for c in frame.commands if c.command.action == "place"), None) or next(
            c for c in frame.commands if c.command.action == "end_setup"
        )
        state, _ = engine.apply(state, chosen.command, frame)
    agent.select(state, engine.legal_commands(state))
    unit = next(u for u in state.units if u.player == 0 and u.kind == "squad" and u.hex is not None)
    early = agent._urgency(state, unit.id, unit.hex)
    late = agent._urgency(state.with_(turn=state.turn + 3), unit.id, unit.hex)
    assert late > early
    assert late <= agent.v7.urgency_cap
    # With no unbroken enemy squad left the press is at its top (P18).
    down = state.with_units({u.id: u.with_(broken=True) for u in state.units if u.player == 1 and u.kind == "squad"})
    assert agent._exploit(down) == 2
    assert agent._exploit(state) == 0 or agent._exploit(state) == 1


def test_an_advance_into_broken_enemies_is_a_sure_kill(engine):
    """Rule 20.9: a broken unit in a melee hex is eliminated."""
    agent = ScriptedV7(engine, 0)
    state = engine.new_game(7)
    ours = tuple(u.id for u in state.units if u.player == 0 and u.kind == "squad")[:2]
    theirs = [u.with_(broken=True) for u in state.units if u.player == 1 and u.kind == "squad"][:2]
    ours_kill, theirs_kill = agent._assault_odds(state, ours, theirs)
    assert (ours_kill, theirs_kill) == (odds.WAYS, 0)
    fresh = [u for u in state.units if u.player == 1 and u.kind == "squad"][:2]
    ours_kill, theirs_kill = agent._assault_odds(state, ours, fresh)
    assert 0 < ours_kill < odds.WAYS and 0 < theirs_kill < odds.WAYS


def test_parameters_from_text_and_the_profiles():
    params = parameters_from_text("loss_scale=9, fire_floor=3")
    assert params.loss_scale == 9 and params.fire_floor == 3
    with pytest.raises(ValueError):
        parameters_from_text("no_such_parameter=1")
    with pytest.raises(ValueError):
        parameters_from_text("loss_scale=nine")
    with pytest.raises(ValueError):
        parameters_from_text("loss_scale")
    assert profile_for("german").close_combat_margin == 0
    assert profile_for("german", defending=True).close_combat_margin == -3
    assert profile_for("soviet").schedule_margin == 3
    assert profile_for("american").group_size == 7
    with pytest.raises(UnknownNation):
        profile_for("british")


def test_the_factory_builds_v7_with_parameters(engine):
    agent = make_agent("v7[loss_scale=9]", engine, 1, 0)
    assert isinstance(agent, ScriptedV7) and agent.v7.loss_scale == 9
    assert isinstance(make_agent("v7:soviet", engine, 1, 0), ScriptedV7)
    with pytest.raises(ValueError):
        make_agent("v7[nope=1]", engine, 1, 0)


def test_a_broken_unit_routs_to_the_cover_with_the_least_loss(engine):
    """Rule 13.43 gives the nearest cover hexes. The agent takes the one the enemy fire
    hurts least, and a leader breaks a tie."""
    agents = (make_agent("v7", engine, 7, 0), make_agent("v7", engine, 7, 1))

    def two_rout_options(state, frame):
        if state.phase != "rout":
            return False
        by_unit: dict[int, list] = {}
        for lc in frame.commands:
            if lc.command.action == "rout":
                by_unit.setdefault(lc.command.units[0], []).append(lc)
        return any(len(v) >= 2 for v in by_unit.values())

    state, frame = _play_until(engine, agents, two_rout_options)
    agent = agents[state.active]
    chosen = frame.by_id(agent.select(state, frame))
    assert chosen is not None and chosen.command.action in ("rout", "stay")
    unit = state.units[chosen.command.units[0]]
    if chosen.command.action == "rout":
        taken = agent._loss(state, unit, chosen.command.hex, False)
        for lc in frame.commands:
            if lc.command.action == "rout" and lc.command.units == chosen.command.units:
                assert agent._loss(state, unit, lc.command.hex, False) >= taken


def test_a_forced_run_needs_to_arrive(engine):
    """A unit that has to run is forced only when the fastest route gets it to its target
    this turn. Otherwise the step is judged by its value alone."""
    agent = ScriptedV7(engine, 0)
    state = engine.new_game(7)
    for _ in range(300):
        if state.phase != "setup":
            break
        frame = engine.legal_commands(state)
        chosen = next((c for c in frame.commands if c.command.action == "place"), None) or next(
            c for c in frame.commands if c.command.action == "end_setup"
        )
        state, _ = engine.apply(state, chosen.command, frame)
    late = state.with_(turn=engine.scenario.turns)
    agent.select(late, engine.legal_commands(late))
    unit = next(u for u in late.units if u.player == 0 and u.kind == "squad" and u.hex is not None)
    assert agent._press_level(late, unit.id, unit.hex) == 2, "on the last turn the unit has to run"
    target = agent.assignment.get(unit.id, agent.open_objectives)
    far = agent._route_time(late, target, unit.hex, safe=False) > engine.types[unit.type_key].mf_halves + 2
    cache: dict = {}
    forced = [
        agent._step_score(late, unit.id, unit.hex, near, cache)[0]
        for near in engine.board.neighbors(unit.hex)
        if near in engine.board
    ]
    if far:
        assert not any(forced), "a run that cannot arrive is not forced"
    loose = ScriptedV7(engine, 0, parameters_from_text("dash_arrives=0"))
    loose.select(late, engine.legal_commands(late))
    assert loose._press_level(late, unit.id, unit.hex) == 2


def test_the_set_up_by_the_odds_gives_a_legal_command(engine):
    agents = (
        ScriptedV7(engine, 0, parameters_from_text("setup_by_odds=1")),
        ScriptedV7(engine, 1, parameters_from_text("setup_by_odds=1")),
    )
    state = engine.new_game(7)
    steps = 0
    while state.phase == "setup" and steps < 400:
        frame = engine.legal_commands(state)
        chosen = frame.by_id(agents[state.active].select(state, frame))
        assert chosen is not None
        state, _ = engine.apply(state, chosen.command, frame)
        steps += 1
    assert state.phase != "setup"
    placed = [u for u in state.units if u.hex is not None and u.kind == "squad"]
    assert len(placed) >= 30


def test_the_record_of_a_nation_goes_by_the_role_of_its_side():
    """A record of one role does not go to the other role. The German record of the
    evolution is a defence, and as the German attacker of scenario 2 it wins 6 of 100
    where the attack record wins 23. So `side_defends` picks the record: a side with a
    positional victory condition of its own attacks, and the other side defends."""
    from slagents.scripted.v7 import DEFENCE_PROFILES, NATION_PROFILES, side_defends

    first = build_engine("s01_guards_counterattack")
    second = build_engine("s02_tractor_works")
    # Scenario 1: the Russian has the building swing, so the German defends.
    assert not side_defends(first, 0) and side_defends(first, 1)
    # Scenario 2: each side has a positional condition, so neither one defends.
    assert not side_defends(second, 0) and not side_defends(second, 1)
    defence = make_agent("v7:german", first, 1, 1)
    attack = make_agent("v7:german", second, 1, 0)
    assert defence.v7 == DEFENCE_PROFILES["german"]
    assert attack.v7 == NATION_PROFILES["german"]
    assert defence.v7.fire_floor > attack.v7.fire_floor
    # A nation with no record of the defence keeps its record of the attack.
    soviet = make_agent("v7:soviet", first, 1, 1)
    assert soviet.v7 == NATION_PROFILES["soviet"]
    # The values of a study go on top of the record of the role.
    study = make_agent("v7:german[smoke_horizon=1]", first, 1, 1)
    assert study.v7.smoke_horizon == 1 and study.v7.fire_floor == DEFENCE_PROFILES["german"].fire_floor


def test_the_german_profile_is_the_defence_the_evolution_found():
    """The German profile of 2026-09-20 comes from candidate 167 of
    `runs/20260920T201936Z-evolve-v7`, and it held 95 of 100 against the v7 Russian on
    seeds no generation played, where the profile before it held 79. Its numbers are the
    defence: fire only when the shot pays, no value for the fire a hex gives, a threat
    counted in large units, and a high price on a loss."""
    german = profile_for("german", defending=True)
    default = Parameters()
    assert german.fire_floor > default.fire_floor
    assert german.fire_weight == 0
    assert german.threat_scale > default.threat_scale
    assert german.threat_aversion == 0
    assert german.loss_scale > default.loss_scale
    assert german.group_size < default.group_size
    assert german.spare_targets < default.spare_targets
    # The profile is a record of the evolution artifact, so the text is the candidate.
    from slagents.scripted.evolve import genome_of, text_of

    text = text_of(genome_of(german))
    assert "fire_floor=4" in text and "fire_weight=0" in text and "loss_scale=30" in text


# ----------------------------------------------------------------- rule 24, the smoke


SMOKE_SCENARIO = "s02_tractor_works"


def a_smoke_window(engine, seed: int = 3, agent: str = "v7", must_place: bool = False):
    """A smoke window of a game, with the agent of the acting side and its selection.

    Scenario 2 gives the German six counters and six assault engineer squads (rule 24.1),
    and the window opens at the start of its Prep Fire Phase (rule 24.3). With
    `must_place` the search goes on to the first window where the agent puts a counter
    down, because a window early in the game can hold no hex worth the floor.
    """
    state = engine.new_game(seed)
    agents = {p: make_agent(agent, engine, seed, p) for p in (0, 1)}
    steps = 0
    while not state.game_over and steps < 4000:
        frame = engine.legal_commands(state)
        offered = frame.sub_step == "smoke_window" and any(lc.command.action == "place_smoke" for lc in frame.commands)
        chosen = frame.by_id(agents[frame.player].select(state, frame))
        if offered and (not must_place or chosen.command.action == "place_smoke"):
            return state, frame, agents[frame.player], chosen
        state, _ = engine.apply(state, chosen.command, frame)
        steps += 1
    raise AssertionError("no smoke window with a placement")


def test_the_odds_read_the_smoke_die_of_rule_24_6():
    """A group whose line of sight meets smoke takes the die of rule 24.6, so its odds
    fall. `group_meets_smoke` asks the question the core asks, and `odds.loss` uses it."""
    from slagents.scripted import odds
    from slcore.game import Smoke

    engine = build_engine(SMOKE_SCENARIO)
    state = engine.new_game(3)
    scripted = {p: make_agent("v1", engine, 3, p) for p in (0, 1)}
    while state.phase in ("setup", "rally"):
        frame = engine.legal_commands(state)
        state, _ = engine.apply(state, frame.by_id(scripted[frame.player].select(state, frame)).command, frame)
    shooter = next(
        u for u in state.player_units(0)
        if u.hex is not None and u.kind == "squad" and not u.broken
        and any(
            r08_fire.member_firepower(state, engine.types, u, None, t.hex, False) is not None
            and evaluate_los(engine.board, engine.los, u.hex, t.hex).clear
            for t in state.player_units(1) if t.hex is not None and t.is_infantry
        )
    )
    target = next(
        t.hex for t in state.player_units(1)
        if t.hex is not None and t.is_infantry
        and r08_fire.member_firepower(state, engine.types, shooter, None, t.hex, False) is not None
        and evaluate_los(engine.board, engine.los, shooter.hex, t.hex).clear
    )
    group = FireGroup(target, ((shooter.id, None),), None)
    assert not odds.group_meets_smoke(engine, state, group)
    clear = odds.shot(engine, state, group, PHASE_PREP_FIRE)
    smoked = state.with_(smoke=state.smoke + (Smoke(target, 1),))
    assert odds.group_meets_smoke(engine, smoked, group)
    through = odds.shot(engine, smoked, group, PHASE_PREP_FIRE, smoke=True)
    assert through.drm > clear.drm
    assert through.effect <= clear.effect
    # The loss of a hex falls behind a screen, which is what the agent trades on.
    defender = next(u for u in state.player_units(1) if u.hex == target and u.is_infantry)
    groups = odds.enemy_groups(engine, state, target, state.player_units(0))
    assert groups
    open_loss = odds.loss(engine, state, defender, target, False, groups)
    screened = odds.loss(engine, smoked, defender, target, False, groups)
    assert screened < open_loss


def test_v7_places_the_smoke_where_it_takes_the_loss_off_its_force():
    """Rule 24.3 with P15: the counter goes on the hex with the best fall of the expected
    loss of our force, less the fire it costs us. The command is legal, and the hex is one
    the host offered."""
    engine = build_engine(SMOKE_SCENARIO)
    state, frame, _agent, chosen = a_smoke_window(engine, must_place=True)
    assert chosen is not None and chosen.command.action == "place_smoke"
    offered = {lc.command.hex for lc in frame.commands if lc.command.action == "place_smoke"}
    assert chosen.command.hex in offered
    # The state after it holds one counter more, of our side (rule 24.3).
    after, _ = engine.apply(state, chosen.command, frame)
    assert len(after.smoke) == len(state.smoke) + 1
    assert after.smoke[-1].player == frame.player
    assert after.smoke_left[frame.player] == state.smoke_left[frame.player] - 1


def test_a_high_floor_places_no_smoke():
    """A counter that saves less than `smoke_floor` of a squad is not placed. A screen
    over a force of twenty five units saves a few squads of expected loss, so a floor of
    fifty squads is above each hex and the agent ends the window."""
    engine = build_engine(SMOKE_SCENARIO)
    state, frame, _agent, chosen = a_smoke_window(engine, must_place=True)
    assert chosen.command.action == "place_smoke"
    quiet = make_agent("v7[smoke_floor=5000]", engine, 3, frame.player)
    chosen = frame.by_id(quiet.select(state, frame))
    assert chosen is not None and chosen.command.action == "end_phase"


def test_the_smoke_of_v7_is_measured_in_a_game():
    """One game of scenario 2 with v7 on the two sides: the German places counters, and
    it places no more than the scenario gives it (rule 24.1)."""
    engine = build_engine(SMOKE_SCENARIO)
    seed = 3
    agents = {p: make_agent("v7", engine, seed, p) for p in (0, 1)}
    state = engine.new_game(seed)
    allowance = state.smoke_left
    placed = 0
    steps = 0
    while not state.game_over and steps < 4000:
        frame = engine.legal_commands(state)
        chosen = frame.by_id(agents[frame.player].select(state, frame))
        if chosen.command.action == "place_smoke":
            placed += 1
        state, _ = engine.apply(state, chosen.command, frame)
        steps += 1
    assert state.game_over
    assert placed > 0
    assert placed <= sum(allowance)
