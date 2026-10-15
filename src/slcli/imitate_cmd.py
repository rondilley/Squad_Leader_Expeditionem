"""The imitation command: a policy that copies the scripted agents, as the start of PPO.

`sl-cli imitate --scenario s01_guards_counterattack --teachers v4,v5,v6 --labels 0=v5,1=v6
--games 300 --dagger-rounds 3` plays the games of the teacher pool, fits the policy to the
label teacher of each side, then plays three rounds of the policy's own games with the
label teacher's answer at each state and fits again on the whole. It writes the snapshot
and evaluates it against the constant opponents of the league the way `sl-cli train` does
(TC-18). Then `sl-cli train --start-from <snapshot>` continues from it.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import torch

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
    labels: dict[int, str] | None = None,
    dagger_rounds: int = 0,
    dagger_games: int = 0,
    dagger_epochs: int = 0,
    dagger_mix: float = 0.0,
    workers: int = 1,
) -> artifact.RunArtifact:
    """The whole pass: the games, the fit, the DAgger rounds, the snapshot, and the evaluation.

    `labels` is the label teacher of each side; without it each teacher labels its own
    decisions. Each DAgger round plays `dagger_games` games of the policy against the pool,
    labels each state with the label teacher of its side, and fits `dagger_epochs` more
    epochs on everything collected so far. The rounds need the labels, because the policy's
    decision has no teacher of its own.
    """
    if dagger_rounds > 0 and labels is None:
        raise ValueError("the DAgger rounds need --labels, because the policy's own decisions have no teacher")
    from slagents.learned.workers import corrections_parallel, demonstrations_parallel

    engine, board_record = build_engine_with_record(scenario)
    env = make_env(engine, seed=seed)
    compute = ppo.resolve_device(device)
    policy = Policy(env.spaces_record, net).to(compute)
    generator = torch.Generator().manual_seed(seed)
    started = time.perf_counter()

    def make_teacher(kind: str, game_seed: int, player: int):
        return make_agent(kind, engine, game_seed, player)

    def on_game(game: int, a: str, b: str, result: float) -> None:
        if (game + 1) % 10 == 0 or game + 1 == games:
            log(f"game {game + 1}/{games}: {a} against {b}, result {result:+.0f}")

    if workers > 1:
        data = demonstrations_parallel(scenario, teachers, games, seed, workers, env.max_commands, labels, on_game)
    else:
        data = imitate.collect_demonstrations(env, make_teacher, teachers, games, seed, on_game, labels)
    collected = time.perf_counter() - started
    log(f"{len(data)} decisions from {data.games} games in {collected:.1f} s, results {data.results}")

    def on_epoch(epoch: int, row: dict[str, float]) -> None:
        log(
            f"epoch {epoch}: cross entropy {row['cross_entropy']:.3f}, value loss {row['value_loss']:.3f}, "
            f"holdout cross entropy {row['holdout_cross_entropy']:.3f}, holdout accuracy {row['holdout_accuracy'] * 100:.1f} percent"
        )

    def log_kept(fitted: list[dict[str, float]]) -> None:
        kept = [row for row in fitted if row.get("kept")]
        if kept:
            log(f"kept the weights of epoch {kept[0]['epoch']:.0f}, holdout cross entropy {kept[0]['holdout_cross_entropy']:.3f}")

    rows = imitate.fit(policy, data, config, env.spaces_record, seed, on_epoch)
    log_kept(rows)
    rounds: list[dict[str, Any]] = []
    for round_index in range(dagger_rounds):
        round_started = time.perf_counter()
        round_seed = seed + games + (round_index + 1) * dagger_games
        wins = [0, 0]
        played = [0, 0]

        def on_round_game(game: int, side: int, kind: str, result: float) -> None:
            played[side] += 1
            wins[side] += 1 if result > 0 else 0
            if (game + 1) % 10 == 0 or game + 1 == dagger_games:
                log(f"round {round_index + 1} game {game + 1}/{dagger_games}: policy as player {side} against {kind}, result {result:+.0f}")

        if workers > 1:
            fresh = corrections_parallel(
                scenario, policy, labels, teachers, dagger_games, round_seed, workers, env.max_commands, dagger_mix, on_round_game
            )
        else:
            fresh = imitate.collect_corrections(
                env, policy, make_teacher, labels, teachers, dagger_games, round_seed, generator, on_round_game, dagger_mix
            )
        data.extend(fresh)
        log(
            f"round {round_index + 1}: {len(fresh)} decisions from {fresh.games} games, the policy won "
            f"{wins[0]} of {played[0]} as player 0 and {wins[1]} of {played[1]} as player 1; {len(data)} decisions in all"
        )
        round_config = imitate.FitConfig(**{**config.to_dict(), "epochs": dagger_epochs or config.epochs})
        round_rows = imitate.fit(policy, data, round_config, env.spaces_record, round_seed, on_epoch)
        log_kept(round_rows)
        rows.extend(round_rows)
        rounds.append(
            {
                "round": round_index + 1,
                "games": fresh.games,
                "decisions": len(fresh),
                "policy_wins": wins,
                "policy_games": played,
                "seconds": round(time.perf_counter() - round_started, 1),
                "epochs": round_rows,
            }
        )
    fitted = time.perf_counter() - started - collected
    record = {
        "scenario": scenario,
        "teachers": teachers,
        "labels": None if labels is None else {str(k): v for k, v in labels.items()},
        "games": data.games,
        "decisions": len(data),
        "seed": seed,
        "fit": config.to_dict(),
        "epochs": rows,
        "dagger": rounds,
    }
    path = imitate.save(policy, out, net, record)
    log(f"snapshot {path}")
    league = build_league(engine, seed)
    evaluation = evaluate(env, policy, league, 0, eval_games, workers, scenario, first_seed=seed) if eval_games else []
    art = artifact.RunArtifact(
        kind="imitate",
        slug=f"imitate-{scenario}",
        config={
            "scenario": scenario,
            **board_record,
            "agent_a": "learner",
            "agent_b": "league",
            "teachers": teachers,
            "labels": None if labels is None else {str(k): v for k, v in labels.items()},
            "games": games,
            "dagger_rounds": dagger_rounds,
            "dagger_games": dagger_games,
            "dagger_mix": dagger_mix,
            "workers": workers,
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
        "dagger": rounds,
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
        stop_weight=args.stop_weight,
        side_weights=imitate.parse_side_weights(args.side_weights),
    )
    net = NetConfig(channels=args.channels, hidden=args.hidden)
    labels = imitate.parse_labels(args.labels) if args.labels else None
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
        labels=labels,
        dagger_rounds=args.dagger_rounds,
        dagger_games=args.dagger_games or max(1, args.games // 2),
        dagger_epochs=args.dagger_epochs,
        dagger_mix=args.dagger_mix,
        workers=args.workers,
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
    p.add_argument("--teachers", default="v4,v5,v6", help="a comma list of scripted agents; each ordered pair plays")
    p.add_argument(
        "--labels",
        default="",
        help="the teacher whose command labels each side, as 0=v3,1=v3; without it each teacher labels its own decisions",
    )
    p.add_argument("--games", type=int, default=100, help="games of the teachers against each other")
    p.add_argument("--dagger-rounds", type=int, default=0, help="rounds of the policy's own games with the teachers' labels")
    p.add_argument("--dagger-games", type=int, default=0, help="games in each round, default half of --games")
    p.add_argument("--dagger-epochs", type=int, default=0, help="epochs of the fit after each round, default --epochs")
    p.add_argument("--dagger-mix", type=float, default=0.0, help="the share of the policy's decisions the teacher plays in a round")
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--epochs", type=int, default=5)
    p.add_argument("--minibatch", type=int, default=256)
    p.add_argument("--learning-rate", type=float, default=1e-3)
    p.add_argument("--value-coefficient", type=float, default=0.1, help="the weight of the value error in the loss")
    p.add_argument("--holdout", type=float, default=0.1, help="the share of the decisions held out of the fit")
    p.add_argument(
        "--stop-weight",
        type=float,
        default=1.0,
        help="the weight of a decision that fires the group or ends a phase, against 1 for each other decision",
    )
    p.add_argument(
        "--side-weights",
        default="",
        help="the weight of the decisions of each side in the fit, as 0=1,1=0 for the decisions of player 0 only; default 1 each",
    )
    p.add_argument("--device", default="auto", help="auto, cpu, cuda, or cuda:0")
    from slcli.worker_limit import workers_argument

    p.add_argument("--workers", type=workers_argument, default=1, help="processes that play the games; 1 plays them in this process")
    p.add_argument("--channels", type=int, default=32, help="convolution channels of the board encoder")
    p.add_argument("--hidden", type=int, default=256, help="width of the trunk and the heads")
    p.add_argument("--out", default="runs/imitate/snapshot-0.pt", help="the snapshot file")
    p.add_argument("--eval-games", type=int, default=0, help="games against each constant opponent at the end (TC-18)")
    p.add_argument("--runs", default="runs")
    p.set_defaults(func=run)
