"""Headless games from the command line (FR-40), with the command log (DR-04)."""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slagents.base import Agent, RandomAgent
from slagents.scripted.v0 import ScriptedV0
from slagents.scripted.v1 import ScriptedV1
from slagents.scripted.v2 import ScriptedV2
from slagents.scripted.v3 import ScriptedV3
from slagents.tuned.traces import TraceWriter, board_source
from slcore.commands import Command
from slcore.engine import Engine
from slcore.events import Event
from slcore.game import State
from slboards.reference import source_of
from sldata.loaders import DataError, board_and_parameters, load_all_counters, load_board, load_hexsides, load_scenario, load_tables, load_terrain

MAX_COMMANDS = 20000


@dataclass
class GameRecord:
    seed: int
    scenario: str
    board: str
    agents: tuple[str, str]
    commands: list[dict[str, Any]]
    hashes: list[str]
    events: list[dict[str, Any]]
    result: str
    result_cause: str
    turns_played: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "scenario": self.scenario,
            "board": self.board,
            "agents": list(self.agents),
            "commands": self.commands,
            "hashes": self.hashes,
            "events": self.events,
            "result": self.result,
            "result_cause": self.result_cause,
            "turns_played": self.turns_played,
            "platform": platform.platform(),
        }


def build_engine(scenario_name: str, board_name: str | None = None) -> Engine:
    engine, _ = build_engine_with_record(scenario_name, board_name)
    return engine


RANDOM_PREFIX = "random:"


def random_scenario(name: str):
    """A scenario that the random construction of Game Set IV builds from a seed (FR-17).

    `random:500` is a scenario the same way `s01_guards_counterattack` is one. It has no
    file, because the seed is the whole record: the draws, the two forces, and the board
    all come from it.
    """
    from slcampaign.build import build_scenario
    from slcampaign.generator import draw_scenario
    from slcampaign.run import counter_types, point_values

    text = name[len(RANDOM_PREFIX) :]
    try:
        seed = int(text)
    except ValueError as exc:
        raise DataError(f"a random scenario needs a seed, and {text!r} is not one") from exc
    types = counter_types()
    draw, defending, attacking = draw_scenario(seed, types, point_values(types))
    return build_scenario(seed, draw, defending, attacking, types)


def build_engine_with_record(
    scenario_name: str, board_name: str | None = None
) -> tuple[Engine, dict[str, Any]]:
    """The engine and the record of the board it plays on (FR-25).

    The record goes in the run artifact, so that a later session builds the same board
    from the same parameters. A board from the reference directory carries its source
    tag and no parameters, because the project does not ship that layout (DR-06).

    A name that starts with `random:` is a scenario of Game Set IV, built from the seed
    that follows the prefix, and not a file in `sldata/scenarios`.
    """
    if scenario_name.startswith(RANDOM_PREFIX):
        scenario = random_scenario(scenario_name)
    else:
        scenario = load_scenario(scenario_name)
    terrain = load_terrain()
    if board_name:
        board = load_board(board_name, terrain)
        params = None
    else:
        board, params = board_and_parameters(scenario, terrain)
    record: dict[str, Any] = {
        "board": board.name,
        "board_source": source_of(board),
        "board_columns": list(scenario.board_columns) if scenario.board_columns else None,
        "generator": params.to_dict() if params is not None else None,
    }
    engine = Engine(scenario, board, terrain, load_hexsides(), load_all_counters(), load_tables())
    return engine, record


def make_agent(kind: str, engine: Engine, seed: int, player: int) -> Agent:
    if kind == "random":
        return RandomAgent(seed, player)
    if kind == "v0":
        return ScriptedV0(engine, player)
    if kind == "v1":
        return ScriptedV1(engine, player)
    if kind == "v2":
        return ScriptedV2(engine, player)
    if kind == "v3":
        return ScriptedV3(engine, player)
    if kind.startswith("model:"):
        return make_model_agent(kind.split(":", 1)[1], engine, seed, player)
    if kind.startswith("tuned:"):
        return make_model_agent(kind.split(":", 1)[1], engine, seed, player, tuned=True)
    raise ValueError(
        f"unknown agent kind {kind!r}; use random, v0, v1, v2, v3, model:<providers>, or tuned:<providers>"
    )


def make_model_agent(providers: str, engine: Engine, seed: int, player: int, tuned: bool = False) -> Agent:
    """A model agent (FR-45). The name is a sequence, so `model:local+openai` fails over.

    The tuned family is the same harness with the constraint of FR-62 on: the provider
    holds the model to the schema, whose command field is the enum of the legal identities.
    """
    from slagents.prompted.harness import PromptedAgent
    from slagents.prompted.providers import make_provider
    from slagents.prompted.router import Router

    names = [name for name in providers.split("+") if name]
    if not names:
        raise ValueError("a model agent needs one provider name or more, as model:local+openai")
    clients = [make_provider(name) for name in names]
    client = clients[0] if len(clients) == 1 else Router(clients)
    agent = PromptedAgent(engine, player, client, ScriptedV1(engine, player), constrained=tuned)
    if tuned:
        agent.name = "tuned"
    return agent


