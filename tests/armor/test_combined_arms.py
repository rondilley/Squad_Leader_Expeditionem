"""The combined-arms pass of the armor policy (2026-10-11, RV-9 P4, P6, P7, P13).

The owner watched v7 and v6 on scenario 4: "The tanks do not appear to be working in
coordination or within written doctrines for tank warfare, small unit tactics, mixed unit
tactics." Each tank chose its hex and its target alone. A measure of 40 games found the
whole section in motion in 22 of 131 Movement Phases in contact, and the Allied tanks of v6
within three hexes of enemy infantry with no escort in 31 percent of the samples. These
tests hold the doctrine that the pass put in.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from slagents.base import decide
from slagents.scripted import evolve
from slagents.scripted.armor import ArmorParameters, ArmorPolicy
from slagents.scripted.v7 import Parameters, ScriptedV7, parameters_from_text
from slcli.play import build_engine, make_agent
from slcore import geometry
from slcore.player_state import for_player

SCENARIO = "s04_armor_probe"


def _states(first: str, second: str, seed: int):
    """Each state and frame of one game, in order, with the engine."""
    engine = build_engine(SCENARIO)
    state = engine.new_game(seed)
    agents = {0: make_agent(first, engine, seed, 0), 1: make_agent(second, engine, seed, 1)}
    while not state.game_over:
        frame = engine.legal_commands(state)
        yield engine, state, frame
        chosen = frame.by_id(decide(agents[state.active], state, frame))
        state, _ = engine.apply(state, chosen.command, frame)


def _by_action(frame) -> dict:
    out: dict = {}
    for lc in frame.commands:
        out.setdefault(lc.command.action, []).append(lc)
    return out


def _mid_game(seed: int = 1, turn: int = 2, player: int = 0):
    """The first Movement Phase frame of a player in a turn, with the player's view."""
    for engine, state, frame in _states("v7", "v6", seed):
        if state.turn == turn and state.active == player and frame.phase == "movement":
            return engine, for_player(state, player), frame
    raise AssertionError("the game ended before the turn")


@pytest.mark.parametrize("first,second", [("v7", "v6"), ("v6", "v7")])
def test_the_section_never_moves_all_its_tanks_in_contact(first, second):
    """P7: in contact, one tank of the section always stands and watches the others bound.
    A tank that fired in the Prep Fire Phase stands, so it watches too. The old policy moved
    each tank in 22 of 131 such phases."""
    in_contact = 0
    for seed in (1, 2, 3):
        start = None
        for engine, state, frame in _states(first, second, seed):
            if frame.phase == "movement" and start is None:
                player = state.active
                view = for_player(state, player)
                enemies = [u.hex for u in view.player_units(1 - player) if u.hex is not None and not u.hidden and not u.eliminated and not u.wreck]
                mobile = [
                    u for u in state.player_units(player)
                    if u.is_vehicle and u.hex is not None and not u.wreck and not u.immobilized and not u.eliminated
                ]
                contact = all(any(geometry.distance(u.hex, e) <= ArmorParameters().contact_range for e in enemies) for u in mobile)
                # P13 comes first: a tank in the anti-tank range of seen enemy infantry with no
                # escort pulls back in any turn, so a phase that starts with one is no test.
                policy = ArmorPolicy(engine, player)
                danger = any(u.hex in policy._danger_map(view) for u in mobile)
                start = ({u.id: u.hex for u in mobile}, contact and not danger)
            if frame.phase != "movement" and start is not None:
                hexes, contact = start
                if len(hexes) >= 2 and contact:
                    in_contact += 1
                    moved = [i for i in hexes if state.units[i].hex != hexes[i]]
                    assert len(moved) < len(hexes), f"each tank moved in turn {state.turn} (seed {seed})"
                start = None
    assert in_contact >= 10


def test_a_firing_position_pays_for_its_distance_from_the_infantry():
    """P13: a firing position past the leash costs `leash_cost` halves for each hex."""
    engine, view, _ = _mid_game()
    params = ArmorParameters(gun_exposure=0, flank_bonus=0)
    policy = ArmorPolicy(engine, 0, params)
    friends = policy._friends(view)
    costs = policy.goal_costs(view)
    assert friends and costs
    for here, cost in costs.items():
        near = min(geometry.distance(here, f) for f in friends)
        assert cost == params.leash_cost * max(0, near - params.leash)
    assert any(cost > 0 for cost in costs.values())


