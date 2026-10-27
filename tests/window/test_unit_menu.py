"""The menu of one unit (`slwindow.unitmenu`): the model, with no screen."""

from __future__ import annotations

from slwindow import unitmenu
from slwindow.unitmenu import ROW_ABOUT, ROW_COMMAND, ROW_HEADER, ROW_NOTE, ROW_UNDO


def _entry(action: str, units: list[int], hex_id: str | None = None, label: str = "", **extra):
    payload = {"action": action, "units": units, **extra}
    if hex_id is not None:
        payload["hex"] = hex_id
    return {"id": f"{action}-{units}-{hex_id}-{extra}", "payload": payload, "label": label or f"{action} {hex_id}"}


VIEW = {
    "units": [
        {"id": 1, "name": "4-4-7 #1", "hex": "C3", "own": True},
        {"id": 2, "name": "9-1 #1", "hex": "C3", "own": True},
        {"id": 9, "name": "4-6-7 #1", "hex": "F3", "own": False},
    ]
}


def _kinds(rows):
    return [(row.kind, row.text) for row in rows]


def test_the_menu_groups_the_commands_of_the_unit_and_keeps_the_side_commands():
    legal = [
        _entry("group_add", [1], "F3", "4-4-7 #1 fires at F3"),
        _entry("group_add_weapon", [1], "F3", "4-4-7 #1 fires LMG at F3", weapon=5),
        _entry("drop", [1], None, "4-4-7 #1 drops LMG", weapon=5),
        _entry("group_add", [2], "F3", "9-1 #1 fires at F3"),
        _entry("end_phase", [], None, "end the Prep Fire Phase"),
    ]
    rows = unitmenu.rows(VIEW, legal, 1, "Prep Fire Phase.", None, can_undo=True)
    kinds = _kinds(rows)
    assert kinds[0] == (ROW_NOTE, "Prep Fire Phase.")
    fire = kinds.index((ROW_HEADER, "Fire"))
    assert kinds[fire + 1 : fire + 3] == [(ROW_COMMAND, "4-4-7 #1 fires at F3"), (ROW_COMMAND, "4-4-7 #1 fires LMG at F3")]
    assert (ROW_HEADER, "Weapons and equipment") in kinds and (ROW_COMMAND, "4-4-7 #1 drops LMG") in kinds
    assert (ROW_COMMAND, "9-1 #1 fires at F3") not in kinds, "the commands of another unit are not in its menu"
    assert (ROW_COMMAND, "end the Prep Fire Phase") in kinds
    command_rows = [row for row in rows if row.kind == ROW_COMMAND]
    assert [row.index for row in command_rows] == [0, 1, 2, 4], "each row plays its legal entry"
    assert kinds[-2:] == [(ROW_ABOUT, "About this unit"), (ROW_UNDO, "Undo the last command (Ctrl and z)")]


def test_the_steps_of_a_move_are_a_note_and_the_reach_is_counted():
    legal = [_entry("move", [1], hex_id) for hex_id in ("B3", "C2", "D3")]
    legal.append(_entry("vehicle_pivot", [1], None, "turn to face 2", facing=2))
    answer = {"kind": "move", "reach": {h: 2 for h in ("B3", "C2", "D3", "E3", "E4")}}
    rows = unitmenu.rows(VIEW, legal, 1, "", answer, can_undo=False)
    texts = [row.text for row in rows]
    assert "Click a blue hex on the board to move one hex (3 hexes)." in texts
    assert "Click a pale blue hex to move there (5 hexes)." in texts
    assert not any(row.kind == ROW_COMMAND and row.text.startswith("move") for row in rows)
    assert (ROW_COMMAND, "turn to face 2") in _kinds(rows)
    assert rows[-1] == unitmenu.MenuRow(ROW_UNDO, "Undo: nothing to take back now")


def test_a_long_group_keeps_ten_rows_and_counts_the_rest():
    legal = [_entry("group_add", [1], f"H{n}", f"4-4-7 #1 fires at H{n}") for n in range(14)]
    rows = unitmenu.rows(VIEW, legal, 1)
    assert sum(1 for row in rows if row.kind == ROW_COMMAND) == unitmenu.GROUP_LIMIT
    assert "4 more in the list on the right." in [row.text for row in rows]


def test_a_unit_with_no_command_says_why():
    rows = unitmenu.rows(VIEW, [], 9)
    assert (ROW_NOTE, "A unit of the other side.") in _kinds(rows)
    own = unitmenu.rows(VIEW, [], 2, answer={"kind": "fire", "note": "The 9-1 has no firepower."})
    assert (ROW_NOTE, "This unit has no command now.") in _kinds(own)
    assert (ROW_NOTE, "The 9-1 has no firepower.") in _kinds(own)
    assert unitmenu.title(VIEW, 1) == "4-4-7 #1 in C3"
