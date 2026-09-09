"""Events with rule IDs (FR-02, FR-06). The action log is the event list."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Event:
    rule_id: str
    kind: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"rule_id": self.rule_id, "kind": self.kind, "data": dict(self.data)}
