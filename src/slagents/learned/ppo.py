"""PPO in raw torch for the composed command (FR-51).

The loop is the standard one: collect a rollout with the current policy, compute the
advantage with generalized advantage estimation, and take a few epochs of the clipped
objective on minibatches. Nothing here knows a rule of the game. Each legal command comes
from the environment, which asks the core.

Two properties of this game shape the code.

The result of the game goes to the league, and the shaped reward of
`slagents.learned.reward` goes to the update. The core decides the result from the victory
conditions, and the shaped terms pay each decision for what came after it. The discount
stays at one by default for a game of five to eight turns.

The command has four parts and each part has its own mask. A step of the rollout keeps
the masks it used, because the update must read the same distribution that the rollout read.

A rollout ends at a decision of the learner and not after its last command. The opponent
plays on to the learner's next decision, what accrued on the way is paid to the last
decision, and the value of the state the learner then faces is the bootstrap of the
advantage. Before this the bootstrap was zero, so the last decisions of each rollout were
paid as if the game had ended there with nothing, and the reward of the opponent's stretch
between two rollouts was dropped (the first six runs of the ladder).

An update can hold the policy near an anchor: a frozen copy of the policy it started from,
as the one `sl-cli imitate` writes. The loss adds the KL divergence of the four heads from
the anchor's, times `anchor_kl`. A start from a copied policy is otherwise undone in the
first updates, because the clipped objective keeps the policy near the last rollout and
not near the start.

`collect_parallel` is `collect` over the worker pool of `slagents.learned.workers`: each
worker plays one game, the policy answers all of them in one forward pass, and the rollout
holds the steps of every worker with the worker of each step, so the advantage runs along
each worker's own sequence.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Sequence

import numpy as np
import torch
from torch import nn

from slagents.learned.encoding import Spaces, option_mask_for, target_mask_for
from slagents.learned.env import SquadLeaderEnv
from slagents.learned.nets import NetConfig, Policy


def resolve_device(name: str = "auto") -> torch.device:
    """The compute device. `auto` takes the GPU when torch reports one, and the CPU if not.

    The learned pipeline built every tensor on the CPU before this, so the RTX card did no
    work on a run (VIBE_HISTORY, 2026-09-10). A named device (`cuda`, `cpu`, `cuda:0`) forces
    the choice, and `auto` is the default the training command passes.
    """
    if name == "auto":
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")
    return torch.device(name)


def policy_device(policy: Policy) -> torch.device:
    """The device the policy's parameters live on. The rollout tensors move to it."""
    return next(policy.parameters()).device


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
    # The shaped reward pays a win one hundred, so the returns are in the hundreds and the
    # value loss is in the thousands, which drowns the policy loss. The update reads the
    # reward divided by this scale. The artifact and the log keep the reward as paid.
    reward_scale: float = 10.0
    # The weight of the KL divergence from the anchor policy, zero for no anchor.
    anchor_kl: float = 0.0
    # The first decisions of the run that train the value head alone, with the policy
    # fixed, zero for none (PIRLNav, https://arxiv.org/abs/2301.07302).
    value_warmup_steps: int = 0

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
            "reward_scale": self.reward_scale,
            "anchor_kl": self.anchor_kl,
            "value_warmup_steps": self.value_warmup_steps,
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
    option: list[int] = field(default_factory=list)
    option_mask: list[np.ndarray] = field(default_factory=list)
    log_prob: list[float] = field(default_factory=list)
    value: list[float] = field(default_factory=list)
    reward: list[float] = field(default_factory=list)
    done: list[float] = field(default_factory=list)
    # The side the learner holds when the next collection starts. It is the side given to
    # `collect` unless the learner changes sides at each new game.
    next_learner: int = 0
    # The value of the state the learner faces after its last decision here, or zero when
    # that decision ended the game. The advantage of the last decisions bootstraps on it.
    last_value: float = 0.0
    # The worker each step came from, when the rollout came from a pool, and the bootstrap
    # value of each worker's last step. A rollout of one environment leaves them empty.
    worker: list[int] = field(default_factory=list)
    last_values: dict[int, float] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self.unit)


