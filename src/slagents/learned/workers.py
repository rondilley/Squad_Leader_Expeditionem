"""Parallel collection: worker processes hold the environments, one process holds the policy.

One environment with one opponent gives the trainer 30 to 300 decisions a second, and
most of a decision is the core and the scripted opponent on one core, plus a forward pass
of the policy for a batch of one, which on the GPU costs more than the pass itself
(2026-09-16: 7.6 ms on the card against 2.8 ms on the processor). A game of scenario 1 is
about 600 decisions, so 1 million steps of the ladder were an hour or two, and the 10
million rung was days.

The split here: each worker process owns one environment, its opponent, and the seed of
its games. It plays the opponent's commands itself and sends the trainer the observation
at each decision of the learner, with the legal four-part keys of that state and the reward that
accrued since the last one. The trainer batches the observations of every worker into one
forward pass, samples one composed command for each, and sends them back. The workers run
in parallel on the cores, and the card sees one batch and not sixteen batches of one.

The worker holds a rule no more than the environment does: it builds the engine, the
environment, and the scripted agents by name, and it asks the core through them. The
policy never leaves the trainer's process, except as a snapshot file a worker loads as an
opponent (FR-52), which it runs on the processor.

The protocol is small. The trainer sends `("reset", member_spec, learner_side, seed, guide)`
or `("act", key)` or `("stop",)`. `guide` is None, or `(kind, turns)`: the scripted agent
`kind` plays the learner's side in the first `turns` turns of the game (Jump-Start RL,
`slagents.learned.jumpstart`). The worker answers each of the first two with
`("decision", observation, legal_keys, reward_delta, ended, result)`. When `ended` is
true the observation is the last state's, the delta holds the end reward, and the trainer
sends the next reset. A member spec is `("random",)`, `("scripted", kind)`, or
`("snapshot", path)`.
"""

from __future__ import annotations

import multiprocessing as mp
import sys
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from multiprocessing.connection import Connection
from typing import Any, Callable, Sequence

import numpy as np

MemberSpec = tuple[str, ...]

# A remote worker that stops leaves the pool, and the run goes on while at least this share
# of the workers it started with is live (2026-10-16). One bad line from one farm host
# stopped all 120 workers of a run before.
MIN_LIVE_SHARE = 0.5


def agent_key(agent: Any, env: Any) -> tuple[int, int, int, int]:
    """The command an Agent selects, as the environment's four-part key."""
    from slagents.base import decide
    from slagents.learned.encoding import command_index

    chosen = decide(agent, env.state_, env.frame)
    legal = env.frame.by_id(chosen)
    if legal is None:
        raise RuntimeError(f"the agent {agent.name} gave an ID that is not in the frame")
    try:
        return command_index(legal, env.groups)
    except KeyError as exc:
        raise RuntimeError(f"the agent {agent.name} gave a command that is not in the action space") from exc


@dataclass
class Decision:
    """What a worker sends at each decision of the learner, or at the end of the game."""

    observation: dict[str, np.ndarray]
    legal: list[tuple[int, int, int, int]]
    reward_delta: float
    ended: bool
    result: float
    # The seconds from the worker's receipt of the command to this decision: the learner's
    # step, the opponent's play, and the observation. The trainer's timers subtract it from
    # the round trip to get the time in the pipes, the bridge, and the network (2026-10-24).
    work_seconds: float = 0.0


