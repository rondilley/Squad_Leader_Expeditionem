"""The board data model (DR-03) and the terrain types.

Slice 1 holds Board, Hex, Building, Polygon, and TerrainType. The game State,
Unit, and Stack come in slice 2. Nothing here reads a file: the loaders in
`sldata` give the core parsed dictionaries.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from slcore import geometry
from slcore.geometry import HexRef, Point

LOS_CLEAR = "clear"
LOS_BLOCK = "block"
LOS_HINDER = "hinder"

HEXSIDE_FEATURES = ("wall", "hedge", "cliff")


@dataclass(frozen=True)
class TerrainType:
    """One row of the terrain table.

    tem: the terrain effects modifier of rule 11.1.
    mf_halves: the infantry movement cost of rule 5.5 in half movement factors.
    los: clear, block, or hinder (rules 7.2, 44).
    building: the terrain is a building for rules 7.4 to 7.7.
    """

    name: str
    tem: int
    mf_halves: int
    los: str
    building: bool = False


@dataclass(frozen=True)
class Polygon:
    """A convex terrain shape on the lattice. kind is a terrain type name."""

    kind: str
    points: tuple[Point, ...]

    @staticmethod
    def make(kind: str, points: Iterable[Point]) -> "Polygon":
        return Polygon(kind, geometry.normalize_polygon(points))


@dataclass(frozen=True)
class Building:
    """A building that covers one or more hexes. size counts the hexes (rule 7.4).

    landmark: "mill" or "windmill" for a building with a picture and a name of its own, or
    None. It changes no rule (PR-57).
    """

    id: str
    kind: str
    size: int
    landmark: str | None = None

    @property
    def multi_story(self) -> bool:
        return self.size >= 3


@dataclass(frozen=True)
class Hex:
    col: int
    row: int
    terrain: str = "open"
    elevation: int = 0
    road: bool = False
    building: Building | None = None
    hexsides: tuple[str | None, ...] = (None, None, None, None, None, None)
    sewer: bool = False
    stairs: bool = False
    polygons: tuple[Polygon, ...] = ()
    # PR-50: the directions in which the road of this hex crosses a hexside. An empty
    # tuple on every hex of a board means the board document names no road hexside.
    road_sides: tuple[int, ...] = ()

    @property
    def ref(self) -> HexRef:
        return (self.col, self.row)

    @property
    def id(self) -> str:
        return geometry.hex_id(self.col, self.row)

    @property
    def center(self) -> Point:
        return geometry.center(self.col, self.row)


class Board:
    """A board of `cols` columns and `rows` rows with half hexes on the edges.

    Valid hexes: even-index columns have rows 1 to rows. Odd-index columns
    have rows 0 to rows, where 0 and rows are half hexes.
    """

    def __init__(
        self,
        cols: int,
        rows: int,
        hexes: Iterable[Hex],
        terrain: Mapping[str, TerrainType],
        name: str = "",
    ) -> None:
        if cols < 1 or rows < 1:
            raise ValueError("cols and rows must be positive")
        self.cols = cols
        self.rows = rows
        self.name = name
        self.terrain: dict[str, TerrainType] = dict(terrain)
        self._hexes: dict[HexRef, Hex] = {}
        for h in hexes:
            if not self.valid(h.col, h.row):
                raise ValueError(f"hex {h.id} is outside a {cols} by {rows} board")
            if h.ref in self._hexes:
                raise ValueError(f"duplicate hex {h.id}")
            if h.terrain not in self.terrain:
                raise ValueError(f"hex {h.id} has unknown terrain {h.terrain!r}")
            for poly in h.polygons:
                if poly.kind not in self.terrain:
                    raise ValueError(f"hex {h.id} has a polygon of unknown kind {poly.kind!r}")
            self._hexes[h.ref] = h
        for ref in self.all_refs():
            if ref not in self._hexes:
                raise ValueError(f"board has no hex {geometry.hex_id(*ref)}")
        self.order: tuple[HexRef, ...] = tuple(sorted(self._hexes))
        self.index: dict[HexRef, int] = {ref: i for i, ref in enumerate(self.order)}
        self._check_hexsides()
        self.named_road_sides = any(h.road_sides for h in self._hexes.values())
        self._check_road_sides()

    def all_refs(self) -> Iterable[HexRef]:
        for col in range(self.cols):
            first = 0 if col & 1 else 1
            for row in range(first, self.rows + 1):
                yield (col, row)

    def valid(self, col: int, row: int) -> bool:
        if col < 0 or col >= self.cols:
            return False
        first = 0 if col & 1 else 1
        return first <= row <= self.rows

    def __contains__(self, ref: object) -> bool:
        return ref in self._hexes

    def __len__(self) -> int:
        return len(self._hexes)

    def __iter__(self) -> Iterable[Hex]:
        return (self._hexes[ref] for ref in self.order)

    def get(self, col: int, row: int) -> Hex:
        return self._hexes[(col, row)]

    def hex(self, ref: HexRef) -> Hex:
        return self._hexes[ref]

    def by_id(self, text: str) -> Hex:
        return self._hexes[geometry.parse_hex_id(text)]

    def neighbors(self, ref: HexRef) -> tuple[HexRef, ...]:
        return tuple(n for n in geometry.neighbors(*ref) if n in self._hexes)

    def adjacent(self, a: HexRef, b: HexRef) -> bool:
        return geometry.direction_to(a, b) is not None

    def hexside(self, ref: HexRef, direction: int) -> str | None:
        return self._hexes[ref].hexsides[direction]

    def los_class(self, kind: str) -> str:
        return self.terrain[kind].los

    def is_building_kind(self, kind: str) -> bool:
        return self.terrain[kind].building

    def _check_hexsides(self) -> None:
        for ref, h in self._hexes.items():
            for d, feature in enumerate(h.hexsides):
                if feature is None:
                    continue
                if feature not in HEXSIDE_FEATURES:
                    raise ValueError(f"hex {h.id} has unknown hexside feature {feature!r}")
                other = geometry.neighbor(ref[0], ref[1], d)
                if other in self._hexes:
                    back = self._hexes[other].hexsides[(d + 3) % 6]
                    if back != feature:
                        raise ValueError(
                            f"hexside {h.id}-{geometry.hex_id(*other)} is {feature!r} on one side and {back!r} on the other"
                        )

    def _check_road_sides(self) -> None:
        """PR-50: a road hexside is on a road hex and is named from both of its hexes."""
        for ref, h in self._hexes.items():
            for d in h.road_sides:
                if not 0 <= d < 6:
                    raise ValueError(f"hex {h.id} names road direction {d}")
                if not h.road:
                    raise ValueError(f"hex {h.id} names a road hexside and is not a road hex")
                other = geometry.neighbor(ref[0], ref[1], d)
                if other in self._hexes and (d + 3) % 6 not in self._hexes[other].road_sides:
                    raise ValueError(f"the road hexside {h.id}-{geometry.hex_id(*other)} is named from one side only")

    def road_crosses(self, ref: HexRef, direction: int) -> bool:
        """PR-50: the road of this hex crosses the hexside in this direction.

        A board document that names no road hexside reads two adjacent road hexes as joined,
        which is the reading from before PR-50.
        """
        here = self._hexes[ref]
        if not here.road:
            return False
        if self.named_road_sides:
            return direction in here.road_sides
        other = geometry.neighbor(ref[0], ref[1], direction)
        return other in self._hexes and self._hexes[other].road

    def subset_columns(self, lo: int, hi: int) -> "Board":
        """A board of the columns lo to hi. A scenario that uses part of a board uses this."""
        kept = [h for h in self if lo <= h.col <= hi]
        sizes: dict[str, int] = {}
        for h in kept:
            if h.building is not None:
                sizes[h.building.id] = sizes.get(h.building.id, 0) + 1
        hexes = []
        for h in kept:
            building = h.building
            if building is not None and sizes[building.id] != building.size:
                building = Building(building.id, building.kind, sizes[building.id], building.landmark)
            hexes.append(
                Hex(
                    col=h.col - lo,
                    row=h.row,
                    terrain=h.terrain,
                    elevation=h.elevation,
                    road=h.road,
                    building=building,
                    hexsides=h.hexsides,
                    sewer=h.sewer,
                    stairs=h.stairs,
                    polygons=default_polygons(h.col - lo, h.row, h.terrain, self.terrain),
                    road_sides=h.road_sides,
                )
            )
        return Board(hi - lo + 1, self.rows, hexes, self.terrain, name=f"{self.name}-{lo}-{hi}")

    def to_dict(self) -> dict[str, Any]:
        hexes = []
        for h in self:
            item: dict[str, Any] = {"id": h.id, "terrain": h.terrain}
            if h.elevation:
                item["elevation"] = h.elevation
            if h.road:
                item["road"] = True
            if h.road_sides:
                item["road_sides"] = list(h.road_sides)
            if h.building is not None:
                item["building"] = {"id": h.building.id, "kind": h.building.kind, "size": h.building.size}
                if h.building.landmark is not None:
                    item["building"]["landmark"] = h.building.landmark
            sides = {str(d): f for d, f in enumerate(h.hexsides) if f is not None}
            if sides:
                item["hexsides"] = sides
            if h.sewer:
                item["sewer"] = True
            if h.stairs:
                item["stairs"] = True
            item["polygons"] = [{"kind": p.kind, "points": [list(pt) for pt in p.points]} for p in h.polygons]
            hexes.append(item)
        return {"name": self.name, "cols": self.cols, "rows": self.rows, "hexes": hexes}

    @staticmethod
    def from_dict(data: Mapping[str, Any], terrain: Mapping[str, TerrainType]) -> "Board":
        hexes = []
        for item in data["hexes"]:
            col, row = geometry.parse_hex_id(item["id"])
            building = None
            if item.get("building") is not None:
                b = item["building"]
                landmark = b.get("landmark")
                building = Building(str(b["id"]), str(b["kind"]), int(b["size"]), None if landmark is None else str(landmark))
            sides: list[str | None] = [None] * 6
            for key, value in item.get("hexsides", {}).items():
                sides[int(key)] = str(value)
            kind = str(item["terrain"])
            if "polygons" in item:
                polys = tuple(Polygon.make(str(p["kind"]), [tuple(pt) for pt in p["points"]]) for p in item["polygons"])
            else:
                polys = default_polygons(col, row, kind, terrain)
            hexes.append(
                Hex(
                    col=col,
                    row=row,
                    terrain=kind,
                    elevation=int(item.get("elevation", 0)),
                    road=bool(item.get("road", False)),
                    building=building,
                    hexsides=tuple(sides),
                    sewer=bool(item.get("sewer", False)),
                    stairs=bool(item.get("stairs", False)),
                    polygons=polys,
                    road_sides=tuple(sorted(int(d) for d in item.get("road_sides", []))),
                )
            )
        return Board(int(data["cols"]), int(data["rows"]), hexes, terrain, name=str(data.get("name", "")))


def default_polygons(col: int, row: int, kind: str, terrain: Mapping[str, TerrainType]) -> tuple[Polygon, ...]:
    """A whole-hex polygon for terrain that blocks or hinders LOS, else none."""
    if terrain[kind].los == LOS_CLEAR:
        return ()
    return (Polygon(kind, geometry.hex_polygon(col, row)),)


def make_hex(col: int, row: int, terrain: Mapping[str, TerrainType], kind: str = "open", **fields: Any) -> Hex:
    """Build a hex with the default whole-hex polygon when none is given."""
    if "polygons" not in fields:
        fields["polygons"] = default_polygons(col, row, kind, terrain)
    if "hexsides" in fields and isinstance(fields["hexsides"], dict):
        sides: list[str | None] = [None] * 6
        for d, f in fields["hexsides"].items():
            sides[int(d)] = f
        fields["hexsides"] = tuple(sides)
    return Hex(col=col, row=row, terrain=kind, **fields)


def terrain_table_from_dict(data: Mapping[str, Any]) -> dict[str, TerrainType]:
    """Parse the terrain table document (sldata/tables/terrain.json) into TerrainType rows."""
    table: dict[str, TerrainType] = {}
    for name, row in data["terrain"].items():
        table[name] = TerrainType(
            name=name,
            tem=int(row["tem"]),
            mf_halves=int(row["mf_halves"]),
            los=str(row["los"]),
            building=bool(row.get("building", False)),
        )
    for t in table.values():
        if t.los not in (LOS_CLEAR, LOS_BLOCK, LOS_HINDER):
            raise ValueError(f"terrain {t.name} has unknown los class {t.los!r}")
    return table


@dataclass(frozen=True)
class HexsideRule:
    """One row of the hexside table: wall, hedge, cliff."""

    name: str
    tem: int
    mf_extra_halves: int
    los: str
    passable: bool


def hexside_table_from_dict(data: Mapping[str, Any]) -> dict[str, HexsideRule]:
    table: dict[str, HexsideRule] = {}
    for name, row in data["hexsides"].items():
        table[name] = HexsideRule(
            name=name,
            tem=int(row["tem"]),
            mf_extra_halves=int(row["mf_extra_halves"]),
            los=str(row["los"]),
            passable=bool(row["passable"]),
        )
    return table
