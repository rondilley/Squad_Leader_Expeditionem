"""The per-player view (AR-09, FR-42).

The host calculates a view for one player before each outbound message, prompt, trace,
log line, and public replay. A view holds the player's own units in full and the
opponent's units that the rules let that player see.

Rule 25.2 says a stack below a concealment counter cannot be inspected by the opposing
player and must be treated as an opposing squad until proven otherwise. So the view of
the opponent holds a token and not the units: the identity of the counter, its hex, and
how many counters are stacked there. A counter with no unit below it is a dummy (rule
25.7), and the token of a dummy is the same as the token of a full stack. That is the
whole point of the rule, and it is why the count of counters is in the token while the
count of units is not.

A player always sees its own units and its own counters in full.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from slcore import geometry
from slcore.game import State
from slcore.geometry import HexRef
from slcore.units import KIND_LEADER, KIND_SW, KIND_VEHICLE, Unit, UnitType


@dataclass(frozen=True)
class UnitView:
    """One unit as one player sees it."""

    id: int
    player: int
    type_key: str
    kind: str
    hex: HexRef | None
    carrier: int | None
    broken: bool
    berserk: bool
    prep_fired: bool
    moved: bool
    malfunction: bool
    dm: bool
    name: str
    firepower: int
    range: int
    morale: int
    leadership: int
    own: bool
    # Rules 28 to 41. A counter that is not a vehicle leaves each of these at its default
    # and `to_dict` writes none of them, so an infantry view is the document it was.
    facing: int = -1
    wreck: bool = False
    immobilized: bool = False
    crew_exposed: bool = False
    riding: int | None = None
    gun: int = 0
    movement_points: int = 0
    # Rule 16.1 and rule 16.4: the hexes the unit entered in this Movement Phase, and the
    # hex it holds while the defender fires at it on its track. The legal list of the
    # defender names each track hex already, so the view discloses nothing new (AR-09). A
    # window draws the track as shaded hexes and keeps the counter at its end hex.
    track: tuple[HexRef, ...] = ()
    returned_from: HexRef | None = None
    # The face of the counter, as the 1977 counter prints it (RV-10). Each of these is on
    # the front of the piece, so a view gives away nothing that the table does not show.
    elite: bool = False
    breakdown: int = 0
    weapon_class: str = ""
    vehicle_class: str = ""
    open_top: bool = False
    transport_pp: int = 0
    mg_ca: int = 0
    mg_360: int = 0
    gun_he_only: bool = False
    gun_low_velocity: bool = False
    survival: int = 0

    def to_dict(self) -> dict[str, Any]:
        face: dict[str, Any] = {}
        if self.kind == KIND_VEHICLE:
            face = {
                "facing": self.facing,
                "wreck": self.wreck,
                "immobilized": self.immobilized,
                "crew_exposed": self.crew_exposed,
                "gun": self.gun,
                "movement_points": self.movement_points,
                "vehicle_class": self.vehicle_class,
                "open_top": self.open_top,
                "transport_pp": self.transport_pp,
                "mg_ca": self.mg_ca,
                "mg_360": self.mg_360,
                "gun_he_only": self.gun_he_only,
                "gun_low_velocity": self.gun_low_velocity,
                "survival": self.survival,
            }
        elif self.kind == KIND_SW:
            face = {"breakdown": self.breakdown, "weapon_class": self.weapon_class}
        elif self.kind != KIND_LEADER:
            face = {"elite": self.elite}
        if self.riding is not None:
            face["riding"] = self.riding
        return {**self._base(), **face}

    def _base(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "player": self.player,
            "type": self.type_key.split(":")[-1],
            "nationality": self.type_key.split(":")[0],
            "kind": self.kind,
            "hex": None if self.hex is None else geometry.hex_id(*self.hex),
            "carrier": self.carrier,
            "broken": self.broken,
            "berserk": self.berserk,
            "prep_fired": self.prep_fired,
            "moved": self.moved,
            "malfunction": self.malfunction,
            "dm": self.dm,
            "name": self.name,
            "firepower": self.firepower,
            "range": self.range,
            "morale": self.morale,
            "leadership": self.leadership,
            "own": self.own,
            "track": [geometry.hex_id(*h) for h in self.track],
            "returned_from": None if self.returned_from is None else geometry.hex_id(*self.returned_from),
        }


_UNIT_KEYS = frozenset({"unit", "weapon", "leader", "carrier", "vehicle", "placer"})
_UNIT_LIST_KEYS = frozenset({"units", "attackers", "targets"})


def _named_unit_ids(value: Any, found: list[int]) -> None:
    """The unit ids a log line names. A hex string and a die are not unit ids."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _UNIT_KEYS and isinstance(item, int):
                found.append(item)
            elif key in _UNIT_LIST_KEYS and isinstance(item, list):
                for one in item:
                    if isinstance(one, int):
                        found.append(one)
                    else:
                        _named_unit_ids(one, found)
            else:
                _named_unit_ids(item, found)
    elif isinstance(value, list):
        for item in value:
            _named_unit_ids(item, found)