def worker_main(connection: Connection, scenario: str, index: int, seed: int, max_commands: int) -> None:
    """The loop of one worker process. It answers each message until `stop`."""
    import torch

    from slagents.learned.env import make_env
    from slagents.registry import build_engine, make_agent

    torch.set_num_threads(1)
    engine = build_engine(scenario)
    env = make_env(engine, seed=seed, max_commands=max_commands)
    learner = 0
    opponents: dict[MemberSpec, Callable[[], tuple[int, int, int, int]]] = {}
    generator = torch.Generator().manual_seed(seed + index)

    def scripted(kind: str) -> Callable[[], tuple[int, int, int, int]]:
        agents = {player: make_agent(kind, engine, seed, player) for player in (0, 1)}
        return lambda: agent_key(agents[env.frame.player], env)

    def random_act() -> tuple[int, int, int, int]:
        keys = list(env.choices)
        return keys[int(torch.randint(len(keys), (1,), generator=generator).item())]

    def snapshot(path: str) -> Callable[[], tuple[int, int, int, int]]:
        from slagents.learned.agent import load_policy
        from slagents.learned.ppo import choose

        policy = load_policy(path)
        return lambda: choose(policy, env.observe(env.agent_selection), env, generator)[0]

    def opponent_of(spec: MemberSpec) -> Callable[[], tuple[int, int, int, int]]:
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

    guides: dict[str, Callable[[], tuple[int, int, int, int]]] = {}
    opponent = random_act
    guide: Callable[[], tuple[int, int, int, int]] | None = None
    guide_turns = 0
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
                state = env.state_
                # The guide never plays the last turn, so the learner has decisions.
                if guide is not None and state.turn <= min(guide_turns, state.turn_limit - 1):
                    env.step(guide())
                    continue
                ended = False
                break
            env.step(opponent())
        total = float(env._cumulative_rewards[agent_name])
        delta = total - paid
        paid = total
        result = float(env.results[agent_name]) if ended else 0.0
        return Decision(env.observe(agent_name), list(env.choices), delta, ended, result)

    while True:
        message = connection.recv()
        received = time.perf_counter()
        kind = message[0]
        if kind == "stop":
            connection.close()
            return
        if kind == "reset":
            _, spec, learner, game_seed, guide_spec = message
            opponent = opponent_of(tuple(spec))
            if guide_spec is None:
                guide, guide_turns = None, 0
            else:
                kind, guide_turns = str(guide_spec[0]), int(guide_spec[1])
                if kind not in guides:
                    guides[kind] = scripted(kind)
                guide = guides[kind]
            env.reset(seed=int(game_seed))
            paid = 0.0
            # What accrues before the learner's first decision belongs to no decision.
            decision = advance()
            paid = float(env._cumulative_rewards[env.agent_of(learner)])
            decision.reward_delta = 0.0
            decision.work_seconds = time.perf_counter() - received
            connection.send(decision)
        elif kind == "act":
            env.step(tuple(int(x) for x in message[1]))
            decision = advance()
            decision.work_seconds = time.perf_counter() - received
            connection.send(decision)
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
    # The turns the guide plays in the game in progress, zero for none (Jump-Start RL).
    guide_turns: int = 0
    pending: Decision | None = None
    # The steps of the game in progress that are in the rollout being built, as indexes.
    steps: list[int] = field(default_factory=list)