def choose(
    policy: Policy,
    observation: dict[str, np.ndarray],
    env: SquadLeaderEnv,
    generator: torch.Generator,
    greedy: bool = False,
) -> tuple[tuple[int, int, int, int], float, float, np.ndarray, np.ndarray]:
    """One composed command from the policy, with its log probability and the value."""
    spaces = env.spaces_record
    device = policy_device(policy)
    board = torch.from_numpy(observation["board"]).unsqueeze(0).to(device)
    units = torch.from_numpy(observation["units"]).unsqueeze(0).to(device)
    scalars = torch.from_numpy(observation["scalars"]).unsqueeze(0).to(device)
    unit_mask = torch.from_numpy(observation["unit_mask"].astype(np.float32)).unsqueeze(0).to(device)
    action_mask = torch.from_numpy(
        observation["action_mask"].astype(np.float32).reshape(spaces.units, spaces.actions)
    ).unsqueeze(0).to(device)
    with torch.no_grad():
        trunk, unit_embeddings = policy.encode(board, units, scalars)
        u_logits = policy.unit_logits(trunk, unit_embeddings, unit_mask)
        u_dist = torch.distributions.Categorical(logits=u_logits)
        unit = u_logits.argmax(dim=-1) if greedy else _sample(u_dist, generator)
        a_mask = action_mask[0, unit.item()].unsqueeze(0)
        a_logits = policy.action_logits(trunk, unit_embeddings, unit, a_mask)
        a_dist = torch.distributions.Categorical(logits=a_logits)
        action = a_logits.argmax(dim=-1) if greedy else _sample(a_dist, generator)
        target_bits = env.target_mask(int(unit.item()), int(action.item()))
        target_mask = torch.from_numpy(target_bits.astype(np.float32)).unsqueeze(0).to(device)
        t_logits = policy.target_logits(trunk, unit_embeddings, unit, action, target_mask)
        t_dist = torch.distributions.Categorical(logits=t_logits)
        target = t_logits.argmax(dim=-1) if greedy else _sample(t_dist, generator)
        option_bits = env.option_mask(int(unit.item()), int(action.item()), int(target.item()))
        option_mask = torch.from_numpy(option_bits.astype(np.float32)).unsqueeze(0).to(device)
        o_logits = policy.option_logits(trunk, unit_embeddings, unit, action, target, option_mask)
        o_dist = torch.distributions.Categorical(logits=o_logits)
        option = o_logits.argmax(dim=-1) if greedy else _sample(o_dist, generator)
        log_prob = u_dist.log_prob(unit) + a_dist.log_prob(action) + t_dist.log_prob(target) + o_dist.log_prob(option)
        value = policy.value(trunk)
    quad = (int(unit.item()), int(action.item()), int(target.item()), int(option.item()))
    return quad, float(log_prob.item()), float(value.item()), target_bits, option_bits


def value_of(policy: Policy, observation: dict[str, np.ndarray]) -> float:
    """The value the policy gives one observation, for the bootstrap at a rollout's end."""
    device = policy_device(policy)
    board = torch.from_numpy(observation["board"]).unsqueeze(0).to(device)
    units = torch.from_numpy(observation["units"]).unsqueeze(0).to(device)
    scalars = torch.from_numpy(observation["scalars"]).unsqueeze(0).to(device)
    with torch.no_grad():
        trunk, _ = policy.encode(board, units, scalars)
        return float(policy.value(trunk).item())


