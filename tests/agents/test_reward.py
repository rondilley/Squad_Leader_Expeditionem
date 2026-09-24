"""The shaped reward of the learned tier (FR-51, follow-up item e).

The first rung ran on the result alone, and the policy learned to hold a game at the
command limit, because a truncation was worth zero and a loss minus one. The tests here
read each term on a real event of a real game, and the two ends: a truncation costs a loss,
and a win pays.
"""

from __future__ import annotations

import pytest

from slagents.learned.encoding import command_index
from slagents.learned.env import make_env
from slagents.learned.reward import (
    NATION_WEIGHTS,
    RewardWeights,
    doctrine_weights,
    event_rewards,
    objective_progress,
    result_rewards,
    term_counts,
    weights_for_scenario,
    with_weights,
)
from slcli.play import build_engine, make_agent
from slcore.events import Event


@pytest.fixture(scope="module")
def engine():
    return build_engine("s01_guards_counterattack")


def _events_of_a_game(engine, seed: int = 20260912, kinds=("broken", "eliminated", "unconcealed", "concealed", "morale_pass", "fire_result", "move", "advance")):
    """Each (before, after, events) of a v6 against v1 game whose events hold one of the kinds."""
    state = engine.new_game(seed)
    agents = (make_agent("v6", engine, seed, 0), make_agent("v1", engine, seed, 1))
    out = []
    n = 0
    while not state.game_over and n < 5000:
        frame = engine.legal_commands(state)
        lc = frame.by_id(agents[state.active].select(state, frame))
        after, events = engine.apply(state, lc.command, frame)
        if any(e.kind in kinds for e in events):
            out.append((state, after, events))
        state = after
        n += 1
    return out


def test_a_truncation_costs_a_loss_on_each_side(engine):
    w = RewardWeights()
    sides = engine.scenario.players()
    assert result_rewards(engine, sides[0], truncated=True, weights=w) == (w.loss, w.loss)
    assert result_rewards(engine, "draw", truncated=False, weights=w) == (w.loss, w.loss), "a draw by the card is a defeat too"
    assert result_rewards(engine, sides[0], truncated=False, weights=w) == (w.win, w.loss)
    assert result_rewards(engine, sides[1], truncated=False, weights=w) == (w.loss, w.win)
    assert w.loss < 0 < w.win and w.win >= 20 * w.kill, "the win is worth more than a game of kills"


def test_each_event_pays_the_side_the_doctrine_says(engine):
    w = RewardWeights()
    games = _events_of_a_game(engine)
    assert games, "the game had events to score"
    seen = set()
    for before, after, events in games:
        r0, r1 = event_rewards(engine, before, after, events, w)
        for e in events:
            data = e.data
            if e.kind in ("broken", "eliminated") and "unit" in data:
                victim = before.units[int(data["unit"])].player
                single = event_rewards(engine, before, after, [e], w)
                assert single[1 - victim] > 0 > single[victim], f"{e.kind} pays the other side"
                seen.add(e.kind)
            if e.kind == "unconcealed":
                owner = int(data["player"])
                single = event_rewards(engine, before, after, [e], w)
                assert single[1 - owner] == w.find and single[owner] == -w.find, "the side that is found pays"
                seen.add(e.kind)
            if e.kind == "concealed":
                owner = int(data["player"])
                single = event_rewards(engine, before, after, [e], w)
                assert single[owner] == w.hide, "the side that hides is paid"
                seen.add(e.kind)
            if e.kind == "morale_pass":
                owner = before.units[int(data["unit"])].player
                single = event_rewards(engine, before, after, [e], w)
                assert single[owner] == w.survive, "the unit that survives is paid"
                seen.add(e.kind)
            if e.kind == "fire_result" and data.get("units"):
                single = event_rewards(engine, before, after, [e], w)
                if "firer" in data:
                    firer = int(data["firer"])
                    assert single[firer] == w.fire and single[1 - firer] == -w.fire, "the side that fired is paid"
                else:
                    target = before.units[int(data["units"][0])].player
                    assert single[1 - target] == w.fire and single[target] == -w.fire, "the side shot at pays"
                seen.add(e.kind)
        counts = term_counts(engine, before, after, events)
        for term in set(counts[0]) | set(counts[1]):
            assert abs(counts[0][term] + counts[1][term]) < 1e-9, f"the count of {term} is zero-sum"
        assert abs(r0 + r1) < 1e-9, "with one weight set for both sides the reward is zero-sum too"
    assert {"broken", "fire_result", "morale_pass"} <= seen, f"the game showed the events: {sorted(seen)}"


