import { describe, expect, it } from "vitest";
import { demoAssets } from "./fixtures";
import { computeLayout } from "./townLayout";
import { distToSegment } from "./cityGeometry";
import { pointAlong, routeLength, routeToPlaza, type Point } from "./routes";

const layout = computeLayout(demoAssets());

describe("routeToPlaza", () => {
  it("starts at each company and ends on the central plaza edge", () => {
    for (const lot of layout.lots.values()) {
      const district = layout.districts.find((item) => item.id === lot.district)!;
      const route = routeToPlaza(lot, district, layout);
      expect(route[0]).toEqual({ x: lot.x, z: lot.z });
      expect(Math.hypot(route.at(-1)!.x, route.at(-1)!.z)).toBeLessThan(16);
      expect(route.length).toBeGreaterThan(3);
      expect(route.every((point) => Number.isFinite(point.x) && Number.isFinite(point.z))).toBe(true);
    }
  });

  it("follows the street graph: every leg between nodes lies on a road", () => {
    const lot = [...layout.lots.values()][0];
    const district = layout.districts.find((item) => item.id === lot.district)!;
    const route = routeToPlaza(lot, district, layout);
    // Skip the door leg (lot centre to the street) and the last step onto the plaza.
    for (let i = 2; i < route.length - 2; i++) {
      const mid = { x: (route[i].x + route[i + 1].x) / 2, z: (route[i].z + route[i + 1].z) / 2 };
      const onRoad = layout.roads.some((r) => distToSegment(mid, { x: r.x1, z: r.z1 }, { x: r.x2, z: r.z2 }) < 0.01);
      expect(onRoad).toBe(true);
    }
  });

  it("takes a sensible way: no longer than a Manhattan detour of the straight line", () => {
    for (const lot of layout.lots.values()) {
      const district = layout.districts.find((item) => item.id === lot.district)!;
      const route = routeToPlaza(lot, district, layout);
      const manhattan = Math.abs(lot.x) + Math.abs(lot.z);
      expect(routeLength(route)).toBeLessThan(manhattan + 140);
    }
  });

  it("includes green spaces and a pond in the urban layout", () => {
    expect(layout.greenSpaces.some((space) => space.kind === "city-park" && space.pond)).toBe(true);
    expect(layout.greenSpaces.some((space) => space.kind === "pocket-park")).toBe(true);
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
