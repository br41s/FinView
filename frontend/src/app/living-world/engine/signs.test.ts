import { describe, expect, it } from "vitest";
import { lanternTop, NOMINAL, signGeometry } from "./buildingFactory";

describe("company sign", () => {
  it.each(Object.entries(NOMINAL))("puts a four-sided lantern on the roof of a %s building", (_tier, nominal) => {
    const top = 12;
    const g = signGeometry(nominal, top);
    // The facade plate plus four lantern faces, four vertices each.
    expect(g.getAttribute("position").count).toBe(5 * 4);
    g.computeBoundingBox();
    const box = g.boundingBox!;
    // Above the roof, never inside it, and its top is what labels and markers float over.
    expect(box.max.y).toBeCloseTo(lanternTop(nominal, top), 5);
    const pos = g.getAttribute("position");
    const lantern = Array.from({ length: 16 }, (_, i) => pos.getY(4 + i));
    expect(Math.min(...lantern)).toBeGreaterThan(top);
  });

  it("grows with the building, so the tallest holdings keep a readable sign", () => {
    const width = (n: number) => {
      const g = signGeometry(n, 10);
      g.computeBoundingBox();
      return g.boundingBox!.max.x - g.boundingBox!.min.x;
    };
    expect(width(NOMINAL.major)).toBeGreaterThan(width(NOMINAL.outpost));
  });
});
