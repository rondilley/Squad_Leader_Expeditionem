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
from slagents.learned.encoding import command_triple
from slagents.learned.env import make_env
from slagents.learned.league import League, Member, load_snapshot
from slagents.learned.nets import NetConfig, Policy
from slcli.play import build_engine_with_record, make_agent
from slruns import artifact
from slruns.elo import wilson_interval
from slruns.index import connect, upsert

LEARNER = "learner"
SCRIPTED_KINDS = ("v0", "v1", "v2", "v3")
SECONDS_IN_HOUR = 3600.0
RATE_INTERVAL_SECONDS = 60.0


def scripted_member(engine, kind: str, seed: int, player: int) -> Member:
    """A versioned scripted agent as a constant opponent (FR-52, TC-18)."""
    agent = make_agent(kind, engine, seed, player)

    def act(env, observation):
        chosen = agent.select(env.state_, env.frame)
        legal = env.frame.by_id(chosen)
        if legal is None:
            raise RuntimeError(f"the scripted agent {kind} gave an ID that is not in the frame")
        return command_triple(legal.command, env.hexes)

    return Member(name=f"scripted-{agent.name}-v{agent.version}", kind="scripted", act=act)


def build_league(engine, seed: int, opponent_player: int) -> League:
    league = League()
    league.add(Member(name="random", kind="random", act=ppo.random_opponent))
    for kind in SCRIPTED_KINDS:
        league.add(scripted_member(engine, kind, seed, opponent_player))
    return league


def snapshot_member(path: Path, policy_shape: Policy, generator: torch.Generator, step: int) -> Member:
    """A snapshot of the learner as an opponent."""
    copy = Policy(policy_shape.spaces, policy_shape.config)
    load_snapshot(path, copy)
    return Member(name=f"snapshot-{step}", kind="snapshot", act=ppo.policy_opponent(copy, generator))


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
) -> artifact.RunArtifact:
    """The training loop. It gives a run artifact, whether it finished or stopped early."""
    engine, board_record = build_engine_with_record(scenario)
    env = make_env(engine, seed=seed)
    policy = Policy(env.spaces_record, net)
    optimizer = torch.optim.Adam(policy.parameters(), lr=config.learning_rate)
    generator = torch.Generator().manual_seed(seed)
    league = build_league(engine, seed, 1 - learner_player)
    writer = _tensorboard(log_dir)
    art = artifact.RunArtifact(
        kind="train",
        slug=f"ppo-{scenario}",
        config={
            "scenario": scenario,
            **board_record,
            "agent_a": "learner",
            "agent_b": "league",
            "learner_player": learner_player,
            "steps": steps,
            "hours": hours,
            "first_seed": seed,
            "snapshot_every": snapshot_every,
            "ppo": config.to_dict(),
            "net": net.to_dict(),
            "parameters": sum(p.numel() for p in policy.parameters()),
            "opponents": [m.name for m in league.members],
            "criteria": ["TC-13", "TC-18", "TC-19", "IR-07"],
        },
    )
    art.seeds = [seed]
    snapshots: list[dict[str, Any]] = []
    done = 0
    updates = 0
    started = time.perf_counter()
    deadline = started + hours * SECONDS_IN_HOUR if hours else None
    last_rate_report = started
    rates: list[dict[str, float]] = []
    stopped = "the step count is complete"
    try:
        while done < steps and (deadline is None or time.perf_counter() < deadline):
            member = league.sample(generator)
            results: list[float] = []
            rollout = ppo.collect(
                env,
                policy,
                learner_player,
                member.act,
                min(config.steps_per_update, steps - done),
                generator,
                results.append,
            )
            for reward in results:
                league.record(member, reward, LEARNER)
            stats = ppo.update(policy, optimizer, rollout, config, env.spaces_record)
            done += len(rollout)
            updates += 1
            now = time.perf_counter()
            rate = done / max(1e-9, now - started)
            _log(writer, stats, league, done, rate, member)
            if now - last_rate_report >= RATE_INTERVAL_SECONDS:
                rates.append({"step": done, "seconds": round(now - started, 1), "steps_per_second": round(rate, 1)})
                last_rate_report = now
            if snapshot_every and done // snapshot_every > league.snapshots - 1 and done >= snapshot_every:
                path = league.take_snapshot(policy, out / "snapshots", done, net)
                league.add(snapshot_member(path, policy, generator, done))
                snapshots.append({"step": done, "path": str(path)})
    except KeyboardInterrupt:
        stopped = "a keyboard interrupt"
    seconds = time.perf_counter() - started
    if not rates:
        rates.append({"step": done, "seconds": round(seconds, 1), "steps_per_second": round(done / max(1e-9, seconds), 1)})
    evaluation = evaluate(env, policy, league, learner_player, eval_games, generator) if eval_games else []
    art.stats = {
        "steps": done,
        "updates": updates,
        "seconds": round(seconds, 1),
        "steps_per_second": round(done / max(1e-9, seconds), 1),
        "rate_reports": rates,
        "snapshots": snapshots,
        "elo": league.table(LEARNER),
        "league": league.record_table(),
        "evaluation": evaluation,
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
    generator: torch.Generator,
) -> list[dict[str, Any]]:
    """TC-18: the win rate of the learner against each constant opponent.

    The sides change on each odd game, so a scenario that favours one side does not decide
    the number. The policy plays its best command and does not sample, because the measure
    is what the policy learned and not what it explores.
    """
    rows: list[dict[str, Any]] = []
    for member in league.members:
        if member.kind == "snapshot":
            continue
        wins = 0.0
        played = 0
        results = {"win": 0, "loss": 0, "draw": 0}
        for game in range(games):
            player = learner_player if game % 2 == 0 else 1 - learner_player
            reward = _play_one(env, policy, member, player, generator)
            played += 1
            if reward > 0:
                wins += 1.0
                results["win"] += 1
            elif reward < 0:
                results["loss"] += 1
            else:
                wins += 0.5
                results["draw"] += 1
        low, high = wilson_interval(wins, played)
        rows.append(
            {
                "opponent": member.name,
                "games": played,
                "score": wins,
                "win_rate": round(wins / played, 4) if played else 0.0,
                "confidence_low": round(low, 4),
                "confidence_high": round(high, 4),
                "results": results,
                "beats_opponent": low > 0.5,
            }
        )
    return rows


