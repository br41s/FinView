import * as THREE from "three";
import { FACADE_ROWS, FLOOR_H, type Crown, type Plan } from "../model/towerSpec";
import type { Builder } from "./buildingFactory";

/**
 * Geometry generators for the holdings' towers: floor-by-floor lofts (twist, taper, setbacks),
 * lathe-style bodies (the egg, a cooling tower, a dome), lattice masts and crowns. Everything is
 * added to a `Builder`, so a whole site stays ONE merged mesh with vertex colours.
 *
 * Facade contract (see `materials.ts`): glass is `Builder.kind = 1` (or 3 with a diagrid) and the
 * window grid is read from local position (rows) and from `aArc` (columns round a curved shell:
 * a whole number of window columns per ring, so the pattern closes without a seam). A storey is
 * `FLOOR_H` = 1 / FACADE_ROWS tall, so glass volumes should stand on `k * FLOOR_H`.
 */

export const WHITE = 0xfaf7f0;
export const GREY = 0xb9c0c8;
export const DARK = 0x353c47;
export const DECK = 0xf3ede0;
export const GOLD = 0xf0b938;
/** Window columns per local unit round a shell: the same as the rows, so windows come out square. */
export const SITE_COLS = FACADE_ROWS;

export type V2 = readonly [number, number];
interface Chain {
  pts: V2[];
}

/** The outline of a plan, as chains of points: each smooth run is one chain, each flat side its own. */
export function planChains(plan: Plan, w: number, d: number): Chain[] {
  const hw = w / 2;
  const hd = d / 2;
  if (plan === "rect") {
    const c: V2[] = [[-hw, -hd], [hw, -hd], [hw, hd], [-hw, hd]];
    return c.map((p, i) => ({ pts: [p, c[(i + 1) % 4]] }));
  }
  if (plan === "hex") {
    const c: V2[] = Array.from({ length: 6 }, (_, i) => [Math.cos((i / 6) * Math.PI * 2 + Math.PI / 6) * hw, Math.sin((i / 6) * Math.PI * 2 + Math.PI / 6) * hd] as const);
    return c.map((p, i) => ({ pts: [p, c[(i + 1) % 6]] }));
  }
  const pts: V2[] = [];
  if (plan === "rounded") {
    const r = Math.min(hw, hd) * 0.55;
    const corners: V2[] = [[hw - r, hd - r], [-(hw - r), hd - r], [-(hw - r), -(hd - r)], [hw - r, -(hd - r)]];
    corners.forEach(([cx, cz], q) => {
      for (let k = 0; k <= 3; k++) {
        const a = (q + k / 3) * (Math.PI / 2);
        pts.push([cx + Math.cos(a) * r, cz + Math.sin(a) * r]);
      }
    });
  } else {
    const N = 20;
    const e = plan === "super" ? 2 / 3.2 : 1;
    for (let i = 0; i < N; i++) {
      const a = (i / N) * Math.PI * 2;
      const cs = Math.cos(a);
      const sn = Math.sin(a);
      pts.push([Math.sign(cs) * Math.pow(Math.abs(cs), e) * hw, Math.sign(sn) * Math.pow(Math.abs(sn), e) * hd]);
    }
  }
  pts.push(pts[0]);
  return [{ pts }];
}

export interface LoftOpts {
  plan: Plan;
  w: number;
  d: number;
  cx: number;
  cz: number;
  y0: number;
  h: number;
  hex: number;
  /** Intervals along the height (rings = segs + 1). Straight or linearly tapered shafts need 1. */
  segs?: number;
  /** 0..1 sample positions along the height; overrides `segs`. */
  ts?: number[];
  /** Scale of the plan at t (default 1). */
  scale?: (t: number) => number;
  /** Rotation of the plan at t, radians (default 0). */
  twist?: (t: number) => number;
  /** Height at t as a share of `h` (default t); lets a dome be a lathe. */
  yAt?: (t: number) => number;
  rot?: number;
  /** 1 glass, 3 glass with diagrid, 0 wall, 2 accent. */
  kind?: 0 | 1 | 2 | 3;
  /** A flat top; its colour. */
  cap?: number;
  capKind?: 0 | 1 | 2;
  /** Round the number of window columns of a ring to a multiple of this (diagrid period). */
  colMultiple?: number;
  /** Faces point inwards (the inner wall of a bowl). */
  inward?: boolean;
}

