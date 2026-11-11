import { FLOOR_H, type PartKind, type TowerSpec } from "../model/towerSpec";
import type { Builder } from "./buildingFactory";
import { DECK_TOP } from "./mains";
import { BASE_Y, DARK, DECK, GOLD, GREY, WHITE, bar, hcyl, latticeMast, loft, tree } from "./towers";

/**
 * The other structures of a holding's complex: plazas, halls, pavilions, car parks, annex towers,
 * and the industrial kit (tanks, silos, turbine halls, substations, wind turbines, solar fields,
 * cooling towers, conveyors...). Each builder fills a slot (`w` x `d` around `x`, `z`, local units)
 * and stays inside it; `variant` (0..2, from the id) changes the flavour.
 */

export interface PartCtx {
  b: Builder;
  n: number;
  spec: TowerSpec;
  /** Height of the main structure, for parts that must stay below it. */
  mainTop: number;
}

type PartFn = (c: PartCtx, x: number, z: number, w: number, d: number, v: number) => void;

const LEAF = [0x3ea65a, 0x56b56a, 0x2f9a58];
const CAR = [0xe84a5f, 0x2f80ed, 0xf2c230, 0xffffff, 0x1fb8a8, 0xff8a3d];

/** y of the ground floor level of a low building: its plinth tops out on the storey grid. */
const G0 = BASE_Y;

function plinthBox(b: Builder, x: number, z: number, w: number, d: number) {
  b.kind = 0;
  b.box(w * 1.04, G0 - DECK_TOP, d * 1.04, x, DECK_TOP, z, DARK);
}

const plaza: PartFn = ({ b, spec, n }, x, z, w, d, v) => {
  b.kind = 0;
  b.box(w, 0.03, d, x, DECK_TOP, z, 0xe8dfc8);
  b.box(w * 0.9, 0.035, d * 0.9, x, DECK_TOP, z, 0xf6f0e2);
  b.kind = 2;
  b.box(w, 0.04, 0.07, x, DECK_TOP, z - d * 0.45, spec.accent);
  b.box(w, 0.04, 0.07, x, DECK_TOP, z + d * 0.45, spec.accent);
  b.kind = 0;
  if (v === 0) {
    const r = Math.min(w, d) * 0.3;
    b.cyl(r, r * 1.05, 0.2, x, DECK_TOP, z, WHITE, 14);
    b.cyl(r * 0.85, r * 0.85, 0.22, x, DECK_TOP, z, 0x6fd0f5, 14);
    b.cyl(0.03, 0.05, 0.7, x, DECK_TOP, z, 0xdff6ff, 5);
    b.ico(0.09, x, DECK_TOP + 0.74, z, 0xdff6ff, 0);
  } else if (v === 1) {
    for (const [dx, dz, s] of [[-0.28, -0.1, 0.9], [0.26, 0.05, 1.1], [0, 0.3, 0.8], [0.0, -0.28, 0.7]] as const) tree(b, x + dx * w, DECK_TOP + 0.02, z + dz * d, s * 0.9 * (n / 8 + 0.4), LEAF[(Math.abs(dx * 10) | 0) % 3]);
    b.box(w * 0.5, 0.1, 0.14, x, DECK_TOP, z + d * 0.1, 0xcfa56b);
  } else {
    b.kind = 2;
    bar(b, [x - 0.2, DECK_TOP, z], [x + 0.1, DECK_TOP + 1.1, z], 0.14, spec.accent);
    b.kind = 0;
    b.ico(0.22, x + 0.12, DECK_TOP + 1.3, z, GOLD, 1);
    b.cyl(0.26, 0.3, 0.12, x - 0.2, DECK_TOP, z, GREY, 8);
  }
  for (const s of [-1, 1]) {
    b.cyl(0.025, 0.025, 0.42, x + s * w * 0.46, DECK_TOP, z + d * 0.3, DARK, 4);
    b.ico(0.06, x + s * w * 0.46, DECK_TOP + 0.45, z + d * 0.3, 0xfff1b8, 0);
  }
};

