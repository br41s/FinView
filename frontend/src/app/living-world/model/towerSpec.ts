import { hashString, seeded } from "./rng";
import type { Tier } from "./scale";
import type { Archetype } from "./types";

/**
 * What a portfolio holding looks like, decided from three things only: its archetype, its id
 * (an ISIN: hashed, so it never changes when the price does) and its size tier. Weight never
 * reaches this module, so a price move cannot redraw a building; only a tier change can, and it
 * then only ADDS parts (every tier's parts are a prefix of the next one's).
 *
 * Pure data, no Three.js: `engine/towers.ts` turns a spec into geometry.
 */

/** Window rows per local unit of the site material; a storey is exactly 1/ROWS tall. */
export const FACADE_ROWS = 2.6;
export const FLOOR_H = 1 / FACADE_ROWS;

export type Family =
  | "twist" // rotating floorplan
  | "egg" // gherkin: lathe profile with a diagrid
  | "stepped" // setbacks
  | "cylinder" // round tower with a helipad ring
  | "slab" // twin slabs with a sky-bridge
  | "needle" // lattice / spire
  | "dome" // rotunda
  | "stadium" // arena bowl
  | "stack" // power-plant / refinery skyline
  | "crystal"; // faceted monolith

export type Plan = "rect" | "rounded" | "ellipse" | "super" | "hex";
export type Crown = "flat" | "helipad" | "spire" | "antenna" | "pinnacle" | "dome";

/** Where an extra part goes on the plot: the engine maps a zone to slots. */
export type Zone = "front" | "flank" | "back";

export type PartKind =
  | "plaza"
  | "pavilion"
  | "annex"
  | "hall"
  | "carpark"
  | "garden"
  | "mall"
  | "wing"
  | "dish"
  | "mast"
  | "silo"
  | "tank"
  | "flare"
  | "pipes"
  | "turbineHall"
  | "substation"
  | "wind"
  | "solar"
  | "cooling"
  | "chimney"
  | "heap"
  | "processing"
  | "conveyor"
  | "cube"
  | "vault"
  | "colonnade";

export const PART_ZONE: Record<PartKind, Zone> = {
  plaza: "front",
  pavilion: "front",
  carpark: "front",
  garden: "front",
  mall: "front",
  colonnade: "front",
  solar: "front",
  pipes: "front",
  cube: "front",
  annex: "back",
  silo: "back",
  tank: "back",
  flare: "back",
  substation: "back",
  cooling: "back",
  chimney: "back",
  mast: "back",
  heap: "back",
  hall: "flank",
  wing: "flank",
  dish: "flank",
  turbineHall: "flank",
  wind: "flank",
  processing: "flank",
  conveyor: "flank",
  vault: "flank",
};

/** Extra parts by tier: outpost 1, small 3, campus 5, major 7 (the main structure always stands). */
export const EXTRA_COUNT: Record<Tier, number> = { outpost: 1, small: 3, campus: 5, major: 7 };

/** Height of the tallest element, in local (nominal) units, by tier. Outposts already clear every filler. */
export const HEIGHT_RANGE: Record<Tier, readonly [number, number]> = {
  outpost: [8.4, 9.8],
  small: [11, 13.4],
  campus: [15, 19],
  major: [22, 30],
};

/**
 * Families whose tallest element is a mast or a spire, not the building: they stand shorter than a
 * tower of their tier, so a stadium is not drawn as four needles. Still above every filler (tested).
 */
export const FAMILY_HEIGHT: Partial<Record<Family, number>> = { stadium: 0.7, dome: 0.88 };

/** Base width of the main structure as a share of the nominal footprint. */
const WIDTH_FRAC: Record<Tier, readonly [number, number]> = {
  outpost: [0.36, 0.42],
  small: [0.32, 0.38],
  campus: [0.3, 0.36],
  major: [0.28, 0.34],
};

const MAIN_POOL: Record<Archetype, readonly Family[]> = {
  tech: ["twist", "egg", "cylinder", "slab"],
  semis: ["slab", "stepped", "crystal"],
  banking: ["stepped", "slab", "twist", "egg"],
  telecom: ["needle", "cylinder"],
  health: ["slab", "cylinder", "stepped"],
  retail: ["stepped", "cylinder", "dome"],
  consumer: ["cylinder", "stepped", "stack"],
  realestate: ["twist", "stepped", "slab"],
  energy: ["stack"],
  utilities: ["stack"],
  mining: ["needle", "stack"],
  fund: ["dome", "stadium"],
  crypto: ["crystal", "twist"],
  cash: ["stepped", "dome"],
};

