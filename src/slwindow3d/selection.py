"""What a click on the board means: select a unit, then pick one of its legal commands.

The 3D window gets the legal list from the host with each frame. A person plays it by a
click on a unit and then a click on a hex. This module turns those clicks into one command
ID from that list. It builds no command, and it reads no rule (AR-06, DR-04): each choice it
gives is an entry of the legal list, and the only test it applies is "does this entry name
the selected unit and this hex".

A legal entry is `{"id": ..., "payload": {...}}`, as the host sends it. The payload has an
`action`, and most have `units`, and a `hex` when the command goes to a hex.

The flow:

- A click on a hex with a unit that a legal command names selects that unit. A second click
  on the same hex selects the next such unit in that hex, so a person reaches each unit of
  a stack.
- When a unit is selected, each hex that a legal command of that unit names is a target. A
  click on a target with one command sends it. A click on a target with more than one
  command (a fire with the squad or with its machine gun) opens a menu of those commands.
  A click on a target that also holds other units the person can select opens the menu
  too, with a "select" entry for each of those units, because the click has two readings.
- The commands with no hex (end the phase, fire the group, rally, pick up a weapon) go in a
  list beside the board, with the commands of the selected unit first.
- In set up the units to place are on no hex, so the window lists them, and the first one
  is selected with no click. After each placement the next one is selected.
- A command to a hex that names no unit (a concealment counter of rule 25.3) goes by a
  click on the hex, with no unit selected.

This module imports no part of Panda3D, so a test reads it with no window.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

SEND = "send"
MENU = "menu"
SELECT = "select"
CLEAR = "clear"

# The actions whose hex is a target of fire and not a destination, for the wording only.
FIRE_ACTIONS = frozenset({"group_add", "group_add_weapon", "ft_fire", "afv_fire", "afv_mg", "at_fire", "afv_attack"})


def payload(command: dict[str, Any]) -> dict[str, Any]:
    """The payload of a legal entry."""
    return command.get("payload", command)


def _units(command: dict[str, Any]) -> list[int]:
    return [int(u) for u in payload(command).get("units", []) or []]


@dataclass(frozen=True)
class ClickResult:
    """What one click asks the window to do."""

    kind: str
    commands: tuple[dict[str, Any], ...] = ()
    unit: int | None = None
    # In a menu: the other units in the hex that a click can select in place of a command.
    units: tuple[int, ...] = ()


@dataclass
class Selection:
    """The unit the person selected, and the frame it was selected in."""

    unit: int | None = None
    frame_id: str = ""
    history: list[int] = field(default_factory=list)

    def refresh(self, frame_id: str, legal: Sequence[dict[str, Any]], view: dict[str, Any] | None) -> None:
        """Keep the selection across a new frame when the unit still has a command, so a
        person who moves a squad one hex at a time does not click the squad again. In set
        up, when the selection has no command, select the first unit to place."""
        if frame_id == self.frame_id:
            return
        self.frame_id = frame_id
        if self.unit is not None and not any(self.unit in _units(c) for c in legal):
            self.unit = None
        if self.unit is None:
            waiting = reserve_units(legal, view)
            if waiting:
                self.unit = waiting[0]

    def select(self, unit: int | None) -> ClickResult:
        """Select a unit from the list beside the board (a unit that is not on the board)."""
        self.unit = unit
        return ClickResult(SELECT if unit is not None else CLEAR, (), unit)

    def click(self, hex_id: str | None, legal: Sequence[dict[str, Any]], view: dict[str, Any] | None) -> ClickResult:
        if hex_id is None:
            self.unit = None
            return ClickResult(CLEAR)
        here = actable_units_at(view, legal, hex_id)
        loose = loose_commands(legal, hex_id)
        if self.unit is not None:
            commands = targets(legal, self.unit).get(hex_id, [])
            others = tuple(u for u in here if u != self.unit)
            if commands and (others or loose):
                # The hex is a target of the selected unit and holds other choices too (a
                # unit to select, a command that names no unit). Each reading is a choice,
                # so the menu asks.
                return ClickResult(MENU, tuple(commands) + tuple(loose), self.unit, others)
            if len(commands) == 1:
                return ClickResult(SEND, (commands[0],), self.unit)
            if len(commands) > 1:
                return ClickResult(MENU, tuple(commands), self.unit)
        if loose:
            # A command to this hex that names no unit (a concealment counter of rule 25.3).
            if len(loose) == 1 and not here:
                return ClickResult(SEND, (loose[0],), self.unit)
            return ClickResult(MENU, tuple(loose), self.unit, tuple(here))
        if not here:
            self.unit = None
            return ClickResult(CLEAR)
        if self.unit in here:
            self.unit = here[(here.index(self.unit) + 1) % len(here)]
        else:
            self.unit = here[0]
        return ClickResult(SELECT, (), self.unit)


def actable_units_at(view: dict[str, Any] | None, legal: Sequence[dict[str, Any]], hex_id: str) -> list[int]:
    """The units in this hex that a legal command names, in the order of their ids."""
    if not view:
        return []
    named = {u for c in legal for u in _units(c)}
    return sorted(
        int(unit["id"]) for unit in view.get("units", []) if unit.get("hex") == hex_id and int(unit["id"]) in named
    )


def loose_commands(legal: Sequence[dict[str, Any]], hex_id: str) -> list[dict[str, Any]]:
    """The legal commands to this hex that name no unit."""
    return [c for c in legal if payload(c).get("hex") == hex_id and not _units(c)]


def loose_hexes(legal: Sequence[dict[str, Any]]) -> list[str]:
    """Each hex that a legal command with no unit names."""
    return sorted({str(payload(c)["hex"]) for c in legal if payload(c).get("hex") and not _units(c)})


def targets(legal: Sequence[dict[str, Any]], unit: int) -> dict[str, list[dict[str, Any]]]:
    """Each hex that a legal command of this unit names, with the commands to that hex."""
    out: dict[str, list[dict[str, Any]]] = {}
    for command in legal:
        body = payload(command)
        hex_id = body.get("hex")
        if hex_id and unit in _units(command):
            out.setdefault(str(hex_id), []).append(command)
    return out


def free_commands(legal: Sequence[dict[str, Any]], unit: int | None) -> list[dict[str, Any]]:
    """The commands with no hex, for the list beside the board.

    The commands of the selected unit come first, then the commands that name no unit (end
    the phase, fire the group), then the rest.
    """
    no_hex = [c for c in legal if not payload(c).get("hex")]

    def rank(command: dict[str, Any]) -> int:
        units = _units(command)
        if unit is not None and unit in units:
            return 0
        if not units:
            return 1
        return 2

    return sorted(no_hex, key=rank)


def reserve_units(legal: Sequence[dict[str, Any]], view: dict[str, Any] | None) -> list[int]:
    """The units that a hex command names and that are on no hex of the view: the units to
    place in set up. A click on the board cannot select them, so the window lists them."""
    on_board = {int(u["id"]) for u in (view or {}).get("units", []) if u.get("hex")}
    named = {u for c in legal if payload(c).get("hex") for u in _units(c)}
    return sorted(named - on_board)


def describe(command: dict[str, Any], view: dict[str, Any] | None) -> str:
    """One line for a menu or the list: the action, the units by name, the hex, the weapon."""
    body = payload(command)
    names: dict[int, str] = {}
    if view:
        for unit in view.get("units", []):
            label = unit.get("name") or unit.get("type") or str(unit["id"])
            names[int(unit["id"])] = str(label)
    parts = [str(body.get("action", "?")).replace("_", " ")]
    units = _units(command)
    if units:
        parts.append(", ".join(names.get(u, f"unit {u}") for u in units))
    if body.get("weapon") is not None:
        parts.append("with " + names.get(int(body["weapon"]), f"weapon {body['weapon']}"))
    if body.get("targets"):
        parts.append("at " + ", ".join(names.get(int(u), f"unit {u}") for u in body["targets"]))
    if body.get("hex"):
        word = "at" if str(body.get("action", "")) in FIRE_ACTIONS else "to"
        parts.append(f"{word} {body['hex']}")
    for key in ("facing", "aim", "ammo", "armament", "vehicle", "leader"):
        if body.get(key) is not None:
            parts.append(f"{key} {body[key]}")
    return " ".join(parts)


def result_name(result: str) -> str:
    """The words for one IFT result as the core names it: KIA, a morale check (M), a
    morale check with a modifier (a number), or no effect (-)."""
    if result == "KIA":
        return "KIA"
    if result == "M":
        return "MC"
    if result == "-":
        return "no effect"
    return f"MC+{result}"


def preview_text(preview: dict[str, Any] | None) -> str:
    """One line of the fire preview that the host sent, or an empty line."""
    if not preview:
        return ""
    drm = int(preview.get("drm", 0))
    causes = ", ".join(
        f"{part.get('rule')} {str(part.get('cause')).replace('_', ' ')} {int(part.get('value', 0)):+d}"
        for part in preview.get("modifiers", [])
    )
    rolls = preview.get("rolls_of_36", {})
    # The worst result first: KIA, then the morale checks by size, then no effect.
    def order(item: tuple[str, int]) -> tuple[int, int]:
        name = item[0]
        if name == "KIA":
            return (0, 0)
        if name == "-":
            return (3, 0)
        if name == "M":
            return (2, 0)
        return (1, -int(name)) if name.isdigit() else (2, 1)

    odds = ", ".join(f"{result_name(name)} {count}" for name, count in sorted(rolls.items(), key=order))
    text = f"Fire at {preview.get('target')}: {preview.get('firepower')} FP (column {preview.get('column')}), DRM {drm:+d}"
    if causes:
        text += f" ({causes})"
    return f"{text}. Of 36 rolls: {odds}"


def game_over_lines(snapshot: Any, person_side: str | None = None) -> list[str]:
    """The lines of the end-of-game screen: who won, why, and when. Each word comes from the
    result that the host sent (AR-06). `person_side` is the side the person at this window
    plays against the computer; with no such side (hot seat, or a watcher) the screen names
    the winner and not "you"."""
    result = str(getattr(snapshot, "result", "") or "")
    cause = str(getattr(snapshot, "result_cause", "") or "")
    if result in ("draw", "no_result"):
        title = "Draw" if result == "draw" else "No result"
    elif person_side is not None:
        title = "You win" if result == person_side else f"{result.capitalize()} wins: you lose"
    else:
        title = f"{result.capitalize()} wins"
    lines = [title]
    if cause:
        lines.append(cause)
    turn = getattr(snapshot, "turn", 0)
    lines.append(f"after turn {turn}. Press q to quit.")
    return lines


def los_text(answer: dict[str, Any] | None) -> str:
    """One line for the host's line of sight answer, with the rule that decided it."""
    if not answer:
        return ""
    text = f"Line of sight {answer.get('from')} to {answer.get('to')}: "
    if answer.get("clear"):
        text += "clear"
        hindrance = int(answer.get("hindrance") or 0)
        if hindrance:
            text += f", hindrance {hindrance:+d}"
    else:
        text += f"blocked at {answer.get('blocking_hex')}"
    rule = answer.get("rule_id")
    return f"{text} (rule {rule})" if rule else text
