"""How performance in one scenario decides the next one (FR-17).

Rule 1 of the Campaign Game says that how a player does in one scenario influences the
chances of advancement, and indirectly of survival, in the next. The printed rules carry
that influence in one place only: the rank of the personal leader, which decides the
counter that joins the force.

This module carries it in two more places, and both are the project's own rules, not the
printed ones. A campaign is still its seed and nothing else, because each step reads only
what the earlier steps recorded.

1. The strength of the defence. A player who wins meets a stronger position next time, and
   a player who loses meets a weaker one. The step is a fixed number of force points for
   each win above the losses, plus a smaller part for the points on the personnel file. The
   total stays between a floor and a ceiling, so a run of wins cannot make a scenario that
   no force can take, and a run of losses cannot make one that plays itself.

2. The draw itself. The seed of the next scenario mixes the record so far, so the board
   type, the armies, the turn count, and the victory condition all follow from what
   happened. Two campaigns from one seed that go differently do not meet the same
   scenarios, which is what a sequence influenced by performance means.

The mix is a small integer hash. It is not a cryptographic hash and it does not need to
be: it needs to be a repeatable function of the record, and multiplication by an odd
constant with a mask does that in integers (NFR-05).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MASK = (1 << 31) - 1
ODD = 2654435761
CARRIED_DIVISOR = 5


@dataclass(frozen=True)
class Ladder:
    """The rules that turn a record into the next scenario."""

    base_points: int = 400
    step: int = 45
    floor: int = 220
    ceiling: int = 900
    seed_step: int = 1000

    def points_for(self, wins: int, losses: int, carried: int) -> int:
        """The point total of the defending force of the next scenario."""
        swing = (wins - losses) * self.step + carried // CARRIED_DIVISOR
        return max(self.floor, min(self.ceiling, self.base_points + swing))

    def seed_for(self, campaign_seed: int, index: int, wins: int, losses: int, carried: int) -> int:
        """The seed of the next scenario, mixed with the record so far."""
        state = (wins * 7 + losses * 13 + carried) & MASK
        mixed = ((campaign_seed + index * self.seed_step) ^ (state * ODD)) & MASK
        return mixed

    def to_dict(self) -> dict[str, Any]:
        return {
            "base_points": self.base_points,
            "step": self.step,
            "floor": self.floor,
            "ceiling": self.ceiling,
            "seed_step": self.seed_step,
        }
