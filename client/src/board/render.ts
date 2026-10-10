// The board renderer (FR-30). Flat fills, hard edges, and no gradients. The client draws
// the polygons the host sends and applies no rule.
//
// The base tones are the ones of `src/slwindow/theme.py`, so the browser and the desktop
// window show one board. The window adds the cel shading of a lit face and a shaded face;
// the browser holds the base tone of each feature and no shading.

import type { BoardDocument, HexDocument, ViewDocument } from "../net/protocol";
import { Camera, hexCorners, latticeToScreen } from "./geometry";
import { drawConcealment, drawCounters } from "../counters/draw";

const FILLS: Record<string, string> = {
  open: "#9eb068",
  wheat: "#dec674",
  shellhole: "#96a868",
  woods: "#5c8044",
  wooden_building: "#804230",
  stone_building: "#b0825c",
};

// Rule 43.1: three levels of hills. Each level is a flat brown that takes the place of the
// ground, and the woods polygon or the building polygon of the hex draws on top of it. A
// wheatfield keeps its yellow on a hill, because rule 44.2 gives it the whole hex.
const HILL_FILLS = ["#c68e54", "#ac704c", "#8c5a44"];
const CREST = "#6e442c";
const HEXSIDE_COLORS: Record<string, string> = {
  wall: "#928c7a",
  hedge: "#4a6e3a",
  cliff: "#3a322a",
};

const WOODS_LINE = "#263e24";
const BUILDING_LINE: Record<string, string> = {
  wooden_building: "#3a1c12",
  stone_building: "#603e28",
};
// The roof tone the browser fills a building block with. It is a brown that reads as the
// lit roof of the window (the window adds a shaded face; the browser holds one tone).
const BUILDING_ROOF: Record<string, string> = {
  wooden_building: "#98543e",
  stone_building: "#c69a70",
};
// The building step from a hex centre to a neighbour centre, on the pixel lattice. A block
// reaches this far on a side that a joined hex covers, and pulls in on an open side so the
// footprint is about two thirds of the hex and the ground shows around it.
const BUILDING_INSET = 0.64;
// The lattice steps to the neighbour hexes the building block asks about, in the same order
// the core numbers the directions. A block joins the mass across a side these hexes cover.
const B_NORTH: [number, number] = [0, -2];
const B_SOUTH: [number, number] = [0, 2];
const B_WEST: [number, number][] = [
  [-3, -1],
  [-3, 1],
];
const B_EAST: [number, number][] = [
  [3, -1],
  [3, 1],
];
const PAPER = "#c6cdb0";
const ROAD_COLOR = "#d6c082";
const GRID = "#60684a";
// Rule 3.5 and rule 7.1: the centre dot that a line of sight threads to. FR-30 asks for
// it and item 1 of the board rubric scores it.
const CENTRE_DOT = "#f4efe0";
const LABEL = "#76805c";
const SELECT = "#ac3e2e";
const LOS_LINE = "rgba(172, 62, 46, 0.85)";

export interface RenderState {
  board: BoardDocument;
  view: ViewDocument | null;
  camera: Camera;
  selected: string | null;
  highlighted: Set<string>;
  losFrom: string | null;
  losTraced: string[];
  losClear: boolean | null;
  tabletop: boolean;
}

export function render(context: CanvasRenderingContext2D, state: RenderState): void {
  const { board, camera } = state;
  context.save();
  context.clearRect(0, 0, context.canvas.width, context.canvas.height);
  context.fillStyle = PAPER;
  context.fillRect(0, 0, context.canvas.width, context.canvas.height);

  for (const hex of board.hexes) {
    drawHexFill(context, hex, camera);
  }
  for (const hex of board.hexes) {
    if (hex.road) {
      drawRoad(context, hex, camera);
    }
  }
  for (const hex of board.hexes) {
    drawHexPolygons(context, hex, camera);
  }
  drawBuildings(context, board, camera);
  const levels = levelsByCentre(board.hexes);
  for (const hex of board.hexes) {
    drawCrestLines(context, hex, camera, levels);
  }
  for (const hex of board.hexes) {
    drawHexOutline(context, hex, camera);
    drawHexsides(context, hex, camera, board);
  }
  if (camera.scale > 7) {
    for (const hex of board.hexes) {
      drawLabel(context, hex, camera);
    }
  }
  drawHighlights(context, state);
  if (state.view) {
    drawCounters(context, state.board, state.view, camera);
    drawConcealment(context, state.board, state.view, camera);
  }
  drawLos(context, state);
  context.restore();
}