def collect(
    env: SquadLeaderEnv,
    policy: Policy,
    learner: int,
    opponent: Callable[[SquadLeaderEnv, dict[str, np.ndarray]], tuple[int, int, int, int]],
    steps: int,
    generator: torch.Generator,
    on_game_end: Callable[[float], None] | None = None,
    alternate_sides: bool = False,
    next_opponent: Callable[[], Callable[[SquadLeaderEnv, dict[str, np.ndarray]], tuple[int, int, int, int]]] | None = None,
) -> Rollout:
    """Play until the rollout has `steps` decisions of the learner.

    `opponent` plays the game in progress. With `next_opponent`, each new game that
    starts in this collection takes its opponent from it, so a league member plays one
    whole game and no member takes over a game in its middle (L3). A game that goes on
    past the end of the rollout keeps its opponent: the caller gives the same one to the
    next collection.

    The opponent acts in the same environment. Its decisions are not in the rollout,
    because the learner did not make them. With `alternate_sides` the learner takes the
    other side at each new game, so one policy learns the attack and the defence, and the
    balanced evaluation of TC-18 measures a side the policy has played. The third 1 million
    step run trained the Russian side only, and as the German it cycled in the first turn.

    The rollout ends where the learner has its next decision, or where the game ended on
    the way there. In the first case `last_value` is the policy's value of that state and
    the environment waits at it, so the next collection starts with no gap. In the second
    case the game's end is paid to the last decision, `done` marks it, and the environment
    holds a new game.
    """
    rollout = Rollout(next_learner=learner)
    learner_agent = env.agent_of(learner)
    # The shaped reward accrues between two decisions of the learner, through the
    # opponent's commands as well. Each decision is paid what accrued after it.
    paid = float(env._cumulative_rewards[learner_agent])

    def pay_last() -> float:
        nonlocal paid
        total = float(env._cumulative_rewards[learner_agent])
        delta = total - paid
        paid = total
        if rollout.reward and rollout.done[-1] == 0.0:
            rollout.reward[-1] += delta
        return delta

    def advance() -> bool:
        """The opponent plays to the learner's next decision. True when the game ended first."""
        while True:
            agent = env.agent_selection
            if env.terminations[agent] or env.truncations[agent]:
                return True
            if env.player_of(agent) == learner:
                return False
            env.step(opponent(env, env.observe(agent)))

    def end_game() -> None:
        nonlocal paid, learner, learner_agent, opponent
        pay_last()
        if on_game_end is not None:
            on_game_end(float(env.results[learner_agent]))
        if rollout.reward:
            rollout.done[-1] = 1.0
        env.reset(seed=env.seed_value + 1)
        paid = 0.0
        if next_opponent is not None:
            opponent = next_opponent()
        if alternate_sides:
            learner = 1 - learner
            learner_agent = env.agent_of(learner)
            rollout.next_learner = learner

    while len(rollout) < steps:
        if advance():
            end_game()
            continue
        pay_last()
        observation = env.observe(learner_agent)
        quad, log_prob, value, target_bits, option_bits = choose(policy, observation, env, generator)
        rollout.board.append(observation["board"])
        rollout.units.append(observation["units"])
        rollout.scalars.append(observation["scalars"])
        rollout.unit_mask.append(observation["unit_mask"])
        rollout.action_mask.append(observation["action_mask"])
        rollout.target_mask.append(target_bits)
        rollout.option_mask.append(option_bits)
        rollout.unit.append(quad[0])
        rollout.action.append(quad[1])
        rollout.target.append(quad[2])
        rollout.option.append(quad[3])
        rollout.log_prob.append(log_prob)
        rollout.value.append(value)
        rollout.reward.append(0.0)
        rollout.done.append(0.0)
        env.step(quad)
    if advance():
        end_game()
        rollout.last_value = 0.0
    else:
        pay_last()
        rollout.last_value = value_of(policy, env.observe(learner_agent))
    return rollout


def advantages(rollout: Rollout, config: PpoConfig, last_value: float | None = None) -> tuple[np.ndarray, np.ndarray]:
    """Generalized advantage estimation over the learner's own decisions.

    The steps of a pool rollout are interleaved across the workers, so the estimate runs
    along each worker's own steps, and each worker's last step bootstraps on its own
    `last_values` entry. A rollout of one environment is one sequence, and its last step
    bootstraps on `last_value`, which is the rollout's own unless a caller gives one.
    """
    if last_value is None:
        last_value = rollout.last_value
    n = len(rollout)
    adv = np.zeros(n, dtype=np.float32)
    values = np.array(rollout.value, dtype=np.float32)
    rewards = np.array(rollout.reward, dtype=np.float32) / max(1e-9, config.reward_scale)
    dones = np.array(rollout.done, dtype=np.float32)
    sequences: dict[int, list[int]] = {}
    workers = rollout.worker if rollout.worker else [0] * n
    for i in range(n):
        sequences.setdefault(workers[i], []).append(i)
    for worker, steps in sequences.items():
        tail = rollout.last_values.get(worker, last_value) if rollout.last_values else last_value
        running = 0.0
        for k in reversed(range(len(steps))):
            i = steps[k]
            next_value = tail if k == len(steps) - 1 else values[steps[k + 1]]
            next_non_terminal = 1.0 - dones[i]
            delta = rewards[i] + config.discount * next_value * next_non_terminal - values[i]
            running = delta + config.discount * config.gae_lambda * next_non_terminal * running
            adv[i] = running
    return adv, adv + values