/** The complex of each archetype, in the order it grows. A tier shows the first `EXTRA_COUNT` of them. */
const EXTRAS: Record<Archetype, readonly PartKind[]> = {
  tech: ["plaza", "pavilion", "annex", "hall", "pavilion", "annex", "garden"],
  semis: ["hall", "silo", "plaza", "hall", "annex", "pipes", "pavilion"],
  banking: ["hall", "plaza", "annex", "pavilion", "garden", "annex", "colonnade"],
  telecom: ["dish", "hall", "mast", "dish", "plaza", "mast", "hall"],
  health: ["wing", "plaza", "wing", "garden", "annex", "pavilion", "wing"],
  retail: ["mall", "carpark", "annex", "plaza", "carpark", "pavilion", "mall"],
  consumer: ["silo", "hall", "carpark", "silo", "plaza", "hall", "tank"],
  realestate: ["annex", "garden", "annex", "pavilion", "plaza", "annex", "garden"],
  energy: ["tank", "flare", "pipes", "tank", "hall", "tank", "substation"],
  utilities: ["turbineHall", "substation", "wind", "solar", "wind", "cooling", "solar"],
  mining: ["processing", "heap", "conveyor", "silo", "heap", "tank", "hall"],
  fund: ["plaza", "pavilion", "garden", "pavilion", "colonnade", "garden", "pavilion"],
  crypto: ["cube", "plaza", "cube", "annex", "cube", "plaza", "annex"],
  cash: ["vault", "plaza", "carpark", "annex", "vault", "garden", "plaza"],
};

/** Accent hues (0..1) an archetype draws from; the id picks one and nudges it. */
const HUES: Record<Archetype, readonly number[]> = {
  tech: [0.55, 0.62, 0.74, 0.48],
  semis: [0.5, 0.58, 0.8, 0.42],
  banking: [0.6, 0.66, 0.1, 0.52],
  telecom: [0.58, 0.9, 0.45, 0.68],
  health: [0.47, 0.38, 0.97, 0.55],
  retail: [0.98, 0.08, 0.92, 0.13],
  consumer: [0.08, 0.14, 0.02, 0.35],
  realestate: [0.06, 0.78, 0.5, 0.12],
  energy: [0.06, 0.02, 0.12, 0.58],
  utilities: [0.33, 0.4, 0.52, 0.16],
  mining: [0.1, 0.07, 0.13, 0.04],
  fund: [0.58, 0.12, 0.45, 0.75],
  crypto: [0.82, 0.5, 0.92, 0.45],
  cash: [0.12, 0.14, 0.38, 0.1],
};

/** Curtain-wall tints (hex) an archetype draws from. */
const GLASSES: Record<Archetype, readonly number[]> = {
  tech: [0x58c4ff, 0x45d6cc, 0x7fa6ff, 0x6fe0ff],
  semis: [0x6fd0ff, 0x8fb4ff, 0x59e0d2],
  banking: [0x4f9ae8, 0x3fb5c8, 0x6e8cf0, 0x58b8ff],
  telecom: [0x58b8ff, 0x7ac8ff, 0x5ad0e0],
  health: [0x6fdcd6, 0x7ad8f0, 0x8be6c8],
  retail: [0x6fc8ff, 0xffc27a, 0x9fd8ff],
  consumer: [0x7ad0f0, 0xffc88a, 0x8be0c8],
  realestate: [0x78c8ff, 0xf5c89a, 0x86d6e0],
  energy: [0x6fc0e8, 0x9ad6f0],
  utilities: [0x7ad8c4, 0x6fc8f0, 0x8fe0b0],
  mining: [0x8cc4d8, 0xe0c090],
  fund: [0x8fd0ff, 0xa8d8f0, 0x7ac8e0],
  crypto: [0x7affe8, 0xd08cff, 0x6fb8ff],
  cash: [0x9fd0e0, 0xe8d090],
};

/** Hex of an HSL colour (all components 0..1). Pure, so the model needs no Three.js. */
export function hslHex(h: number, s: number, l: number): number {
  const hh = ((h % 1) + 1) % 1;
  const f = (n: number) => {
    const k = (n + hh * 12) % 12;
    const a = s * Math.min(l, 1 - l);
    return l - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  };
  const to = (x: number) => Math.round(Math.min(1, Math.max(0, x)) * 255);
  return (to(f(0)) << 16) | (to(f(8)) << 8) | to(f(4));
}

/** The accent of a holding: an archetype hue picked and nudged by its id. Stable across price updates. */
export function accentColour(archetype: Archetype, id: string): number {
  const r = seeded(hashString(id + ":accent"));
  const hues = HUES[archetype];
  const hue = hues[Math.floor(r() * hues.length)] + (r() - 0.5) * 0.07;
  return hslHex(hue, 0.66 + r() * 0.16, 0.46 + r() * 0.08);
}