def secret_from(state: State, unit: Unit, viewer: int) -> bool:
    """True when this viewer must not read a log line that names the unit.

    An own unit stays in the owner's log, including after it is eliminated.
    `visible_to` rejects every eliminated unit, and that would strip the owner's
    own loss from the log. An enemy unit is secret while it is concealed or hidden,
    and it stays secret after it dies if that mark is still on it.
    """
    if unit.player == viewer:
        return False
    if hidden_from(state, unit, viewer) or concealed_from(state, unit, viewer):
        return True
    if unit.eliminated:
        return False
    return not visible_to(state, unit, viewer)


def event_visible(state: State, entry: dict[str, Any], viewer: int) -> bool:
    """Whether this log line may go to this viewer (AR-09).

    A line that names a unit `secret_from` rejects does not go out. A `demo_placed`
    line goes only to the player who placed the charge. The check reads the state
    now, so a move that was public becomes hidden once the unit is concealed.
    """
    data = entry.get("data") or {}
    if entry.get("kind") == "demo_placed":
        unit_id = data.get("unit")
        if not isinstance(unit_id, int) or unit_id < 0 or unit_id >= len(state.units):
            return False
        return state.units[unit_id].player == viewer
    named: list[int] = []
    _named_unit_ids(data, named)
    for unit_id in named:
        if unit_id < 0 or unit_id >= len(state.units):
            continue
        if secret_from(state, state.units[unit_id], viewer):
            return False
    return True


def visible_to(state: State, unit: Unit, viewer: int) -> bool:
    """A player sees each of its own counters, on the board or waiting for set up.

    A player sees the opponent's counters that are on the board and that no concealment
    counter of the opponent covers (rule 25.2). A weapon that a concealed unit carries is
    concealed with its carrier. A hidden unit of rule 42.1 is on no board that the other
    player sees, so it is not in the view at all.
    """
    if unit.eliminated:
        return False
    if unit.player == viewer:
        return True
    if unit.hex is None and unit.carrier is None:
        return False
    if hidden_from(state, unit, viewer):
        return False
    return not concealed_from(state, unit, viewer)


def hidden_from(state: State, unit: Unit, viewer: int) -> bool:
    """Rule 42.1: this unit of the other side is on the record and not on the board.

    A weapon that a hidden unit carries is hidden with its carrier, in the same way as a
    weapon below a concealment counter.
    """
    if unit.player == viewer:
        return False
    if unit.hidden:
        return True
    if unit.carrier is not None:
        carrier = state.units[unit.carrier]
        return bool(carrier.hidden)
    return False


