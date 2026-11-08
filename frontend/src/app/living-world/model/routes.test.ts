import { describe, expect, it } from "vitest";
import { demoAssets } from "./fixtures";
import { LOT_PITCH, computeLayout, toLocal } from "./townLayout";
import { MAX_FOOTPRINT } from "./scale";
import { pointAlong, routeLength, routeToPlaza, type Point } from "./routes";

const assets = demoAssets();
const layout = computeLayout(assets);
const half = MAX_FOOTPRINT / 2;

/** Does the segment (in a district's own axes) pass through another holding's largest building? */
function crossesBuilding(a: Point, b: Point, ignore: string, district: string): boolean {
  for (const lot of layout.lots.values()) {
    if (lot.assetId === ignore || lot.district !== district) continue;
    const minX = Math.min(a.x, b.x);
    const maxX = Math.max(a.x, b.x);
    const minZ = Math.min(a.z, b.z);
    const maxZ = Math.max(a.z, b.z);
    if (maxX > lot.lx - half && minX < lot.lx + half && maxZ > lot.lz - half && minZ < lot.lz + half) return true;
  }
  return false;
}

describe("routeToPlaza", () => {
  it("never cuts through another building on the way out of the district", () => {
    for (const lot of layout.lots.values()) {
      const d = layout.districts.find((x) => x.id === lot.district)!;
      const r = routeToPlaza(lot, d).map((p) => toLocal(d, p.x, p.z));
      // Legs inside the district grid are axis-aligned in its own axes; the boulevard is separate.
      for (let i = 1; i < r.length - 1; i++) {
        expect(crossesBuilding(r[i - 1], r[i], lot.assetId, lot.district), `${lot.assetId} leg ${i}`).toBe(false);
      }
    }
  });

  it("starts at the lot, ends on the plaza ring, and keeps the district legs axis-aligned", () => {
    for (const lot of layout.lots.values()) {
      const d = layout.districts.find((x) => x.id === lot.district)!;
      const r = routeToPlaza(lot, d);
      expect(r[0]).toEqual({ x: lot.x, z: lot.z });
      expect(Math.hypot(r.at(-1)!.x, r.at(-1)!.z)).toBeLessThan(16);
      const local = r.map((p) => toLocal(d, p.x, p.z));
      for (let i = 1; i < local.length - 1; i++) {
        const same = Math.abs(local[i].x - local[i - 1].x) < 1e-6 || Math.abs(local[i].z - local[i - 1].z) < 1e-6;
        expect(same, `${lot.assetId} leg ${i}`).toBe(true);
      }
    }
  });

  it("uses the street gap, half a pitch from the lot centre", () => {
    const lot = [...layout.lots.values()][0];
    const d = layout.districts.find((x) => x.id === lot.district)!;
    const r = routeToPlaza(lot, d);
    expect(Math.hypot(r[1].x - r[0].x, r[1].z - r[0].z)).toBeCloseTo(LOT_PITCH / 2, 6);
  });
});

describe("pointAlong", () => {
  const path: Point[] = [{ x: 0, z: 0 }, { x: 10, z: 0 }, { x: 10, z: 10 }];
  it("walks the polyline and clamps at both ends", () => {
    expect(routeLength(path)).toBe(20);
    expect(pointAlong(path, 5)).toMatchObject({ x: 5, z: 0 });
    expect(pointAlong(path, 15)).toMatchObject({ x: 10, z: 5 });
    expect(pointAlong(path, 99)).toMatchObject({ x: 10, z: 10 });
    expect(pointAlong(path, -4)).toMatchObject({ x: 0, z: 0 });
  });

  it("reports the heading of the current leg", () => {
    expect(pointAlong(path, 5).heading).toBeCloseTo(Math.PI / 2);
    expect(pointAlong(path, 15).heading).toBeCloseTo(0);
  });
});