const pavilion: PartFn = ({ b, spec }, x, z, w, d, v) => {
  plinthBox(b, x, z, w * 0.9, d * 0.9);
  const fl = 2 + (v === 2 ? 1 : 0);
  b.kind = 1;
  if (v === 1) {
    loft(b, { plan: "ellipse", w: w * 0.9, d: d * 0.9, cx: x, cz: z, y0: G0, h: fl * FLOOR_H, hex: spec.glass, kind: 1, colMultiple: 4, cap: spec.accent });
  } else {
    b.box(w * 0.84, fl * FLOOR_H, d * 0.84, x, G0, z, spec.glass);
    b.kind = 2;
    b.box(w * 0.98, 0.07, d * 0.98, x, G0 + fl * FLOOR_H, z, spec.accent);
  }
  b.kind = 0;
  b.box(w * 0.4, 0.05, d * 0.32, x, G0 + 0.5, z + d * 0.5, WHITE);
  if (v === 2) {
    b.kind = 2;
    b.pyramid(w * 0.8, 0.5, x, G0 + fl * FLOOR_H + 0.07, z, spec.accent);
  }
};

const annex: PartFn = ({ b, spec, mainTop }, x, z, w, d, v) => {
  const s = Math.min(w, d);
  const h = Math.min(mainTop * (0.4 + 0.1 * v), 5 + 2.6 * (spec.tier === "major" ? 1.3 : 1));
  const floors = Math.max(6, Math.round(h / FLOOR_H));
  plinthBox(b, x, z, s * 0.86, s * 0.86);
  if (v === 0) {
    const top = loft(b, { plan: "rounded", w: s * 0.8, d: s * 0.8, cx: x, cz: z, y0: G0, h: floors * FLOOR_H, hex: spec.glass, segs: 8, scale: (t) => 1 - 0.3 * t, twist: (t) => 0.9 * t, cap: spec.accent });
    b.kind = 0;
    b.cyl(0.02, 0.05, 0.5, x, top, z, WHITE, 5);
  } else if (v === 1) {
    let y = G0;
    let ww = s * 0.84;
    for (let k = 0; k < 3; k++) {
      const fl = Math.max(2, Math.round(floors / (k + 2.2)));
      y = loft(b, { plan: "rect", w: ww, d: ww, cx: x, cz: z, y0: y, h: fl * FLOOR_H, hex: spec.glass, cap: k === 2 ? spec.accent : DARK, capKind: k === 2 ? 2 : 0 });
      ww *= 0.78;
    }
  } else {
    const top = loft(b, { plan: "rect", w: s * 0.7, d: s * 0.8, cx: x, cz: z, y0: G0, h: floors * FLOOR_H, hex: spec.glass, cap: spec.accent, scale: (t) => 1 - 0.18 * t });
    b.kind = 2;
    b.box(s * 0.82, 0.06, s * 0.92, x, G0 + floors * FLOOR_H * 0.5, z, spec.accent);
    b.kind = 0;
    b.box(s * 0.3, 0.16, s * 0.3, x, top, z, GREY);
  }
};

const hall: PartFn = ({ b, spec }, x, z, w, d, v) => {
  plinthBox(b, x, z, w, d);
  const fl = 2 + (v === 1 ? 1 : 0);
  b.kind = 0;
  b.box(w * 0.94, fl * FLOOR_H, d * 0.94, x, G0, z, v === 2 ? 0xe9eef2 : WHITE);
  b.kind = 1;
  b.box(w * 0.86, FLOOR_H, 0.05, x, G0 + FLOOR_H * (fl - 1.0) * 0.5, z + d * 0.475, spec.glass);
  b.kind = 2;
  b.box(w, 0.08, d, x, G0 + fl * FLOOR_H, z, spec.accent);
  b.kind = 0;
  if (v === 1) {
    for (let i = 0; i < 3; i++) b.tilted(w * 0.28, 0.06, d * 0.9, x - w * 0.3 + i * w * 0.3, G0 + fl * FLOOR_H + 0.22, z, WHITE, 0.45);
  } else {
    b.box(w * 0.3, 0.2, d * 0.3, x - w * 0.2, G0 + fl * FLOOR_H + 0.08, z, GREY);
    b.cyl(0.07, 0.07, 0.34, x + w * 0.24, G0 + fl * FLOOR_H + 0.08, z - d * 0.1, DARK, 6);
  }
};

