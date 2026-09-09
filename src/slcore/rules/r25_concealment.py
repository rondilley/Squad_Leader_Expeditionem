"""Rule 25, concealment.

A concealment counter sits on a hex. The units of that side below it are concealed. The
opposing player sees the counter and not the units (rule 25.2), which is why the counter
has its own identity: the view gives the opponent a token and never a unit (AR-09).

A counter with no unit below it is a dummy (rule 25.7), and the opposing view cannot
tell it from a counter with a stack below it.

Two rules make the fire arithmetic: rule 25.8 halves the firepower against a hex with a
counter, under the area fire provision of rule 9.4, and rule 25.41 keeps the fire at
full strength against the units in that hex that are not concealed. So the halving is
for each unit, and not for the fire group.
"""

from __future__ import annotations

from typing import Iterable, Mapping

from slcore import geometry
from slcore.events import Event
from slcore.game import Concealment, State
from slcore.geometry import HexRef
from slcore.state import Board
from slcore.units import KIND_LEADER, KIND_SQUAD, Unit

RULE_25_1 = "25.1"
RULE_25_2 = "25.2"
RULE_25_3 = "25.3"
RULE_25_4 = "25.4"
RULE_25_41 = "25.41"
RULE_25_42 = "25.42"
RULE_25_5 = "25.5"
RULE_25_6 = "25.6"
RULE_25_7 = "25.7"
RULE_25_8 = "25.8"
RULE_25_9 = "25.9"

PLACEABLE_KINDS = (KIND_SQUAD, KIND_LEADER)


def hex_allows_concealment(board: Board, hex_ref: HexRef) -> bool:
    """Rule 25.3: a counter goes on a woods hex or a building hex, and nowhere else."""
    if hex_ref not in board:
        return False
    h = board.hex(hex_ref)
    if h.building is not None:
        return True
    return board.terrain[h.terrain].building or h.terrain == "woods"


def adjacent_enemy(state: State, hex_ref: HexRef, player: int) -> bool:
    """Rule 25.3 and 25.4: an enemy infantry unit in this hex or next to it."""
    around = [hex_ref] + list(geometry.neighbors(*hex_ref))
    for u in state.units:
        if u.eliminated or u.player == player or not u.is_infantry or u.carrier is not None:
            continue
        if u.hex in around:
            return True
    return False


def quiet(unit: Unit) -> bool:
    """Rule 25.3: the unit did not move, fire, make smoke, or take a Morale Check."""
    return not (unit.moved or unit.fired or unit.made_smoke or unit.dm or unit.mf_used or unit.sewer_move)


def can_conceal(state: State, board: Board, unit: Unit) -> bool:
    """Rule 25.3: the conditions for a counter at the end of a complete player turn."""
    if unit.eliminated or unit.hex is None or unit.carrier is not None:
        return False
    if unit.kind not in PLACEABLE_KINDS:
        return False
    if not quiet(unit):
        return False
    if not hex_allows_concealment(board, unit.hex):
        return False
    if state.in_melee(unit.hex):
        return False
    if adjacent_enemy(state, unit.hex, unit.player):
        return False
    return True


def add(state: State, player: int, hex_ref: HexRef) -> tuple[State, Concealment]:
    """One new counter with the next identity. The identity never repeats in a game."""
    counter = Concealment(state.next_marker, player, hex_ref)
    return state.with_(concealment=state.concealment + (counter,), next_marker=state.next_marker + 1), counter


def grow(state: State, board: Board) -> tuple[State, list[Event]]:
    """Rule 25.3: the automatic step at the end of a complete player turn.

    One counter goes on each hex that satisfies the conditions and does not have one.
    """
    events: list[Event] = []
    for player in (0, 1):
        hexes: list[HexRef] = []
        for unit in sorted(state.player_units(player), key=lambda u: u.id):
            if unit.hex in hexes:
                continue
            if not can_conceal(state, board, unit):
                continue
            if any(c.hex == unit.hex and c.player == player for c in state.concealment):
                continue
            hexes.append(unit.hex)
        for hex_ref in hexes:
            state, counter = add(state, player, hex_ref)
            events.append(
                Event(RULE_25_3, "concealed", {"counter": counter.id, "player": player, "hex": geometry.hex_id(*hex_ref)})
            )
    return state, events


def remove_in(state: State, hex_ref: HexRef, player: int | None, rule: str, cause: str) -> tuple[State, list[Event]]:
    """Rule 25.42: when one unit of a hex acts, every counter of that side in the hex goes.

    With `player` None the call removes the counters of both sides, which is what rule
    25.9 asks for after an attack that had a result.
    """
    keep = []
    gone = []
    for c in state.concealment:
        if c.hex == hex_ref and (player is None or c.player == player):
            gone.append(c)
        else:
            keep.append(c)
    if not gone:
        return state, []
    events = [
        Event(rule, "unconcealed", {"counter": c.id, "player": c.player, "hex": geometry.hex_id(*hex_ref), "cause": cause})
        for c in gone
    ]
    return state.with_(concealment=tuple(keep)), events


def remove_for_units(state: State, unit_ids: Iterable[int], rule: str, cause: str) -> tuple[State, list[Event]]:
    """Rule 25.4: the counter over each of these units goes, whatever the unit did."""
    events: list[Event] = []
    seen: set[tuple[HexRef, int]] = set()
    for uid in unit_ids:
        unit = state.units[uid]
        if unit.hex is None:
            continue
        key = (unit.hex, unit.player)
        if key in seen:
            continue
        seen.add(key)
        state, ev = remove_in(state, unit.hex, unit.player, rule, cause)
        events.extend(ev)
    return state, events


def refresh_adjacency(state: State) -> tuple[State, list[Event]]:
    """Rule 25.4 after Defensive Fire and Advance: a counter next to an enemy comes off.

    Rule 25.5 is the reason this runs at the end of the phase and not at the moment of
    the move. An enemy that Defensive Fire eliminated or broke does not remove a counter,
    and a broken unit is not an infantry unit for this test.
    """
    events: list[Event] = []
    for counter in list(state.concealment):
        if unbroken_enemy_near(state, counter.hex, counter.player):
            state, ev = remove_in(state, counter.hex, counter.player, RULE_25_4, "an enemy unit is adjacent")
            events.extend(ev)
    return state, events


def unbroken_enemy_near(state: State, hex_ref: HexRef, player: int) -> bool:
    """Rule 25.5: a broken or eliminated enemy does not take a counter off."""
    around = [hex_ref] + list(geometry.neighbors(*hex_ref))
    for u in state.units:
        if u.eliminated or u.player == player or not u.is_infantry or u.carrier is not None or u.broken:
            continue
        if u.hex in around:
            return True
    return False


def halves_for(state: State, unit: Unit, halves: int) -> int:
    """Rules 25.8, 25.41, and 9.4: the firepower against one unit of the target hex."""
    return halves // 2 if state.concealed(unit) else halves


def counters_left(state: State, player: int, allowed: Mapping[int, int]) -> int:
    """Rule 25.6: how many of the counters the scenario gave are still to place."""
    placed = sum(1 for c in state.concealment if c.player == player)
    return max(0, int(allowed.get(player, 0)) - placed)