/** A shell lofted floor by floor from a plan. Returns the y of its top. */
export function loft(b: Builder, o: LoftOpts): number {
  const chains = planChains(o.plan, o.w, o.d);
  const ts = o.ts ?? Array.from({ length: (o.segs ?? 1) + 1 }, (_, j) => j / (o.segs ?? 1));
  const scale = o.scale ?? (() => 1);
  const twist = o.twist ?? (() => 0);
  const yAt = o.yAt ?? ((t: number) => t);
  const mult = o.colMultiple ?? 1;
  const rot = o.rot ?? 0;
  const at = (x: number, z: number, t: number): [number, number, number] => {
    const s = scale(t);
    const a = rot + twist(t);
    const ca = Math.cos(a);
    const sa = Math.sin(a);
    const px = x * s;
    const pz = z * s;
    return [o.cx + px * ca + pz * sa, o.y0 + yAt(t) * o.h, o.cz - px * sa + pz * ca];
  };
  const saved = b.kind;
  b.kind = o.kind ?? 1;
  const R = ts.length;
  for (const ch of chains) {
    const P = ch.pts.length;
    const cum = [0];
    for (let i = 1; i < P; i++) cum.push(cum[i - 1] + Math.hypot(ch.pts[i][0] - ch.pts[i - 1][0], ch.pts[i][1] - ch.pts[i - 1][1]));
    const L = cum[P - 1];
    const ncols = Math.max(mult, Math.round((L * SITE_COLS) / mult) * mult);
    const pos = new Float32Array(P * R * 3);
    const arc = new Float32Array(P * R);
    for (let j = 0; j < R; j++) {
      for (let i = 0; i < P; i++) {
        const [x, y, z] = at(ch.pts[i][0], ch.pts[i][1], ts[j]);
        pos.set([x, y, z], (j * P + i) * 3);
        arc[j * P + i] = ((cum[i] / L) * ncols) / SITE_COLS;
      }
    }
    const idx: number[] = [];
    for (let j = 0; j < R - 1; j++) {
      for (let i = 0; i < P - 1; i++) {
        const a = j * P + i;
        idx.push(a, a + P, a + 1, a + 1, a + P, a + P + 1);
      }
    }
    // Wind the first quad so its normal points away from the axis; the rest of the chain follows.
    const A = new THREE.Vector3().fromArray(pos, 0);
    const Bv = new THREE.Vector3().fromArray(pos, 3);
    const C = new THREE.Vector3().fromArray(pos, P * 3);
    const nrm = new THREE.Vector3().subVectors(C, A).cross(new THREE.Vector3().subVectors(Bv, A));
    const out = (A.x + Bv.x) / 2 - o.cx;
    const outz = (A.z + Bv.z) / 2 - o.cz;
    let flip = nrm.x * out + nrm.z * outz < 0;
    if (o.inward) flip = !flip;
    if (flip) for (let k = 0; k < idx.length; k += 3) [idx[k + 1], idx[k + 2]] = [idx[k + 2], idx[k + 1]];
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aArc", new THREE.BufferAttribute(arc, 1));
    g.setIndex(idx);
    g.computeVertexNormals();
    b.custom(g, o.hex);
  }
  if (o.cap !== undefined) {
    b.kind = o.capKind ?? 2;
    const top = ts[R - 1];
    const ring: Array<[number, number, number]> = [];
    for (const ch of chains) for (let i = 0; i < ch.pts.length - 1; i++) ring.push(at(ch.pts[i][0], ch.pts[i][1], top));
    const centre = at(0, 0, top);
    const pos = new Float32Array((ring.length + 1) * 3);
    pos.set(centre, 0);
    ring.forEach((p, i) => pos.set(p, (i + 1) * 3));
    const nor = new Float32Array((ring.length + 1) * 3);
    for (let i = 0; i <= ring.length; i++) nor[i * 3 + 1] = 1;
    const idx: number[] = [];
    for (let i = 0; i < ring.length; i++) {
      const a = 1 + i;
      const c = 1 + ((i + 1) % ring.length);
      // Up-facing: (a - centre) x (c - centre) must have positive y.
      const cross = (ring[i][2] - centre[2]) * (ring[(i + 1) % ring.length][0] - centre[0]) - (ring[i][0] - centre[0]) * (ring[(i + 1) % ring.length][2] - centre[2]);
      idx.push(0, ...(cross > 0 ? [a, c] : [c, a]));
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
    g.setIndex(idx);
    b.custom(g, o.cap);
  }
  b.kind = saved;
  return o.y0 + yAt(ts[R - 1]) * o.h;
}

/** A thin square bar between two points (lattice members, blades, struts). */
export function bar(b: Builder, a: readonly [number, number, number], c: readonly [number, number, number], t: number, hex: number) {
  const dir = new THREE.Vector3(c[0] - a[0], c[1] - a[1], c[2] - a[2]);
  const len = dir.length();
  if (len < 1e-6) return;
  const g = new THREE.BoxGeometry(t, len, t);
  g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0, 1, 0), dir.normalize()));
  g.translate((a[0] + c[0]) / 2, (a[1] + c[1]) / 2, (a[2] + c[2]) / 2);
  b.custom(g, hex);
}

