"""Parallel collection: worker processes hold the environments, one process holds the policy.

One environment with one opponent gives the trainer 30 to 300 decisions a second, and
most of a decision is the core and the scripted opponent on one core, plus a forward pass
of the policy for a batch of one, which on the GPU costs more than the pass itself
(2026-09-16: 7.6 ms on the card against 2.8 ms on the processor). A game of scenario 1 is
about 600 decisions, so 1 million steps of the ladder were an hour or two, and the 10
million rung was days.

The split here: each worker process owns one environment, its opponent, and the seed of
its games. It plays the opponent's commands itself and sends the trainer the observation
at each decision of the learner, with the legal triples of that state and the reward that
accrued since the last one. The trainer batches the observations of every worker into one
forward pass, samples one composed command for each, and sends them back. The workers run
in parallel on the cores, and the card sees one batch and not sixteen batches of one.

The worker holds a rule no more than the environment does: it builds the engine, the
environment, and the scripted agents by name, and it asks the core through them. The
policy never leaves the trainer's process, except as a snapshot file a worker loads as an
opponent (FR-52), which it runs on the processor.

The protocol is small. The trainer sends `("reset", member_spec, learner_side, seed)` or
`("act", triple)` or `("stop",)`. The worker answers each of the first two with
`("decision", observation, legal_triples, reward_delta, ended, result)`. When `ended` is
true the observation is the last state's, the delta holds the end reward, and the trainer
sends the next reset. A member spec is `("random",)`, `("scripted", kind)`, or
`("snapshot", path)`.
"""

from __future__ import annotations

import multiprocessing as mp
from dataclasses import dataclass, field
from multiprocessing.connection import Connection
from typing import Any, Callable, Sequence

import numpy as np

MemberSpec = tuple[str, ...]


@dataclass
class Decision:
    """What a worker sends at each decision of the learner, or at the end of the game."""

    observation: dict[str, np.ndarray]
    legal: list[tuple[int, int, int]]
    reward_delta: float
    ended: bool
    result: float


def worker_main(connection: Connection, scenario: str, index: int, seed: int, max_commands: int) -> None:
    """The loop of one worker process. It answers each message until `stop`."""
    import torch

    from slagents.learned.env import make_env
    from slcli.play import build_engine, make_agent

    torch.set_num_threads(1)
    engine = build_engine(scenario)
    env = make_env(engine, seed=seed, max_commands=max_commands)
    learner = 0
    opponents: dict[MemberSpec, Callable[[], tuple[int, int, int]]] = {}
    generator = torch.Generator().manual_seed(seed + index)

    def scripted(kind: str) -> Callable[[], tuple[int, int, int]]:
        from slcli.train import agent_triple

        agents = {player: make_agent(kind, engine, seed, player) for player in (0, 1)}
        return lambda: agent_triple(agents[env.frame.player], env)

    def random_act() -> tuple[int, int, int]:
        triples = list(env.groups)
        return triples[int(torch.randint(len(triples), (1,), generator=generator).item())]

    def snapshot(path: str) -> Callable[[], tuple[int, int, int]]:
        from slagents.learned.agent import load_policy
        from slagents.learned.ppo import choose

        policy = load_policy(path)
        return lambda: choose(policy, env.observe(env.agent_selection), env, generator)[0]

    def opponent_of(spec: MemberSpec) -> Callable[[], tuple[int, int, int]]:
        if spec not in opponents:
            if spec[0] == "random":
                opponents[spec] = random_act
            elif spec[0] == "scripted":
                opponents[spec] = scripted(spec[1])
            elif spec[0] == "snapshot":
                opponents[spec] = snapshot(spec[1])
            else:
                raise ValueError(f"unknown member spec {spec!r}")
        return opponents[spec]

    opponent = random_act
    paid = 0.0

    def advance() -> Decision:
        """The opponent plays to the learner's next decision, or the game ends first."""
        nonlocal paid
        agent_name = env.agent_of(learner)
        while True:
            agent = env.agent_selection
            if env.terminations[agent] or env.truncations[agent]:
                ended = True
                break
            if env.player_of(agent) == learner:
                ended = False
                break
            env.step(opponent())
        total = float(env._cumulative_rewards[agent_name])
        delta = total - paid
        paid = total
        result = float(env.results[agent_name]) if ended else 0.0
        return Decision(env.observe(agent_name), list(env.groups), delta, ended, result)

    while True:
        message = connection.recv()
        kind = message[0]
        if kind == "stop":
            connection.close()
            return
        if kind == "reset":
            _, spec, learner, game_seed = message
            opponent = opponent_of(tuple(spec))
            env.reset(seed=int(game_seed))
            paid = 0.0
            # What accrues before the learner's first decision belongs to no decision.
            decision = advance()
            paid = float(env._cumulative_rewards[env.agent_of(learner)])
            decision.reward_delta = 0.0
            connection.send(decision)
        elif kind == "act":
            env.step(tuple(int(x) for x in message[1]))
            connection.send(advance())
        else:
            raise ValueError(f"unknown message {kind!r}")


