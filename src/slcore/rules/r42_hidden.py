"""Rule 42, Hidden Initial Placement (FR-10).

Concealment (rule 25) tells the other player where a unit is not. Hidden initial placement
tells the other player nothing at all: the unit is not on the board that the opponent sees,
and the owner keeps its position on the scenario record.

Rule 42 is optional. The text says both players agree to it, unless the scenario in play
names it. So a scenario names the side that may use it, and no other scenario changes.

What this module applies:

- 42.1: a side that the scenario names records a unit hidden, and only in a woods hex or a
  building hex. Each other unit of that side goes on the board in full view.
- 42.2: a hidden unit comes on the board when it moves, when it fires, when it makes smoke,
  or when it is next to an enemy unit at the end of a Defensive Fire Phase or an Advance
  Phase. Entrenchment is rule 51 and it waits for its own tier.
- 42.3: a unit that came on the board does not go back. It can take a concealment counter,
  which is rule 25.3.
- 42.4, the second half: a hidden unit in a target hex comes on the board when an attack on
  that hex gives a result that is not "No Effect". Fire on a hex that holds a hidden unit is
  half strength, which is the Area Fire of rule 9.4.
- 42.5: a unit that moves into the hex of a hidden unit stops there and ends its Movement
  Phase in the hex it came from.

What this module does not apply. The first half of rule 42.4 lets a player fire into a hex
where no enemy is known to be. That changes the legal list of each fire window from "a hex
with an enemy in it" to "each hex in the line of sight", on every board and in every
scenario, and the reinforcement learning environment reads that list as its action space
(FR-50). It waits for its own tier, and `blind_fire_hexes` gives the error that says so.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from slcore import geometry
from slcore.events import Event
from slcore.game import State
from slcore.geometry import HexRef
from slcore.state import Board
from slcore.units import Unit

RULE_42_1 = "42.1"
RULE_42_2 = "42.2"
RULE_42_3 = "42.3"
RULE_42_4 = "42.4"
RULE_42_5 = "42.5"

# Rule 42.1: a unit is recorded hidden only in one of these.
HIDING_KINDS = ("woods", "stone_building", "wooden_building")

CAUSE_MOVED = "the unit moved"
CAUSE_FIRED = "the unit fired"
CAUSE_SMOKE = "the unit made smoke"
CAUSE_ADJACENT = "an enemy unit is next to it"
CAUSE_HIT = "the attack on its hex had an effect"


class HiddenNotAvailable(NotImplementedError):
    """A part of rule 42 that waits for its own tier."""


def hex_allows_hiding(board: Board, hex_ref: HexRef) -> bool:
    """Rule 42.1: a unit is recorded hidden only in a woods hex or a building hex."""
    return board.hex(hex_ref).terrain in HIDING_KINDS


def hidden_units(state: State, player: int | None = None) -> tuple[Unit, ...]:
    """Each unit that is hidden, for one player or for both."""
    return tuple(
        u
        for u in state.units
        if u.hidden and not u.eliminated and (player is None or u.player == player)
    )


def hidden_in(state: State, hex_ref: HexRef, player: int | None = None) -> tuple[Unit, ...]:
    """The hidden units of a hex."""
    return tuple(u for u in hidden_units(state, player) if u.hex == hex_ref)


def enemy_hidden_in(state: State, hex_ref: HexRef, player: int) -> bool:
    """Whether a hidden unit of the other side is in this hex (rule 42.5)."""
    return any(u.player != player for u in hidden_in(state, hex_ref))


def can_hide(scenario_side: str, side_of: Mapping[int, str], board: Board, unit: Unit) -> bool:
    """Rule 42.1: this unit of the named side may go on the record instead of the board."""
    if not scenario_side or unit.hex is None:
        return False
    if side_of.get(unit.player) != scenario_side:
        return False
    return hex_allows_hiding(board, unit.hex)


def reveal(state: State, unit_ids: Iterable[int], cause: str, rule_id: str = RULE_42_2) -> tuple[State, list[Event]]:
    """Put hidden units on the board, and say why (rules 42.2 and 42.4)."""
    events: list[Event] = []
    changed: dict[int, Unit] = {}
    for unit_id in sorted(set(unit_ids)):
        unit = state.units[unit_id]
        if not unit.hidden or unit.eliminated:
            continue
        changed[unit_id] = unit.with_(hidden=False)
        events.append(
            Event(
                rule_id,
                "revealed",
                {
                    "unit": unit_id,
                    "hex": geometry.hex_id(*unit.hex) if unit.hex else None,
                    "cause": cause,
                },
            )
        )
    if not changed:
        return state, []
    return state.with_units(changed), events


def reveal_in(state: State, hex_ref: HexRef, player: int | None, cause: str, rule_id: str = RULE_42_2) -> tuple[State, list[Event]]:
    """Put every hidden unit of a hex on the board."""
    ids = [u.id for u in hidden_in(state, hex_ref, player)]
    return reveal(state, ids, cause, rule_id)


def refresh_adjacency(state: State, board: Board) -> tuple[State, list[Event]]:
    """Rule 42.2: a hidden unit next to an enemy unit comes on the board.

    The rule tests it at the end of a Defensive Fire Phase and at the end of an Advance
    Phase, which are the two phases that put the two sides next to each other.
    """
    ids = []
    for unit in hidden_units(state):
        if unit.hex is None:
            continue
        for other in board.neighbors(unit.hex):
            if any(u.player != unit.player and not u.eliminated for u in state.infantry_in(other)):
                ids.append(unit.id)
                break
    return reveal(state, ids, CAUSE_ADJACENT)


def halves_for(state: State, target: HexRef, halves: int) -> int:
    """Rule 42.4 with rule 9.4: fire on a hex that holds a hidden unit is half strength.

    The halving is per unit of firepower and not per fire group, in the same way as the
    concealment halving of rule 25.8.
    """
    return halves // 2 if hidden_in(state, target) else halves


def blind_fire_hexes(board: Board, firer: HexRef) -> tuple[HexRef, ...]:
    """The first half of rule 42.4, which waits for its own tier."""
    raise HiddenNotAvailable(
        "blind fire into a hex with no known enemy (rule 42.4) waits for its own tier, "
        "because it changes the legal list of each fire window and the action space of FR-50"
    )