const carpark: PartFn = ({ b, spec }, x, z, w, d, v) => {
  b.kind = 0;
  b.box(w, 0.04, d, x, DECK_TOP, z, 0x4a505a);
  for (let i = 0; i < 5; i++) b.box(0.03, 0.05, d * 0.42, x - w * 0.4 + i * w * 0.2, DECK_TOP, z - d * 0.12, WHITE);
  if (v === 1) {
    // A multi-storey car park: two decks on columns.
    for (let k = 0; k < 2; k++) {
      b.box(w * 0.9, 0.08, d * 0.7, x, DECK_TOP + 0.5 + k * 0.5, z - d * 0.1, k ? spec.accent : GREY);
      for (const sx of [-1, 1]) for (const sz of [-1, 1]) b.box(0.07, 0.5, 0.07, x + sx * w * 0.42, DECK_TOP + (k ? 0.5 : 0), z - d * 0.1 + sz * d * 0.32, WHITE);
    }
  }
  for (let i = 0; i < 4; i++) b.box(w * 0.14, 0.1, d * 0.26, x - w * 0.3 + i * w * 0.2, DECK_TOP + 0.04, z + d * 0.12, CAR[(i + v * 2) % CAR.length]);
  b.kind = 2;
  b.box(w * 0.2, 0.3, 0.06, x + w * 0.42, DECK_TOP, z + d * 0.46, spec.accent);
};

const garden: PartFn = ({ b, n }, x, z, w, d, v) => {
  b.kind = 0;
  b.box(w, 0.05, d, x, DECK_TOP, z, 0x7cc46a);
  b.box(w * 0.16, 0.06, d, x, DECK_TOP, z, 0xe8dfc8);
  const s = 0.55 + n * 0.04;
  const pts: Array<[number, number]> = v === 0 ? [[-0.3, -0.3], [0.3, -0.25], [-0.3, 0.3], [0.3, 0.3]] : v === 1 ? [[-0.32, 0], [0.32, 0], [0, -0.35], [0, 0.35]] : [[-0.3, -0.3], [0.3, 0.3], [0.32, -0.3]];
  pts.forEach(([dx, dz], i) => tree(b, x + dx * w, DECK_TOP + 0.04, z + dz * d, s * (0.9 + 0.2 * (i % 2)), LEAF[i % 3]));
  if (v === 2) b.cyl(w * 0.12, w * 0.12, 0.08, x - w * 0.28, DECK_TOP + 0.04, z + d * 0.28, 0x6fd0f5, 10);
};

const mall: PartFn = ({ b, spec }, x, z, w, d) => {
  plinthBox(b, x, z, w, d);
  b.kind = 0;
  b.box(w * 0.96, 2 * FLOOR_H, d * 0.9, x, G0, z, 0xfaf2e4);
  b.kind = 1;
  b.box(w * 0.88, 1.5 * FLOOR_H, 0.05, x, G0 + 0.1, z + d * 0.46, spec.glass);
  b.kind = 2;
  b.box(w, 0.14, d * 0.94, x, G0 + 2 * FLOOR_H, z, spec.accent);
  for (let i = 0; i < 6; i++) b.box(w * 0.14, 0.1, 0.34, x - w * 0.42 + i * w * 0.168, G0 + 0.5, z + d * 0.5, i % 2 ? WHITE : spec.accent);
  loft(b, { plan: "ellipse", w: w * 0.4, d: d * 0.5, cx: x, cz: z, y0: G0 + 2 * FLOOR_H + 0.14, h: 0.6, hex: spec.glass, ts: [0, 0.4, 0.75, 1], scale: (t) => Math.max(0.05, Math.cos(t * Math.PI * 0.5)), yAt: (t) => Math.sin(t * Math.PI * 0.5), kind: 1 });
};

