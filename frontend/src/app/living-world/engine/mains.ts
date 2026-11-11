import * as THREE from "three";
import { FLOOR_H, type TowerSpec } from "../model/towerSpec";
import type { Builder } from "./buildingFactory";
import { BASE_Y, CROWN_SHARE, DARK, GREY, WHITE, bar, crown, hcyl, latticeMast, loft } from "./towers";

/**
 * The main structure of a holding: the tower (or the stack, dome, arena) the rest of the complex
 * is arranged around. One function per silhouette family; `buildMain` picks it from the spec.
 * Local units, nominal footprint `n`; the shaft stands at (0, MAIN_Z) and keeps within ~0.42 n.
 */

export const MAIN_Z = -0.02;
export const DECK_TOP = 0.24;

export interface MainCtx {
  b: Builder;
  n: number;
  spec: TowerSpec;
}

export interface MainResult {
  /** Highest point of the main structure. */
  top: number;
  /** Radius of the base, for placing neighbours. */
  radius: number;
}

const floorsFor = (h: number) => Math.max(4, Math.round(h / FLOOR_H));

/** A flat disc or ring-shaped annulus lying at height y. */
function annulus(b: Builder, cx: number, cz: number, y: number, w: number, d: number, sOuter: number, sInner: number, hex: number) {
  const N = 24;
  const pos = new Float32Array(N * 2 * 3);
  const nor = new Float32Array(N * 2 * 3);
  for (let i = 0; i < N; i++) {
    const a = (i / N) * Math.PI * 2;
    pos.set([cx + Math.cos(a) * (w / 2) * sOuter, y, cz + Math.sin(a) * (d / 2) * sOuter], i * 6);
    pos.set([cx + Math.cos(a) * (w / 2) * sInner, y, cz + Math.sin(a) * (d / 2) * sInner], i * 6 + 3);
    nor[i * 6 + 1] = 1;
    nor[i * 6 + 4] = 1;
  }
  const idx: number[] = [];
  for (let i = 0; i < N; i++) {
    const a = i * 2;
    const c = ((i + 1) % N) * 2;
    // Seen from above (x right, z towards the viewer) the outer ring runs clockwise in this order.
    idx.push(a, a + 1, c, c, a + 1, c + 1);
  }
  // Orient up: flip when the first triangle faces down.
  const p = (k: number) => new THREE.Vector3().fromArray(pos, k * 3);
  const n0 = new THREE.Vector3().subVectors(p(idx[1]), p(idx[0])).cross(new THREE.Vector3().subVectors(p(idx[2]), p(idx[0])));
  if (n0.y < 0) for (let k = 0; k < idx.length; k += 3) [idx[k + 1], idx[k + 2]] = [idx[k + 2], idx[k + 1]];
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("normal", new THREE.BufferAttribute(nor, 3));
  g.setIndex(idx);
  b.custom(g, hex);
}

function plinth(c: MainCtx, w: number, d: number, cx: number, cz: number) {
  c.b.kind = 0;
  c.b.box(w * 1.2, BASE_Y - DECK_TOP, d * 1.2, cx, DECK_TOP, cz, DARK);
}

/** Glass ground floor + podium band under a shaft: a two-storey lobby wider than the tower. */
function lobby(c: MainCtx, w: number, d: number, cx: number, cz: number, roundish: boolean) {
  const { b, spec } = c;
  b.kind = 0;
  const h = 2 * FLOOR_H;
  if (roundish) b.cyl(w * 0.72, w * 0.72, h, cx, BASE_Y, cz, WHITE, 16);
  else b.box(w * 1.3, h, d * 1.3, cx, BASE_Y, cz, WHITE);
  b.kind = 2;
  if (roundish) b.cyl(w * 0.74, w * 0.74, 0.06, cx, BASE_Y + h, cz, spec.accent, 16);
  else b.box(w * 1.34, 0.06, d * 1.34, cx, BASE_Y + h, cz, spec.accent);
  return BASE_Y + h + 0.06;
}

