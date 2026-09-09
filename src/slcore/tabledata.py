"""The combat tables as parsed data (rules 10 and 20). No file access here."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

RESULT_NONE = "-"
RESULT_MC = "M"
RESULT_KIA = "KIA"


@dataclass(frozen=True)
class IftTable:
    columns: tuple[int, ...]
    rows: dict[int, tuple[str, ...]]
    row_below_2: str

    def column_index(self, firepower: int) -> int | None:
        """Rule 10.3: the rightmost column that does not exceed the firepower."""
        best = None
        for i, c in enumerate(self.columns):
            if c <= firepower:
                best = i
        return best

    def lookup(self, firepower: int, adjusted_roll: int) -> str:
        i = self.column_index(firepower)
        if i is None:
            return RESULT_NONE
        if adjusted_roll < 2:
            return self.row_below_2
        if adjusted_roll > max(self.rows):
            return RESULT_NONE
        return self.rows[adjusted_roll][i]


def ift_from_dict(data: Mapping[str, Any]) -> IftTable:
    columns = tuple(int(c) for c in data["columns"])
    rows: dict[int, tuple[str, ...]] = {}
    for key, values in data["rows"].items():
        if len(values) != len(columns):
            raise ValueError(f"IFT row {key} has {len(values)} values for {len(columns)} columns")
        rows[int(key)] = tuple(str(v) for v in values)
    return IftTable(columns, rows, str(data.get("row_below_2", RESULT_KIA)))


@dataclass(frozen=True)
class OddsRow:
    label: str
    attack: int
    defense: int
    kill: int


@dataclass(frozen=True)
class CcTable:
    odds: tuple[OddsRow, ...]

    def odds_row(self, attack: int, defense: int) -> OddsRow:
        """Rule 20.3: the highest odds row that does not exceed attack to defense, rounded down for the defender."""
        if defense <= 0:
            return self.odds[-1]
        chosen = self.odds[0]
        for row in self.odds:
            if attack * row.defense >= row.attack * defense:
                chosen = row
        return chosen


def cc_from_dict(data: Mapping[str, Any]) -> CcTable:
    rows = tuple(OddsRow(str(r["label"]), int(r["attack"]), int(r["defense"]), int(r["kill"])) for r in data["odds"])
    return CcTable(rows)


RUSSIAN = "russian"
NA = None


PREP_OR_DEFENSIVE = "prep_or_defensive_fire"
ADVANCING_AFTER_MOVEMENT = "advancing_fire_after_movement"


@dataclass(frozen=True)
class GunColumn:
    """Rule 34.2 and project ruling PR-25: what one main gun calibre reads."""

    calibre: int
    kill_ap: str | None
    kill_he: str | None
    firepower: int


@dataclass(frozen=True)
class HandheldToHit:
    """The to-hit chart of a panzerfaust (rule 37.31) or a bazooka (rule 37.41)."""

    rule: str
    ranges: tuple[int, ...]
    prep_or_defensive: tuple[int, ...]
    advancing_after_movement: tuple[int, ...]

    @property
    def max_range(self) -> int:
        return self.ranges[-1]

    def number(self, distance: int, after_movement: bool) -> int | None:
        """The roll or less that hits. None means the range is beyond the weapon."""
        if distance not in self.ranges:
            return None
        row = self.advancing_after_movement if after_movement else self.prep_or_defensive
        return row[self.ranges.index(distance)]


@dataclass(frozen=True)
class ArmorTables:
    """The tables of armor combat: rules 33.3, 33.31, 33.4, 33.41, 34.2, 36.12, 37.31, 37.41.

    A to-hit number and a kill number are both roll-or-less numbers. The roll of two dice,
    with its modifiers, must be equal to or less than the number.
    """

    ranges: tuple[tuple[int, int | None], ...]
    to_hit_default: dict[str, tuple[int | None, ...]]
    to_hit_russian: dict[str, tuple[int | None, ...]]
    hit_modifiers: dict[str, int]
    kill_number_modifiers: dict[str, int]
    weapons: tuple[str, ...]
    kill_rows: dict[str, tuple[int | None, ...]]
    pre_afv_attack: dict[str, int]
    panzerfaust: HandheldToHit
    bazooka: HandheldToHit
    guns: tuple[GunColumn, ...]

    def gun_column(self, calibre: int) -> GunColumn:
        """Rule 34.2 with PR-25: the largest entry that does not exceed the calibre."""
        best: GunColumn | None = None
        for row in self.guns:
            if row.calibre <= calibre and (best is None or row.calibre > best.calibre):
                best = row
        if best is None:
            raise KeyError(f"no gun column covers a calibre of {calibre}")
        return best

    def gun_firepower(self, calibre: int) -> int:
        """Rule 34.2: the firepower column of the Infantry Fire Table a hit is worth."""
        return self.gun_column(calibre).firepower

    def gun_kill_column(self, calibre: int, ammunition: str) -> str:
        """Rule 33.4 with PR-25: the column of the kill table this gun and shell read."""
        row = self.gun_column(calibre)
        column = row.kill_ap if ammunition == "ap" else row.kill_he
        if column is None:
            raise KeyError(f"a {calibre} millimetre gun has no {ammunition} column on the kill table")
        return column

    def pre_afv_number(self, location: str) -> int:
        """Rule 36.12: the roll or less that immobilizes the vehicle from that location."""
        if location not in self.pre_afv_attack:
            raise KeyError(f"rule 36.12 has no row for {location!r}")
        return self.pre_afv_attack[location]

    def range_index(self, distance: int) -> int | None:
        """Rule 33.3: which column of the to-hit table a distance in hexes falls in."""
        for i, (low, high) in enumerate(self.ranges):
            if distance >= low and (high is None or distance <= high):
                return i
        return None

    def to_hit(self, target: str, distance: int, nationality: str = "") -> int | None:
        """Rule 33.3: the number the firer must roll or less to hit.

        A Russian firing unit reads the second number of the cell, and each other firing
        unit reads the first. None means that the table gives no number, and the shot
        cannot hit.
        """
        table = self.to_hit_russian if nationality == RUSSIAN else self.to_hit_default
        if target not in table:
            raise KeyError(f"the to-hit table has no row for the target {target!r}")
        index = self.range_index(distance)
        if index is None:
            return None
        return table[target][index]

    def hit_modifier(self, cases: "list[str] | tuple[str, ...]") -> int:
        """Rule 33.31: the modifiers of the cases that apply, added together."""
        total = 0
        for case in cases:
            if case not in self.hit_modifiers:
                raise KeyError(f"rule 33.31 has no case {case!r}")
            total += self.hit_modifiers[case]
        return total

    def kill_number(self, target: str, weapon: str, vehicle: str = "") -> int | None:
        """Rules 33.4 and 33.41: the number the firer must roll or less to kill.

        None means NA: the weapon has no kill number against that target, and rule 51.4
        sends the attack to the Infantry Fire Table instead.
        """
        if target not in self.kill_rows:
            raise KeyError(f"the kill table has no row for the target {target!r}")
        if weapon not in self.weapons:
            raise KeyError(f"the kill table has no column for the weapon {weapon!r}")
        base = self.kill_rows[target][self.weapons.index(weapon)]
        if base is None:
            return None
        return base + self.kill_number_modifiers.get(vehicle, 0)


def armor_from_dict(data: Mapping[str, Any]) -> ArmorTables:
    hit = data["to_hit"]
    ranges = tuple(
        (int(r["low"]), None if r.get("high") is None else int(r["high"])) for r in hit["ranges"]
    )

    def numbers(values: Any) -> tuple[int | None, ...]:
        return tuple(None if v is None else int(v) for v in values)

    def handheld(key: str) -> HandheldToHit:
        row = data[key]
        return HandheldToHit(
            rule=str(row["rule"]),
            ranges=tuple(int(r) for r in row["ranges"]),
            prep_or_defensive=tuple(int(v) for v in row[PREP_OR_DEFENSIVE]),
            advancing_after_movement=tuple(int(v) for v in row[ADVANCING_AFTER_MOVEMENT]),
        )

    kill = data["kill_table"]
    return ArmorTables(
        ranges=ranges,
        to_hit_default={str(r["target"]): numbers(r["default"]) for r in hit["rows"]},
        to_hit_russian={str(r["target"]): numbers(r["russian"]) for r in hit["rows"]},
        hit_modifiers={str(c["case"]): int(c["modifier"]) for c in data["hit_modifiers"]["cases"]},
        kill_number_modifiers={
            str(v["vehicle"]): int(v["drm"]) for v in data["kill_number_modifiers"]["vehicles"]
        },
        weapons=tuple(str(w["weapon"]) for w in kill["weapons"]),
        kill_rows={str(r["target"]): numbers(r["kill"]) for r in kill["rows"]},
        pre_afv_attack={str(r["location"]): int(r["roll"]) for r in data["pre_afv_attack"]["rows"]},
        panzerfaust=handheld("panzerfaust_to_hit"),
        bazooka=handheld("bazooka_to_hit"),
        guns=tuple(
            GunColumn(
                calibre=int(g["calibre"]),
                kill_ap=None if g.get("kill_ap") is None else str(g["kill_ap"]),
                kill_he=None if g.get("kill_he") is None else str(g["kill_he"]),
                firepower=int(g["firepower"]),
            )
            for g in data["gun_columns"]["guns"]
        ),
    )


NOT_ALLOWED = None


@dataclass(frozen=True)
class VehicleMovement:
    """The Vehicle Movement Cost Chart of rule 30. Every cost is in half movement points."""

    terrain_afv: dict[str, int | None]
    terrain_truck: dict[str, int | None]
    hexside_afv: dict[str, int | None]
    hexside_truck: dict[str, int | None]
    extra_afv: dict[str, int | None]
    extra_truck: dict[str, int | None]
    breakdown_terrain: frozenset[str]
    no_halftrack_terrain: frozenset[str]

    def terrain_cost(self, kind: str, truck: bool) -> int | None:
        table = self.terrain_truck if truck else self.terrain_afv
        if kind not in table:
            raise KeyError(f"the vehicle movement chart has no row for the terrain {kind!r}")
        return table[kind]

    def hexside_cost(self, feature: str, truck: bool) -> int | None:
        table = self.hexside_truck if truck else self.hexside_afv
        if feature not in table:
            raise KeyError(f"the vehicle movement chart has no row for the hexside {feature!r}")
        return table[feature]

    def extra_cost(self, name: str, truck: bool) -> int | None:
        table = self.extra_truck if truck else self.extra_afv
        if name not in table:
            raise KeyError(f"the vehicle movement chart has no row named {name!r}")
        return table[name]

    def needs_breakdown_roll(self, kind: str) -> bool:
        """Rule 39.1: a woods hex and a wooden building hex need the breakdown die."""
        return kind in self.breakdown_terrain


def vehicle_movement_from_dict(data: Mapping[str, Any]) -> VehicleMovement:
    def column(rows: Mapping[str, Any], name: str) -> dict[str, int | None]:
        out: dict[str, int | None] = {}
        for key, row in rows.items():
            value = row.get(name)
            out[str(key)] = None if value is None else int(value)
        return out

    terrain = data["terrain"]
    return VehicleMovement(
        terrain_afv=column(terrain, "afv"),
        terrain_truck=column(terrain, "truck"),
        hexside_afv=column(data["hexsides"], "afv"),
        hexside_truck=column(data["hexsides"], "truck"),
        extra_afv=column(data["extra"], "afv"),
        extra_truck=column(data["extra"], "truck"),
        breakdown_terrain=frozenset(k for k, r in terrain.items() if r.get("breakdown")),
        no_halftrack_terrain=frozenset(k for k, r in terrain.items() if r.get("no_halftrack")),
    )


@dataclass(frozen=True)
class Tables:
    ift: IftTable
    cc: CcTable
    armor: ArmorTables | None = None
    vehicle: VehicleMovement | None = None

    @property
    def armor_tables(self) -> ArmorTables:
        """The armor tables, or an error that says the engine was built without them."""
        if self.armor is None:
            raise ValueError("this engine has no armor tables, so the rules 28 to 41 cannot run")
        return self.armor

    @property
    def vehicle_movement(self) -> VehicleMovement:
        if self.vehicle is None:
            raise ValueError("this engine has no vehicle movement chart, so rule 30 cannot run")
        return self.vehicle
