"""The parameter evolution of the doctrine agent (FR-44, FR-50): the search with no game in it.

Agent v7 has about thirty named parameters, and each pass of the doctrine work set them
by hand, one or two at a time, with a gauntlet for each idea. This module is the same
loop with no hand in it: a (mu + lambda) evolution strategy over the integer and the
boolean parameters, with the games as the fitness.

The design, and the cause of each part:

- The genome is the parameter record. A candidate is a mapping of the names in `SPACE`
  to a value in the range of the name, on top of a base record. So a candidate is also
  a command line, `v7[name=value,...]`, and a person can play it.
- The mutation is a step of a discrete normal on each parameter, with a rate, and a flip
  of a boolean with a lower rate. The step is one eighth of the range, so a search moves
  in the units the doctrine work moved in.
- A search may move a few parameters and hold the rest (`only`). A run of thirty
  parameters on a scenario of forty seconds a game reads its own noise, and a rule with
  three parameters of its own is a search of three.
- The selection is (mu + lambda): the parents of the next generation are the best mu of
  the elites and the children together. The elites play again in each generation,
  because a game is noise and a lucky elite must not hold its place by one draw.
- The fitness is a callable that scores a list of candidates at one time, so the command
  plays each game of a generation in one pool of workers, and the test scores with a
  function and no game.
- The same seeds score each candidate of a generation (common random numbers), so the
  order in a generation is the order of the play and not of the dice. Each generation
  gets new seeds, so an elite that stays is one that wins on many seeds.

The search is deterministic for its seed. The record of a run has each candidate of each
generation with its score, so a run artifact replays as a table.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field, replace
from typing import Any, Callable, Mapping, Sequence

from slagents.scripted.v7 import Parameters

# The range of each integer parameter the search moves. A parameter that is not here
# keeps the value of the base record.
SPACE: dict[str, tuple[int, int]] = {
    "aggression": (1, 6),
    "cover_preference": (0, 6),
    "fire_priority": (0, 6),
    "group_size": (2, 10),
    "threat_aversion": (0, 4),
    "close_combat_superiority": (1, 4),
    "superiority_tenths": (8, 30),
    "suppression_priority": (0, 5),
    "threat_scale": (2, 16),
    "schedule_margin": (0, 5),
    "route_risk": (0, 6),
    "fire_floor": (0, 10),
    "fire_weight": (0, 6),
    "overkill_share": (0, 25),
    "loss_scale": (4, 40),
    "route_loss": (4, 60),
    "return_margin": (0, 40),
    "close_combat_margin": (-20, 40),
    "urgency_cap": (1, 10),
    "suicide_percent": (30, 100),
    "spare_targets": (0, 4),
    "garrison_hexes": (0, 6),
    "share_targets": (1, 4),
    "field_weight": (0, 4),
    # The smoke of rule 24 (P15). The floor is in percent of a squad of expected loss
    # saved, and a screen over a force saves a few squads, so the range goes to 800.
    "smoke_floor": (0, 800),
    "smoke_fire_share": (0, 200),
    "smoke_horizon": (1, 4),
}

# The boolean parameters the search flips.
FLAGS: tuple[str, ...] = (
    "advance_into_close_combat",
    "share_fire",
    "rout_block",
    "rout_by_loss",
    "dash_arrives",
    "setup_by_odds",
)

Genome = dict[str, Any]

# The best candidate of a run is the one with the highest lower bound of its win rate,
# and this is the confidence of that bound (1.96 is 95 percent). A candidate with two
# generations at 32 percent and one with five generations at 32 percent are not the
# same claim, and the bound is what says so.
CONFIDENCE = 1.96


class EvolveError(Exception):
    """A setting of the search that cannot run."""


def genome_of(params: Parameters) -> Genome:
    """The searched parameters of a record, as a genome."""
    out: Genome = {name: int(getattr(params, name)) for name in SPACE}
    for name in FLAGS:
        out[name] = bool(getattr(params, name))
    return out


def parameters_of(genome: Mapping[str, Any], base: Parameters | None = None) -> Parameters:
    """The record of a genome, on top of a base record."""
    return replace(base or Parameters(), **dict(genome))


def clip(name: str, value: int) -> int:
    low, high = SPACE[name]
    return max(low, min(high, int(value)))


def text_of(genome: Mapping[str, Any], base: Parameters | None = None) -> str:
    """The agent name of a genome: `v7[name=value,...]` with the values that differ from
    the base, or `v7` when none does. A person can play it, and `make_agent` builds it."""
    origin = base or Parameters()
    parts = []
    for name in list(SPACE) + list(FLAGS):
        value = genome[name]
        if value != getattr(origin, name):
            parts.append(f"{name}={int(value) if isinstance(value, bool) else value}")
    return "v7" if not parts else "v7[" + ",".join(parts) + "]"


def moved_names(only: Sequence[str] | None = None) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """The integer names and the flag names a search moves, from an `only` list.

    An empty list moves each of them. A name that is not a parameter is an error, so a
    typo in a study does not run the full space in silence.
    """
    if not only:
        return tuple(SPACE), FLAGS
    unknown = [name for name in only if name not in SPACE and name not in FLAGS]
    if unknown:
        raise EvolveError(f"not parameters of the search: {', '.join(sorted(unknown))}")
    return tuple(n for n in SPACE if n in only), tuple(n for n in FLAGS if n in only)


def mutate(
    genome: Mapping[str, Any],
    rng: random.Random,
    rate: float = 0.25,
    flip_rate: float = 0.1,
    only: Sequence[str] | None = None,
) -> Genome:
    """One child of one parent: each integer moves with the rate by a discrete normal
    step of one eighth of its range, and each flag flips with the flip rate. A child is
    never its parent: when no parameter moved, one integer takes a step of one."""
    names, flags = moved_names(only)
    child: Genome = dict(genome)
    changed = False
    for name in names:
        low, high = SPACE[name]
        if rng.random() < rate:
            sigma = max(1.0, (high - low) / 8.0)
            step = int(round(rng.gauss(0.0, sigma)))
            if step == 0:
                step = rng.choice((-1, 1))
            value = clip(name, child[name] + step)
            if value != child[name]:
                child[name] = value
                changed = True
    for name in flags:
        if rng.random() < flip_rate:
            child[name] = not child[name]
            changed = True
    if not changed and names:
        name = rng.choice(list(names))
        low, high = SPACE[name]
        step = 1 if child[name] < high else -1
        child[name] = clip(name, child[name] + step)
    elif not changed and flags:
        name = rng.choice(list(flags))
        child[name] = not child[name]
    return child


def crossover(a: Mapping[str, Any], b: Mapping[str, Any], rng: random.Random, only: Sequence[str] | None = None) -> Genome:
    """A uniform crossover: each moved parameter from one parent or the other, and the
    rest from the first parent, which holds the base of a search with an `only` list."""
    names, flags = moved_names(only)
    moved = set(names) | set(flags)
    return {name: (a[name] if name not in moved or rng.random() < 0.5 else b[name]) for name in a}


@dataclass
class Candidate:
    """One genome in the run, with its scores by generation."""

    id: int
    genome: Genome
    parent_ids: tuple[int, ...] = ()
    scores: dict[int, float] = field(default_factory=dict)
    details: dict[int, Any] = field(default_factory=dict)

    @property
    def mean(self) -> float:
        return sum(self.scores.values()) / len(self.scores) if self.scores else 0.0

    @property
    def evaluations(self) -> int:
        return len(self.scores)

    def lower_bound(self, games: int) -> float:
        """The Wilson lower bound of the mean, over the games of each evaluation.

        A score is a share of wins, so the games of a candidate are its evaluations
        times the games of one evaluation. With no games known the bound is the mean.
        """
        n = self.evaluations * max(0, games)
        if n <= 0:
            return self.mean
        z = CONFIDENCE
        p = self.mean
        centre = p + z * z / (2 * n)
        margin = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        return (centre - margin) / (1 + z * z / n)

    def to_dict(self, base: Parameters | None = None, games: int = 0) -> dict[str, Any]:
        return {
            "id": self.id,
            "text": text_of(self.genome, base),
            "genome": dict(self.genome),
            "parents": list(self.parent_ids),
            "scores": {str(g): s for g, s in self.scores.items()},
            "mean": round(self.mean, 4),
            "lower_bound": round(self.lower_bound(games), 4),
            "evaluations": self.evaluations,
            "games": self.evaluations * max(0, games),
            "details": {str(g): d for g, d in self.details.items()},
        }


# The fitness of a generation: the candidates and the generation index in, one score for
# each candidate out (higher is better), with an optional detail record for each.
Fitness = Callable[[Sequence[Candidate], int], Sequence[tuple[float, Any]]]


@dataclass
class Generation:
    index: int
    elites: list[int]  # the candidate ids kept as parents, best first
    scored: list[tuple[int, float]]  # each candidate id scored in this generation, best first


@dataclass
class Evolution:
    """The state of one run: every candidate, and the elites of each generation."""

    base: Parameters
    candidates: list[Candidate] = field(default_factory=list)
    generations: list[Generation] = field(default_factory=list)
    games: int = 0  # the games of one evaluation, for the lower bound

    def candidate(self, cid: int) -> Candidate:
        return self.candidates[cid]

    def best(self) -> Candidate:
        """The candidate with the best lower bound of its win rate, among those that
        played two evaluations or more.

        The mean alone picks a candidate that had one lucky generation. The bound falls
        with the count of games, so a candidate that held an elite place for five
        generations wins against one that scored the same in two. A candidate of the
        last generation alone has no second measurement, so it is not the best of a run,
        and the search keeps it as a parent.
        """
        if not self.generations:
            raise EvolveError("no generation ran")
        pool = [c for c in self.candidates if c.evaluations >= 2]
        if not pool:
            pool = [self.candidates[cid] for cid in self.generations[-1].elites]
        return max(pool, key=lambda c: (c.lower_bound(self.games), c.evaluations, -c.id))

    def to_dict(self) -> dict[str, Any]:
        return {
            "base": text_of(genome_of(self.base)),
            "games_per_evaluation": self.games,
            "candidates": [c.to_dict(self.base, self.games) for c in self.candidates],
            "generations": [
                {"index": g.index, "elites": list(g.elites), "scored": [[cid, round(score, 4)] for cid, score in g.scored]}
                for g in self.generations
            ],
            "best": self.best().to_dict(self.base, self.games) if self.generations else None,
        }


def run_evolution(
    fitness: Fitness,
    generations: int,
    population: int = 8,
    parents: int = 3,
    seed: int = 1,
    base: Parameters | None = None,
    rate: float = 0.25,
    flip_rate: float = 0.1,
    crossover_rate: float = 0.3,
    games: int = 0,
    only: Sequence[str] | None = None,
    on_generation: Callable[[Evolution, Generation], None] | None = None,
) -> Evolution:
    """The (mu + lambda) loop. `population` is lambda, `parents` is mu.

    Generation 0 scores the base and `population - 1` children of it. Each later
    generation scores the elites again and `population` new children of them. The
    parents of a child are one elite, or two elites through a crossover.
    """
    if generations < 1:
        raise EvolveError("the search needs one generation or more")
    if population < 2 or parents < 1 or parents >= population + 1:
        raise EvolveError("the search needs a population of two or more and fewer parents than the population plus one")
    origin = base or Parameters()
    rng = random.Random(seed)
    run = Evolution(base=origin, games=games)

    def register(genome: Genome, parent_ids: tuple[int, ...]) -> Candidate:
        cand = Candidate(id=len(run.candidates), genome=genome, parent_ids=parent_ids)
        run.candidates.append(cand)
        return cand

    moved_names(only)  # a typo in the list is an error before the first game
    root = register(genome_of(origin), ())
    pool: list[Candidate] = [root]
    for _ in range(population - 1):
        pool.append(register(mutate(root.genome, rng, rate, flip_rate, only), (root.id,)))
    elites: list[Candidate] = []
    for index in range(generations):
        if index > 0:
            children: list[Candidate] = []
            for _ in range(population):
                if len(elites) > 1 and rng.random() < crossover_rate:
                    a, b = rng.sample(elites, 2)
                    genome = mutate(crossover(a.genome, b.genome, rng, only), rng, rate, flip_rate, only)
                    children.append(register(genome, (a.id, b.id)))
                else:
                    a = rng.choice(elites)
                    children.append(register(mutate(a.genome, rng, rate, flip_rate, only), (a.id,)))
            pool = list(elites) + children
        results = list(fitness(pool, index))
        if len(results) != len(pool):
            raise EvolveError(f"the fitness gave {len(results)} scores for {len(pool)} candidates")
        for cand, (score, detail) in zip(pool, results):
            cand.scores[index] = float(score)
            cand.details[index] = detail
        # The order of the generation: the score of this generation, then the mean over
        # the generations a candidate played, then the lower id (the older).
        order = sorted(pool, key=lambda c: (-c.scores[index], -c.mean, c.id))
        elites = order[:parents]
        gen = Generation(index=index, elites=[c.id for c in elites], scored=[(c.id, c.scores[index]) for c in order])
        run.generations.append(gen)
        if on_generation is not None:
            on_generation(run, gen)
    return run