@dataclass(eq=False)
class Worker:
    """One worker process and what the trainer knows about its game.

    Identity is the worker itself (`eq=False`), so a set of workers holds each one once.
    """

    index: int
    process: Any
    connection: Connection
    learner: int = 0
    spec: MemberSpec = ("random",)
    member_name: str = "random"
    pending: Decision | None = None
    # The steps of the game in progress that are in the rollout being built, as indexes.
    steps: list[int] = field(default_factory=list)


class WorkerPool:
    """The worker processes of one training run."""

    def __init__(self, scenario: str, workers: int, seed: int, max_commands: int, spaces: Any) -> None:
        from slcli.worker_limit import limit_workers

        workers = limit_workers(workers)
        context = mp.get_context("spawn")
        # The sizes of the three heads, which the batched choice reads for its masks.
        self.spaces = spaces
        self.workers: list[Worker] = []
        for index in range(workers):
            ours, theirs = context.Pipe()
            process = context.Process(
                target=worker_main,
                args=(theirs, scenario, index, seed + index * 1_000_003, max_commands),
                daemon=True,
                name=f"sl-worker-{index}",
            )
            process.start()
            theirs.close()
            self.workers.append(Worker(index=index, process=process, connection=ours))

    def __len__(self) -> int:
        return len(self.workers)

    def reset(self, worker: Worker, spec: MemberSpec, member_name: str, learner: int, seed: int) -> None:
        worker.spec = spec
        worker.member_name = member_name
        worker.learner = learner
        worker.steps = []
        worker.connection.send(("reset", spec, learner, seed))

    def act(self, worker: Worker, triple: tuple[int, int, int]) -> None:
        worker.connection.send(("act", triple))

    def receive(self, worker: Worker) -> Decision:
        decision = worker.connection.recv()
        worker.pending = decision
        return decision

    def close(self) -> None:
        for worker in self.workers:
            try:
                worker.connection.send(("stop",))
            except (OSError, ValueError):
                pass
        for worker in self.workers:
            worker.process.join(timeout=10.0)
            if worker.process.is_alive():
                worker.process.terminate()
            worker.connection.close()

    def __enter__(self) -> "WorkerPool":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


# ------------------------------------------------------------ the imitation games

# What one process of the imitation pool holds: its engine, its environment, and the
# policy of the round, built once by `_init_imitation` and read by each game.
_imitation: dict[str, Any] = {}


def _init_imitation(scenario: str, max_commands: int, policy_state: dict | None, net: dict | None) -> None:
    import torch

    from slagents.learned.env import make_env
    from slagents.learned.nets import NetConfig, Policy
    from slcli.play import build_engine

    torch.set_num_threads(1)
    engine = build_engine(scenario)
    env = make_env(engine, seed=1, max_commands=max_commands)
    policy = None
    if policy_state is not None:
        policy = Policy(env.spaces_record, NetConfig(**net))
        policy.load_state_dict(policy_state)
        policy.eval()
    _imitation.update(engine=engine, env=env, policy=policy)


def _make_teacher(kind: str, game_seed: int, player: int) -> Any:
    from slcli.play import make_agent

    return make_agent(kind, _imitation["engine"], game_seed, player)


def _demonstration_game(args: tuple) -> tuple[Any, float]:
    from slagents.learned.imitate import play_demonstration

    kind_a, kind_b, game_seed, labels = args
    return play_demonstration(_imitation["env"], _make_teacher, kind_a, kind_b, game_seed, labels)


def _correction_game(args: tuple) -> tuple[Any, float]:
    import torch

    from slagents.learned.imitate import play_correction

    labels, side, kind, game_seed, mix = args
    generator = torch.Generator().manual_seed(game_seed)
    return play_correction(_imitation["env"], _imitation["policy"], _make_teacher, labels, side, kind, game_seed, generator, mix)


