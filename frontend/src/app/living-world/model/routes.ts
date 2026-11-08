import { LOT_PITCH, PLAZA_RADIUS, type DistrictLayout, type Lot } from "./townLayout";

/**
 * Street routing for vehicles and couriers. Lots sit on a grid with a street between
 * every row and column, so a route is: out of the door onto the street, along it to the
 * district's outer street, round to the corner facing the plaza, then down the boulevard.
 * Pure, so a test can prove no route ever cuts through a building.
 */

export interface Point {
  x: number;
  z: number;
}

/** Unit vector of the lot's front (+Z rotated by rotationY), snapped to an axis. */
export function frontOf(lot: Lot): Point {
  return { x: Math.round(Math.sin(lot.rotationY)), z: Math.round(Math.cos(lot.rotationY)) };
}

/** Lot door → plaza edge. The last point sits on the plaza ring, not inside the buildings there. */
export function routeToPlaza(lot: Lot, d: DistrictLayout): Point[] {
  const f = frontOf(lot);
  const s: Point = { x: lot.x + (f.x * LOT_PITCH) / 2, z: lot.z + (f.z * LOT_PITCH) / 2 };
  const out: Point[] = [{ x: lot.x, z: lot.z }, s];
  if (f.x !== 0) {
    // Front faces ±X: the street in front runs along Z.
    out.push({ x: s.x, z: d.gateZ }, { x: d.gateX, z: d.gateZ });
  } else {
    out.push({ x: d.gateX, z: s.z }, { x: d.gateX, z: d.gateZ });
  }
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
