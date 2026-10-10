"""A start from the scripted agents: the policy copies their decisions before PPO (FR-51).

Two runs of 1 million PPO steps from a random start learned a defence against attackers
that do not come, and no attack (VIBE_HISTORY, 2026-09-13 and 2026-09-14). The scripted
agents v5 and v6 win the Russian attack of scenario 1 against v1 on the front board. So
the policy first learns to give the command a scripted agent gives in the same state, and
PPO then starts from a policy that already attacks.

The data comes from games the scripted agents play in the environment of FR-50, so each
observation is the one the trainer reads, and each label is the triple of the environment's
action space. A trace file of FR-60 holds the view and not the state, so it cannot give the
board tensor again; the games are played here instead. Nothing in this module knows a
rule of the game: the teacher selects from the frame, and the environment asks the core.

The fit is a cross entropy on the three heads: the negative log probability of the
teacher's triple under the policy, with the same masks the trainer uses. The value head
fits the shaped return of the decision, divided by the trainer's reward scale, so that PPO
starts with a value estimate and not with a zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

import numpy as np
import torch
from torch import nn

from slagents.learned.encoding import Spaces, command_triple
from slagents.learned.env import SquadLeaderEnv
from slagents.learned.league import write_snapshot
from slagents.learned.nets import NetConfig, Policy
from slagents.learned.ppo import PpoConfig, policy_device


@dataclass
class Demonstrations:
    """The decisions of the teachers, in the form the update reads."""

    board: list[np.ndarray] = field(default_factory=list)
    units: list[np.ndarray] = field(default_factory=list)
    scalars: list[np.ndarray] = field(default_factory=list)
    unit_mask: list[np.ndarray] = field(default_factory=list)
    action_mask: list[np.ndarray] = field(default_factory=list)
    target_mask: list[np.ndarray] = field(default_factory=list)
    unit: list[int] = field(default_factory=list)
    action: list[int] = field(default_factory=list)
    target: list[int] = field(default_factory=list)
    # The shaped return of each decision: what its side was paid after it, to the end of
    # the game. The value head fits it.
    value: list[float] = field(default_factory=list)
    player: list[int] = field(default_factory=list)
    games: int = 0
    results: dict[str, int] = field(default_factory=lambda: {"win": 0, "loss": 0, "draw": 0, "truncated": 0})

    def __len__(self) -> int:
        return len(self.unit)


def teacher_pairs(kinds: Sequence[str]) -> list[tuple[str, str]]:
    """Each ordered pair of the teacher kinds, self play included.

    A policy that copies v5 on the two sides and v6 on the two sides has seen each teacher
    attack and defend, and each one against the other.
    """
    return [(a, b) for a in kinds for b in kinds]


def collect_demonstrations(
    env: SquadLeaderEnv,
    make_teacher: Callable[[str, int, int], Any],
    kinds: Sequence[str],
    games: int,
    seed: int,
    on_game: Callable[[int, str, str, float], None] | None = None,
) -> Demonstrations:
    """Play `games` games of the teachers against each other and record each decision.

    `make_teacher(kind, seed, player)` builds one scripted agent. The pairs of teachers
    cycle over the games, and each game has a new seed. Each decision of each side goes
    in, because the policy plays the two sides (`--player both`).
    """
    data = Demonstrations()
    pairs = teacher_pairs(kinds)
    for game in range(games):
        kind_a, kind_b = pairs[game % len(pairs)]
        game_seed = seed + game
        teachers = {0: make_teacher(kind_a, game_seed, 0), 1: make_teacher(kind_b, game_seed, 1)}
        env.reset(seed=game_seed)
        paid: list[float] = []
        players: list[int] = []
        while True:
            agent = env.agent_selection
            if env.terminations[agent] or env.truncations[agent]:
                break
            player = env.player_of(agent)
            observation = env.observe(agent)
            legal = env.frame.by_id(teachers[player].select(env.state_, env.frame))
            triple = command_triple(legal.command, env.hexes)
            if triple not in env.groups:
                raise RuntimeError(f"the teacher's command {legal.command} has no triple in the action space")
            data.board.append(observation["board"])
            data.units.append(observation["units"])
            data.scalars.append(observation["scalars"])
            data.unit_mask.append(observation["unit_mask"])
            data.action_mask.append(observation["action_mask"])
            data.target_mask.append(env.target_mask(triple[0], triple[1]))
            data.unit.append(triple[0])
            data.action.append(triple[1])
            data.target.append(triple[2])
            data.player.append(player)
            paid.append(float(env._cumulative_rewards[agent]))
            players.append(player)
            env.step(triple)
        # The return of a decision is the total its side was paid at the end, less what it
        # had been paid before the decision.
        totals = {p: float(env._cumulative_rewards[env.agent_of(p)]) for p in (0, 1)}
        for before, player in zip(paid, players):
            data.value.append(totals[player] - before)
        assert len(data.value) == len(data), "each decision has a return"
        data.games += 1
        result = float(env.results[env.agent_of(0)])
        if env.truncations[env.agent_of(0)]:
            data.results["truncated"] += 1
        elif result > 0:
            data.results["win"] += 1
        elif result < 0:
            data.results["loss"] += 1
        else:
            data.results["draw"] += 1
        if on_game is not None:
            on_game(game, kind_a, kind_b, result)
    return data


@dataclass(frozen=True)
class FitConfig:
    """The numbers of the fit. A run artifact records them."""

    epochs: int = 5
    minibatch: int = 256
    learning_rate: float = 1e-3
    # The value error is in tens on the scaled return, and the cross entropy in units. A
    # coefficient of one half, as in PPO, lets the value error pull the shared trunk away
    # from the policy heads, so the fit weighs it lower.
    value_coefficient: float = 0.1
    max_gradient: float = 1.0
    holdout: float = 0.1
    reward_scale: float = PpoConfig.reward_scale

    def to_dict(self) -> dict[str, Any]:
        return {
            "epochs": self.epochs,
            "minibatch": self.minibatch,
            "learning_rate": self.learning_rate,
            "value_coefficient": self.value_coefficient,
            "max_gradient": self.max_gradient,
            "holdout": self.holdout,
            "reward_scale": self.reward_scale,
        }


class Tensors:
    """The demonstrations as tensors.

    They stay on the processor, and each minibatch moves to the policy's device. Four
    hundred games of scenario 1 are 300,000 decisions and nine gigabytes as float32, which
    is more than the card holds; the masks stay as bytes until the batch reads them.
    """

    def __init__(self, data: Demonstrations, spaces: Spaces, device: torch.device, scale: float) -> None:
        self.device = device
        self.spaces = spaces
        self.board = torch.from_numpy(np.stack(data.board))
        self.units = torch.from_numpy(np.stack(data.units))
        self.scalars = torch.from_numpy(np.stack(data.scalars))
        self.unit_mask = torch.from_numpy(np.stack(data.unit_mask).astype(np.int8))
        self.action_mask = torch.from_numpy(np.stack(data.action_mask).astype(np.int8).reshape(-1, spaces.units, spaces.actions))
        self.target_mask = torch.from_numpy(np.stack(data.target_mask).astype(np.int8))
        self.unit = torch.tensor(data.unit, dtype=torch.long)
        self.action = torch.tensor(data.action, dtype=torch.long)
        self.target = torch.tensor(data.target, dtype=torch.long)
        self.value = torch.tensor(data.value, dtype=torch.float32) / max(1e-9, scale)

    def __len__(self) -> int:
        return int(self.unit.shape[0])

    def batch(self, index: torch.Tensor) -> dict[str, torch.Tensor]:
        """One minibatch on the device, with the masks as float."""
        index = index.cpu()
        d = self.device
        return {
            "board": self.board[index].to(d),
            "units": self.units[index].to(d),
            "scalars": self.scalars[index].to(d),
            "unit_mask": self.unit_mask[index].to(d).float(),
            "action_mask": self.action_mask[index].to(d).float(),
            "target_mask": self.target_mask[index].to(d).float(),
            "unit": self.unit[index].to(d),
            "action": self.action[index].to(d),
            "target": self.target[index].to(d),
            "value": self.value[index].to(d),
        }

    def losses(self, policy: Policy, index: torch.Tensor, value_coefficient: float) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """The cross entropy of the teacher's triple, the value error, and their sum."""
        b = self.batch(index)
        log_prob, _, value = policy.evaluate(
            b["board"],
            b["units"],
            b["scalars"],
            b["unit_mask"],
            b["action_mask"],
            b["target_mask"],
            b["unit"],
            b["action"],
            b["target"],
        )
        cross_entropy = -log_prob.mean()
        value_loss = nn.functional.mse_loss(value, b["value"])
        return cross_entropy, value_loss, cross_entropy + value_coefficient * value_loss