function twistTower(c: MainCtx): MainResult {
  const { b, spec, n } = c;
  const m = spec.main;
  const w = m.width * n;
  const d = w * m.aspect;
  const cz = MAIN_Z * n;
  const crownLen = m.height * CROWN_SHARE[m.crown];
  const floors = floorsFor(m.height - crownLen);
  plinth(c, w, d, 0, cz);
  const y0 = lobby(c, w, d, 0, cz, false);
  const h = floors * FLOOR_H - (y0 - BASE_Y);
  const segs = Math.min(24, Math.max(6, Math.round(floors / 1.5)));
  const top = loft(b, {
    plan: m.plan, w, d, cx: 0, cz, y0, h, hex: spec.glass, segs, rot: m.rotation,
    scale: (t) => 1 - (1 - m.taper) * t,
    twist: (t) => m.twist * t,
    cap: spec.accent,
  });
  const t = crown(b, m.crown, 0, top, cz, (w / 2) * m.taper, crownLen, spec.accent);
  return { top: t, radius: w * 0.65 };
}

function eggTower(c: MainCtx): MainResult {
  const { b, spec, n } = c;
  const m = spec.main;
  const w = m.width * n * 1.28;
  const cz = MAIN_Z * n;
  const crownLen = m.height * CROWN_SHARE[m.crown];
  const H = floorsFor(m.height - crownLen) * FLOOR_H;
  plinth(c, w, w, 0, cz);
  // Gherkin profile: a narrow waist at the ground, the belly a third of the way up, then a dome.
  const prof = (t: number) => {
    if (t < 0.36) return 0.62 + 0.38 * Math.sin((t / 0.36) * Math.PI * 0.5);
    const u = (t - 0.36) / 0.64;
    return 0.04 + 0.96 * Math.sqrt(Math.max(0, 1 - u * u));
  };
  const ts = Array.from({ length: 19 }, (_, i) => i / 18).map((t) => (t > 0.8 ? 0.8 + (t - 0.8) * 0.97 : t));
  ts[ts.length - 1] = 1;
  const top = loft(b, {
    plan: "ellipse", w, d: w, cx: 0, cz, y0: BASE_Y, h: H, hex: spec.glass, ts, scale: prof,
    kind: m.diagrid ? 3 : 1, colMultiple: 4,
  });
  const t = crown(b, m.crown, 0, top - 0.04, cz, w * 0.1, crownLen, spec.accent);
  return { top: t, radius: w * 0.5 };
}

function steppedTower(c: MainCtx): MainResult {
  const { b, spec, n } = c;
  const m = spec.main;
  const w0 = m.width * n;
  const cz0 = MAIN_Z * n;
  const crownLen = m.height * CROWN_SHARE[m.crown];
  const total = floorsFor(m.height - crownLen);
  const S = m.steps;
  const weights = [4.2, 3, 2.2, 1.5, 1].slice(0, S);
  const sum = weights.reduce((a, x) => a + x, 0);
  const shrink = 0.8;
  plinth(c, w0, w0 * m.aspect, 0, cz0);
  let y = lobby(c, w0 * 0.96, w0 * m.aspect * 0.96, 0, cz0, false);
  let done = Math.round((y - BASE_Y) / FLOOR_H);
  let w = w0;
  let top = y;
  const shift = Math.sin(m.rotation) * 0.05 * w0;
  for (let k = 0; k < S; k++) {
    const fl = k === S - 1 ? Math.max(2, total - done) : Math.max(2, Math.round((weights[k] / sum) * total));
    const h = fl * FLOOR_H;
    const d = w * m.aspect;
    top = loft(b, { plan: m.plan, w, d, cx: shift * k, cz: cz0, y0: y, h, hex: spec.glass, cap: k === S - 1 ? spec.accent : DARK, capKind: k === S - 1 ? 2 : 0, scale: (t) => 1 - (1 - m.taper * 0.96) * 0.3 * t });
    // Terrace edge and corner fins in the accent colour.
    b.kind = 2;
    b.box(w * 1.04, 0.07, d * 1.04, shift * k, top - 0.02, cz0, spec.accent);
    b.kind = 0;
    y = top + 0.05;
    done += fl;
    w *= shrink;
  }
  const t = crown(b, m.crown, shift * (S - 1), top + 0.05, cz0, w * 0.5, crownLen, spec.accent);
  return { top: t, radius: w0 * 0.62 };
}

