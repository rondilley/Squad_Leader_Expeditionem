"""Rule 27, sewer movement.

A sewer is a second level below the board. A stack that starts its Movement Phase on a
sewer entrance hex may announce sewer movement and try to come up at another sewer
entrance within three hexes. One die decides: 4 or less and the stack arrives, 5 or 6
and the stack is lost. A lost stack spends the rest of the turn off the board, and in
its next Movement Phase the opposing player names the entrance it comes up at, within
six hexes of where it went down (rules 27.1, 27.22).

Three properties make the move worth the risk. The stack pays no terrain cost for the
turn (rule 27.3). It cannot be fired at while it is under the street, except in the hex
where it comes up (rule 27.4). It arrives concealed when no enemy is next to it in the
same building (rule 27.5).

The cost is that a squad needs a leader with it (rule 27.21), that the heavy weapons
stay behind (rule 27.3), and that coming up in an occupied entrance hex is a fight the
defender starts at point blank range (rule 27.7).
"""

from __future__ import annotations

from typing import Iterable, Mapping

from slcore import geometry
from slcore.events import Event
from slcore.game import SewerParty, State
from slcore.geometry import HexRef
from slcore.state import Board
from slcore.units import KIND_LEADER, KIND_SW, Unit, UnitType

RULE_27_1 = "27.1"
RULE_27_2 = "27.2"
RULE_27_21 = "27.21"
RULE_27_22 = "27.22"
RULE_27_3 = "27.3"
RULE_27_4 = "27.4"
RULE_27_5 = "27.5"
RULE_27_6 = "27.6"
RULE_27_7 = "27.7"

MOVE_RANGE = 3
LOST_RANGE = 6
ARRIVE_ROLL = 4


def entrances(board: Board, state: State) -> tuple[HexRef, ...]:
    """The sewer entrance hexes that a charge has not closed (rules 27.1 and 27.6)."""
    closed = set(state.sewer_closed)
    return tuple(h.ref for h in board if h.sewer and h.ref not in closed)


def is_entrance(board: Board, state: State, hex_ref: HexRef | None) -> bool:
    if hex_ref is None or hex_ref not in board:
        return False
    return board.hex(hex_ref).sewer and hex_ref not in state.sewer_closed


def carryable(types: Mapping[str, UnitType], weapon: Unit) -> bool:
    """Rule 27.3: the heavy weapons do not go down the ladder.

    The counter data marks each of them, because the rule names weapons and not classes:
    heavy machine guns, mortars, one hundred and five millimetre guns, and anti-tank guns.
    """
    return not types[weapon.type_key].heavy


def party_in(state: State, hex_ref: HexRef, player: int) -> tuple[Unit, ...]:
    """The units of one player in the hex that could go down together."""
    return tuple(
        u
        for u in sorted(state.infantry_in(hex_ref), key=lambda u: u.id)
        if u.player == player and not u.broken and not u.moved and not u.eliminated
    )


def party_allowed(party: Iterable[Unit]) -> bool:
    """Rule 27.21: a squad needs a leader with it. A leader alone may go."""
    units = list(party)
    if not units:
        return False
    if any(u.kind == KIND_LEADER for u in units):
        return True
    return all(u.kind == KIND_LEADER for u in units)


def destinations(board: Board, state: State, start: HexRef) -> tuple[HexRef, ...]:
    """Rule 27.2: another entrance within three hexes."""
    return tuple(
        h for h in entrances(board, state) if h != start and geometry.distance(start, h) <= MOVE_RANGE
    )


def lost_destinations(board: Board, state: State, start: HexRef) -> tuple[HexRef, ...]:
    """Rule 27.22: where the opposing player may bring a lost stack up, within six hexes."""
    return tuple(h for h in entrances(board, state) if geometry.distance(start, h) <= LOST_RANGE)


def drop_heavy(state: State, types: Mapping[str, UnitType], unit_ids: Iterable[int]) -> tuple[State, list[Event]]:
    """Rule 27.3: the weapons that cannot go down stay in the entrance hex."""
    events: list[Event] = []
    changed = {}
    for uid in unit_ids:
        carrier = state.units[uid]
        for w in state.carried_by(uid):
            if carryable(types, w):
                continue
            changed[w.id] = w.with_(carrier=None, hex=carrier.hex)
            events.append(Event(RULE_27_3, "left_behind", {"unit": uid, "weapon": w.id}))
    return (state.with_units(changed) if changed else state), events


def send(state: State, unit_ids: tuple[int, ...], start: HexRef, target: HexRef, die: int) -> tuple[State, list[Event]]:
    """Rule 27.22: the die decides between the chosen entrance and the sewer."""
    arrived = die <= ARRIVE_ROLL
    data = {"units": list(unit_ids), "from": geometry.hex_id(*start), "to": geometry.hex_id(*target), "die": die}
    if arrived:
        changed = {}
        for uid in unit_ids:
            unit = state.units[uid]
            changed[uid] = unit.with_(hex=target, moved=True, sewer_move=True, mf_used=0, track=(start, target))
            for w in state.carried_by(uid):
                changed[w.id] = w.with_(hex=target, moved=True)
        return state.with_units(changed), [Event(RULE_27_22, "sewer_move", data)]
    changed = {}
    for uid in unit_ids:
        unit = state.units[uid]
        changed[uid] = unit.with_(hex=None, moved=True, sewer_move=True, mf_used=0, track=())
        for w in state.carried_by(uid):
            changed[w.id] = w.with_(hex=None, moved=True)
    state = state.with_units(changed)
    state = state.with_(sewer_lost=state.sewer_lost + (SewerParty(unit_ids, start),))
    return state, [Event(RULE_27_22, "sewer_lost", data)]


def surface(state: State, party: SewerParty, target: HexRef) -> tuple[State, list[Event]]:
    """Rule 27.22: the opposing player names the entrance, and the stack comes up there."""
    changed = {}
    for uid in party.units:
        unit = state.units[uid]
        if unit.eliminated:
            continue
        changed[uid] = unit.with_(hex=target, moved=True, sewer_move=True, track=(party.start, target))
        for w in state.carried_by(uid):
            changed[w.id] = w.with_(hex=target, moved=True)
    state = state.with_units(changed)
    state = state.with_(sewer_lost=tuple(p for p in state.sewer_lost if p is not party))
    return state, [
        Event(
            RULE_27_22,
            "sewer_surface",
            {"units": list(party.units), "from": geometry.hex_id(*party.start), "to": geometry.hex_id(*target)},
        )
    ]


def close(state: State, hex_ref: HexRef) -> State:
    """Rule 27.6: a demolition charge in an entrance hex closes it for the scenario."""
    if hex_ref in state.sewer_closed:
        return state
    return state.with_(sewer_closed=tuple(sorted(state.sewer_closed + (hex_ref,))))


def arrivals(state: State, player: int) -> tuple[Unit, ...]:
    """The units that came up this turn, for the concealment of rule 27.5."""
    return tuple(u for u in state.player_units(player) if u.sewer_move and u.hex is not None)


def same_building_enemy(board: Board, state: State, hex_ref: HexRef, player: int) -> bool:
    """Rule 27.5: an enemy next to the arrival hex in the same building."""
    building = board.hex(hex_ref).building
    for other in geometry.neighbors(*hex_ref):
        if other not in board:
            continue
        if building is None or board.hex(other).building is None or board.hex(other).building.id != building.id:
            continue
        for u in state.infantry_in(other):
            if u.player != player:
                return True
    for u in state.infantry_in(hex_ref):
        if u.player != player:
            return True
    return False
