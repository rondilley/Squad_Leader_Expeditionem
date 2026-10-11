"""Scripted agent v3: the tanker. It plays the armor rules 28 to 41.

Agent v1 plays rules 1 to 21 and agent v2 adds rules 22 to 27. Neither of them has a
policy for a vehicle, so a tank of theirs stands where the scenario put it and its gun
stays quiet. Agent v3 adds one policy for each armor command:

- A vehicle drives along a route to a firing position and holds there (`armor.py`).
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
- `tank_aggression`: how close a tank comes to enemy infantry: it keeps 7 minus this many
  hexes away (4 by default, beyond the panzerfaust and the bazooka).
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
from slagents.scripted.armor import ARMOR_FIRE_ACTIONS, ArmorParameters, ArmorPolicy  # noqa: F401


@dataclass(frozen=True)
class Parameters(V2Parameters):
    """The named parameters of the tanker."""

    armor_priority: int = 6
    tank_aggression: int = 3
    overrun: bool = True
    pivot_to_aim: bool = True


class ScriptedV3(ScriptedV2):
    name = "tanker"
    # 3.1 (2026-10-10): the vehicles use the armor policy of `armor.py` (a route to a firing
    # position, hold and fire, overrun only a weak target).
    version = "3.1"

    def __init__(self, engine: Engine, player: int, params: Parameters | None = None) -> None:
        super().__init__(engine, player, params or Parameters())
        self.params: Parameters = params or Parameters()
        self.armor = ArmorPolicy(
            engine,
            player,
            ArmorParameters(
                armor_priority=self.params.armor_priority,
                fire_priority=self.params.fire_priority,
                standoff=max(2, 7 - self.params.tank_aggression),
                overrun=self.params.overrun,
                pivot_to_aim=self.params.pivot_to_aim,
            ),
            objectives=lambda: self.objectives,
        )

    def select(self, state: State, frame: DecisionFrame) -> str:
        if not frame.commands:
            raise ValueError("no legal command")
        by_action: dict[str, list[LegalCommand]] = {}
        for lc in frame.commands:
            by_action.setdefault(lc.command.action, []).append(lc)
        choice = self.armor.choose(state, frame, by_action)
        if choice is not None:
            return choice
        return super().select(state, frame)


def with_parameters(**changes: object) -> Parameters:
    """A parameter record with named changes, for the tournament and the sweep (FR-44)."""
    return replace(Parameters(), **changes)  # type: ignore[arg-type]
