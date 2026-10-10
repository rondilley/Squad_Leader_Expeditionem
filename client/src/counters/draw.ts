// Counters drawn from data (FR-31). The values and their positions follow the 1977
// counters: firepower, range, and morale for a squad, and morale with the leadership
// modifier for a leader. The art is new: flat national color, ink border, no scan.

import type { BoardDocument, ConcealmentToken, UnitDocument, ViewDocument } from "../net/protocol";
import { Camera, latticeToScreen } from "../board/geometry";

// The tones of `src/slwindow/theme.py`. Each national colour is more saturated than the
// ground of the board, so a counter is the first thing the eye finds.
const NATIONAL: Record<string, string> = {
  german: "#6c7a8c",
  russian: "#ba9852",
  american: "#acbe4c",
};

const INK = "#24221a";
const WEAPON = "#3a4450";
const CONCEALED = "#e2dcca";
// Rule 28: a vehicle counter is wider than an infantry counter and it carries a gun.
const VEHICLE_EDGE = "#181612";
const WRECK = "#565046";
const IMMOBILE = "#c46830";
const SPINES: [number, number][] = [
  [2, 0],
  [1, 1],
  [-1, 1],
  [-2, 0],
  [-1, -1],
  [1, -1],
];
const ROOT_THREE_OVER_TWO = Math.sqrt(3) / 2;
const SMOKE = "rgba(226, 222, 212, 0.72)";
const CHARGE = "#a23e2e";

// The physical look of a counter (src/slwindow/theme.py). A counter is a die-cut cardboard
// chit: rounded corners, a pale cut edge that shows the cardboard core, a bevel from its
// thickness (the light is at the top), and wear at the corners. A broken unit is a counter
// turned to its reverse: a colour band of its side over a plainer back tone.
const CHIT_RADIUS = 0.16;
const CHIT_EDGE = "#d0c8b2";
const CHIT_SHADOW = "rgba(26, 24, 18, 0.38)";
const CHIT_WEAR = "#d8d0bc";
const BACK = "#968e78";
const CHIT_BEVEL_LIGHT = 46;
const CHIT_BEVEL_DARK = 42;

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

/** Lighten (amount > 0) or darken (amount < 0) a hex colour, clamped to the byte range. */
function shade(hex: string, amount: number): string {
  const [r, g, b] = hexToRgb(hex);
  const c = (v: number) => Math.max(0, Math.min(255, v + amount));
  return `rgb(${c(r)}, ${c(g)}, ${c(b)})`;
}

/** A stable seed from a string (FNV-1a); the built-in string hash is not stable. */
function strSeed(text: string): number {
  let h = 2166136261;
  for (let i = 0; i < text.length; i += 1) {
    h = Math.imul(h ^ text.charCodeAt(i), 16777619) >>> 0;
  }
  return h >>> 0;
}

function roundRectPath(context: CanvasRenderingContext2D, x: number, y: number, w: number, h: number, r: number): void {
  const radius = Math.max(0, Math.min(r, w / 2, h / 2));
  context.beginPath();
  context.moveTo(x + radius, y);
  context.arcTo(x + w, y, x + w, y + h, radius);
  context.arcTo(x + w, y + h, x, y + h, radius);
  context.arcTo(x, y + h, x, y, radius);
  context.arcTo(x, y, x + w, y, radius);
  context.closePath();
}

/** The corner nicks of one counter, from its seed and not from a random number (SR-07). */
function wearMarks(seed: number, x: number, y: number, w: number, h: number, size: number): [number, number, number][] {
  const s = (Math.imul(seed >>> 0, 2654435761) + 1013904223) >>> 0;
  const inset = size * 0.16;
  const corners: [number, number][] = [
    [x + inset, y + inset],
    [x + w - inset, y + inset],
    [x + inset, y + h - inset],
    [x + w - inset, y + h - inset],
  ];
  const marks: [number, number, number][] = [];
  corners.forEach(([px, py], i) => {
    const bits = (s >> (i * 4)) & 0xf;
    if (bits < 5) {
      marks.push([px, py, Math.max(1, Math.round(size * (0.05 + 0.02 * (bits % 3))))]);
    }
  });
  return marks;
}

