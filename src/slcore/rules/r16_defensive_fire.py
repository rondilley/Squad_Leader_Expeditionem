"""Rule 16, defensive fire: the track of the moved units and the return to a track hex."""

from __future__ import annotations

from typing import Callable

from slcore import actions, geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import State
from slcore.geometry import HexRef
from slcore.units import MOVE_MODE_STACK, Unit

RULE_16_1 = "16.1"
RULE_16_3 = "16.3"
RULE_16_4 = "16.4"
RULE_16_5 = "16.5"


def moved_units(state: State, player: int) -> list[Unit]:
    return [u for u in state.player_units(player) if u.track and u.hex is not None and not u.eliminated]


def track_hexes(state: State, player: int) -> dict[HexRef, list[int]]:
    """The hexes where the units of the player spent movement factors (rule 16.4)."""
    out: dict[HexRef, list[int]] = {}
    for u in moved_units(state, player):
        for h in u.track:
            out.setdefault(h, []).append(u.id)
    return out


def watchers(state: State, player: int) -> list[HexRef]:
    """PR-53: the hexes of the defender's units whose line of sight marks a track hex.

    An unbroken infantry unit on foot on the board, or a vehicle that is not a wreck.
    """
    out: set[HexRef] = set()
    for u in state.player_units(player):
        if u.hex is None or u.eliminated:
            continue
        if u.is_infantry and not u.broken and not u.riding and u.carrier is None:
            out.add(u.hex)
        elif u.is_vehicle and not u.wreck:
            out.add(u.hex)
    return sorted(out)


def legal_track_returns(state: State, player: int, sees: Callable[[HexRef, HexRef], bool]) -> list[Command]:
    """Rule 16.1: the defender may return moved units to a hex on their track.

    Only a hex that a unit of the defender sees (rule 16.1, PR-53). PR-39: for each track
    hex the defender chooses one unit, the units of one stack move, or all the units that
    moved through the hex.
    """
    out: list[Command] = []
    mover = 1 - player
    eyes = watchers(state, player)
    for hex_ref, ids in sorted(track_hexes(state, mover).items()):
        eligible = tuple(sorted(i for i in ids if state.units[i].returned_from is None and state.units[i].hex != hex_ref))
        if not eligible:
            continue
        if not any(eye == hex_ref or sees(eye, hex_ref) for eye in eyes):
            continue
        for uid in eligible:
            out.append(Command("track_return", units=(uid,), hex=hex_ref))
        stacks: dict[str, list[int]] = {}
        for uid in eligible:
            mode = state.units[uid].move_mode
            if mode.startswith(MOVE_MODE_STACK):
                stacks.setdefault(mode, []).append(uid)
        for mode in sorted(stacks):
            if len(stacks[mode]) > 1:
                out.append(Command("track_return", units=tuple(sorted(stacks[mode])), hex=hex_ref))
        if len(eligible) > 1:
            out.append(Command("track_return", units=eligible, hex=hex_ref))
    return out


def apply_track_return(state: State, command: Command) -> tuple[State, list[Event]]:
    """Rule 16.1: stacking limits are ignored while the units stand in the target hex."""
    hex_ref = command.hex
    if hex_ref is None:
        raise ValueError("track_return needs a hex")
    changed = {}
    for uid in command.units:
        unit = state.units[uid]
        if unit.hex is None:
            continue
        changed[uid] = unit.with_(returned_from=unit.hex, hex=hex_ref)
        for w in state.carried_by(uid):
            changed[w.id] = w.with_(hex=hex_ref)
    state = state.with_units(changed)
    return state, [Event(RULE_16_1, "track_return", {"units": list(command.units), "hex": geometry.hex_id(*hex_ref)})]


def return_units(state: State) -> tuple[State, list[Event]]:
    """Rule 16.3: after the fire, the units that survive go back to the positions they held."""
    changed = {}
    events: list[Event] = []
    for u in state.units:
        if u.returned_from is None or u.eliminated:
            continue
        changed[u.id] = u.with_(hex=u.returned_from, returned_from=None)
        for w in state.carried_by(u.id):
            changed[w.id] = w.with_(hex=u.returned_from)
        events.append(Event(RULE_16_3, "track_return_end", {"unit": u.id, "hex": geometry.hex_id(*u.returned_from)}))
    if changed:
        state = state.with_units(changed)
    return state, events


def clear_returns(state: State) -> State:
    changed = {u.id: u.with_(returned_from=None) for u in state.units if u.returned_from is not None}
    return state.with_units(changed) if changed else state


# ------------------------------------------------------------------ the command handler (M3)
# Rule 16.1 acts on the units of the other side, which are in view already, so it is no
# act of rule 25.4.


@actions.action("track_return")
def _on_track_return(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    return apply_track_return(state, command)
