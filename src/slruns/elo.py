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


def settled_ratings(results: list[tuple[str, str, float]], passes: int = 200) -> EloTable:
    """The Elo table of a finished round-robin, the same whatever the order of the games.

    One pass of the update rule gives a rating that depends on the order of play: the first
    games are played at equal ratings, so a win there is worth less than the same win at
    the end. A ladder that plays its pairs in a fixed order then ranks the first pair low.
    So the table fits the Bradley-Terry strengths to the whole result list with the
    minorization-maximization iteration of Hunter (2004), which reads the results as a
    set, and puts the strengths on the Elo scale about the start rating. A draw is half a
    win for each side. An agent with every game won or every game lost has no finite
    strength, so a small prior game against the field keeps the fit finite.
    """
    agents = sorted({name for first, second, _ in results for name in (first, second)})
    if not agents:
        return EloTable()
    wins: dict[str, float] = {a: 0.0 for a in agents}
    played: dict[tuple[str, str], float] = {}
    for first, second, score in results:
        wins[first] += score
        wins[second] += 1.0 - score
        key = (first, second) if first < second else (second, first)
        played[key] = played.get(key, 0.0) + 1.0
    # The prior: one game against each other agent, drawn (Hunter's regularisation).
    prior = 1.0 / max(1, len(agents) - 1)
    for i, a in enumerate(agents):
        for b in agents[i + 1 :]:
            played[(a, b)] = played.get((a, b), 0.0) + prior
            wins[a] += prior / 2.0
            wins[b] += prior / 2.0
    strength = {a: 1.0 for a in agents}
    for _ in range(passes):
        new: dict[str, float] = {}
        for a in agents:
            denominator = 0.0
            for (x, y), n in played.items():
                if a == x:
                    denominator += n / (strength[a] + strength[y])
                elif a == y:
                    denominator += n / (strength[a] + strength[x])
            new[a] = wins[a] / denominator if denominator > 0 else strength[a]
        mean = math.exp(sum(math.log(v) for v in new.values()) / len(new))
        strength = {a: v / mean for a, v in new.items()}
    table = EloTable()
    for a in agents:
        table.ratings[a] = START_RATING + SCALE * math.log10(strength[a])
        table.games[a] = sum(1 for first, second, _ in results if a in (first, second))
    return table


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
