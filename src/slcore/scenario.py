"""Scenario data (FR-18, FR-21) parsed from a dictionary. No file access here."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Sequence

from slcore import geometry
from slcore.geometry import HexRef
from slcore.state import Board


@dataclass(frozen=True)
class UnitEntry:
    type_key: str
    count: int = 1
    name: str = ""


@dataclass(frozen=True)
class SetupArea:
    """Where a group sets up: a hex list for reference mode, or a zone for generated mode (FR-21)."""

    building: str | None = None
    hexes: tuple[HexRef, ...] = ()
    zone: str | None = None
    params: tuple[tuple[str, Any], ...] = ()

    def resolve(self, board: Board) -> tuple[HexRef, ...]:
        if self.hexes:
            return tuple(h for h in self.hexes if h in board)
        if self.building is not None:
            out = tuple(h.ref for h in board if h.building is not None and h.building.id == self.building)
            if not out:
                raise ValueError(f"the board has no building {self.building!r} for a set up area")
            return out
        if self.zone is not None:
            return resolve_zone(board, self.zone, dict(self.params))
        raise ValueError("a set up area needs hexes, a building, or a zone")

    def building_id(self, board: Board) -> str | None:
        hexes = self.resolve(board)
        for h in hexes:
            b = board.hex(h).building
            if b is not None:
                return b.id
        return None


def in_band(hexes: Sequence[HexRef], params: Mapping[str, Any]) -> bool:
    """True when each hex of a building is inside the column and row band of `params`.

    The keys are `min_col`, `max_col`, `min_row`, and `max_row`, and each one is optional.

    The column test reads each hex: a building that crosses a column line is outside the
    band, because a scenario that plays on part of a board cuts the building at that line
    and its hex count changes. The row test reads the north hex of the building only, so
    that two bands that divide the rows between them give each building to one side. A
    building that crosses the row line is not cut by it, and on the printed board of
    scenario 1 the two sides hold buildings that are one hexside apart.
    """
    low_col = params.get("min_col")
    high_col = params.get("max_col")
    low_row = params.get("min_row")
    high_row = params.get("max_row")
    if low_col is not None and any(ref[0] < int(low_col) for ref in hexes):
        return False
    if high_col is not None and any(ref[0] > int(high_col) for ref in hexes):
        return False
    north = min(ref[1] for ref in hexes)
    if low_row is not None and north < int(low_row):
        return False
    if high_row is not None and north > int(high_row):
        return False
    return True


def near_band(
    hexes: Sequence[HexRef],
    buildings: Iterable[Sequence[HexRef]],
    near: Mapping[str, Any],
) -> bool:
    """True when a building is within `max_distance` hexes of a stone building of another band.

    `near` holds the band keys of `in_band` and `max_distance`. The distance is the least
    hex distance between a hex of this building and a hex of a building of the band. This
    is how a card puts an attacker on top of a defender: the guards of scenario 1 set up
    in the building next to the one the Germans hold, and a band of columns alone cannot
    say that.
    """
    limit = int(near.get("max_distance", 2))
    for other in buildings:
        if other is hexes or not in_band(other, near):
            continue
        if min(geometry.distance(a, b) for a in hexes for b in other) <= limit:
            return True
    return False


def band_text(params: Mapping[str, Any]) -> str:
    """The band of `params` in words, for an error message."""
    parts = []
    low_col = params.get("min_col")
    high_col = params.get("max_col")
    if low_col is not None or high_col is not None:
        parts.append(_band_text(low_col, high_col))
    low_row = params.get("min_row")
    high_row = params.get("max_row")
    if low_row is not None and high_row is not None:
        parts.append(f"in rows {int(low_row)} to {int(high_row)}")
    elif low_row is not None:
        parts.append(f"in the rows from {int(low_row)}")
    elif high_row is not None:
        parts.append(f"in the rows up to {int(high_row)}")
    near = params.get("near")
    if near and not isinstance(near, Mapping):
        near = dict(near)
    if near:
        parts.append(f"within {int(near.get('max_distance', 2))} hexes of a stone building {band_text(near)}")
    return " ".join(parts) if parts else "on the board"


def stone_buildings(board: Board) -> list[tuple[str, tuple[HexRef, ...]]]:
    """The stone buildings of the board, from west to east, then north to south."""
    groups: dict[str, list[HexRef]] = {}
    for h in board:
        if h.building is not None and h.terrain == "stone_building":
            groups.setdefault(h.building.id, []).append(h.ref)
    out = [(k, tuple(sorted(v))) for k, v in groups.items()]
    out.sort(key=lambda item: item[1][0])
    return out


ZONES = ("stone_building", "columns", "edge")
EDGES = ("north", "south", "east", "west")


def zone_filter(board: Board, params: Mapping[str, Any]):
    """The terrain test that a `columns` or an `edge` zone applies to each hex.

    - `terrain`: one terrain kind, or a list of them. A hex of another kind is out.
    - `not_terrain`: one terrain kind, or a list of them, that the zone does not take. It
      keeps a group of the open ground out of the building that another group holds.
    - `road`: true for road hexes only, false for hexes with no road.
    - `level`: one elevation level, for a zone on a hill of rule 43.

    A zone with none of these takes each hex of its band, which is the set up area that
    RV-2 section 6 calls a whole board or a part of one.
    """
    def kind_set(value):
        if value is None:
            return None
        return {str(value)} if isinstance(value, str) else {str(k) for k in value}

    kinds = kind_set(params.get("terrain"))
    without = kind_set(params.get("not_terrain"))
    road = params.get("road")
    level = params.get("level")

    def keep(ref: HexRef) -> bool:
        h = board.hex(ref)
        if kinds is not None and h.terrain not in kinds:
            return False
        if without is not None and h.terrain in without:
            return False
        if road is not None and bool(h.road) != bool(road):
            return False
        if level is not None and h.elevation != int(level):
            return False
        return True

    return keep


def resolve_columns(board: Board, params: Mapping[str, Any]) -> tuple[HexRef, ...]:
    """A band of columns, which is how a card names a whole board or a part of one."""
    low = int(params.get("min_col", 0))
    high = int(params.get("max_col", board.cols - 1))
    keep = zone_filter(board, params)
    return tuple(sorted(ref for ref in board.order if low <= ref[0] <= high and keep(ref)))


def resolve_edge(board: Board, params: Mapping[str, Any]) -> tuple[HexRef, ...]:
    """The hexes within `depth` of one edge, which is how a card names an entry area.

    The east and the west edges are columns. The north and the south edges are rows, and
    an odd-index column has a half hex at each of them, so the count of rows from an edge
    is the count of row indexes and not a distance in hexes.
    """
    side = str(params.get("side", "west"))
    if side not in EDGES:
        raise ValueError(f"an edge is one of {EDGES}, and not {side!r}")
    depth = max(1, int(params.get("depth", 1)))
    keep = zone_filter(board, params)
    out = []
    for ref in board.order:
        col, row = ref
        first = 0 if col & 1 else 1
        if side == "west" and col >= depth:
            continue
        if side == "east" and col < board.cols - depth:
            continue
        if side == "north" and row >= first + depth:
            continue
        if side == "south" and row <= board.rows - depth:
            continue
        if keep(ref):
            out.append(ref)
    return tuple(sorted(out))


def resolve_zone(board: Board, zone: str, params: Mapping[str, Any]) -> tuple[HexRef, ...]:
    """A zone is a predicate on hexes (FR-21).

    Three zones, which are the set up areas that RV-2 section 6 reads off the cards:

    - `stone_building`: one building of a column band, by rank.
    - `columns`: each hex of a column band, with an optional terrain test.
    - `edge`: each hex within a depth of one named edge, with the same test.

    The parameters of `stone_building`:

    - `min_col` and `max_col`: the band of columns the side sets up in. The band, and not
      an index from an end of the board, keeps the two sides apart on every board.
    - `min_row` and `max_row`: the band of rows, for a card whose front runs along the
      rows. Scenario 1 is one: the Russians hold rows 2 to 4 and the Germans rows 5 to 9.
    - `near`: a band of the same keys and a `max_distance`. The building must be within
      that distance of a stone building of the other band. This puts an attacker in the
      building next to a defender, which the card of scenario 1 does.
    - `rank`: which building of the band the group takes. The band is sorted by hex count
      first, from the largest, and then from the west. So rank 0 is the largest building,
      and the scenario gives it to its largest group.
    - `min_hexes`: the room the group needs. A board that does not have it is an error
      with the number of hexes it found, and not a set up that breaks rule 6.1.
    - `max_hexes`: an upper bound, for a group that must not hold a whole block.

    `columns` and `edge` take `terrain`, `road`, and `level`, which `zone_filter` reads.
    """
    if zone == "columns":
        return resolve_columns(board, params)
    if zone == "edge":
        return resolve_edge(board, params)
    if zone != "stone_building":
        raise NotImplementedError(f"zone {zone!r} is not one of {ZONES}")
    buildings = stone_buildings(board)
    shapes = [hexes for _, hexes in buildings]
    near = params.get("near")
    if near and not isinstance(near, Mapping):
        near = dict(near)
    band = []
    for name, hexes in buildings:
        if not in_band(hexes, params):
            continue
        if near and not near_band(hexes, shapes, near):
            continue
        band.append((name, hexes))
    if int(params.get("max_hexes", 99)) < 99:
        band = [b for b in band if len(b[1]) <= int(params["max_hexes"])]
    band.sort(key=lambda item: (-len(item[1]), item[1][0]))
    rank = int(params.get("rank", 0))
    where = band_text(params)
    if rank >= len(band):
        raise ValueError(
            f"the board has {len(band)} stone buildings {where}, and the set up area asks for rank {rank}"
        )
    name, hexes = band[rank]
    need = int(params.get("min_hexes", 1))
    if len(hexes) < need:
        raise ValueError(
            f"building {name} {where} has {len(hexes)} hexes, and the set up area needs {need}"
        )
    return hexes


def _band_text(low_col: Any, high_col: Any) -> str:
    if low_col is None and high_col is None:
        return "on the board"
    if low_col is None:
        return f"in the columns up to {geometry.column_label(int(high_col))}"
    if high_col is None:
        return f"in the columns from {geometry.column_label(int(low_col))}"
    return f"in columns {geometry.column_label(int(low_col))} to {geometry.column_label(int(high_col))}"


@dataclass(frozen=True)
class Group:
    """One force that a scenario puts on the board in one area (rule 21.2).

    `nationality` is for a side that fields more than one army. A side names the army of
    its groups, and a group with a nationality of its own takes the counters of that army
    instead. The two sides of rule 4 do not change: a group belongs to the side that holds
    it, whatever counters it uses.
    """

    id: str
    units: tuple[UnitEntry, ...]
    area: SetupArea
    objective: bool = False
    setup_pass: int | None = None
    nationality: str | None = None


@dataclass(frozen=True)
class SideSpec:
    side: str
    nationality: str
    groups: tuple[Group, ...]

    def army_of(self, group: Group) -> str:
        """The army whose counters a group uses."""
        return group.nationality or self.nationality

    def armies(self) -> tuple[str, ...]:
        """Each army on this side, in the order the groups name them."""
        out: list[str] = []
        for g in self.groups:
            army = self.army_of(g)
            if army not in out:
                out.append(army)
        return tuple(out)


@dataclass(frozen=True)
class VictoryCondition:
    kind: str
    params: tuple[tuple[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class Scenario:
    id: str
    title: str
    board: str
    turns: int
    first_mover: str
    setup_order: tuple[str, ...]
    sides: tuple[SideSpec, ...]
    rules_used: tuple[str, ...]
    switches: tuple[tuple[str, str], ...] = ()
    victory: tuple[VictoryCondition, ...] = ()
    objectives: tuple[HexRef, ...] = ()
    board_generator: tuple[tuple[str, Any], ...] = ()
    board_composition: tuple[tuple[str, Any], ...] = ()
    board_columns: tuple[int, int] | None = None
    board_retries: int = 8
    smoke_counters: tuple[tuple[str, int], ...] = ()
    concealment_counters: tuple[tuple[str, int], ...] = ()
    first_mover_roll: bool = False
    hidden_side: str = ""
    fanatic_side: str = ""
    fanatic_area: SetupArea | None = None
    notes: str = ""

    def side_index(self, side: str) -> int:
        for i, s in enumerate(self.players()):
            if s == side:
                return i
        raise KeyError(side)

    def players(self) -> tuple[str, str]:
        """Player 0 is the first mover (the attacker of turn 1)."""
        names = [s.side for s in self.sides]
        if self.first_mover not in names or len(names) != 2:
            raise ValueError("a scenario needs two sides and a first mover among them")
        other = [n for n in names if n != self.first_mover][0]
        return (self.first_mover, other)

    def group_pass(self, group_id: str) -> int:
        """Which set up pass a group belongs to (rule 21.2).

        A card can call a side to the board more than one time. Scenario 2 sets the
        Russian garrison up first, then the Germans, then the Russian relief force. A
        group with no pass of its own belongs to the first pass of its side.
        """
        for side in self.sides:
            for g in side.groups:
                if g.id != group_id:
                    continue
                if g.setup_pass is not None:
                    return g.setup_pass
                return self.setup_order.index(side.side)
        raise KeyError(group_id)

    def group(self, group_id: str) -> Group:
        for side in self.sides:
            for g in side.groups:
                if g.id == group_id:
                    return g
        raise KeyError(group_id)

    def side_spec(self, side: str) -> SideSpec:
        for s in self.sides:
            if s.side == side:
                return s
        raise KeyError(side)


def _area_from_dict(d: Mapping[str, Any]) -> SetupArea:
    known = {"building", "hexes", "zone"}
    return SetupArea(
        building=None if d.get("building") is None else str(d["building"]),
        hexes=tuple(geometry.parse_hex_id(str(h)) for h in d.get("hexes", [])),
        zone=None if d.get("zone") is None else str(d["zone"]),
        params=tuple(sorted((k, _frozen(v)) for k, v in d.items() if k not in known)),
    )


def _frozen(value: Any) -> Any:
    """A parameter value that a frozen record can hold: a mapping becomes sorted pairs."""
    if isinstance(value, Mapping):
        return tuple(sorted((str(k), _frozen(v)) for k, v in value.items()))
    return value


def _counts(d: Mapping[str, Any], key: str) -> tuple[tuple[str, int], ...]:
    """A count for each side, as the scenario card gives it (rules 24.1 and 25.6)."""
    return tuple(sorted((str(k), int(v)) for k, v in d.get(key, {}).items()))


def scenario_from_dict(d: Mapping[str, Any]) -> Scenario:
    sides = []
    for s in d["sides"]:
        groups = []
        for g in s["groups"]:
            units = tuple(UnitEntry(str(u["type"]), int(u.get("count", 1)), str(u.get("name", ""))) for u in g["units"])
            groups.append(
                Group(
                    str(g["id"]),
                    units,
                    _area_from_dict(g["area"]),
                    bool(g.get("objective", False)),
                    None if g.get("setup_pass") is None else int(g["setup_pass"]),
                    None if g.get("nationality") is None else str(g["nationality"]),
                )
            )
        sides.append(SideSpec(str(s["side"]), str(s["nationality"]), tuple(groups)))
    victory = tuple(
        VictoryCondition(str(v["kind"]), tuple(sorted((k, val) for k, val in v.items() if k != "kind")))
        for v in d.get("victory", [])
    )
    return Scenario(
        id=str(d["id"]),
        title=str(d["title"]),
        board=str(d["board"]),
        turns=int(d["turns"]),
        first_mover=str(d["first_mover"]),
        setup_order=tuple(str(x) for x in d["setup_order"]),
        sides=tuple(sides),
        rules_used=tuple(str(x) for x in d.get("rules_used", [])),
        switches=tuple(sorted((str(k), str(v)) for k, v in d.get("switches", {}).items())),
        victory=victory,
        objectives=tuple(geometry.parse_hex_id(str(h)) for h in d.get("objectives", [])),
        board_generator=tuple(sorted((str(k), v) for k, v in d.get("board_generator", {}).items())),
        board_composition=tuple(sorted((str(k), v) for k, v in d.get("board_composition", {}).items())),
        board_columns=None if d.get("board_columns") is None else (int(d["board_columns"][0]), int(d["board_columns"][1])),
        board_retries=int(d.get("board_retries", 8)),
        first_mover_roll=bool(d.get("first_mover_roll", False)),
        smoke_counters=_counts(d, "smoke_counters"),
        concealment_counters=_counts(d, "concealment_counters"),
        hidden_side=str(d.get("hidden_placement", {}).get("side", "")),
        fanatic_side=str(d.get("fanatic", {}).get("side", "")),
        fanatic_area=None if d.get("fanatic") is None else _area_from_dict(d["fanatic"].get("area", {})),
        notes=str(d.get("notes", "")),
    )
