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

The fit is a cross entropy on the four heads: the negative log probability of the
teacher's command under the policy, with the same masks the trainer uses. The value head
fits the shaped return of the decision, divided by the trainer's reward scale, so that PPO
starts with a value estimate and not with a zero.

Each side has one label teacher. The scripted agents differ by side: on the front board
v5 wins the Russian attack 10 of 10 against v1 and v6 wins 3, and v6 holds the German
defence better than v5 (2026-09-16). A fit that copies v5 and v6 on the two sides gets two
answers for one state, and its accuracy stops at the share the two agree on. So the pool
of teachers plays the games, for the states, and the label of each decision is the command
of the label teacher of that side.

A policy that copies the teacher's decisions on the teacher's states drifts on its own
states, because one wrong command leads to a state the teacher never showed it. The
DAgger rounds (Ross, Gordon, and Bagnell, 2011) close that gap: the policy plays, the label
teacher of its side names the command at each state it reaches, the new decisions join the
old, and the fit runs again. The label teacher is a function of the state, so it can name
a command in any state, which is what makes the round possible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import numpy as np
import torch
from torch import nn

from slagents.learned.encoding import Spaces, command_index
from slagents.learned.env import SquadLeaderEnv
from slagents.learned.league import write_snapshot
from slagents.learned.nets import NetConfig, Policy
from slagents.learned.ppo import PpoConfig, choose, policy_device


FIELDS = (
    "board",
    "units",
    "scalars",
    "unit_mask",
    "action_mask",
    "target_mask",
    "option_mask",
    "unit",
    "action",
    "target",
    "option",
    "value",
    "player",
)


@dataclass
class GameBuffer:
    """The decisions of the game in play, one array or number for each decision."""

    board: list[np.ndarray] = field(default_factory=list)
    units: list[np.ndarray] = field(default_factory=list)
    scalars: list[np.ndarray] = field(default_factory=list)
    unit_mask: list[np.ndarray] = field(default_factory=list)
    action_mask: list[np.ndarray] = field(default_factory=list)
    target_mask: list[np.ndarray] = field(default_factory=list)
    option_mask: list[np.ndarray] = field(default_factory=list)
    unit: list[int] = field(default_factory=list)
    action: list[int] = field(default_factory=list)
    target: list[int] = field(default_factory=list)
    option: list[int] = field(default_factory=list)
    value: list[float] = field(default_factory=list)
    player: list[int] = field(default_factory=list)

    def __len__(self) -> int:
        return len(self.unit)

    def block(self) -> dict[str, np.ndarray]:
        """The game as one array for each field."""
        return {
            "board": np.stack(self.board),
            "units": np.stack(self.units),
            "scalars": np.stack(self.scalars),
            "unit_mask": np.stack(self.unit_mask),
            "action_mask": np.stack(self.action_mask),
            "target_mask": np.stack(self.target_mask),
            "option_mask": np.stack(self.option_mask),
            "unit": np.array(self.unit, dtype=np.int64),
            "action": np.array(self.action, dtype=np.int64),
            "target": np.array(self.target, dtype=np.int64),
            "option": np.array(self.option, dtype=np.int64),
            "value": np.array(self.value, dtype=np.float32),
            "player": np.array(self.player, dtype=np.int64),
        }


class Demonstrations:
    """The decisions of the teachers, in the form the update reads.

    The decisions are held as one block of arrays for each game, not one array for each
    decision. A collection of 900 games is 550,000 decisions, and as 3 million small
    arrays its release at the end of the command took the Windows heap fifteen minutes
    (`RtlFreeHeap`, one block at a time, 2026-09-16). As 900 blocks it is nothing.

    Each field reads as one array over every decision (`data.unit[i]`, `data.board[i]`),
    concatenated from the blocks when read.
    """

    def __init__(self) -> None:
        self.blocks: list[dict[str, np.ndarray]] = []
        self.games = 0
        self.results: dict[str, int] = {"win": 0, "loss": 0, "draw": 0, "truncated": 0}

    def __len__(self) -> int:
        return sum(int(block["unit"].shape[0]) for block in self.blocks)

    def add_game(self, buffer: GameBuffer) -> None:
        if len(buffer):
            self.blocks.append(buffer.block())

    def field(self, name: str) -> np.ndarray:
        if name not in FIELDS:
            raise KeyError(f"no field {name!r} in the demonstrations")
        if not self.blocks:
            return np.zeros((0,), dtype=np.float32)
        return np.concatenate([block[name] for block in self.blocks])

    def __getattr__(self, name: str) -> np.ndarray:
        # The fields as arrays over every decision. `__getattr__` runs only for a name that
        # is not an attribute, so `blocks`, `games`, and `results` come first.
        if name in FIELDS:
            return self.field(name)
        raise AttributeError(name)

    def extend(self, other: "Demonstrations") -> None:
        """The decisions of another collection after these, as a DAgger round adds its own."""
        self.blocks.extend(other.blocks)
        self.games += other.games
        for key, count in other.results.items():
            self.results[key] = self.results.get(key, 0) + count