/** One die-cut cardboard chit: shadow, cut edge, printed face, bevel, and corner wear. */
function drawChit(
  context: CanvasRenderingContext2D,
  cx: number,
  cy: number,
  size: number,
  base: string,
  seed: number,
  options: { flipped?: boolean; nationality?: string; outline?: string; edgeWidth?: number } = {},
): void {
  const { flipped = false, nationality, outline = INK, edgeWidth = 2 } = options;
  const radius = Math.max(2, size * CHIT_RADIUS);
  const x = Math.round(cx - size / 2);
  const y = Math.round(cy - size / 2);
  const w = Math.round(size);
  const h = Math.round(size);
  const offset = Math.max(1, Math.round(size * 0.08));
  context.fillStyle = CHIT_SHADOW;
  roundRectPath(context, x + offset, y + offset, w, h, radius);
  context.fill();
  context.fillStyle = CHIT_EDGE;
  roundRectPath(context, x, y, w, h, radius);
  context.fill();
  const fx = x + edgeWidth;
  const fy = y + edgeWidth;
  const fw = w - edgeWidth * 2;
  const fh = h - edgeWidth * 2;
  const fr = Math.max(1, radius - edgeWidth);
  const faceBase = flipped ? BACK : base;
  context.fillStyle = faceBase;
  roundRectPath(context, fx, fy, fw, fh, fr);
  context.fill();
  if (flipped && nationality && fh >= 12) {
    context.save();
    roundRectPath(context, fx, fy, fw, fh, fr);
    context.clip();
    context.fillStyle = NATIONAL[nationality] ?? NATIONAL.german;
    context.fillRect(fx, fy, fw, Math.max(3, fh * 0.3));
    context.restore();
  }
  if (size >= 12) {
    context.lineWidth = 1;
    context.strokeStyle = shade(faceBase, CHIT_BEVEL_LIGHT);
    context.beginPath();
    context.moveTo(fx + fr, fy + 1);
    context.lineTo(fx + fw - fr, fy + 1);
    context.moveTo(fx + 1, fy + fr);
    context.lineTo(fx + 1, fy + fh - fr);
    context.stroke();
    context.strokeStyle = shade(faceBase, -CHIT_BEVEL_DARK);
    context.beginPath();
    context.moveTo(fx + fr, fy + fh - 1);
    context.lineTo(fx + fw - fr, fy + fh - 1);
    context.moveTo(fx + fw - 1, fy + fr);
    context.lineTo(fx + fw - 1, fy + fh - fr);
    context.stroke();
    context.fillStyle = CHIT_WEAR;
    for (const [px, py, worn] of wearMarks(seed, fx, fy, fw, fh, size)) {
      context.beginPath();
      context.arc(px, py, worn, 0, Math.PI * 2);
      context.fill();
    }
  }
  context.strokeStyle = outline;
  context.lineWidth = 1;
  roundRectPath(context, x, y, w, h, radius);
  context.stroke();
}

export function drawCounters(
  context: CanvasRenderingContext2D,
  board: BoardDocument,
  view: ViewDocument,
  camera: Camera,
): void {
  const centers = new Map(board.hexes.map((h) => [h.id, h.center] as const));
  const stacks = new Map<string, UnitDocument[]>();
  for (const unit of view.units) {
    if (unit.hex === null || unit.carrier !== null) {
      continue;
    }
    const list = stacks.get(unit.hex) ?? [];
    list.push(unit);
    stacks.set(unit.hex, list);
  }
  const size = Math.max(10, camera.scale * 1.45);
  drawSmoke(context, centers, view, camera, size);
  for (const [hexId, units] of stacks) {
    const center = centers.get(hexId);
    if (!center) {
      continue;
    }
    const [cx, cy] = latticeToScreen(center[0], center[1], camera);
    units.sort((a, b) => a.id - b.id);
    units.forEach((unit, index) => {
      const step = size * 0.18;
      drawCounter(context, unit, cx - step * (units.length - 1) / 2 + step * index, cy + step * index * 0.6, size, view);
    });
  }
}

/** Rule 24: a smoke counter covers its hex and hides nothing. */
function drawSmoke(
  context: CanvasRenderingContext2D,
  centers: Map<string, [number, number]>,
  view: ViewDocument,
  camera: Camera,
  size: number,
): void {
  for (const hexId of view.smoke) {
    const center = centers.get(hexId);
    if (!center) {
      continue;
    }
    const [cx, cy] = latticeToScreen(center[0], center[1], camera);
    context.fillStyle = SMOKE;
    context.beginPath();
    context.arc(cx, cy, size * 0.62, 0, Math.PI * 2);
    context.fill();
  }
}

/**
 * Rule 25.2: a concealment counter of the other side is a token and nothing else. The
 * client draws what the host sent, so a dummy stack looks like a full one (rule 25.7).
 */
export function drawConcealment(
  context: CanvasRenderingContext2D,
  board: BoardDocument,
  view: ViewDocument,
  camera: Camera,
): void {
  const centers = new Map(board.hexes.map((h) => [h.id, h.center] as const));
  const size = Math.max(10, camera.scale * 1.45);
  const byHex = new Map<string, ConcealmentToken[]>();
  for (const token of view.concealment) {
    const list = byHex.get(token.hex) ?? [];
    list.push(token);
    byHex.set(token.hex, list);
  }
  for (const [hexId, tokens] of byHex) {
    const center = centers.get(hexId);
    if (!center) {
      continue;
    }
    const [cx, cy] = latticeToScreen(center[0], center[1], camera);
    const half = size / 2;
    const lift = tokens[0].own ? -size * 0.55 : 0;
    drawChit(context, cx, cy + lift, size * 0.94, CONCEALED, strSeed(hexId) ^ (tokens[0].own ? 1 : 0), { edgeWidth: 1 });
    if (size >= 16) {
      context.fillStyle = INK;
      context.textAlign = "center";
      context.font = `${Math.round(size * 0.5)}px "Trebuchet MS", sans-serif`;
      context.fillText("?", cx, cy + size * 0.18 + lift);
      if (tokens.length > 1) {
        context.font = `${Math.round(size * 0.22)}px "Trebuchet MS", sans-serif`;
        context.fillText(String(tokens.length), cx + half * 0.6, cy - half * 0.5 + lift);
      }
    }
  }
  for (const charge of view.demo) {
    const center = centers.get(charge.hex);
    if (!center) {
      continue;
    }
    const [cx, cy] = latticeToScreen(center[0], center[1], camera);
    context.strokeStyle = CHARGE;
    context.lineWidth = 2;
    context.beginPath();
    context.arc(cx, cy, size * 0.3, 0, Math.PI * 2);
    context.stroke();
  }
}

