"""The play input of the 3D window: a person plays a side with the mouse.

The window shows the board and the counters. This module adds the input: a click on a unit
selects it, the hexes it can go to or fire at get a ring, and a click on one of them sends
that legal command to the host. The commands with no hex (end the phase, fire the group,
rally) and the units to place in set up are a list of buttons on the left. When a hex has
more than one command for the unit, a small menu asks which one.

All of it is a choice from the legal list that the host sent with the frame
(`selection.py`). The window builds no command and applies no rule (AR-06, DR-04). The host
checks each intent against the frame, and the frame ID goes with each intent, so a click on
an old frame is refused by the host and not played.

The window sends one intent for each frame. It does not send a second one before the next
frame comes, so a double click does not play two commands.
"""

from __future__ import annotations

from typing import Any, Callable

from panda3d.core import TextNode

from slwindow3d.selection import (
    CLEAR,
    FIRE_ACTIONS,
    MENU,
    SELECT,
    SEND,
    Selection,
    describe,
    free_commands,
    loose_hexes,
    los_text,
    payload,
    preview_text,
    reserve_units,
    targets,
)

# The number of rows in the list on the left. A frame can have more commands with no hex
# than this (a fire group in a large stack); the list then names how many it does not show.
MAX_ROWS = 18
ROW_STEP = 0.062
ROW_SCALE = 0.038
LIST_TOP = -0.16
MENU_TOP = 0.3
ROW_COLOR = (0.08, 0.1, 0.08, 0.82)
ROW_TEXT = (0.95, 0.95, 0.9, 1)
RESERVE_TEXT = (0.75, 0.9, 1.0, 1)