def parse_labels(text: str) -> dict[int, str]:
    """`0=v5,1=v6` as the label teacher of each side."""
    out: dict[int, str] = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        side, _, kind = part.partition("=")
        if not kind or side.strip() not in ("0", "1"):
            raise ValueError(f"a label is <side>=<agent> with the side 0 or 1, not {part!r}")
        out[int(side)] = kind.strip()
    if set(out) != {0, 1}:
        raise ValueError(f"the labels must name the two sides, as 0=v5,1=v6, not {text!r}")
    return out


def _record(data: GameBuffer, env: SquadLeaderEnv, observation: dict[str, np.ndarray], key: tuple[int, int, int, int], player: int) -> None:
    data.board.append(observation["board"])
    data.units.append(observation["units"])
    data.scalars.append(observation["scalars"])
    data.unit_mask.append(observation["unit_mask"])
    data.action_mask.append(observation["action_mask"])
    data.target_mask.append(env.target_mask(key[0], key[1]))
    data.option_mask.append(env.option_mask(key[0], key[1], key[2]))
    data.unit.append(key[0])
    data.action.append(key[1])
    data.target.append(key[2])
    data.option.append(key[3])
    data.player.append(player)


def _teacher_key(teacher: Any, env: SquadLeaderEnv) -> tuple[int, int, int, int]:
    """The four parts of the command the teacher names. The option is that command, not the lowest id."""
    legal = env.frame.by_id(teacher.select(env.state_, env.frame))
    if legal is None:
        raise RuntimeError("the teacher gave an ID that is not in the frame")
    try:
        return command_index(legal, env.groups)
    except KeyError as exc:
        raise RuntimeError(f"the teacher's command {legal.command} has no key in the action space") from exc


def _close_game(data: Demonstrations, buffer: GameBuffer, env: SquadLeaderEnv, paid: list[float], players: list[int]) -> float:
    """The returns of the game's decisions, the game as one block, its result for player 0, and the count."""
    totals = {p: float(env._cumulative_rewards[env.agent_of(p)]) for p in (0, 1)}
    for before, player in zip(paid, players):
        buffer.value.append(totals[player] - before)
    assert len(buffer.value) == len(buffer), "each decision has a return"
    data.add_game(buffer)
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
    return result


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
    labels: Mapping[int, str] | None = None,
) -> Demonstrations:
    """Play `games` games of the teachers against each other and record each decision.

    `make_teacher(kind, seed, player)` builds one scripted agent. The pairs of teachers
    cycle over the games, and each game has a new seed. Each decision of each side goes
    in, because the policy plays the two sides (`--player both`).

    `labels` names the teacher whose command is the label of each side, as `{0: "v5",
    1: "v6"}`. Without it the acting teacher labels its own decision. With it the acting
    teacher plays and the label teacher of its side names the command the record holds,
    so the pool gives the states and one agent for each side gives the answers.
    """
    data = Demonstrations()
    pairs = teacher_pairs(kinds)
    for game in range(games):
        kind_a, kind_b = pairs[game % len(pairs)]
        played, result = play_demonstration(env, make_teacher, kind_a, kind_b, seed + game, labels)
        data.extend(played)
        if on_game is not None:
            on_game(game, kind_a, kind_b, result)
    return data


