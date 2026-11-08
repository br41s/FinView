import { describe, expect, it } from "vitest";
import { ARCHETYPE_DISTRICT } from "./archetypes";
import { demoAssets } from "./fixtures";
import { LOT_PITCH, PLAZA_RADIUS, capacityFor, computeLayout } from "./townLayout";

describe("computeLayout", () => {
  const assets = demoAssets();

  it("gives every asset exactly one lot, in its archetype's district", () => {
    const layout = computeLayout(assets);
    expect(layout.lots.size).toBe(assets.length);
    for (const a of assets) {
      expect(layout.lots.get(a.id)?.district).toBe(ARCHETYPE_DISTRICT[a.archetype]);
    }
  });

  it("is identical across runs and independent of the input order", () => {
    const a = computeLayout(assets);
    const b = computeLayout([...assets].reverse());
    expect([...b.lots.entries()].sort()).toEqual([...a.lots.entries()].sort());
  });

  it("does not move anything when weights or prices change", () => {
    const moved = assets.map((a) => ({ ...a, weightPct: 50, marketValueEur: 1, dayChangePct: 9 }));
    expect([...computeLayout(moved).lots.entries()]).toEqual([...computeLayout(assets).lots.entries()]);
  });

  it("never puts two buildings closer than a lot pitch", () => {
    const lots = [...computeLayout(assets).lots.values()];
    let min = Infinity;
    for (let i = 0; i < lots.length; i++) {
      for (let j = i + 1; j < lots.length; j++) {
        min = Math.min(min, Math.hypot(lots[i].x - lots[j].x, lots[i].z - lots[j].z));
      }
    }
    expect(min).toBeGreaterThanOrEqual(LOT_PITCH - 1e-6);
  });

  it("keeps districts clear of the plaza and of each other", () => {
    const { districts } = computeLayout(assets);
    for (const d of districts) expect(Math.hypot(d.cx, d.cz)).toBeGreaterThan(PLAZA_RADIUS + d.extent);
    for (let i = 0; i < districts.length; i++) {
      for (let j = i + 1; j < districts.length; j++) {
        const dist = Math.hypot(districts[i].cx - districts[j].cx, districts[i].cz - districts[j].cz);
        expect(dist).toBeGreaterThan(districts[i].extent + districts[j].extent);
      }
    }
  });

  it("handles empty and single-district portfolios", () => {
    expect(computeLayout([]).lots.size).toBe(0);
    const funds = assets.filter((a) => a.archetype === "fund");
    const layout = computeLayout(funds);
    expect(layout.districts).toHaveLength(1);
    expect(layout.lots.size).toBe(funds.length);
  });

  it("faces each building toward the central square in quarter turns", () => {
    for (const lot of computeLayout(assets).lots.values()) {
      expect(Math.abs((lot.rotationY / (Math.PI / 2)) % 1)).toBeLessThan(1e-9);
    }
  });
});

describe("capacityFor", () => {
  it("leaves slack and steps in fours", () => {
    expect(capacityFor(1)).toBe(4);
    expect(capacityFor(10)).toBe(16);
    for (const n of [1, 5, 17, 40]) {
      expect(capacityFor(n) % 4).toBe(0);
      expect(capacityFor(n)).toBeGreaterThanOrEqual(n);
    }
  });
});
