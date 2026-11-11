/**
 * The land under the town (pure). The city is flat: the only relief is a canal, a trench
 * cut into a level plain. The canal is a function of the street template only (never of the
 * holdings), so nothing under a building can move.
 */

export interface Pt {
  x: number;
  z: number;
}

/** Water surface. The ground is carved below it along the canal. */
export const WATER_Y = -0.45;
/** Depth of the canal bed below the plain. */
export const CANAL_DEPTH = 1.7;

export interface TerrainSpec {
  /** Canal centre line (axis-aligned legs) and its half width at the water line. */
  canal: Pt[];
  canalHalfWidth: number;
  /** Half extent of the land; the canal runs out to it on both ends. */
  extent: number;
}

export interface Terrain {
  spec: TerrainSpec;
  /** Ground height: 0 everywhere except the canal bed. */
  heightAt(x: number, z: number): number;
  /** Where a road or a vehicle runs: the ground, but flat across water (a bridge). */
  roadY(x: number, z: number): number;
  isWater(x: number, z: number): boolean;
  /** Dry and clear of the canal bank, with `margin` of room around the point. */
  buildable(x: number, z: number, margin?: number): boolean;
  /** Bounding half-extent of the terrain mesh. */
  extent: number;
  /** Distance from the canal centre line. */
  canalDistance(x: number, z: number): number;
  /** Sample coordinates for the ground mesh: coarse on the plain, fine across the canal. */
  groundAxes(): { xs: number[]; zs: number[] };
}

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

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
  const { canal, canalHalfWidth: hw, extent } = spec;

  const canalDistance = (x: number, z: number) => distToPolyline(x, z, canal);
  function heightAt(x: number, z: number): number {
    const d = canalDistance(x, z);
    if (d > hw + 3) return 0;
    // Bed flat under the water, banks sloping up to the plain in about 3 units.
    return -CANAL_DEPTH * (1 - smooth(hw - 1.5, hw + 2.2, d));
  }

  function groundAxes() {
    const coarse = 14;
    const xs = new Set<number>();
    const zs = new Set<number>();
    for (let v = -extent; v <= extent + 1e-6; v += coarse) {
      xs.add(Math.round(v * 4) / 4);
      zs.add(Math.round(v * 4) / 4);
    }
    // Fine lines across every axis-aligned canal leg (and a little past its ends).
    for (let i = 1; i < canal.length; i++) {
      const a = canal[i - 1];
      const b = canal[i];
      const vertical = Math.abs(a.x - b.x) < 1e-6;
      const c = vertical ? a.x : a.z;
      const axis = vertical ? xs : zs;
      for (let o = -hw - 5; o <= hw + 5 + 1e-6; o += 0.75) axis.add(Math.round((c + o) * 4) / 4);
    }
    const sort = (s: Set<number>) => [...s].sort((p, q) => p - q);
    return { xs: sort(xs), zs: sort(zs) };
  }

  return {
    spec,
    heightAt,
    roadY: (x, z) => Math.max(0, heightAt(x, z)),
    isWater: (x, z) => heightAt(x, z) < WATER_Y + 0.05,
    buildable: (x, z, margin = 0) => canalDistance(x, z) > hw + 2.2 + margin,
    extent,
    canalDistance,
    groundAxes,
  };
}
