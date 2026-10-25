"""The approach potential and the near limit of cover in the shaped reward (2026-10-20).

The nets of gate item 5 defended and did not attack. No term paid an attacker for getting
nearer to its objective, and cover and sneak paid a squad that stayed far back.
"""

from __future__ import annotations

import pytest

pytest.importorskip("numpy")

from slagents.base import decide
from slagents.learned import encoding, reward
from slagents.learned.env import make_env
from slcli.play import build_engine, make_agent
from slcore.events import Event
from slcore.geometry import distance
from slcore.rules.r13_rout import is_cover

SCENARIO = "lib02_pump_house"
SEED = 900101


@pytest.fixture(scope="module")
def engine():
    return build_engine(SCENARIO)


@pytest.fixture(scope="module")
def moving(engine):
    """The first Movement Phase of the attacker, after v7 set up the two sides."""
    env = make_env(engine, seed=SEED, use_routes=False)
    agents = {p: make_agent("v7", engine, SEED, p) for p in (0, 1)}
    while not (env.frame.phase == "movement" and env.frame.player == 0):
        legal = env.frame.by_id(decide(agents[env.frame.player], env.state_, env.frame))
        env.step(encoding.command_index(legal, env.groups))
    return env


def test_the_objective_of_a_side_is_the_hexes_its_condition_names(engine):
    attacker = reward.objective_hexes(engine, 0)
    assert attacker, "the Germans must take a building"
    assert not reward.objective_hexes(engine, 1), "the Russians have no positional condition"


def test_a_squad_that_goes_nearer_pays_and_a_squad_that_goes_back_pays_it_back(engine, moving):
    approach = reward.Approach(engine, moving.weights)
    state = moving.state_
    approach.start(state)
    nearer = None
    for legal in moving.frame.commands:
        c = legal.command
        if c.action != "move":
            continue
        unit = state.unit(c.units[0])
        if unit.kind == "squad" and approach.nearest(0, c.hex) == approach.nearest(0, unit.hex) - 1:
            nearer = legal
            break
    assert nearer is not None, "a squad has a move one hex nearer"
    after, _ = engine.apply(state, nearer.command, moving.frame)
    assert approach.swing(after) == (1, 0), "one hex nearer for one squad, and the defender has no term"
    back_frame = engine.legal_commands(after)
    back = next(l for l in back_frame.commands if l.command.action == "move" and l.command.units == nearer.command.units and l.command.hex == state.unit(nearer.command.units[0]).hex)
    again, _ = engine.apply(after, back.command, back_frame)
    assert approach.swing(again) == (-1, 0), "the move back gives the payment back"


def test_an_eliminated_squad_keeps_its_last_distance(engine, moving):
    approach = reward.Approach(engine, moving.weights)
    state = moving.state_
    approach.start(state)
    squad = next(u for u in state.units if u.player == 0 and u.kind == "squad" and u.hex is not None)
    gone = state.with_units({squad.id: squad.with_(eliminated=True, hex=None)})
    assert approach.swing(gone) == (0, 0), "a kill does not move the potential"


def test_the_approach_term_is_paid_at_the_end_of_a_player_turn(engine, moving):
    weights = moving.weights
    approach = reward.Approach(engine, weights)
    state = moving.state_
    approach.start(state)
    squad = next(u for u in state.units if u.player == 0 and u.kind == "squad" and u.hex is not None)
    target = min(reward.objective_hexes(engine, 0), key=lambda h: (distance(h, squad.hex), h))
    before = approach.nearest(0, squad.hex)
    nearer = state.with_units({squad.id: squad.with_(hex=target)})
    progress = reward.objective_progress(engine, state)
    (r0, r1), _ = reward.step_rewards(engine, state, nearer, [Event("4.8", "player_turn_end", {})], 1, weights, progress, approach)
    plain, _ = reward.step_rewards(engine, state, nearer, [Event("4.8", "player_turn_end", {})], 1, weights, progress)
    assert r0 - plain[0] == pytest.approx(weights[0].approach * before), "the attacker gets the approach of its squad"
    assert r1 == plain[1], "the defender gets no approach term"


def test_cover_far_from_the_objective_does_not_pay_the_attacker(engine, moving):
    approach = reward.Approach(engine, moving.weights)
    radius = moving.weights[0].cover_radius
    assert radius == 4
    cover = [h.ref for h in engine.board if is_cover(engine.board, h.ref)]
    far = next(h for h in cover if approach.nearest(0, h) > radius)
    near = next(h for h in cover if approach.nearest(0, h) <= radius)

    def paid(hex_ref, with_approach):
        counts = {0: {}, 1: {}}

        def credit(player, term, amount=1.0):
            counts[player][term] = counts[player].get(term, 0) + amount

        reward._credit_position(engine, moving.state_, 0, hex_ref, 1, credit, approach if with_approach else None)
        return counts[0].get("cover", 0)

    assert paid(far, False) == 1, "without the limit cover pays everywhere"
    assert paid(far, True) == 0, "the attacker gets no cover far from its objective"
    assert paid(near, True) == 1, "the attacker gets cover near its objective"
    assert approach.near(1, far), "the defender has no objective, so its cover pays everywhere"