function drawCounter(
  context: CanvasRenderingContext2D,
  unit: UnitDocument,
  cx: number,
  cy: number,
  size: number,
  view: ViewDocument,
): void {
  const vehicle = unit.kind === "vehicle";
  const chitSize = vehicle ? size * 1.15 : size;
  const half = chitSize / 2;
  const weapon = unit.kind === "sw";
  const base = weapon ? WEAPON : unit.wreck ? WRECK : (NATIONAL[unit.nationality] ?? "#b0a894");
  drawChit(context, cx, cy, chitSize, base, unit.id, {
    flipped: !vehicle && unit.broken,
    nationality: unit.nationality,
    outline: vehicle ? VEHICLE_EDGE : INK,
    edgeWidth: 2,
  });
  if (vehicle) {
    drawVehicleMarks(context, unit, cx, cy, half);
    if (unit.wreck) {
      return;
    }
  }
  if (unit.player === view.active) {
    context.strokeStyle = "rgba(244, 239, 224, 0.9)";
    context.lineWidth = 1;
    context.strokeRect(cx - half + 2, cy - half + 2, size - 4, size - 4);
  }
  if (size < 16) {
    return;
  }
  context.fillStyle = "#f4efe0";
  context.textAlign = "center";
  context.font = `${Math.round(size * 0.3)}px "Trebuchet MS", sans-serif`;
  const label = counterLabel(unit);
  context.fillText(label, cx, cy + size * 0.12);
  if (unit.kind === "leader" && unit.name) {
    context.font = `${Math.round(size * 0.2)}px "Trebuchet MS", sans-serif`;
    context.fillText(unit.name.slice(0, 9), cx, cy - size * 0.22);
  }
  const marks: string[] = [];
  if (unit.prep_fired) {
    marks.push("P");
  }
  if (unit.moved) {
    marks.push("M");
  }
  if (unit.dm) {
    marks.push("DM");
  }
  if (unit.berserk) {
    marks.push("B");
  }
  if (unit.malfunction) {
    marks.push("X");
  }
  if (marks.length > 0) {
    context.fillStyle = "#f2d7a0";
    context.font = `${Math.round(size * 0.2)}px "Trebuchet MS", sans-serif`;
    context.fillText(marks.join(""), cx, cy + size * 0.42);
  }
}

/**
 * Rule 29.4: the gun barrel lies along the spine the vehicle faces, and rule 39 marks a
 * vehicle that cannot move.
 */
function drawVehicleMarks(
  context: CanvasRenderingContext2D,
  unit: UnitDocument,
  cx: number,
  cy: number,
  half: number,
): void {
  if (unit.wreck) {
    context.strokeStyle = INK;
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(cx - half, cy - half);
    context.lineTo(cx + half, cy + half);
    context.moveTo(cx + half, cy - half);
    context.lineTo(cx - half, cy + half);
    context.stroke();
    return;
  }
  const facing = unit.facing ?? -1;
  if (facing >= 0) {
    const [ox, oy] = SPINES[facing % 6];
    const y = oy * ROOT_THREE_OVER_TWO;
    const length = Math.hypot(ox, y) || 1;
    context.strokeStyle = VEHICLE_EDGE;
    context.lineWidth = Math.max(2, half * 0.24);
    context.beginPath();
    context.moveTo(cx, cy);
    context.lineTo(cx + (ox / length) * half * 1.44, cy + (y / length) * half * 1.44);
    context.stroke();
  }
  if (unit.immobilized) {
    context.strokeStyle = IMMOBILE;
    context.lineWidth = 3;
    context.strokeRect(cx - half, cy - half, half * 2, half * 2);
  }
}

/** Firepower, range, and morale for a squad. Morale and the modifier for a leader. */
function counterLabel(unit: UnitDocument): string {
  if (unit.kind === "sw") {
    return unit.type;
  }
  if (unit.kind === "vehicle") {
    return `${unit.movement_points ?? 0}/${unit.gun ?? 0}`;
  }
  if (unit.kind === "leader") {
    const sign = unit.leadership > 0 ? "+" : "";
    return `${unit.morale}${sign}${unit.leadership}`;
  }
  return `${unit.firepower}-${unit.range}-${unit.morale}`;
}
