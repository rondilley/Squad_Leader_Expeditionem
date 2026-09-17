"""The imitation command: a policy that copies the scripted agents, as the start of PPO.

`sl-cli imitate --scenario s01_guards_counterattack --teachers v5,v6 --games 200` plays
the games, fits the policy, writes the snapshot, and evaluates it against the constant
opponents of the league the way `sl-cli train` does (TC-18). Then
`sl-cli train --start-from <snapshot>` continues from it.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from slagents.learned import imitate, ppo
from slagents.learned.env import make_env
from slagents.learned.nets import NetConfig, Policy
from slcli.play import build_engine_with_record, make_agent
from slcli.train import build_league, evaluate
from slruns import artifact
from slruns.index import connect, upsert


def run_imitation(
    scenario: str,
    teachers: list[str],
    games: int,
    seed: int,
    config: imitate.FitConfig,
    net: NetConfig,
    out: Path,
    eval_games: int = 0,
    device: str = "auto",
    log=print,
) -> artifact.RunArtifact:
    """The whole pass: the games, the fit, the snapshot, and the evaluation."""
    engine, board_record = build_engine_with_record(scenario)
    env = make_env(engine, seed=seed)
    compute = ppo.resolve_device(device)
    policy = Policy(env.spaces_record, net).to(compute)
    started = time.perf_counter()

    def make_teacher(kind: str, game_seed: int, player: int):
        return make_agent(kind, engine, game_seed, player)

    def on_game(game: int, a: str, b: str, result: float) -> None:
        if (game + 1) % 10 == 0 or game + 1 == games:
            log(f"game {game + 1}/{games}: {a} against {b}, result {result:+.0f}")

    data = imitate.collect_demonstrations(env, make_teacher, teachers, games, seed, on_game)
    collected = time.perf_counter() - started
    log(f"{len(data)} decisions from {data.games} games in {collected:.1f} s, results {data.results}")

    def on_epoch(epoch: int, row: dict[str, float]) -> None:
        log(
            f"epoch {epoch}: cross entropy {row['cross_entropy']:.3f}, value loss {row['value_loss']:.3f}, "
            f"holdout cross entropy {row['holdout_cross_entropy']:.3f}, holdout accuracy {row['holdout_accuracy'] * 100:.1f} percent"
        )

    rows = imitate.fit(policy, data, config, env.spaces_record, seed, on_epoch)
    fitted = time.perf_counter() - started - collected
    record = {
        "scenario": scenario,
        "teachers": teachers,
        "games": data.games,
        "decisions": len(data),
        "seed": seed,
        "fit": config.to_dict(),
        "epochs": rows,
    }
    path = imitate.save(policy, out, net, record)
    log(f"snapshot {path}")
    league = build_league(engine, seed)
    evaluation = evaluate(env, policy, league, 0, eval_games) if eval_games else []
    art = artifact.RunArtifact(
        kind="imitate",
        slug=f"imitate-{scenario}",
        config={
            "scenario": scenario,
            **board_record,
            "agent_a": "learner",
            "agent_b": "league",
            "teachers": teachers,
            "games": games,
            "first_seed": seed,
            "fit": config.to_dict(),
            "net": net.to_dict(),
            "device": str(compute),
            "parameters": sum(p.numel() for p in policy.parameters()),
            "snapshot": str(path),
            "criteria": ["TC-18"],
        },
    )
    art.seeds = [seed]
    art.stats = {
        "decisions": len(data),
        "games": data.games,
        "teacher_results": data.results,
        "collect_seconds": round(collected, 1),
        "fit_seconds": round(fitted, 1),
        "epochs": rows,
        "evaluation": evaluation,
        "passed": {"TC-18": bool(evaluation) and any(row["beats_opponent"] for row in evaluation)},
    }
    return art


def run(args: Any) -> int:
    teachers = [t.strip() for t in args.teachers.split(",") if t.strip()]
    config = imitate.FitConfig(
        epochs=args.epochs,
        minibatch=args.minibatch,
        learning_rate=args.learning_rate,
        value_coefficient=args.value_coefficient,
        holdout=args.holdout,
    )
    net = NetConfig(channels=args.channels, hidden=args.hidden)
    art = run_imitation(
        scenario=args.scenario,
        teachers=teachers,
        games=args.games,
        seed=args.seed,
        config=config,
        net=net,
        out=Path(args.out),
        eval_games=args.eval_games,
        device=args.device,
    )
    stats = art.stats
    print(f"device {art.config['device']}")
    for row in stats["evaluation"]:
        print(
            f"against {row['opponent']}: win rate {row['win_rate'] * 100:.1f} percent in {row['games']} games "
            f"({_counts(row['results'])}), "
            f"95 percent interval {row['confidence_low'] * 100:.1f} to {row['confidence_high'] * 100:.1f}"
        )
        for side, counts in row["by_side"].items():
            print(f"    as {side}: {_counts(counts)}")
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
    p = subparsers.add_parser("imitate", help="fit the learned agent to the decisions of the scripted agents, as the start of PPO")
    p.add_argument("--scenario", default="s01_guards_counterattack")
    p.add_argument("--teachers", default="v5,v6", help="a comma list of scripted agents; each ordered pair plays")
    p.add_argument("--games", type=int, default=100, help="games of the teachers against each other")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--minibatch", type=int, default=256)
    p.add_argument("--learning-rate", type=float, default=1e-3)
    p.add_argument("--value-coefficient", type=float, default=0.1, help="the weight of the value error in the loss")
    p.add_argument("--holdout", type=float, default=0.1, help="the share of the decisions held out of the fit")
    p.add_argument("--device", default="auto", help="auto, cpu, cuda, or cuda:0")
    p.add_argument("--channels", type=int, default=32, help="convolution channels of the board encoder")
    p.add_argument("--hidden", type=int, default=256, help="width of the trunk and the heads")
    p.add_argument("--out", default="runs/imitate/snapshot-0.pt", help="the snapshot file")
    p.add_argument("--eval-games", type=int, default=0, help="games against each constant opponent at the end (TC-18)")
    p.add_argument("--runs", default="runs")
    p.set_defaults(func=run)