class WorkerPool:
    """The worker processes of one training run.

    With `farm` (an `slfarm.client.Farm`) the pool has remote workers too: each one is the
    loop of `worker_main` on a farm host, and a bridge process for each host gives the
    trainer a pipe end to it, so the trainer reads a remote worker as it reads a local one
    (2026-10-14).
    `remote_envs` is the count of them on each host; zero is the slots of the host.

    A remote worker that stops (its host, its bridge, or the network) leaves the pool by
    `drop`, and `dropped` records it. A local worker that stops is a fault of the code on
    this machine, so it stops the run.
    """

    def __init__(
        self, scenario: str, workers: int, seed: int, max_commands: int, spaces: Any,
        farm: Any = None, remote_envs: int = 0,
    ) -> None:
        from slagents.registry import limit_workers

        workers = limit_workers(workers)
        context = mp.get_context("spawn")
        # The sizes of the three heads, which the batched choice reads for its masks.
        self.spaces = spaces
        self.workers: list[Worker] = []
        self.bridges: list[Any] = []
        self.dropped: list[dict[str, Any]] = []
        self.started_with = 0
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
        if farm is not None:
            try:
                self._open_remote(farm, remote_envs, scenario, seed, max_commands)
            except BaseException:
                self.close()
                raise
        self.started_with = len(self.workers)

    def _open_remote(self, farm: Any, remote_envs: int, scenario: str, seed: int, max_commands: int) -> None:
        """One bridge process for each host (`slfarm.client.host_bridge_main`), so the JSON
        of the decisions does not take the interpreter lock of the trainer."""
        from slfarm.client import BRIDGE_OPEN_SECONDS, RemoteEnvError, host_bridge_main, ping

        context = mp.get_context("spawn")
        # All bridges start before the pool waits for one, so the hosts open at the same time.
        controls: list[tuple[Any, Any, int]] = []
        try:
            for address in farm.addresses:
                count = remote_envs
                if count == 0:
                    row = ping([address], farm.key)[0]
                    if "error" in row:
                        raise RemoteEnvError(f"{address}: {row['error']}")
                    count = int(row["slots"])
                first = len(self.workers)
                pairs = [context.Pipe() for _ in range(count)]
                control, their_control = context.Pipe()
                process = context.Process(
                    target=host_bridge_main,
                    args=(their_control, [theirs for _, theirs in pairs], address, farm.key, scenario, first, seed, max_commands),
                    daemon=True,
                    name=f"sl-bridge-{address.host}",
                )
                process.start()
                their_control.close()
                for _, theirs in pairs:
                    theirs.close()
                self.bridges.append(process)
                for offset, (ours, _) in enumerate(pairs):
                    self.workers.append(Worker(index=first + offset, process=None, connection=ours))
                controls.append((address, control, count))
            for address, control, count in controls:
                if not control.poll(BRIDGE_OPEN_SECONDS):
                    raise RemoteEnvError(f"{address} did not open {count} environments in {BRIDGE_OPEN_SECONDS:.0f} s")
                try:
                    answer = control.recv()
                except EOFError as exc:
                    raise RemoteEnvError(f"the bridge process of {address} stopped") from exc
                if answer[0] != "ready":
                    raise RemoteEnvError(f"{address} did not open its environments: {answer[1]}")
        finally:
            for _, control, _ in controls:
                control.close()

    def __len__(self) -> int:
        return len(self.workers)

    def reset(
        self, worker: Worker, spec: MemberSpec, member_name: str, learner: int, seed: int,
        guide: tuple[str, int] | None = None,
    ) -> None:
        worker.spec = spec
        worker.member_name = member_name
        worker.learner = learner
        worker.guide_turns = 0 if guide is None else int(guide[1])
        worker.steps = []
        self._send(worker, ("reset", spec, learner, seed, guide))

    def act(self, worker: Worker, quad: tuple[int, int, int, int]) -> None:
        self._send(worker, ("act", quad))

    def _send(self, worker: Worker, message: tuple) -> None:
        try:
            worker.connection.send(message)
        except (OSError, ValueError) as exc:
            raise WorkerDied(f"{self._where(worker)} (worker {worker.index}) stopped during the rollout: {exc}") from exc

    def receive(self, worker: Worker) -> Decision:
        try:
            decision = worker.connection.recv()
        except (EOFError, OSError) as exc:
            raise WorkerDied(f"{self._where(worker)} (worker {worker.index}) stopped during the rollout") from exc
        worker.pending = decision
        return decision

    @staticmethod
    def _where(worker: Worker) -> str:
        return "a remote worker of the farm" if worker.process is None else "a worker process"

    def drop(self, worker: Worker, error: WorkerDied) -> None:
        """Take a remote worker that stopped out of the pool, or raise `error` again.

        It raises for a local worker, and when the live workers would fall below
        `MIN_LIVE_SHARE` of the workers the pool started with.
        """
        live = len(self.workers) - 1
        if worker.process is not None or worker not in self.workers or live < MIN_LIVE_SHARE * self.started_with:
            raise error
        self.workers.remove(worker)
        try:
            worker.connection.close()
        except OSError:
            pass
        self.dropped.append({"worker": worker.index, "error": str(error)})
        print(f"train: {error}; the run goes on with {live} workers", file=sys.stderr, flush=True)

    def close(self) -> None:
        for worker in self.workers:
            try:
                worker.connection.send(("stop",))
            except (OSError, ValueError):
                pass
        for worker in self.workers:
            if worker.process is not None:
                worker.process.join(timeout=10.0)
                if worker.process.is_alive():
                    worker.process.terminate()
            worker.connection.close()
        for process in self.bridges:
            process.join(timeout=10.0)
            if process.is_alive():
                process.terminate()

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
    from slagents.registry import build_engine

    torch.set_num_threads(1)
    engine = build_engine(scenario)
    env = make_env(engine, seed=1, max_commands=max_commands)
    policy = None
    if policy_state is not None:
        policy = Policy(env.spaces_record, NetConfig(**net))
        policy.load_state_dict(policy_state)
        policy.eval()
    _imitation.update(engine=engine, env=env, policy=policy)