def play_demonstration(
    env: SquadLeaderEnv,
    make_teacher: Callable[[str, int, int], Any],
    kind_a: str,
    kind_b: str,
    game_seed: int,
    labels: Mapping[int, str] | None = None,
) -> tuple[Demonstrations, float]:
    """One game of two teachers, as `collect_demonstrations` plays it. Gives its decisions and the result."""
    data = Demonstrations()
    buffer = GameBuffer()
    actors = {0: make_teacher(kind_a, game_seed, 0), 1: make_teacher(kind_b, game_seed, 1)}
    labelers = dict(actors)
    if labels is not None:
        for player, kind in ((0, kind_a), (1, kind_b)):
            if labels[player] != kind:
                labelers[player] = make_teacher(labels[player], game_seed, player)
    env.reset(seed=game_seed)
    paid: list[float] = []
    players: list[int] = []
    while True:
        agent = env.agent_selection
        if env.terminations[agent] or env.truncations[agent]:
            break
        player = env.player_of(agent)
        observation = env.observe(agent)
        triple = _teacher_key(actors[player], env)
        label = triple if labelers[player] is actors[player] else _teacher_key(labelers[player], env)
        _record(buffer, env, observation, label, player)
        paid.append(float(env._cumulative_rewards[agent]))
        players.append(player)
        env.step(triple)
    # The return of a decision is the total its side was paid at the end, less what it
    # had been paid before the decision.
    return data, _close_game(data, buffer, env, paid, players)


def collect_corrections(
    env: SquadLeaderEnv,
    policy: Policy,
    make_teacher: Callable[[str, int, int], Any],
    labels: Mapping[int, str],
    opponents: Sequence[str],
    games: int,
    seed: int,
    generator: torch.Generator,
    on_game: Callable[[int, int, str, float], None] | None = None,
    mix: float = 0.0,
) -> Demonstrations:
    """One DAgger round: the policy plays, and the label teachers name the command at each state.

    The policy holds one side of each game, the other side in turn, against a scripted
    opponent from `opponents`, which cycle. Each decision of the two sides goes in with the
    label of the label teacher of that side, so the round adds the states the policy
    reaches and the answer the teacher gives there. The policy samples its command, because
    its argmax repeats a position and the environment ends the game there. With `mix`
    above zero the teacher's command is played in that share of the policy's decisions,
    which is the first rounds' schedule of the paper; the label is the teacher's in each
    case.

    `on_game(game, policy_side, opponent_kind, result)` gives the result for the policy's side.
    """
    data = Demonstrations()
    for game in range(games):
        side = game % 2
        kind = opponents[game % len(opponents)]
        played, result = play_correction(env, policy, make_teacher, labels, side, kind, seed + game, generator, mix)
        data.extend(played)
        if on_game is not None:
            on_game(game, side, kind, result)
    return data


