"""The training command (FR-51, FR-52, IR-07, TC-13, TC-18, TC-19).

One command starts a run: `sl-cli train --scenario s01_guards_counterattack --steps 100000`.
The run writes TensorBoard scalars while it goes, and a run artifact at the end with the
Elo table, the league record, the network shape, and the numbers of the algorithm.

The run stops on the step count or on the hour count, and it stops cleanly on a keyboard
interrupt. A run that stops early still writes its artifact, because a measurement that
only exists at the end of a long run is a measurement that a long run can lose.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import torch

from slagents.learned import ppo
from slagents.learned.agent import LearnedAgent
from slagents.learned.env import make_env
from slagents.learned.jumpstart import JumpStart
from slagents.learned.league import League, Member, load_snapshot
from slagents.learned.nets import NetConfig, Policy
from slagents.learned.workers import agent_key
from slcli.gauntlet import add_farm_arguments, farm_of
from slcli.play import build_engine_with_record, make_agent
from slruns import artifact
from slruns.elo import wilson_interval
from slruns.seeds import MINIMUM_BASELINE_GAMES, family_seed, sample_warning
from slruns.index import connect, upsert

LEARNER = "learner"
SCRIPTED_KINDS = ("v0", "v1", "v2", "v3", "v4", "v5", "v6", "v7")
SECONDS_IN_HOUR = 3600.0
RATE_INTERVAL_SECONDS = 60.0


def scripted_member(engine, kind: str, seed: int) -> Member:
    """A versioned scripted agent as a constant opponent (FR-52, TC-18).

    The member holds one agent for each side and plays the one whose side the frame names.
    A scripted agent plans for the side it was built for, so an agent built for the German
    side that is handed the Russian frame moves the Russians with the German plan. The
    evaluation of the third 1 million step run did that in each odd game, because the
    member was built for the opponent of the learner and the sides then changed.
    """
    agents = {player: make_agent(kind, engine, seed, player) for player in (0, 1)}

    def act(env, observation):
        return agent_key(agents[env.frame.player], env)

    first = agents[0]
    return Member(name=f"scripted-{first.name}-v{first.version}", kind="scripted", act=act, spec=kind)


def build_league(engine, seed: int, opponents: list[str] | None = None) -> League:
    """The league of the run: random and each scripted agent, or the `opponents` alone."""
    league = League()
    for kind in ("random", *SCRIPTED_KINDS) if opponents is None else opponents:
        if kind == "random":
            league.add(Member(name="random", kind="random", act=ppo.random_opponent))
        else:
            league.add(scripted_member(engine, kind, seed))
    return league


def snapshot_member(path: Path, policy_shape: Policy, generator: torch.Generator, step: int) -> Member:
    """A snapshot of the learner as an opponent, on the same device as the learner."""
    copy = Policy(policy_shape.spaces, policy_shape.config).to(ppo.policy_device(policy_shape))
    load_snapshot(path, copy)
    return Member(name=f"snapshot-{step}", kind="snapshot", act=ppo.policy_opponent(copy, generator), spec=str(path))


def run_training(
    scenario: str,
    steps: int,
    hours: float,
    seed: int,
    learner_player: int,
    snapshot_every: int,
    config: ppo.PpoConfig,
    net: NetConfig,
    out: Path,
    log_dir: Path | None,
    eval_games: int = 0,
    device: str = "auto",
    alternate_sides: bool = False,
    start_from: Path | None = None,
    workers: int = 1,
    opponent_cap: float | None = None,
    opponents: list[str] | None = None,
    jump_start: JumpStart | None = None,
    farm: Any = None,
    remote_envs: int = 0,
) -> artifact.RunArtifact:
    """The training loop. It gives a run artifact, whether it finished or stopped early.

    `learner_player` is the side the learner holds first. With `alternate_sides` it takes
    the other side at each new game (`--player both`). `start_from` is a snapshot whose
    weights the policy starts with, as the one `sl-cli imitate` writes; its shape replaces
    `net`, because the weights fit one shape. With `workers` above one the games play in
    that many worker processes and the policy answers them in one batch (`--workers`).
    `opponent_cap` is the largest share of the games one league member gets
    (`--opponent-cap`). `opponents` names the only league members (`--opponents v7`), and
    then no snapshot of the learner goes into the league: the s04 attacker run of
    2026-10-13 trains against v7 alone. `jump_start` gives the first turns of the
    learner's side of each game to a guide agent (`--jump-start v7`); it needs workers.
    `farm` adds remote workers on the farm hosts (`--remote`), `remote_envs` on each host
    (zero is the slots of the host); the farm plays random and scripted opponents only, so
    it needs `opponents`.
    """
    from slagents.learned.workers import WorkerPool, member_spec

    if jump_start is not None and workers < 2 and farm is None:
        raise ValueError("--jump-start needs --workers 2 or more, because the guide plays in the worker processes")
    if farm is not None and opponents is None:
        raise ValueError("--remote needs --opponents: the farm plays random and scripted opponents, and a league snapshot is a file of this workstation")
    engine, board_record = build_engine_with_record(scenario)
    env = make_env(engine, seed=seed)
    compute = ppo.resolve_device(device)
    if start_from is not None:
        net = snapshot_net(start_from, env.spaces_record)
    policy = Policy(env.spaces_record, net).to(compute)
    anchor: Policy | None = None
    if start_from is not None:
        load_snapshot(start_from, policy)
        policy.train()
        if config.anchor_kl > 0.0:
            # The frozen start, which the KL term of the update holds the policy near.
            anchor = Policy(env.spaces_record, net).to(compute)
            load_snapshot(start_from, anchor)
            for parameter in anchor.parameters():
                parameter.requires_grad_(False)
    elif config.anchor_kl > 0.0:
        raise ValueError("--anchor-kl needs --start-from, because the anchor is the policy the run starts from")
    optimizer = torch.optim.Adam(policy.parameters(), lr=config.learning_rate)
    generator = torch.Generator().manual_seed(seed)
    league = build_league(engine, seed, opponents)
    league.share_cap = opponent_cap
    writer = _tensorboard(log_dir)
    art = artifact.RunArtifact(
        kind="train",
        slug=f"ppo-{scenario}",
        config={
            "scenario": scenario,
            **board_record,
            "agent_a": "learner",
            "agent_b": "league",
            "learner_player": "both" if alternate_sides else learner_player,
            "start_from": None if start_from is None else str(start_from),
            "first_learner_player": learner_player,
            "steps": steps,
            "hours": hours,
            "first_seed": seed,
            "snapshot_every": snapshot_every,
            "ppo": config.to_dict(),
            "reward": {"player_0": env.weights[0].to_dict(), "player_1": env.weights[1].to_dict()},
            "net": net.to_dict(),
            "device": str(compute),
            "parameters": sum(p.numel() for p in policy.parameters()),
            "opponents": [m.name for m in league.members],
            "workers": workers,
            "farm": [str(a) for a in farm.addresses] if farm is not None else [],
            "remote_envs": remote_envs,
            "opponent_cap": opponent_cap,
            "fixed_opponents": opponents is not None,
            "jump_start": None if jump_start is None else jump_start.to_dict(),
            "criteria": ["TC-13", "TC-18", "TC-19", "IR-07"],
        },
    )
    art.seeds = [seed]
    snapshots: list[dict[str, Any]] = []
    done = 0
    updates = 0
    warmup_updates = 0
    started = time.perf_counter()
    deadline = started + hours * SECONDS_IN_HOUR if hours else None
    last_rate_report = started
    rates: list[dict[str, float]] = []
    stopped = "the step count is complete"
    side = learner_player
    pool = None
    if workers > 1 or farm is not None:
        pool = WorkerPool(scenario, workers, seed, env.max_commands, env.spaces_record, farm=farm, remote_envs=remote_envs)
        art.config["remote_workers"] = len(pool.workers) - workers
        # With both sides the workers start on the two sides in turn, so each rollout
        # holds the attack and the defence.
        for w in pool.workers:
            w.learner = (learner_player + w.index) % 2 if alternate_sides else learner_player
    games_started = 0

    def next_member() -> tuple[tuple[str, ...], str]:
        member = league.sample(generator)
        return member_spec(member), member.name

    def next_seed() -> int:
        nonlocal games_started
        games_started += 1
        return family_seed("train", seed, games_started)

    # L3: in the one-process path a league member plays a whole game. The member of the
    # game in progress stays across the rollouts, and a new game samples the next one.
    current: Member | None = league.sample(generator) if pool is None else None

    def next_opponent():
        nonlocal current
        current = league.sample(generator)
        return current.act

    def record_current(result: float) -> None:
        if current is None:
            raise RuntimeError("a game ended with no league member in it")
        league.record(current, result, LEARNER)

    def record_result(member_name: str, result: float) -> None:
        member = league.by_name(member_name)
        if member is None:
            raise RuntimeError(f"a worker played {member_name}, which is not in the league")
        league.record(member, result, LEARNER)

    try:
        while done < steps and (deadline is None or time.perf_counter() < deadline):
            if pool is not None:
                rollout = ppo.collect_parallel(
                    pool,
                    policy,
                    min(config.steps_per_update, steps - done),
                    generator,
                    next_member,
                    next_seed,
                    record_result,
                    alternate_sides=alternate_sides,
                    jump_start=jump_start,
                )
            else:
                rollout = ppo.collect(
                    env,
                    policy,
                    side,
                    current.act,
                    min(config.steps_per_update, steps - done),
                    generator,
                    record_current,
                    alternate_sides=alternate_sides,
                    next_opponent=next_opponent,
                )
                side = rollout.next_learner
            stats = ppo.update(
                policy, optimizer, rollout, config, env.spaces_record, anchor,
                value_only=done < config.value_warmup_steps,
            )
            done += len(rollout)
            updates += 1
            warmup_updates += int(stats["value_only"])
            now = time.perf_counter()
            rate = done / max(1e-9, now - started)
            _log(writer, stats, league, done, rate)
            if writer is not None and jump_start is not None:
                writer.add_scalar("jump_start/turns", jump_start.turns, done)
                writer.add_scalar("jump_start/win_rate", jump_start.win_rate(), done)
            if now - last_rate_report >= RATE_INTERVAL_SECONDS:
                rates.append({"step": done, "seconds": round(now - started, 1), "steps_per_second": round(rate, 1)})
                last_rate_report = now
            if snapshot_every and done // snapshot_every > league.snapshots - 1 and done >= snapshot_every:
                path = league.take_snapshot(policy, out / "snapshots", done, net)
                if opponents is None:
                    league.add(snapshot_member(path, policy, generator, done))
                snapshots.append({"step": done, "path": str(path)})
    except KeyboardInterrupt:
        stopped = "a keyboard interrupt"
    finally:
        if pool is not None:
            pool.close()
    # The policy at the end, also when the count is not a multiple of the interval: a run
    # of 1,996,416 decisions with an interval of 2,000,000 kept no net (2026-10-16).
    if snapshot_every and done and (not snapshots or snapshots[-1]["step"] != done):
        path = league.take_snapshot(policy, out / "snapshots", done, net)
        snapshots.append({"step": done, "path": str(path)})
    seconds = time.perf_counter() - started
    if not rates:
        rates.append({"step": done, "seconds": round(seconds, 1), "steps_per_second": round(done / max(1e-9, seconds), 1)})
    evaluation = evaluate(env, policy, league, learner_player, eval_games, workers, scenario, first_seed=seed) if eval_games else []
    art.stats = {
        "steps": done,
        "updates": updates,
        "value_warmup_updates": warmup_updates,
        "seconds": round(seconds, 1),
        "steps_per_second": round(done / max(1e-9, seconds), 1),
        "rate_reports": rates,
        "snapshots": snapshots,
        "dropped_workers": [] if pool is None else pool.dropped,
        "elo": league.table(LEARNER),
        "league": league.record_table(),
        "evaluation": evaluation,
        "jump_start": None if jump_start is None else jump_start.to_dict(),
        "stopped_because": stopped,
        "passed": {
            "TC-19": _elo_complete(league),
            "TC-18": bool(evaluation) and any(row["beats_opponent"] for row in evaluation),
        },
    }
    if writer is not None:
        writer.close()
    return art


def evaluate(
    env,
    policy: Policy,
    league: League,
    learner_player: int,
    games: int,
    workers: int = 1,
    scenario: str | None = None,
    first_seed: int | None = None,
) -> list[dict[str, Any]]:
    """TC-18: the win rate of the learner against each constant opponent.

    The sides change on each odd game, so a scenario that favours one side does not decide
    the number. The policy plays through `LearnedAgent`, the wrapper a tournament and a
    real game use: the argmax of the composed score, with the repeat guard, and no
    sampling, because the measure is what the policy learned and not what it explores.
    With `workers` above one the games play in a process pool, each with its own copy of
    the policy, and `scenario` names the engine each process builds.

    The seeds are in the evaluation range of `slruns.seeds` (L4), so no evaluation game
    is a game the policy trained on: before this the evaluation played the seeds after the
    first training seed, which the training had played. `first_seed` is the seed of the
    run, and the environment's seed when it is none. The two games of each pair share one
    seed and change the sides (L7), so the side the scenario favours cancels in the pair.
    A repeated position counts as a loss for the learner in the win rate (L5), and the
    `repeated` count keeps the games apart.
    """
    from slagents.learned.workers import evaluation_parallel, member_spec

    rows: list[dict[str, Any]] = []
    base_seed = env.seed_value if first_seed is None else first_seed

    def game_seed(game: int) -> int:
        return family_seed("train_evaluation", base_seed, 1 + game // 2)

    learner = LearnedAgent.from_policy(env.engine, policy)
    members = [m for m in league.members if m.kind != "snapshot"]
    outcomes: dict[str, list[tuple[float, bool, bool]]] = {}
    if workers > 1:
        if scenario is None:
            raise ValueError("a parallel evaluation needs the scenario name for its workers")
        tasks = []
        for member in members:
            for game in range(games):
                player = learner_player if game % 2 == 0 else 1 - learner_player
                tasks.append((member_spec(member), player, game_seed(game)))
        played_games = evaluation_parallel(scenario, policy, tasks, workers, env.max_commands)
        for member in members:
            outcomes[member.name] = played_games[: games]
            played_games = played_games[games:]
    for member in members:
        wins = 0.0
        played = 0
        results = {"win": 0, "loss": 0, "draw": 0, "truncated": 0, "repeated": 0}
        # The same counts for each side the learner held. A policy that trained on one
        # side plays the other side cold, and the sum hides which side each result came
        # from: the third 1 million step run read 10 lost and 10 repeated against each
        # scripted agent, and that was every game lost as the Russian and every game
        # cycled as the German.
        by_side = {f"player_{player}": dict(results) for player in (0, 1)}
        for game in range(games):
            player = learner_player if game % 2 == 0 else 1 - learner_player
            if workers > 1:
                result, truncated, repeated = outcomes[member.name][game]
            else:
                result, truncated = _play_one(env, learner, member, player, game_seed(game))
                repeated = env.repeated
            played += 1
            if truncated and repeated:
                # A cycle: a command undid the one before it, and the environment stopped
                # the game there as a defeat of the side that made the cycle. It adds
                # nothing to the score, so the win rate counts it as a loss (L5).
                outcome = "repeated"
            elif truncated:
                # A game that hit the command limit is not a draw and not half a win. The
                # first rung's evaluation counted 153 of them as half a win each, and the
                # score column read 50 percent (docs/reports/2026-09-12_training_run_1m.md).
                outcome = "truncated"
            elif result > 0:
                wins += 1.0
                outcome = "win"
            elif result < 0:
                outcome = "loss"
            else:
                wins += 0.5
                outcome = "draw"
            results[outcome] += 1
            by_side[f"player_{player}"][outcome] += 1
        low, high = wilson_interval(wins, played)
        rows.append(
            {
                "opponent": member.name,
                "games": played,
                "score": wins,
                "win_rate": round(wins / played, 4) if played else 0.0,
                "confidence_low": round(low, 4),
                "confidence_high": round(high, 4),
                "seeds": sorted({game_seed(game) for game in range(games)}),
                "results": results,
                "by_side": by_side,
                "beats_opponent": low > 0.5,
            }
        )
    return rows


def _play_one(env, learner: LearnedAgent, member: Member, learner_player: int, seed: int) -> tuple[float, bool]:
    """One whole game of the learner against one member. Gives the result and whether it was truncated."""
    env.reset(seed=seed)
    while True:
        agent = env.agent_selection
        if env.terminations[agent] or env.truncations[agent]:
            learner_agent = env.agent_of(learner_player)
            return float(env.results[learner_agent]), bool(env.truncations[learner_agent])
        if env.player_of(agent) == learner_player:
            env.step(agent_key(learner, env))
        else:
            env.step(member.act(env, env.observe(agent)))


def snapshot_net(path: Path, spaces) -> NetConfig:
    """The shape of a snapshot, checked against the spaces of this scenario."""
    saved = torch.load(path, map_location="cpu", weights_only=True)
    if "spaces" not in saved or "net" not in saved:
        raise ValueError(f"the snapshot {path} has no spaces or net record; it is not a training snapshot")
    s = saved["spaces"]
    theirs = (int(s["units"]), int(s["actions"]), int(s["targets"]), int(s["cols"]), int(s["rows"]))
    ours = (spaces.units, spaces.actions, spaces.targets, spaces.cols, spaces.rows)
    if theirs != ours:
        raise ValueError(
            f"the snapshot {path} has the spaces {theirs} and this scenario has {ours}; "
            "a start needs a snapshot of the same scenario and board"
        )
    return NetConfig(**{k: int(v) for k, v in saved["net"].items()})


def _elo_complete(league: League) -> bool:
    """TC-19: the table has an entry for each member and for the learner."""
    table = league.table(LEARNER)
    return all(m.name in table for m in league.members) and LEARNER in table


def _tensorboard(log_dir: Path | None):
    if log_dir is None:
        return None
    try:
        from torch.utils.tensorboard import SummaryWriter
    except ImportError:
        return None
    log_dir.mkdir(parents=True, exist_ok=True)
    return SummaryWriter(str(log_dir))


def _log(writer, stats: dict[str, float], league: League, step: int, rate: float) -> None:
    """IR-07: loss, entropy, win rate, and Elo as scalars."""
    if writer is None:
        return
    writer.add_scalar("loss/total", stats["loss"], step)
    writer.add_scalar("loss/policy", stats["policy_loss"], step)
    writer.add_scalar("loss/value", stats["value_loss"], step)
    writer.add_scalar("policy/entropy", stats["entropy"], step)
    writer.add_scalar("policy/anchor_kl", stats.get("anchor_kl", 0.0), step)
    writer.add_scalar("run/value_only", stats.get("value_only", 0.0), step)
    writer.add_scalar("run/steps_per_second", rate, step)
    writer.add_scalar("elo/learner", league.elo.rating(LEARNER), step)
    for other in league.members:
        if other.games:
            writer.add_scalar(f"win_rate/{other.name}", other.wins / other.games, step)
            writer.add_scalar(f"elo/{other.name}", league.elo.rating(other.name), step)


def run(args: Any) -> int:
    out = Path(args.out)
    config = ppo.PpoConfig(
        steps_per_update=args.rollout,
        minibatch=args.minibatch,
        epochs=args.epochs,
        learning_rate=args.learning_rate,
        entropy_coefficient=args.entropy,
        discount=args.discount,
        anchor_kl=args.anchor_kl,
        value_warmup_steps=args.value_warmup,
    )
    net = NetConfig(channels=args.channels, hidden=args.hidden)
    art = run_training(
        scenario=args.scenario,
        steps=args.steps,
        hours=args.hours,
        seed=args.seed,
        learner_player=0 if args.player == "both" else int(args.player),
        alternate_sides=args.player == "both",
        snapshot_every=args.snapshot_every,
        config=config,
        net=net,
        out=out,
        log_dir=Path(args.tensorboard) if args.tensorboard else None,
        eval_games=args.eval_games,
        device=args.device,
        start_from=Path(args.start_from) if args.start_from else None,
        workers=args.workers,
        opponent_cap=args.opponent_cap,
        opponents=[k.strip() for k in args.opponents.split(",") if k.strip()] or None,
        jump_start=(
            JumpStart(args.jump_start, args.jump_start_turns, args.jump_start_threshold, args.jump_start_window)
            if args.jump_start else None
        ),
        farm=farm_of(args),
        remote_envs=args.remote_envs,
    )
    stats = art.stats
    print(f"device {art.config['device']}")
    print(f"{stats['steps']} steps in {stats['seconds']} s = {stats['steps_per_second']} steps/s, {stats['updates']} updates")
    print(f"stopped because of {stats['stopped_because']}")
    if stats.get("jump_start"):
        js = stats["jump_start"]
        print(f"jump start: the guide {js['guide']} plays {js['turns']} turns at the end, after {len(js['changes'])} changes in {js['games']} games")
    print("elo " + json.dumps({k: v["rating"] for k, v in sorted(stats["elo"].items())}, sort_keys=True))
    for row in stats["evaluation"]:
        print(
            f"against {row['opponent']}: win rate {row['win_rate'] * 100:.1f} percent in {row['games']} games "
            f"({_counts(row['results'])}), "
            f"95 percent interval {row['confidence_low'] * 100:.1f} to {row['confidence_high'] * 100:.1f}"
        )
        for side, counts in row["by_side"].items():
            print(f"    as {side}: {_counts(counts)}")
        warning = sample_warning(row["games"])
        if warning:
            print(f"    {warning}")
    directory = art.write(args.runs)
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        upsert(conn, directory)
    finally:
        conn.close()
    print(f"run artifact {directory}")
    return 0


def _counts(results: dict[str, int]) -> str:
    return (
        f"{results['win']} won, {results['loss']} lost, {results['draw']} drawn, "
        f"{results['truncated']} truncated, {results['repeated']} repeated"
    )


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("train", help="train the learned agent with PPO against the league")
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--steps", type=int, default=10000, help="how many decisions of the learner")
    p.add_argument("--hours", type=float, default=0.0, help="stop after this many hours, 0 for no limit")
    p.add_argument(
        "--seed",
        type=int,
        default=1,
        help="the first training seed; the evaluation plays its own range of seeds (slruns.seeds), so no evaluation game is a training game",
    )
    p.add_argument(
        "--player",
        default="0",
        choices=("0", "1", "both"),
        help="which side the learner holds; both changes the side at each new game",
    )
    p.add_argument("--rollout", type=int, default=512, help="decisions in one rollout")
    p.add_argument("--minibatch", type=int, default=128)
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--learning-rate", type=float, default=3e-4)
    p.add_argument("--entropy", type=float, default=0.01)
    p.add_argument("--discount", type=float, default=1.0, help="the discount of a later reward, 1.0 for none")
    p.add_argument("--device", default="auto", help="auto, cpu, cuda, or cuda:0 (auto takes the GPU when there is one)")
    from slcli.worker_limit import workers_argument

    p.add_argument("--workers", type=workers_argument, default=1, help="worker processes that play the games; 1 plays them in this process")
    add_farm_arguments(p)
    p.add_argument("--remote-envs", type=int, default=0, help="PPO workers on each farm host of --remote; 0 is the slots of the host")
    p.add_argument(
        "--opponent-cap",
        type=float,
        default=None,
        help="the largest share of the games one league member gets, as 0.05; none for the loss-rate rule alone",
    )
    p.add_argument(
        "--opponents",
        default="",
        help="a comma list of the only league members, as v7 or random,v5; no snapshot of the learner joins them; default random and each scripted agent",
    )
    p.add_argument(
        "--jump-start",
        default="",
        help="a scripted agent, as v7, that plays the learner's side in the first turns of each game (Jump-Start RL); needs --workers 2 or more",
    )
    p.add_argument("--jump-start-turns", type=int, default=3, help="the turns the guide plays at the start of the run")
    p.add_argument(
        "--jump-start-threshold",
        type=float,
        default=0.4,
        help="the learner's win rate at one horizon that makes the guide play one turn less",
    )
    p.add_argument("--jump-start-window", type=int, default=100, help="the games at one horizon that the win rate reads")
    p.add_argument("--channels", type=int, default=32, help="convolution channels of the board encoder")
    p.add_argument("--hidden", type=int, default=256, help="width of the trunk and the heads")
    p.add_argument("--start-from", default=None, help="a snapshot the policy starts from, as sl-cli imitate writes")
    p.add_argument(
        "--anchor-kl",
        type=float,
        default=0.0,
        help="the weight of the KL divergence from the start snapshot, which holds the policy near it; 0 for none",
    )
    p.add_argument(
        "--value-warmup",
        type=int,
        default=0,
        help="the first decisions of the run that train the value head alone, with the policy fixed; 0 for none",
    )
    p.add_argument("--snapshot-every", type=int, default=20000, help="0 for no snapshot")
    p.add_argument("--out", default="runs/train", help="directory for the snapshots")
    p.add_argument("--tensorboard", default=None, help="directory for the TensorBoard scalars (IR-07)")
    p.add_argument(
        "--eval-games",
        type=int,
        default=0,
        help=f"games against each constant opponent at the end (TC-18); a baseline rate needs {MINIMUM_BASELINE_GAMES} or more, and each rate prints with its 95 percent Wilson interval",
    )
    p.add_argument("--runs", default="runs")
    p.set_defaults(func=run)
