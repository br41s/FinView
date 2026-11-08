import { describe, expect, it } from "vitest";
import { demoAssets } from "./fixtures";
import { computeLayout } from "./townLayout";
import { pointAlong, routeLength, routeToPlaza, type Point } from "./routes";

const layout = computeLayout(demoAssets());

describe("routeToPlaza", () => {
  it("starts at each company and ends on the central plaza edge", () => {
    for (const lot of layout.lots.values()) {
      const district = layout.districts.find((item) => item.id === lot.district)!;
      const route = routeToPlaza(lot, district, layout.roads);
      expect(route[0]).toEqual({ x: lot.x, z: lot.z });
      expect(Math.hypot(route.at(-1)!.x, route.at(-1)!.z)).toBeLessThan(16);
      expect(route.length).toBeGreaterThan(7);
      expect(route.every((point) => Number.isFinite(point.x) && Number.isFinite(point.z))).toBe(true);
    }
  });

  it("uses each district loop and its boulevard to reach the shared arterial", () => {
    for (const district of layout.districts) {
      const local = layout.roads.find((road) => road.kind === "local" && road.districtId === district.id);
      const boulevard = layout.roads.find((road) => road.kind === "boulevard" && road.districtId === district.id);
      expect(local, district.id).toBeDefined();
      expect(boulevard, district.id).toBeDefined();
      expect(local!.path[0]).toEqual(local!.path.at(-1));
      expect(boulevard!.path[0]).toEqual(layout.roads.find((road) => road.kind === "arterial")!.path.reduce((best, point) =>
        Math.hypot(point.x - boulevard!.path[0].x, point.z - boulevard!.path[0].z) <
        Math.hypot(best.x - boulevard!.path[0].x, best.z - boulevard!.path[0].z) ? point : best
      ));
      expect(boulevard!.path.length).toBeGreaterThan(3);
    }
  });

  it("keeps routes meaningfully curved rather than drawing a diagonal to the centre", () => {
    for (const lot of layout.lots.values()) {
      const district = layout.districts.find((item) => item.id === lot.district)!;
      const route = routeToPlaza(lot, district, layout.roads);
      expect(routeLength(route)).toBeGreaterThan(Math.hypot(route.at(-1)!.x - lot.x, route.at(-1)!.z - lot.z) * 1.15);
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