def choose_batch(
    policy: Policy,
    observations: Sequence[dict[str, np.ndarray]],
    legal: Sequence[Sequence[tuple[int, int, int, int]]],
    spaces: Spaces,
    generator: torch.Generator,
    greedy: bool = False,
) -> tuple[list[tuple[int, int, int, int]], list[float], list[float], list[np.ndarray], list[np.ndarray]]:
    """One composed command for each observation, in one forward pass of each head.

    `legal[i]` is the list of legal commands of observation `i`, as four-part keys, from
    which the target mask and the option mask of the sampled parts are built here, because
    the worker that holds the environment is in another process.
    """
    device = policy_device(policy)
    board = torch.from_numpy(np.stack([o["board"] for o in observations])).to(device)
    units = torch.from_numpy(np.stack([o["units"] for o in observations])).to(device)
    scalars = torch.from_numpy(np.stack([o["scalars"] for o in observations])).to(device)
    unit_mask = torch.from_numpy(np.stack([o["unit_mask"] for o in observations]).astype(np.float32)).to(device)
    action_mask = torch.from_numpy(
        np.stack([o["action_mask"] for o in observations]).astype(np.float32).reshape(-1, spaces.units, spaces.actions)
    ).to(device)
    with torch.no_grad():
        trunk, unit_embeddings = policy.encode(board, units, scalars)
        u_logits = policy.unit_logits(trunk, unit_embeddings, unit_mask)
        unit, u_log_prob = _pick(u_logits, greedy, generator)
        a_mask = action_mask.gather(1, unit.view(-1, 1, 1).expand(-1, 1, spaces.actions)).squeeze(1)
        a_logits = policy.action_logits(trunk, unit_embeddings, unit, a_mask)
        action, a_log_prob = _pick(a_logits, greedy, generator)
        unit_list = unit.tolist()
        action_list = action.tolist()
        # The mask helpers read each legal key once; a list serves as well as the dict of a frame.
        target_bits = [target_mask_for(legal[i], spaces, unit_list[i], action_list[i]) for i in range(len(observations))]
        target_mask = torch.from_numpy(np.stack(target_bits).astype(np.float32)).to(device)
        t_logits = policy.target_logits(trunk, unit_embeddings, unit, action, target_mask)
        target, t_log_prob = _pick(t_logits, greedy, generator)
        target_list = target.tolist()
        option_bits = [
            option_mask_for(legal[i], spaces, unit_list[i], action_list[i], target_list[i])
            for i in range(len(observations))
        ]
        option_mask = torch.from_numpy(np.stack(option_bits).astype(np.float32)).to(device)
        o_logits = policy.option_logits(trunk, unit_embeddings, unit, action, target, option_mask)
        option, o_log_prob = _pick(o_logits, greedy, generator)
        log_prob = u_log_prob + a_log_prob + t_log_prob + o_log_prob
        value = policy.value(trunk)
    log_probs = log_prob.tolist()
    if any(math.isnan(x) for x in log_probs):
        # The check that torch.distributions made of each head, once for the batch.
        raise ValueError("the policy gave a NaN log probability; the weights are not finite")
    quads = list(zip(unit_list, action_list, target_list, option.tolist()))
    return quads, log_probs, value.tolist(), target_bits, option_bits


# How long the parallel collection waits for more workers before it answers the ready ones.
GATHER_SECONDS = 0.002
# The pipes one `multiprocessing.connection.wait` call takes on Windows is 63
# (WaitForMultipleObjects). The farm gives the trainer more workers than that.
WAIT_LIMIT = 60


