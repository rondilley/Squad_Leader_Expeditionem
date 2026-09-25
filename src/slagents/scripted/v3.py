"""Scripted agent v3: the tanker. It plays the armor rules 28 to 41.

Agent v1 plays rules 1 to 21 and agent v2 adds rules 22 to 27. Neither of them has a
policy for a vehicle, so a tank of theirs stands where the scenario put it and its gun
stays quiet. Agent v3 adds one policy for each armor command:

- A vehicle drives towards the objective, in the same way an infantry unit does.
- A gun fires at an enemy vehicle first, because rule 33.4 says a shell through the armour
  removes a counter that no infantry weapon can touch.
- A machine gun fires at infantry after the gun.
- A panzerfaust or a bazooka fires at any vehicle in range, because rule 37.3 removes the
  counter after one use and a counter that is never used is a counter that is lost.
- Infantry that stands next to a vehicle in cover attacks it in the Defensive Fire Phase
  (rule 36.1), and infantry that shares a hex with one attacks it in close combat (36.2).
- A broken gun gets its repair die in the Rally Phase (rule 38.1).

The named parameters (FR-44):

- `armor_priority`: how much the agent adds to a shot at a vehicle over a shot at
  infantry.
- `tank_aggression`: how far a vehicle drives towards the objective in one command.
- `overrun`: whether a vehicle drives into a hex that enemy infantry holds (rule 35).
- `pivot_to_aim`: whether a vehicle that will not move turns to face the nearest enemy.

The agent is deterministic for a state and a frame, so a game of v3 against v3 replays.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from slagents.scripted.v2 import Parameters as V2Parameters
from slagents.scripted.v2 import ScriptedV2
from slcore import geometry
from slcore.engine import Engine
from slcore.frame import DecisionFrame, LegalCommand
from slcore.game import (
    PHASE_ADVANCING_FIRE,
    PHASE_CLOSE_COMBAT,
    PHASE_DEFENSIVE_FIRE,
    PHASE_MOVEMENT,
    PHASE_PREP_FIRE,
    PHASE_RALLY,
    State,
)
from slcore.rules import r28_vehicles
from slcore.view import visible_to

ARMOR_FIRE_ACTIONS = ("at_fire", "afv_fire", "afv_mg", "afv_attack")


@dataclass(frozen=True)
class Parameters(V2Parameters):
    """The named parameters of the tanker."""

    armor_priority: int = 6
    tank_aggression: int = 3
    overrun: bool = True
    pivot_to_aim: bool = True


class ScriptedV3(ScriptedV2):
    name = "tanker"
    version = "3"

    def __init__(self, engine: Engine, player: int, params: Parameters | None = None) -> None:
        super().__init__(engine, player, params or Parameters())
        self.params: Parameters = params or Parameters()

    # ------------------------------------------------------------- selection

    def select(self, state: State, frame: DecisionFrame) -> str:
        if not frame.commands:
            raise ValueError("no legal command")
        by_action: dict[str, list[LegalCommand]] = {}
        for lc in frame.commands:
            by_action.setdefault(lc.command.action, []).append(lc)
        phase = frame.phase
        if phase == PHASE_RALLY and "afv_repair" in by_action:
            # Rule 38.1: a gun that nobody works on stays broken for the game.
            return min(by_action["afv_repair"], key=lambda lc: lc.id).id
        if phase in (PHASE_PREP_FIRE, PHASE_DEFENSIVE_FIRE, PHASE_ADVANCING_FIRE):
            shot = self._armor_shot(state, by_action)
            if shot is not None:
                return shot
        if phase == PHASE_MOVEMENT:
            drive = self._drive(state, by_action)
            if drive is not None:
                return drive
        if phase == PHASE_CLOSE_COMBAT and "cc_afv" in by_action:
            # Rule 36.23: a squad that stands on a tank kills it on its firepower factor.
            return min(by_action["cc_afv"], key=lambda lc: lc.id).id
        return super().select(state, frame)

    # ----------------------------------------------------------------- fire

    def _armor_shot(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        """The best armor shot of this window, or None when the agent has no policy for one."""
        best: LegalCommand | None = None
        best_score: tuple[int, int] | None = None
        for action in ARMOR_FIRE_ACTIONS:
            for lc in by_action.get(action, []):
                score = self._shot_score(state, action, lc)
                if score is None:
                    continue
                if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                    best, best_score = lc, score
        return None if best is None else best.id

    def _shot_score(self, state: State, action: str, lc: LegalCommand) -> tuple[int, int] | None:
        """How much this shot is worth. A shot at a vehicle is worth the most."""
        target = lc.command.hex
        if target is None:
            return None
        payload = dict(lc.command.extra)
        vehicle = r28_vehicles.vehicle_in(state, target)
        hostile = vehicle is not None and vehicle.player != self.player
        occupants = sum(1 for u in state.infantry_in(target) if u.player != self.player and visible_to(state, u, self.player) and not u.broken)
        if action == "at_fire":
            # Rule 37: one of these weapons has no other target, so it fires when it can.
            return (self.params.armor_priority * 2, 0) if hostile else None
        if action == "afv_attack":
            return (self.params.armor_priority, 0) if hostile else None
        if action == "afv_fire":
            if str(payload.get("aim")) == "vehicle":
                return (self.params.armor_priority, 0)
            if occupants == 0:
                return None
            return (self.params.fire_priority * occupants, occupants)
        if action == "afv_mg":
            if occupants == 0:
                return None
            return (self.params.fire_priority * occupants - 1, occupants)
        return None

    # ------------------------------------------------------------- movement

    def _drive(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        """Rule 30: a vehicle drives towards the objective, and rule 35 lets it drive over."""
        best: LegalCommand | None = None
        best_score: tuple[int, int] | None = None
        for lc in by_action.get("vehicle_move", []):
            unit = state.units[lc.command.units[0]]
            dst = lc.command.hex
            if unit.hex is None or dst is None:
                continue
            gain = self._distance(unit.hex) - self._distance(dst)
            enemies = sum(1 for u in state.infantry_in(dst) if u.player != self.player and visible_to(state, u, self.player))
            if enemies and not self.params.overrun:
                continue
            score = (gain * self.params.tank_aggression + enemies * self.params.armor_priority, enemies)
            if best_score is None or score > best_score or (score == best_score and best is not None and lc.id < best.id):
                best, best_score = lc, score
        if best is not None and best_score is not None and best_score[0] > 0:
            return best.id
        return self._aim(state, by_action)

    def _aim(self, state: State, by_action: dict[str, list[LegalCommand]]) -> str | None:
        """Rule 30.5: a vehicle that will not drive turns its gun towards the nearest enemy."""
        if not self.params.pivot_to_aim:
            return None
        enemies = [u.hex for u in state.player_units(1 - self.player) if u.hex is not None]
        if not enemies:
            return None
        for lc in sorted(by_action.get("vehicle_pivot", []), key=lambda lc: lc.id):
            unit = state.units[lc.command.units[0]]
            if unit.hex is None or unit.pivoted:
                continue
            near = min(enemies, key=lambda h: (geometry.distance(unit.hex, h), h))
            if r28_vehicles.in_covered_arc(unit.hex, unit.facing, near):
                continue
            facing = int(dict(lc.command.extra).get("facing", -1))
            if facing >= 0 and r28_vehicles.in_covered_arc(unit.hex, facing, near):
                return lc.id
        return None


def with_parameters(**changes: object) -> Parameters:
    """A parameter record with named changes, for the tournament and the sweep (FR-44)."""
    return replace(Parameters(), **changes)  # type: ignore[arg-type]
