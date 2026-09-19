"""The odds of a fire (`slagents.scripted.odds`): the expected result of a fire group.

The odds are the number a doctrine agent trades on: concentrate until the chance of a break
is high enough (P2), value a leader above a squad (P12), route by the expected loss (P8).
A wrong number here is a wrong decision in every game, so the main test compares the odds
with the core itself. It takes a real fire group of a real game, resolves it with the core
under many random number states, and reads the frequency of each break against the
computed chance. The odds roll nothing, so the two have to agree within the noise of the
sample, and they agree on several different groups, phases, and target terrains.
"""

from __future__ import annotations

import math

from slcli.play import build_engine, make_agent
from slcore import rng
from slcore.game import PHASE_DEFENSIVE_FIRE, PHASE_PREP_FIRE, FireGroup
from slcore.rules import r10_resolution
from slcore.units import KIND_LEADER
from slagents.scripted import odds

SCENARIO = "s01_guards_counterattack"
SAMPLES = 1500


def _fire_states(engine, seed: int, phases: tuple[str, ...], limit: int = 6):
    """Real states of a real game with a complete fire group about to fire, in the phases."""
    agents = (make_agent("v6", engine, seed, 0), make_agent("v6", engine, seed, 1))
    state = engine.new_game(seed)
    found = []
    steps = 0
    while not state.game_over and steps < 6000 and len(found) < limit:
        frame = engine.legal_commands(state)
        chosen = frame.by_id(agents[state.active].select(state, frame))
        if chosen.command.action == "group_fire" and state.phase in phases and state.fire_group is not None:
            targets = [u for u in state.infantry_in(state.fire_group.target) if u.player != state.active]
            if targets and len(state.fire_group.members) >= 2:
                found.append(state)
        state, _ = engine.apply(state, chosen.command, frame)
        steps += 1
    assert found, f"no fire group with two members in {phases} on seed {seed}"
    return found


def _frequencies(engine, state, group: FireGroup, samples: int) -> tuple[dict[int, int], int, int]:
    """Resolve the same group under `samples` random number states, with the core."""
    before = {u.id: u for u in state.infantry_in(group.target) if u.player != state.active}
    broke = {uid: 0 for uid in before}
    effects = 0
    kias = 0
    for i in range(samples):
        rolled = state.with_(rng=rng.seed_state(1_000_003 * (i + 1)))
        after, events = r10_resolution.resolve_group(engine.fire_ctx, rolled, group, state.phase)
        kinds = [e.kind for e in events]
        if any(k in ("broken", "eliminated", "morale_pass", "berserk") for k in kinds) or any(
            e.kind == "fire_result" and e.data.get("result") != "-" for e in events
        ):
            effects += 1
        if any(e.kind == "fire_result" and e.data.get("result") == "KIA" for e in events):
            kias += 1
        for uid, was in before.items():
            now = after.units[uid]
            if now.eliminated or (now.broken and not was.broken):
                broke[uid] += 1
    return broke, effects, kias


def _close(count: int, chance: int, samples: int) -> bool:
    """Within four standard deviations of the binomial, plus one for a tiny chance."""
    p = chance / odds.ONE
    sigma = math.sqrt(max(p * (1 - p), 1e-6) * samples)
    return abs(count - p * samples) <= 4 * sigma + 1


def test_the_odds_agree_with_the_core_in_prep_fire():
    engine = build_engine(SCENARIO)
    for state in _fire_states(engine, 7, (PHASE_PREP_FIRE,), limit=4):
        group = state.fire_group
        result = odds.shot(engine, state, group, state.phase)
        broke, effects, kias = _frequencies(engine, state, group, SAMPLES)
        assert _close(effects, result.effect, SAMPLES), (effects, result.p_effect, result)
        assert _close(kias, result.kia, SAMPLES), (kias, result.p_kia, result)
        for uid, count in broke.items():
            assert _close(count, result.breaks.get(uid, 0), SAMPLES), (uid, count, result.p_break(uid), result)


def test_the_odds_agree_with_the_core_in_defensive_fire():
    """Rule 16.5: the minus two against a unit that moved in the open is in the odds."""
    engine = build_engine(SCENARIO)
    states = _fire_states(engine, 8, (PHASE_DEFENSIVE_FIRE,), limit=4)
    moved_in_open = 0
    for state in states:
        group = state.fire_group
        result = odds.shot(engine, state, group, state.phase)
        if any(u.moved for u in state.infantry_in(group.target)) and result.drm != r10_resolution.common_modifier(
            engine.fire_ctx, state, group, state.phase
        )[0]:
            moved_in_open += 1
        broke, effects, kias = _frequencies(engine, state, group, SAMPLES)
        assert _close(effects, result.effect, SAMPLES), (effects, result.p_effect, result)
        for uid, count in broke.items():
            assert _close(count, result.breaks.get(uid, 0), SAMPLES), (uid, count, result.p_break(uid), result)


def test_a_bigger_group_and_a_better_leader_raise_the_odds():
    """The odds move the way the table does: more firepower and a minus rating help."""
    engine = build_engine(SCENARIO)
    state = _fire_states(engine, 7, (PHASE_PREP_FIRE,), limit=1)[0]
    group = state.fire_group
    full = odds.shot(engine, state, group, state.phase)
    smaller = odds.shot(engine, state, FireGroup(group.target, group.members[:1], group.leader), state.phase)
    assert full.halves >= smaller.halves
    assert full.value >= smaller.value
    assert full.effect >= smaller.effect
    if group.leader is not None:
        rating = engine.types[state.units[group.leader].type_key].leadership
        without = odds.shot(engine, state, FireGroup(group.target, group.members, None), state.phase)
        if rating < 0:
            assert full.value >= without.value
        elif rating > 0:
            assert full.value <= without.value


def test_an_empty_hex_and_no_firepower_give_no_odds():
    engine = build_engine(SCENARIO)
    state = _fire_states(engine, 7, (PHASE_PREP_FIRE,), limit=1)[0]
    group = state.fire_group
    empty = next(h for h in engine.board.order if not state.infantry_in(h))
    nothing = odds.shot(engine, state, FireGroup(empty, group.members, group.leader), state.phase)
    assert nothing.value == 0 and nothing.effect == 0 and nothing.breaks == {}
    no_members = odds.shot(engine, state, FireGroup(group.target, (), None), state.phase)
    assert no_members.value == 0 and no_members.halves == 0


def test_a_leader_is_worth_more_than_a_squad_and_a_broken_unit_less():
    engine = build_engine(SCENARIO)
    state = engine.new_game(7)
    types = engine.types
    leaders = [u for u in state.units if u.kind == KIND_LEADER]
    squads = [u for u in state.units if u.kind == "squad"]
    best_leader = min(leaders, key=lambda u: types[u.type_key].leadership)
    assert odds.unit_value(types, best_leader) > max(odds.unit_value(types, s) for s in squads)
    squad = squads[0]
    assert odds.unit_value(types, squad.with_(broken=True)) < odds.unit_value(types, squad)
    assert odds.check_fail_ways(7, 0) == sum(c for r, c in odds.DICE_WAYS.items() if r > 7)
    assert odds.check_fail_ways(7, 2) > odds.check_fail_ways(7, 0)
    assert odds.check_fail_ways(12, 0) == 0