function cylinderTower(c: MainCtx): MainResult {
  const { b, spec, n } = c;
  const m = spec.main;
  const w = m.width * n * 1.12;
  const cz = MAIN_Z * n;
  const crownLen = m.height * CROWN_SHARE.helipad;
  const floors = floorsFor(m.height - crownLen - 0.4);
  const H = floors * FLOOR_H;
  plinth(c, w, w, 0, cz);
  const y0 = lobby(c, w, w, 0, cz, true);
  const h = H - (y0 - BASE_Y);
  const top = loft(b, { plan: "ellipse", w, d: w, cx: 0, cz, y0, h, hex: spec.glass, scale: (t) => 1 - (1 - m.taper) * t, kind: m.diagrid ? 3 : 1, colMultiple: 4, cap: WHITE, capKind: 0 });
  const rTop = (w / 2) * m.taper;
  // Accent rings at a quarter, half and three quarters of the height, hugging the taper.
  b.kind = 2;
  for (const f of [0.25, 0.5, 0.75]) {
    const r = (w / 2) * (1 - (1 - m.taper) * f) + 0.05;
    b.cyl(r, r, 0.1, 0, Math.round((y0 + h * f) / FLOOR_H) * FLOOR_H, cz, spec.accent, 18);
  }
  // A cantilevered top deck wider than the shaft carries the helipad.
  b.kind = 0;
  b.cyl(rTop * 1.18, rTop * 1.08, 0.34, 0, top, cz, WHITE, 18);
  const t = crown(b, "helipad", 0, top + 0.34, cz, rTop * 1.12, crownLen, spec.accent);
  return { top: t, radius: w * 0.6 };
}

function slabTower(c: MainCtx): MainResult {
  const { b, spec, n } = c;
  const m = spec.main;
  const sw = m.width * n * 0.6;
  const d = sw * 1.5;
  const gap = sw * 0.7;
  const cz = MAIN_Z * n;
  const crownLen = m.height * CROWN_SHARE[m.crown];
  const f1 = floorsFor(m.height - crownLen);
  const f2 = Math.max(6, Math.round(f1 * 0.8));
  const x1 = -(sw + gap) / 2;
  const x2 = (sw + gap) / 2;
  plinth(c, sw * 2 + gap, d, 0, cz);
  b.kind = 0;
  const y0 = BASE_Y + 2 * FLOOR_H;
  b.box(sw * 2 + gap + 0.3, 2 * FLOOR_H, d * 1.2, 0, BASE_Y, cz, WHITE);
  b.kind = 2;
  b.box(sw * 2 + gap + 0.34, 0.06, d * 1.24, 0, y0, cz, spec.accent);
  const topA = loft(b, { plan: "rect", w: sw, d, cx: x1, cz, y0, h: f1 * FLOOR_H - 2 * FLOOR_H, hex: spec.glass, cap: spec.accent, scale: (t) => 1 - (1 - m.taper) * 0.5 * t });
  const topB = loft(b, { plan: "rect", w: sw, d, cx: x2, cz, y0, h: f2 * FLOOR_H - 2 * FLOOR_H, hex: spec.glass, cap: spec.accent, scale: (t) => 1 - (1 - m.taper) * 0.5 * t });
  // The sky-bridge: two glass storeys with an accent frame, a little under the lower roof.
  const by = Math.round((topB - 6 * FLOOR_H) / FLOOR_H) * FLOOR_H;
  b.kind = 1;
  b.box(gap + 0.1, 2 * FLOOR_H, d * 0.5, 0, by, cz, spec.glass);
  b.kind = 2;
  b.box(gap + 0.16, 0.06, d * 0.54, 0, by + 2 * FLOOR_H, cz, spec.accent);
  b.box(gap + 0.16, 0.06, d * 0.54, 0, by - 0.06, cz, spec.accent);
  const kind = m.crown === "spire" || m.crown === "pinnacle" ? "antenna" : m.crown;
  const t = crown(b, kind, x1, topA, cz, sw * 0.4, crownLen, spec.accent);
  // The lower slab gets a rooftop garden.
  b.kind = 0;
  b.box(sw * 0.7, 0.1, d * 0.7, x2, topB, cz, 0x4aa760);
  return { top: t, radius: sw + gap / 2 + 0.3 };
}

