"""The action log for one player: no event names a unit that player could not see (AR-09).

The core gives each event with the IDs of the units it is about. The host sends the log
with each frame, and before this module it sent the same log to each seat. That told a
player where the other side set up a hidden unit (rule 42.1) and where a concealed unit
moved (rule 25.2), because the view hid the unit and the log named it.

The filter works when the host applies a command, not when it sends a frame. A unit that
the command eliminates is out of the view after it, and the player saw it before; a unit
that comes out of concealment is in the view after it. So a player gets the event when
each unit it names is visible to that player in the state before the command or in the
state after it. For a unit that is visible in neither:

- an event about where a unit is or goes (a placement, a move, a rout) is left out, and
- any other event goes with that unit's ID made unknown (None), so a player still reads
  "no effect" on a fire into a concealed hex, and does not read which unit was there.

The decision of what a player sees is `slcore.view.visible_to`, the same function that
builds the view. This module adds no rule.
"""

from __future__ import annotations

import copy
from typing import Any, Iterable, Mapping

from slcore import view

# The data keys that hold one unit ID, and the ones that hold a list of unit IDs.
ONE_UNIT_KEYS = ("unit", "carrier", "weapon", "leader")
UNIT_LIST_KEYS = ("units", "attackers", "targets")

# The events that tell where a unit is or where it goes. For a unit the player does not
# see, the whole event stays on the host.
POSITION_KINDS = frozenset(
    {
        "place",
        "place_weapon",
        "move",
        "stack_move",
        "vehicle_move",
        "vehicle_pivot",
        "advance",
        "rout",
        "stay",
        "sewer_move",
        "sewer_surface",
        "sewer_lost",
        "track_return",
        "track_return_end",
        "pickup",
        "drop",
        "board",
        "dismount",
        "debark_cost",
        "returned",
        "left_behind",
        "pushed_out",
    }
)


def named_units(data: Mapping[str, Any]) -> set[int]:
    """The unit IDs that the data of one event names."""
    out: set[int] = set()
    for key in ONE_UNIT_KEYS:
        value = data.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            out.add(value)
    for key in UNIT_LIST_KEYS:
        value = data.get(key)
        if isinstance(value, (list, tuple)):
            out.update(v for v in value if isinstance(v, int) and not isinstance(v, bool))
    for member in data.get("members") or []:
        if isinstance(member, Mapping):
            for key in ("unit", "weapon"):
                value = member.get(key)
                if isinstance(value, int) and not isinstance(value, bool):
                    out.add(value)
    return out


def visible_ids(state: Any, viewer: int) -> set[int]:
    """The units this player sees in this state, by the rule of the view."""
    return {u.id for u in state.units if view.visible_to(state, u, viewer)}


def _redact(data: Mapping[str, Any], hidden: set[int]) -> dict[str, Any]:
    out = copy.deepcopy(dict(data))
    for key in ONE_UNIT_KEYS:
        if out.get(key) in hidden:
            out[key] = None
    for key in UNIT_LIST_KEYS:
        value = out.get(key)
        if isinstance(value, list):
            out[key] = [None if v in hidden else v for v in value]
    for member in out.get("members") or []:
        if isinstance(member, dict):
            for key in ("unit", "weapon"):
                if member.get(key) in hidden:
                    member[key] = None
    return out


def entry_for(entry: Mapping[str, Any], seen: set[int]) -> dict[str, Any] | None:
    """One log entry for a player who sees the units in `seen`, or None to leave it out."""
    data = entry.get("data") or {}
    hidden = named_units(data) - seen
    if not hidden:
        return dict(entry)
    if entry.get("kind") in POSITION_KINDS:
        return None
    out = dict(entry)
    out["data"] = _redact(data, hidden)
    return out


def entries_for_players(
    entries: Iterable[Mapping[str, Any]], before: Any, after: Any, players: Iterable[int]
) -> dict[int, list[dict[str, Any]]]:
    """The entries of one command for each player, from the states before and after it."""
    entries = list(entries)
    out: dict[int, list[dict[str, Any]]] = {}
    for player in players:
        seen = visible_ids(before, player) | visible_ids(after, player)
        kept = (entry_for(e, seen) for e in entries)
        out[player] = [e for e in kept if e is not None]
    return out