def concealed_from(state: State, unit: Unit, viewer: int) -> bool:
    """Rule 25.2: this unit of the other side is below a concealment counter."""
    if unit.player == viewer:
        return False
    where = unit.hex if unit.carrier is None else state.units[unit.carrier].hex
    if where is None:
        return False
    return any(c.hex == where and c.player == unit.player for c in state.concealment)


def tokens_for(state: State, viewer: int) -> list[dict[str, Any]]:
    """The concealment counters as this player sees them (rule 25.2, AR-09).

    The viewer's own counters carry the units below them, because the viewer already
    sees those units. The opponent's counters carry nothing but their identity, their
    hex, and how many counters are stacked in that hex (rule 25.7).
    """
    by_hex: dict[HexRef, list] = {}
    for counter in state.concealment:
        by_hex.setdefault(counter.hex, []).append(counter)
    out: list[dict[str, Any]] = []
    for counter in sorted(state.concealment, key=lambda c: c.id):
        item: dict[str, Any] = {
            "id": counter.id,
            "hex": geometry.hex_id(*counter.hex),
            "own": counter.player == viewer,
            "stack": len(by_hex[counter.hex]),
        }
        if counter.player == viewer:
            item["player"] = counter.player
            item["units"] = [
                u.id for u in state.units_in(counter.hex) if u.player == viewer and not u.eliminated
            ]
        out.append(item)
    return out


def unit_view(types: Mapping[str, UnitType], unit: Unit, viewer: int) -> UnitView:
    t = types[unit.type_key]
    return UnitView(
        id=unit.id,
        player=unit.player,
        type_key=unit.type_key,
        kind=unit.kind,
        hex=unit.hex,
        carrier=unit.carrier,
        broken=unit.broken,
        berserk=unit.berserk,
        prep_fired=unit.prep_fired,
        moved=unit.moved,
        malfunction=unit.malfunction,
        dm=unit.dm,
        name=unit.name,
        firepower=t.firepower,
        range=t.range,
        morale=t.broken_morale if unit.broken else t.morale,
        leadership=t.leadership,
        own=unit.player == viewer,
        facing=unit.facing,
        wreck=unit.wreck,
        immobilized=unit.immobilized,
        crew_exposed=unit.crew_exposed,
        riding=unit.passenger_of,
        track=unit.track,
        returned_from=unit.returned_from,
        gun=t.gun,
        movement_points=t.mp,
        elite=t.elite,
        breakdown=t.breakdown,
        weapon_class=t.weapon_class,
        vehicle_class=t.vehicle_class,
        open_top=t.open_top,
        transport_pp=t.transport_pp,
        mg_ca=t.mg_ca,
        mg_360=t.mg_360,
        gun_he_only=t.gun_he_only,
        gun_low_velocity=t.gun_low_velocity,
        survival=t.survival,
    )


SPECTATOR = -1


def nationalities_of(state: State) -> dict[str, str]:
    """The army of each player, keyed by the player number as a string.

    A side that fields two armies takes the army of its first unit. The order of battle is
    on the scenario card, so this discloses nothing (AR-09).
    """
    out: dict[str, str] = {}
    for unit in state.units:
        key = str(unit.player)
        if key not in out:
            out[key] = unit.type_key.split(":")[0]
    return out


def _member_visible(state: State, unit_id: int, weapon_id: int | None, viewer: int) -> bool:
    if not visible_to(state, state.units[unit_id], viewer):
        return False
    if weapon_id is not None and not visible_to(state, state.units[weapon_id], viewer):
        return False
    return True


def _fire_group_view(state: State, viewer: int, spectator: bool) -> dict[str, Any] | None:
    """The open fire group as this viewer may see it.

    A member or a leader that `visible_to` rejects is omitted. The target hex stays,
    because the hex of the shot is not the identity of a hidden unit.
    """
    group = state.fire_group
    if group is None:
        return None
    if spectator:
        members = [[u, w] for u, w in group.members]
        leader = group.leader
    else:
        members = [[u, w] for u, w in group.members if _member_visible(state, u, w, viewer)]
        leader = group.leader
        if leader is not None and not visible_to(state, state.units[leader], viewer):
            leader = None
    return {
        "target": geometry.hex_id(*group.target),
        "members": members,
        "leader": leader,
    }