def demonstrations_parallel(
    scenario: str,
    kinds: Sequence[str],
    games: int,
    seed: int,
    workers: int,
    max_commands: int,
    labels: Any = None,
    on_game: Callable[[int, str, str, float], None] | None = None,
) -> Any:
    """`imitate.collect_demonstrations` over a process pool, one game for each task.

    The games come back in their order, so the collection is the same as the one-process
    one with the same seed, game for game.
    """
    from slagents.learned.imitate import Demonstrations, teacher_pairs

    pairs = teacher_pairs(kinds)
    tasks = [(pairs[game % len(pairs)][0], pairs[game % len(pairs)][1], seed + game, labels) for game in range(games)]
    data = Demonstrations()
    from slcli.worker_limit import limit_workers

    workers = limit_workers(workers)
    context = mp.get_context("spawn")
    with context.Pool(workers, initializer=_init_imitation, initargs=(scenario, max_commands, None, None)) as pool:
        for game, (played, result) in enumerate(pool.imap(_demonstration_game, tasks)):
            data.extend(played)
            if on_game is not None:
                on_game(game, tasks[game][0], tasks[game][1], result)
    return data


def corrections_parallel(
    scenario: str,
    policy: Any,
    labels: Any,
    opponents: Sequence[str],
    games: int,
    seed: int,
    workers: int,
    max_commands: int,
    mix: float = 0.0,
    on_game: Callable[[int, int, str, float], None] | None = None,
) -> Any:
    """`imitate.collect_corrections` over a process pool. Each process holds a copy of the policy on the processor."""
    from slagents.learned.imitate import Demonstrations

    state = {k: v.detach().cpu() for k, v in policy.state_dict().items()}
    tasks = [(labels, game % 2, opponents[game % len(opponents)], seed + game, mix) for game in range(games)]
    data = Demonstrations()
    from slcli.worker_limit import limit_workers

    workers = limit_workers(workers)
    context = mp.get_context("spawn")
    with context.Pool(workers, initializer=_init_imitation, initargs=(scenario, max_commands, state, policy.config.to_dict())) as pool:
        for game, (played, result) in enumerate(pool.imap(_correction_game, tasks)):
            data.extend(played)
            if on_game is not None:
                on_game(game, tasks[game][1], tasks[game][2], result)
    return data


def _evaluation_game(args: tuple) -> tuple[float, bool, bool]:
    """One game of the policy, as the agent a tournament plays, against one member."""
    from slagents.learned.agent import LearnedAgent
    from slcli.play import make_agent
    from slcli.train import agent_triple

    spec, learner_side, game_seed = args
    env = _imitation["env"]
    engine = _imitation["engine"]
    learner = LearnedAgent.from_policy(engine, _imitation["policy"])
    if spec[0] == "random":
        opponent = make_agent("random", engine, game_seed, 1 - learner_side)
    elif spec[0] == "scripted":
        opponent = make_agent(spec[1], engine, game_seed, 1 - learner_side)
    else:
        raise ValueError(f"the evaluation plays no member of spec {spec!r}")
    env.reset(seed=game_seed)
    while True:
        agent = env.agent_selection
        if env.terminations[agent] or env.truncations[agent]:
            learner_agent = env.agent_of(learner_side)
            return float(env.results[learner_agent]), bool(env.truncations[learner_agent]), bool(env.repeated)
        actor = learner if env.player_of(agent) == learner_side else opponent
        env.step(agent_triple(actor, env))


def evaluation_parallel(
    scenario: str,
    policy: Any,
    tasks: Sequence[tuple[MemberSpec, int, int]],
    workers: int,
    max_commands: int,
) -> list[tuple[float, bool, bool]]:
    """The games of `tasks` (member spec, learner side, seed) over a process pool, in their order.

    Each process holds a copy of the policy on the processor and plays through
    `LearnedAgent`, so the result is the one the one-process evaluation gives.
    """
    state = {k: v.detach().cpu() for k, v in policy.state_dict().items()}
    from slcli.worker_limit import limit_workers

    workers = limit_workers(workers)
    context = mp.get_context("spawn")
    with context.Pool(workers, initializer=_init_imitation, initargs=(scenario, max_commands, state, policy.config.to_dict())) as pool:
        return list(pool.imap(_evaluation_game, list(tasks)))


def member_spec(member: Any) -> MemberSpec:
    """The spec a worker builds a league member from (see `slagents.learned.league.Member`)."""
    if member.kind == "random":
        return ("random",)
    if member.kind == "scripted":
        if not member.spec:
            raise ValueError(f"the scripted member {member.name} has no agent kind for a worker")
        return ("scripted", member.spec)
    if member.kind == "snapshot":
        if not member.spec:
            raise ValueError(f"the snapshot member {member.name} has no path for a worker")
        return ("snapshot", str(member.spec))
    raise ValueError(f"unknown member kind {member.kind!r}")
