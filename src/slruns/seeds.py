"""The seed range of each command family, and the sample size a rate needs (L7).

Each command that plays games takes `--seed`, and each one had the default 1. The seeds
of a training run, of its evaluation, of a gauntlet, of an evolution, and of a tournament
were then the same numbers, and a measure played the games its subject had trained or
been selected on. The review of 2026-09-23 found that in two places: the evaluation of
`sl-cli train` played the training seeds (L4), and the default ranges of evolve, gauntlet,
and train overlapped (L7).

So each family plays in its own range: the seed a person gives is an offset inside the
range of the command. The ranges are one billion seeds apart, which no run reaches, and
the artifact records each seed it played, so a replay needs no knowledge of this table.
Training keeps the base zero, so a training run with a seed gives the games it gave
before this change.

The seed of the core is 64 bits (`slcore.rng.seed_state`), so the bases fit.
"""

from __future__ import annotations

from slruns.elo import wilson_interval

FAMILY_STRIDE = 1_000_000_000

# The base of each family. A new family goes at the end with the next multiple.
FAMILY_BASE: dict[str, int] = {
    "train": 0,
    "train_evaluation": 1 * FAMILY_STRIDE,
    "tournament": 2 * FAMILY_STRIDE,
    "gauntlet": 3 * FAMILY_STRIDE,
    "evolve": 4 * FAMILY_STRIDE,
    "evolve_final": 5 * FAMILY_STRIDE,
    "evolve_confirm": 6 * FAMILY_STRIDE,
    "gate": 7 * FAMILY_STRIDE,
}

# The smallest game count for a baseline rate. At 20 games one win of twenty has a 95
# percent interval of 0.9 to 24 percent, so a change below about 20 points is not visible.
# At 200 games the interval on a rate near one half is about 7 points each way.
MINIMUM_BASELINE_GAMES = 200


class UnknownFamily(ValueError):
    """A command asked for the seed range of a family this table does not name."""


def family_seed(family: str, seed: int, offset: int = 0) -> int:
    """The seed of one game: the base of the family, the seed a person gave, and the game's offset."""
    base = FAMILY_BASE.get(family)
    if base is None:
        raise UnknownFamily(f"no seed range for the command family {family!r}; the families are {sorted(FAMILY_BASE)}")
    return base + int(seed) + int(offset)


def rate_text(score: float, games: int) -> str:
    """A win rate with its 95 percent Wilson interval, as each command prints it."""
    low, high = wilson_interval(score, games)
    rate = score / games if games else 0.0
    shown = f"{score:g}"
    return f"{shown} of {games} ({rate * 100:.1f} percent, 95 percent interval {low * 100:.1f} to {high * 100:.1f})"


def sample_warning(games: int) -> str | None:
    """A warning line when a rate rests on fewer games than a baseline needs."""
    if games >= MINIMUM_BASELINE_GAMES:
        return None
    return (
        f"WARNING a rate of {games} games is not a baseline; use {MINIMUM_BASELINE_GAMES} or more "
        "to see a change of less than about 10 points"
    )
