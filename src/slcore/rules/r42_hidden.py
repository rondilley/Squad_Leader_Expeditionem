"""Rule 42, Hidden Initial Placement (FR-10).

Concealment (rule 25) tells the other player where a unit is not. Hidden initial placement
tells the other player nothing at all: the unit is not on the board that the opponent sees,
and the owner keeps its position on the scenario record.

Rule 42 is optional. The text says both players agree to it, unless the scenario in play
names it. So a scenario names the side that may use it, and no other scenario changes.

What this module applies:

- 42.1: a side that the scenario names records a unit hidden, and only in a woods hex or a
  building hex. Each other unit of that side goes on the board in full view. Rule 42.7
  limits an AFV to a woods hex or a wood building hex (PR-49).
- 42.2: a hidden unit comes on the board when it moves, when it fires, when it makes smoke,
  or when it is next to an enemy unit at the end of a Defensive Fire Phase or an Advance
  Phase. Entrenchment is rule 51 and it waits for its own tier.
- 42.3: a unit that came on the board does not go back. It can take a concealment counter,
  which is rule 25.3.
- 42.4, the second half: a hidden unit in a target hex comes on the board when an attack on
  that hex gives a result that is not "No Effect". Fire on a hex that holds a hidden unit is
  half strength, which is the Area Fire of rule 9.4.
- 42.5: a unit that moves into the hex of a hidden unit stops there and ends its Movement
  Phase in the hex it came from. PR-32 applies the same stop to each unit of a stack move
  and to a rout, and an advance or any other entry into the hex reveals the unit at once
  (`reveal_contact`).

- 42.4, the first half: a player may fire blind into a hex where no enemy is known to be,
  at half strength. PR-52 gives the hexes: each woods or building hex with no unit of the
  firer's side, when the scenario gives the other side hidden placement
  (`blind_fire_hexes`). A scenario with no hidden placement keeps its legal list.
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
# Rule 42.7: an AFV starts hidden only in a woods hex or a wood building hex.
AFV_HIDING_KINDS = ("woods", "wooden_building")

CAUSE_MOVED = "the unit moved"
CAUSE_FIRED = "the unit fired"
CAUSE_SMOKE = "the unit made smoke"
CAUSE_ADJACENT = "an enemy unit is next to it"
CAUSE_HIT = "the attack on its hex had an effect"
CAUSE_CONTACT = "an enemy unit entered its hex"


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
    """Rules 42.1 and 42.7: this unit of the named side may go on the record instead of the board.

    Rule 42.7 lets an AFV start hidden in a woods hex or a wood building hex only (PR-49).
    A support weapon goes with the unit that carries it and is not recorded by itself.
    """
    if not scenario_side or unit.hex is None:
        return False
    if side_of.get(unit.player) != scenario_side:
        return False
    if unit.is_vehicle:
        return board.hex(unit.hex).terrain in AFV_HIDING_KINDS
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
    Phase, which are the two phases that put the two sides next to each other. The hex of
    the hidden unit counts as well as the hexes next to it (PR-32). A concealment counter of
    the other side counts as an enemy unit (rule 25.2, PR-31), so a dummy reveals the unit
    as a real stack would.
    """
    ids = []
    for unit in hidden_units(state):
        if unit.hex is None:
            continue
        for other in [unit.hex] + list(board.neighbors(unit.hex)):
            if state.enemy_counter_in(other, unit.player) or any(
                u.player != unit.player and not u.eliminated for u in state.infantry_in(other)
            ):
                ids.append(unit.id)
                break
    return reveal(state, ids, CAUSE_ADJACENT)


def reveal_contact(state: State) -> tuple[State, list[Event]]:
    """PR-32: a hidden unit whose hex an enemy unit entered comes on the board at once.

    A move and a rout stop before the hex (rule 42.5). An advance, a sewer arrival, a
    debark, or a return of rule 16.1 does not, and then the two sides share the hex.
    """
    ids = []
    for unit in hidden_units(state):
        if unit.hex is None:
            continue
        if any(
            u.player != unit.player and not u.eliminated and not u.hidden and (u.is_infantry or u.is_vehicle)
            for u in state.units_in(unit.hex)
        ):
            ids.append(unit.id)
    return reveal(state, ids, CAUSE_CONTACT)


def halves_for(state: State, target: HexRef, halves: int) -> int:
    """Rule 42.4 with rule 9.4: fire on a hex that holds a hidden unit is half strength.

    The halving is per unit of firepower and not per fire group, in the same way as the
    concealment halving of rule 25.8.
    """
    return halves // 2 if hidden_in(state, target) else halves


def blind_fire_hexes(board: Board, state: State, player: int, known: Iterable[HexRef]) -> frozenset[HexRef]:
    """The first half of rule 42.4 with PR-52: the hexes this player may fire blind into.

    A hex is a woods or building hex (rule 42.1), because only such a hex can hold a
    hidden unit. It holds no unit and no concealment counter of the player's side, because
    a hidden enemy cannot share a hex with them (PR-32). `known` is the enemy hexes that
    are targets already. The set reads no hidden unit, so it is the same whether a hidden
    unit is there or not.
    """
    own = {u.hex for u in state.units if u.player == player and u.hex is not None and not u.eliminated}
    own.update(c.hex for c in state.concealment if c.player == player)
    taken = own | set(known)
    return frozenset(h.ref for h in board if hex_allows_hiding(board, h.ref) and h.ref not in taken)
