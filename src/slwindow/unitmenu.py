"""The menu of one unit: what a person can do with it now. One model, no game library.

A right click on a unit of the board, or Ctrl and Space with a unit in focus, opens the
menu (`slwindow.boxes.draw_menu` draws it, in the 2D and the 3D window). The menu shows each command of the legal list that
names the unit, in groups (fire, move, weapons, close combat, rally, and the commands
of the side), with the label and the odds of the host. A click on a row plays it.

The model reads the legal list, the view, and the options answer of the host
(`slhost.options`), and nothing else. It applies no rule (AR-06): a row is a command only
because the legal list names it. The kinds of fire are the commands of the phase, which
the host gives: the fire of a unit with its own firepower and with each weapon it
carries, a fire group with a leader, and the special weapons. The phase text of the host
says which phase it is.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from slwindow.choice import row_text
from slwindow.overlay import payload_of, unit_ids

ROW_HEADER = "header"
ROW_NOTE = "note"
ROW_COMMAND = "command"
ROW_ABOUT = "about"
ROW_UNDO = "undo"

# The most rows of one group. The list on the right holds the rest.
GROUP_LIMIT = 10

# The group of each action, in the order of the menu.
GROUPS: tuple[tuple[str, frozenset[str]], ...] = (
    (
        "Fire",
        frozenset(
            {
                "group_add",
                "group_add_weapon",
                "group_leader",
                "ft_fire",
                "at_fire",
                "afv_fire",
                "afv_mg",
                "afv_attack",
                "explode_demo",
            }
        ),
    ),
    ("Smoke", frozenset({"place_smoke", "afv_smoke", "afv_dischargers"})),
    ("Close combat", frozenset({"cc_attack", "cc_afv"})),
    (
        "Move",
        frozenset(
            {
                "move",
                "stack_move",
                "vehicle_move",
                "vehicle_pivot",
                "advance",
                "rout",
                "sewer_move",
                "sewer_return",
                "board",
                "debark",
                "push_out",
                "push_wreck",
                "stay",
                "track_return",
            }
        ),
    ),
    ("Weapons and equipment", frozenset({"pickup", "drop", "place_demo", "repair", "afv_repair"})),
    ("Rally", frozenset({"rally"})),
)
# The one-hex steps are many (six facings for each hex of a vehicle), and the board shows
# them as blue hexes, so the menu gives their count and not a row for each.
STEP_ACTIONS = frozenset({"move", "stack_move", "vehicle_move"})
# The commands of the side that name no unit, which the menu also offers.
SIDE_ACTIONS = ("group_fire", "end_phase")


@dataclass(frozen=True)
class MenuRow:
    """One row of the menu. `index` is the legal index of a command row."""

    kind: str
    text: str
    index: int | None = None


def _group_of(action: str) -> str:
    for name, actions in GROUPS:
        if action in actions:
            return name
    return "Other"


def _unit(view: dict[str, Any] | None, unit_id: int) -> dict[str, Any] | None:
    for unit in (view or {}).get("units", []) or []:
        if isinstance(unit, dict) and unit.get("id") == unit_id:
            return unit
    return None


def title(view: dict[str, Any] | None, unit_id: int) -> str:
    unit = _unit(view, unit_id) or {}
    name = str(unit.get("name") or unit.get("type") or f"unit {unit_id}")
    here = unit.get("hex")
    return f"{name} in {here}" if here else name


def rows(
    view: dict[str, Any] | None,
    legal: Sequence[dict[str, Any]],
    unit_id: int,
    phase_text: str = "",
    answer: dict[str, Any] | None = None,
    can_undo: bool = False,
) -> list[MenuRow]:
    """The rows of the menu of one unit."""
    out: list[MenuRow] = []
    unit = _unit(view, unit_id) or {}
    if phase_text:
        out.append(MenuRow(ROW_NOTE, phase_text))
    grouped: dict[str, list[int]] = {}
    for index, entry in enumerate(legal):
        if unit_id in unit_ids(entry):
            grouped.setdefault(_group_of(str(payload_of(entry).get("action", ""))), []).append(index)
    order = [name for name, _ in GROUPS] + ["Other"]
    for name in order:
        found = grouped.get(name)
        if not found:
            continue
        out.append(MenuRow(ROW_HEADER, name))
        steps = [i for i in found if payload_of(legal[i]).get("action") in STEP_ACTIONS]
        if steps:
            hexes = {str(payload_of(legal[i]).get("hex")) for i in steps}
            out.append(MenuRow(ROW_NOTE, f"Click a blue hex on the board to move one hex ({len(hexes)} hexes)."))
            if answer and answer.get("kind") == "move" and len(answer.get("reach") or {}) > len(hexes):
                out.append(MenuRow(ROW_NOTE, f"Click a pale blue hex to move there ({len(answer['reach'])} hexes)."))
        others = [i for i in found if i not in steps]
        for index in others[:GROUP_LIMIT]:
            out.append(MenuRow(ROW_COMMAND, row_text(legal[index], view), index))
        if len(others) > GROUP_LIMIT:
            out.append(MenuRow(ROW_NOTE, f"{len(others) - GROUP_LIMIT} more in the list on the right."))
    if not grouped:
        if not unit.get("own"):
            out.append(MenuRow(ROW_NOTE, "A unit of the other side."))
        else:
            out.append(MenuRow(ROW_NOTE, "This unit has no command now."))
    if answer and answer.get("note"):
        out.append(MenuRow(ROW_NOTE, str(answer["note"])))
    side = [i for i, entry in enumerate(legal) if not unit_ids(entry) and payload_of(entry).get("action") in SIDE_ACTIONS]
    if side:
        out.append(MenuRow(ROW_HEADER, "Your side"))
        out.extend(MenuRow(ROW_COMMAND, row_text(legal[i], view), i) for i in side)
    out.append(MenuRow(ROW_HEADER, ""))
    out.append(MenuRow(ROW_ABOUT, "About this unit"))
    out.append(MenuRow(ROW_UNDO, "Undo the last command (Ctrl and z)" if can_undo else "Undo: nothing to take back now"))
    return out
