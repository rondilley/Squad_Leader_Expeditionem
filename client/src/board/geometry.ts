// Hex hit testing and the lattice to screen transform (FR-32).
//
// The core sends each hex center and each terrain polygon on the exact lattice, where
// x is an integer and y is an integer in units of the square root of three. The client
// multiplies y by that constant one time to draw. It calculates no rule.

import type { BoardDocument, HexDocument } from "../net/protocol";

export const ROOT_THREE = Math.sqrt(3);
export const HEX_SIDE = 2;

export interface Camera {
  scale: number;
  offsetX: number;
  offsetY: number;
}

export function latticeToScreen(x: number, y: number, camera: Camera): [number, number] {
  return [x * camera.scale + camera.offsetX, y * ROOT_THREE * camera.scale + camera.offsetY];
}

export function screenToLattice(px: number, py: number, camera: Camera): [number, number] {
  return [(px - camera.offsetX) / camera.scale, (py - camera.offsetY) / (camera.scale * ROOT_THREE)];
}

export function hexCorners(center: [number, number]): [number, number][] {
  const [cx, cy] = center;
  return [
    [cx + 2, cy],
    [cx + 1, cy + 1],
    [cx - 1, cy + 1],
    [cx - 2, cy],
    [cx - 1, cy - 1],
    [cx + 1, cy - 1],
  ];
}

export function boardExtent(board: BoardDocument): { minX: number; minY: number; maxX: number; maxY: number } {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const hex of board.hexes) {
    for (const [x, y] of hexCorners(hex.center)) {
      minX = Math.min(minX, x);
      maxX = Math.max(maxX, x);
      minY = Math.min(minY, y * ROOT_THREE);
      maxY = Math.max(maxY, y * ROOT_THREE);
    }
  }
  return { minX, minY, maxX, maxY };
}

export function fitCamera(board: BoardDocument, width: number, height: number, margin = 16): Camera {
  const extent = boardExtent(board);
  const scaleX = (width - margin * 2) / (extent.maxX - extent.minX);
  const scaleY = (height - margin * 2) / (extent.maxY - extent.minY);
  const scale = Math.min(scaleX, scaleY);
  return {
    scale,
    offsetX: margin - extent.minX * scale,
    offsetY: margin - extent.minY * scale,
  };
}

/** The hex whose center is nearest the point, when the point is inside that hex. */
export function hexAt(board: BoardDocument, px: number, py: number, camera: Camera): HexDocument | null {
  const [lx, ly] = screenToLattice(px, py, camera);
  let best: HexDocument | null = null;
  let bestDistance = Infinity;
  for (const hex of board.hexes) {
    const dx = lx - hex.center[0];
    const dy = (ly - hex.center[1]) * ROOT_THREE;
    const distance = dx * dx + dy * dy;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = hex;
    }
  }
  if (best === null) {
    return null;
  }
  return pointInHex(lx, ly, best.center) ? best : null;
}

/** A point is in a flat-topped hex of side 2 when it is inside the six half planes. */
export function pointInHex(lx: number, ly: number, center: [number, number]): boolean {
  const dx = lx - center[0];
  const dy = (ly - center[1]) * ROOT_THREE;
  if (Math.abs(dx) > 2 + 1e-9) {
    return false;
  }
  if (Math.abs(dy) > ROOT_THREE + 1e-9) {
    return false;
  }
  return Math.abs(dy) <= ROOT_THREE * (2 - Math.abs(dx)) + 1e-9 || Math.abs(dx) <= 1 + 1e-9;
}