def wait_any(connections: Sequence[Any], timeout: float | None) -> list[Any]:
    """The connections with a message, as `multiprocessing.connection.wait`, for any count.

    For more than WAIT_LIMIT connections it looks at each group with no wait, and when no
    message is in, it waits a short time on one group and looks again.
    """
    from multiprocessing.connection import wait

    if len(connections) <= WAIT_LIMIT:
        return wait(connections, timeout=timeout)
    groups = [list(connections[i : i + WAIT_LIMIT]) for i in range(0, len(connections), WAIT_LIMIT)]
    deadline = None if timeout is None else time.monotonic() + timeout
    turn = 0
    while True:
        found = [c for group in groups for c in wait(group, timeout=0)]
        if found:
            return found
        if deadline is not None and time.monotonic() >= deadline:
            return []
        wait(groups[turn % len(groups)], timeout=GATHER_SECONDS)
        turn += 1


def _sample(distribution: torch.distributions.Categorical, generator: torch.Generator) -> torch.Tensor:
    """A sample of each row with the trainer's own generator, so a run repeats from its seed."""
    probs = distribution.probs.detach().cpu()
    return torch.multinomial(probs, 1, generator=generator).squeeze(-1).to(distribution.logits.device)


def _pick(logits: torch.Tensor, greedy: bool, generator: torch.Generator) -> tuple[torch.Tensor, torch.Tensor]:
    """The choice of each row of one head and its log probability, with no distribution
    object: `torch.distributions.Categorical` checked its arguments at each call, and that
    was a sixth of the time of `choose_batch` (2026-10-14). The sample uses the trainer's
    own generator on the processor, as `_sample` does, so a run repeats from its seed."""
    log_p = torch.log_softmax(logits, dim=-1)
    if greedy:
        choice = logits.argmax(dim=-1)
    else:
        choice = torch.multinomial(log_p.exp().cpu(), 1, generator=generator).squeeze(-1).to(logits.device)
    return choice, log_p.gather(1, choice.view(-1, 1)).squeeze(1)


def values_batch(policy: Policy, observations: Sequence[dict[str, np.ndarray]]) -> list[float]:
    """The value of each observation, for the bootstrap of each worker's last step."""
    if not observations:
        return []
    device = policy_device(policy)
    board = torch.from_numpy(np.stack([o["board"] for o in observations])).to(device)
    units = torch.from_numpy(np.stack([o["units"] for o in observations])).to(device)
    scalars = torch.from_numpy(np.stack([o["scalars"] for o in observations])).to(device)
    with torch.no_grad():
        trunk, _ = policy.encode(board, units, scalars)
        return policy.value(trunk).tolist()


