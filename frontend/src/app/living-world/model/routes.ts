import { LOT_PITCH, PLAZA_RADIUS, toWorld, type DistrictLayout, type Lot } from "./townLayout";

/**
 * Street routing for vehicles and couriers. A district is a street grid with a street
 * between every row and column, so a route is: out of the door onto the street, along it to
 * the grid's outer street, round to the corner facing the plaza, then down the boulevard.
 * The legs inside a district are axis-aligned in the district's own axes (the grid is
 * rotated in the world). Pure, so a test can prove no route ever cuts through a building.
 */

export interface Point {
  x: number;
  z: number;
}

/** Lot door → plaza edge. The last point sits on the plaza ring, not inside the buildings there. */
export function routeToPlaza(lot: Lot, d: DistrictLayout): Point[] {
  const s = { x: lot.lx + (lot.fx * LOT_PITCH) / 2, z: lot.lz + (lot.fz * LOT_PITCH) / 2 };
  const local: Point[] = [{ x: lot.lx, z: lot.lz }, s];
  if (lot.fx !== 0) {
    // Front faces ±X of the grid: the street in front runs along Z.
    local.push({ x: s.x, z: d.gateLZ }, { x: d.gateLX, z: d.gateLZ });
  } else {
    local.push({ x: d.gateLX, z: s.z }, { x: d.gateLX, z: d.gateLZ });
  }
  const out: Point[] = local.map((p) => toWorld(d, p.x, p.z));
  out[0] = { x: lot.x, z: lot.z };
  const len = Math.hypot(d.gateX, d.gateZ) || 1;
  const k = (PLAZA_RADIUS - 2) / len;
  out.push({ x: d.gateX * k, z: d.gateZ * k });
  return dedupe(out);
}

function dedupe(p: Point[]): Point[] {
  return p.filter((q, i) => i === 0 || Math.hypot(q.x - p[i - 1].x, q.z - p[i - 1].z) > 1e-6);
}

export function routeLength(p: readonly Point[]): number {
  let s = 0;
  for (let i = 1; i < p.length; i++) s += Math.hypot(p[i].x - p[i - 1].x, p[i].z - p[i - 1].z);
  return s;
}

/** Position `dist` along the polyline, clamped to its ends, plus the heading there. */
export function pointAlong(p: readonly Point[], dist: number): Point & { heading: number } {
  let left = Math.max(0, dist);
  for (let i = 1; i < p.length; i++) {
    const dx = p[i].x - p[i - 1].x;
    const dz = p[i].z - p[i - 1].z;
    const len = Math.hypot(dx, dz);
    if (left <= len || i === p.length - 1) {
      const t = len === 0 ? 1 : Math.min(1, left / len);
      return { x: p[i - 1].x + dx * t, z: p[i - 1].z + dz * t, heading: Math.atan2(dx, dz) };
    }
    left -= len;
  }
  return { x: p[0].x, z: p[0].z, heading: 0 };
}
