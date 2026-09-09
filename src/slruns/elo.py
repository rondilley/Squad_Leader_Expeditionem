"""Elo ratings and the win rate interval (OR-04, FR-58).

Elo uses the usual logistic model with a K factor. The interval on a win rate is the
Wilson score interval, which behaves at 0 and 1 where the normal interval does not.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

START_RATING = 1500.0
K_FACTOR = 32.0
SCALE = 400.0
Z_95 = 1.959963984540054


def expected(rating_a: float, rating_b: float) -> float:
    return 1.0 / (1.0 + 10.0 ** ((rating_b - rating_a) / SCALE))


@dataclass
class EloTable:
    k: float = K_FACTOR
    ratings: dict[str, float] = field(default_factory=dict)
    games: dict[str, int] = field(default_factory=dict)

    def rating(self, agent: str) -> float:
        return self.ratings.get(agent, START_RATING)

    def update(self, agent_a: str, agent_b: str, score_a: float) -> tuple[float, float]:
        """score_a is 1 for a win, 0.5 for a draw, 0 for a loss."""
        if not 0.0 <= score_a <= 1.0:
            raise ValueError("the score must be between 0 and 1")
        ra = self.rating(agent_a)
        rb = self.rating(agent_b)
        ea = expected(ra, rb)
        new_a = ra + self.k * (score_a - ea)
        new_b = rb + self.k * ((1.0 - score_a) - (1.0 - ea))
        self.ratings[agent_a] = new_a
        self.ratings[agent_b] = new_b
        self.games[agent_a] = self.games.get(agent_a, 0) + 1
        self.games[agent_b] = self.games.get(agent_b, 0) + 1
        return new_a, new_b

    def to_dict(self) -> dict[str, dict[str, float | int]]:
        return {
            agent: {"rating": round(self.ratings[agent], 1), "games": self.games.get(agent, 0)}
            for agent in sorted(self.ratings)
        }


def wilson_interval(wins: float, total: int, z: float = Z_95) -> tuple[float, float]:
    """The Wilson score interval for a proportion. Draws count as half a win."""
    if total <= 0:
        return (0.0, 1.0)
    p = wins / total
    denominator = 1.0 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    margin = z * math.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, center - margin), min(1.0, center + margin))


@dataclass
class Record:
    wins: int = 0
    losses: int = 0
    draws: int = 0

    @property
    def games(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def score(self) -> float:
        return self.wins + 0.5 * self.draws

    @property
    def win_rate(self) -> float:
        return self.score / self.games if self.games else 0.0

    def interval(self) -> tuple[float, float]:
        return wilson_interval(self.score, self.games)

    def to_dict(self) -> dict[str, float | int]:
        low, high = self.interval()
        return {
            "wins": self.wins,
            "losses": self.losses,
            "draws": self.draws,
            "games": self.games,
            "win_rate": round(self.win_rate, 4),
            "confidence_low": round(low, 4),
            "confidence_high": round(high, 4),
        }
