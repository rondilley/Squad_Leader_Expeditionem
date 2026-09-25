"""The snapshot league (FR-52).

A policy that only plays itself learns to beat itself. The league keeps three kinds of
opponent and samples between them:

- The random agent, which is the floor of the ladder.
- The versioned scripted agents, which are the constant opponents. Their version is in the
  run artifact, so a number from one run compares with a number from another (TC-18).
- The snapshots of the policy itself, taken at a fixed interval.

The sampling is by loss rate: an opponent that beats the learner more often is selected
more often. That is the rule the sibling project used, and it keeps the learner on the
opponents it has not solved. A cap on the share of one member holds the rule back where
it sends most of the games to an opponent the learner cannot beat at all: in the 10
million step run of 2026-09-17 the v6 agent got the most games of the scripted members,
and the learner won the Russian attack against it in 0 to 3 of 50 at each snapshot.

The Elo table has one entry for each opponent and each snapshot (TC-19). It uses the same
Elo code as the tournament, so one number means the same thing in the two places.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import torch

from slagents.learned.env import SquadLeaderEnv
from slagents.learned.nets import NetConfig, Policy
from slruns.elo import EloTable, wilson_interval

RANDOM = "random"
SNAPSHOT_PREFIX = "snapshot-"
MINIMUM_WEIGHT = 0.05


@dataclass
class Member:
    """One opponent in the league and how the learner does against it."""

    name: str
    kind: str
    act: Callable[[SquadLeaderEnv, Any], tuple[int, int, int, int]]
    # What a worker process builds this member from: the agent kind of a scripted member
    # (`v5`) or the snapshot path of a snapshot member. Empty for the random member.
    spec: str = ""
    games: int = 0
    losses: int = 0
    wins: int = 0
    draws: int = 0

    @property
    def loss_rate(self) -> float:
        """How often the learner loses to this member. A new member starts at one half."""
        return 0.5 if self.games == 0 else self.losses / self.games

    def record(self, reward: float) -> None:
        self.games += 1
        if reward > 0:
            self.wins += 1
        elif reward < 0:
            self.losses += 1
        else:
            self.draws += 1

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind,
            "games": self.games,
            "learner_wins": self.wins,
            "learner_losses": self.losses,
            "draws": self.draws,
            "loss_rate": round(self.loss_rate, 4),
        }


@dataclass
class League:
    """The opponents, the sampling, and the Elo table."""

    members: list[Member] = field(default_factory=list)
    elo: EloTable = field(default_factory=EloTable)
    snapshots: int = 0
    # The largest share of the games one member gets, or none. The weights above the cap
    # are cut to it and the rest spread over the others, until no member is above it.
    share_cap: float | None = None

    def add(self, member: Member) -> Member:
        self.members.append(member)
        return member

    def by_name(self, name: str) -> Member | None:
        for member in self.members:
            if member.name == name:
                return member
        return None

    def weights(self) -> list[float]:
        """Rule of the league: the loss rate, with a floor so no opponent disappears.

        With `share_cap` the weights are shares that add to one, and no member's share is
        above the cap (unless the cap is below one over the member count, in which case
        the shares are equal).
        """
        raw = [max(MINIMUM_WEIGHT, m.loss_rate) for m in self.members]
        if self.share_cap is None:
            return raw
        return capped_shares(raw, self.share_cap)

    def sample(self, generator: torch.Generator) -> Member:
        weights = torch.tensor(self.weights(), dtype=torch.float32)
        index = int(torch.multinomial(weights, 1, generator=generator).item())
        return self.members[index]

    def record(self, member: Member, reward: float, learner_name: str = "learner") -> None:
        member.record(reward)
        score = 1.0 if reward > 0 else (0.0 if reward < 0 else 0.5)
        self.elo.update(learner_name, member.name, score)

    def table(self, learner_name: str = "learner") -> dict[str, Any]:
        """The Elo table of TC-19, in the shape the run index reads (OR-04).

        One row for each member and one for the learner, each with its rating and its
        game count. The tournament writes the same shape, so `sl-cli runs --elo` shows a
        training run and a tournament run in one history.
        """
        rows = dict(self.elo.to_dict())
        for name in [learner_name] + [m.name for m in self.members]:
            rows.setdefault(name, {"rating": round(self.elo.rating(name), 1), "games": 0})
        return rows

    def record_table(self) -> list[dict[str, Any]]:
        """What the learner did against each member of the league."""
        return [m.to_dict() for m in self.members]

    def take_snapshot(self, policy: Policy, directory: Path, step: int, config: NetConfig) -> Path:
        """A copy of the policy as it is now, for a later opponent and for the artifact."""
        path = write_snapshot(policy, directory / f"{SNAPSHOT_PREFIX}{step}.pt", step, config)
        self.snapshots += 1
        return path


def capped_shares(weights: list[float], cap: float) -> list[float]:
    """The weights as shares of one, with no share above `cap`.

    Each share above the cap is set to the cap, and the excess goes to the members below
    it in proportion to their weight. The loop repeats until no share is above the cap,
    which takes at most one pass for each member. A cap at or below one over the member
    count gives equal shares.
    """
    n = len(weights)
    if n == 0:
        return []
    if cap <= 1.0 / n:
        return [1.0 / n] * n
    total = sum(weights)
    shares = [w / total for w in weights]
    fixed: set[int] = set()
    while True:
        over = [i for i in range(n) if i not in fixed and shares[i] > cap + 1e-12]
        if not over:
            return shares
        excess = sum(shares[i] - cap for i in over)
        for i in over:
            shares[i] = cap
            fixed.add(i)
        free = [i for i in range(n) if i not in fixed]
        if not free:
            return shares
        free_total = sum(shares[i] for i in free)
        for i in free:
            shares[i] += excess * (shares[i] / free_total if free_total > 0 else 1.0 / len(free))


def _json_object(extra: dict) -> dict:
    """The extra record as JSON values, so a snapshot holds no object the loader cannot read."""
    try:
        plain = json.loads(json.dumps(extra))
    except (TypeError, ValueError) as exc:
        raise ValueError("the snapshot extra must be JSON values") from exc
    if not isinstance(plain, dict):
        raise ValueError("the snapshot extra must be a JSON object")
    return plain


def write_snapshot(policy: Policy, path: Path, step: int, config: NetConfig, extra: dict | None = None) -> Path:
    """A policy on disk with the shape it needs to load again.

    The trainer writes one at each snapshot step, and the imitation fit writes one as the
    start of a run. `extra` is a record the writer adds, as the imitation record. It must
    be JSON values. The load uses `weights_only=True`, so a snapshot is weights and plain
    records and nothing else.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    saved = {
        "step": step,
        "state_dict": policy.state_dict(),
        "net": config.to_dict(),
        "spaces": {
            "units": policy.spaces.units,
            "actions": policy.spaces.actions,
            "targets": policy.spaces.targets,
            "cols": policy.spaces.cols,
            "rows": policy.spaces.rows,
            "options": policy.spaces.options,
        },
    }
    if extra:
        saved.update(_json_object(extra))
    torch.save(saved, path)
    return path


def load_snapshot(path: Path, policy: Policy) -> Policy:
    """A snapshot back into a policy of the same shape."""
    saved = torch.load(path, map_location="cpu", weights_only=True)
    policy.load_state_dict(saved["state_dict"])
    policy.eval()
    return policy


def win_rate(member: Member) -> float:
    return 0.0 if member.games == 0 else member.wins / member.games


def confidence_interval(wins: float, games: int) -> tuple[float, float]:
    """The Wilson interval, from the same code as the tournament (FR-58)."""
    return wilson_interval(wins, games)