class WorkerDied(RuntimeError):
    """A game ended its worker process each time it played, also alone in a pool, or a
    worker of the training pool (a remote one of the farm too) stopped during a rollout."""


def play_in_order(
    play: Callable[[Any], Any],
    tasks: Sequence[Any],
    workers: int,
    initializer: Callable[..., None] | None,
    initargs: tuple,
    deliver: Callable[[int, Any], None],
) -> None:
    """Play each task in a process pool and give each result to `deliver` in task order.

    A worker process that dies (a native fault, not a Python exception) loses its game, and
    `multiprocessing.Pool.imap` then waits for that result for ever (the s04 gauntlet of
    2026-10-12). The executor marks the pool broken, and the tasks with no result play
    again in a new pool while each pass gives a new result. A game is its seed, so the
    second play gives the same result. After a pass with no new result, each task left
    plays in a pool of its own, and a task that ends its worker there too is a `WorkerDied`.
    """
    context = mp.get_context("spawn")
    done: set[int] = set()
    ready: dict[int, Any] = {}
    next_index = 0

    def one_pass(indexes: list[int], size: int) -> None:
        nonlocal next_index
        with ProcessPoolExecutor(max_workers=size, mp_context=context, initializer=initializer, initargs=initargs) as executor:
            futures = {executor.submit(play, tasks[index]): index for index in indexes}
            for future in as_completed(futures):
                try:
                    value = future.result()
                except BrokenProcessPool:
                    continue
                index = futures[future]
                done.add(index)
                ready[index] = value
                while next_index in ready:
                    deliver(next_index, ready.pop(next_index))
                    next_index += 1

    while True:
        waiting = [index for index in range(len(tasks)) if index not in done]
        if not waiting:
            return
        before = len(done)
        one_pass(waiting, max(1, min(workers, len(waiting))))
        if len(done) == before:
            break
    for index in [index for index in range(len(tasks)) if index not in done]:
        one_pass([index], 1)
        if index not in done:
            raise WorkerDied(f"the worker process died each time it played task {index}: {tasks[index]!r}")


def _make_teacher(kind: str, game_seed: int, player: int) -> Any:
    from slagents.registry import make_agent

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
    from slagents.registry import limit_workers

    workers = limit_workers(workers)

    def deliver(game: int, outcome: tuple[Any, float]) -> None:
        played, result = outcome
        data.extend(played)
        if on_game is not None:
            on_game(game, tasks[game][0], tasks[game][1], result)

    play_in_order(_demonstration_game, tasks, workers, _init_imitation, (scenario, max_commands, None, None), deliver)
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
    from slagents.registry import limit_workers

    workers = limit_workers(workers)

    def deliver(game: int, outcome: tuple[Any, float]) -> None:
        played, result = outcome
        data.extend(played)
        if on_game is not None:
            on_game(game, tasks[game][1], tasks[game][2], result)

    play_in_order(_correction_game, tasks, workers, _init_imitation, (scenario, max_commands, state, policy.config.to_dict()), deliver)
    return data


def _evaluation_game(args: tuple) -> tuple[float, bool, bool]:
    """One game of the policy, as the agent a tournament plays, against one member."""
    from slagents.learned.agent import LearnedAgent
    from slagents.registry import make_agent

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
        env.step(agent_key(actor, env))


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
    from slagents.registry import limit_workers

    workers = limit_workers(workers)
    results: list[tuple[float, bool, bool]] = []
    play_in_order(
        _evaluation_game,
        list(tasks),
        workers,
        _init_imitation,
        (scenario, max_commands, state, policy.config.to_dict()),
        lambda _index, outcome: results.append(outcome),
    )
    return results


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