def test_a_move_into_cover_pays_and_a_move_into_the_open_in_sight_costs(engine):
    w = RewardWeights()
    paid_cover = paid_exposed = paid_sneak = 0
    for before, after, events in _events_of_a_game(engine, kinds=("move", "advance")):
        for e in events:
            if e.kind not in ("move", "advance"):
                continue
            mover = before.units[int(e.data["unit"])].player
            single = event_rewards(engine, before, after, [e], w)
            from slcore import geometry
            from slcore.rules.r13_rout import is_cover

            dst = geometry.parse_hex_id(e.data["to"])
            if is_cover(engine.board, dst):
                assert single[mover] >= w.cover
                paid_cover += 1
            elif single[mover] < 0:
                assert single[mover] == -w.exposed, "open ground in an enemy's sight costs the exposure"
                paid_exposed += 1
            if single[mover] in (w.sneak, w.cover + w.sneak):
                paid_sneak += 1
    assert paid_cover > 0 and paid_exposed > 0 and paid_sneak > 0, (paid_cover, paid_exposed, paid_sneak)


def test_a_shared_hex_pays_once_and_a_crush_and_a_passenger_pay_a_kill():
    """Scenario 3A counts one factory hex for both sides. A transfer pays one time.

    A crushed squad and a passenger who dies with the vehicle pay the kill term.
    A fire result credits the firer named on the event, not the first unit in a mixed list.
    """
    from slagents.learned.reward import objective_swing, term_counts
    from slcore.events import Event
    from slcore.units import KIND_SQUAD

    assert objective_swing(1, 0) == 1
    assert objective_swing(0, 1) == -1
    assert objective_swing(1, -1) == 1
    assert objective_swing(-1, 1) == -1
    assert objective_swing(2, -1) == 2

    engine = build_engine("s01_guards_counterattack")
    state = engine.new_game(1)
    squad = next(u for u in state.units if u.kind == KIND_SQUAD and u.player == 1)
    leader = next(u for u in state.units if u.kind == "leader" and u.player == 0)
    crushed = term_counts(engine, state, state, [Event("35.8", "crushed", {"unit": squad.id, "vehicle": 0})])
    assert crushed[0]["kill"] == 1 and crushed[1]["kill"] == -1
    passenger = term_counts(
        engine, state, state, [Event("31.8", "passenger_eliminated", {"unit": squad.id, "vehicle": 0})]
    )
    assert passenger[0]["kill"] == 1
    mixed = term_counts(
        engine,
        state,
        state,
        [Event("10.5", "fire_result", {"units": [leader.id, squad.id], "firer": 0, "result": "M"})],
    )
    assert mixed[0]["fire"] == 1 and mixed[1]["fire"] == -1


def test_the_objective_term_reads_the_core_evaluator(engine):
    """The swing reads minus five before the set up, and the set up is not paid as progress."""
    from slagents.learned.reward import step_rewards

    state = engine.new_game(20260912)
    assert objective_progress(engine, state) == (-5, 0), "before the set up the Russians hold none of their five buildings"
    w = with_weights(objective=7.0)
    assert w.objective == 7.0 and w.kill == RewardWeights().kill
    # Play the set up with the scripted agents and read the baseline the setup_done event sets.
    agents = (make_agent("v6", engine, 1, 0), make_agent("v6", engine, 1, 1))
    progress = objective_progress(engine, state)
    paid = 0.0
    while state.phase == "setup":
        frame = engine.legal_commands(state)
        lc = frame.by_id(agents[state.active].select(state, frame))
        after, events = engine.apply(state, lc.command, frame)
        (r0, _r1), progress = step_rewards(engine, state, after, events, state.active, w, progress)
        paid += r0
        state = after
    assert progress == (0, 0), "after the set up the baseline is zero on each side"
    assert paid > -1.0 and paid <= 0.0, "the set up paid the step cost only, and no objective"


def test_the_environment_pays_the_shaped_reward_and_keeps_the_result(engine):
    """A whole game with random commands: the totals are the shaped sums, and results is the card's answer."""
    import numpy as np

    env = make_env(engine, seed=13)
    rng = np.random.default_rng(0)
    for _ in range(6000):
        agent = env.agent_selection
        if env.terminations[agent] or env.truncations[agent]:
            break
        triples = sorted(env.groups)
        env.step(triples[int(rng.integers(len(triples)))])
    assert env.state_.game_over
    results = [env.results[a] for a in env.possible_agents]
    assert sorted(results) == [-1.0, 1.0], "the result is the win and the loss"
    totals = [env._cumulative_rewards[a] for a in env.possible_agents]
    winner = results.index(1.0)
    assert totals[winner] > 0 > totals[1 - winner], "the win pays and the loss costs, whatever the small terms did"


