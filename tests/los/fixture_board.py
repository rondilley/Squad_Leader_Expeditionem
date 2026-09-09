"""A hand-written 10 by 10 test board. It is not a 1977 layout.

Columns A to J, rows 1 to 10 (odd-index columns B, D, F, H, J have half
hexes at rows 0 and 10). The terrain is built so that the rule 7 examples
have a geometric equivalent on it:

- B1, stone, 4 hexes: C3, C4, C5, B5. C4 holds a sub-hex kite polygon on its
  right part, so the line C3 to B5 misses it (rule 7.7 example) and the line
  C3 to C5 crosses it.
- B4, stone, 3 hexes: E4, E5, E6 (multi-story, rule 7.5).
- B3, stone, 3 hexes: G6, H6, H7 (multi-story firer for rule 7.4).
- B2, wooden, 2 hexes: F8, G8 (a small building, rule 7.4).
- Woods: E2, E3, H4, D9, I8, I9.
- Wheat: I5, I6 (hindrance count).
- Shellhole: H3. Road: A5, A6.
- A wall on the hexside between F5 and F6 (rule 11.51).
- Sewer entrances at C5, E5, and G6 (rule 27.1).
"""

from __future__ import annotations

from slcore import geometry
from slcore.state import Board, Building, Hex, Polygon, TerrainType, default_polygons
from sldata.loaders import load_terrain

COLS = 10
ROWS = 10

B1 = Building("B1", "stone", 4)
B2 = Building("B2", "wooden", 2)
B3 = Building("B3", "stone", 3)
B4 = Building("B4", "stone", 3)

BUILDING_HEXES = {
    "C3": B1, "C4": B1, "C5": B1, "B5": B1,
    "E4": B4, "E5": B4, "E6": B4,
    "G6": B3, "H6": B3, "H7": B3,
    "F8": B2, "G8": B2,
}
WOODS = {"E2", "E3", "H4", "D9", "I8", "I9"}
WHEAT = {"I5", "I6"}
SHELLHOLE = {"H3"}
ROAD = {"A5", "A6"}
# Sewer entrances for rule 27. C5 and E5 are two hexes apart, and G6 is four from E5,
# so a move of rule 27.2 reaches one and a lost stack of rule 27.22 reaches all three.
SEWER = {"C5", "E5", "G6"}
WALLS = {("F5", 3)}


def build_fixture(terrain: dict[str, TerrainType] | None = None) -> Board:
    if terrain is None:
        terrain = load_terrain()
    wall_sides: dict[str, dict[int, str]] = {}
    for hid, d in WALLS:
        wall_sides.setdefault(hid, {})[d] = "wall"
        other = geometry.neighbor(*geometry.parse_hex_id(hid), d)
        wall_sides.setdefault(geometry.hex_id(*other), {})[(d + 3) % 6] = "wall"
    hexes = []
    for col in range(COLS):
        first = 0 if col & 1 else 1
        for row in range(first, ROWS + 1):
            hid = geometry.hex_id(col, row)
            kind = "open"
            building = None
            if hid in BUILDING_HEXES:
                building = BUILDING_HEXES[hid]
                kind = "stone_building" if building.kind == "stone" else "wooden_building"
            elif hid in WOODS:
                kind = "woods"
            elif hid in WHEAT:
                kind = "wheat"
            elif hid in SHELLHOLE:
                kind = "shellhole"
            polygons = default_polygons(col, row, kind, terrain)
            if hid == "C4":
                polygons = (Polygon.make(kind, [(5, 8), (7, 7), (8, 8), (7, 9)]),)
            sides: list[str | None] = [None] * 6
            for d, f in wall_sides.get(hid, {}).items():
                sides[d] = f
            hexes.append(
                Hex(
                    col=col,
                    row=row,
                    terrain=kind,
                    road=hid in ROAD,
                sewer=hid in SEWER,
                    building=building,
                    hexsides=tuple(sides),
                    polygons=polygons,
                )
            )
    return Board(COLS, ROWS, hexes, terrain, name="fixture-10x10")