def fit(
    policy: Policy,
    data: Demonstrations,
    config: FitConfig,
    spaces: Spaces,
    seed: int,
    on_epoch: Callable[[int, dict[str, float]], None] | None = None,
) -> list[dict[str, float]]:
    """Fit the policy to the demonstrations. Gives one row of losses for each epoch.

    A holdout of the decisions, by game order at the end, measures the cross entropy on
    decisions the fit did not see, so that a fit that memorises shows.
    """
    device = policy_device(policy)
    tensors = Tensors(data, spaces, device, config.reward_scale)
    n = len(tensors)
    held = int(n * config.holdout)
    train_index = torch.arange(0, n - held)
    held_index = torch.arange(n - held, n)
    optimizer = torch.optim.Adam(policy.parameters(), lr=config.learning_rate)
    generator = torch.Generator().manual_seed(seed)
    rows: list[dict[str, float]] = []
    for epoch in range(config.epochs):
        policy.train()
        order = train_index[torch.randperm(len(train_index), generator=generator)]
        totals = {"cross_entropy": 0.0, "value_loss": 0.0, "loss": 0.0, "batches": 0.0}
        for start in range(0, len(order), config.minibatch):
            batch = order[start : start + config.minibatch]
            cross_entropy, value_loss, loss = tensors.losses(policy, batch, config.value_coefficient)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), config.max_gradient)
            optimizer.step()
            totals["cross_entropy"] += float(cross_entropy.item())
            totals["value_loss"] += float(value_loss.item())
            totals["loss"] += float(loss.item())
            totals["batches"] += 1.0
        count = max(1.0, totals["batches"])
        row = {
            "epoch": float(epoch + 1),
            "cross_entropy": totals["cross_entropy"] / count,
            "value_loss": totals["value_loss"] / count,
            "loss": totals["loss"] / count,
        }
        row.update(holdout_losses(policy, tensors, held_index, config))
        rows.append(row)
        if on_epoch is not None:
            on_epoch(epoch + 1, row)
    policy.eval()
    return rows


