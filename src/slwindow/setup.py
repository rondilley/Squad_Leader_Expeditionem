"""The set up tray of the windows: one model, and no game library in it.

While the side of a person sets up, a window shows a tray with a picture of each counter
of that side (`slwindow.traydraw` draws it, in the 2D and the 3D window). This module
holds what the tray shows and what a click does, so a test reads it with no screen:

- the items of the tray: each counter of the side, with its place state. A counter that
  is on the board is in the tray too, so the person can take it back and place it again.
- the offered counter of an item. Rule 21.2 with PR-06 offers the lowest ID of each type,
  so a click on the second 4-4-7 of a stack of identical counters selects the one that
  the legal list names.
- the targets of a counter: the hexes where the legal list lets it go. A weapon goes to
  a unit that is already on the board and can carry it (`place_weapon`), and the hex of
  that unit is its target. A weapon goes on a hex alone only when no unit can carry it.

The model reads the legal list and the view that the host sent, and nothing else. It
applies no rule and holds no rule table (AR-06): a hex is a target only because a legal
entry names it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from slwindow.overlay import hexes_of, payload_of

SETUP_PHASE = "setup"
PLACE_ACTIONS = ("place", "place_weapon", "place_concealment")
END_SETUP = "end_setup"
# The tray item of a concealment counter (rule 25.6) has this ID, because it is no unit.
CONCEALMENT = -1

# The order of the tray: the leaders, the squads, the weapons, then the vehicles.
_KIND_ORDER = {"leader": 0, "squad": 1, "crew": 2, "sw": 3, "vehicle": 4}


@dataclass(frozen=True)
class TrayItem:
    """One counter of the tray. `offered` is the unit the legal list names for it now, or
    None when it cannot go on the board in this step (a counter of a later set up pass)."""

    unit_id: int
    unit: dict[str, Any] | None
    placed: bool
    offered: int | None

    @property
    def hex(self) -> str | None:
        return None if self.unit is None else self.unit.get("hex")


def setup_entries(legal: Sequence[dict[str, Any]]) -> list[int]:
    """The indexes of the place entries of the legal list."""
    return [i for i, entry in enumerate(legal) if payload_of(entry).get("action") in PLACE_ACTIONS]


def is_setup(snapshot: Any) -> bool:
    """True while the person at this window sets up a side: the frame is in the set up
    phase and its legal list has a place entry or the end of the set up."""
    if str(getattr(snapshot, "phase", "")) != SETUP_PHASE:
        return False
    legal = list(getattr(snapshot, "legal", None) or [])
    return any(payload_of(e).get("action") in PLACE_ACTIONS + (END_SETUP,) for e in legal)


def _acting(entry: dict[str, Any]) -> int | None:
    """The counter a place entry puts on the board."""
    payload = payload_of(entry)
    action = payload.get("action")
    if action == "place_weapon":
        weapon = payload.get("weapon")
        return None if weapon is None else int(weapon)
    if action == "place":
        units = payload.get("units") or []
        return int(units[0]) if units else None
    if action == "place_concealment":
        return CONCEALMENT
    return None


def _units(view: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    if not isinstance(view, dict):
        return {}
    return {int(u["id"]): u for u in view.get("units", []) or [] if isinstance(u, dict) and u.get("id") is not None}


def _same_counter(a: dict[str, Any], b: dict[str, Any]) -> bool:
    return a.get("type") == b.get("type") and a.get("nationality") == b.get("nationality") and a.get("kind") == b.get("kind")


def offered_id(view: dict[str, Any] | None, legal: Sequence[dict[str, Any]], unit_id: int) -> int | None:
    """The unit of the legal list for a click on this counter: the counter itself when
    the list names it, else an identical counter that the list names (PR-06)."""
    named = [_acting(legal[i]) for i in setup_entries(legal)]
    named_ids = {n for n in named if n is not None}
    if unit_id in named_ids:
        return unit_id
    units = _units(view)
    unit = units.get(unit_id)
    if unit is None:
        return None
    for other in sorted(named_ids):
        candidate = units.get(other)
        if candidate is not None and candidate.get("hex") is None and _same_counter(unit, candidate):
            return other
    return None


def tray(view: dict[str, Any] | None, legal: Sequence[dict[str, Any]]) -> list[TrayItem]:
    """The counters of the side that sets up, the ones to place first. A weapon that a
    unit carries is on the board with that unit."""
    own = [u for u in _units(view).values() if u.get("own")]
    items = []
    for unit in own:
        unit_id = int(unit["id"])
        placed = unit.get("hex") is not None
        items.append(TrayItem(unit_id, unit, placed, None if placed else offered_id(view, legal, unit_id)))
    if any(_acting(legal[i]) == CONCEALMENT for i in setup_entries(legal)):
        items.append(TrayItem(CONCEALMENT, None, False, CONCEALMENT))
    items.sort(key=lambda item: (item.placed, _KIND_ORDER.get(str((item.unit or {}).get("kind")), 9), item.unit_id))
    return items


def targets(legal: Sequence[dict[str, Any]], unit_id: int, view: dict[str, Any] | None = None) -> dict[str, list[int]]:
    """The hexes where the legal list lets this counter go, each with its legal indexes.
    `unit_id` is the offered unit (see `offered_id`).

    A weapon goes to a unit that carries it: its targets are the hexes of the units that
    the legal list lets carry it (`place_weapon`). A weapon alone on a hex cannot move
    until a unit picks it up, so the tray offers that only when no unit of the side can
    carry it and no unit is left to place. With the view and a unit of the side still off
    the board, a weapon with no carrier has no target yet (see `weapon_step`).
    """
    out: dict[str, list[int]] = {}
    for index in setup_entries(legal):
        entry = legal[index]
        if _acting(entry) != unit_id:
            continue
        for hex_id in hexes_of(entry):
            out.setdefault(str(hex_id), []).append(index)
    step = weapon_step(view, legal, unit_id) if view is not None else _weapon_step_of_list(legal, unit_id)
    if step == WEAPON_CARRY:
        return {h: [i for i in found if payload_of(legal[i]).get("action") == "place_weapon"] for h, found in out.items() if any(payload_of(legal[i]).get("action") == "place_weapon" for i in found)}
    if step == WEAPON_WAIT:
        return {}
    return out


# The set up step of a weapon of the tray: a unit on the board can carry it, a unit of the
# side is still to place first, or no unit can carry it and it goes on a hex alone.
WEAPON_CARRY = "carry"
WEAPON_WAIT = "wait"
WEAPON_ALONE = "alone"


def _weapon_step_of_list(legal: Sequence[dict[str, Any]], unit_id: int) -> str | None:
    gifts = [i for i in setup_entries(legal) if _acting(legal[i]) == unit_id and payload_of(legal[i]).get("action") == "place_weapon"]
    return WEAPON_CARRY if gifts else None


def weapon_step(view: dict[str, Any] | None, legal: Sequence[dict[str, Any]], unit_id: int) -> str | None:
    """The set up step of a weapon (the offered unit), or None for a counter that is not
    a weapon."""
    unit = _units(view).get(unit_id)
    if unit is None or unit.get("kind") != "sw":
        return _weapon_step_of_list(legal, unit_id)
    if _weapon_step_of_list(legal, unit_id) == WEAPON_CARRY:
        return WEAPON_CARRY
    waiting = [u for u in _units(view).values() if u.get("own") and u.get("kind") in ("squad", "leader", "crew") and u.get("hex") is None]
    return WEAPON_WAIT if waiting else WEAPON_ALONE


def carrier_of(view: dict[str, Any] | None, unit_id: int) -> dict[str, Any] | None:
    """The unit that carries this weapon, or None."""
    units = _units(view)
    unit = units.get(unit_id)
    carrier = None if unit is None else unit.get("carrier")
    return None if carrier is None else units.get(int(carrier))


def can_finish(legal: Sequence[dict[str, Any]]) -> int | None:
    """The index of the end of the set up, when the legal list has it."""
    for index, entry in enumerate(legal):
        if payload_of(entry).get("action") == END_SETUP:
            return index
    return None


def counts(items: Sequence[TrayItem]) -> tuple[int, int]:
    """How many counters are on the board, and how many the side has."""
    real = [item for item in items if item.unit is not None]
    return sum(1 for item in real if item.placed), len(real)


def item_label(view: dict[str, Any] | None, legal: Sequence[dict[str, Any]], item: TrayItem) -> str:
    """The short text below a counter of the tray."""
    carrier = carrier_of(view, item.unit_id) if item.unit is not None else None
    if carrier is not None:
        return f"with {carrier.get('type', '')}"
    if item.placed:
        return f"in {item.hex}"
    if item.offered is None:
        return "later"
    if weapon_step(view, legal, item.offered) == WEAPON_WAIT:
        return "units first"
    return "to place"


def hint(view: dict[str, Any] | None, legal: Sequence[dict[str, Any]], selected: int | None) -> str:
    """The line of the tray that says what to do with the selected counter."""
    if selected is None:
        return "Click or drag a counter to a shaded hex."
    unit = _units(view).get(selected)
    if unit is None or unit.get("kind") != "sw":
        return "Click or drag it to a shaded hex. Right click a counter to read about it."
    name = unit.get("type", "the weapon")
    carrier = carrier_of(view, selected)
    if carrier is not None:
        return f"The {carrier.get('type', '')} carries the {name}: it moves with it. Click the {name} to take it back."
    offered = offered_id(view, legal, selected)
    step = None if offered is None else weapon_step(view, legal, offered)
    if step == WEAPON_CARRY:
        return f"Drag the {name} onto a shaded unit. That unit carries it and moves with it."
    if step == WEAPON_WAIT:
        return f"Place your squads and leaders first. Then drag the {name} onto one of them."
    return f"No unit can carry the {name}. Put it on a hex: a unit must pick it up to move it."
