import { describe, expect, it } from "vitest";
import { MAX_FOOTPRINT, approach, componentCount, footprintFor, tierFor, tierWithHysteresis } from "./scale";

describe("footprintFor", () => {
  it("is monotonic and bounded by the largest footprint", () => {
    let prev = -1;
    for (let w = 0; w <= 40; w += 0.1) {
      const f = footprintFor(w);
      expect(f).toBeGreaterThanOrEqual(prev);
      expect(f).toBeLessThanOrEqual(MAX_FOOTPRINT);
      prev = f;
    }
  });

  it("is continuous across tier boundaries (no jump when a position crosses one)", () => {
    for (const edge of [1, 3, 7, 15]) {
      expect(Math.abs(footprintFor(edge + 1e-6) - footprintFor(edge - 1e-6))).toBeLessThan(1e-3);
    }
  });

  it("draws an unknown or non-positive weight as the smallest site, never larger", () => {
    expect(footprintFor(null)).toBe(footprintFor(0));
    expect(footprintFor(Number.NaN)).toBe(footprintFor(0));
    expect(footprintFor(-3)).toBe(footprintFor(0));
  });

  it("does not let one large position dwarf the rest", () => {
    expect(footprintFor(60) / footprintFor(0.2)).toBeLessThan(4);
  });
});

describe("tiers", () => {
  it("maps weight to tier at the boundaries", () => {
    expect(tierFor(0.99)).toBe("outpost");
    expect(tierFor(1)).toBe("small");
    expect(tierFor(3)).toBe("campus");
    expect(tierFor(7)).toBe("major");
    expect(tierFor(null)).toBe("outpost");
  });

  it("holds the tier inside the hysteresis margin and moves outside it", () => {
    expect(tierWithHysteresis("outpost", 1.1)).toBe("outpost");
    expect(tierWithHysteresis("outpost", 1.3)).toBe("small");
    expect(tierWithHysteresis("small", 0.9)).toBe("small");
    expect(tierWithHysteresis("small", 0.7)).toBe("outpost");
  });

  it("adds a component per tier", () => {
    expect(["outpost", "small", "campus", "major"].map((t) => componentCount(t as never))).toEqual([1, 2, 3, 4]);
  });
});

describe("approach", () => {
  it("converges without overshooting and snaps when close", () => {
    let v = 0;
    for (let i = 0; i < 600; i++) {
      v = approach(v, 10, 16);
      expect(v).toBeLessThanOrEqual(10);
    }
    expect(v).toBe(10);
  });

  it("does nothing for a zero or negative step", () => {
    expect(approach(3, 10, 0)).toBe(3);
  });
});