const wing: PartFn = ({ b, spec }, x, z, w, d, v) => {
  plinthBox(b, x, z, w, d);
  const fl = 6 + v * 2;
  b.kind = 1;
  b.box(w * 0.86, fl * FLOOR_H, d * 0.86, x, G0, z, 0xcdeaf0);
  b.kind = 2;
  b.box(w * 0.96, 0.08, d * 0.96, x, G0 + fl * FLOOR_H, z, spec.accent);
  b.kind = 0;
  const top = G0 + fl * FLOOR_H + 0.08;
  b.box(0.08, 0.5, 0.08, x, top, z, 0xe63946);
  b.box(0.4, 0.08, 0.08, x, top + 0.2, z, 0xe63946);
  if (v === 0) {
    b.cyl(w * 0.24, w * 0.24, 0.05, x - w * 0.2, top, z - d * 0.2, 0x3fb84a, 12);
    b.box(w * 0.2, 0.06, w * 0.04, x - w * 0.2, top + 0.05, z - d * 0.2, WHITE);
  }
};

const dish: PartFn = ({ b, spec }, x, z, w, d, v) => {
  plinthBox(b, x, z, w, d);
  b.kind = 0;
  b.box(w * 0.5, 2 * FLOOR_H, d * 0.5, x, G0, z + d * 0.18, WHITE);
  b.kind = 2;
  b.box(w * 0.54, 0.06, d * 0.54, x, G0 + 2 * FLOOR_H, z + d * 0.18, spec.accent);
  const top = G0 + 2 * FLOOR_H + 0.06;
  b.kind = 0;
  b.cyl(0.07, 0.1, 0.5, x, top, z - d * 0.1, GREY, 6);
  const r = Math.min(w, d) * (0.36 + 0.05 * v);
  // A dish: a funnel tilted towards the sky, with its feed horn.
  b.cyl(r, 0.06, r * 0.42, x, top + 0.5, z - d * 0.1, WHITE, 10);
  b.cyl(0.02, 0.02, r * 0.7, x, top + 0.5 + r * 0.2, z - d * 0.1, GREY, 4);
};

const mast: PartFn = ({ b, spec, mainTop }, x, z, w, d, v) => {
  plinthBox(b, x, z, w * 0.6, d * 0.6);
  b.kind = 0;
  latticeMast(b, x, G0, z, Math.min(w, d) * 0.8, Math.min(mainTop * 0.55, 4.2 + v * 0.8), spec.accent, { levels: 3, braces: false, thick: 0.04 });
};

const silo: PartFn = ({ b, spec }, x, z, w, d, v) => {
  plinthBox(b, x, z, w, d);
  b.kind = 0;
  const cnt = 2 + (v === 2 ? 1 : 0);
  const r = Math.min(w / (cnt * 2.1), d * 0.4);
  for (let i = 0; i < cnt; i++) {
    const h = 3.2 + ((i + v) % 2) * 0.9;
    const cx = x - ((cnt - 1) * r * 1.1) + i * r * 2.2;
    b.cyl(r, r, h, cx, G0, z, i % 2 ? WHITE : 0xe9eef2, 10);
    b.cyl(r * 1.04, r * 1.04, 0.08, cx, G0 + h * 0.6, z, spec.accent, 10);
    b.cone(r * 1.02, 0.5, cx, G0 + h, z, spec.accent, 10);
  }
  b.box(r * 2 * cnt * 1.05, 0.08, 0.12, x, G0 + 2.6, z - r * 1.0, DARK);
};

const tank: PartFn = ({ b, spec }, x, z, w, d, v) => {
  plinthBox(b, x, z, w, d);
  b.kind = 0;
  const r = Math.min(w, d) * 0.3;
  const spots: Array<[number, number]> = [[-0.5, -0.5], [0.5, -0.1], [-0.1, 0.5]];
  spots.slice(0, v === 0 ? 3 : 2).forEach(([dx, dz], i) => {
    const px = x + dx * r * 1.6;
    const pz = z + dz * r * 1.6;
    if (v === 2 && i === 0) {
      b.ico(r, px, G0 + r * 1.4, pz, WHITE, 1);
      for (let k = 0; k < 3; k++) b.cyl(0.04, 0.04, r * 1.3, px + Math.cos(k * 2.1) * r * 0.7, G0, pz + Math.sin(k * 2.1) * r * 0.7, GREY, 4);
    } else {
      b.cyl(r, r, 1.1, px, G0, pz, WHITE, 12);
      b.cyl(r * 1.02, r * 1.02, 0.1, px, G0 + 0.8, pz, spec.accent, 12);
      b.cyl(r * 0.9, r * 0.9, 0.06, px, G0 + 1.1, pz, GREY, 12);
    }
  });
};