def play_game(
    engine: Engine,
    seed: int,
    agents: tuple[Agent, Agent],
    max_commands: int = MAX_COMMANDS,
    traces: TraceWriter | None = None,
) -> GameRecord:
    """One headless game. With a trace writer, each decision goes in the data set (FR-60).

    The writer reads the view of the acting player only, so a trace never holds the state
    of the other side (SR-09).
    """
    state: State = engine.new_game(seed)
    commands: list[dict[str, Any]] = []
    hashes: list[str] = []
    events_out: list[dict[str, Any]] = []
    while not state.game_over and len(commands) < max_commands:
        frame = engine.legal_commands(state)
        if not frame.commands:
            raise RuntimeError(f"no legal command in {state.phase}/{frame.sub_step} for player {state.active}")
        chosen = agents[state.active].select(state, frame)
        legal = frame.by_id(chosen)
        if legal is None:
            raise RuntimeError(f"agent {agents[state.active].name} gave an ID that is not in the frame")
        before = state
        state, events = engine.apply(state, legal.command, frame)
        if traces is not None:
            traces.add(engine, before, frame, agents[frame.player], legal.id, events)
        h = engine.hash_state(state)
        commands.append({"seq": state.seq, "player": frame.player, "phase": frame.phase, "frame_id": frame.frame_id, "command_id": legal.id, "payload": legal.payload, "hash": h})
        hashes.append(h)
        events_out.extend(e.to_dict() for e in events)
    if not state.game_over:
        raise RuntimeError(f"game did not end within {max_commands} commands")
    if traces is not None:
        traces.finish(state.result)
    return GameRecord(seed, engine.scenario.id, engine.board.name, (agents[0].name, agents[1].name), commands, hashes, events_out, state.result, state.result_cause, state.turn - 1)


def trace_writer(engine: Engine, seed: int, agents: tuple[Agent, Agent]) -> TraceWriter:
    """A writer for one game, with the game identity and the board source (DR-08, SR-10)."""
    name = f"{engine.scenario.id}-{seed}-{agents[0].name}-{agents[1].name}"
    return TraceWriter(game_id=name, board_source=board_source(engine))


def replay_record(engine: Engine, record: GameRecord) -> bool:
    hashes = engine.replay(record.seed, [c["payload"] for c in record.commands])
    return hashes == record.hashes


def write_record(record: GameRecord, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(record.to_dict(), indent=1), encoding="utf-8")
    except OSError as exc:
        raise DataError(f"cannot write {path}: {exc}") from exc


def run(args: Any) -> int:
    engine = build_engine(args.scenario, args.board)
    for i in range(args.games):
        seed = args.seed + i
        agents = (make_agent(args.agent_a, engine, seed, 0), make_agent(args.agent_b, engine, seed, 1))
        writer = trace_writer(engine, seed, agents) if args.traces else None
        record = play_game(engine, seed, agents, traces=writer)
        ok = replay_record(engine, record) if args.verify else None
        line = f"game {i + 1}/{args.games} seed {seed}: {len(record.commands)} commands, {record.turns_played} turns, result {record.result}, last hash {record.hashes[-1][:16]}"
        if ok is not None:
            line += f", replay {'agrees' if ok else 'DISAGREES'}"
        print(line)
        if args.out:
            write_record(record, Path(args.out) / f"game_{seed}.json")
        if writer is not None:
            path = writer.write(args.traces, f"traces_{seed}.json")
            print(f"  {len(writer.records)} trace records in {path} ({writer.board_source})")
        if ok is False:
            return 1
    return 0


def format_events(events: list[Event]) -> str:
    return "\n".join(f"[{e.rule_id}] {e.kind} {json.dumps(e.data, sort_keys=True)}" for e in events)


def add_parser(subparsers: Any) -> None:
    p = subparsers.add_parser("play", help="play headless games and write the command log")
    p.add_argument("--scenario", default="s00_movement_drill")
    p.add_argument("--board", default=None)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--games", type=int, default=1)
    p.add_argument("--agent-a", default="v1", choices=("random", "v0", "v1", "v2", "v3"))
    p.add_argument("--agent-b", default="v1", choices=("random", "v0", "v1", "v2", "v3"))
    p.add_argument("--headless", action="store_true", help="accepted for the documented command line; play is headless only in v0.1")
    p.add_argument("--verify", action="store_true", help="replay each game and compare the hash sequence")
    p.add_argument("--out", default=None, help="directory for the game records")
    p.add_argument("--traces", default=None, help="directory for the trace records of each decision (FR-60)")
    p.set_defaults(func=run)
