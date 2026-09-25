"""The odds of a fire: what a fire group does to a hex, before any die is thrown.

RV-9 table A gives the doctrine its numbers: concentrate fire on one target until the
probability of a break crosses a threshold and no further (P2), value a leader above a
squad (P12), and route a move by the expected loss of each hex and not by a count of the
enemies that see it (P7, P8). Each of those needs one function: the expected result of a
fire group at a hex. This module is that function.

It reads the core and rolls nothing. The firepower of the group comes from rule 8 and rule
9 (`r08_fire.group_firepower`, `r10_resolution.rural_halves`), the modifiers from rules 11
and 15 (`r10_resolution.common_modifier`), the moving-in-the-open modifier of rule 16.5,
the halving of rule 25.8 for a concealed unit, the table of rule 10, and the morale check
of rule 12 with the leadership of rule 15 and the fanatic modifier of rule 26. The two dice
of rule 10.4 and the two dice of the check are the 36 by 36 outcomes, so each probability
is an integer count out of 1,296. A leader who breaks stops helping the units the core
checks after him, and that count is the nearest count out of 1,296. No rule is written here: a
change to a rule module changes these odds with it.

A leader who fails a check gives the other units of its hex one more check (rule 12.22,
`r12_morale.leader_break_cascade`). A hex with a leader goes through an exact count of
each outcome for that (`_leader_raw`), and a hex with no leader keeps the fast count.
Before the exact count, in a stack of two 4-4-7 squads and an 8-0 leader in a stone
building, a charge broke each squad 72 times in 100 in the core and 65 in the odds.

`flame` and `charge` give the same result for a flamethrower (rules 22.1 and 22.2) and a
demolition charge (rules 23.1, 23.5, and 23.8), which fire alone and not as a group.

The smoke die of rule 24.6 is a third roll. It adds to the roll of a group whose line of
sight goes into, out of, or through a smoke hex, so a shot through smoke is worse for the
firer. `smoke=True` puts the mean of that die in the odds, and `group_meets_smoke` says
whether a group meets smoke on its line, by the same test the core uses (rule 24.6 with
`r24_smoke.blocks_path`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from slcore.game import PHASE_DEFENSIVE_FIRE, PHASE_PREP_FIRE, FireGroup, State
from slcore.geometry import HexRef
from slcore.los_eval import evaluate as evaluate_los
from slcore.rules import r08_fire, r10_resolution, r11_terrain, r22_flamethrower, r23_demolition, r24_smoke, r25_concealment, r26_fanaticism
from slcore.rules.r12_morale import BERSERK_ROLL, RUSSIAN, morale_value
from slcore.tabledata import RESULT_KIA, RESULT_MC, RESULT_NONE
from slcore.units import KIND_LEADER, KIND_SQUAD, KIND_SW, Unit, UnitType
from slcore.view import visible_to

# The 36 outcomes of two dice, as the count of each total.
DICE_WAYS: dict[int, int] = {2: 1, 3: 2, 4: 3, 5: 4, 6: 5, 7: 6, 8: 5, 9: 4, 10: 3, 11: 2, 12: 1}
WAYS = 36
# Each probability is a count out of this many outcomes: the fire dice and the check dice.
ONE = WAYS * WAYS

# The worth of a unit, in the same halves the firepower is in. A leader is worth the
# squads its rating lifts: a 9-2 leader in a fire group is a minus two on each roll, which
# is about one column of the table, and it rallies the broken (RV-9 P12).
LEADER_BASE_HALVES = 8
LEADER_RATING_HALVES = 6
WEAPON_VALUE_SHARE = 2  # a weapon is worth this share of its firepower in halves


@dataclass(frozen=True)
class Shot:
    """The expected result of one fire group at one hex.

    `chance` values are counts out of `ONE`. `value` is the sum over the units in the hex
    of the chance of a break times the worth of the unit, in halves times `ONE`.
    """

    target: HexRef
    halves: int
    firepower: int
    drm: int
    effect: int  # the chance that the table gives any result
    kia: int  # the chance of a KIA
    breaks: dict[int, int]  # unit id to the chance that it breaks or dies
    value: int

    @property
    def p_effect(self) -> float:
        return self.effect / ONE

    @property
    def p_kia(self) -> float:
        return self.kia / ONE

    def p_break(self, unit_id: int) -> float:
        return self.breaks.get(unit_id, 0) / ONE

    @property
    def expected_halves(self) -> float:
        return self.value / ONE


def unit_value(types: Mapping[str, UnitType], unit: Unit) -> int:
    """The worth of one unit to its side, in firepower halves.

    A squad or a crew is its firepower. A leader is a base plus its rating, because a good
    leader lifts each fire group and each rally it directs (RV-9 P12). A weapon is a share
    of its firepower, because a squad has to carry it. A broken unit is worth half: it is
    out of the fight until it rallies, and one more failed check removes it.
    """
    t = types[unit.type_key]
    if unit.kind == KIND_LEADER:
        worth = LEADER_BASE_HALVES + LEADER_RATING_HALVES * max(0, -t.leadership)
    elif unit.kind == KIND_SW:
        worth = max(1, t.firepower * 2 // WEAPON_VALUE_SHARE)
    else:
        worth = max(1, t.firepower * 2)
    if unit.broken:
        worth = max(1, worth // 2)
    return worth


def check_fail_ways(morale: int, modifier: int) -> int:
    """Rule 12.1: the number of the 36 rolls that fail a check at this morale and modifier."""
    ways = 0
    for roll, count in DICE_WAYS.items():
        if roll + modifier > morale:
            ways += count
    return ways


def shot(
    engine: Any,
    state: State,
    group: FireGroup,
    phase: str,
    smoke: bool = False,
    viewer: int | None = None,
) -> Shot:
    """The expected result of a fire group at its target hex, in this phase.

    The group is a rule 8.6 fire group under formation or complete. Each member fires as
    the rules let it (range, long range, moved), the leader gives its rating, the terrain
    gives its modifier, and in the Defensive Fire Phase a unit that moved in the open
    takes the minus two of rule 16.5.

    The odds count only the units in the target hex that `viewer` sees (S4). The viewer is
    the firer when the caller gives none. A unit below a concealment counter of the other
    side, or hidden by rule 42.1, is not in the count, so the odds of a shot never tell the
    agent what is below a counter.
    """
    ctx = engine.fire_ctx
    types = engine.types
    halves, members = r08_fire.group_firepower(state, types, group)
    halves, members = r10_resolution.rural_halves(ctx, state, group, members, ctx.wheat_in_season)
    drm, _parts = r10_resolution.common_modifier(ctx, state, group, phase)
    if smoke:
        # Rule 24.6: one die, so the mean is three and a half. The half rounds toward the
        # firer, so the odds stay a little hopeful and never hide a shot behind smoke.
        drm += 3
    firer_player = state.units[group.members[0][0]].player if group.members else -1
    moved_bonus = r11_terrain.moving_in_open_modifier(ctx.board, group.target) if phase == PHASE_DEFENSIVE_FIRE else 0
    return _resolve(engine, state, group.target, halves, drm, moved_bonus, firer_player, viewer)


def flame(
    engine: Any, state: State, player: int, weapon: Unit, target: HexRef, viewer: int | None = None, halved: bool = False
) -> Shot:
    """The expected result of a flamethrower of `player` at `target` (rules 22.1 and 22.2).

    The firepower is the printed one, and the attack has no modifier of any kind: no
    terrain, no leader, and no minus two against a unit that moved in the open. `halved`
    gives the half firepower of rule 22.1 against a concealed stand-in (see `charge`).
    """
    halves = r22_flamethrower.halves(engine.types, weapon)
    return _resolve(engine, state, target, halves // 2 if halved else halves, 0, 0, player, viewer)


def charge(
    engine: Any,
    state: State,
    player: int,
    weapon_key: str,
    target: HexRef,
    viewer: int | None = None,
    halved: bool = False,
) -> Shot:
    """The expected result of a demolition charge of `player` that explodes at `target`.

    Rules 23.1 and 23.5: 30 factors, and the protective cover of the hex is the one
    modifier. Rule 23.8: a roll of 12 is a dud. The charge goes off in the Advancing Fire
    Phase, so no unit takes the minus two of rule 16.5. The odds count the enemy units
    only; a caller keeps a charge off a hex with its own units.

    `halved` gives the half firepower of rule 23.5. A caller that values a hex below a
    concealment counter puts a visible stand-in there and asks with `halved`, because the
    odds never count a unit the player cannot see.
    """
    halves = r23_demolition.halves(engine.types, weapon_key)
    if halved:
        halves //= 2
    drm = r11_terrain.target_hex_modifier(engine.board, target)
    return _resolve(engine, state, target, halves, drm, 0, player, viewer, dud_roll=r23_demolition.MALFUNCTION_ROLL)


def _resolve(
    engine: Any,
    state: State,
    target: HexRef,
    halves: int,
    drm: int,
    moved_bonus: int,
    firer_player: int,
    viewer: int | None,
    dud_roll: int | None = None,
) -> Shot:
    """The chances of an attack of `halves` with `drm` at the enemy units of `target`.

    `moved_bonus` is the modifier of rule 16.5 for a unit that moved, and a raw roll of
    `dud_roll` gives no result at all.
    """
    ctx = engine.fire_ctx
    types = engine.types
    seer = firer_player if viewer is None else viewer
    occupants = [
        u
        for u in state.infantry_in(target)
        if not u.eliminated and u.player != firer_player and visible_to(state, u, seer)
    ]
    effect = 0
    kia = 0
    breaks: dict[int, int] = {}
    value = 0
    if halves <= 0 or not occupants:
        return Shot(target, halves, halves // 2, drm, 0, 0, {}, 0)
    # The core checks the units of one result group in leader-then-id order, and the
    # groups in order of the adjusted roll. A leader who breaks is not there for the
    # units that follow (rule 15.6).
    prepared: list[tuple[Unit, int, int, int]] = []
    for u in occupants:
        own = r25_concealment.halves_for(state, u, halves)
        if u.hidden and own == halves:
            own = halves // 2
        extra = moved_bonus if (moved_bonus and u.moved) else 0
        fanatic = r26_fanaticism.modifier_for(state, u)
        prepared.append((u, own, extra, fanatic))
    for raw, ways in DICE_WAYS.items():
        if raw == dud_roll:
            continue
        grouped: dict[tuple[int, int], list[tuple[Unit, int, int]]] = {}
        for u, own, extra, fanatic in prepared:
            grouped.setdefault((raw + drm + extra, own), []).append((u, fanatic, unit_value(types, u)))
        order: list[tuple[Unit, str, int, int]] = []
        for key in sorted(grouped):
            rows = sorted(grouped[key], key=lambda row: (row[0].kind != KIND_LEADER, row[0].id))
            adjusted, own_halves = key
            result = ctx.ift.lookup(own_halves // 2, adjusted)
            for u, fanatic, worth in rows:
                order.append((u, result, fanatic, worth))
        if any(u.kind == KIND_LEADER for u in occupants):
            # Rule 12.22 needs the status of each unit, so a hex with a leader goes to the
            # exact count (`_leader_raw`), and a hex with none keeps the fast count below.
            raw_breaks, raw_value, any_effect, any_kia = _leader_raw(state, types, order, occupants, ways)
            for uid, chance in raw_breaks.items():
                breaks[uid] = breaks.get(uid, 0) + chance
            value += raw_value
            if any_effect:
                effect += ways * WAYS
            if any_kia:
                kia += ways * WAYS
            continue
        helpers = frozenset(
            u.id for u, _result, _fanatic, _worth in order if u.kind == KIND_LEADER and not u.broken and not u.manned_mg
        )
        dist: dict[frozenset[int], int] = {helpers: 1}
        denom = 1
        any_effect = False
        any_kia = False
        for u, result, fanatic, worth in order:
            if result == RESULT_NONE:
                continue
            any_effect = True
            if result == RESULT_KIA:
                any_kia = True
                chance = ways * WAYS
                breaks[u.id] = breaks.get(u.id, 0) + chance
                value += chance * worth
                if u.id in helpers:
                    collapsed: dict[frozenset[int], int] = {}
                    for mask, weight in dist.items():
                        gone = frozenset(lid for lid in mask if lid != u.id)
                        collapsed[gone] = collapsed.get(gone, 0) + weight
                    dist = collapsed
                continue
            if u.berserk:
                continue
            modifier = 0 if result == RESULT_MC else int(result)
            morale = morale_value(types, u)
            russian = types[u.type_key].nationality == RUSSIAN
            next_dist: dict[frozenset[int], int] = {}
            break_numer = 0
            for mask, weight in dist.items():
                check_mod = _helper_rating(state, types, mask, u.id) + fanatic
                fail = _fail_ways(morale, modifier + check_mod, russian)
                break_numer += weight * fail
                if u.id in mask:
                    gone = frozenset(lid for lid in mask if lid != u.id)
                    next_dist[gone] = next_dist.get(gone, 0) + weight * fail
                    next_dist[mask] = next_dist.get(mask, 0) + weight * (WAYS - fail)
                else:
                    next_dist[mask] = next_dist.get(mask, 0) + weight * WAYS
            dist = next_dist
            denom *= WAYS
            chance = (WAYS * ways * break_numer + denom // 2) // denom
            if chance:
                breaks[u.id] = breaks.get(u.id, 0) + chance
                value += chance * worth
        if any_effect:
            effect += ways * WAYS
        if any_kia:
            kia += ways * WAYS
    return Shot(target, halves, halves // 2, drm, effect, kia, breaks, value)


# The memo of `_leader_count`, and the type tables of its keys.
LEADER_MEMO_LIMIT = 100_000
_LEADER_MEMO: dict[tuple, tuple[dict[int, int], int]] = {}
_LEADER_TABLES: dict[int, Any] = {}

# The status of a unit in the exact count of `_leader_raw`.
_OK = 0
_BROKEN = 1
_DEAD = 2
_BERSERK = 3


def _leader_raw(
    state: State,
    types: Mapping[str, UnitType],
    order: list[tuple[Unit, str, int, int]],
    occupants: list[Unit],
    ways: int,
) -> tuple[dict[int, int], int, bool, bool]:
    """The break chances of one fire roll at a hex with a leader, with rule 12.22.

    A leader who fails a check gives each other unit of its side in the hex one more
    check with no modifier, at once (`r12_morale.leader_break_cascade`). A unit that
    broke fails that check at its broken morale and dies, and a leader who fails it
    gives the hex one more round. The core does the checks of a failed leader before
    the next check of the fire, so a task list with those checks at the front gives
    the same order. The count goes through each outcome of each check, and a chance is
    the nearest count out of 1,296 for the `ways` of this roll.

    A KIA takes its units with no check (rule 8.8), so it gives no second check.
    """
    results = [(u, result, fanatic) for u, result, fanatic, _worth in order if result != RESULT_NONE]
    any_effect = bool(results)
    any_kia = any(result == RESULT_KIA for _u, result, _f in results)
    if not results:
        return {}, 0, False, False
    index = {u.id: i for i, u in enumerate(occupants)}
    worth = [unit_value(types, u) for u in occupants]
    # The count reads the result of each unit and not the roll or the firepower, and the
    # table has few results, so a decision meets the same count many times. The types
    # are in the key by identity, and `_LEADER_TABLES` holds them so that an identity is
    # not used two times.
    key = (
        id(types),
        tuple((u.id, result, fanatic) for u, result, fanatic in results),
        tuple((u.id, u.type_key, u.kind, u.broken, u.berserk, u.manned_mg, fanatic) for u, _r, fanatic, _w in order),
    )
    found = _LEADER_MEMO.get(key)
    if found is None:
        found = _leader_count(state, types, order, occupants, results, index)
        if len(_LEADER_MEMO) >= LEADER_MEMO_LIMIT:
            _LEADER_MEMO.clear()
        _LEADER_TABLES[id(types)] = types
        _LEADER_MEMO[key] = found
    weights, total = found
    out: dict[int, int] = {}
    value = 0
    for uid, weight in weights.items():
        count = (weight * ways * WAYS + total // 2) // total
        if count:
            out[uid] = count
            value += count * worth[index[uid]]
    return out, value, any_effect, any_kia


def _leader_count(
    state: State,
    types: Mapping[str, UnitType],
    order: list[tuple[Unit, str, int, int]],
    occupants: list[Unit],
    results: list[tuple[Unit, str, int]],
    index: dict[int, int],
) -> tuple[dict[int, int], int]:
    """The weight of a break or a death of each unit, over one total (`_leader_raw`)."""
    fanatic_of = {u.id: fanatic for u, _result, fanatic, _worth in order}
    cascade_order = sorted(occupants, key=lambda u: (u.kind != KIND_LEADER, u.id))
    start = tuple(_BERSERK if u.berserk else (_BROKEN if u.broken else _OK) for u in occupants)
    helpers = frozenset(u.id for u in occupants if u.kind == KIND_LEADER and not u.broken and not u.manned_mg)
    tasks: tuple[tuple[str, int, int], ...] = tuple(
        ("kia" if result == RESULT_KIA else "fire", u.id, 0 if result in (RESULT_MC, RESULT_KIA) else int(result))
        for u, result, _fanatic in results
    )
    # The count goes one check at a time, and each outcome of a check multiplies the
    # weight by its ways out of 36. A state with no check at this level multiplies by
    # 36, so each level has the one denominator 36 to the level, and equal states merge.
    level: dict[tuple, int] = {(tasks, start, helpers): 1}
    depth = 0
    leaves: dict[tuple[int, ...], tuple[int, int]] = {}
    ended: list[tuple[tuple[int, ...], int, int]] = []
    while level:
        following: dict[tuple, int] = {}

        def add(key: tuple, weight: int) -> None:
            following[key] = following.get(key, 0) + weight

        for (todo, status, mask), weight in level.items():
            if not todo:
                ended.append((status, weight, depth))
                continue
            (kind, uid, modifier), rest = todo[0], todo[1:]
            i = index[uid]
            if kind == "kia":
                if status[i] == _DEAD:
                    add((rest, status, mask), weight * WAYS)
                else:
                    add((rest, status[:i] + (_DEAD,) + status[i + 1 :], mask - {uid}), weight * WAYS)
                continue
            unit = occupants[i]
            if status[i] in (_DEAD, _BERSERK):
                add((rest, status, mask), weight * WAYS)
                continue
            broken = status[i] == _BROKEN
            morale = types[unit.type_key].broken_morale if broken else types[unit.type_key].morale
            check_mod = modifier + _helper_rating(state, types, mask, uid) + fanatic_of[uid]
            russian = kind == "fire" and types[unit.type_key].nationality == RUSSIAN
            berserk = DICE_WAYS[BERSERK_ROLL] if russian else 0
            fail = check_fail_ways(morale, check_mod)
            if russian and BERSERK_ROLL + check_mod > morale:
                fail -= DICE_WAYS[BERSERK_ROLL]
            passed = WAYS - fail - berserk
            if passed:
                add((rest, status, mask), weight * passed)
            if berserk:
                add((rest, status[:i] + (_BERSERK,) + status[i + 1 :], mask), weight * berserk)
            if fail:
                failed = status[:i] + (_DEAD if broken else _BROKEN,) + status[i + 1 :]
                if unit.kind == KIND_LEADER:
                    second = tuple(("leader_break", v.id, 0) for v in cascade_order if v.id != uid)
                    add((second + rest, failed, mask - {uid}), weight * fail)
                else:
                    add((rest, failed, mask), weight * fail)
        level = following
        depth += 1
    deepest = max(d for _s, _w, d in ended)
    total = WAYS**deepest
    for status, weight, d in ended:
        scaled = weight * WAYS ** (deepest - d)
        old, _ = leaves.get(status, (0, 0))
        leaves[status] = (old + scaled, 0)
    breaks: dict[int, int] = {}
    for status, (weight, _unused) in leaves.items():
        for i, u in enumerate(occupants):
            if status[i] in (_BROKEN, _DEAD) and status[i] != start[i]:
                breaks[u.id] = breaks.get(u.id, 0) + weight
    return breaks, total


def _helper_rating(state: State, types: Mapping[str, UnitType], mask: frozenset[int], unit_id: int) -> int:
    """The best leadership still standing in the hex, other than the unit on the check."""
    best: int | None = None
    for lid in mask:
        if lid == unit_id:
            continue
        rating = types[state.units[lid].type_key].leadership
        if best is None or rating < best:
            best = rating
    return 0 if best is None else best


def _fail_ways(morale: int, modifier: int, russian: bool) -> int:
    """The 36 rolls that break the unit. A Russian natural two goes berserk and does not break."""
    fail = check_fail_ways(morale, modifier)
    if russian and BERSERK_ROLL + modifier > morale:
        fail -= DICE_WAYS[BERSERK_ROLL]
    return max(0, fail)


def group_meets_smoke(engine: Any, state: State, group: FireGroup) -> bool:
    """Rule 24.6: the line of sight of one member goes into, out of, or through smoke.

    The core asks the same question of a real fire group (`r10_resolution.smoke_modifier`),
    so an agent that asks it here reads the board the rules read.
    """
    if not state.smoke:
        return False
    for uid, _weapon in group.members:
        firer = state.units[uid].hex
        if firer is None:
            continue
        traced = () if firer == group.target else evaluate_los(engine.board, engine.los, firer, group.target).traced
        if r24_smoke.blocks_path(state, traced, firer, group.target):
            return True
    return False


# One enemy fire group as a hex could draw it: its members and the best leader with them.
EnemyGroup = tuple[tuple[tuple[int, int | None], ...], int | None]


def enemy_groups(engine: Any, state: State, dst: HexRef, enemies: Iterable[Unit]) -> list[EnemyGroup]:
    """The fire groups these enemy units could form against a hex, with the best leader of each.

    Rule 8.6 chains the members of a group through adjacent hexes, so the shooters that
    see the hex fall into clusters of adjacent hexes, and each cluster is one group. The
    caller gives the enemy units, so a scripted agent gives the whole side and a prompt
    gives the units its player can see (AR-09).
    """
    types = engine.types
    by_hex: dict[HexRef, list[tuple[int, int | None]]] = {}
    leaders: dict[HexRef, Unit] = {}
    for enemy in enemies:
        if enemy.hex is None or enemy.broken or enemy.is_vehicle or enemy.hex == dst or enemy.eliminated:
            continue
        if not evaluate_los(engine.board, engine.los, enemy.hex, dst).clear:
            continue
        # Rule 15.2: a leader directs the group only when that leader has not fired.
        if enemy.kind == KIND_LEADER and not enemy.fired and not enemy.directed and not state.in_melee(enemy.hex):
            held = leaders.get(enemy.hex)
            if held is None or types[enemy.type_key].leadership < types[held.type_key].leadership:
                leaders[enemy.hex] = enemy
        # The same tests the core uses before it offers the shot. A unit that fired, or
        # a unit in melee, is not in the group. An empty phase string keeps the prep-fire
        # and advancing-fire marks out of this read: those marks belong to one phase.
        if r08_fire.can_fire_inherent(state, types, enemy, "") and r08_fire.member_firepower(
            state, types, enemy, None, dst, False
        ) is not None:
            by_hex.setdefault(enemy.hex, []).append((enemy.id, None))
        for weapon in state.carried_by(enemy.id):
            if not r08_fire.can_fire_weapon(state, types, enemy, weapon, ""):
                continue
            if r08_fire.member_firepower(state, types, enemy, weapon, dst, False) is not None:
                by_hex.setdefault(enemy.hex, []).append((enemy.id, weapon.id))
    groups: list[EnemyGroup] = []
    left = set(by_hex)
    while left:
        start = min(left)
        cluster = [start]
        left.discard(start)
        i = 0
        while i < len(cluster):
            for near in engine.board.neighbors(cluster[i]):
                if near in left:
                    left.discard(near)
                    cluster.append(near)
            i += 1
        members: list[tuple[int, int | None]] = []
        directing: list[Unit] = []
        covered = True
        for h in sorted(cluster):
            members.extend(by_hex[h])
            # The core offers a directing leader only when every hex of the group has one.
            candidate = leaders.get(h)
            if candidate is None:
                covered = False
            else:
                directing.append(candidate)
        leader = None
        if covered and directing:
            leader = min(directing, key=lambda u: types[u.type_key].leadership)
        groups.append((tuple(members), None if leader is None else leader.id))
    return groups


def loss(engine: Any, state: State, unit: Unit, dst: HexRef, moving: bool, groups: Iterable[EnemyGroup]) -> int:
    """The chance, out of `ONE`, that this unit breaks or dies in `dst` under the fire of
    these enemy groups. With `moving` the fire is the Defensive Fire Phase at a unit that
    moved there, so open ground costs the minus two of rule 16.5. The worst group sets the
    chance, because the defender spreads its groups over many targets and one hex draws
    one of them. A group that meets smoke on its line takes the die of rule 24.6."""
    stand_in = unit.with_(hex=dst, moved=moving, returned_from=None)
    # A unit that moves into the hex brings no friends with it. A unit that stands
    # there keeps them, and rule 15.6 gives it the leader in the hex.
    others: dict[int, Unit] = {}
    if moving:
        others = {u.id: u.with_(hex=None) for u in state.infantry_in(dst) if u.player == unit.player and u.id != unit.id}
    hypothetical = state.with_units({unit.id: stand_in, **others})
    phase = PHASE_DEFENSIVE_FIRE if moving else PHASE_PREP_FIRE
    chance = 0
    for members, leader in groups:
        group = FireGroup(dst, members, leader)
        smoke = group_meets_smoke(engine, hypothetical, group)
        result = shot(engine, hypothetical, group, phase, smoke=smoke, viewer=unit.player)
        chance = max(chance, result.breaks.get(unit.id, 0))
    return chance


def stack_value(types: Mapping[str, UnitType], units: Iterable[Unit]) -> int:
    return sum(unit_value(types, u) for u in units)


def is_shooter(unit: Unit) -> bool:
    """A unit that has firepower of its own: a squad or a crew, and not a leader."""
    return unit.kind in (KIND_SQUAD, "crew") and not unit.broken
