"""Scripted agent v4: the doctrine agent. Fire and maneuver, do not move under fire.

v4 keeps the fire, setup, rout, and close-combat logic of v1, and it changes two things
that real small-unit doctrine calls the load-bearing rules (see
docs/research/2026-09-10_RV-9_small_unit_and_combined_arms_doctrine.md):

1. Do not maneuver under effective fire (FM 3-21.8, FM 3-90). Each candidate move hex gets a
   threat value: the firepower that an unbroken enemy could deliver on it with a clear line
   of sight. The move score subtracts that threat, and cover halves it, so the agent routes
   through cover and low-threat hexes toward the objective instead of walking into a beaten
   zone. Prep fire (inherited from v1) suppresses the enemy first, which lowers the threat of
   the lane on the same turn, so the fire and the move work together.

2. Assault only a suppressed enemy or with local superiority (FM 3-90, MCDP 1-3). v1 rewards
   an advance into any enemy hex, which is a suicide charge against a fresh defender in cover.
   v4 advances into an enemy hex only when the enemy there is broken, or when the agent brings
   enough units to win the close combat.

A nation profile biases the named parameters, so a German, Soviet, or American agent plays
its own way. The numbers come from the national doctrine research; British is not yet in the
profile set because that research pass did not confirm a distinct British profile.

The threat map reads infantry firepower only. Vehicle fire is not in it yet, so on an armor
board v4 routes against infantry threat and leaves the armor logic to v3. That is a follow-up.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from slcore.engine import Engine
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import State
from slcore.geometry import HexRef
from slcore.los_eval import evaluate as evaluate_los
from slcore.rules import r08_fire
from slcore.rules.r13_rout import is_cover

from slagents.scripted.v1 import Parameters as V1Parameters
from slagents.scripted.v1 import ScriptedV1


@dataclass(frozen=True)
class Parameters:
    """The named parameters of v4. It is a superset of the v1 parameters (FR-44)."""

    aggression: int = 2
    cover_preference: int = 3
    fire_priority: int = 2
    group_size: int = 3
    advance_into_close_combat: bool = True
    # v4 adds these:
    threat_aversion: int = 1
    close_combat_superiority: int = 2  # our units must reach this fraction of the tenths below
    superiority_tenths: int = 15  # 1.5x: assault an unbroken enemy only with this local edge


# Nation profiles. The values are the behavioral biases the national doctrine research gave
# (see RV-9, table B). German: high initiative and aggression, bold movement. Soviet: high
# close-combat willingness and casualty tolerance, so a lower threat aversion. American: high
# reliance on fire, so cautious movement and a higher fire priority. British is not here yet:
# the research did not confirm a distinct British profile, so v4:british raises until a
# follow-up pass lands.
NATION_PROFILES: dict[str, Parameters] = {
    "german": Parameters(aggression=3, cover_preference=3, fire_priority=2, threat_aversion=1, superiority_tenths=13),
    "soviet": Parameters(aggression=3, cover_preference=2, fire_priority=2, threat_aversion=1, close_combat_superiority=2, superiority_tenths=12),
    "american": Parameters(aggression=2, cover_preference=4, fire_priority=3, threat_aversion=2, superiority_tenths=18),
}


class UnknownNation(Exception):
    """The nation profile is not defined. British waits for its research pass."""


def profile_for(nation: str) -> Parameters:
    key = nation.strip().lower()
    if key not in NATION_PROFILES:
        raise UnknownNation(
            f"no v4 profile for {nation!r}. Defined: {', '.join(sorted(NATION_PROFILES))}. "
            f"British is not confirmed yet and waits for a follow-up research pass."
        )
    return NATION_PROFILES[key]


def with_parameters(**changes: object) -> Parameters:
    return replace(Parameters(), **changes)


class ScriptedV4(ScriptedV1):
    name = "scripted"
    version = "4"

    def __init__(self, engine: Engine, player: int, params: Parameters | None = None) -> None:
        self.v4 = params or Parameters()
        # v1 reads its own field names off self.params; the v4 parameters are a superset, so
        # v1's methods keep working through the same attribute names.
        super().__init__(engine, player, V1Parameters(
            aggression=self.v4.aggression,
            cover_preference=self.v4.cover_preference,
            fire_priority=self.v4.fire_priority,
            group_size=self.v4.group_size,
            advance_into_close_combat=self.v4.advance_into_close_combat,
        ))
        self.opponent = 1 - player

    # ---------------------------------------------------------- the threat map

    def _threat(self, state: State, dst: HexRef, cache: dict[HexRef, int]) -> int:
        """The firepower an unbroken enemy could put on dst with a clear line of sight.

        The enemy fires defensively during our movement, so it is stationary: moving=False.
        The line of sight uses the static cache in the engine, so this is cheap.
        """
        found = cache.get(dst)
        if found is not None:
            return found
        total = 0
        for enemy in state.player_units(self.opponent):
            if enemy.hex is None or enemy.broken:
                continue
            fire = r08_fire.member_firepower(state, self.engine.types, enemy, None, dst, False)
            if fire is None:
                continue
            if evaluate_los(self.engine.board, self.engine.los, enemy.hex, dst).clear:
                total += fire.halves
        cache[dst] = total
        return total

    def _move_score(self, state: State, dst: HexRef, unit_count: int, cache: dict[HexRef, int], unit_hex: HexRef) -> tuple[int, int]:
        gain = self._distance(unit_hex) - self._distance(dst)
        covered = is_cover(self.engine.board, dst)
        cover = self.v4.cover_preference if covered else 0
        threat = self._threat(state, dst, cache)
        if covered:
            threat //= 2  # cover mitigates fire, so a covered bound is worth the risk
        value = gain * self.v4.aggression + cover - threat * self.v4.threat_aversion
        return (value, unit_count)

    # -------------------------------------------------------------- movement

    def _move(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        cache: dict[HexRef, int] = {}
        best: LegalCommand | None = None
        best_score: tuple[int, int] | None = None
        for action in ("stack_move", "move"):
            for lc in by_action.get(action, []):
                unit = state.units[lc.command.units[0]]
                dst = lc.command.hex
                if unit.hex is None or dst is None:
                    continue
                score = self._move_score(state, dst, len(lc.command.units), cache, unit.hex)
                if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                    best = lc
                    best_score = score
        if best is not None and best_score is not None and best_score[0] > 0:
            return best.id
        if "end_phase" in by_action:
            return by_action["end_phase"][0].id
        return self._relief(state, by_action, best)

    # --------------------------------------------------------------- advance

    def _advance(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str:
        """Advance toward the objective, and assault a hex only when the odds are good.

        A hex with an unbroken enemy is a close combat. Doctrine assaults a suppressed enemy
        or one it outnumbers, not a fresh defender in cover. So the enemy in the hex is a
        reason to advance only when it is broken, or when this stack brings local superiority.
        Otherwise the enemy is not a bonus and the advance is scored as a plain move.
        """
        cache: dict[HexRef, int] = {}
        best: LegalCommand | None = None
        best_score: tuple[int, int, int] | None = None
        for lc in by_action.get("advance", []):
            unit = state.units[lc.command.units[0]]
            dst = lc.command.hex
            if unit.hex is None or dst is None:
                continue
            enemies = [u for u in state.infantry_in(dst) if u.player != self.player]
            unbroken = [u for u in enemies if not u.broken]
            favorable = self._assault_is_favorable(len(lc.command.units), unbroken)
            if unbroken and not favorable:
                if not self.v4.advance_into_close_combat:
                    continue
                assault_bonus = 0  # do not reward a charge into a fresh defender
            else:
                assault_bonus = len(enemies) * self.v4.aggression
            gain = self._distance(unit.hex) - self._distance(dst)
            cover = self.v4.cover_preference if is_cover(self.engine.board, dst) else 0
            threat = self._threat(state, dst, cache)
            value = gain * self.v4.aggression + cover + assault_bonus - threat * self.v4.threat_aversion
            score = (value, 1 if (not unbroken or favorable) else 0, -len(unbroken))
            if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                best = lc
                best_score = score
        if best is not None and best_score is not None and best_score[0] > 0:
            return best.id
        return self._first_of(by_action, ("end_phase",))

    def _assault_is_favorable(self, our_count: int, unbroken_enemies: list) -> bool:
        if not unbroken_enemies:
            return True
        return our_count * 10 >= len(unbroken_enemies) * self.v4.superiority_tenths
