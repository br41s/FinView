import { describe, expect, it } from "vitest";
import { ARCHETYPE_DISTRICT } from "./archetypes";
import { demoAssets } from "./fixtures";
import { LOT_PITCH, PLAZA_RADIUS, capacityFor, computeLayout } from "./townLayout";
import { PLATEAU_HEIGHT, distToPolyline } from "./terrain";

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

  it("faces each building toward the central square in quarter turns of its district's grid", () => {
    const layout = computeLayout(assets);
    for (const lot of layout.lots.values()) {
      const theta = layout.districts.find((d) => d.id === lot.district)!.theta;
      const turns = (lot.rotationY + theta) / (Math.PI / 2);
      expect(Math.abs(turns - Math.round(turns))).toBeLessThan(1e-9);
    }
  });
});

describe("the land", () => {
  const layout = computeLayout(demoAssets());
  const { terrain } = layout;

  it("builds every holding and every generic building on dry ground", () => {
    for (const l of layout.lots.values()) expect(terrain.heightAt(l.x, l.z), l.assetId).toBeGreaterThan(-0.05);
    for (const f of layout.filler) expect(terrain.heightAt(f.x, f.z)).toBeGreaterThan(-0.05);
  });

  it("puts funds and treasury on the plateau and everything else on the plain", () => {
    for (const l of layout.lots.values()) {
      const high = l.district === "funds" || l.district === "treasury";
      const h = terrain.heightAt(l.x, l.z);
      if (high) expect(h, l.assetId).toBeGreaterThan(PLATEAU_HEIGHT - 1);
      else expect(h, l.assetId).toBeLessThan(1);
    }
  });

  it("has a river between the square and the outer districts, crossed by water", () => {
    expect(terrain.isWater(...riverPoint(layout))).toBe(true);
    expect(terrain.isWater(0, 0)).toBe(false);
  });

  it("has mountains and a sea", () => {
    const a = terrain.spec.plateauAngle;
    let peak = 0;
    for (let r = terrain.spec.plateauOuter + 40; r < terrain.spec.plateauOuter + 110; r += 6) {
      for (let d = -0.5; d <= 0.5; d += 0.1) peak = Math.max(peak, terrain.heightAt(Math.cos(a + d) * r, Math.sin(a + d) * r));
    }
    expect(peak).toBeGreaterThan(25);
    expect(terrain.heightAt(Math.cos(a + Math.PI) * (layout.radius + 60), Math.sin(a + Math.PI) * (layout.radius + 60))).toBeLessThan(-2);
  });

  it("is a pure function of the holdings (heights included)", () => {
    const other = computeLayout([...demoAssets()].reverse());
    for (const [x, z] of [[10, 20], [-70, 5], [90, -60], [0, 0]] as const) {
      expect(other.terrain.heightAt(x, z)).toBe(terrain.heightAt(x, z));
    }
    expect(other.filler).toEqual(layout.filler);
  });
});

describe("generic buildings", () => {
  const layout = computeLayout(demoAssets());
  const homes = (id: string) => layout.filler.filter((f) => f.district === id && ["block", "house", "villa"].includes(f.kind)).length;

  it("keep clear of the holdings", () => {
    for (const f of layout.filler) {
      for (const l of layout.lots.values()) {
        expect(Math.hypot(f.x - l.x, f.z - l.z)).toBeGreaterThan(4.5);
      }
    }
  });

  it("keep clear of each other", () => {
    const fs = layout.filler;
    let min = Infinity;
    for (let i = 0; i < fs.length; i++) {
      for (let j = i + 1; j < fs.length; j++) min = Math.min(min, Math.hypot(fs[i].x - fs[j].x, fs[i].z - fs[j].z));
    }
    expect(min).toBeGreaterThan(5.5);
  });

  it("put homes in every district, and fewer of them downtown than in the suburbs", () => {
    for (const d of layout.districts) expect(homes(d.id), d.id).toBeGreaterThan(2);
    const share = (id: string) => homes(id) / Math.max(1, layout.filler.filter((f) => f.district === id).length);
    expect(share("finance")).toBeLessThan(share("retail"));
  });

  it("include skyscrapers, ordinary blocks, houses and villas", () => {
    const kinds = new Set(layout.filler.map((f) => f.kind));
    for (const k of ["skyscraper", "block", "house", "villa"]) expect(kinds.has(k as never), k).toBe(true);
  });

  it("put the villas on the plateau", () => {
    for (const f of layout.filler.filter((x) => x.kind === "villa")) {
      expect(layout.terrain.heightAt(f.x, f.z)).toBeGreaterThan(PLATEAU_HEIGHT - 1);
    }
  });
});

describe("transport", () => {
  const layout = computeLayout(demoAssets());
  const { infra } = layout;
  const corridors = [...infra.highways, infra.rail, infra.monorail];

  it("has expressways, a railway and a monorail loop", () => {
    expect(infra.highways.length).toBeGreaterThanOrEqual(2);
    expect(infra.rail.path.length).toBeGreaterThanOrEqual(2);
    const loop = infra.monorail.path;
    expect(loop[0]).toEqual(loop.at(-1));
    expect(infra.monorail.stations.length).toBeGreaterThanOrEqual(4);
  });

  it("never builds a generic building in a corridor", () => {
    for (const c of corridors) {
      for (const f of layout.filler) expect(distToPolyline(f.x, f.z, c.path)).toBeGreaterThan(c.clear / 2);
    }
  });

  it("never runs a corridor through a holding", () => {
    for (const c of corridors) {
      for (const l of layout.lots.values()) {
        // Half the largest building plus half the deck: the lot's footprint must stay clear.
        expect(distToPolyline(l.x, l.z, c.path), `${l.assetId} (${l.district})`).toBeGreaterThan(3.5 + c.clear / 4);
      }
    }
  });
});

function riverPoint(layout: ReturnType<typeof computeLayout>): [number, number] {
  const r = layout.terrain.spec.river;
  const p = r[Math.floor(r.length / 2)];
  return [p.x, p.z];
}

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
