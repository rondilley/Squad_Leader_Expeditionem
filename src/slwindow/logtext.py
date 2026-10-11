"""One short line for one event of the action log: the rule, the dice, the modifier, the result.

The core puts the rule ID, the dice, and each modifier in each event (FR-06), and the
action log must show them (BC-04). This module only writes the event data as words. It
reads no rule and computes no result (AR-06): each number in a line is a number of the
event. It imports no drawing library, so a test reads it with no window.
"""

from __future__ import annotations

from typing import Any, Mapping


def _result(code: Any) -> str:
    text = str(code)
    if text == "KIA":
        return "KIA"
    if text == "M":
        return "MC"
    if text == "-":
        return "no effect"
    return f"MC+{text}"


def _dice(data: Mapping[str, Any]) -> str:
    dice = data.get("dice") or []
    return "+".join(str(d) for d in dice)


def _signed(value: Any) -> str:
    return f"{int(value):+d}"


def _who(unit: Any, names: Mapping[int, str]) -> str:
    if unit is None:
        return "?"
    return names.get(int(unit), f"unit {unit}")


def log_text(entry: Mapping[str, Any], names: Mapping[int, str] | None = None) -> str:
    """The line for one event. `names` gives a name for a unit ID, when the view has one."""
    names = names or {}
    rule = str(entry.get("rule_id", ""))
    kind = str(entry.get("kind", ""))
    data = entry.get("data") or {}
    if kind == "fire":
        dice = data.get("dice") or []
        drm = int(data.get("adjusted", 0)) - sum(int(d) for d in dice)
        return (
            f"{rule} fire at {data.get('target')}: {data.get('firepower')} FP col {data.get('column')}, "
            f"dice {_dice(data)} DRM {_signed(drm)} = {data.get('adjusted')}"
        )
    if kind == "fire_result":
        hit = ", ".join(_who(u, names) for u in data.get("units", []))
        return f"{rule} {data.get('target')}: {_result(data.get('result'))} on {hit}"
    if kind in ("morale_pass", "broken", "eliminated"):
        verb = {"morale_pass": "passes MC", "broken": "breaks", "eliminated": "eliminated"}[kind]
        modifier = int(data.get("modifier", 0)) + int(data.get("leadership", 0))
        return (
            f"{rule} {_who(data.get('unit'), names)} {verb}: {_dice(data)} {_signed(modifier)} = "
            f"{data.get('adjusted')} vs {data.get('morale')}"
        )
    if kind in ("rallied", "rally_failed"):
        verb = "rallies" if kind == "rallied" else "fails to rally"
        return (
            f"{rule} {_who(data.get('unit'), names)} {verb}: {_dice(data)} {_signed(data.get('leadership', 0))} = "
            f"{data.get('adjusted')} vs {data.get('target')}"
        )
    if kind in ("cc_kill", "cc_miss"):
        verb = "kills" if kind == "cc_kill" else "misses"
        return (
            f"{rule} close combat {data.get('odds')} needs {data.get('kill')}: "
            f"{_dice(data)} {_signed(data.get('leadership', 0))} = {data.get('adjusted')}, {verb}"
        )
    if kind in ("move", "advance", "rout"):
        return f"{rule} {_who(data.get('unit'), names)} {kind} {data.get('from')} to {data.get('to')}"
    if kind == "place":
        return f"{rule} {_who(data.get('unit'), names)} set up in {data.get('hex')}"
    if kind == "phase":
        return f"{rule} turn {data.get('turn')} {str(data.get('phase', '')).replace('_', ' ')}"
    if kind == "game_end":
        return f"game over: {data.get('result')}"
    return f"{rule} {kind.replace('_', ' ')}"


def unit_names(view: Mapping[str, Any] | None) -> dict[int, str]:
    """A short name for each unit of a view: the leader's name, or the counter type."""
    names: dict[int, str] = {}
    for unit in (view or {}).get("units", []):
        names[int(unit["id"])] = str(unit.get("name") or unit.get("type") or unit["id"])
    return names