/** The A-frame winding tower of a mine, with its sheave wheels and hoist house. */
function headframe(b: Builder, x: number, z: number, w: number, h: number, accent: number) {
  b.kind = 0;
  b.box(w * 1.3, 1.1, w * 0.9, x - w * 0.2, DECK_TOP, z + w * 0.9, accent);
  b.box(w * 0.9, 0.5, w * 0.9, x - w * 0.2, DECK_TOP + 1.1, z + w * 0.9, DARK);
  const hw = w / 2;
  const ty = BASE_Y + h * 0.9;
  for (const s of [-1, 1]) {
    bar(b, [x + s * hw, BASE_Y, z - hw], [x + s * hw * 0.25, ty, z - 0.05], 0.14, accent);
    bar(b, [x + s * hw, BASE_Y, z + hw * 0.6], [x + s * hw * 0.25, ty, z + 0.05], 0.14, accent);
  }
  for (let i = 1; i < 6; i++) {
    const t = i / 6;
    const e = hw * (1 - t * 0.8);
    bar(b, [x - e, BASE_Y + t * h * 0.9, z - 0.04], [x + e, BASE_Y + t * h * 0.9, z - 0.04], 0.07, WHITE);
    if (i < 5) bar(b, [x - e, BASE_Y + t * h * 0.9, z], [x + hw * (1 - (t + 1 / 6) * 0.8), BASE_Y + (t + 1 / 6) * h * 0.9, z], 0.05, WHITE);
  }
  b.box(w * 0.6, 0.3, 0.5, x, ty, z, DARK);
  hcyl(b, 0.42, 0.14, x - 0.15, h * 0.97 + BASE_Y, z, GREY, "z", 14);
  hcyl(b, 0.42, 0.14, x + 0.15, h * 0.97 + BASE_Y, z, GREY, "z", 14);
  bar(b, [x - 0.15, BASE_Y + h * 0.97 - 0.42, z], [x - w * 0.2, DECK_TOP + 1.6, z + w * 0.9 - 0.4], 0.03, DARK);
  return BASE_Y + h;
}

function needleTower(c: MainCtx): MainResult {
  const { b, spec, n } = c;
  const m = spec.main;
  const w = m.width * n * 1.25;
  const cz = MAIN_Z * n;
  plinth(c, w, w, 0, cz);
  if (spec.archetype === "mining") {
    const top = headframe(b, 0, cz, w * 0.9, m.height - 0.5, spec.accent);
    return { top: top + 0.3, radius: w * 0.7 };
  }
  b.kind = 0;
  const top = latticeMast(b, 0, BASE_Y, cz, w, m.height, spec.accent, { levels: m.height > 18 ? 6 : 5, braces: spec.tier !== "outpost" });
  return { top, radius: w * 0.6 };
}

