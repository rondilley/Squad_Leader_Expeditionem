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
is an integer count out of 1,296 and the arithmetic is exact. No rule is written here: a
change to a rule module changes these odds with it.

The smoke die of rule 24.6 is a third roll. It is rare and it adds to the roll, so the
odds here read the smoke as absent. An agent that wants the smoke in its odds asks for
`smoke=True` and gets the mean of the die.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from slcore.game import PHASE_DEFENSIVE_FIRE, FireGroup, State
from slcore.geometry import HexRef
from slcore.rules import r08_fire, r10_resolution, r11_terrain, r15_leadership, r25_concealment, r26_fanaticism
from slcore.rules.r12_morale import BERSERK_ROLL, RUSSIAN, morale_value
from slcore.tabledata import RESULT_KIA, RESULT_MC, RESULT_NONE
from slcore.units import KIND_LEADER, KIND_SQUAD, KIND_SW, Unit, UnitType

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
) -> Shot:
    """The expected result of a fire group at its target hex, in this phase.

    The group is a rule 8.6 fire group under formation or complete. Each member fires as
    the rules let it (range, long range, moved), the leader gives its rating, the terrain
    gives its modifier, and in the Defensive Fire Phase a unit that moved in the open
    takes the minus two of rule 16.5.
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
    occupants = [u for u in state.infantry_in(group.target) if not u.eliminated and u.player != firer_player]
    effect = 0
    kia = 0
    breaks: dict[int, int] = {}
    value = 0
    if halves <= 0 or not occupants:
        return Shot(group.target, halves, halves // 2, drm, 0, 0, {}, 0)
    # The check of each unit does not depend on the roll of the fire beyond the result, so
    # the failing ways of each unit at each result modifier are computed one time.
    per_unit: list[tuple[Unit, int, int, int]] = []
    for u in occupants:
        own = r25_concealment.halves_for(state, u, halves)
        if u.hidden and own == halves:
            own = halves // 2
        leader_mod, _ = r15_leadership.modifier_for_check(state, types, u)
        fanatic = r26_fanaticism.modifier_for(state, u)
        per_unit.append((u, own, leader_mod + fanatic, unit_value(types, u)))
    for raw, ways in DICE_WAYS.items():
        any_effect = False
        any_kia = False
        for u, own, check_mod, worth in per_unit:
            extra = moved_bonus if (moved_bonus and u.moved) else 0
            result = ctx.ift.lookup(own // 2, raw + drm + extra)
            if result == RESULT_NONE:
                continue
            any_effect = True
            if result == RESULT_KIA:
                any_kia = True
                fail = WAYS
            elif u.berserk:
                # Rule 18.42: a berserk unit takes no morale check.
                continue
            else:
                modifier = 0 if result == RESULT_MC else int(result)
                fail = check_fail_ways(morale_value(types, u), modifier + check_mod)
                if types[u.type_key].nationality == RUSSIAN:
                    # Rule 18.4: a natural two on the check sends a Russian unit berserk, and
                    # a berserk unit is not broken. That roll can never fail, so it comes off.
                    if BERSERK_ROLL + modifier + check_mod > morale_value(types, u):
                        fail -= DICE_WAYS[BERSERK_ROLL]
            chance = ways * fail
            if chance:
                breaks[u.id] = breaks.get(u.id, 0) + chance
                value += chance * worth
        if any_effect:
            effect += ways * WAYS
        if any_kia:
            kia += ways * WAYS
    return Shot(group.target, halves, halves // 2, drm, effect, kia, breaks, value)


def stack_value(types: Mapping[str, UnitType], units: Iterable[Unit]) -> int:
    return sum(unit_value(types, u) for u in units)


def is_shooter(unit: Unit) -> bool:
    """A unit that has firepower of its own: a squad or a crew, and not a leader."""
    return unit.kind in (KIND_SQUAD, "crew") and not unit.broken
