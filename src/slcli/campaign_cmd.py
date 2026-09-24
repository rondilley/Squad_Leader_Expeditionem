"""The campaign command: the design-your-own tools of Game Set IV (FR-17).

`sl-cli campaign --scenarios 6 --seed 11` plays one campaign and writes a run artifact
with the personnel file of each scenario.

`sl-cli campaign --draw 12` writes twelve random scenarios and says what each one is,
without playing any of them. That is the scenario set the owner asked for: a game does not
need the twelve printed cards to have twelve scenarios to play.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from slcampaign.build import build_scenario
from slcampaign.generator import draw_scenario
from slcampaign.ladder import Ladder
from slcampaign.run import counter_types, play_campaign, point_values
from slcli.play import make_agent, play_game
from slruns import artifact
from slruns.index import connect, upsert

DEFAULT_SCENARIOS = 6
DEFAULT_POINTS = 400


def draw_set(count: int, first_seed: int, points: int, out: Path | None) -> int:
    """Random scenario construction, `count` times. Nothing plays; each one is written."""
    types = counter_types()
    values = point_values(types)
    if out is not None:
        out.mkdir(parents=True, exist_ok=True)
    for step in range(count):
        seed = first_seed + step
        draw, defending, attacking = draw_scenario(seed, types, values, points)
        scenario = build_scenario(seed, draw, defending, attacking, types)
        squads = defending.squads(types), attacking.squads(types)
        print(
            f"{scenario.id}: {draw.attacker} attacks {draw.defender} on a {draw.board_type} board, "
            f"{draw.turns} turns, {draw.victory_kind}"
        )
        print(
            f"    defence {draw.defender_points} points and {squads[0]} squads, "
            f"attack {draw.attacker_points} points and {squads[1]} squads"
        )
        print(f"    victory: {draw.victory_text}")
        if out is not None:
            document = {
                "id": scenario.id,
                "title": scenario.title,
                "notes": scenario.notes,
                "draw": draw.to_dict(),
                "defending": defending.to_dict(),
                "attacking": attacking.to_dict(),
            }
            (out / f"{scenario.id}.json").write_text(json.dumps(document, indent=1), encoding="utf-8")
    if out is not None:
        print(f"wrote {count} scenario records in {out}")
    return 0


def run_campaign(seed: int, scenarios: int, agent_a: str, agent_b: str, ladder: Ladder) -> artifact.RunArtifact:
    """One campaign, with a run artifact that holds the personnel file of each scenario."""
    art = artifact.RunArtifact(
        kind="campaign",
        slug=f"campaign-{seed}",
        config={
            "seed": seed,
            "scenarios": scenarios,
            "agents": [agent_a, agent_b],
            "ladder": ladder.to_dict(),
            "criteria": ["FR-17"],
        },
    )

    def agents(engine, game_seed):
        return (make_agent(agent_a, engine, game_seed, 0), make_agent(agent_b, engine, game_seed, 1))

    run = play_campaign(seed, agents, play_game, scenarios=scenarios, ladder=ladder)
    art.seeds = [r.seed for r in run.records]
    art.stats = run.to_dict()
    return art


def run(args: Any) -> int:
    if args.draw:
        return draw_set(args.draw, args.seed, args.points, Path(args.out) if args.out else None)
    ladder = Ladder(base_points=args.points, step=args.step)
    art = run_campaign(args.seed, args.scenarios, args.agent_a, args.agent_b, ladder)
    stats = art.stats
    leader = stats["leader"]
    print(f"campaign {args.seed}: {stats['scenarios_played']} scenarios, {stats['scenarios_won']} won")
    for record in stats["records"]:
        performance = record["performance"]
        print(
            f"  {record['index']}. {record['scenario']} seed {record['seed']} "
            f"defence {record['defence_points']} points: {record['result']}, "
            f"{record['starting_rank']} to {record['ending_rank']}, "
            f"elan {performance['elan']}, cowardice {performance['cowardice']}"
            + (", killed in action" if performance["killed"] else "")
        )
    print(
        f"{leader['name']} ends as {leader['title']} with {leader['carried_points']} points carried"
    )
    print(f"victory points {stats['victory_points']}")
    directory = art.write(args.runs)
    conn = connect(Path(args.runs) / "runs.sqlite")
    try:
        upsert(conn, directory)
    finally:
        conn.close()
    print(f"run artifact {directory}")
    return 0


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("campaign", help="random scenarios and the campaign game of Game Set IV")
    p.add_argument("--seed", type=int, default=1, help="the campaign seed, or the first scenario seed with --draw")
    p.add_argument("--scenarios", type=int, default=DEFAULT_SCENARIOS, help="how many scenarios in the campaign")
    p.add_argument("--draw", type=int, default=0, help="draw this many scenarios and play none of them")
    p.add_argument("--points", type=int, default=DEFAULT_POINTS, help="the point total of the first defence")
    p.add_argument("--step", type=int, default=Ladder().step, help="how much a win moves the next defence")
    p.add_argument("--agent-a", default="v2")
    p.add_argument("--agent-b", default="v1")
    p.add_argument("--out", default=None, help="with --draw, the directory for the scenario records")
    p.add_argument("--runs", default="runs")
    p.set_defaults(func=run)