function domeTower(c: MainCtx): MainResult {
  const { b, spec, n } = c;
  const m = spec.main;
  const r = m.width * n * 0.82;
  const cz = MAIN_Z * n;
  plinth(c, r * 2, r * 2, 0, cz);
  b.kind = 0;
  const drumH = 4 * FLOOR_H;
  b.cyl(r * 1.05, r * 1.12, 0.12, 0, BASE_Y, cz, GREY, 20);
  b.cyl(r, r, drumH, 0, BASE_Y + 0.12, cz, WHITE, 20);
  // A ring of columns round the drum.
  for (let i = 0; i < 10; i++) {
    const a = (i / 10) * Math.PI * 2;
    b.cyl(0.07, 0.07, drumH, Math.cos(a) * (r + 0.06), BASE_Y + 0.12, cz + Math.sin(a) * (r + 0.06), GREY, 6);
  }
  b.kind = 2;
  b.cyl(r * 1.06, r * 1.06, 0.1, 0, BASE_Y + 0.12 + drumH, cz, spec.accent, 20);
  const y1 = BASE_Y + 0.22 + drumH;
  const domeH = r * 0.95;
  const top = loft(b, { plan: "ellipse", w: r * 2, d: r * 2, cx: 0, cz, y0: y1, h: domeH, hex: spec.glass, ts: [0, 0.15, 0.32, 0.5, 0.68, 0.84, 1], scale: (t) => Math.max(0.05, Math.cos(t * Math.PI * 0.5)), yAt: (t) => Math.sin(t * Math.PI * 0.5), kind: 1, colMultiple: 4 });
  // The lantern and a tall spire carry the height.
  b.kind = 2;
  b.cyl(r * 0.16, r * 0.2, 0.5, 0, top - 0.04, cz, spec.accent, 8);
  const t = crown(b, "spire", 0, top + 0.46, cz, r * 0.5, Math.max(1.5, m.height - (top + 0.46)), spec.accent);
  return { top: t, radius: r * 1.1 };
}

function stadiumTower(c: MainCtx): MainResult {
  const { b, spec, n } = c;
  const m = spec.main;
  const w = n * 0.66;
  const d = n * 0.5;
  const cz = MAIN_Z * n;
  plinth(c, w, d, 0, cz);
  const H = 5 * FLOOR_H;
  const y0 = BASE_Y;
  b.kind = 0;
  const topY = loft(b, { plan: m.plan === "super" ? "super" : "ellipse", w, d, cx: 0, cz, y0, h: H, hex: WHITE, kind: 0 });
  // Glass band round the upper bowl, then the roof ring and the inner terraces going down.
  loft(b, { plan: "ellipse", w: w * 1.02, d: d * 1.02, cx: 0, cz, y0: y0 + 2 * FLOOR_H, h: 2 * FLOOR_H, hex: spec.glass, kind: 1, colMultiple: 4 });
  annulus(b, 0, cz, topY, w, d, 1.06, 0.74, spec.accent);
  loft(b, { plan: "ellipse", w: w * 0.74, d: d * 0.74, cx: 0, cz, y0: topY, h: -(H - 0.5), hex: 0xe9e2d2, kind: 0, inward: true, ts: [0, 1], scale: (t) => 1 - 0.18 * t });
  // The pitch.
  loft(b, { plan: "ellipse", w: w * 0.56, d: d * 0.56, cx: 0, cz, y0: y0 + 0.5, h: 0.02, hex: 0x3fa456, cap: 0x3fa456, capKind: 0, kind: 0 });
  b.kind = 0;
  b.box(w * 0.3, 0.02, 0.05, 0, y0 + 0.54, cz, WHITE);
  // Floodlight masts at the corners set the height of the site.
  const mastH = m.height - topY;
  for (const [sx, sz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]] as const) {
    const mx = sx * w * 0.5;
    const mz = cz + sz * d * 0.5;
    b.cyl(0.04, 0.08, mastH + topY - BASE_Y, mx, BASE_Y, mz, GREY, 6);
    b.box(0.34, 0.2, 0.1, mx, m.height - 0.2, mz, 0xfff4c8);
  }
  return { top: m.height, radius: w * 0.58 };
}

