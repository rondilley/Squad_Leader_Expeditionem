"""Command payloads and their canonical form (ARCHITECTURE section 3.4).

A command is one player intent. Its canonical payload is a small record with
sorted keys and no white space, so the same intent has the same bytes in
Python, in Rust, and in the browser.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Mapping

from slcore import geometry
from slcore.geometry import HexRef

ACTIONS = (
    "place",
    "place_weapon",
    "end_setup",
    "end_phase",
    "move",
    "stack_move",
    "pickup",
    "drop",
    "advance",
    "group_add",
    "group_add_weapon",
    "group_leader",
    "group_fire",
    "track_return",
    "rout",
    "stay",
    "rally",
    "repair",
    "cc_attack",
    "place_concealment",
    "place_smoke",
    "place_demo",
    "explode_demo",
    "ft_fire",
    "sewer_move",
    "sewer_return",
    # Rules 28 to 41, the armor game.
    "vehicle_move",
    "vehicle_pivot",
    "board",
    "debark",
    "afv_fire",
    "afv_mg",
    "at_fire",
    "afv_attack",
    "cc_afv",
    "afv_repair",
    "push_wreck",
    "afv_smoke",
    "afv_dischargers",
)


@dataclass(frozen=True)
class Command:
    action: str
    units: tuple[int, ...] = ()
    hex: HexRef | None = None
    weapon: int | None = None
    extra: tuple[tuple[str, Any], ...] = field(default_factory=tuple)

    def payload(self) -> dict[str, Any]:
        """The canonical record of the command. A sequence value is a list in the payload."""
        d: dict[str, Any] = {"action": self.action}
        if self.units:
            d["units"] = sorted(self.units)
        if self.hex is not None:
            d["hex"] = geometry.hex_id(*self.hex)
        if self.weapon is not None:
            d["weapon"] = self.weapon
        for k, v in self.extra:
            d[k] = list(v) if isinstance(v, tuple) else v
        return d

    @staticmethod
    def from_payload(d: Mapping[str, Any]) -> "Command":
        known = {"action", "units", "hex", "weapon"}
        extra = tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in d.items() if k not in known))
        return Command(
            action=str(d["action"]),
            units=tuple(sorted(int(u) for u in d.get("units", []))),
            hex=None if d.get("hex") is None else geometry.parse_hex_id(str(d["hex"])),
            weapon=None if d.get("weapon") is None else int(d["weapon"]),
            extra=extra,
        )

    @property
    def id(self) -> str:
        return _id_of(self.action, self.units, self.hex, self.weapon, self.extra)


def canonical_bytes(payload: Mapping[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def command_id(payload: Mapping[str, Any]) -> str:
    """The first 64 bits of SHA-256 of the canonical payload, as 16 hex digits."""
    return hashlib.sha256(canonical_bytes(payload)).hexdigest()[:16]


@lru_cache(maxsize=1 << 17)
def _id_of(action: str, units: tuple[int, ...], hex_ref: HexRef | None, weapon: int | None, extra: tuple[tuple[str, Any], ...]) -> str:
    """The ID of a command from its fields. The same command gives the same ID."""
    return command_id(Command(action, units, hex_ref, weapon, extra).payload())


END_PHASE = Command("end_phase")
END_SETUP = Command("end_setup")