def collect_parallel(
    pool: Any,
    policy: Policy,
    steps: int,
    generator: torch.Generator,
    next_member: Callable[[], tuple[tuple[str, ...], str]],
    next_seed: Callable[[], int],
    on_game_end: Callable[[str, float], None] | None = None,
    alternate_sides: bool = False,
    jump_start: Any = None,
) -> Rollout:
    """`collect` over a worker pool: each worker plays one game, and the policy answers all.

    `jump_start`, a `jumpstart.JumpStart`, gives each new game its guide and horizon, and
    it sees the result of each game that ended with the horizon the game started with.

    `next_member()` gives the spec and the name of the opponent of a new game, and
    `next_seed()` its seed. `on_game_end(member_name, result)` sees each game that ended.
    A worker whose game ends gets a new game at once, on the other side when
    `alternate_sides` is set, so every rollout holds the two sides. The rollout ends when
    it has `steps` decisions; each worker then waits at its next decision, whose value is
    the worker's bootstrap.

    The loop is not in lockstep. It answers the workers that are ready and lets the others
    play on, because an opponent's Movement Phase is dozens of its decisions in a row and
    a loop that waits for the slowest worker at each step runs at that worker's pace. A
    short wait gathers a larger batch when few are ready.

    A remote worker that stops leaves the pool (`WorkerPool.drop`, 2026-10-16). Its game
    does not count in the league, and its last step in the rollout bootstraps on the value
    of that step, because the state after it did not come.
    """

    from slagents.learned.workers import Worker, WorkerDied

    rollout = Rollout()
    workers: list[Worker] = pool.workers
    by_connection = {w.connection: w for w in workers}
    # The workers a message went to whose answer is not in yet, and the workers with a
    # decision that waits for a command.
    awaiting: set[Worker] = set()
    ready: list[Worker] = []
    # The bootstrap of each worker that left the pool in this rollout.
    lost_tails: dict[int, float] = {}

    def lose(worker: Worker, error: WorkerDied) -> None:
        pool.drop(worker, error)
        awaiting.discard(worker)
        if worker in ready:
            ready.remove(worker)
        if worker.steps:
            lost_tails[worker.index] = rollout.value[worker.steps[-1]]

    def start(worker: Worker) -> None:
        spec, name = next_member()
        guide = jump_start.next() if jump_start is not None else None
        try:
            pool.reset(worker, spec, name, worker.learner, next_seed(), guide)
        except WorkerDied as error:
            lose(worker, error)
            return
        awaiting.add(worker)

    def settle(worker: Worker, decision: Any) -> None:
        """One answer from a worker: the reward of its last step, and the end of its game."""
        if worker.steps:
            rollout.reward[worker.steps[-1]] += decision.reward_delta
        if decision.ended:
            if on_game_end is not None:
                on_game_end(worker.member_name, decision.result)
            if jump_start is not None:
                jump_start.record(worker.guide_turns, decision.result)
            if worker.steps:
                rollout.done[worker.steps[-1]] = 1.0
            if alternate_sides:
                worker.learner = 1 - worker.learner
            start(worker)
        else:
            ready.append(worker)

    def receive(block: bool) -> None:
        """The answers that are in, or the next one when `block` is set."""
        if not awaiting:
            return
        timeout = None if block else GATHER_SECONDS
        for connection in wait_any([w.connection for w in awaiting], timeout=timeout):
            worker = by_connection[connection]
            awaiting.discard(worker)
            try:
                decision = pool.receive(worker)
            except WorkerDied as error:
                lose(worker, error)
                continue
            settle(worker, decision)

    # The steps a worker recorded belong to the rollout before this one.
    for w in list(workers):
        w.steps = []
        if w.pending is None:
            start(w)
        elif w.pending.ended:
            start(w)
        else:
            ready.append(w)
    while len(rollout) < steps:
        receive(block=not ready)
        if not ready:
            continue
        batch = ready[: steps - len(rollout)]
        del ready[: len(batch)]
        observations = [w.pending.observation for w in batch]
        legal = [w.pending.legal for w in batch]
        quads, log_probs, values, target_bits, option_bits = choose_batch(policy, observations, legal, pool.spaces, generator)
        for w, quad, log_prob, value, bits, options in zip(batch, quads, log_probs, values, target_bits, option_bits):
            observation = w.pending.observation
            rollout.board.append(observation["board"])
            rollout.units.append(observation["units"])
            rollout.scalars.append(observation["scalars"])
            rollout.unit_mask.append(observation["unit_mask"])
            rollout.action_mask.append(observation["action_mask"])
            rollout.target_mask.append(bits)
            rollout.option_mask.append(options)
            rollout.unit.append(quad[0])
            rollout.action.append(quad[1])
            rollout.target.append(quad[2])
            rollout.option.append(quad[3])
            rollout.log_prob.append(log_prob)
            rollout.value.append(value)
            rollout.reward.append(0.0)
            rollout.done.append(0.0)
            rollout.worker.append(w.index)
            w.steps.append(len(rollout) - 1)
            try:
                pool.act(w, quad)
            except WorkerDied as error:
                lose(w, error)
                continue
            awaiting.add(w)
    # Each worker's answer to its last command, so its last step has its reward, and the
    # value of the state it waits at, which is its bootstrap.
    while awaiting:
        receive(block=True)
    tails = values_batch(policy, [w.pending.observation for w in workers])
    rollout.last_values = {w.index: tail for w, tail in zip(workers, tails)}
    rollout.last_values.update(lost_tails)
    return rollout


