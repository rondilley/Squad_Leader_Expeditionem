"""Unit types (rule 2) and unit state.

A UnitType is one counter type from the counter data. A Unit is one counter in
a game with its current state. Support weapons are units of kind "sw" with a
carrier.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Mapping

from slcore.geometry import HexRef

KIND_SQUAD = "squad"
KIND_CREW = "crew"
KIND_LEADER = "leader"
KIND_SW = "sw"
KIND_VEHICLE = "vehicle"
INFANTRY_KINDS = (KIND_SQUAD, KIND_CREW, KIND_LEADER)

MOVE_MODE_NONE = ""
MOVE_MODE_SOLO = "solo"
MOVE_MODE_STACK = "stack:"

# Rule 28: the vehicle classes of the counter set. A tank has a turret, a self-propelled
# gun does not. Rule 28 says the halftrack, the truck, and the jeep have rules of their
# own that come later, and project ruling PR-20 keeps them out of a scenario until then.
CLASS_TANK = "tank"
CLASS_SP_GUN = "sp_gun"
CLASS_HALFTRACK = "halftrack"
CLASS_TRUCK = "truck"
CLASS_JEEP = "jeep"
ARMOURED_CLASSES = (CLASS_TANK, CLASS_SP_GUN, CLASS_HALFTRACK)
THIS_TIER_CLASSES = (CLASS_TANK, CLASS_SP_GUN)


@dataclass(frozen=True)
class UnitType:
    key: str
    nationality: str
    kind: str
    firepower: int = 0
    range: int = 0
    morale: int = 0
    broken_morale: int = 0
    leadership: int = 0
    breakdown: int = 0
    penetration: int = 0
    pp_squad: int = 0
    pp_leader: int | None = None
    # Rule 37.35: a panzerfaust counts as half a machine gun for portage, so portage is
    # kept in halves as well as movement factors are (NFR-05). A weapon with no half value
    # in its data uses twice its whole value.
    pp_squad_half: int = 0
    pp_leader_half: int | None = None
    elite: bool = False
    assault_engineer: bool = False
    weapon_class: str = ""
    heavy: bool = False
    # Rule 28: the printed values of a vehicle counter.
    vehicle_class: str = ""
    mp: int = 0
    gun: int = 0
    gun_he_only: bool = False
    gun_low_velocity: bool = False
    mg_ca: int = 0
    mg_360: int = 0
    survival: int = 0
    armor_key: str = ""
    open_top: bool = False
    fires_twice: bool = False
    transport_pp: int = 0
    canister: bool = False
    heat: bool = False
    quad_fifty: bool = False

    @property
    def is_squad_like(self) -> bool:
        return self.kind in (KIND_SQUAD, KIND_CREW)

    @property
    def portage_squad_halves(self) -> int:
        """Rule 5.7 in halves: what one squad or crew pays to carry this weapon."""
        return self.pp_squad_half or self.pp_squad * 2

    @property
    def portage_leader_halves(self) -> int | None:
        """Rule 5.7 in halves for a leader. None means one leader cannot carry it."""
        if self.pp_leader_half is not None:
            return self.pp_leader_half
        return None if self.pp_leader is None else self.pp_leader * 2

    @property
    def free_portage_halves(self) -> int:
        return self.free_portage * 2

    @property
    def is_vehicle(self) -> bool:
        return self.kind == KIND_VEHICLE

    @property
    def is_afv(self) -> bool:
        """Rule 28: tanks, self-propelled guns, and halftracks are armoured fighting vehicles."""
        return self.vehicle_class in ARMOURED_CLASSES

    @property
    def is_turreted(self) -> bool:
        """Rule 28: a tank has a turret, so rule 33.31 case D lets it fire outside its arc."""
        return self.vehicle_class == CLASS_TANK

    @property
    def mp_halves(self) -> int:
        """Rule 28.1: the movement points of the counter, in halves (NFR-05)."""
        return self.mp * 2

    @property
    def mf_halves(self) -> int:
        """Rule 5.41 and 5.42: squads 4 MF, leaders 6 MF, in halves."""
        if self.kind == KIND_LEADER:
            return 12
        if self.kind in (KIND_SQUAD, KIND_CREW):
            return 8
        return 0

    @property
    def free_portage(self) -> int:
        """Rule 5.7: a squad carries 3 points free, a leader 1 point free."""
        if self.kind == KIND_LEADER:
            return 1
        if self.kind in (KIND_SQUAD, KIND_CREW):
            return 3
        return 0


def counter_types_from_dict(data: Mapping[str, Any]) -> dict[str, UnitType]:
    nationality = str(data["nationality"])
    out: dict[str, UnitType] = {}
    for key, row in data["types"].items():
        kind = str(row["kind"])
        pp_leader = row.get("pp_leader")
        out[key] = UnitType(
            key=key,
            nationality=nationality,
            kind=kind,
            firepower=int(row.get("fp", 0)),
            range=int(row.get("range", 0)),
            morale=int(row.get("morale", 0)),
            broken_morale=int(row.get("broken_morale", row.get("morale", 0))),
            leadership=int(row.get("leadership", 0)),
            breakdown=int(row.get("breakdown", 0)),
            penetration=int(row.get("penetration", 0)),
            pp_squad=int(row.get("pp_squad", 0)),
            pp_leader=None if pp_leader is None else int(pp_leader),
            pp_squad_half=int(row.get("pp_squad_half", 0)),
            pp_leader_half=None if row.get("pp_leader_half") is None else int(row["pp_leader_half"]),
            elite=bool(row.get("elite", False)),
            assault_engineer=bool(row.get("assault_engineer", False)),
            weapon_class=str(row.get("weapon_class", "")),
            heavy=bool(row.get("heavy", False)),
            vehicle_class=str(row.get("vehicle_class", "")),
            mp=int(row.get("mp", 0)),
            gun=int(row.get("gun", 0)),
            gun_he_only=bool(row.get("gun_he_only", False)),
            gun_low_velocity=bool(row.get("gun_low_velocity", False)),
            mg_ca=int(row.get("mg_ca", 0)),
            mg_360=int(row.get("mg_360", 0)),
            survival=int(row.get("survival", 0)),
            armor_key=str(row.get("armor_key", "")),
            open_top=bool(row.get("open_top", False)),
            fires_twice=bool(row.get("fires_twice", False)),
            transport_pp=int(row.get("transport_pp", 0)),
            canister=bool(row.get("canister", False)),
            heat=bool(row.get("heat", False)),
            quad_fifty=bool(row.get("quad_fifty", False)),
        )
    return out


@dataclass(frozen=True)
class Unit:
    id: int
    player: int
    type_key: str
    kind: str
    group: str
    name: str = ""
    hex: HexRef | None = None
    carrier: int | None = None
    broken: bool = False
    prep_fired: bool = False
    moved: bool = False
    mf_used: int = 0
    move_mode: str = MOVE_MODE_NONE
    track: tuple[HexRef, ...] = ()
    portage_max: int = 0
    dm: bool = False
    malfunction: bool = False
    eliminated: bool = False
    stay: bool = False
    fired: bool = False
    directed: bool = False
    rally_tried: bool = False
    repair_tried: bool = False
    berserk: bool = False
    returned_from: HexRef | None = None
    made_smoke: bool = False
    sewer_move: bool = False
    demo_placed: bool = False
    routed: bool = False
    hidden: bool = False
    # Rules 28 to 41. A unit that is not a vehicle leaves every one of these at its
    # default, and `to_dict` writes none of them, so a game with no vehicle has the same
    # state document and the same hash as before this tier.
    facing: int = -1
    mp_used: int = 0
    wreck: bool = False
    immobilized: bool = False
    crew_exposed: bool = False
    mg_malfunction: bool = False
    disabled: bool = False
    mg_disabled: bool = False
    passenger_of: int | None = None
    pivoted: bool = False
    gun_shots: int = 0
    mg_fired: bool = False
    boarded: bool = False
    overran: bool = False
    dischargers_used: bool = False
    canister_spent: bool = False
    from_wreck: int | None = None
    # Rule 17.4: this leader mans a machine gun, so rule 15.6 does not use the rating.
    manned_mg: bool = False

    @property
    def placed(self) -> bool:
        return self.hex is not None or self.carrier is not None

    @property
    def is_infantry(self) -> bool:
        return self.kind in INFANTRY_KINDS

    @property
    def is_weapon(self) -> bool:
        return self.kind == KIND_SW

    @property
    def is_vehicle(self) -> bool:
        return self.kind == KIND_VEHICLE

    @property
    def riding(self) -> bool:
        """Rule 31.2: the unit is on top of a vehicle counter and not on foot."""
        return self.passenger_of is not None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "player": self.player,
            "type": self.type_key,
            "kind": self.kind,
            "group": self.group,
            "name": self.name,
            "hex": None if self.hex is None else list(self.hex),
            "carrier": self.carrier,
            "broken": self.broken,
            "prep_fired": self.prep_fired,
            "moved": self.moved,
            "mf_used": self.mf_used,
            "move_mode": self.move_mode,
            "track": [list(h) for h in self.track],
            "portage_max": self.portage_max,
            "dm": self.dm,
            "malfunction": self.malfunction,
            "eliminated": self.eliminated,
            "stay": self.stay,
            "fired": self.fired,
            "directed": self.directed,
            "rally_tried": self.rally_tried,
            "repair_tried": self.repair_tried,
            "berserk": self.berserk,
            "returned_from": None if self.returned_from is None else list(self.returned_from),
            "made_smoke": self.made_smoke,
            "sewer_move": self.sewer_move,
            "demo_placed": self.demo_placed,
            "routed": self.routed,
            "hidden": self.hidden,
            "manned_mg": self.manned_mg,
        }
        # Only three kinds of counter ever leave one of these at a value that is not the
        # default: a vehicle, a unit that rides on one, and a crew counter in reserve. The
        # state hash reads this record for each unit of each state, so an infantry game
        # must not pay for sixteen lookups that give nothing (NFR-01).
        if self.kind == KIND_VEHICLE or self.passenger_of is not None or self.from_wreck is not None:
            for key, value in _VEHICLE_DEFAULTS.items():
                here = getattr(self, key)
                if here != value:
                    d[key] = here
        return d

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "Unit":
        return Unit(
            id=int(d["id"]),
            player=int(d["player"]),
            type_key=str(d["type"]),
            kind=str(d["kind"]),
            group=str(d["group"]),
            name=str(d.get("name", "")),
            hex=None if d.get("hex") is None else (int(d["hex"][0]), int(d["hex"][1])),
            carrier=None if d.get("carrier") is None else int(d["carrier"]),
            broken=bool(d.get("broken", False)),
            prep_fired=bool(d.get("prep_fired", False)),
            moved=bool(d.get("moved", False)),
            mf_used=int(d.get("mf_used", 0)),
            move_mode=str(d.get("move_mode", "")),
            track=tuple((int(h[0]), int(h[1])) for h in d.get("track", [])),
            portage_max=int(d.get("portage_max", 0)),
            dm=bool(d.get("dm", False)),
            malfunction=bool(d.get("malfunction", False)),
            eliminated=bool(d.get("eliminated", False)),
            stay=bool(d.get("stay", False)),
            fired=bool(d.get("fired", False)),
            directed=bool(d.get("directed", False)),
            rally_tried=bool(d.get("rally_tried", False)),
            repair_tried=bool(d.get("repair_tried", False)),
            berserk=bool(d.get("berserk", False)),
            returned_from=None if d.get("returned_from") is None else (int(d["returned_from"][0]), int(d["returned_from"][1])),
            made_smoke=bool(d.get("made_smoke", False)),
            sewer_move=bool(d.get("sewer_move", False)),
            demo_placed=bool(d.get("demo_placed", False)),
            routed=bool(d.get("routed", False)),
            hidden=bool(d.get("hidden", False)),
            manned_mg=bool(d.get("manned_mg", False)),
            **{key: d[key] for key in _VEHICLE_DEFAULTS if key in d},
        )

    def with_(self, **changes: Any) -> "Unit":
        return replace(self, **changes)


# The vehicle fields of rules 28 to 41 with their default. `to_dict` writes a field only
# when it is not at its default, so an infantry game keeps the state document it had.
_VEHICLE_DEFAULTS: dict[str, Any] = {
    "facing": -1,
    "mp_used": 0,
    "wreck": False,
    "immobilized": False,
    "crew_exposed": False,
    "mg_malfunction": False,
    "disabled": False,
    "mg_disabled": False,
    "passenger_of": None,
    "pivoted": False,
    "gun_shots": 0,
    "mg_fired": False,
    "boarded": False,
    "overran": False,
    "dischargers_used": False,
    "canister_spent": False,
    "from_wreck": None,
}