def test_a_truncated_game_costs_both_sides(engine):
    env = make_env(engine, seed=13, max_commands=40)
    import numpy as np

    rng = np.random.default_rng(1)
    for _ in range(100):
        agent = env.agent_selection
        if env.terminations[agent] or env.truncations[agent]:
            break
        triples = sorted(env.groups)
        env.step(triples[int(rng.integers(len(triples)))])
    assert all(env.truncations.values()), "the game hit the limit"
    assert all(env.results[a] == 0.0 for a in env.possible_agents), "the result is no result"
    assert all(env._cumulative_rewards[a] <= env.weights[0].loss + 10 for a in env.possible_agents), "and the reward is a defeat on each side"


def test_each_army_reads_its_doctrine_weights(engine):
    """RV-9 table B: the Soviet side tolerates a loss, the American side leans on fire."""
    soviet, german = weights_for_scenario(engine)
    assert soviet.nation == "soviet" and german.nation == "german", "scenario 1 is Russians against Germans"
    american = doctrine_weights("american")
    assert doctrine_weights("british").nation == "universal", "the British profile is unsourced, so it gets no bias"
    assert doctrine_weights(None).nation == "universal"
    assert soviet.casualty_tolerance > german.casualty_tolerance > american.casualty_tolerance
    assert american.fire > german.fire and american.hurt > RewardWeights().hurt
    assert german.objective > RewardWeights().objective, "aggression high and counterattack high"
    assert soviet.find < RewardWeights().find, "reconnaissance low"
    assert set(NATION_WEIGHTS) == {"german", "soviet", "american"}


def test_a_lost_squad_costs_the_soviet_side_less_than_the_american_side():
    from collections import Counter

    loss = Counter({"kill": -1.0})
    gain = Counter({"kill": 1.0})
    soviet = doctrine_weights("russian")
    american = doctrine_weights("american")
    universal = RewardWeights()
    assert soviet.value(loss) > american.value(loss), "the Soviet side pays less for a lost squad"
    assert abs(universal.value(loss)) == universal.value(gain), "the universal weights are symmetric"
    assert soviet.value(gain) == universal.value(gain), "the tolerance scales the loss and not the gain"


def test_a_leader_kill_and_a_trap_pay_more_than_a_squad_kill(engine):
    from collections import Counter

    w = RewardWeights()
    assert w.value(Counter({"kill_leader": 1.0})) > w.value(Counter({"kill": 1.0})), "P12: kill leaders"
    assert w.value(Counter({"kill": 1.0, "trap": 1.0})) > w.value(Counter({"kill": 1.0})), "P11: trap the router"
    state = engine.new_game(20260912)
    from slcore.events import Event

    leader = next(u for u in state.units if u.kind == "leader" and u.player == 1)
    squad = next(u for u in state.units if u.kind == "squad" and u.player == 1)
    counts = term_counts(engine, state, state, [Event("13.6", "eliminated", {"unit": leader.id, "cause": "fire"})])
    assert counts[0]["kill_leader"] == 1 and counts[1]["kill_leader"] == -1
    counts = term_counts(engine, state, state, [Event("13.47", "eliminated", {"unit": squad.id, "cause": "no rout route"})])
    assert counts[0]["kill"] == 1 and counts[0]["trap"] == 1


def test_a_repeated_state_is_a_defeat_of_the_side_that_repeated_it(engine):
    """A drop and a pickup of the same weapon give the state before them. The game stops there."""
    from slcore.game import PHASE_MOVEMENT

    env = make_env(engine, seed=13)
    agents = (make_agent("v6", engine, 13, 0), make_agent("v6", engine, 13, 1))
    # Play with the scripted agents to a Movement Phase of player 0 in which a unit holds
    # a weapon it can put down.
    for _ in range(4000):
        state = env.state_
        assert not state.game_over, "the game ended before a Movement Phase with a drop"
        if state.active == 0 and state.phase == PHASE_MOVEMENT and any(lc.command.action == "drop" for lc in env.frame.commands):
            break
        frame = env.frame
        lc = frame.by_id(agents[state.active].select(state, frame))
        env.step(command_index(lc, env.groups))
    else:
        raise AssertionError("no Movement Phase with a drop in 4000 commands")
    before_total = env._cumulative_rewards[env.agent_of(0)]
    weapon = next(g for g in env.groups.values() if g.command.action == "drop")
    env.step(command_index(weapon, env.groups))
    assert not env.repeated
    pickup = next(g for g in env.groups.values() if g.command.action == "pickup" and g.command.weapon == weapon.command.weapon)
    env.step(command_index(pickup, env.groups))
    assert env.repeated, "the pickup gave the state the drop started from"
    assert all(env.truncations.values()), "the game stopped"
    assert env.results[env.agent_of(0)] == 0.0 and env.results[env.agent_of(1)] == 0.0, "no side won by the card"
    assert env._cumulative_rewards[env.agent_of(0)] <= before_total + env.weights[0].loss + 1.0, "the side that made the cycle paid the loss"
    assert env._cumulative_rewards[env.agent_of(1)] > env._cumulative_rewards[env.agent_of(0)], "and the other side did not"
