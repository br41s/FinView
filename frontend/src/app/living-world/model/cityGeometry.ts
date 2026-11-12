/**
 * Small planar-geometry helpers for the city (pure, convex polygons only).
 * Polygons are lists of {x, z}; "CCW" means positive `polyArea`, which is how the half-edge
 * face walker in `cityGraph.ts` emits every block.
 */

export interface V {
  x: number;
  z: number;
}

export function polyArea(poly: readonly V[]): number {
  let a = 0;
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i];
    const q = poly[(i + 1) % poly.length];
    a += p.x * q.z - q.x * p.z;
  }
  return a / 2;
}

export function polyCentroid(poly: readonly V[]): V {
  let ax = 0;
  let az = 0;
  let a2 = 0;
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i];
    const q = poly[(i + 1) % poly.length];
    const c = p.x * q.z - q.x * p.z;
    a2 += c;
    ax += (p.x + q.x) * c;
    az += (p.z + q.z) * c;
  }
  if (Math.abs(a2) < 1e-9) {
    const n = poly.length || 1;
    return { x: poly.reduce((s, p) => s + p.x, 0) / n, z: poly.reduce((s, p) => s + p.z, 0) / n };
  }
  return { x: ax / (3 * a2), z: az / (3 * a2) };
}

/** Sutherland-Hodgman against one half-plane: keeps the points with `nx*x + nz*z <= c`. */
export function clipHalfPlane(poly: readonly V[], nx: number, nz: number, c: number): V[] {
  const out: V[] = [];
  const side = (p: V) => nx * p.x + nz * p.z - c;
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i];
    const q = poly[(i + 1) % poly.length];
    const sp = side(p);
    const sq = side(q);
    if (sp <= 0) out.push(p);
    if ((sp < 0 && sq > 0) || (sp > 0 && sq < 0)) {
      const t = sp / (sp - sq);
      out.push({ x: p.x + (q.x - p.x) * t, z: p.z + (q.z - p.z) * t });
    }
  }
  return dropRepeats(out);
}

function dropRepeats(poly: V[]): V[] {
  return poly.filter((p, i) => {
    const q = poly[(i + 1) % poly.length];
    return Math.hypot(p.x - q.x, p.z - q.z) > 1e-7;
  });
}

export interface Obb {
  cx: number;
  cz: number;
  /** Unit axes and half-extents along them. */
  ux: number;
  uz: number;
  vx: number;
  vz: number;
  hu: number;
  hv: number;
}

/** Smallest-area oriented box that has one side along a polygon edge. */
export function orientedBox(poly: readonly V[]): Obb {
  let best: Obb | null = null;
  let bestArea = Infinity;
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i];
    const q = poly[(i + 1) % poly.length];
    const l = Math.hypot(q.x - p.x, q.z - p.z);
    if (l < 1e-9) continue;
    const ux = (q.x - p.x) / l;
    const uz = (q.z - p.z) / l;
    const vx = -uz;
    const vz = ux;
    let u0 = Infinity;
    let u1 = -Infinity;
    let v0 = Infinity;
    let v1 = -Infinity;
    for (const r of poly) {
      const u = r.x * ux + r.z * uz;
      const v = r.x * vx + r.z * vz;
      u0 = Math.min(u0, u);
      u1 = Math.max(u1, u);
      v0 = Math.min(v0, v);
      v1 = Math.max(v1, v);
    }
    const area = (u1 - u0) * (v1 - v0);
    if (area < bestArea - 1e-9) {
      bestArea = area;
      const cu = (u0 + u1) / 2;
      const cv = (v0 + v1) / 2;
      best = { cx: cu * ux + cv * vx, cz: cu * uz + cv * vz, ux, uz, vx, vz, hu: (u1 - u0) / 2, hv: (v1 - v0) / 2 };
    }
  }
  return best ?? { cx: 0, cz: 0, ux: 1, uz: 0, vx: 0, vz: 1, hu: 0, hv: 0 };
}

/** Closest point of segment a-b to p, with the parameter along it in [0, 1]. */
export function closestOnSegment(p: V, a: V, b: V): V & { t: number } {
  const dx = b.x - a.x;
  const dz = b.z - a.z;
  const l2 = dx * dx + dz * dz;
  const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.z - a.z) * dz) / l2));
  return { x: a.x + dx * t, z: a.z + dz * t, t };
}

export function distToSegment(p: V, a: V, b: V): number {
  const c = closestOnSegment(p, a, b);
  return Math.hypot(p.x - c.x, p.z - c.z);
}