function pathHex(context: CanvasRenderingContext2D, hex: HexDocument, camera: Camera): void {
  const corners = hexCorners(hex.center);
  context.beginPath();
  corners.forEach(([x, y], index) => {
    const [px, py] = latticeToScreen(x, y, camera);
    if (index === 0) {
      context.moveTo(px, py);
    } else {
      context.lineTo(px, py);
    }
  });
  context.closePath();
}

function drawHexFill(context: CanvasRenderingContext2D, hex: HexDocument, camera: Camera): void {
  pathHex(context, hex, camera);
  const level = hex.elevation ?? 0;
  if (hex.terrain !== "wheat" && level > 0) {
    context.fillStyle = HILL_FILLS[Math.min(level, HILL_FILLS.length) - 1];
  } else {
    context.fillStyle = FILLS[hex.terrain] ?? FILLS.open;
  }
  context.fill();
}

// The hexsides of direction d, as the pair of corners the core documents in
// geometry.HEXSIDE_VERTICES. The renderer reads it for a crest line and for a wall.
const SIDE_CORNERS: [number, number][] = [
  [4, 5],
  [5, 0],
  [0, 1],
  [1, 2],
  [2, 3],
  [3, 4],
];

// The offsets of geometry.DIRECTIONS, on the same integer lattice the centres use. A step
// in direction d from a hex centre lands on the centre of the hex across hexside d, so the
// renderer finds a neighbour the way the core finds it and no label arithmetic is needed.
const STEPS: [number, number][] = [
  [0, -2],
  [3, -1],
  [3, 1],
  [0, 2],
  [-3, 1],
  [-3, -1],
];

export function levelsByCentre(hexes: HexDocument[]): Map<string, number> {
  return new Map(hexes.map((h) => [`${h.center[0]},${h.center[1]}`, h.elevation ?? 0] as const));
}

function drawCrestLines(
  context: CanvasRenderingContext2D,
  hex: HexDocument,
  camera: Camera,
  levels: Map<string, number>,
): void {
  // Rule 43.2: a crest line runs along every hexside where two levels meet. The line is
  // drawn once, by the higher hex, so two hexes do not paint over each other.
  const here = hex.elevation ?? 0;
  if (here === 0) {
    return;
  }
  const corners = hexCorners(hex.center);
  for (let d = 0; d < 6; d += 1) {
    const [dx, dy] = STEPS[d];
    const level = levels.get(`${hex.center[0] + dx},${hex.center[1] + dy}`);
    if (level !== undefined && level >= here) {
      continue;
    }
    const [a, b] = SIDE_CORNERS[d];
    const [ax, ay] = latticeToScreen(corners[a][0], corners[a][1], camera);
    const [bx, by] = latticeToScreen(corners[b][0], corners[b][1], camera);
    context.beginPath();
    context.moveTo(ax, ay);
    context.lineTo(bx, by);
    context.strokeStyle = CREST;
    context.lineWidth = Math.max(1, camera.scale * 0.09);
    context.stroke();
  }
}

function drawRoad(context: CanvasRenderingContext2D, hex: HexDocument, camera: Camera): void {
  const [cx, cy] = latticeToScreen(hex.center[0], hex.center[1], camera);
  context.beginPath();
  context.arc(cx, cy, Math.max(2, camera.scale * 0.5), 0, Math.PI * 2);
  context.fillStyle = ROAD_COLOR;
  context.fill();
}