def holdout_losses(policy: Policy, tensors: Tensors, index: torch.Tensor, config: FitConfig) -> dict[str, float]:
    """The cross entropy, the value error, and the accuracy of the argmax on the holdout."""
    if len(index) == 0:
        return {"holdout_cross_entropy": float("nan"), "holdout_value_loss": float("nan"), "holdout_accuracy": float("nan")}
    policy.eval()
    cross_total = 0.0
    value_total = 0.0
    correct = 0
    with torch.no_grad():
        for start in range(0, len(index), config.minibatch):
            batch = index[start : start + config.minibatch]
            cross_entropy, value_loss, _ = tensors.losses(policy, batch, config.value_coefficient)
            cross_total += float(cross_entropy.item()) * len(batch)
            value_total += float(value_loss.item()) * len(batch)
            correct += argmax_matches(policy, tensors, batch)
    n = float(len(index))
    return {
        "holdout_cross_entropy": cross_total / n,
        "holdout_value_loss": value_total / n,
        "holdout_accuracy": correct / n,
    }


def argmax_matches(policy: Policy, tensors: Tensors, index: torch.Tensor) -> int:
    """How many decisions of the batch the greedy policy gives as the teacher gave them."""
    b = tensors.batch(index)
    trunk, unit_embeddings = policy.encode(b["board"], b["units"], b["scalars"])
    unit = policy.unit_logits(trunk, unit_embeddings, b["unit_mask"]).argmax(dim=-1)
    a_mask = b["action_mask"].gather(1, unit.view(-1, 1, 1).expand(-1, 1, b["action_mask"].shape[-1])).squeeze(1)
    action = policy.action_logits(trunk, unit_embeddings, unit, a_mask).argmax(dim=-1)
    # The target mask of the batch is the teacher's, for the teacher's unit and action. A
    # decision with another unit or action is wrong already, so its target does not count.
    target = policy.target_logits(trunk, unit_embeddings, unit, action, b["target_mask"]).argmax(dim=-1)
    same = (unit == b["unit"]) & (action == b["action"]) & (target == b["target"])
    return int(same.sum().item())


def save(policy: Policy, path: Path, config: NetConfig, record: dict[str, Any]) -> Path:
    """The fitted policy as a training snapshot, so `sl-cli train --start-from` and `learned:` read it."""
    return write_snapshot(policy, path, 0, config, extra={"imitation": record})
