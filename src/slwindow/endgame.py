"""The text of the end of a game and of the turn count, for the two windows. No game library.

The host sends `game_over` with the winner index, the side names, the conditions, the
turn, and the losses (protocol version 2). This module turns it into the words a person
reads: "You won." or "You lost." when one side is the person's, the side that wins, and
what each victory condition gave. It also gives the line of the turn count during the game:
the turn, the count of turns of the scenario, and how many turns are left.

The text reads what the host sent and applies no rule (AR-06).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

CONTROLLER_HUMAN = "human"


@dataclass(frozen=True)
class EndSummary:
    """The headline of the end ("You lost."), and the lines below it."""

    headline: str
    lines: list[str] = field(default_factory=list)


def _sides(state: Any) -> dict[str, Any]:
    sides = getattr(state, "sides", None)
    return sides if isinstance(sides, dict) else {}


def side_name(state: Any, player: Any) -> str:
    """The name of a side, from the welcome (version 2) or from the scenario."""
    record = _sides(state).get(str(player))
    if isinstance(record, dict) and record.get("name"):
        return str(record["name"])
    names = (getattr(state, "scenario", None) or {}).get("players", [])
    try:
        index = int(player)
    except (TypeError, ValueError):
        return str(player)
    return str(names[index]) if 0 <= index < len(names) else f"side {index}"


def person_side(state: Any) -> int | None:
    """The side of the person at this window, when exactly one side is the person's: a
    game against the computer, or a seat of a LAN game. Hot seat with two people and a
    watcher give None."""
    mine = [int(p) for p, record in _sides(state).items() if isinstance(record, dict) and record.get("controller") == CONTROLLER_HUMAN]
    return mine[0] if len(mine) == 1 else None


def _player_of_side_key(state: Any, key: Any) -> int | None:
    """The player index of a side key of the scenario ("allied"), or None."""
    players = (getattr(state, "scenario", None) or {}).get("players", [])
    return players.index(key) if key in players else None


def _total_turns(state: Any) -> int | None:
    turns = (getattr(state, "scenario", None) or {}).get("turns")
    try:
        return int(turns)
    except (TypeError, ValueError):
        return None


def turn_text(state: Any) -> str:
    """The turn and how many turns are left: "turn 2 of 5: 3 more turns after this one"."""
    turn = int(getattr(state, "turn", 0) or 0)
    total = _total_turns(state)
    if total is None or turn <= 0:
        return f"turn {turn}"
    if turn > total:
        return f"turn {total} of {total}: the last turn is complete"
    left = total - turn
    if left == 0:
        return f"turn {turn} of {total}: the last turn"
    more = "1 more turn" if left == 1 else f"{left} more turns"
    return f"turn {turn} of {total}: {more} after this one"


def _winner(state: Any) -> int | None:
    over = dict(getattr(state, "over", None) or {})
    result = over.get("result")
    if isinstance(result, int) and not isinstance(result, bool):
        return result
    try:
        return int(str(getattr(state, "result", "")))
    except ValueError:
        return None


def _condition_line(state: Any, condition: Any) -> str:
    if not isinstance(condition, dict):
        return str(condition)
    player = _player_of_side_key(state, condition.get("side"))
    side = side_name(state, player) if player is not None else str(condition.get("side", "")).replace("_", " ")
    kind = str(condition.get("kind", "condition")).replace("_", " ")
    met = condition.get("satisfied")
    state_text = "" if met is None else (" It is met." if met else " It is not met.")
    detail = str(condition.get("detail") or "")
    return f"The {side} side, {kind}: {detail}.{state_text}".replace("..", ".")


def summary(state: Any) -> EndSummary:
    """The headline and the lines of the end of the game."""
    over = dict(getattr(state, "over", None) or {})
    winner = _winner(state)
    mine = person_side(state)
    winner_name = over.get("winner_name") or (side_name(state, winner) if winner is not None else "")
    if winner is None:
        headline = "The game ends with no winner."
    elif mine is None:
        headline = f"The {winner_name} side wins."
    elif winner == mine:
        headline = "You won."
    else:
        headline = "You lost."
    lines: list[str] = []
    if mine is not None and winner is not None:
        lines.append(f"The {winner_name} side wins. You played the {side_name(state, mine)} side.")
    total = _total_turns(state)
    turn = over.get("turn")
    if isinstance(turn, int) and total is not None and turn > total:
        lines.append(f"The game ended after the last turn, turn {total}.")
    elif isinstance(turn, int):
        lines.append(f"The game ended in turn {turn}.")
    conditions = over.get("conditions")
    if isinstance(conditions, list) and conditions:
        lines.extend(_condition_line(state, condition) for condition in conditions)
    else:
        cause = over.get("cause") or getattr(state, "result_cause", "")
        if cause:
            lines.append(str(cause)[:1].upper() + str(cause)[1:].rstrip(".") + ".")
    casualties = over.get("casualties")
    if isinstance(casualties, dict):
        for player, losses in sorted(casualties.items(), key=lambda item: str(item[0])):
            if isinstance(losses, dict):
                text = ", ".join(f"{losses[key]} {key[:-1] if losses[key] == 1 else key}" for key in ("squads", "leaders", "vehicles") if key in losses)
                lines.append(f"Losses of the {side_name(state, player)} side: {text or 'none'}.")
    return EndSummary(headline, lines)