/** A cylinder lying along x (`axis` "x") or z, `y` is its centre height. */
export function hcyl(b: Builder, r: number, len: number, x: number, y: number, z: number, hex: number, axis: "x" | "z" = "x", seg = 8) {
  const g = new THREE.CylinderGeometry(r, r, len, seg);
  if (axis === "x") g.rotateZ(Math.PI / 2);
  else g.rotateX(Math.PI / 2);
  g.translate(x, y, z);
  b.custom(g, hex);
}

/** A tiny tree: trunk + a rounded crown. */
export function tree(b: Builder, x: number, y: number, z: number, s: number, hex = 0x3ea65a) {
  b.kind = 0;
  b.box(s * 0.12, s * 0.5, s * 0.12, x, y, z, 0x8a6a4a);
  b.ico(s * 0.36, x, y + s * 0.7, z, hex, 0);
}

export const BASE_Y = FLOOR_H;

/** A square tapering pinnacle: stacked cones ending in a needle. */
function pinnacle(b: Builder, x: number, y: number, z: number, r: number, len: number, accent: number) {
  b.kind = 2;
  b.cyl(r * 0.55, r * 0.8, len * 0.22, x, y, z, accent, 8);
  b.cyl(r * 0.3, r * 0.5, len * 0.2, x, y + len * 0.22, z, WHITE, 8);
  b.kind = 0;
  b.cyl(0.02, r * 0.18, len * 0.58, x, y + len * 0.42, z, WHITE, 5);
  b.ico(Math.max(0.05, r * 0.14), x, y + len, z, accent, 0);
}

/** A helipad on a green ring, `H` marked. */
export function helipadRing(b: Builder, x: number, y: number, z: number, R: number, ring: number) {
  b.kind = 2;
  b.cyl(R, R, 0.16, x, y, z, ring, 16);
  b.kind = 0;
  b.cyl(R * 0.84, R * 0.84, 0.19, x, y, z, 0x2a2f38, 16);
  b.cyl(R * 0.56, R * 0.56, 0.2, x, y, z, 0xf0c030, 14);
  b.cyl(R * 0.5, R * 0.5, 0.21, x, y, z, 0x2a2f38, 14);
  const t = R * 0.12;
  b.box(t, 0.22, R * 0.62, x - R * 0.17, y, z, WHITE);
  b.box(t, 0.22, R * 0.62, x + R * 0.17, y, z, WHITE);
  b.box(R * 0.46, 0.22, t, x, y, z, WHITE);
}