def update(
    policy: Policy,
    optimizer: torch.optim.Optimizer,
    rollout: Rollout,
    config: PpoConfig,
    spaces: Spaces,
    anchor: Policy | None = None,
    value_only: bool = False,
) -> dict[str, float]:
    """One PPO update. Gives the losses, which a scalar log records (IR-07).

    `anchor` is the frozen policy the KL term of `config.anchor_kl` holds this one near.

    `value_only` is the warm-up of the value head. A policy from imitation has a value head
    fitted to the returns of the teachers' games, not to its own, so its first advantages
    are noise, and the first policy updates follow that noise away from the clone. The
    warm-up fits the value head to the returns of the policy's own rollouts first. The
    trunk is shared with the policy heads, so the warm-up reads it with no gradient, and
    only the value head changes. The policy then plays the same commands as before.
    """
    if config.anchor_kl > 0.0 and anchor is None:
        raise ValueError("anchor_kl is above zero and the update has no anchor policy")
    adv, returns = advantages(rollout, config)
    device = policy_device(policy)
    board = torch.from_numpy(np.stack(rollout.board)).to(device)
    units = torch.from_numpy(np.stack(rollout.units)).to(device)
    scalars = torch.from_numpy(np.stack(rollout.scalars)).to(device)
    unit_mask = torch.from_numpy(np.stack(rollout.unit_mask).astype(np.float32)).to(device)
    action_mask = torch.from_numpy(
        np.stack(rollout.action_mask).astype(np.float32).reshape(-1, spaces.units, spaces.actions)
    ).to(device)
    target_mask = torch.from_numpy(np.stack(rollout.target_mask).astype(np.float32)).to(device)
    option_mask = torch.from_numpy(np.stack(rollout.option_mask).astype(np.float32)).to(device)
    unit = torch.tensor(rollout.unit, dtype=torch.long, device=device)
    action = torch.tensor(rollout.action, dtype=torch.long, device=device)
    target = torch.tensor(rollout.target, dtype=torch.long, device=device)
    option = torch.tensor(rollout.option, dtype=torch.long, device=device)
    old_log_prob = torch.tensor(rollout.log_prob, dtype=torch.float32, device=device)
    advantage = torch.from_numpy(adv).to(device)
    if advantage.numel() > 1 and float(advantage.std()) > 1e-8:
        advantage = (advantage - advantage.mean()) / (advantage.std() + 1e-8)
    target_return = torch.from_numpy(returns).to(device)
    n = len(rollout)
    totals = {"policy_loss": 0.0, "value_loss": 0.0, "entropy": 0.0, "anchor_kl": 0.0, "loss": 0.0, "updates": 0.0}
    for _ in range(config.epochs):
        order = torch.randperm(n, device=device)
        for start in range(0, n, config.minibatch):
            batch = order[start : start + config.minibatch]
            if value_only:
                with torch.no_grad():
                    trunk, _ = policy.encode(board[batch], units[batch], scalars[batch])
                value_loss = nn.functional.mse_loss(policy.value(trunk), target_return[batch])
                loss = config.value_coefficient * value_loss
                optimizer.zero_grad(set_to_none=True)
                loss.backward()
                nn.utils.clip_grad_norm_(policy.value_head.parameters(), config.max_gradient)
                optimizer.step()
                totals["value_loss"] += float(value_loss.item())
                totals["loss"] += float(loss.item())
                totals["updates"] += 1.0
                continue
            parts = (
                board[batch],
                units[batch],
                scalars[batch],
                unit_mask[batch],
                action_mask[batch],
                target_mask[batch],
                option_mask[batch],
                unit[batch],
                action[batch],
                target[batch],
            )
            u_logits, a_logits, t_logits, o_logits, value = policy.head_logits(*parts)
            log_prob, entropy = log_prob_and_entropy(
                u_logits, a_logits, t_logits, o_logits, unit[batch], action[batch], target[batch], option[batch]
            )
            ratio = torch.exp(log_prob - old_log_prob[batch])
            clipped = torch.clamp(ratio, 1.0 - config.clip, 1.0 + config.clip)
            policy_loss = -torch.min(ratio * advantage[batch], clipped * advantage[batch]).mean()
            value_loss = nn.functional.mse_loss(value, target_return[batch])
            entropy_mean = entropy.mean()
            loss = policy_loss + config.value_coefficient * value_loss - config.entropy_coefficient * entropy_mean
            kl_mean = torch.zeros((), device=device)
            if anchor is not None and config.anchor_kl > 0.0:
                with torch.no_grad():
                    anchor_u, anchor_a, anchor_t, anchor_o, _ = anchor.head_logits(*parts)
                kl_mean = anchor_divergence(
                    u_logits, a_logits, t_logits, o_logits, anchor_u, anchor_a, anchor_t, anchor_o
                ).mean()
                loss = loss + config.anchor_kl * kl_mean
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            nn.utils.clip_grad_norm_(policy.parameters(), config.max_gradient)
            optimizer.step()
            totals["policy_loss"] += float(policy_loss.item())
            totals["value_loss"] += float(value_loss.item())
            totals["entropy"] += float(entropy_mean.item())
            totals["anchor_kl"] += float(kl_mean.item())
            totals["loss"] += float(loss.item())
            totals["updates"] += 1.0
    count = max(1.0, totals["updates"])
    return {
        "policy_loss": totals["policy_loss"] / count,
        "value_loss": totals["value_loss"] / count,
        "entropy": totals["entropy"] / count,
        "anchor_kl": totals["anchor_kl"] / count,
        "loss": totals["loss"] / count,
        "minibatches": totals["updates"],
        "value_only": 1.0 if value_only else 0.0,
    }


