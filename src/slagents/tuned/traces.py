"""The trace writer (FR-60, DR-08, SR-09, SR-10).

One trace record is one decision: what the acting agent could see, what it could do, what
it did, and what came of it. The data set of those records is the training target of the
tuned model agent in v0.4.

Three rules shape the record and none of them is negotiable.

- The view is the view of the acting agent and of nobody else (SR-09). The writer calls
  the same `slcore.view.build` that the host sends to a player, so a trace cannot hold a
  unit that the player is not allowed to see. Rule 25.2 is the reason: a concealed stack
  is a token in that view, and a trace that held the units below it would teach the model
  to see through concealment.
- The record says where the board came from (SR-10). A game on a layout from the owner's
  reference directory carries `board_source = "reference_private"`, and the fine-tune
  command refuses those records without an explicit local-only flag.
- The record holds no key, no header, and no state of the other side (SR-09).

The view text is the compact form a language model reads. It is deterministic: the same
view gives the same text, so a trace built two times is the same trace.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from slcore import geometry, view as view_module
from slcore.engine import Engine
from slcore.frame import DecisionFrame
from slcore.game import State

TRACES_FILE = "traces.json"
FORMAT_VERSION = 1
SOURCE_GENERATED = "generated"
SOURCE_REFERENCE = "reference_private"
UNKNOWN_OUTCOME = "unknown"


class TraceError(Exception):
    """A trace could not be written or read."""


@dataclass(frozen=True)
class TraceRecord:
    """One decision, in the fields that DR-08 names."""

    game_id: str
    decision: int
    family: str
    version: str
    player: int
    side: str
    phase: str
    sub_step: str
    turn: int
    view_text: str
    legal_command_ids: tuple[str, ...]
    selected_command_id: str
    selected_payload: Mapping[str, Any]
    outcome: tuple[str, ...]
    board_source: str
    result: str = UNKNOWN_OUTCOME

    def to_dict(self) -> dict[str, Any]:
        return {
            "game_id": self.game_id,
            "decision": self.decision,
            "family": self.family,
            "version": self.version,
            "player": self.player,
            "side": self.side,
            "phase": self.phase,
            "sub_step": self.sub_step,
            "turn": self.turn,
            "view_text": self.view_text,
            "legal_command_ids": list(self.legal_command_ids),
            "selected_command_id": self.selected_command_id,
            "selected_payload": dict(self.selected_payload),
            "outcome": list(self.outcome),
            "board_source": self.board_source,
            "result": self.result,
        }

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "TraceRecord":
        return TraceRecord(
            game_id=str(d["game_id"]),
            decision=int(d["decision"]),
            family=str(d["family"]),
            version=str(d["version"]),
            player=int(d["player"]),
            side=str(d["side"]),
            phase=str(d["phase"]),
            sub_step=str(d["sub_step"]),
            turn=int(d["turn"]),
            view_text=str(d["view_text"]),
            legal_command_ids=tuple(str(x) for x in d["legal_command_ids"]),
            selected_command_id=str(d["selected_command_id"]),
            selected_payload=dict(d["selected_payload"]),
            outcome=tuple(str(x) for x in d.get("outcome", [])),
            board_source=str(d["board_source"]),
            result=str(d.get("result", UNKNOWN_OUTCOME)),
        )


def board_source(engine: Engine) -> str:
    """SR-10: which kind of board this game is on."""
    from slboards.reference import source_of

    return source_of(engine.board)


def view_text(engine: Engine, state: State, player: int) -> str:
    """The compact text of one player's view (FR-45 in v0.4, and the trace field here).

    The text has one line for each thing the player may know: the turn and the phase, the
    player's own units with their state, the opponent units the view holds, the
    concealment counters as tokens, and the smoke. It never has a unit that the view of
    that player does not hold.
    """
    document = view_module.build(state, engine.types, player)
    side = engine.scenario.players()[player]
    lines = [
        f"turn {document['turn']} of {document['turn_limit']} phase {document['phase']} "
        f"side {side} player {player}"
    ]
    own: list[str] = []
    other: list[str] = []
    for unit in document["units"]:
        if unit["hex"] is None and unit["carrier"] is None:
            continue
        text = _unit_text(unit)
        (own if unit["own"] else other).append(text)
    lines.append("own: " + ("; ".join(sorted(own)) if own else "none"))
    lines.append("enemy seen: " + ("; ".join(sorted(other)) if other else "none"))
    # One entry for each hex, because the stack count is already in the token (rule 25.7).
    by_hex = {c["hex"]: c for c in document["concealment"]}
    counters = [
        f"{h}x{c['stack']}" + ("(own)" if c["own"] else "") for h, c in sorted(by_hex.items())
    ]
    lines.append("concealment: " + ("; ".join(counters) if counters else "none"))
    lines.append("smoke: " + ("; ".join(sorted(document["smoke"])) if document["smoke"] else "none"))
    if document["melee"]:
        lines.append("melee: " + "; ".join(sorted(document["melee"])))
    return "\n".join(lines)


def _unit_text(unit: Mapping[str, Any]) -> str:
    where = unit["hex"] if unit["hex"] is not None else f"carried by {unit['carrier']}"
    marks = [name for name in ("broken", "berserk", "moved", "prep_fired", "malfunction", "dm") if unit[name]]
    tail = " " + ",".join(marks) if marks else ""
    name = f" {unit['name']}" if unit["name"] else ""
    return f"{unit['id']}:{unit['type']}{name}@{where}{tail}"


def outcome_of(events: Iterable[Any]) -> tuple[str, ...]:
    """The immediate result of one command, as rule and kind pairs from the action log."""
    out: list[str] = []
    for event in events:
        rule = event.rule_id if hasattr(event, "rule_id") else event["rule_id"]
        kind = event.kind if hasattr(event, "kind") else event["kind"]
        out.append(f"{rule}:{kind}")
    return tuple(out)


@dataclass
class TraceWriter:
    """The records of one game, and the file they go to.

    The writer holds the records in memory and writes them one time, because a game is
    short and a partial file is worse than no file.
    """

    game_id: str
    board_source: str
    records: list[TraceRecord] = field(default_factory=list)

    def add(
        self,
        engine: Engine,
        state: State,
        frame: DecisionFrame,
        agent: Any,
        command_id: str,
        events: Iterable[Any],
    ) -> TraceRecord:
        """One decision of the acting player, from that player's view alone (SR-09)."""
        player = frame.player
        legal = frame.by_id(command_id)
        if legal is None:
            raise TraceError(f"the command {command_id} is not in the frame of decision {len(self.records)}")
        record = TraceRecord(
            game_id=self.game_id,
            decision=len(self.records),
            family=getattr(agent, "name", "unknown"),
            version=str(getattr(agent, "version", "0")),
            player=player,
            side=engine.scenario.players()[player],
            phase=frame.phase,
            sub_step=frame.sub_step,
            turn=frame.turn,
            view_text=view_text(engine, state, player),
            legal_command_ids=tuple(lc.id for lc in frame.commands),
            selected_command_id=command_id,
            selected_payload=legal.payload,
            outcome=outcome_of(events),
            board_source=self.board_source,
        )
        self.records.append(record)
        return record

    def finish(self, result: str) -> None:
        """The result of the game goes on each record, which is the training label."""
        from dataclasses import replace

        self.records = [replace(r, result=result) for r in self.records]

    def to_dict(self) -> dict[str, Any]:
        return {
            "format": FORMAT_VERSION,
            "game_id": self.game_id,
            "board_source": self.board_source,
            "records": [r.to_dict() for r in self.records],
        }

    def write(self, directory: str | Path, name: str = TRACES_FILE) -> Path:
        path = Path(directory) / name
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(self.to_dict(), indent=1), encoding="utf-8")
        except OSError as exc:
            raise TraceError(f"cannot write the traces in {path}: {exc}") from exc
        return path


def read(path: str | Path) -> list[TraceRecord]:
    """The records of one trace file."""
    p = Path(path)
    try:
        doc = json.loads(p.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TraceError(f"there is no trace file at {p}") from exc
    except OSError as exc:
        raise TraceError(f"cannot read {p}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise TraceError(f"{p} is not valid JSON: {exc}") from exc
    return [TraceRecord.from_dict(r) for r in doc.get("records", [])]


def generated_only(records: Sequence[TraceRecord]) -> list[TraceRecord]:
    """SR-10: the records a build may use without the owner's local-only flag."""
    return [r for r in records if r.board_source == SOURCE_GENERATED]


def private_count(records: Sequence[TraceRecord]) -> int:
    return sum(1 for r in records if r.board_source == SOURCE_REFERENCE)
