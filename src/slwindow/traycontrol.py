"""What a click of the set up tray does, for the two windows, with no game library.

`slwindow.setup` is the model of the tray, and `slwindow.traydraw` draws it. This mixin
holds the steps that the 2D and the 3D window share: select a counter of the tray, place it
on a shaded hex, take a placed counter back (`setup_lift`), keep the hex that refused a
counter and say why (the host's `options_request` answer), wait for the host before a
drop of a counter that was on the board, and go on to the next identical counter after a
placement.

A window that uses it has these attributes: `pinned`, `chooser`, `client`, `refusal`,
`_pending_drop`, `_placed_last`, `_carry`, and `_snapshot`. It has these methods:
`_view()`, `_legal()`, `send(index)`, `_end_carry()`, `auto_setup()`, and
`show_about(unit)`. The mixin applies no rule (AR-06): a hex is a target only because a
legal entry names it.
"""

from __future__ import annotations

from typing import Any

from slwindow import setup as setup_model
from slwindow.choice import is_watcher
from slwindow.overlay import position_of, setup_refusal, units_in
from slwindow.traydraw import ACTION_ABOUT, ACTION_AUTO, ACTION_FINISH, ACTION_UNIT


class SetupTrayControl:
    """The set up steps of a window. See the module text for what the window gives."""

    def in_setup(self) -> bool:
        """True while the person at this window places the counters of a side."""
        snapshot = self._snapshot
        return snapshot is not None and not is_watcher(snapshot) and setup_model.is_setup(snapshot)

    def tray_items(self) -> list[Any]:
        return setup_model.tray(self._view(), self._legal())

    def pick_tray(self, unit_id: int) -> None:
        """A click on a counter of the tray: select one to place, or take a placed one back
        to the tray (the host plays the set up again without it)."""
        item = {i.unit_id: i for i in self.tray_items()}.get(unit_id)
        if item is None:
            return
        self.refusal = None
        if item.placed:
            self.lift(unit_id)
            return
        self.pinned = unit_id
        self.chooser.unit = None
        self.chooser.hex = None
        if item.offered is None:
            self.chooser.only = set()
        else:
            self.chooser.only = {i for found in setup_model.targets(self._legal(), item.offered, self._view()).values() for i in found}
        self.chooser.position = 0
        self.chooser.scroll = 0

    def lift(self, unit_id: int) -> None:
        """Ask the host to take a placed counter of this side off the board again, and keep
        it selected, so the next click on a shaded hex places it."""
        if self.client is not None:
            self.client.send_setup_lift(unit_id)
        self.pinned = unit_id
        self.chooser.only = None

    def finish_setup(self) -> bool:
        index = setup_model.can_finish(self._legal())
        return False if index is None else self.send(index)

    def _setup_click(self, hex_id: str | None) -> bool:
        """A click on the board while the side sets up. Return True when it was a set up
        click. With a counter of the tray selected, a shaded hex places it; a click on a
        counter of this side on the board takes that counter back to the tray."""
        if hex_id is None:
            return False
        if self._place_at(hex_id):
            return True
        own = [u for u in units_in(self._view(), hex_id) if u.get("own")]
        if own and not self._weapon_selected():
            self.lift(int(own[0]["id"]))
            return True
        return self._refuse(hex_id)

    def _tray_targets(self) -> dict[str, list[int]]:
        """The hexes of the selected counter when it is in the tray, else none."""
        view = self._view()
        legal = self._legal()
        units = {int(u["id"]): u for u in (view or {}).get("units", []) or []}
        pin = self.pinned
        if pin == setup_model.CONCEALMENT:
            return setup_model.targets(legal, pin, view)
        if pin not in units or position_of(units[pin]) is not None:
            return {}
        offered = setup_model.offered_id(view, legal, pin)
        return setup_model.targets(legal, offered, view) if offered is not None else {}

    def _tray_selection(self) -> int | None:
        """The selected counter when it is in the tray (not on the board), else None."""
        pin = self.pinned
        if pin is None:
            return None
        if pin == setup_model.CONCEALMENT:
            return pin
        units = {int(u["id"]): u for u in (self._view() or {}).get("units", []) or []}
        if pin not in units or position_of(units[pin]) is not None:
            return None
        return pin

    def _weapon_selected(self) -> bool:
        pin = self._tray_selection()
        units = {int(u["id"]): u for u in (self._view() or {}).get("units", []) or []}
        return pin is not None and units.get(pin, {}).get("kind") == "sw"

    def _refuse(self, hex_id: str) -> bool:
        """A click or a drop of the tray counter on a hex the legal list does not name for
        it. Keep the hex, so the tray says why. Return True when a tray counter was selected."""
        pin = self._tray_selection()
        if pin is None or pin == setup_model.CONCEALMENT:
            return False
        self.refusal = (pin, hex_id)
        return True

    def refusal_text(self) -> str | None:
        """Why the last hex refused the counter of the tray, or None. The reason comes from
        the host (`slhost.options`); the window applies no rule (AR-06)."""
        if self.refusal is None:
            return None
        pin, hex_id = self.refusal
        view, legal = self._view(), self._legal()
        units = {int(u["id"]): u for u in (view or {}).get("units", []) or []}
        unit = units.get(pin)
        if unit is None or position_of(unit) is not None:
            return None
        name = str(unit.get("type", "counter"))
        offered = setup_model.offered_id(view, legal, pin)
        asked = offered if offered is not None else pin
        answers = getattr(self._snapshot, "options", None) or {}
        text = setup_refusal(answers.get(asked), name, hex_id)
        if text is not None:
            return text
        if offered is not None and hex_id in setup_model.targets(legal, offered, view):
            return None
        if unit.get("kind") == "sw" and offered is not None:
            # The legal list lets the weapon go there alone, but a unit on the board can
            # carry it, and the tray offers that first (`setup.targets`).
            return setup_model.hint(view, legal, pin)
        return f"{hex_id} does not take the {name}. The host checks the reason."

    def _place_at(self, hex_id: str) -> bool:
        """Place the selected counter of the tray on this hex, when the legal list has it."""
        found = self._tray_targets().get(hex_id, [])
        if found:
            self.refusal = None
        if len(found) == 1:
            self.send(found[0])
            return True
        if found:
            # A vehicle has a command for each facing, and a weapon can go to each unit of
            # the hex: the list shows them, and the person picks one.
            self.chooser.only = set(found)
            self.chooser.position = 0
            self.chooser.scroll = 0
            return True
        return False

    def _grab_on_board(self, hex_id: str | None) -> int | None:
        """The counter of this side that a press on this hex picks up, or None. A press on
        a shaded hex of the selected counter is a placement, not a pick up."""
        if hex_id is None or hex_id in self._tray_targets():
            return None
        own = [u for u in units_in(self._view(), hex_id) if u.get("own")]
        return int(own[0]["id"]) if own else None

    def drop(self, hex_id: str | None) -> bool:
        """The release of a dragged counter on a hex places it there. When the host has not
        yet taken it off the board, the drop waits for the next frame."""
        unit_id = self._carry
        self._end_carry()
        if unit_id is None or hex_id is None:
            return False
        self.pinned = unit_id
        units = {int(u["id"]): u for u in (self._view() or {}).get("units", []) or []}
        if unit_id in units and position_of(units[unit_id]) is not None:
            self._pending_drop = (unit_id, hex_id)
            return True
        if self._place_at(hex_id):
            return True
        self._refuse(hex_id)
        return False

    def _apply_pending_drop(self) -> None:
        """On a new frame, place a counter that was dropped before its pick up came back."""
        if self._pending_drop is None:
            return
        unit_id, hex_id = self._pending_drop
        units = {int(u["id"]): u for u in (self._view() or {}).get("units", []) or []}
        if unit_id in units and position_of(units[unit_id]) is not None:
            # The host has not taken it off yet; a frame of something else came first.
            return
        self._pending_drop = None
        if self.in_setup():
            self.pinned = unit_id
            if not self._place_at(hex_id):
                self._refuse(hex_id)

    def _follow_identical(self) -> None:
        """After a counter goes on the board, the selection moves to an identical counter
        that is still to place, so three 4-4-7 squads take three clicks on the board."""
        if not self._placed_last:
            return
        self._placed_last = False
        view = self._view()
        units = {int(u["id"]): u for u in (view or {}).get("units", []) or []}
        pin = self.pinned
        if pin is None or pin not in units or position_of(units[pin]) is None:
            return
        nxt = setup_model.offered_id(view, self._legal(), pin)
        if nxt is not None and nxt != pin:
            self.pinned = nxt
            self.chooser.only = {i for found in setup_model.targets(self._legal(), nxt, view).values() for i in found}
        else:
            self.pinned = None

    def tray_action(self, action: str, unit_id: int | None) -> None:
        """The action of a hit of the tray: a counter, Finish set up, Set up for me, or
        About this unit."""
        if action == ACTION_UNIT and unit_id is not None:
            self.pick_tray(unit_id)
        elif action == ACTION_FINISH:
            self.finish_setup()
        elif action == ACTION_AUTO:
            self.auto_setup()
        elif action == ACTION_ABOUT and self.pinned is not None:
            units = {int(u["id"]): u for u in (self._view() or {}).get("units", []) or []}
            self.show_about(units.get(self.pinned))
