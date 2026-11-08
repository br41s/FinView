import { valueNoise } from "./rng";

/**
 * The land under the town (pure): a sea around an island, a lake in the mountain foot, a
 * river that bends round the central square and reaches the sea, a plateau for the funds
 * and treasury districts, and a mountain range behind it. Everything is a function of a few
 * numbers the layout derives from the holdings, so a price refresh can never move a hill.
 */

export interface Pt {
  x: number;
  z: number;
}

/** Water surface. The ground is carved below it for the sea, the lake and the river. */
export const WATER_Y = -0.45;
export const PLATEAU_HEIGHT = 9;
export const RIVER_HALF_WIDTH = 5;

export interface TerrainSpec {
  /** Radius of the urban area; the coast sits a little beyond it. */
  cityRadius: number;
  plazaRadius: number;
  /** Plateau: an annular sector centred on `plateauAngle`. */
  plateauAngle: number;
  plateauHalfAngle: number;
  plateauInner: number;
  plateauOuter: number;
  /** River centre line (already smooth) and the lake it starts from. */
  river: Pt[];
  lake: { x: number; z: number; r: number };
  seed: number;
}

export interface Terrain {
  spec: TerrainSpec;
  /** Ground height, including the carved riverbed, lake and seabed. */
  heightAt(x: number, z: number): number;
  /** Where a road or a vehicle runs: the ground, but flat across water (a bridge). */
  roadY(x: number, z: number): number;
  isWater(x: number, z: number): boolean;
  /** Flat, dry and gentle enough to build on, with `margin` of room around the point. */
  buildable(x: number, z: number, margin?: number): boolean;
  /** Bounding half-extent of the terrain mesh. */
  extent: number;
  /** Distance from the river centre line (Infinity without a river). */
  riverDistance(x: number, z: number): number;
}

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

function angleDiff(a: number, b: number): number {
  let d = a - b;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  return d;
}

export function distToPolyline(px: number, pz: number, line: readonly Pt[]): number {
  let best = Infinity;
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1];
    const b = line[i];
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const l2 = dx * dx + dz * dz;
    const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - a.x) * dx + (pz - a.z) * dz) / l2));
    const d = Math.hypot(px - (a.x + t * dx), pz - (a.z + t * dz));
    if (d < best) best = d;
  }
  return best;
}

/** One Chaikin pass rounds every corner of a polyline, keeping its ends. */
export function chaikin(line: readonly Pt[], passes = 2): Pt[] {
  let out = [...line];
  for (let k = 0; k < passes; k++) {
    const next: Pt[] = [out[0]];
    for (let i = 1; i < out.length; i++) {
      const a = out[i - 1];
      const b = out[i];
      next.push({ x: a.x * 0.75 + b.x * 0.25, z: a.z * 0.75 + b.z * 0.25 });
      next.push({ x: a.x * 0.25 + b.x * 0.75, z: a.z * 0.25 + b.z * 0.75 });
    }
    next.push(out[out.length - 1]);
    out = next;
  }
  return out;
}

export function createTerrain(spec: TerrainSpec): Terrain {
  const { cityRadius, plateauAngle, plateauHalfAngle, plateauInner, plateauOuter, river, lake, seed } = spec;
  const mountainStart = plateauOuter + 14;
  // Land runs on beyond the town towards the mountains, and ends in the sea elsewhere.
  const extent = mountainStart + 110;

  const coast = (angle: number) => {
    const toward = Math.max(0, Math.cos(angleDiff(angle, plateauAngle)));
    return cityRadius + 20 + valueNoise(angle * 2.2 + 40, 0, seed) * 9 + toward * toward * 120;
  };

  function raw(x: number, z: number): number {
    const r = Math.hypot(x, z);
    const angle = Math.atan2(z, x);
    let h = 0;

    // Plateau: flat top, a gentle ramp on the plaza side and a steeper one on the others.
    const da = Math.abs(angleDiff(angle, plateauAngle));
    const wa = 1 - smooth(plateauHalfAngle - 0.04, plateauHalfAngle + 0.1, da);
    const wr = smooth(plateauInner - 18, plateauInner, r) * (1 - smooth(plateauOuter, plateauOuter + 16, r));
    const plateau = PLATEAU_HEIGHT * wa * wr;

    // Mountains behind the plateau: a shelf at plateau height, then ridges and peaks.
    const wm = Math.max(0, Math.cos(angleDiff(angle, plateauAngle) * 0.9)) ** 2;
    const ridge = 1 - Math.abs(valueNoise(x * 0.035, z * 0.035, seed + 3) * 2 - 1);
    const detail = valueNoise(x * 0.11, z * 0.11, seed + 9);
    const peaks = 16 + Math.max(0, ridge - 0.2) * 66 + detail * 8;
    const rise = smooth(mountainStart - 6, mountainStart + 70, r);
    const mountain = wm * (smooth(mountainStart - 14, mountainStart, r) * (PLATEAU_HEIGHT - 0.5) + rise * peaks);

    h = Math.max(plateau, mountain);

    // The sea.
    h -= 4.4 * smooth(coast(angle) - 8, coast(angle) + 12, r);

    // River and lake carve the ground; the lake is a little deeper and rounder.
    const rd = distToPolyline(x, z, river);
    const cr = 1 - smooth(RIVER_HALF_WIDTH * 0.55, RIVER_HALF_WIDTH * 1.7, rd);
    h = h * (1 - cr) + -2.1 * cr;
    const ld = Math.hypot(x - lake.x, z - lake.z);
    const cl = 1 - smooth(lake.r * 0.7, lake.r * 1.3, ld);
    h = h * (1 - cl) + -2.4 * cl;
    return h;
  }

  const heightAt = (x: number, z: number) => raw(x, z);
  const roadY = (x: number, z: number) => Math.max(0, raw(x, z));
  const isWater = (x: number, z: number) => raw(x, z) < WATER_Y + 0.05;

  function buildable(x: number, z: number, margin = 0): boolean {
    const c = raw(x, z);
    if (c < -0.05) return false;
    const m = Math.max(1, margin);
    for (const [dx, dz] of [[m, 0], [-m, 0], [0, m], [0, -m]] as const) {
      const h = raw(x + dx, z + dz);
      if (h < -0.05 || Math.abs(h - c) > 1.1) return false;
    }
    return true;
  }

  return {
    spec,
    heightAt,
    roadY,
    isWater,
    buildable,
    extent,
    riverDistance: (x, z) => distToPolyline(x, z, river),
  };
}