const flare: PartFn = ({ b, mainTop }, x, z, w, d) => {
  plinthBox(b, x, z, w * 0.5, d * 0.5);
  b.kind = 0;
  const h = Math.min(mainTop * 0.6, 6);
  b.cyl(0.05, 0.1, h, x, G0, z, GREY, 6);
  bar(b, [x - 0.4, G0, z], [x, G0 + h * 0.6, z], 0.04, WHITE);
  bar(b, [x + 0.4, G0, z], [x, G0 + h * 0.6, z], 0.04, WHITE);
  b.cone(0.13, 0.6, x, G0 + h, z, 0xff9224, 6);
};

const pipes: PartFn = ({ b, spec }, x, z, w, d, v) => {
  b.kind = 0;
  for (let i = 0; i < 4; i++) b.box(0.08, 0.7, 0.08, x - w * 0.42 + i * w * 0.28, DECK_TOP, z, GREY);
  hcyl(b, 0.07, w * 0.95, x, DECK_TOP + 0.62, z - 0.1, spec.accent, "x", 6);
  hcyl(b, 0.07, w * 0.95, x, DECK_TOP + 0.62, z + 0.1, WHITE, "x", 6);
  if (v > 0) hcyl(b, 0.09, d * 0.9, x + w * 0.42, DECK_TOP + 0.3, z, DARK, "z", 6);
};

const turbineHall: PartFn = ({ b, spec }, x, z, w, d, v) => {
  plinthBox(b, x, z, w, d);
  b.kind = 0;
  const L = Math.max(w, d);
  const alongZ = d >= w;
  const bw = alongZ ? w * 0.84 : L * 0.94;
  const bd = alongZ ? L * 0.94 : d * 0.84;
  b.box(bw, 3 * FLOOR_H, bd, x, G0, z, 0xeaf0ea);
  b.kind = 1;
  b.box(alongZ ? bw * 1.01 : bw * 0.8, FLOOR_H, alongZ ? bd * 0.8 : bd * 1.01, x, G0 + 1.5 * FLOOR_H, z, spec.glass);
  b.kind = 2;
  b.box(bw * 1.04, 0.1, bd * 1.04, x, G0 + 3 * FLOOR_H, z, spec.accent);
  b.kind = 0;
  b.tilted(bw * 0.5, 0.06, bd * 1.0, x, G0 + 3 * FLOOR_H + 0.3, z, 0xdde5df, 0.0);
  b.cyl(0.1, 0.12, 1.1 + v * 0.3, x + (alongZ ? 0 : L * 0.3), G0 + 3 * FLOOR_H, z + (alongZ ? L * 0.3 : 0), GREY, 6);
  b.ico(0.22, x + (alongZ ? 0 : L * 0.3), G0 + 3 * FLOOR_H + 1.4, z + (alongZ ? L * 0.3 : 0), WHITE, 0);
};

const substation: PartFn = ({ b, spec }, x, z, w, d) => {
  b.kind = 0;
  b.box(w, 0.04, d, x, DECK_TOP, z, 0xc9d1c8);
  for (let i = 0; i < 3; i++) {
    const px = x - w * 0.3 + i * w * 0.3;
    b.box(w * 0.18, 0.4, d * 0.2, px, DECK_TOP + 0.04, z + d * 0.1, i === 1 ? spec.accent : GREY);
    b.cyl(0.03, 0.03, 0.3, px - 0.07, DECK_TOP + 0.44, z + d * 0.1, WHITE, 5);
    b.cyl(0.03, 0.03, 0.3, px + 0.07, DECK_TOP + 0.44, z + d * 0.1, WHITE, 5);
  }
  // Gantry: two pylons, a busbar and drops.
  for (const s of [-1, 1]) bar(b, [x + s * w * 0.46, DECK_TOP, z - d * 0.25], [x + s * w * 0.46, DECK_TOP + 1.3, z - d * 0.25], 0.07, DARK);
  bar(b, [x - w * 0.46, DECK_TOP + 1.25, z - d * 0.25], [x + w * 0.46, DECK_TOP + 1.25, z - d * 0.25], 0.05, spec.accent);
  bar(b, [x - w * 0.46, DECK_TOP + 1.05, z - d * 0.25], [x + w * 0.46, DECK_TOP + 1.05, z - d * 0.25], 0.04, DARK);
  for (const s of [-0.3, 0, 0.3]) bar(b, [x + s * w, DECK_TOP + 1.25, z - d * 0.25], [x + s * w, DECK_TOP + 0.5, z + d * 0.1], 0.03, WHITE);
};