def log_prob_and_entropy(
    u_logits: torch.Tensor,
    a_logits: torch.Tensor,
    t_logits: torch.Tensor,
    o_logits: torch.Tensor,
    unit: torch.Tensor,
    action: torch.Tensor,
    target: torch.Tensor,
    option: torch.Tensor,
) -> tuple[torch.Tensor, torch.Tensor]:
    """The log probability of the composed command and the entropy of the four heads."""
    u_dist = torch.distributions.Categorical(logits=u_logits)
    a_dist = torch.distributions.Categorical(logits=a_logits)
    t_dist = torch.distributions.Categorical(logits=t_logits)
    o_dist = torch.distributions.Categorical(logits=o_logits)
    log_prob = u_dist.log_prob(unit) + a_dist.log_prob(action) + t_dist.log_prob(target) + o_dist.log_prob(option)
    entropy = u_dist.entropy() + a_dist.entropy() + t_dist.entropy() + o_dist.entropy()
    return log_prob, entropy


def anchor_divergence(
    u_logits: torch.Tensor,
    a_logits: torch.Tensor,
    t_logits: torch.Tensor,
    o_logits: torch.Tensor,
    anchor_u: torch.Tensor,
    anchor_a: torch.Tensor,
    anchor_t: torch.Tensor,
    anchor_o: torch.Tensor,
) -> torch.Tensor:
    """The KL divergence of the four heads from the anchor's, for each row of the batch.

    The two policies read the same masks, so an impossible command has probability zero
    on the two sides and adds nothing. The sum runs on the log-softmax of the two, and not
    on `torch.distributions.kl_divergence`, which reads infinity where the anchor's
    probability of a legal command underflows to zero in float32 and then cuts the
    gradient of that entry (the first pooled run, 2026-09-16).
    """
    total = torch.zeros(u_logits.shape[0], device=u_logits.device)
    for mine, theirs in ((u_logits, anchor_u), (a_logits, anchor_a), (t_logits, anchor_t), (o_logits, anchor_o)):
        log_p = torch.log_softmax(mine, dim=-1)
        log_q = torch.log_softmax(theirs, dim=-1)
        p = log_p.exp()
        total = total + torch.where(p > 0, p * (log_p - log_q), torch.zeros_like(p)).sum(dim=-1)
    return total


def random_opponent(env: SquadLeaderEnv, observation: dict[str, np.ndarray]) -> tuple[int, int, int, int]:
    """The opponent of the first rung of the ladder: a uniform legal command."""
    quads = list(env.choices)
    index = int(torch.randint(len(quads), (1,)).item())
    return quads[index]


def policy_opponent(policy: Policy, generator: torch.Generator) -> Callable[[SquadLeaderEnv, dict[str, np.ndarray]], tuple[int, int, int, int]]:
    """A snapshot of a policy as the opponent (FR-52)."""

    def act(env: SquadLeaderEnv, observation: dict[str, np.ndarray]) -> tuple[int, int, int, int]:
        quad, _, _, _, _ = choose(policy, observation, env, generator)
        return quad

    return act