def build(
    state: State, types: Mapping[str, UnitType], viewer: int, spectator: bool = False
) -> dict[str, Any]:
    """The document that the host sends to one player.

    With `spectator` the document holds each unit of each side. That view goes to a watcher
    of a game between two computer opponents, where no person holds a seat and so no person
    can gain by what the view shows. The host refuses to build it in any other game, and
    `visible_to` still decides what a seated player sees (AR-09).
    """
    units = [
        unit_view(types, u, viewer).to_dict()
        for u in state.units
        if spectator or visible_to(state, u, viewer)
    ]
    if spectator:
        units = [u for u in units if not state.units[u["id"]].eliminated]
    return {
        "viewer": viewer,
        "spectator": spectator,
        # The army of each side, from its order of battle. The scenario card prints it, so
        # a concealment token can take the stock of its army (rule 25, RV-10 section 5).
        "nationalities": nationalities_of(state),
        "concealment": tokens_for(state, viewer),
        "smoke": [geometry.hex_id(*s.hex) for s in state.smoke],
        "demo": [
            {"id": d.id, "hex": geometry.hex_id(*d.hex), "own": d.player == viewer}
            for d in state.demo
            if spectator or d.player == viewer
        ],
        "turn": state.turn,
        "turn_limit": state.turn_limit,
        "phase": state.phase,
        "phasing": state.phasing,
        "active": state.active,
        "game_over": state.game_over,
        "result": state.result,
        "result_cause": state.result_cause,
        "melee": [geometry.hex_id(*h) for h in state.melee],
        "fire_group": _fire_group_view(state, viewer, spectator),
        "units": units,
    }


def board_document(board: Any) -> dict[str, Any]:
    """The board as the client draws it. The client has no rule logic (AR-06)."""
    hexes = []
    for h in board:
        item: dict[str, Any] = {
            "id": h.id,
            "col": h.col,
            "row": h.row,
            "center": list(h.center),
            "terrain": h.terrain,
        }
        if h.road:
            item["road"] = True
        if h.elevation:
            item["elevation"] = h.elevation
        if h.building is not None:
            item["building"] = {"id": h.building.id, "size": h.building.size, "kind": h.building.kind}
        sides = {str(d): f for d, f in enumerate(h.hexsides) if f is not None}
        if sides:
            item["hexsides"] = sides
        item["polygons"] = [{"kind": p.kind, "points": [list(pt) for pt in p.points]} for p in h.polygons]
        hexes.append(item)
    return {
        "name": board.name,
        "cols": board.cols,
        "rows": board.rows,
        "hexes": hexes,
        "terrain": {
            name: {"tem": t.tem, "mf_halves": t.mf_halves, "los": t.los, "building": t.building}
            for name, t in board.terrain.items()
        },
    }


def hidden_unit_ids(state: State, viewer: int) -> tuple[int, ...]:
    """The units that a view for this player must not name (TR-09)."""
    return tuple(u.id for u in state.units if not visible_to(state, u, viewer) and u.player != viewer)


def hidden_hex_ids(state: State, viewer: int) -> tuple[str, ...]:
    """The hexes whose contents the view must not describe, for the secrecy test.

    A hex below an opposing concealment counter is one of them. The hex itself is on the
    board and the viewer sees the counter, so the hex name is not a secret. What the
    view must not carry is the identity of a unit in it.
    """
    hidden = set()
    for u in state.units:
        if u.player == viewer or u.eliminated:
            continue
        if concealed_from(state, u, viewer) and u.hex is not None:
            hidden.add(geometry.hex_id(*u.hex))
    return tuple(sorted(hidden))
