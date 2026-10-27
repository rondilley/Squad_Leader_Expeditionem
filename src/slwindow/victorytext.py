"""The text of the victory conditions during play, for the two windows. No game library.

The host sends the conditions in each frame (`objectives`, `slhost.objectives`). This module
turns them into the lines of the "Victory conditions" box: the sentence of the card, where
the objective hexes are on the map (violet), and for the person's own side the present
count, for example "You control 0 of the 5 violet hexes. You need 1 at the end of turn 5."
It reads what the host sent and applies no rule (AR-06).
"""

from __future__ import annotations

from typing import Any

from slwindow import endgame


def records(state: Any) -> list[dict[str, Any]]:
    found = getattr(state, "objectives", None)
    return [r for r in found if isinstance(r, dict)] if isinstance(found, list) else []


def _who(state: Any, record: dict[str, Any]) -> tuple[str, bool]:
    """The subject of a sentence of the record: "You" for the person's side, else the side."""
    mine = endgame.person_side(state)
    if mine is not None and record.get("side") == mine:
        return "You", True
    return f"The {record.get('side_name', 'other')} side", False


def lines(state: Any) -> list[str]:
    """The lines of the box: the turn, then each condition with its hexes and its status."""
    out = [endgame.turn_text(state) + "."]
    for record in records(state):
        who, mine = _who(state, record)
        note = str(record.get("note") or "").strip()
        out.append(note or f"{who}: {str(record.get('kind', 'condition')).replace('_', ' ')}.")
        hexes = list(record.get("hexes") or [])
        status = record.get("status")
        turns = record.get("turns")
        when = f" at the end of turn {turns}" if turns else " at the end of the game"
        if hexes and not isinstance(status, dict):
            out.append(f"The violet hexes are the objective of the {record.get('side_name', 'other')} side: {', '.join(hexes)}.")
        if isinstance(status, dict):
            held = list(status.get("held") or [])
            if record.get("kind") == "hex_control" and hexes:
                verb = "control" if mine else "controls"
                out.append(
                    f"{who} {verb} {status.get('count', 0)} of the {len(hexes)} violet hexes"
                    f"{' (' + ', '.join(held) + ')' if held else ''}. "
                    f"{'You need' if mine else 'It needs'} {status.get('threshold', 1)}{when}."
                )
            else:
                if hexes:
                    out.append(f"The violet hexes: {', '.join(hexes)}.")
                out.append(f"Now: {status.get('detail', '')}. {'Met' if status.get('satisfied') else 'Not met'} at this time.")
    if len(out) == 1:
        out.append("The host sent no victory condition.")
    return out


def hexes(state: Any) -> tuple[set[str], set[str]]:
    """The objective hexes of all conditions, and the ones that the person's side (or a
    side, for a watcher) controls now."""
    every: set[str] = set()
    held: set[str] = set()
    for record in records(state):
        every.update(str(h) for h in record.get("hexes") or [])
        status = record.get("status")
        if isinstance(status, dict):
            held.update(str(h) for h in status.get("held") or [])
    return every, held