function drawHexPolygons(context: CanvasRenderingContext2D, hex: HexDocument, camera: Camera): void {
  for (const polygon of hex.polygons) {
    if (polygon.points.length < 3) {
      continue;
    }
    // A building is drawn by drawBuildings as a small inset block, so its full-hex polygon
    // is not filled here. It would fill the whole hex and bleed past the hex boundary.
    if (polygon.kind.endsWith("building")) {
      continue;
    }
    context.beginPath();
    polygon.points.forEach(([x, y], index) => {
      const [px, py] = latticeToScreen(x, y, camera);
      if (index === 0) {
        context.moveTo(px, py);
      } else {
        context.lineTo(px, py);
      }
    });
    context.closePath();
    context.fillStyle = FILLS[polygon.kind] ?? FILLS.open;
    context.fill();
    if (polygon.kind === "woods") {
      context.strokeStyle = WOODS_LINE;
      context.lineWidth = 1;
      context.stroke();
    }
  }
}

function drawBuildings(context: CanvasRenderingContext2D, board: BoardDocument, camera: Camera): void {
  // Rules 7.4 and 7.5: a building is the plan of a structure and not a hexagon. Each hex of
  // the building is one small block. The block sits inside the hex, so the ground shows
  // around it. The block reaches out to a neighbour hex only when that hex holds the same
  // building, so several hexes of one building read as one connected mass and one hex reads
  // as a small house. This mirrors slwindow.render._buildings, so the window and the
  // browser draw one board.
  const byCentre = new Map(board.hexes.map((h) => [`${h.center[0]},${h.center[1]}`, h] as const));
  const joined = (hex: HexDocument, dx: number, dy: number): boolean => {
    const other = byCentre.get(`${hex.center[0] + dx},${hex.center[1] + dy}`);
    return other !== undefined && other.building?.id === hex.building?.id && hex.building !== undefined;
  };
  const anyJoined = (hex: HexDocument, steps: [number, number][]): boolean =>
    steps.some(([dx, dy]) => joined(hex, dx, dy));
  const reachX = camera.scale * 1.5;
  const reachY = camera.scale * Math.sqrt(3);
  for (const hex of board.hexes) {
    if (!hex.building || !hex.terrain.endsWith("building")) {
      continue;
    }
    const [cx, cy] = latticeToScreen(hex.center[0], hex.center[1], camera);
    const north = joined(hex, B_NORTH[0], B_NORTH[1]) ? reachY : reachY * BUILDING_INSET;
    const south = joined(hex, B_SOUTH[0], B_SOUTH[1]) ? reachY : reachY * BUILDING_INSET;
    const west = anyJoined(hex, B_WEST) ? reachX : reachX * BUILDING_INSET;
    const east = anyJoined(hex, B_EAST) ? reachX : reachX * BUILDING_INSET;
    const left = Math.round(cx - west);
    const top = Math.round(cy - north);
    const right = Math.round(cx + east);
    const bottom = Math.round(cy + south);
    context.fillStyle = BUILDING_ROOF[hex.terrain] ?? FILLS[hex.terrain] ?? FILLS.open;
    context.fillRect(left, top, right - left, bottom - top);
    // The outline goes on each side that faces open ground, so the line follows the outside
    // of one building and a shared side inside the mass carries none.
    context.strokeStyle = BUILDING_LINE[hex.terrain] ?? WOODS_LINE;
    context.lineWidth = 1;
    if (!joined(hex, B_NORTH[0], B_NORTH[1])) {
      line(context, left, top, right, top);
    }
    if (!joined(hex, B_SOUTH[0], B_SOUTH[1])) {
      line(context, left, bottom, right, bottom);
    }
    if (!anyJoined(hex, B_WEST)) {
      line(context, left, top, left, bottom);
    }
    if (!anyJoined(hex, B_EAST)) {
      line(context, right, top, right, bottom);
    }
  }
}

