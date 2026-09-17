"""Scripted agent v5: the combined-arms doctrine agent. It closes two v4 gaps.

Agent v4 does two things well: it does not maneuver into a beaten zone, and it does not
assault a fresh defender without local superiority. The v4 note (VIBE_HISTORY, 2026-09-10)
lists what it still gets wrong, and each item is a place a strong human beats it. Agent v5
closes two of them, and every change is on the agent side, so the core does not change and a
v5 game against v5 replays (TR-02).

1. Vehicle fire is in the threat map now. Agent v4 reads infantry firepower only, so on an
   armor board it walks a squad in front of a tank gun. Agent v5 adds the gun and the machine
   gun of each unbroken enemy vehicle that has a clear line of sight to a candidate hex. So it
   routes its infantry around the arc of a tank the way it routes them around a machine gun.

2. Fire and maneuver, not fire then maneuver. Agent v4 inherits v1's fire, which shoots at the
   best raw odds. That breaks whatever is easiest, which is not always what blocks the advance.
   Agent v5 adds a suppression bonus to the target score: the more of our own units an enemy in
   the target hex can see and hit, the more the agent wants to break it first. So prep fire
   suppresses the defender that covers the lane, and then the move goes through the lane the
   same turn (FM 3-21.8, the base-of-fire element fixes the enemy so the maneuver element can
   move). This is the load-bearing change on an infantry board.

The third v4 gap, close-combat odds by firepower and not by head count, waits for a later
slice: the v4 advance call passes the counts, not the units, so a real firepower gate needs a
wider signature, and this slice keeps that surface. The v4 count gate stays in force here.

A nation profile biases the named parameters, the same three the v4 research gave, plus the
suppression weight. The American profile leans hardest on fire, the German on tempo, the
Soviet on the close assault.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from slcore.engine import Engine
from slcore.frame import LegalCommand
from slcore.game import State
from slcore.geometry import HexRef
from slcore.los_eval import evaluate as evaluate_los
from slcore.rules import r08_fire, r11_terrain, r34_afv_vs_infantry
from slcore.units import Unit

from slagents.scripted.v4 import Parameters as V4Parameters
from slagents.scripted.v4 import ScriptedV4


@dataclass(frozen=True)
class Parameters:
    """The named parameters of v5. It is a superset of the v4 parameters (FR-44)."""

    aggression: int = 2
    cover_preference: int = 3
    fire_priority: int = 2
    group_size: int = 3
    advance_into_close_combat: bool = True
    threat_aversion: int = 1
    close_combat_superiority: int = 2
    superiority_tenths: int = 15
    # v5 adds this:
    suppression_priority: int = 2  # weight of "this target threatens our own units" in fire


# The nation profiles carry the v4 biases and add the suppression weight. American doctrine
# relies on fire, so its suppression weight is the highest. German doctrine values tempo, so it
# keeps the v4 aggression. Soviet doctrine presses the close assault, so its suppression weight
# is the lowest of the three.
NATION_PROFILES: dict[str, Parameters] = {
    "german": Parameters(aggression=3, cover_preference=3, fire_priority=2, threat_aversion=1, superiority_tenths=13, suppression_priority=2),
    "soviet": Parameters(aggression=3, cover_preference=2, fire_priority=2, threat_aversion=1, close_combat_superiority=2, superiority_tenths=12, suppression_priority=1),
    "american": Parameters(aggression=2, cover_preference=4, fire_priority=3, threat_aversion=2, superiority_tenths=18, suppression_priority=3),
}


class UnknownNation(Exception):
    """The nation profile is not defined. British waits for its research pass."""


def profile_for(nation: str) -> Parameters:
    key = nation.strip().lower()
    if key not in NATION_PROFILES:
        raise UnknownNation(
            f"no v5 profile for {nation!r}. Defined: {', '.join(sorted(NATION_PROFILES))}. "
            f"British is not confirmed yet and waits for a follow-up research pass."
        )
    return NATION_PROFILES[key]


def with_parameters(**changes: object) -> Parameters:
    return replace(Parameters(), **changes)


class ScriptedV5(ScriptedV4):
    name = "scripted"
    version = "5"

    def __init__(self, engine: Engine, player: int, params: Parameters | None = None) -> None:
        self.v5 = params or Parameters()
        super().__init__(
            engine,
            player,
            V4Parameters(
                aggression=self.v5.aggression,
                cover_preference=self.v5.cover_preference,
                fire_priority=self.v5.fire_priority,
                group_size=self.v5.group_size,
                advance_into_close_combat=self.v5.advance_into_close_combat,
                threat_aversion=self.v5.threat_aversion,
                close_combat_superiority=self.v5.close_combat_superiority,
                superiority_tenths=self.v5.superiority_tenths,
            ),
        )

    # ------------------------------------------------------- gap 1: vehicle threat

    def _threat(self, state: State, dst: HexRef, cache: dict[HexRef, int]) -> int:
        """v4's infantry threat, plus the gun and machine gun of each unbroken enemy vehicle.

        A tank that sees dst puts its gun firepower on the Infantry Fire Table there, and its
        machine gun adds to that. So a lane in front of a tank reads as high threat, and the
        move scorer routes around it exactly as it routes around infantry fire.
        """
        found = cache.get(dst)
        if found is not None:
            return found
        total = 0
        for enemy in state.player_units(self.opponent):
            if enemy.hex is None or enemy.broken:
                continue
            if enemy.is_vehicle:
                total += self._vehicle_threat(state, enemy, dst)
                continue
            fire = r08_fire.member_firepower(state, self.engine.types, enemy, None, dst, False)
            if fire is None:
                continue
            if evaluate_los(self.engine.board, self.engine.los, enemy.hex, dst).clear:
                total += fire.halves
        cache[dst] = total
        return total

    def _vehicle_threat(self, state: State, vehicle: Unit, dst: HexRef) -> int:
        ctx = self.engine.armor_ctx
        if ctx is None or vehicle.hex is None:
            return 0
        if not evaluate_los(self.engine.board, self.engine.los, vehicle.hex, dst).clear:
            return 0
        threat = 0
        if self.engine.types[vehicle.type_key].gun > 0:
            # A turret can turn, so the gun threatens any hex it can see (rule 34.2). The
            # firepower is the Infantry Fire Table value of a hit, which is what the move
            # scorer already speaks in.
            threat += r34_afv_vs_infantry.firepower_halves(ctx, vehicle, dst)
        mg = r08_fire.member_firepower(state, self.engine.types, vehicle, None, dst, False)
        if mg is not None:
            threat += mg.halves
        return threat

    # ------------------------------------------ gap 2: fire and maneuver, suppression first

    def _target_score(self, state: State, lc: LegalCommand, target: HexRef) -> tuple[int, int, int]:
        """v1's odds and terrain, plus a bonus for a target that threatens our own force.

        The suppression value is how many of our unbroken units the unbroken enemy in the
        target hex can see and hit. Breaking that enemy first lowers the fire on our advance,
        so a base-of-fire element covers the maneuver element (FM 3-21.8).
        """
        halves = self._member_value(state, lc, target)
        modifier = r11_terrain.target_hex_modifier(self.engine.board, target)
        occupants = sum(1 for u in state.infantry_in(target) if u.player != self.player and not u.broken)
        suppression = self._suppression_value(state, target) * self.v5.suppression_priority
        value = halves * self.params.fire_priority - modifier * 2 + suppression
        return (value, occupants, -modifier)

    def _suppression_value(self, state: State, target: HexRef) -> int:
        shooters = [u for u in state.infantry_in(target) if u.player != self.player and not u.broken]
        if not shooters:
            return 0
        threatened = 0
        for ours in state.player_units(self.player):
            if ours.hex is None or ours.broken:
                continue
            for enemy in shooters:
                if enemy.hex is None:
                    continue
                fire = r08_fire.member_firepower(state, self.engine.types, enemy, None, ours.hex, False)
                if fire is None:
                    continue
                if evaluate_los(self.engine.board, self.engine.los, enemy.hex, ours.hex).clear:
                    threatened += 1
                    break
        return threatened