def test_a_screened_tank_may_stand_nearer_to_the_enemy():
    """P13: a hex that an own squad or crew screens is a firing position at
    `escorted_standoff` hexes from enemy infantry; with no escort it needs `standoff`."""
    found = False
    for seed in (1, 2, 3):
        for engine, state, frame in _states("v7", "v6", seed):
            if frame.phase != "movement":
                continue
            view = for_player(state, state.active)
            screened = ArmorPolicy(engine, state.active, ArmorParameters())
            alone = ArmorPolicy(engine, state.active, ArmorParameters(escort=False))
            near, far = screened.firing_positions(view), alone.firing_positions(view)
            infantry = screened._enemy_infantry(view)
            friends = screened._friends(view)
            for here in near - far:
                found = True
                assert screened._escorted(friends, here)
                distance = min(geometry.distance(here, h) for h in infantry)
                assert ArmorParameters().escorted_standoff <= distance < ArmorParameters().standoff
            if found:
                return
    assert found, "no game had a screened position"


def test_the_section_fires_again_at_its_target():
    """P6: a hex that a tank of ours fired at in this phase is worth `focus_bonus` more to
    the next tank, while it holds an unbroken enemy."""
    for seed in (1, 2, 3):
        for engine, state, frame in _states("v7", "v6", seed):
            if frame.phase not in ("prep_fire", "defensive_fire", "advancing_fire"):
                continue
            shots = [lc for lc in frame.commands if lc.command.action in ("afv_fire", "afv_mg")]
            if not shots:
                continue
            view = for_player(state, state.active)
            policy = ArmorPolicy(engine, state.active)
            for lc in shots:
                before = policy._shot_score(view, lc.command.action, lc)
                if before is None:
                    continue
                policy._record_shot(view, lc)
                after = policy._shot_score(view, lc.command.action, lc)
                assert after[0] == before[0] + policy.params.focus_bonus
                return
    raise AssertionError("no game had a tank shot at infantry")


def test_a_squad_escorts_a_tank_that_is_in_contact():
    """P13, the infantry half: a squad of the attacker gains `escort_bonus` for the hex of a
    tank of its own that is near seen enemy infantry and has no escort. A second squad gains
    nothing there, so the force does not gather around the tanks."""
    for seed in (1, 2, 3, 4):
        for engine, state, frame in _states("v7", "v6", seed):
            if frame.phase != "movement" or state.active != 0:
                continue
            view = for_player(state, 0)
            agent = ScriptedV7(engine, 0)
            squads = [u for u in view.player_units(0) if u.kind == "squad" and u.hex is not None and not u.broken]
            for tank in view.player_units(0):
                if not tank.is_vehicle or tank.hex is None or tank.wreck:
                    continue
                values = {u.id: agent._escort_value(view, u, tank.hex) for u in squads}
                if not any(values.values()):
                    continue
                assert set(values.values()) <= {0, agent.v6.escort_bonus}
                off = ScriptedV7(engine, 0, replace(Parameters(), escort_bonus=0))
                assert all(off._escort_value(view, u, tank.hex) == 0 for u in squads)
                return
    raise AssertionError("no game had a tank of the attacker in contact with no escort")


def test_the_tank_parameters_reach_the_armor_policy():
    """FR-44: the tank parameters are v7 parameters, so a command line and the evolution
    reach them."""
    params = parameters_from_text("tank_leash=5,tank_bound=false,tank_focus_bonus=7")
    engine = build_engine(SCENARIO)
    agent = ScriptedV7(engine, 0, params)
    assert (agent.armor.params.leash, agent.armor.params.bound, agent.armor.params.focus_bonus) == (5, False, 7)
    names = set(vars(Parameters()))
    for name in list(evolve.SPACE) + list(evolve.FLAGS):
        assert name in names, name


@pytest.mark.parametrize("first,second", [("v7", "v6"), ("v6", "v7")])
def test_no_tank_waits_in_anti_tank_range_without_escort(first, second):
    """P13: a tank stands within three hexes of enemy infantry with no squad or crew of its
    own next to it in at most one sample in ten. The old policy did so in 31 percent."""
    samples: dict[int, int] = {0: 0, 1: 0}
    alone: dict[int, int] = {0: 0, 1: 0}
    for seed in (1, 2, 3, 4):
        phase = None
        for engine, state, frame in _states(first, second, seed):
            if frame.phase == phase:
                continue
            phase = frame.phase
            for tank in state.units:
                if not tank.is_vehicle or tank.hex is None or tank.wreck or tank.eliminated:
                    continue
                p = tank.player
                own = [u.hex for u in state.player_units(p) if u.kind in ("squad", "crew") and u.hex is not None and not u.broken and not u.eliminated]
                enemy = [u.hex for u in state.player_units(1 - p) if u.is_infantry and u.hex is not None and not u.eliminated]
                samples[p] += 1
                near_enemy = any(geometry.distance(tank.hex, h) <= 3 for h in enemy)
                screened = any(geometry.distance(tank.hex, h) <= 1 for h in own)
                alone[p] += near_enemy and not screened
    for p in (0, 1):
        assert samples[p] > 0
        assert alone[p] * 10 <= samples[p], f"side {p}: {alone[p]} of {samples[p]}"