function line(context: CanvasRenderingContext2D, x1: number, y1: number, x2: number, y2: number): void {
  context.beginPath();
  context.moveTo(x1, y1);
  context.lineTo(x2, y2);
  context.stroke();
}

function drawHexOutline(context: CanvasRenderingContext2D, hex: HexDocument, camera: Camera): void {
  pathHex(context, hex, camera);
  context.strokeStyle = GRID;
  context.lineWidth = 1;
  context.stroke();
  const [cx, cy] = latticeToScreen(hex.center[0], hex.center[1], camera);
  context.beginPath();
  context.arc(cx, cy, Math.max(1, camera.scale * 0.09), 0, Math.PI * 2);
  context.fillStyle = CENTRE_DOT;
  context.fill();
}

function drawHexsides(context: CanvasRenderingContext2D, hex: HexDocument, camera: Camera, board: BoardDocument): void {
  if (!hex.hexsides) {
    return;
  }
  const corners = hexCorners(hex.center);
  for (const [key, feature] of Object.entries(hex.hexsides)) {
    const index = Number(key);
    const pair = SIDE_CORNERS[index];
    if (!pair) {
      continue;
    }
    const [a, b] = pair;
    const [ax, ay] = latticeToScreen(corners[a][0], corners[a][1], camera);
    const [bx, by] = latticeToScreen(corners[b][0], corners[b][1], camera);
    context.beginPath();
    context.moveTo(ax, ay);
    context.lineTo(bx, by);
    // Rule 44.1 tints a cliff hexside in black, and rule 11.5 gives a wall and a hedge.
    context.strokeStyle = HEXSIDE_COLORS[feature] ?? HEXSIDE_COLORS.hedge;
    context.lineWidth = Math.max(2, camera.scale * (feature === "cliff" ? 0.3 : 0.22));
    context.stroke();
  }
  void board;
}

function drawLabel(context: CanvasRenderingContext2D, hex: HexDocument, camera: Camera): void {
  const [cx, cy] = latticeToScreen(hex.center[0], hex.center[1] - 0.62, camera);
  context.fillStyle = LABEL;
  context.font = `${Math.max(7, Math.round(camera.scale * 0.42))}px "Trebuchet MS", sans-serif`;
  context.textAlign = "center";
  context.fillText(hex.id, cx, cy);
}

function drawHighlights(context: CanvasRenderingContext2D, state: RenderState): void {
  const byId = new Map(state.board.hexes.map((h) => [h.id, h] as const));
  for (const id of state.highlighted) {
    const hex = byId.get(id);
    if (!hex) {
      continue;
    }
    pathHex(context, hex, state.camera);
    context.fillStyle = "rgba(172, 62, 46, 0.20)";
    context.fill();
  }
  if (state.selected) {
    const hex = byId.get(state.selected);
    if (hex) {
      pathHex(context, hex, state.camera);
      context.strokeStyle = SELECT;
      context.lineWidth = 2.5;
      context.stroke();
    }
  }
}

function drawLos(context: CanvasRenderingContext2D, state: RenderState): void {
  if (state.tabletop || state.losTraced.length === 0 || state.losFrom === null) {
    return;
  }
  const byId = new Map(state.board.hexes.map((h) => [h.id, h] as const));
  const first = byId.get(state.losFrom);
  if (!first) {
    return;
  }
  const points = [first, ...state.losTraced.map((id) => byId.get(id)).filter((h): h is HexDocument => Boolean(h))];
  context.beginPath();
  points.forEach((hex, index) => {
    const [px, py] = latticeToScreen(hex.center[0], hex.center[1], state.camera);
    if (index === 0) {
      context.moveTo(px, py);
    } else {
      context.lineTo(px, py);
    }
  });
  context.strokeStyle = state.losClear === false ? "#5a5a5a" : LOS_LINE;
  context.lineWidth = 2;
  context.setLineDash(state.losClear === false ? [6, 4] : []);
  context.stroke();
  context.setLineDash([]);
}