const wind: PartFn = ({ b, spec, mainTop }, x, z, w, d, v) => {
  b.kind = 0;
  const h = Math.min(mainTop * 0.58, 4.4 + v * 0.5);
  b.cyl(w * 0.08 + 0.03, w * 0.18, 0.18, x, DECK_TOP, z, DARK, 8);
  b.cyl(0.05, 0.1, h, x, DECK_TOP + 0.18, z, WHITE, 8);
  const hy = DECK_TOP + 0.18 + h;
  b.box(0.16, 0.14, 0.3, x, hy - 0.05, z, WHITE);
  b.ico(0.08, x, hy, z + 0.17, spec.accent, 0);
  const L = Math.min(w, d) * 0.85;
  for (let i = 0; i < 3; i++) {
    const a = (i / 3) * Math.PI * 2 + v * 0.9;
    bar(b, [x, hy, z + 0.17], [x + Math.cos(a) * L, hy + Math.sin(a) * L, z + 0.17], 0.05, WHITE);
  }
};

const solar: PartFn = ({ b }, x, z, w, d, v) => {
  b.kind = 0;
  b.box(w, 0.03, d, x, DECK_TOP, z, 0xb7c9a0);
  const cols = 3;
  const rows = 2;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      const px = x - w * 0.34 + c * w * 0.34;
      const pz = z - d * 0.22 + r * d * 0.44;
      b.tilted(w * 0.3, 0.05, d * 0.36, px, DECK_TOP + 0.28 + v * 0.02, pz, 0x1d5fb0, -0.5);
      b.box(0.04, 0.26, 0.04, px, DECK_TOP, pz + 0.02, GREY);
    }
  }
};

const cooling: PartFn = ({ b, spec }, x, z, w, d) => {
  const r = Math.min(w, d) * 0.5;
  const h = 4.2;
  loft(b, { plan: "ellipse", w: r * 2, d: r * 2, cx: x, cz: z, y0: DECK_TOP, h, hex: 0xe8e4dc, kind: 0, ts: [0, 0.18, 0.36, 0.54, 0.72, 0.86, 1], scale: (t) => Math.sqrt(0.4356 + 1.089 * (t - 0.72) * (t - 0.72)), cap: 0xd6d2c8, capKind: 0 });
  b.kind = 2;
  b.cyl(r * 0.74, r * 0.74, 0.07, x, DECK_TOP + h, z, spec.accent, 12);
  b.kind = 0;
  b.ico(r * 0.5, x, DECK_TOP + h + r * 0.45, z, WHITE, 1);
};

const heap: PartFn = ({ b }, x, z, w, d, v) => {
  b.kind = 0;
  const cols = [0xb88b58, 0x9c7244, 0xd49b4b];
  for (let i = 0; i < 2 + (v === 1 ? 1 : 0); i++) {
    const r = Math.min(w, d) * (0.5 - i * 0.1);
    b.cone(r, 1.3 - i * 0.3, x + (i - 0.5) * w * 0.32, DECK_TOP, z + (i % 2) * d * 0.15, cols[(i + v) % 3], 8);
  }
  b.box(0.34, 0.2, 0.2, x + w * 0.4, DECK_TOP + 0.05, z + d * 0.38, 0xf0b938);
  b.box(0.16, 0.14, 0.16, x + w * 0.4, DECK_TOP + 0.25, z + d * 0.38, DARK);
};

