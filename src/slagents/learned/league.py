"""The snapshot league (FR-52).

A policy that only plays itself learns to beat itself. The league keeps three kinds of
opponent and samples between them:

- The random agent, which is the floor of the ladder.
- The versioned scripted agents, which are the constant opponents. Their version is in the
  run artifact, so a number from one run compares with a number from another (TC-18).
- The snapshots of the policy itself, taken at a fixed interval.

The sampling is by loss rate: an opponent that beats the learner more often is selected
more often. That is the rule the sibling project used, and it keeps the learner on the
opponents it has not solved.

The Elo table has one entry for each opponent and each snapshot (TC-19). It uses the same
Elo code as the tournament, so one number means the same thing in the two places.
"""

from __future__ import annotations

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
    act: Callable[[SquadLeaderEnv, Any], tuple[int, int, int]]
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

    def add(self, member: Member) -> Member:
        self.members.append(member)
        return member

    def by_name(self, name: str) -> Member | None:
        for member in self.members:
            if member.name == name:
                return member
        return None

    def weights(self) -> list[float]:
        """Rule of the league: the loss rate, with a floor so no opponent disappears."""
        return [max(MINIMUM_WEIGHT, m.loss_rate) for m in self.members]

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
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{SNAPSHOT_PREFIX}{step}.pt"
        torch.save(
            {
                "step": step,
                "state_dict": policy.state_dict(),
                "net": config.to_dict(),
                "spaces": {
                    "units": policy.spaces.units,
                    "actions": policy.spaces.actions,
                    "targets": policy.spaces.targets,
                    "cols": policy.spaces.cols,
                    "rows": policy.spaces.rows,
                },
            },
            path,
        )
        self.snapshots += 1
        return path


def load_snapshot(path: Path, policy: Policy) -> Policy:
    """A snapshot back into a policy of the same shape."""
    saved = torch.load(path, map_location="cpu", weights_only=False)
    policy.load_state_dict(saved["state_dict"])
    policy.eval()
    return policy


def win_rate(member: Member) -> float:
    return 0.0 if member.games == 0 else member.wins / member.games


def confidence_interval(wins: float, games: int) -> tuple[float, float]:
    """The Wilson interval, from the same code as the tournament (FR-58)."""
    return wilson_interval(wins, games)