/** The crown of a shaft that ends at `y` with a roof of radius `r`. Returns the new top. */
export function crown(b: Builder, kind: Crown, x: number, y: number, z: number, r: number, len: number, accent: number): number {
  switch (kind) {
    case "helipad":
      helipadRing(b, x, y, z, r * 0.96, 0x3fb84a);
      return y + 0.24;
    case "spire":
      b.kind = 2;
      b.cyl(r * 0.05, r * 0.2, len * 0.34, x, y, z, accent, 8);
      b.kind = 0;
      b.cyl(0.02, r * 0.05, len * 0.66, x, y + len * 0.34, z, WHITE, 5);
      return y + len;
    case "antenna":
      b.kind = 0;
      b.cyl(0.025, 0.05, len, x, y, z, WHITE, 5);
      b.ico(0.09, x, y + len, z, 0xff4b4b, 0);
      b.cyl(0.03, 0.03, 0.04, x, y + len * 0.55, z, GREY, 5);
      for (let i = 0; i < 4; i++) bar(b, [x, y + len * 0.5 + i * len * 0.12, z - 0.14], [x, y + len * 0.5 + i * len * 0.12, z + 0.14], 0.03, WHITE);
      return y + len + 0.09;
    case "pinnacle":
      pinnacle(b, x, y, z, r, len, accent);
      return y + len;
    case "dome":
      loft(b, { plan: "ellipse", w: r * 1.8, d: r * 1.8, cx: x, cz: z, y0: y, h: len * 0.5, hex: accent, kind: 2, ts: [0, 0.35, 0.65, 0.88, 1], scale: (t) => Math.max(0.04, Math.cos(t * Math.PI * 0.5)), yAt: (t) => Math.sin(t * Math.PI * 0.5) });
      return y + len * 0.5;
    default:
      b.kind = 2;
      b.box(r * 1.3, 0.1, r * 1.3, x, y, z, accent);
      b.kind = 0;
      return y + 0.1;
  }
}

/** Share of the height the crown takes. */
export const CROWN_SHARE: Record<Crown, number> = { flat: 0.02, helipad: 0.04, spire: 0.14, antenna: 0.1, pinnacle: 0.12, dome: 0.06 };

/** An Eiffel-like lattice tower: four curved legs, ring beams, X braces, platforms and an antenna. */
export function latticeMast(b: Builder, x: number, y0: number, z: number, w: number, h: number, accent: number, opts: { levels?: number; braces?: boolean; thick?: number } = {}) {
  const levels = opts.levels ?? 5;
  const th = opts.thick ?? Math.max(0.045, w * 0.04);
  const half = (t: number) => (w / 2) * (0.1 + 0.9 * Math.pow(1 - t, 1.7));
  const ys = Array.from({ length: levels + 1 }, (_, i) => y0 + (i / levels) * h * 0.86);
  const corner = (t: number, i: number): [number, number] => [(i & 1 ? 1 : -1) * half(t), (i & 2 ? 1 : -1) * half(t)];
  b.kind = 0;
  for (let l = 0; l < levels; l++) {
    const t0 = l / levels;
    const t1 = (l + 1) / levels;
    for (let i = 0; i < 4; i++) {
      const [a0, c0] = corner(t0, i);
      const [a1, c1] = corner(t1, i);
      bar(b, [x + a0, ys[l], z + c0], [x + a1, ys[l + 1], z + c1], th * (1.5 - t0), accent);
    }
    if (opts.braces !== false && l < levels - 1) {
      for (const [i, j] of [[0, 1], [1, 3], [3, 2], [2, 0]] as const) {
        const [a0, c0] = corner(t0, i);
        const [a1, c1] = corner(t1, j);
        bar(b, [x + a0, ys[l], z + c0], [x + a1, ys[l + 1], z + c1], th * 0.6, WHITE);
      }
    }
    if (l > 0) {
      for (let i = 0; i < 4; i++) {
        const [a0, c0] = corner(t0, i);
        const [a1, c1] = corner(t0, [1, 3, 0, 2][i]);
        bar(b, [x + a0, ys[l], z + c0], [x + a1, ys[l], z + c1], th * 0.7, WHITE);
      }
    }
  }
  // Two observation platforms and the antenna.
  for (const t of [0.34, 0.66]) {
    const hw = half(t) * 1.5 + 0.05;
    b.box(hw * 2, 0.07, hw * 2, x, y0 + t * h * 0.86, z, accent);
    b.box(hw * 1.7, 0.18, hw * 1.7, x, y0 + t * h * 0.86 + 0.07, z, DARK);
  }
  b.cyl(0.03, 0.06, h * 0.14, x, y0 + h * 0.86, z, WHITE, 5);
  b.ico(0.1, x, y0 + h, z, 0xff4b4b, 0);
  return y0 + h;
}
