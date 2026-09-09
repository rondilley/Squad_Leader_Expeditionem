"""The decision frame (ARCHITECTURE section 3.4).

A frame is what the host, the trainer, the harness, the trace writer, and
the replay tool share: the frame ID, the active player, the phase and
sub-step, and the legal commands with their canonical payloads and IDs.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from slcore.commands import Command


@dataclass(frozen=True)
class LegalCommand:
    id: str
    command: Command

    @property
    def payload(self) -> dict[str, Any]:
        return self.command.payload()


@dataclass(frozen=True)
class DecisionFrame:
    frame_id: str
    player: int
    phase: str
    sub_step: str
    turn: int
    commands: tuple[LegalCommand, ...]

    def by_id(self, command_id: str) -> LegalCommand | None:
        for lc in self.commands:
            if lc.id == command_id:
                return lc
        return None

    def ids(self) -> tuple[str, ...]:
        return tuple(lc.id for lc in self.commands)

    def to_dict(self) -> dict[str, Any]:
        return {
            "frame_id": self.frame_id,
            "player": self.player,
            "phase": self.phase,
            "sub_step": self.sub_step,
            "turn": self.turn,
            "commands": [{"id": lc.id, "payload": lc.payload} for lc in self.commands],
        }


def make_frame(frame_id: str, player: int, phase: str, sub_step: str, turn: int, commands: list[Command]) -> DecisionFrame:
    seen: set[str] = set()
    legal: list[LegalCommand] = []
    for c in commands:
        cid = c.id
        if cid in seen:
            continue
        seen.add(cid)
        legal.append(LegalCommand(cid, c))
    return DecisionFrame(frame_id, player, phase, sub_step, turn, tuple(legal))