/** A stack complex: what the archetype is makes it a cooling tower, a refinery, a silo works or a plant. */
function stackComplex(c: MainCtx): MainResult {
  const { b, spec, n } = c;
  const m = spec.main;
  const w = m.width * n;
  const cz = MAIN_Z * n;
  const H = m.height;
  plinth(c, w, w, 0, cz);
  b.kind = 0;
  const chimney = (x: number, z: number, h: number, r: number) => {
    const bands = 4;
    for (let i = 0; i < bands; i++) {
      const y = BASE_Y + (i / bands) * h;
      const r0 = r * (1 - 0.35 * (i / bands));
      const r1 = r * (1 - 0.35 * ((i + 1) / bands));
      b.cyl(r1, r0, h / bands, x, y, z, i % 2 ? 0xd8392c : WHITE, 9);
    }
    b.cyl(r * 0.72, r * 0.72, 0.1, x, BASE_Y + h, z, DARK, 9);
  };
  if (spec.archetype === "utilities") {
    const rc = w * 0.46;
    const ch = Math.max(4.2, H * 0.52);
    const cxT = -w * 0.18;
    // Hyperboloid cooling tower.
    loft(b, { plan: "ellipse", w: rc * 2, d: rc * 2, cx: cxT, cz, y0: BASE_Y, h: ch, hex: 0xe8e4dc, kind: 0, ts: [0, 0.18, 0.36, 0.54, 0.72, 0.86, 1], scale: (t) => Math.sqrt(0.4356 + 1.089 * (t - 0.72) * (t - 0.72)), cap: 0xd6d2c8, capKind: 0 });
    b.cyl(rc * 0.74, rc * 0.74, 0.08, cxT, BASE_Y + ch, cz, spec.accent, 14);
    b.ico(rc * 0.55, cxT, BASE_Y + ch + rc * 0.5, cz, WHITE, 1);
    b.ico(rc * 0.4, cxT + rc * 0.3, BASE_Y + ch + rc * 1.1, cz + rc * 0.1, 0xf2f5f8, 0);
    for (let i = 0; i < m.chimneys; i++) {
      const hh = H - i * H * 0.07;
      chimney(w * 0.5 + i * w * 0.13 - (m.chimneys > 2 ? 0.1 : 0), cz - rc * 0.5 + i * rc * 0.6, hh, w * 0.085);
    }
    return { top: BASE_Y + H + 0.1, radius: w * 0.7 };
  }
  if (spec.archetype === "energy") {
    // Process columns, a pipe rack and the flare stack.
    const cols: Array<[number, number, number, number]> = [[-w * 0.4, 0.55, 0.11, -0.12], [-w * 0.02, 0.38, 0.14, 0.08], [w * 0.3, 0.28, 0.1, -0.1]];
    for (const [x, hs, rs, zo] of cols) {
      const h = H * hs;
      b.cyl(w * rs, w * rs * 1.1, h, x, BASE_Y, cz + zo * w, WHITE, 8);
      b.cyl(w * rs * 1.18, w * rs * 1.18, 0.1, x, BASE_Y + h * 0.5, cz + zo * w, spec.accent, 10);
      b.cyl(w * rs * 1.18, w * rs * 1.18, 0.1, x, BASE_Y + h * 0.82, cz + zo * w, spec.accent, 10);
      b.ico(w * rs, x, BASE_Y + h, cz + zo * w, WHITE, 0);
      b.box(0.07, h * 0.9, 0.07, x + w * rs + 0.05, BASE_Y, cz + zo * w, DARK);
    }
    hcyl(b, 0.07, w * 0.8, -w * 0.05, BASE_Y + 1.1, cz + w * 0.18, GREY, "x", 6);
    hcyl(b, 0.07, w * 0.8, -w * 0.05, BASE_Y + 1.4, cz + w * 0.18, spec.accent, "x", 6);
    // Flare stack.
    const fx = w * 0.62;
    b.cyl(0.06, 0.14, H - 1, fx, BASE_Y, cz - w * 0.2, GREY, 6);
    bar(b, [fx - 0.3, BASE_Y, cz - w * 0.2], [fx, BASE_Y + H * 0.55, cz - w * 0.2], 0.04, WHITE);
    b.cyl(0.14, 0.1, 0.4, fx, BASE_Y + H - 1, cz - w * 0.2, DARK, 6);
    b.cone(0.17, 0.75, fx, BASE_Y + H - 0.6, cz - w * 0.2, 0xff9224, 6);
    return { top: BASE_Y + H + 0.15, radius: w * 0.72 };
  }
  if (spec.archetype === "consumer") {
    for (let i = 0; i < 3; i++) {
      const x = -w * 0.38 + i * w * 0.34;
      const h = H * (0.36 + 0.08 * (i % 2));
      b.cyl(w * 0.14, w * 0.14, h, x, BASE_Y, cz + w * 0.08, WHITE, 12);
      b.cyl(w * 0.145, w * 0.145, 0.1, x, BASE_Y + h * 0.72, cz + w * 0.08, spec.accent, 12);
      b.cone(w * 0.14, 0.4, x, BASE_Y + h, cz + w * 0.08, spec.accent, 12);
    }
    chimney(w * 0.3, cz - w * 0.22, H, w * 0.1);
    return { top: BASE_Y + H + 0.1, radius: w * 0.72 };
  }
  // Mining: a crusher tower, a conveyor and a chimney.
  b.box(w * 0.5, H * 0.38, w * 0.5, -w * 0.2, BASE_Y, cz, spec.accent);
  b.box(w * 0.54, 0.1, w * 0.54, -w * 0.2, BASE_Y + H * 0.38, cz, DARK);
  b.cone(w * 0.3, 1.4, -w * 0.2, BASE_Y + H * 0.38 + 0.1, cz, 0xb88b58, 8);
  bar(b, [w * 0.05, BASE_Y + 0.4, cz + w * 0.45], [-w * 0.2, BASE_Y + H * 0.34, cz + w * 0.1], 0.16, DARK);
  chimney(w * 0.42, cz - w * 0.1, H, w * 0.09);
  return { top: BASE_Y + H + 0.1, radius: w * 0.7 };
}

