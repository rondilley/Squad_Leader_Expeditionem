"""Rule 24, smoke.

A smoke counter is not a support weapon. It sits on a hex, it does not count against
stacking, and it costs one more movement factor to enter or cross. Its effect on fire is
a dice roll: a fire group whose line of sight goes into, out of, or through a smoke hex
adds the roll of one die to its fire combat dice roll (rule 24.6). That roll comes after
the fire combat roll and it belongs to one fire group only (rule 24.7).

Only an assault engineer squad places smoke, one counter for each squad in a turn, and
only as the first action of its own Prep Fire Phase (rules 24.2 and 24.3).
"""

from __future__ import annotations

from typing import Mapping, Sequence

from slcore import actions, geometry
from slcore.commands import Command
from slcore.events import Event
from slcore.game import Smoke, State
from slcore.geometry import HexRef
from slcore.rng import roll_die
from slcore.state import Board
from slcore.units import UnitType

RULE_24_1 = "24.1"
RULE_24_2 = "24.2"
RULE_24_3 = "24.3"
RULE_24_4 = "24.4"
RULE_24_5 = "24.5"
RULE_24_6 = "24.6"
RULE_24_7 = "24.7"
RULE_24_8 = "24.8"

MF_HALVES_PENALTY = 2
NO_SMOKE_EFFECT = ("demo", "flamethrower")


def can_place(state: State, types: Mapping[str, UnitType], unit) -> bool:
    """Rule 24.2: an assault engineer squad, one counter for each squad in a turn."""
    if unit.eliminated or unit.hex is None or unit.carrier is not None or unit.broken:
        return False
    if not types[unit.type_key].assault_engineer:
        return False
    if unit.made_smoke:
        return False
    if state.smoke_left[unit.player] <= 0:
        return False
    return True


def target_hexes(board: Board, unit) -> list[HexRef]:
    """Rule 24.3: the hex of the engineer squad or a hex next to it."""
    if unit.hex is None:
        return []
    out = [unit.hex] + [h for h in geometry.neighbors(*unit.hex) if h in board]
    return sorted(set(out))


def place(state: State, unit_id: int, hex_ref: HexRef) -> tuple[State, list[Event]]:
    """Rule 24.3: the counter goes down and the squad keeps its move and its fire."""
    unit = state.units[unit_id]
    left = list(state.smoke_left)
    left[unit.player] -= 1
    state = state.with_(
        smoke=state.smoke + (Smoke(hex_ref, unit.player),),
        smoke_left=(left[0], left[1]),
    )
    state = state.with_unit(unit.with_(made_smoke=True))
    return state, [
        Event(RULE_24_3, "smoke", {"unit": unit_id, "player": unit.player, "hex": geometry.hex_id(*hex_ref), "left": left[unit.player]})
    ]


def expire(state: State, player: int) -> tuple[State, list[Event]]:
    """Rule 24.8: a counter goes at the beginning of the next Prep Fire Phase of its owner."""
    keep = tuple(s for s in state.smoke if s.player != player)
    gone = [s for s in state.smoke if s.player == player]
    if not gone:
        return state, []
    events = [Event(RULE_24_8, "smoke_gone", {"player": player, "hex": geometry.hex_id(*s.hex)}) for s in gone]
    return state.with_(smoke=keep), events


def blocks_path(state: State, traced: Sequence[HexRef], firer: HexRef, target: HexRef) -> bool:
    """Rule 24.6: the line of sight goes into, out of, or through a smoke hex."""
    if state.smoke_in(firer) or state.smoke_in(target):
        return True
    return any(state.smoke_in(h) for h in traced)


def modifier(state: State, hexes: Sequence[HexRef]) -> tuple[State, int]:
    """Rule 24.6 and 24.7: one die, rolled after the fire combat roll, for the group."""
    rng, value = roll_die(state.rng)
    return state.with_(rng=rng), value


def move_penalty(state: State, hex_ref: HexRef) -> int:
    """Rule 24.5: one more movement factor, in half units (NFR-05)."""
    return MF_HALVES_PENALTY if state.smoke_in(hex_ref) else 0


# ------------------------------------------------------------------ the command handler (M3)


@actions.action("place_smoke", unconceals=actions.CAUSE_SMOKE)
def _on_place_smoke(engine, state: State, command: Command) -> tuple[State, list[Event]]:
    if command.hex is None:
        raise ValueError("a smoke counter needs a hex")
    return place(state, command.units[0], command.hex)
