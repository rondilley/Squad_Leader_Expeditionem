"""The board generator (FR-24 to FR-26, ARCHITECTURE section 7).

Five passes make a board from a seed:

1. Edge pass. The geomorphic constants that all four printed boards share, so that any
   two generated boards join along an edge (FR-24).
2. Structure pass. The large features of the board type (FR-25). A city gets a road grid
   and blocks of stone buildings, with the zone constraints a scenario asks for. A hills
   board gets one or two hill masses in three terraced levels. A village gets a cluster of
   stone buildings around a road junction and one low hill. A rural board gets grain
   fields, hedgerows, and a farmstead or two. The style record of FR-26 gives the density
   of each feature, and each board type has its own default style.
3. Fill pass. Wave Function Collapse over what remains, with the adjacency rules of the
   small hand-written tile set. The sewer entrances of rule 27.1 go on with the
   buildings, because an entrance is a building hex.
4. Polygon pass. The terrain shape of each hex on the exact lattice, for line of sight.
5. Style pass. The client shows the polygons in the 1977 look, so that pass is not here.

The generator is deterministic. The same parameters give the same board, and the
parameter record in a run artifact builds it again.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Sequence

from slboards import edges, polygons
from slboards import tiles as tile_rules
from slboards.wfc import FillFailed, collapse
from slcore import geometry, scenario
from slcore.geometry import HexRef
from slcore.rng import RngState, choice_index, seed_state
from slcore.state import Board, Building, Hex, TerrainType

GENERATOR_VERSION = 7
TYPE_CITY = "city"
TYPE_HILLS = "hills"
TYPE_VILLAGE = "village"
TYPE_RURAL = "rural"
BOARD_TYPES = (TYPE_CITY, TYPE_HILLS, TYPE_VILLAGE, TYPE_RURAL)

MIN_BUILDING = 2
MAX_BUILDING = 6
# How many start hexes the zone pass tries for one zone before it gives the seed up.
ZONE_ATTEMPTS = 40
MAX_FILL_TRIES = 12
SEWER_RANGE = 3
MAX_LEVEL = 3
VILLAGE_RADIUS = 6
# Rule 7.4 makes a building of three hexes or more a multi-story building, and a wooden
# building on the printed boards is a small one.
WOODEN_MAX = 2

# FR-26. `buildings` is a divisor, so a larger number gives fewer buildings. `woods`,
# `grain`, and `shellholes` are the weights the fill pass gives those tiles. `hills` is
# how many hill masses the structure pass raises and `hill_levels` is the top level of
# each. `walls` and `hedges` are how many hexside features the board gets. `roads` is how
# many of the three interior road columns carry a road.
STYLE_KEYS = (
    "buildings", "wooden", "woods", "grain", "shellholes",
    "hills", "hill_levels", "walls", "hedges", "roads", "cliffs",
)

STYLE_DEFAULTS: dict[str, dict[str, int]] = {
    TYPE_CITY: {
        "cliffs": 0, "wooden": 0, "buildings": 3, "woods": 12, "grain": 4, "shellholes": 16,
        "hills": 0, "hill_levels": 0, "walls": 0, "hedges": 0, "roads": 3,
    },
    TYPE_HILLS: {
        "cliffs": 4, "wooden": 45, "buildings": 14, "woods": 30, "grain": 8, "shellholes": 4,
        "hills": 2, "hill_levels": 3, "walls": 0, "hedges": 6, "roads": 1,
    },
    TYPE_VILLAGE: {
        "cliffs": 0, "wooden": 35, "buildings": 5, "woods": 20, "grain": 14, "shellholes": 5,
        "hills": 1, "hill_levels": 1, "walls": 10, "hedges": 8, "roads": 2,
    },
    TYPE_RURAL: {
        "cliffs": 2, "wooden": 55, "buildings": 16, "woods": 18, "grain": 40, "shellholes": 3,
        "hills": 1, "hill_levels": 2, "walls": 2, "hedges": 18, "roads": 2,
    },
}


def default_style(board_type: str) -> dict[str, int]:
    """The style of a board type, as a new dictionary the caller may change."""
    if board_type not in STYLE_DEFAULTS:
        raise GeneratorError(f"there is no default style for the board type {board_type!r}")
    return dict(STYLE_DEFAULTS[board_type])


class GeneratorError(Exception):
    """The generator cannot satisfy the parameters it was given."""


@dataclass(frozen=True)
class ZoneConstraint:
    """What a scenario asks of the board before it sets up (FR-21).

    The generator makes at least `count` stone buildings whose hex count is inside the
    range, so that the zones of the scenario resolve on the board it makes.

    A scenario that plays on part of a board gives the column range too. A building that
    crosses the edge of that range does not count, because the column subset cuts it and
    its hex count changes. A row range is the same test on the other axis, for a card
    whose front runs along the rows.

    `near` puts the buildings of this zone next to the buildings of another band: it holds
    the band keys and a `max_distance`, and a building counts only when a stone building
    of that band is within the distance. The predicates are `slcore.scenario.in_band` and
    `near_band`, the ones the set up areas resolve with, so the board the generator passes
    is a board the scenario sets up on.
    """

    count: int
    min_hexes: int = 2
    max_hexes: int = MAX_BUILDING
    min_col: int | None = None
    max_col: int | None = None
    min_row: int | None = None
    max_row: int | None = None
    near: tuple[tuple[str, int], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "count": self.count,
            "min_hexes": self.min_hexes,
            "max_hexes": self.max_hexes,
            "min_col": self.min_col,
            "max_col": self.max_col,
        }
        if self.min_row is not None:
            out["min_row"] = self.min_row
        if self.max_row is not None:
            out["max_row"] = self.max_row
        if self.near:
            out["near"] = dict(self.near)
        return out

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "ZoneConstraint":
        near = d.get("near") or {}
        return ZoneConstraint(
            int(d["count"]),
            int(d.get("min_hexes", 2)),
            int(d.get("max_hexes", MAX_BUILDING)),
            None if d.get("min_col") is None else int(d["min_col"]),
            None if d.get("max_col") is None else int(d["max_col"]),
            None if d.get("min_row") is None else int(d["min_row"]),
            None if d.get("max_row") is None else int(d["max_row"]),
            tuple(sorted((str(k), int(v)) for k, v in dict(near).items())),
        )

    def band(self) -> dict[str, int]:
        """The band keys, in the form the scenario predicates read."""
        out: dict[str, int] = {}
        for key in ("min_col", "max_col", "min_row", "max_row"):
            value = getattr(self, key)
            if value is not None:
                out[key] = value
        return out

    def holds(self, shape: list[HexRef], shapes: Sequence[Sequence[HexRef]] = ()) -> bool:
        """True when this building counts against the constraint.

        `shapes` is each stone building of the board, for the `near` test.
        """
        if not self.min_hexes <= len(shape) <= self.max_hexes:
            return False
        if not scenario.in_band(shape, self.band()):
            return False
        if self.near and not scenario.near_band(shape, shapes, dict(self.near)):
            return False
        return True

    def where(self) -> str:
        params: dict[str, Any] = self.band()
        if self.near:
            params["near"] = dict(self.near)
        return scenario.band_text(params)


@dataclass(frozen=True)
class GeneratorParameters:
    """The record that a run artifact stores, so that a board can be built again."""

    seed: int
    board_type: str = TYPE_CITY
    cols: int = edges.COLS
    rows: int = edges.ROWS
    version: int = GENERATOR_VERSION
    building_density: int | None = None
    style: tuple[tuple[str, int], ...] = field(default_factory=tuple)
    zones: tuple[ZoneConstraint, ...] = field(default_factory=tuple)

    def styles(self) -> dict[str, int]:
        """The style of this board: the default of its type, with the overrides on top.

        `building_density` is the name the earlier slices used for one of these numbers.
        A record that carries it still builds the board it built before.
        """
        out = default_style(self.board_type)
        if self.building_density is not None:
            out["buildings"] = self.building_density
        for key, value in self.style:
            if key not in STYLE_KEYS:
                raise GeneratorError(f"{key!r} is not a style of a board; the styles are {STYLE_KEYS}")
            out[key] = int(value)
        return out

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "seed": self.seed,
            "board_type": self.board_type,
            "cols": self.cols,
            "rows": self.rows,
            "version": self.version,
            "style": dict(self.style),
            "zones": [z.to_dict() for z in self.zones],
        }
        if self.building_density is not None:
            doc["building_density"] = self.building_density
        return doc

    @staticmethod
    def from_dict(d: Mapping[str, Any]) -> "GeneratorParameters":
        density = d.get("building_density")
        return GeneratorParameters(
            seed=int(d["seed"]),
            board_type=str(d.get("board_type", TYPE_CITY)),
            cols=int(d.get("cols", edges.COLS)),
            rows=int(d.get("rows", edges.ROWS)),
            version=int(d.get("version", GENERATOR_VERSION)),
            building_density=None if density is None else int(density),
            style=tuple(sorted((str(k), int(v)) for k, v in dict(d.get("style", {})).items())),
            zones=tuple(ZoneConstraint.from_dict(z) for z in d.get("zones", [])),
        )


def all_refs(cols: int, rows: int) -> list[HexRef]:
    out = []
    for col in range(cols):
        first = 0 if col & 1 else 1
        for row in range(first, rows + 1):
            out.append((col, row))
    return out


# ------------------------------------------------------------------ the passes


def edge_pass(cols: int, rows: int) -> tuple[dict[HexRef, str], set[HexRef], set[HexRef]]:
    """Pass 1: the geomorphic constants (FR-24).

    Each hex that a seam can touch takes the kind that `edges.seam_kind` names, and the
    third value of the answer is the set of those hexes. The later passes leave them alone.
    Without that, two boards disagree where they meet and no composition of FR-29 holds.
    """
    kinds: dict[HexRef, str] = {ref: tile_rules.OPEN for ref in all_refs(cols, rows)}
    roads: set[HexRef] = set()
    fixed: set[HexRef] = set()
    for ref in edges.seam_hexes(cols, rows):
        wanted = edges.seam_kind(ref, cols, rows)
        fixed.add(ref)
        if wanted == edges.ROAD_KIND:
            roads.add(ref)
        elif wanted == edges.WOODS_KIND:
            kinds[ref] = tile_rules.WOODS
        else:
            kinds[ref] = tile_rules.OPEN
    return kinds, roads, fixed


@dataclass
class Structure:
    """What pass 2 builds on top of the edge constants."""

    buildings: dict[HexRef, Building] = field(default_factory=dict)
    elevation: dict[HexRef, int] = field(default_factory=dict)
    sides: dict[HexRef, list[str | None]] = field(default_factory=dict)

    def level(self, ref: HexRef) -> int:
        return self.elevation.get(ref, 0)

    def hexsides(self, ref: HexRef) -> tuple[str | None, ...]:
        return tuple(self.sides.get(ref, [None] * 6))


def middle_row(rows: int) -> int:
    """The row the east to west road runs along.

    It is row 5 on a board of ten rows, which is the row that the road entries of FR-24
    name on the west edge and on the east edge (A5 and GG5).
    """
    return min(rows, max(1, rows // 2))


def road_grid(kinds: dict[HexRef, str], roads: set[HexRef], cols: int, rows: int, columns: int) -> None:
    """The north-south roads of the edge constants, and one road from west to east.

    The count says how many of the three interior road columns carry a road. A board type
    with fewer roads still joins its neighbours, because the road entries of FR-24 are on
    the edge hexes and the edge pass has already placed them.

    The east to west road holds one row index for each column. A column of an odd index
    sits half a hex lower than its neighbours on this lattice, so one row index gives the
    zigzag that a road on a hex grid has, and each hex of it touches the next. An earlier
    version of this function put the odd columns one row lower as well. That made a line
    of hexes that are two apart, so the road was 21 pieces and not one road.
    """
    road_columns = edges.road_column_indexes(cols)[:columns]
    middle = middle_row(rows)
    seam = set(edges.seam_hexes(cols, rows))
    for ref in all_refs(cols, rows):
        if kinds[ref] == tile_rules.WOODS:
            continue
        if ref in seam and edges.seam_kind(ref, cols, rows) != edges.ROAD_KIND:
            # A seam hex is the same on each board, so the road grid stops at it. The road
            # entries of FR-24 are already roads, and they carry the road across a join.
            continue
        if ref[0] in road_columns or ref[1] == middle:
            roads.add(ref)


def structure_pass(
    rng: RngState,
    kinds: dict[HexRef, str],
    roads: set[HexRef],
    params: GeneratorParameters,
    fixed: set[HexRef] | None = None,
) -> tuple[RngState, Structure]:
    """Pass 2: the large features of the board type (FR-25)."""
    if params.board_type not in BOARD_TYPES:
        raise GeneratorError(f"there is no structure pass for the board type {params.board_type!r}")
    style = params.styles()
    structure = Structure()
    road_grid(kinds, roads, params.cols, params.rows, style["roads"])
    connect_roads(kinds, roads, params.cols, params.rows)
    rng = hill_pass(rng, structure, params, style)
    rng, buildings = place_buildings(rng, kinds, roads, params, style, structure, fixed or set())
    structure.buildings = buildings
    rng = hexside_pass(rng, structure, kinds, roads, params, style)
    rng = cliff_pass(rng, structure, kinds, params, style)
    return rng, structure


# ----------------------------------------------------------------------- the hill masses


def hill_pass(
    rng: RngState,
    structure: Structure,
    params: GeneratorParameters,
    style: Mapping[str, int],
) -> RngState:
    """One or two hill masses in terraces, for rule 43.

    A mass is a centre and a radius. The level of a hex falls with its distance from the
    centre, in whole steps, so the mass comes out as the terraces of rules 43.11 to 43.13
    and not as a smooth dome. A jitter of one level keeps the crest line off a circle.

    The outer ring of the board stays on ground level. Two boards join along an edge
    (FR-24), and a seam between two levels would be a step that no rule describes.
    """
    masses = style["hills"]
    top = min(style["hill_levels"], MAX_LEVEL)
    if masses <= 0 or top <= 0:
        return rng
    cols, rows = params.cols, params.rows
    for _ in range(masses):
        rng, col = choice_index(rng, max(1, cols - 8))
        rng, row = choice_index(rng, max(1, rows - 4))
        rng, extra = choice_index(rng, 3)
        centre = (col + 4, row + 2)
        radius = top + 1 + extra
        for ref in all_refs(cols, rows):
            gap = geometry.distance(centre, ref)
            if gap > radius:
                continue
            level = top - (gap * top) // radius
            rng, jitter = choice_index(rng, 4)
            if jitter == 0 and level > 0:
                level -= 1
            if level > 0:
                structure.elevation[ref] = max(structure.level(ref), level)
    flatten_edge(structure, cols, rows)
    smooth_levels(structure, cols, rows)
    return rng


def flatten_edge(structure: Structure, cols: int, rows: int) -> None:
    """The outer ring of the board is ground level, so that any two boards join."""
    for ref in all_refs(cols, rows):
        if on_the_rim(ref, cols, rows):
            structure.elevation.pop(ref, None)


def smooth_levels(structure: Structure, cols: int, rows: int) -> None:
    """No hex stands more than one level above its lowest neighbour.

    A step of two levels between two adjacent hexes is a cliff (rule 44.1), and a cliff
    hexside is impassable. The generator makes no cliffs, because a hill it cannot walk on
    would cut a board in two and no scenario asks for that. So it lowers each hex until
    every slope is one level, which is what a terrace is.
    """
    changed = True
    while changed:
        changed = False
        for ref in sorted(structure.elevation):
            here = structure.level(ref)
            lowest = min(
                (structure.level(n) for n in geometry.neighbors(*ref) if 0 <= n[0] < cols),
                default=0,
            )
            if here > lowest + 1:
                structure.elevation[ref] = lowest + 1
                changed = True


# --------------------------------------------------------------- the walls and the hedges


def hexside_pass(
    rng: RngState,
    structure: Structure,
    kinds: dict[HexRef, str],
    roads: set[HexRef],
    params: GeneratorParameters,
    style: Mapping[str, int],
) -> RngState:
    """The walls and the hedges of rule 11.5, along a hexside between two open hexes.

    A feature goes on both hexes it separates, because the board checks that a hexside
    reads the same from each side. The board edge and the road hexes stay clear: a wall on
    the seam would not meet the wall of the board next to it, and a wall across a road
    entry would close a road that FR-24 asks every board to carry. A hexside between two
    levels stays clear too, because that hexside is already a crest line.
    """
    for feature, count in (("wall", style["walls"]), ("hedge", style["hedges"])):
        placed = 0
        tries = 0
        while placed < count and tries < count * 40 + 40:
            tries += 1
            rng, index = choice_index(rng, params.cols * (params.rows + 1))
            here = (index // (params.rows + 1), index % (params.rows + 1))
            rng, d = choice_index(rng, 6)
            there = geometry.neighbor(here[0], here[1], d)
            if here not in kinds or there not in kinds:
                continue
            if here in roads or there in roads:
                continue
            if structure.level(here) != structure.level(there):
                continue
            if not open_ground(kinds, here) or not open_ground(kinds, there):
                continue
            if on_the_rim(here, params.cols, params.rows) or on_the_rim(there, params.cols, params.rows):
                continue
            near = structure.sides.setdefault(here, [None] * 6)
            far = structure.sides.setdefault(there, [None] * 6)
            if near[d] is not None or far[(d + 3) % 6] is not None:
                continue
            near[d] = feature
            far[(d + 3) % 6] = feature
            placed += 1
    return rng


def walkable(structure: "Structure", kinds, cols: int, rows: int) -> bool:
    """Whether each hex of the board reaches each other hex without crossing a cliff.

    Rule 44.1 makes a cliff hexside impassable. A board that a cliff cuts in two is a board
    that a scenario cannot use, so the cliff pass keeps only the cliffs that leave the board
    in one piece.
    """
    refs = [ref for ref in all_refs(cols, rows) if ref in kinds]
    if not refs:
        return True
    start = refs[0]
    seen = {start}
    frontier = [start]
    while frontier:
        here = frontier.pop()
        sides = structure.sides.get(here, [None] * 6)
        for d in range(6):
            if sides[d] == "cliff":
                continue
            nxt = geometry.neighbor(*here, d)
            if nxt in seen or nxt not in kinds:
                continue
            seen.add(nxt)
            frontier.append(nxt)
    return len(seen) == len(refs)


def cliff_pass(
    rng: RngState,
    structure: "Structure",
    kinds,
    params: GeneratorParameters,
    style: Mapping[str, int],
) -> RngState:
    """Rule 44.1: a black hexside on a hill, which no unit crosses.

    A cliff goes on a hexside where the level changes, because that is where the printed
    boards put one. A candidate that would cut the board in two is dropped, so the board
    stays walkable and each scenario can use it.
    """
    wanted = style["cliffs"]
    if wanted <= 0 or not structure.elevation:
        return rng
    crests = []
    for ref in sorted(structure.elevation):
        here = structure.level(ref)
        for d in range(6):
            try:
                other = geometry.neighbor(*ref, d)
            except ValueError:
                continue
            if other not in kinds or on_the_rim(other, params.cols, params.rows):
                continue
            if on_the_rim(ref, params.cols, params.rows):
                continue
            if structure.level(other) < here:
                crests.append((ref, d))
    placed = 0
    tries = 0
    while placed < wanted and crests and tries < wanted * 30 + 30:
        tries += 1
        rng, index = choice_index(rng, len(crests))
        ref, d = crests.pop(index)
        other = geometry.neighbor(*ref, d)
        near = structure.sides.setdefault(ref, [None] * 6)
        far = structure.sides.setdefault(other, [None] * 6)
        if near[d] is not None or far[(d + 3) % 6] is not None:
            continue
        near[d] = "cliff"
        far[(d + 3) % 6] = "cliff"
        if walkable(structure, kinds, params.cols, params.rows):
            placed += 1
            continue
        near[d] = None
        far[(d + 3) % 6] = None
    return rng


def open_ground(kinds, ref: HexRef) -> bool:
    return kinds.get(ref) in (tile_rules.OPEN, tile_rules.WHEAT)


def on_the_rim(ref: HexRef, cols: int, rows: int) -> bool:
    col, row = ref
    first = 0 if col & 1 else 1
    return col in (0, cols - 1) or row in (first, rows)


def fill_pass(
    rng: RngState,
    kinds: dict[HexRef, str],
    roads: set[HexRef],
    buildings: dict[HexRef, Building],
    params: GeneratorParameters,
    seam: set[HexRef] | None = None,
) -> tuple[RngState, dict[HexRef, str]]:
    """Pass 3: Wave Function Collapse over the hexes the first two passes left open."""
    tiles = tile_rules.tile_set(params.board_type, params.styles())
    fillable = tile_rules.fillable(tiles)
    fixed: dict[HexRef, str] = {}
    free: list[HexRef] = []
    on_a_seam = seam or set()
    for ref, kind in kinds.items():
        if ref in buildings:
            fixed[ref] = tile_rules.STONE
        elif ref in roads or kind != tile_rules.OPEN or ref in on_a_seam:
            fixed[ref] = kind
        else:
            free.append(ref)
    free.sort()
    for attempt in range(MAX_FILL_TRIES):
        try:
            return collapse(rng, free, fixed, tiles, fillable)
        except FillFailed:
            rng, _ = choice_index(rng, 97)
            if attempt == MAX_FILL_TRIES - 1:
                raise GeneratorError(
                    f"the fill pass did not satisfy the adjacency rules in {MAX_FILL_TRIES} tries for seed {params.seed}"
                )
    raise GeneratorError("the fill pass did not run")


def polygon_pass(
    rng: RngState, kinds: dict[HexRef, str], terrain: Mapping[str, TerrainType]
) -> tuple[RngState, dict[HexRef, tuple]]:
    """Pass 4: the terrain shape of each hex on the exact lattice."""
    out: dict[HexRef, tuple] = {}
    for ref in sorted(kinds):
        kind = kinds[ref]
        if terrain[kind].los == "clear":
            out[ref] = ()
            continue
        rng, index = choice_index(rng, len(polygons.SHAPES))
        out[ref] = polygons.polygons_for(ref[0], ref[1], kind, terrain, index)
    return rng, out


# ------------------------------------------------------------------- buildings


def road_groups(roads: set[HexRef]) -> list[set[HexRef]]:
    """The road hexes in groups that touch, largest first."""
    seen: set[HexRef] = set()
    out: list[set[HexRef]] = []
    for start in sorted(roads):
        if start in seen:
            continue
        group: set[HexRef] = set()
        stack = [start]
        while stack:
            here = stack.pop()
            if here in group:
                continue
            group.add(here)
            seen.add(here)
            for near in geometry.neighbors(*here):
                if near in roads and near not in group:
                    stack.append(near)
        out.append(group)
    out.sort(key=lambda g: (-len(g), sorted(g)[0]))
    return out


def connect_roads(kinds: dict[HexRef, str], roads: set[HexRef], cols: int, rows: int) -> None:
    """Join each part of the road network to the largest part.

    FR-24 puts a road entry on each edge that a neighbour board can join. A board that
    does not use one of those entries in its own grid gets a road hex that leads nowhere.
    This walks the shortest way from each such part to the main network and makes it road.

    The way goes through open ground only. It does not cross a woods hex, and it does not
    touch a seam hex that FR-24 fixed to another kind, because two boards that meet must
    agree on each seam hex.
    """
    seam = {ref: edges.seam_kind(ref, cols, rows) for ref in edges.seam_hexes(cols, rows)}

    def passable(ref: HexRef) -> bool:
        if ref not in kinds:
            return False
        if ref in seam and seam[ref] != edges.ROAD_KIND:
            return False
        return kinds[ref] != tile_rules.WOODS

    groups = road_groups(roads)
    if len(groups) <= 1:
        return
    main = set(groups[0])
    for group in groups[1:]:
        path = shortest_link(group, main, passable)
        if path is None:
            continue
        roads.update(path)
        main |= group | set(path)


def shortest_link(
    start: set[HexRef], goal: set[HexRef], passable: "Callable[[HexRef], bool]"
) -> list[HexRef] | None:
    """The shortest way of open hexes from one group to another, or None when there is none."""
    frontier: deque[HexRef] = deque(sorted(start))
    came: dict[HexRef, HexRef | None] = {ref: None for ref in start}
    while frontier:
        here = frontier.popleft()
        if here in goal and here not in start:
            path = []
            step: HexRef | None = here
            while step is not None and step not in start:
                path.append(step)
                step = came[step]
            return list(reversed(path))
        for near in sorted(geometry.neighbors(*here)):
            if near in came or not passable(near):
                continue
            came[near] = here
            frontier.append(near)
    return None


def junctions(roads: set[HexRef], cols: int, columns: int, rows: int = edges.ROWS) -> list[HexRef]:
    """The crossroads: where a north to south road meets the east to west road."""
    row = middle_row(rows)
    return sorted((col, row) for col in edges.road_column_indexes(cols)[:columns] if (col, row) in roads)


def place_buildings(
    rng: RngState,
    kinds: dict[HexRef, str],
    roads: set[HexRef],
    params: GeneratorParameters,
    style: Mapping[str, int],
    structure: "Structure",
    fixed: set[HexRef] | None = None,
) -> tuple[RngState, dict[HexRef, Building]]:
    """Blocks of stone buildings between the roads, with the zone constraints of FR-21.

    A village puts most of its buildings around one road junction, which is what makes it
    a village and not a thin city: the buildings of the first pass have to start inside
    the cluster radius, and only the buildings that the radius cannot hold go elsewhere.

    A building stays on one level. A shape that climbed a terrace would stand on two
    heights at once, and rule 43.14 gives a hex one level, the level of its centre dot.
    """
    blocks = building_blocks(params.cols, roads)
    centre: HexRef | None = None
    if params.board_type == TYPE_VILLAGE:
        found = junctions(roads, params.cols, style["roads"], params.rows)
        if found:
            rng, index = choice_index(rng, len(found))
            centre = found[index]
    shapes: list[list[HexRef]] = []
    seeded: set[HexRef] = set()
    if any(z.near for z in params.zones):
        # The zones go on the board first, and the free pass fills around them. A near
        # zone needs the buildings of the other band before its own, and a board the free
        # pass has filled has no room for a building of the size the zone asks for. A
        # record with no near zone does not take this path, so it builds the same board
        # as before.
        rng = fill_zones(rng, kinds, roads, params, structure, blocks, shapes, fixed)
        for shape in shapes:
            seeded.update(shape)
            for h in shape:
                seeded.update(geometry.neighbors(*h))
    for lo, hi in blocks:
        keep_out = fixed or set()
        free = [
            (c, r)
            for c in range(lo, hi + 1)
            for r in range(0 if c & 1 else 1, params.rows + 1)
            if (c, r) not in roads and (c, r) not in keep_out and kinds.get((c, r)) == tile_rules.OPEN
        ]
        free.sort()
        taken: set[HexRef] = {h for h in seeded if lo <= h[0] <= hi}
        wanted = max(1, len(free) // (style["buildings"] * MIN_BUILDING * 2))
        for _ in range(wanted):
            candidates = [f for f in free if f not in taken and not touches(f, taken)]
            if centre is not None and candidates:
                # A village is a cluster around one junction. A building starts inside the
                # radius when the block reaches that far. A block that does not reach it
                # still keeps the cluster shape, because the start goes in the part of the
                # block that is nearest the junction and not anywhere in it.
                near = [f for f in candidates if geometry.distance(centre, f) <= VILLAGE_RADIUS]
                if near:
                    candidates = near
                else:
                    candidates.sort(key=lambda f: (geometry.distance(centre, f), f))
                    candidates = candidates[: max(1, len(candidates) // 3)]
            if not candidates:
                break
            rng, i = choice_index(rng, len(candidates))
            start = candidates[i]
            rng, extra = choice_index(rng, MAX_BUILDING - MIN_BUILDING + 1)
            level = structure.level(start)
            on_one_level = [f for f in free if structure.level(f) == level]
            rng, which = choice_index(rng, len(SILHOUETTES))
            rng, heading = choice_index(rng, 6)
            shape = grow(
                start, MIN_BUILDING + extra, on_one_level, taken, roads, SILHOUETTES[which], heading
            )
            if len(shape) < MIN_BUILDING:
                taken.add(start)
                continue
            taken.update(shape)
            for h in shape:
                taken.update(geometry.neighbors(*h))
            shapes.append(shape)
    shapes.sort(key=lambda s: min(s))
    # A wooden building on the printed boards is small, so only the small shapes become
    # wooden. The share comes from the style, and the city board has none: RV-2 records
    # board 1 as a stone city.
    wooden: set[int] = set()
    share = style["wooden"]
    for i, shape in enumerate(shapes):
        if len(shape) > WOODEN_MAX or share <= 0:
            continue
        rng, roll = choice_index(rng, 100)
        if roll < share:
            wooden.add(i)
    # FR-21 counts the stone buildings, because a scenario zone asks for stone.
    check_zones([shape for i, shape in enumerate(shapes) if i not in wooden], params)
    out: dict[HexRef, Building] = {}
    for i, shape in enumerate(shapes):
        is_wooden = i in wooden
        building = Building(f"B{i + 1}", "wooden" if is_wooden else "stone", len(shape))
        for h in shape:
            out[h] = building
            kinds[h] = tile_rules.WOODEN if is_wooden else tile_rules.STONE
    return rng, out


def sewer_pass(shapes: list[list[HexRef]]) -> set[HexRef]:
    """The sewer entrances of rule 27.1.

    The printed boards mark an entrance in a building hex. The generator marks the first
    hex of each building of two hexes or more, and then keeps only the entrances that
    have a second entrance within the three hexes of rule 27.2. An entrance with no
    destination is a mark with no move behind it.
    """
    candidates = sorted(min(shape) for shape in shapes if len(shape) >= MIN_BUILDING)
    return {
        ref
        for ref in candidates
        if any(other != ref and geometry.distance(ref, other) <= SEWER_RANGE for other in candidates)
    }


def fill_zones(
    rng: RngState,
    kinds: dict[HexRef, str],
    roads: set[HexRef],
    params: GeneratorParameters,
    structure: "Structure",
    blocks: list[tuple[int, int]],
    shapes: list[list[HexRef]],
    fixed: set[HexRef] | None = None,
) -> RngState:
    """The buildings the zones ask for, placed before the free pass (FR-21).

    The free placement scatters the buildings over the board, and a zone that asks for
    buildings within a few hexes of another band is then satisfied by one seed in fifty,
    and a zone that asks for a building of four hexes in a band of three rows almost never.
    The card of scenario 1 puts each Russian building on top of a German one, and the
    guards building holds twelve squads. So this pass places what each zone asks for, in
    the order of the zones: a start hex inside the zone's band, and within the distance of
    a building of the other band when the zone has `near`, then a shape of the size the
    zone asks for. A zone with `near` comes after the zone that holds its anchors, which is
    the order the scenario writes them in.
    """
    keep_out = fixed or set()
    taken: set[HexRef] = set()
    for shape in shapes:
        taken.update(shape)
        for h in shape:
            taken.update(geometry.neighbors(*h))
    free_by_block = []
    for lo, hi in blocks:
        free = [
            (c, r)
            for c in range(lo, hi + 1)
            for r in range(0 if c & 1 else 1, params.rows + 1)
            if (c, r) not in roads and (c, r) not in keep_out and kinds.get((c, r)) == tile_rules.OPEN
        ]
        free.sort()
        free_by_block.append(((lo, hi), free))
    for zone in params.zones:
        band = zone.band()
        near = dict(zone.near)
        limit = int(near.get("max_distance", 2))
        front = anchor_front(zone, params.zones, free_by_block)
        attempts = 0
        while sum(1 for s in shapes if zone.holds(s, shapes)) < zone.count and attempts < ZONE_ATTEMPTS:
            attempts += 1
            anchors: set[HexRef] = set()
            if near:
                anchors = {h for s in shapes if scenario.in_band(s, near) for h in s}
                if not anchors:
                    break
            candidates = []
            for (lo, hi), free in free_by_block:
                for f in free:
                    # The free pass keeps two open hexes between blocks. The card puts
                    # the two sides one hexside apart, so this pass keeps one.
                    if f in taken:
                        continue
                    if not scenario.in_band([f], band):
                        continue
                    if near and not any(geometry.distance(f, a) <= limit for a in anchors):
                        continue
                    if front is not None and f not in front:
                        continue
                    candidates.append((f, free))
            if not candidates:
                break
            rng, i = choice_index(rng, len(candidates))
            start, free = candidates[i]
            rng, extra = choice_index(rng, zone.max_hexes - zone.min_hexes + 1)
            level = structure.level(start)
            on_one_level = [f for f in free if structure.level(f) == level]
            rng, which = choice_index(rng, len(SILHOUETTES))
            rng, heading = choice_index(rng, 6)
            shape = grow(
                start, zone.min_hexes + extra, on_one_level, taken, roads, SILHOUETTES[which], heading
            )
            if len(shape) < zone.min_hexes or not zone.holds(shape, shapes + [shape]):
                taken.add(start)
                continue
            taken.update(shape)
            for h in shape:
                taken.update(geometry.neighbors(*h))
            shapes.append(shape)
    return rng


def anchor_front(
    zone: ZoneConstraint,
    zones: Sequence[ZoneConstraint],
    free_by_block: Sequence[tuple[tuple[int, int], Sequence[HexRef]]],
) -> set[HexRef] | None:
    """The start hexes of a zone that a later `near` zone anchors on, or None.

    A near zone puts its buildings within a distance of the buildings of this zone. A
    building of this zone that is deeper in its band than that distance anchors nothing,
    and the near zone then runs out of room. So the starts of an anchor zone stay within
    the distance of the near zone's band, which is the front of the card: the German
    buildings of scenario 1 stand along the street the Russians attack across.
    """
    if zone.near:
        return None
    own = zone.band()
    front: set[HexRef] = set()
    found = False
    for other in zones:
        if not other.near:
            continue
        other_near = {k: v for k, v in dict(other.near).items() if k != "max_distance"}
        if other_near != own:
            continue
        found = True
        limit = int(dict(other.near).get("max_distance", 2))
        other_band = other.band()
        band_hexes = [f for _, free in free_by_block for f in free if scenario.in_band([f], other_band)]
        for _, free in free_by_block:
            for f in free:
                if scenario.in_band([f], own) and any(
                    geometry.distance(f, g) <= limit for g in band_hexes
                ):
                    front.add(f)
    return front if found else None


def check_zones(shapes: list[list[HexRef]], params: GeneratorParameters) -> None:
    """FR-21: the board must hold the buildings that the scenario zones ask for."""
    for zone in params.zones:
        matching = [s for s in shapes if zone.holds(s, shapes)]
        if len(matching) < zone.count:
            raise GeneratorError(
                f"seed {params.seed} gives {len(matching)} stone buildings of {zone.min_hexes} to "
                f"{zone.max_hexes} hexes {zone.where()}, and the scenario asks for {zone.count}"
            )


def touches(ref: HexRef, taken: set[HexRef]) -> bool:
    return any(n in taken for n in geometry.neighbors(*ref))


# The building silhouettes of the printed boards, as arms from the first hex. Each arm is
# (the index of the hex it starts from, the turn in direction steps, how many hexes). A turn
# of one direction step is 60 degrees, and a turn of two is 120 degrees. RV-2 section 1.4
# records the four silhouettes: a long block, an L, a T, and a plus.
LONG = ((0, 0, 5),)
ELL = ((0, 0, 3), (3, 1, 2))
TEE = ((0, 0, 4), (2, 2, 2))
PLUS = ((0, 0, 2), (1, 2, 1), (1, 4, 1), (1, 1, 1))
SILHOUETTES = (LONG, ELL, TEE, PLUS)


def along(
    start: HexRef,
    arms: tuple[tuple[int, int, int], ...],
    heading: int,
    size: int,
    open_hexes: set[HexRef],
) -> list[HexRef]:
    """One silhouette from `start`, cut to `size` hexes.

    The walk stops at the first hex it cannot use, and it gives back what it has. A shape
    that comes out below the minimum is not a building, and the caller drops it.
    """
    shape: list[HexRef] = [start]
    for base, turn, length in arms:
        if base >= len(shape) or len(shape) >= size:
            break
        here = shape[base]
        direction = (heading + turn) % 6
        for _ in range(length):
            if len(shape) >= size:
                break
            try:
                here = geometry.neighbor(*here, direction)
            except ValueError:
                break
            if here in shape or here not in open_hexes:
                break
            shape.append(here)
    return shape


def grow(
    start: HexRef,
    size: int,
    free: list[HexRef],
    taken: set[HexRef],
    roads: set[HexRef],
    silhouette: tuple[tuple[int, int, int], ...] | None = None,
    heading: int = 0,
) -> list[HexRef]:
    """A building shape of at most `size` hexes from `start`.

    With a silhouette, the shape is one of the four block forms of the printed boards. The
    block grid is narrow, so a silhouette often does not fit, and then the shape falls back
    to the compact form that the earlier slices used. A compact block is on the printed
    boards too, so the fallback is a shape and not a defect.
    """
    open_hexes = {f for f in free if f not in taken and f not in roads} | {start}
    if silhouette is not None:
        shape = along(start, silhouette, heading, size, open_hexes)
        if len(shape) >= MIN_BUILDING:
            return sorted(shape)
    free_set = set(free)
    shape = [start]
    frontier = [start]
    while len(shape) < size and frontier:
        here = frontier.pop(0)
        for d in range(6):
            nxt = geometry.neighbor(*here, d)
            if len(shape) >= size:
                break
            if nxt in shape or nxt not in free_set or nxt in taken or nxt in roads:
                continue
            shape.append(nxt)
            frontier.append(nxt)
    return sorted(shape)


def building_shapes(buildings: Mapping[HexRef, Building]) -> list[list[HexRef]]:
    """The hexes of each building, from the map that pass 2 made."""
    groups: dict[str, list[HexRef]] = {}
    for ref, building in buildings.items():
        groups.setdefault(building.id, []).append(ref)
    return [sorted(v) for _, v in sorted(groups.items())]


def building_blocks(cols: int, roads: set[HexRef]) -> list[tuple[int, int]]:
    """The column ranges between the north and south roads."""
    road_cols = sorted(edges.road_column_indexes(cols))
    out: list[tuple[int, int]] = []
    lo = 0
    for rc in road_cols + [cols]:
        hi = rc - 1
        if hi >= lo:
            out.append((lo, hi))
        lo = rc + 1
    return [(a, b) for a, b in out if a <= b and b < cols]


# ---------------------------------------------------------------- the generator


def generate(params: GeneratorParameters, terrain: Mapping[str, TerrainType]) -> Board:
    """A board of the type the parameters name. The five passes run in sequence."""
    if params.board_type not in BOARD_TYPES:
        raise NotImplementedError(
            f"board type {params.board_type!r} is not one of the four types {BOARD_TYPES}"
        )
    rng = seed_state(params.seed ^ (params.version << 20))
    kinds, roads, seam = edge_pass(params.cols, params.rows)
    rng, structure = structure_pass(rng, kinds, roads, params, seam)
    buildings = structure.buildings
    rng, filled = fill_pass(rng, kinds, roads, buildings, params, seam)
    kinds.update(filled)
    for ref, building in buildings.items():
        kinds[ref] = tile_rules.WOODEN if building.kind == "wooden" else tile_rules.STONE
    rng, shapes = polygon_pass(rng, kinds, terrain)
    # Rule 27 is a city rule, and the printed sewer entrances are on the city board, so a
    # country board has none. A scenario that asks for a sewer move on one gets no move.
    sewers = sewer_pass(building_shapes(buildings)) if params.board_type == TYPE_CITY else set()
    hexes = [
        Hex(
            col=ref[0],
            row=ref[1],
            terrain=kinds[ref],
            elevation=structure.level(ref),
            road=ref in roads,
            building=buildings.get(ref),
            hexsides=structure.hexsides(ref),
            sewer=ref in sewers,
            polygons=shapes[ref],
        )
        for ref in all_refs(params.cols, params.rows)
    ]
    name = f"{params.board_type}-{params.seed}-v{params.version}"
    return Board(params.cols, params.rows, hexes, terrain, name=name)


def generate_with_retry(
    params: GeneratorParameters, terrain: Mapping[str, TerrainType], tries: int = 8
) -> tuple[Board, GeneratorParameters]:
    """FR-21: when a seed does not satisfy the zones, try the next one, and say so.

    The caller gets the parameters that made the board, so a run artifact records the
    seed that worked and not the seed that was asked for.
    """
    last: GeneratorError | None = None
    for step in range(tries):
        attempt = GeneratorParameters(
            seed=params.seed + step,
            board_type=params.board_type,
            cols=params.cols,
            rows=params.rows,
            version=params.version,
            building_density=params.building_density,
            style=params.style,
            zones=params.zones,
        )
        try:
            return generate(attempt, terrain), attempt
        except GeneratorError as exc:
            last = exc
    raise GeneratorError(
        f"no seed from {params.seed} to {params.seed + tries - 1} satisfies the zones of this scenario. "
        f"The last cause: {last}. Ask for another seed or another board type."
    )


def generate_city(params: GeneratorParameters, terrain: Mapping[str, TerrainType]) -> Board:
    """The name the earlier slices used. It makes a city board."""
    return generate(params, terrain)


def board_to_dict(board: Board, params: GeneratorParameters) -> dict[str, Any]:
    doc = board.to_dict()
    doc["generator"] = params.to_dict()
    return doc
