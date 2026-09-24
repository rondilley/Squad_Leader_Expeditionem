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


def _line_of_sight(engine):
    """Two adjacent open hexes that both see a third open hex."""
    from slcore.los_eval import evaluate

    board = engine.board
    opens = [h for h in board.order if board.hex(h).terrain == "open"]
    for left in opens:
        for right in board.neighbors(left):
            if right not in board or board.hex(right).terrain != "open":
                continue
            for target in opens:
                if target in (left, right):
                    continue
                if evaluate(board, engine.los, left, target).clear and evaluate(board, engine.los, right, target).clear:
                    return left, right, target
    raise AssertionError("the board has no two-hex line of sight")


def _stand(state, unit, hex_ref, **changes):
    return unit.with_(hex=hex_ref, broken=False, fired=False, directed=False, prep_fired=False, hidden=False, **changes)


def test_a_leader_in_one_hex_of_a_chain_gives_no_modifier():
    """The core lets a leader direct a group only when every hex of the chain has one."""
    engine = build_engine(SCENARIO)
    left, right, target = _line_of_sight(engine)
    state = engine.new_game(1)
    germans = [u for u in state.units if u.type_key.startswith("german:") and u.kind == "squad"]
    leader = next(u for u in state.units if u.type_key == "german:8-1")
    changed = {
        germans[0].id: _stand(state, germans[0], left),
        germans[1].id: _stand(state, germans[1], right),
        leader.id: _stand(state, leader, left),
    }
    stood = state.with_units(changed)
    groups = odds.enemy_groups(engine, stood, target, [stood.units[i] for i in changed])
    assert groups
    assert all(leader_id is None for _members, leader_id in groups)


def test_a_leader_in_each_hex_gives_the_best_rating():
    engine = build_engine(SCENARIO)
    left, right, target = _line_of_sight(engine)
    state = engine.new_game(1)
    squads = [u for u in state.units if u.type_key.startswith("german:") and u.kind == "squad"]
    best = next(u for u in state.units if u.type_key == "german:9-2")
    weak = next(u for u in state.units if u.type_key == "german:8-1")
    changed = {
        squads[0].id: _stand(state, squads[0], left),
        squads[1].id: _stand(state, squads[1], right),
        best.id: _stand(state, best, left),
        weak.id: _stand(state, weak, right),
    }
    stood = state.with_units(changed)
    groups = odds.enemy_groups(engine, stood, target, [stood.units[i] for i in changed])
    assert len(groups) == 1
    assert groups[0][1] == best.id
    from slcore.game import FireGroup
    from slcore.rules import r10_resolution

    group = FireGroup(target, groups[0][0], groups[0][1])
    _drm, parts = r10_resolution.common_modifier(engine.fire_ctx, stood, group)
    leader_part = next(part for part in parts if part["rule"] == "15.2")
    # QA-15.2: the chain uses the least effective leader, the 8-1, not the named 9-2.
    assert leader_part["value"] == engine.types[weak.type_key].leadership


def test_a_leader_with_a_machine_gun_contributes_that_weapon():
    engine = build_engine(SCENARIO)
    left, _right, target = _line_of_sight(engine)
    state = engine.new_game(1)
    leader = next(u for u in state.units if u.type_key == "german:8-1")
    weapon = next(u for u in state.units if u.type_key == "german:LMG")
    stood = state.with_units({
        leader.id: _stand(state, leader, left),
        weapon.id: weapon.with_(carrier=leader.id, hex=None, fired=False, malfunction=False, eliminated=False),
    })
    groups = odds.enemy_groups(engine, stood, target, [stood.units[leader.id], stood.units[weapon.id]])
    members = [member for group_members, _leader in groups for member in group_members]
    assert (leader.id, weapon.id) in members


def test_a_squad_that_stands_with_a_leader_breaks_less_often():
    """Rule 15.6: a squad that is not moving keeps the leader in its hex."""
    engine = build_engine(SCENARIO)
    left, _right, target = _line_of_sight(engine)
    state = engine.new_game(1)
    shooter = next(u for u in state.units if u.type_key.startswith("german:") and u.kind == "squad")
    squad = next(u for u in state.units if u.type_key.startswith("russian:") and u.kind == "squad")
    leader = next(u for u in state.units if u.type_key == "russian:10-2")
    base = {
        shooter.id: _stand(state, shooter, left),
        squad.id: _stand(state, squad, target),
    }
    alone = state.with_units(base)
    with_leader = state.with_units({**base, leader.id: _stand(state, leader, target)})
    enemies = [alone.units[shooter.id]]
    groups = odds.enemy_groups(engine, alone, target, enemies)
    assert groups
    without = odds.loss(engine, alone, alone.units[squad.id], target, False, groups)
    covered = odds.loss(engine, with_leader, with_leader.units[squad.id], target, False, groups)
    assert covered < without


def test_a_berserk_squad_does_not_share_a_loss_cache_entry():
    from slagents.prompted.oddsview import OddsView
    from slagents.scripted.v7 import ScriptedV7

    engine = build_engine(SCENARIO)
    state = engine.new_game(1)
    squad = next(u for u in state.units if u.player == 0 and u.kind == "squad")
    dst = next(iter(engine.board.order))
    agent = ScriptedV7(engine, 0)
    agent._loss(state, squad, dst, False)
    agent._loss(state, squad.with_(berserk=True), dst, False)
    assert len(agent._loss_map) == 2
    view = OddsView(engine, state, 0)
    view.loss(squad, dst, False)
    view.loss(squad.with_(berserk=True), dst, False)
    assert len(view._loss) == 2