class PlayInput:
    """The mouse input of one person in the 3D window.

    `app` is the `Board3DApp`. `send(frame_id, command_id)` sends an intent to the host. Call
    `update(snapshot)` from the poll task when a new frame comes, and `click_board(x, y)` with
    the mouse position of a click on the board.
    """

    def __init__(self, app: Any, send: Callable[[str, str], None], ask_los: Callable[[str, str], None] | None = None) -> None:
        self.app = app
        self.send = send
        # Asks the host for a line of sight (FR-34); the window computes none (AR-06).
        self.ask_los = ask_los
        self.los: dict[str, Any] | None = None
        self.selection = Selection()
        self.snapshot: Any = None
        self.sent_for: str | None = None
        self.rows: list[Any] = []
        self.menu: list[Any] = []
        self.menu_commands: tuple[dict[str, Any], ...] = ()
        self.list_entries: list[tuple[str, Any]] = []
        self.banner = None
        self.preview_line = None
        self._make_banner()

    # ------------------------------------------------------------------ the frame

    @property
    def legal(self) -> list[dict[str, Any]]:
        if self.snapshot is None or getattr(self.snapshot, "game_over", False):
            return []
        return list(getattr(self.snapshot, "legal", []) or [])

    @property
    def view(self) -> dict[str, Any] | None:
        return getattr(self.snapshot, "view", None) if self.snapshot is not None else None

    @property
    def frame_id(self) -> str:
        return str(getattr(self.snapshot, "frame_id", "") or "")

    def my_turn(self) -> bool:
        """True when this window holds a legal list to choose from and has not chosen yet."""
        return bool(self.legal) and self.sent_for != self.frame_id

    def update(self, snapshot: Any) -> None:
        """A new frame: keep or move the selection, and draw the rings and the list again."""
        self.snapshot = snapshot
        self.close_menu()
        self.selection.refresh(self.frame_id, self.legal, self.view)
        self.redraw()

    # ------------------------------------------------------------------ the input

    def click_board(self, mouse_x: float, mouse_y: float) -> str:
        """A click on the board at a mouse position. Return what the click did."""
        if not self.my_turn():
            return CLEAR
        self.close_menu()
        hex_id = self.app.pick_at(mouse_x, mouse_y)
        return self.click_hex(hex_id)

    def click_hex(self, hex_id: str | None) -> str:
        """A click on one hex (or on no hex). Return what the click did."""
        if not self.my_turn():
            return CLEAR
        if self.los is not None:
            self.show_los(None)
        result = self.selection.click(hex_id, self.legal, self.view)
        if result.kind == SEND:
            self.choose(result.commands[0])
        elif result.kind == MENU:
            self.open_menu(result.commands, result.units)
        else:
            self.redraw()
        return result.kind

    def choose(self, command: dict[str, Any]) -> bool:
        """Send one legal command of this frame. Return False if this frame already sent one."""
        if not self.my_turn():
            return False
        self.close_menu()
        self.sent_for = self.frame_id
        self.send(self.frame_id, str(command["id"]))
        self.redraw()
        return True

    def pick_reserve(self, unit: int) -> None:
        """Select a unit from the list (a unit to place, which is on no hex)."""
        self.selection.select(unit)
        self.redraw()

    def refused(self, snapshot: Any) -> None:
        """The host refused the last intent (its notice says why). The frame is the same, so
        the person can choose again, and the banner shows the cause."""
        self.snapshot = snapshot
        self.sent_for = None
        self.redraw()

    def request_los(self, mouse_x: float, mouse_y: float) -> bool:
        """The `l` key: ask the host for the line of sight from the selected unit's hex to
        the hex under the mouse. Return False when there is nothing to ask."""
        source = self._unit_hex(self.selection.unit)
        target = self.app.pick_at(mouse_x, mouse_y)
        if self.ask_los is None or source is None or target is None:
            return False
        self.ask_los(source, target)
        return True

    def show_los(self, answer: dict[str, Any] | None) -> None:
        """The host answered a line of sight question: draw it and say it."""
        self.los = answer
        if self.app.indicators is not None:
            self.app.indicators.show_los(answer)
        self._draw_banner()

    def cancel(self) -> None:
        """Escape: close the menu, or clear the selection."""
        if self.menu:
            self.close_menu()
            return
        self.selection.select(None)
        self.redraw()

    # ------------------------------------------------------------------ the drawing

    def _unit_hex(self, unit: int | None) -> str | None:
        if unit is None or not self.view:
            return None
        for entry in self.view.get("units", []):
            if int(entry["id"]) == unit:
                return entry.get("hex")
        return None

    def redraw(self) -> None:
        unit = self.selection.unit
        move_hexes: list[str] = []
        fire_hexes: list[str] = []
        if self.my_turn():
            # The hexes of the commands that name no unit get a ring with or without a
            # selection, because a click on one plays it.
            move_hexes.extend(loose_hexes(self.legal))
        if unit is not None and self.my_turn():
            for hex_id, commands in targets(self.legal, unit).items():
                if any(payload(c).get("action") in FIRE_ACTIONS for c in commands):
                    fire_hexes.append(hex_id)
                else:
                    move_hexes.append(hex_id)
        if self.app.indicators is not None:
            self.app.indicators.show_selection(self._unit_hex(unit), move_hexes, fire_hexes)
        self._draw_list()
        self._draw_banner()

    def _list_entries(self) -> list[tuple[str, Any]]:
        """The rows of the list: the units to place, then the commands with no hex."""
        if not self.my_turn():
            return []
        unit = self.selection.unit
        names = {int(u["id"]): u for u in (self.view or {}).get("units", [])}
        commands = free_commands(self.legal, unit)
        # The order: the commands of the selected unit, the commands that name no unit (end
        # the phase, fire the group), the units to place, and then the rest. So the rows a
        # person wants now are at the top, also when the list is longer than the window.
        first = [c for c in commands if unit is not None and unit in [int(u) for u in payload(c).get("units", [])]]
        loose = [c for c in commands if not payload(c).get("units")]
        rest = [c for c in commands if c not in first and c not in loose]
        entries: list[tuple[str, Any]] = [(describe(c, self.view), ("command", c)) for c in first + loose]
        for waiting in reserve_units(self.legal, self.view):
            info = names.get(waiting, {})
            label = info.get("name") or info.get("type") or f"unit {waiting}"
            mark = "> " if waiting == unit else "  "
            entries.append((f"{mark}place {label}", ("reserve", waiting)))
        entries.extend((describe(c, self.view), ("command", c)) for c in rest)
        return entries

    def _row_action(self, entry: tuple[str, Any]) -> None:
        kind, value = entry
        if kind == "reserve":
            self.pick_reserve(value)
        else:
            self.choose(value)

    def _draw_list(self) -> None:
        from direct.gui.DirectGui import DirectButton, DirectLabel

        for row in self.rows:
            row.destroy()
        self.rows = []
        self.list_entries = self._list_entries()
        shown = self.list_entries[:MAX_ROWS]
        for index, (label, entry) in enumerate(shown):
            reserve = entry[0] == "reserve"
            self.rows.append(
                DirectButton(
                    parent=self.app.a2dTopLeft,
                    text=label,
                    text_align=TextNode.ALeft,
                    text_fg=RESERVE_TEXT if reserve else ROW_TEXT,
                    frameColor=ROW_COLOR,
                    pad=(0.3, 0.2),
                    scale=ROW_SCALE,
                    pos=(0.04, 0, LIST_TOP - index * ROW_STEP),
                    command=self._row_action,
                    extraArgs=[entry],
                )
            )
        hidden = len(self.list_entries) - len(shown)
        if hidden > 0:
            self.rows.append(
                DirectLabel(
                    parent=self.app.a2dTopLeft,
                    text=f"and {hidden} more; select a unit to see its own",
                    text_align=TextNode.ALeft,
                    text_fg=ROW_TEXT,
                    frameColor=(0, 0, 0, 0),
                    scale=ROW_SCALE * 0.85,
                    pos=(0.04, 0, LIST_TOP - len(shown) * ROW_STEP),
                )
            )

    def open_menu(self, commands, units=()) -> None:
        """A small menu in the middle of the window: one button for each command, then one
        button to select each other unit of the hex."""
        from direct.gui.DirectGui import DirectButton

        self.close_menu()
        self.menu_commands = tuple(commands)
        names = {int(u["id"]): u for u in (self.view or {}).get("units", [])}
        rows = len(self.menu_commands)
        for index, unit in enumerate(units):
            info = names.get(int(unit), {})
            label = info.get("name") or info.get("type") or f"unit {unit}"
            self.menu.append(
                DirectButton(
                    parent=self.app.aspect2d,
                    text=f"select {label}",
                    text_fg=RESERVE_TEXT,
                    frameColor=(0.05, 0.1, 0.15, 0.92),
                    pad=(0.4, 0.25),
                    scale=0.045,
                    pos=(0, 0, MENU_TOP - (rows + index) * 0.075),
                    command=self.select_from_menu,
                    extraArgs=[int(unit)],
                )
            )
        rows += len(units)
        for index, command in enumerate(self.menu_commands):
            self.menu.append(
                DirectButton(
                    parent=self.app.aspect2d,
                    text=describe(command, self.view),
                    text_fg=ROW_TEXT,
                    frameColor=(0.15, 0.12, 0.05, 0.92),
                    pad=(0.4, 0.25),
                    scale=0.045,
                    pos=(0, 0, MENU_TOP - index * 0.075),
                    command=self.choose,
                    extraArgs=[command],
                )
            )
        self.menu.append(
            DirectButton(
                parent=self.app.aspect2d,
                text="cancel",
                text_fg=ROW_TEXT,
                frameColor=(0.2, 0.2, 0.2, 0.9),
                pad=(0.4, 0.25),
                scale=0.04,
                pos=(0, 0, MENU_TOP - rows * 0.075),
                command=self.close_menu,
            )
        )

    def select_from_menu(self, unit: int) -> None:
        self.close_menu()
        self.pick_reserve(unit)

    def close_menu(self) -> None:
        for button in self.menu:
            button.destroy()
        self.menu = []
        self.menu_commands = ()

    def _make_banner(self) -> None:
        from direct.gui.OnscreenText import OnscreenText

        self.banner = OnscreenText(
            text="",
            parent=self.app.a2dTopLeft,
            pos=(0.04, -0.08),
            scale=0.05,
            fg=(1, 1, 0.85, 1),
            shadow=(0, 0, 0, 0.8),
            align=TextNode.ALeft,
            mayChange=True,
        )
        # The fire preview goes at the bottom left, over the help line.
        self.preview_line = OnscreenText(
            text="",
            parent=self.app.a2dBottomLeft,
            pos=(0.04, 0.1),
            scale=0.042,
            fg=(1, 0.92, 0.5, 1),
            shadow=(0, 0, 0, 0.9),
            align=TextNode.ALeft,
            mayChange=True,
        )

    def preview_line_text(self) -> str:
        """The bottom line: the line of sight answer when there is one, else the fire odds."""
        if self.los:
            return los_text(self.los)
        if not self.my_turn():
            return ""
        return preview_text(getattr(self.snapshot, "fire_preview", None))

    def banner_text(self) -> str:
        """One line: the turn, the phase, and what the person does now."""
        snapshot = self.snapshot
        if snapshot is None:
            return "connecting to the host"
        notice = str(getattr(snapshot, "notice", "") or "")
        if notice and not getattr(snapshot, "game_over", False):
            return f"The host refused the command: {notice}"
        if getattr(snapshot, "game_over", False):
            # The end-of-game screen gives the cause; the banner stays one short line.
            return f"Game over: {getattr(snapshot, 'result', '')}"
        phase = str(getattr(snapshot, "phase", "") or "").replace("_", " ")
        turn = getattr(snapshot, "turn", 0)
        players = (getattr(snapshot, "scenario", None) or {}).get("players", [])
        active = getattr(snapshot, "active", -1)
        side = players[active] if 0 <= active < len(players) else f"side {active}"
        if not self.legal:
            return f"Turn {turn}, {phase}: {side} acts"
        if self.sent_for == self.frame_id:
            return f"Turn {turn}, {phase}: {side}, the host plays your command"
        if self.selection.unit is None:
            return f"Turn {turn}, {phase}: {side}, click a unit or a button"
        return f"Turn {turn}, {phase}: {side}, click a ring or a button"

    def _draw_banner(self) -> None:
        if self.banner is not None:
            self.banner.setText(self.banner_text())
        if self.preview_line is not None:
            self.preview_line.setText(self.preview_line_text())