function crystalTower(c: MainCtx): MainResult {
  const { b, spec, n } = c;
  const m = spec.main;
  const w = m.width * n * 1.1;
  const cz = MAIN_Z * n;
  const crownLen = m.height * CROWN_SHARE.pinnacle;
  const floors = floorsFor(m.height - crownLen);
  plinth(c, w, w, 0, cz);
  b.kind = 0;
  b.cyl(w * 0.62, w * 0.68, 2 * FLOOR_H, 0, BASE_Y, cz, 0x24293e, 6);
  const y0 = BASE_Y + 2 * FLOOR_H;
  const h = floors * FLOOR_H - 2 * FLOOR_H;
  const top = loft(b, { plan: "hex", w, d: w, cx: 0, cz, y0, h, hex: spec.glass, segs: 4, scale: (t) => 1 - (1 - m.taper) * t, twist: (t) => 0.35 * t, kind: m.diagrid ? 3 : 1, colMultiple: 4, cap: spec.accent });
  const t = crown(b, "pinnacle", 0, top, cz, (w / 2) * m.taper, crownLen, spec.accent);
  return { top: t, radius: w * 0.62 };
}

export function buildMain(c: MainCtx): MainResult {
  switch (c.spec.main.family) {
    case "twist":
      return twistTower(c);
    case "egg":
      return eggTower(c);
    case "stepped":
      return steppedTower(c);
    case "cylinder":
      return cylinderTower(c);
    case "slab":
      return slabTower(c);
    case "needle":
      return needleTower(c);
    case "dome":
      return domeTower(c);
    case "stadium":
      return stadiumTower(c);
    case "stack":
      return stackComplex(c);
    default:
      return crystalTower(c);
  }
}