const processing: PartFn = ({ b, spec }, x, z, w, d, v) => {
  plinthBox(b, x, z, w, d);
  b.kind = 0;
  b.box(w * 0.7, 4 * FLOOR_H, d * 0.7, x, G0, z, spec.accent);
  b.box(w * 0.74, 0.08, d * 0.74, x, G0 + 4 * FLOOR_H, z, DARK);
  b.cyl(w * 0.14, w * 0.18, 2.2 + v * 0.4, x + w * 0.3, G0, z - d * 0.2, WHITE, 8);
  b.box(w * 0.22, 0.4, d * 0.22, x - w * 0.2, G0 + 4 * FLOOR_H + 0.08, z, GREY);
};

const conveyor: PartFn = ({ b, spec }, x, z, w, d) => {
  b.kind = 0;
  bar(b, [x - w * 0.45, DECK_TOP + 0.2, z + d * 0.4], [x + w * 0.45, DECK_TOP + 1.7, z - d * 0.4], 0.2, DARK);
  for (let i = 0; i < 3; i++) {
    const t = (i + 0.5) / 3;
    const px = x - w * 0.45 + t * w * 0.9;
    const pz = z + d * 0.4 - t * d * 0.8;
    bar(b, [px, DECK_TOP, pz], [px, DECK_TOP + 0.2 + t * 1.5, pz], 0.06, spec.accent);
  }
  b.box(0.4, 0.3, 0.4, x + w * 0.45, DECK_TOP + 1.7, z - d * 0.4, spec.accent);
};

const cube: PartFn = ({ b, spec }, x, z, w, d, v) => {
  b.kind = 0;
  b.cyl(Math.min(w, d) * 0.45, Math.min(w, d) * 0.5, 0.1, x, DECK_TOP, z, 0x24293e, 6);
  const cols = [0x3ef2de, 0xf58cff, 0xffd24a];
  for (let i = 0; i < 3; i++) {
    const s = 0.34 - i * 0.07;
    const a = i * 2.1 + v;
    b.box(s, s, s, x + Math.cos(a) * w * 0.26, DECK_TOP + 0.45 + i * 0.34, z + Math.sin(a) * d * 0.26, cols[(i + v) % 3], a);
  }
  b.kind = 2;
  b.cyl(0.03, 0.03, 0.9, x, DECK_TOP + 0.1, z, spec.accent, 5);
};

const vault: PartFn = ({ b, spec }, x, z, w, d) => {
  plinthBox(b, x, z, w, d);
  b.kind = 0;
  b.box(w * 0.9, 3 * FLOOR_H, d * 0.84, x, G0, z, 0xd8d2c4);
  b.kind = 2;
  b.box(w * 0.96, 0.1, d * 0.9, x, G0 + 3 * FLOOR_H, z, spec.accent);
  b.kind = 0;
  hcyl(b, w * 0.22, 0.12, x, G0 + 0.7, z + d * 0.43, GOLD, "z", 14);
  hcyl(b, w * 0.1, 0.16, x, G0 + 0.7, z + d * 0.43, GREY, "z", 10);
};

const colonnade: PartFn = ({ b, spec }, x, z, w, d) => {
  b.kind = 0;
  b.box(w, 0.1, d * 0.8, x, DECK_TOP, z, 0xece4d2);
  b.box(w * 0.94, 0.07, d * 0.7, x, DECK_TOP + 0.1, z, WHITE);
  for (let i = 0; i < 6; i++) b.cyl(0.08, 0.1, 1.15, x - w * 0.4 + i * w * 0.16, DECK_TOP + 0.17, z, WHITE, 8);
  b.kind = 2;
  b.box(w * 0.98, 0.14, d * 0.6, x, DECK_TOP + 1.32, z, spec.accent);
  b.pyramid(w * 0.5, 0.3, x, DECK_TOP + 1.46, z, GOLD);
  void DECK;
};

const PARTS: Record<PartKind, PartFn> = {
  plaza, pavilion, annex, hall, carpark, garden, mall, wing, dish, mast, silo, tank, flare, pipes, turbineHall,
  substation, wind, solar, cooling, chimney: silo, heap, processing, conveyor, cube, vault, colonnade,
};

export function buildPart(kind: PartKind, c: PartCtx, x: number, z: number, w: number, d: number, variant: number) {
  PARTS[kind](c, x, z, w, d, variant);
  c.b.kind = 0;
}