def _play_one(env, policy: Policy, member: Member, learner_player: int, generator: torch.Generator) -> float:
    """One whole game of the policy against one member. Gives the learner's reward."""
    env.reset(seed=env.seed_value + 1)
    while True:
        agent = env.agent_selection
        if env.terminations[agent] or env.truncations[agent]:
            return float(env._cumulative_rewards[env.agent_of(learner_player)])
        observation = env.observe(agent)
        if env.player_of(agent) == learner_player:
            triple, _, _, _ = ppo.choose(policy, observation, env, generator, greedy=True)
            env.step(triple)
        else:
            env.step(member.act(env, observation))


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


def _log(writer, stats: dict[str, float], league: League, step: int, rate: float, member: Member) -> None:
    """IR-07: loss, entropy, win rate, and Elo as scalars."""
    if writer is None:
        return
    writer.add_scalar("loss/total", stats["loss"], step)
    writer.add_scalar("loss/policy", stats["policy_loss"], step)
    writer.add_scalar("loss/value", stats["value_loss"], step)
    writer.add_scalar("policy/entropy", stats["entropy"], step)
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
    )
    net = NetConfig()
    art = run_training(
        scenario=args.scenario,
        steps=args.steps,
        hours=args.hours,
        seed=args.seed,
        learner_player=args.player,
        snapshot_every=args.snapshot_every,
        config=config,
        net=net,
        out=out,
        log_dir=Path(args.tensorboard) if args.tensorboard else None,
        eval_games=args.eval_games,
    )
    stats = art.stats
    print(f"{stats['steps']} steps in {stats['seconds']} s = {stats['steps_per_second']} steps/s, {stats['updates']} updates")
    print(f"stopped because of {stats['stopped_because']}")
    print("elo " + json.dumps({k: v["rating"] for k, v in sorted(stats["elo"].items())}, sort_keys=True))
    for row in stats["evaluation"]:
        print(
            f"against {row['opponent']}: win rate {row['win_rate'] * 100:.1f} percent in {row['games']} games, "
            f"95 percent interval {row['confidence_low'] * 100:.1f} to {row['confidence_high'] * 100:.1f}"
        )
    directory = art.write(args.runs)
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        upsert(conn, directory)
    finally:
        conn.close()
    print(f"run artifact {directory}")
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("train", help="train the learned agent with PPO against the league")
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--steps", type=int, default=10000, help="how many decisions of the learner")
    p.add_argument("--hours", type=float, default=0.0, help="stop after this many hours, 0 for no limit")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--player", type=int, default=0, choices=(0, 1), help="which side the learner holds")
    p.add_argument("--rollout", type=int, default=512, help="decisions in one rollout")
    p.add_argument("--minibatch", type=int, default=128)
    p.add_argument("--epochs", type=int, default=4)
    p.add_argument("--learning-rate", type=float, default=3e-4)
    p.add_argument("--entropy", type=float, default=0.01)
    p.add_argument("--snapshot-every", type=int, default=20000, help="0 for no snapshot")
    p.add_argument("--out", default="runs/train", help="directory for the snapshots")
    p.add_argument("--tensorboard", default=None, help="directory for the TensorBoard scalars (IR-07)")
    p.add_argument("--eval-games", type=int, default=0, help="games against each constant opponent at the end (TC-18)")
    p.add_argument("--runs", default="runs")
    p.set_defaults(func=run)