def play_correction(
    env: SquadLeaderEnv,
    policy: Policy,
    make_teacher: Callable[[str, int, int], Any],
    labels: Mapping[int, str],
    side: int,
    kind: str,
    game_seed: int,
    generator: torch.Generator,
    mix: float = 0.0,
) -> tuple[Demonstrations, float]:
    """One game of a DAgger round: the policy on `side` against the teacher `kind`.

    Gives the decisions of the two sides with the label teachers' commands, and the result
    for the policy's side.
    """
    data = Demonstrations()
    buffer = GameBuffer()
    policy.eval()
    opponent = make_teacher(kind, game_seed, 1 - side)
    labelers = {player: make_teacher(labels[player], game_seed, player) for player in (0, 1)}
    env.reset(seed=game_seed)
    paid: list[float] = []
    players: list[int] = []
    while True:
        agent = env.agent_selection
        if env.terminations[agent] or env.truncations[agent]:
            break
        player = env.player_of(agent)
        observation = env.observe(agent)
        label = _teacher_key(labelers[player], env)
        if player == side:
            if mix > 0.0 and float(torch.rand((), generator=generator).item()) < mix:
                triple = label
            else:
                triple, _, _, _, _ = choose(policy, observation, env, generator)
        elif labels[player] == kind:
            # The opponent is the label teacher of its side, so the label is its command.
            triple = label
        else:
            triple = _teacher_key(opponent, env)
        _record(buffer, env, observation, label, player)
        paid.append(float(env._cumulative_rewards[agent]))
        players.append(player)
        env.step(triple)
    result = _close_game(data, buffer, env, paid, players)
    return data, result if side == 0 else -result


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
    # The weight of a decision whose label names no unit: `group_fire`, `end_phase`, and
    # `end_setup`, the decisions that stop a phase or fire a group. The decisions that
    # continue (add a unit, move a unit) outnumber them ten to one, and a fit at equal
    # weight fired a group at the teacher's moment in 2 of 93 states (2026-09-16). A
    # wrong "which unit first" costs little; a wrong "stop now" changes the whole phase.
    stop_weight: float = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "epochs": self.epochs,
            "minibatch": self.minibatch,
            "learning_rate": self.learning_rate,
            "value_coefficient": self.value_coefficient,
            "max_gradient": self.max_gradient,
            "holdout": self.holdout,
            "reward_scale": self.reward_scale,
            "stop_weight": self.stop_weight,
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
        # The board and the unit rows hold small fractions (a quarter, a third, a tenth), so
        # half precision keeps them to three decimals and halves the memory of a collection.
        self.board = torch.from_numpy(data.board).to(torch.float16)
        self.units = torch.from_numpy(data.units).to(torch.float16)
        self.scalars = torch.from_numpy(data.scalars)
        self.unit_mask = torch.from_numpy(data.unit_mask.astype(np.int8))
        self.action_mask = torch.from_numpy(data.action_mask.astype(np.int8).reshape(-1, spaces.units, spaces.actions))
        self.target_mask = torch.from_numpy(data.target_mask.astype(np.int8))
        self.option_mask = torch.from_numpy(data.option_mask.astype(np.int8))
        self.unit = torch.from_numpy(data.unit).to(torch.long)
        self.action = torch.from_numpy(data.action).to(torch.long)
        self.target = torch.from_numpy(data.target).to(torch.long)
        self.option = torch.from_numpy(data.option).to(torch.long)
        self.value = torch.from_numpy(data.value).to(torch.float32) / max(1e-9, scale)

    def __len__(self) -> int:
        return int(self.unit.shape[0])

    def batch(self, index: torch.Tensor) -> dict[str, torch.Tensor]:
        """One minibatch on the device, with the masks as float."""
        index = index.cpu()
        d = self.device
        return {
            "board": self.board[index].to(d).float(),
            "units": self.units[index].to(d).float(),
            "scalars": self.scalars[index].to(d),
            "unit_mask": self.unit_mask[index].to(d).float(),
            "action_mask": self.action_mask[index].to(d).float(),
            "target_mask": self.target_mask[index].to(d).float(),
            "option_mask": self.option_mask[index].to(d).float(),
            "unit": self.unit[index].to(d),
            "action": self.action[index].to(d),
            "target": self.target[index].to(d),
            "option": self.option[index].to(d),
            "value": self.value[index].to(d),
        }

    def losses(
        self, policy: Policy, index: torch.Tensor, value_coefficient: float, stop_weight: float = 1.0
    ) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        """The cross entropy of the teacher's command, the value error, and their sum.

        `stop_weight` weighs each decision whose label is in the slot of no unit, which
        is the decision that stops a phase or fires the group (`FitConfig.stop_weight`).
        """
        b = self.batch(index)
        log_prob, _, value = policy.evaluate(
            b["board"],
            b["units"],
            b["scalars"],
            b["unit_mask"],
            b["action_mask"],
            b["target_mask"],
            b["option_mask"],
            b["unit"],
            b["action"],
            b["target"],
            b["option"],
        )
        weights = torch.where(b["unit"] == 0, torch.full_like(log_prob, stop_weight), torch.ones_like(log_prob))
        cross_entropy = -(log_prob * weights).sum() / weights.sum()
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
            cross_entropy, value_loss, loss = tensors.losses(policy, batch, config.value_coefficient, config.stop_weight)
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
    option = policy.option_logits(trunk, unit_embeddings, unit, action, target, b["option_mask"]).argmax(dim=-1)
    same = (unit == b["unit"]) & (action == b["action"]) & (target == b["target"]) & (option == b["option"])
    return int(same.sum().item())


def save(policy: Policy, path: Path, config: NetConfig, record: dict[str, Any]) -> Path:
    """The fitted policy as a training snapshot, so `sl-cli train --start-from` and `learned:` read it."""
    return write_snapshot(policy, path, 0, config, extra={"imitation": record})
