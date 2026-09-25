"""Headless games from the command line (FR-40), with the command log (DR-04)."""

from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from slagents.base import Agent, decide
from slagents.registry import (  # noqa: F401  re-exported for the callers of slcli.play
    LEARNED_PREFIX,
    RANDOM_PREFIX,
    LearnedNotInstalled,
    build_engine,
    build_engine_with_record,
    make_agent,
    make_learned_agent,
    make_model_agent,
    random_scenario,
)
from slagents.tuned.traces import TraceWriter, board_source
from slcore.engine import Engine
from slcore.events import Event
from slcore.game import State
from sldata.loaders import DataError

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
        chosen = decide(agents[state.active], state, frame)
        legal = frame.by_id(chosen)
        if legal is None:
            raise RuntimeError(f"agent {agents[state.active].name} gave an ID that is not in the frame")
        before = state
        state, events = engine.apply(state, legal.command, frame)
        if traces is not None:
            traces.add(engine, before, frame, agents[frame.player], legal.id, events, after=state)
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
    p.add_argument("--agent-a", default="v1")
    p.add_argument("--agent-b", default="v1")
    p.add_argument("--headless", action="store_true", help="accepted for the documented command line; play is headless only in v0.1")
    p.add_argument("--verify", action="store_true", help="replay each game and compare the hash sequence")
    p.add_argument("--out", default=None, help="directory for the game records")
    p.add_argument("--traces", default=None, help="directory for the trace records of each decision (FR-60)")
    p.set_defaults(func=run)