export interface MainSpec {
  family: Family;
  plan: Plan;
  /** Depth over width of the base. */
  aspect: number;
  /** Width of the base, in local units (nominal footprint x share). */
  width: number;
  /** Height of the tallest element and the storeys of the main shaft (a storey is FLOOR_H). */
  height: number;
  floors: number;
  /** Scale of the top over the base (1 = straight). */
  taper: number;
  /** Total rotation of the floorplan from base to top, radians (twist family; 0 otherwise). */
  twist: number;
  /** Setbacks (stepped family). */
  steps: number;
  crown: Crown;
  diagrid: boolean;
  /** Twin slabs joined by a sky-bridge (slab family). */
  bridge: boolean;
  /** Chimneys of a stack complex. */
  chimneys: number;
  /** Rotation of the shaft about its axis. */
  rotation: number;
}

export interface PartSpec {
  kind: PartKind;
  zone: Zone;
  /** 0..2, picked from the id: which flavour of the part is built. */
  variant: number;
}

export interface TowerSpec {
  id: string;
  archetype: Archetype;
  tier: Tier;
  main: MainSpec;
  parts: PartSpec[];
  /** Flips the complex left to right. */
  mirror: boolean;
  accent: number;
  glass: number;
}

const PLANS: Record<Family, readonly Plan[]> = {
  twist: ["rounded", "super", "rect"],
  egg: ["ellipse"],
  stepped: ["rect", "rounded"],
  cylinder: ["ellipse"],
  slab: ["rect", "rounded"],
  needle: ["rect", "hex"],
  dome: ["ellipse"],
  stadium: ["ellipse", "super"],
  stack: ["ellipse"],
  crystal: ["hex"],
};

const CROWNS: Record<Family, readonly Crown[]> = {
  twist: ["spire", "antenna", "flat"],
  egg: ["pinnacle", "spire"],
  stepped: ["pinnacle", "spire", "antenna"],
  cylinder: ["helipad"],
  slab: ["flat", "antenna", "helipad"],
  needle: ["antenna"],
  dome: ["spire"],
  stadium: ["antenna"],
  stack: ["flat"],
  crystal: ["pinnacle", "spire"],
};

function pick<T>(r: () => number, xs: readonly T[]): T {
  return xs[Math.floor(r() * xs.length) % xs.length];
}

/**
 * The spec of one holding. `accentOverride` lets a brand colour win over the archetype palette.
 * Same (archetype, id, tier) always gives the same spec.
 */
export function towerSpec(archetype: Archetype, id: string, tier: Tier, accentOverride?: number): TowerSpec {
  const r = seeded(hashString(id + ":main"));
  const family = pick(r, MAIN_POOL[archetype]);
  const [h0, h1] = HEIGHT_RANGE[tier];
  const [w0, w1] = WIDTH_FRAC[tier];
  const height = (h0 + (h1 - h0) * r()) * (FAMILY_HEIGHT[family] ?? 1);
  const plan = pick(r, PLANS[family]);
  const taperBase = family === "twist" ? 0.6 + r() * 0.22 : family === "crystal" ? 0.5 + r() * 0.2 : family === "egg" ? 1 : 0.84 + r() * 0.14;
  const main: MainSpec = {
    family,
    plan,
    aspect: 0.74 + r() * 0.26,
    width: 0, // filled by the engine from the nominal footprint: it knows `n`
    height,
    floors: Math.max(4, Math.round(height / FLOOR_H)),
    taper: family === "stack" || family === "dome" || family === "stadium" ? 1 : taperBase,
    twist: family === "twist" ? (0.9 + r() * 1.3) * (r() < 0.5 ? -1 : 1) : 0,
    steps: 3 + Math.floor(r() * 3),
    crown: pick(r, CROWNS[family]),
    diagrid: family === "egg" || (family === "crystal" && r() < 0.5) || (family === "cylinder" && r() < 0.4),
    bridge: family === "slab",
    chimneys: archetype === "utilities" || archetype === "energy" ? (tier === "outpost" || tier === "small" ? 1 : tier === "campus" ? 2 : 3) : 1,
    rotation: r() * Math.PI * 2,
  };
  // The width is stored as a share; the engine multiplies by the nominal footprint.
  main.width = w0 + (w1 - w0) * r();

  const pr = seeded(hashString(id + ":parts"));
  // Draw every part's variant first and slice after, so a part looks the same at every tier.
  const parts = EXTRAS[archetype]
    .map((kind): PartSpec => ({ kind, zone: PART_ZONE[kind], variant: Math.floor(pr() * 3) }))
    .slice(0, EXTRA_COUNT[tier]);

  const accent = accentOverride ?? accentColour(archetype, id);
  const glass = pick(seeded(hashString(id + ":glass")), GLASSES[archetype]);
  return { id, archetype, tier, main, parts, mirror: seeded(hashString(id + ":mirror"))() < 0.5, accent, glass };
}

