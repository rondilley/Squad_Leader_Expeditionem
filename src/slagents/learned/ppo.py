"""PPO in raw torch for the composed command (FR-51).

The loop is the standard one: collect a rollout with the current policy, compute the
advantage with generalized advantage estimation, and take a few epochs of the clipped
objective on minibatches. Nothing here knows a rule of the game. Each legal command comes
from the environment, which asks the core.

Two properties of this game shape the code.

The reward arrives at the end of the game and nowhere else, because the core decides the
result from the victory conditions. So the value head has a long way to look, and the
discount stays at one for a game of five to eight turns.

The command has three parts and each part has its own mask. A step of the rollout keeps
the three masks it used, because the update must read the same distribution that the
rollout read.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

import numpy as np
import torch
from torch import nn

from slagents.learned.encoding import Spaces
from slagents.learned.env import SquadLeaderEnv
from slagents.learned.nets import NetConfig, Policy


@dataclass(frozen=True)
class PpoConfig:
    """The numbers of the algorithm. A run artifact records them."""

    steps_per_update: int = 512
    epochs: int = 4
    minibatch: int = 128
    clip: float = 0.2
    value_coefficient: float = 0.5
    entropy_coefficient: float = 0.01
    max_gradient: float = 0.5
    learning_rate: float = 3e-4
    discount: float = 1.0
    gae_lambda: float = 0.95

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps_per_update": self.steps_per_update,
            "epochs": self.epochs,
            "minibatch": self.minibatch,
            "clip": self.clip,
            "value_coefficient": self.value_coefficient,
            "entropy_coefficient": self.entropy_coefficient,
            "max_gradient": self.max_gradient,
            "learning_rate": self.learning_rate,
            "discount": self.discount,
            "gae_lambda": self.gae_lambda,
        }


@dataclass
class Rollout:
    """What one collection gives the update."""

    board: list[np.ndarray] = field(default_factory=list)
    units: list[np.ndarray] = field(default_factory=list)
    scalars: list[np.ndarray] = field(default_factory=list)
    unit_mask: list[np.ndarray] = field(default_factory=list)
    action_mask: list[np.ndarray] = field(default_factory=list)
    target_mask: list[np.ndarray] = field(default_factory=list)
    unit: list[int] = field(default_factory=list)
    action: list[int] = field(default_factory=list)
    target: list[int] = field(default_factory=list)
    log_prob: list[float] = field(default_factory=list)
    value: list[float] = field(default_factory=list)
    reward: list[float] = field(default_factory=list)
    done: list[float] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.unit)


def choose(
    policy: Policy,
    observation: dict[str, np.ndarray],
    env: SquadLeaderEnv,
    generator: torch.Generator,
    greedy: bool = False,
) -> tuple[tuple[int, int, int], float, float, np.ndarray]:
    """One composed command from the policy, with its log probability and the value."""
    spaces = env.spaces_record
    board = torch.from_numpy(observation["board"]).unsqueeze(0)
    units = torch.from_numpy(observation["units"]).unsqueeze(0)
    scalars = torch.from_numpy(observation["scalars"]).unsqueeze(0)
    unit_mask = torch.from_numpy(observation["unit_mask"].astype(np.float32)).unsqueeze(0)
    action_mask = torch.from_numpy(
        observation["action_mask"].astype(np.float32).reshape(spaces.units, spaces.actions)
    ).unsqueeze(0)
    with torch.no_grad():
        trunk, unit_embeddings = policy.encode(board, units, scalars)
        u_logits = policy.unit_logits(trunk, unit_embeddings, unit_mask)
        u_dist = torch.distributions.Categorical(logits=u_logits)
        unit = u_logits.argmax(dim=-1) if greedy else u_dist.sample()
        a_mask = action_mask[0, unit.item()].unsqueeze(0)
        a_logits = policy.action_logits(trunk, unit_embeddings, unit, a_mask)
        a_dist = torch.distributions.Categorical(logits=a_logits)
        action = a_logits.argmax(dim=-1) if greedy else a_dist.sample()
        target_bits = env.target_mask(int(unit.item()), int(action.item()))
        target_mask = torch.from_numpy(target_bits.astype(np.float32)).unsqueeze(0)
        t_logits = policy.target_logits(trunk, unit_embeddings, unit, action, target_mask)
        t_dist = torch.distributions.Categorical(logits=t_logits)
        target = t_logits.argmax(dim=-1) if greedy else t_dist.sample()
        log_prob = u_dist.log_prob(unit) + a_dist.log_prob(action) + t_dist.log_prob(target)
        value = policy.value(trunk)
    triple = (int(unit.item()), int(action.item()), int(target.item()))
    return triple, float(log_prob.item()), float(value.item()), target_bits


def collect(
    env: SquadLeaderEnv,
    policy: Policy,
    learner: int,
    opponent: Callable[[SquadLeaderEnv, dict[str, np.ndarray]], tuple[int, int, int]],
    steps: int,
    generator: torch.Generator,
    on_game_end: Callable[[float], None] | None = None,
) -> Rollout:
    """Play until the rollout has `steps` decisions of the learner.

    The opponent acts in the same environment. Its decisions are not in the rollout,
    because the learner did not make them.
    """
    rollout = Rollout()
    while len(rollout) < steps:
        agent = env.agent_selection
        player = env.player_of(agent)
        if env.terminations[agent] or env.truncations[agent]:
            reward = env._cumulative_rewards[env.agent_of(learner)]
            if on_game_end is not None:
                on_game_end(float(reward))
            if rollout.reward:
                rollout.reward[-1] = float(reward)
                rollout.done[-1] = 1.0
            env.reset(seed=env.seed_value + 1)
            continue
        observation = env.observe(agent)
        if player != learner:
            env.step(opponent(env, observation))
            continue
        triple, log_prob, value, target_bits = choose(policy, observation, env, generator)
        rollout.board.append(observation["board"])
        rollout.units.append(observation["units"])
        rollout.scalars.append(observation["scalars"])
        rollout.unit_mask.append(observation["unit_mask"])
        rollout.action_mask.append(observation["action_mask"])
        rollout.target_mask.append(target_bits)
        rollout.unit.append(triple[0])
        rollout.action.append(triple[1])
        rollout.target.append(triple[2])
        rollout.log_prob.append(log_prob)
        rollout.value.append(value)
        rollout.reward.append(0.0)
        rollout.done.append(0.0)
        env.step(triple)
    return rollout


def advantages(rollout: Rollout, config: PpoConfig, last_value: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Generalized advantage estimation over the learner's own decisions."""
    n = len(rollout)
    adv = np.zeros(n, dtype=np.float32)
    values = np.array(rollout.value, dtype=np.float32)
    rewards = np.array(rollout.reward, dtype=np.float32)
    dones = np.array(rollout.done, dtype=np.float32)
    running = 0.0
    for i in reversed(range(n)):
        next_value = last_value if i == n - 1 else values[i + 1]
        next_non_terminal = 1.0 - dones[i]
        delta = rewards[i] + config.discount * next_value * next_non_terminal - values[i]
        running = delta + config.discount * config.gae_lambda * next_non_terminal * running
        adv[i] = running
    return adv, adv + values


