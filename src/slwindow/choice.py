"""The command choice of the two windows: one model, and no game library in it.

The pygame window and the 3D window both show the legal list of the host and send one
command ID from it. This module holds what the two share, so a test reads it with no
screen:

- the text of one legal entry: the label of the host (protocol version 2), or a text from
  the payload, with the unit names and the odds when the host sends them
- the list a person sees: the legal list, narrowed by a unit and a hex that the person
  clicked on the board, and by the text the person typed
- the cursor in that list, which goes back to the top on each new frame
- the board choice: a click on a unit narrows the list to the commands of that unit, and
  a click on a hex that one of them names narrows it to that hex. When one command is
  left, the window sends it.

The model reads the legal list and the view that the host sent, and nothing else. It
applies no rule and it holds no rule table (AR-06): a hex is an option only because a
legal entry names it.

The keys of the two windows follow one policy (H7). For a person who holds a seat, a
plain letter or digit always goes to the filter, also while the other side acts, so a
shortcut never takes a letter of the filter and a letter typed early never closes the
window. A letter with Ctrl is always a shortcut. A watcher types no filter, so for a
watcher a plain letter is its shortcut too (`is_watcher`).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from slwindow.overlay import hexes_of, payload_of, position_of, unit_ids

# The odds of the host are counts out of this number (two dice, then two more for a
# second roll where the odds need it).
ODDS_BASE = 1296


def unit_names(entry: dict[str, Any], view: dict[str, Any] | None = None) -> list[str]:
    """The names of the acting units. The host names them in version 2. For a version 1
    host the name comes from the unit of the view, with its hex."""
    listed = entry.get("units")
    if isinstance(listed, list) and listed and isinstance(listed[0], dict):
        return [str(u.get("name") or f"unit {u.get('id')}") for u in listed if isinstance(u, dict)]
    units = _units_by_id(view)
    names = []
    for unit_id in unit_ids(entry):
        unit = units.get(unit_id)
        if unit is None:
            names.append(f"unit {unit_id}")
            continue
        name = str(unit.get("name") or unit.get("type") or f"unit {unit_id}")
        here = unit.get("hex")
        names.append(f"{name} ({here})" if here else name)
    return names


def is_watcher(snapshot: Any) -> bool:
    """True for a connection that holds no seat: a watcher of two computer opponents, or
    a watcher of a room that is full."""
    view = getattr(snapshot, "view", None)
    if isinstance(view, dict) and view.get("spectator"):
        return True
    if str(getattr(snapshot, "seat", "")) == "watcher":
        return True
    return int(getattr(snapshot, "you", -1)) < 0 and int(getattr(snapshot, "player", -1)) < 0


def _percent(count: Any) -> str:
    """A count out of 1296 as a whole percent, with integer arithmetic."""
    try:
        value = int(count)
    except (TypeError, ValueError):
        return "?"
    return f"{(value * 100 + ODDS_BASE // 2) // ODDS_BASE}%"


def odds_text(entry: dict[str, Any]) -> str:
    """The odds of the host for one entry, as short text, or an empty text.

    The host gives each chance as a count out of 1296 for the view of the side that acts.
    A target the side cannot see has no odds, and the entry then has none.
    """
    odds = entry.get("odds")
    if not isinstance(odds, dict):
        return ""
    kind = str(odds.get("kind", ""))
    if kind == "fire":
        return f"KIA {_percent(odds.get('kia'))} K {_percent(odds.get('k'))} break {_percent(odds.get('break'))}"
    if kind == "move":
        return f"break {_percent(odds.get('break_worst'))} at worst"
    if kind == "close_combat":
        return f"kill {_percent(odds.get('kill'))} killed {_percent(odds.get('killed'))}"
    if kind == "rally":
        return f"rally {_percent(odds.get('rally'))}"
    parts = [f"{key} {_percent(value)}" for key, value in sorted(odds.items()) if key not in ("kind", "of")]
    return " ".join(parts)


def describe(entry: dict[str, Any]) -> str:
    """One line for one command, from its payload and nothing else."""
    payload = payload_of(entry)
    parts = [str(payload.get("action", "?"))]
    if payload.get("units"):
        parts.append("u" + ",".join(str(u) for u in payload["units"]))
    if payload.get("hex"):
        parts.append(str(payload["hex"]))
    if payload.get("weapon") is not None:
        parts.append(f"w{payload['weapon']}")
    for key in ("facing", "aim", "ammo", "armament", "vehicle", "charge", "leader", "targets"):
        if payload.get(key) is not None:
            parts.append(f"{key}={payload[key]}")
    return " ".join(parts)


def label_of(entry: dict[str, Any], view: dict[str, Any] | None = None) -> str:
    """The text of one legal entry in the list: the label of the host when it gave one,
    else a text from the payload with the names of the units."""
    label = entry.get("label")
    if isinstance(label, str) and label:
        return label
    payload = payload_of(entry)
    text = describe(entry)
    if payload.get("units") and view is not None:
        text = f"{text} [{', '.join(unit_names(entry, view))}]"
    return text


def row_text(entry: dict[str, Any], view: dict[str, Any] | None = None) -> str:
    """The label and the odds of one entry, which is what a person reads and filters."""
    odds = odds_text(entry)
    label = label_of(entry, view)
    return f"{label}  ({odds})" if odds else label


def _units_by_id(view: dict[str, Any] | None) -> dict[int, dict[str, Any]]:
    if not isinstance(view, dict):
        return {}
    out: dict[int, dict[str, Any]] = {}
    for unit in view.get("units", []) or []:
        if isinstance(unit, dict) and unit.get("id") is not None:
            out[int(unit["id"])] = unit
    return out


def _position(view: dict[str, Any] | None, unit_id: int) -> str | None:
    unit = _units_by_id(view).get(int(unit_id))
    return None if unit is None else position_of(unit)


def entries_for(legal: Sequence[dict[str, Any]], unit: int | None = None, hex_id: str | None = None) -> list[int]:
    """The indexes of the legal entries that name this unit (when given) and this hex
    (when given)."""
    out = []
    for index, entry in enumerate(legal):
        if unit is not None and unit not in unit_ids(entry):
            continue
        if hex_id is not None and hex_id not in hexes_of(entry):
            continue
        out.append(index)
    return out


@dataclass
class BoardClick:
    """What a click on a hex did: the new pin of the focus, and the entry to send."""

    pinned: int | None
    send: int | None = None


class Chooser:
    """The command list of one window: the filter, the board narrowing, and the cursor.

    `position` is the place of the cursor in the list a person sees. `scroll` is the first
    row the panel draws, and `page_rows` is how many rows it has space for. The panel sets
    `page_rows` when it draws.
    """

    def __init__(self) -> None:
        self.filter_text = ""
        self.position = 0
        self.scroll = 0
        self.page_rows = 10
        self.unit: int | None = None
        self.hex: str | None = None
        self.frame_id = ""

    # --------------------------------------------------------------- the frame

    def sync(self, frame_id: str, legal: Sequence[dict[str, Any]]) -> bool:
        """Read a frame. A new frame puts the cursor back at the top (H7) and drops the hex
        of the board choice. The unit stays while it has a command in the new list, so a
        person moves one unit hex by hex. Return True for a new frame."""
        if frame_id == self.frame_id:
            return False
        self.frame_id = frame_id
        self.position = 0
        self.scroll = 0
        self.hex = None
        if self.unit is not None and not entries_for(legal, self.unit):
            self.unit = None
        return True

    # ---------------------------------------------------------------- the list

    def visible(self, legal: Sequence[dict[str, Any]], view: dict[str, Any] | None = None) -> list[tuple[int, dict[str, Any]]]:
        """The rows a person sees, each with its index in the legal list."""
        rows = list(enumerate(legal))
        if self.unit is not None or self.hex is not None:
            keep = set(entries_for(legal, self.unit, self.hex))
            rows = [(i, e) for i, e in rows if i in keep]
        if self.filter_text:
            needle = self.filter_text.lower()
            rows = [(i, e) for i, e in rows if needle in row_text(e, view).lower() or needle in describe(e).lower()]
        return rows

    def selected(self, legal: Sequence[dict[str, Any]], view: dict[str, Any] | None = None) -> int | None:
        """The legal index under the cursor, or None when the list is empty."""
        rows = self.visible(legal, view)
        if not rows:
            return None
        return rows[min(self.position, len(rows) - 1)][0]

    def move(self, delta: int, legal: Sequence[dict[str, Any]], view: dict[str, Any] | None = None) -> None:
        count = len(self.visible(legal, view))
        self.position = max(0, min(max(0, count - 1), self.position + delta))
        self.keep_visible()

    def page(self, delta: int, legal: Sequence[dict[str, Any]], view: dict[str, Any] | None = None) -> None:
        self.move(delta * max(1, self.page_rows - 1), legal, view)

    def point_at(self, legal_index: int, legal: Sequence[dict[str, Any]], view: dict[str, Any] | None = None) -> None:
        """Put the cursor on the row of one legal index, when the list shows it."""
        for position, (index, _entry) in enumerate(self.visible(legal, view)):
            if index == legal_index:
                self.position = position
                self.keep_visible()
                return

    def scroll_by(self, delta: int, legal: Sequence[dict[str, Any]], view: dict[str, Any] | None = None) -> None:
        """The wheel over the list moves the rows and not the cursor."""
        count = len(self.visible(legal, view))
        top = max(0, count - self.page_rows)
        self.scroll = max(0, min(top, self.scroll + delta))

    def keep_visible(self) -> None:
        """Move the rows so the cursor is on the screen."""
        rows = max(1, self.page_rows)
        if self.position < self.scroll:
            self.scroll = self.position
        elif self.position >= self.scroll + rows:
            self.scroll = self.position - rows + 1

    # -------------------------------------------------------------- the filter

    def type(self, text: str) -> None:
        self.filter_text += text
        self.position = 0
        self.scroll = 0

    def backspace(self) -> None:
        self.filter_text = self.filter_text[:-1]
        self.position = 0
        self.scroll = 0

    def escape(self) -> str:
        """Escape clears one thing, in this order: the typed text, the hex of the board
        choice, the unit of the board choice. Return what it cleared, or an empty text
        when nothing was left (the window then clears its focus)."""
        if self.filter_text:
            self.filter_text = ""
            cleared = "filter"
        elif self.hex is not None:
            self.hex = None
            cleared = "hex"
        elif self.unit is not None:
            self.unit = None
            cleared = "unit"
        else:
            return ""
        self.position = 0
        self.scroll = 0
        return cleared

    # --------------------------------------------------------- the board choice

    def board_click(
        self,
        view: dict[str, Any] | None,
        legal: Sequence[dict[str, Any]],
        hex_id: str | None,
        pinned: int | None,
        next_focus: Any,
    ) -> BoardClick:
        """A click on a hex of the board.

        1. With a pinned unit, a hex that a legal entry of that unit names is a choice.
           The list narrows to those entries, and when one is left it is the one to send.
           The hex of the pinned unit is not a choice: a click there takes the next unit
           of the stack, so a second click never sends a command by surprise.
        2. Else the click puts a unit of the hex in focus (`next_focus`, the same in the
           two windows), and the list narrows to the commands of that unit.
        3. A hex with no unit narrows the list to the entries that name the hex (a place
           of set up, for example). With no pinned unit a click sends nothing.
        """
        if hex_id is None:
            return BoardClick(pinned)
        if pinned is not None and hex_id != _position(view, pinned):
            chosen = entries_for(legal, pinned, hex_id)
            if chosen:
                self.unit = pinned
                self.hex = hex_id
                self.position = 0
                self.scroll = 0
                return BoardClick(pinned, chosen[0] if len(chosen) == 1 else None)
        focus = next_focus(view, hex_id, pinned)
        self.hex = None
        self.position = 0
        self.scroll = 0
        if focus is not None:
            self.unit = focus if entries_for(legal, focus) else None
            return BoardClick(focus)
        self.unit = None
        if entries_for(legal, None, hex_id):
            # No unit is pinned, so the click narrows and sends nothing.
            self.hex = hex_id
        return BoardClick(None)
