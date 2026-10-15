"""Jump-Start RL: a guide agent plays the first turns of the learner's side.

PPO learns from the games it wins, and a policy that wins no game gives the win term of
the reward nothing to pay. The s04 attacker won 0 of 12,046 training games against v7 and
6 of 5,484 in the third part of the curriculum (2026-10-13), so 24 hours of training did
not move the attack (docs/reports/2026-10-13_training_review.md).

Jump-Start RL (Uchendu et al., 2023, https://arxiv.org/abs/2204.02372) gives the learner
games that a strong agent began. A guide plays the learner's side for the first turns of
each game, and the learner plays the rest. A game the guide began well is one the learner
can win, so the win term pays and the value head sees states near a win. When the learner
wins enough of the games at one horizon, the guide plays one turn less. At a horizon of
zero the learner plays the whole game, which is the normal training.

The horizon is in game turns, not in decisions, because a turn is the unit in which the
scenarios give their time, and a Movement Phase is a hundred decisions of one side. The
guide never plays the last turn, so each game has decisions of the learner.

The rewards of the guide's turns go to no decision of the learner: the worker starts the
learner's account at its first decision, as it does for the commands of the opponent
before that decision. The game result counts for the learner, and the league records it.

Only the games that started at the current horizon count for the step down. A game that
started before a step down has the old horizon, and it is not evidence for the new one.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any


@dataclass
class JumpStart:
    """The guide, its horizon, and the rule that makes the horizon shorter.

    `turns` is the horizon of the next game. After `window` games at that horizon, the
    horizon goes down by one turn when the learner won `threshold` or more of the last
    `window` of them. The record of each change goes into the run artifact.
    """

    guide: str
    turns: int
    threshold: float = 0.4
    window: int = 100
    games: int = 0
    changes: list[dict[str, Any]] = field(default_factory=list)
    _recent: deque = field(default_factory=deque, repr=False)

    def __post_init__(self) -> None:
        if self.turns < 0:
            raise ValueError(f"the jump-start horizon is {self.turns} turns; it must be zero or more")
        if not 0.0 < self.threshold <= 1.0:
            raise ValueError(f"the jump-start threshold is {self.threshold}; it must be above 0 and at most 1")
        if self.window < 1:
            raise ValueError(f"the jump-start window is {self.window} games; it must be one or more")
        self._recent = deque(maxlen=self.window)

    def next(self) -> tuple[str, int] | None:
        """The guide and the horizon of a new game, or None when the guide plays no turn."""
        return (self.guide, self.turns) if self.turns > 0 else None

    def record(self, turns: int, result: float) -> None:
        """One game that ended, with the horizon it started with and its result."""
        self.games += 1
        if turns != self.turns or self.turns == 0:
            return
        self._recent.append(1.0 if result > 0 else 0.0)
        if len(self._recent) < self.window:
            return
        rate = sum(self._recent) / len(self._recent)
        if rate >= self.threshold:
            self.changes.append({"games": self.games, "from_turns": self.turns, "to_turns": self.turns - 1, "win_rate": round(rate, 3)})
            self.turns -= 1
            self._recent.clear()

    def win_rate(self) -> float:
        """The learner's win rate in the recent games at the current horizon, 0 for none."""
        return sum(self._recent) / len(self._recent) if self._recent else 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "guide": self.guide,
            "turns": self.turns,
            "threshold": self.threshold,
            "window": self.window,
            "games": self.games,
            "changes": list(self.changes),
        }