def update(policy: Policy, optimizer: torch.optim.Optimizer, rollout: Rollout, config: PpoConfig, spaces: Spaces) -> dict[str, float]:
    """One PPO update. Gives the losses, which a scalar log records (IR-07)."""
    adv, returns = advantages(rollout, config)
    board = torch.from_numpy(np.stack(rollout.board))
    units = torch.from_numpy(np.stack(rollout.units))
    scalars = torch.from_numpy(np.stack(rollout.scalars))
    unit_mask = torch.from_numpy(np.stack(rollout.unit_mask).astype(np.float32))
    action_mask = torch.from_numpy(
        np.stack(rollout.action_mask).astype(np.float32).reshape(-1, spaces.units, spaces.actions)
    )
    target_mask = torch.from_numpy(np.stack(rollout.target_mask).astype(np.float32))
    unit = torch.tensor(rollout.unit, dtype=torch.long)
    action = torch.tensor(rollout.action, dtype=torch.long)
    target = torch.tensor(rollout.target, dtype=torch.long)
    old_log_prob = torch.tensor(rollout.log_prob, dtype=torch.float32)
    advantage = torch.from_numpy(adv)
    if advantage.numel() > 1 and float(advantage.std()) > 1e-8:
        advantage = (advantage - advantage.mean()) / (advantage.std() + 1e-8)
    target_return = torch.from_numpy(returns)
    n = len(rollout)
    totals = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "loss": 0.0, "updates": 0.0}
    for _ in range(config.epochs):
        order = torch.randperm(n)
        for start in range(0, n, config.minibatch):
            batch = order[start : start + config.minibatch]
            log_prob, entropy, value = policy.evaluate(
                board[batch],
                units[batch],
                scalars[batch],
                unit_mask[batch],
                action_mask[batch],
                target_mask[batch],
                unit[batch],
                action[batch],
                target[batch],
            )
            ratio = torch.exp(log_prob - old_log_prob[batch])
            clipped = torch.clamp(ratio, 1.0 - config.clip, 1.0 + config.clip)
            policy_loss = -torch.min(ratio * advantage[batch], clipped * advantage[batch]).mean()
            value_loss = nn.functional.mse_loss(value, target_return[batch])
            entropy_mean = entropy.mean()
            loss = policy_loss + config.value_coefficient * value_loss - config.entropy_coefficient * entropy_mean
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), config.max_gradient)
            optimizer.step()
            totals["policy_loss"] += float(policy_loss.item())
            totals["value_loss"] += float(value_loss.item())
            totals["entropy"] += float(entropy_mean.item())
            totals["loss"] += float(loss.item())
            totals["updates"] += 1.0
    count = max(1.0, totals["updates"])
    return {
        "policy_loss": totals["policy_loss"] / count,
        "value_loss": totals["value_loss"] / count,
        "entropy": totals["entropy"] / count,
        "loss": totals["loss"] / count,
        "minibatches": totals["updates"],
    }


def random_opponent(env: SquadLeaderEnv, observation: dict[str, np.ndarray]) -> tuple[int, int, int]:
    """The opponent of the first rung of the ladder: a uniform legal command."""
    triples = list(env.groups)
    index = int(torch.randint(len(triples), (1,)).item())
    return triples[index]


def policy_opponent(policy: Policy, generator: torch.Generator) -> Callable[[SquadLeaderEnv, dict[str, np.ndarray]], tuple[int, int, int]]:
    """A snapshot of a policy as the opponent (FR-52)."""

    def act(env: SquadLeaderEnv, observation: dict[str, np.ndarray]) -> tuple[int, int, int]:
        triple, _, _, _ = choose(policy, observation, env, generator)
        return triple

    return act
