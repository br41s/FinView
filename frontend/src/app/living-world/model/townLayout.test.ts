import { describe, expect, it } from "vitest";
import { ARCHETYPE_DISTRICT } from "./archetypes";
import { distToSegment } from "./cityGeometry";
import { slotAt } from "./cityLots";
import { demoAssets } from "./fixtures";
import { LOT_PITCH, PLAZA_RADIUS, computeLayout } from "./townLayout";
import { distToPolyline } from "./terrain";
import { DISTRICT_IDS } from "./types";

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
    expect(b.filler).toEqual(a.filler);
    expect(b.roads).toEqual(a.roads);
  });

  it("does not move anything when weights or prices change", () => {
    const moved = assets.map((a) => ({ ...a, weightPct: 50, marketValueEur: 1, dayChangePct: 9 }));
    expect([...computeLayout(moved).lots.entries()]).toEqual([...computeLayout(assets).lots.entries()]);
  });

  it("keeps every road, block and tree where it is when holdings are added", () => {
    const base = computeLayout(assets);
    const movedBy: number[] = [];
    for (const n of [1, 2, 3, 4, 5, 6]) {
      const more = computeLayout([...assets, { ...assets[n * 7], id: `ZZ-NEW-${n}`, isin: `ZZ-NEW-${n}`, name: "Nueva" }]);
      expect(more.roads).toEqual(base.roads);
      expect(more.treeSpots).toEqual(base.treeSpots);
      expect(more.infra).toEqual(base.infra);
      expect(more.blocks.map((b) => b.key)).toEqual(base.blocks.map((b) => b.key));
      // Lots are stateless: a holding moves only if a newcomer's own hash claims its lot first,
      // which pushes it to its next-best lot. Rare and local, never a reshuffle.
      let moved = 0;
      for (const [id, lot] of base.lots) {
        const next = more.lots.get(id)!;
        if (next.x !== lot.x || next.z !== lot.z) moved++;
      }
      movedBy.push(moved);
    }
    expect(Math.max(...movedBy)).toBeLessThanOrEqual(6);
    expect([...movedBy].sort((p, q) => p - q)[3]).toBeLessThanOrEqual(3);
  });

  it("never puts two buildings closer than a lot pitch", () => {
    const lots = [...computeLayout(assets).lots.values()];
    let min = Infinity;
    for (let i = 0; i < lots.length; i++) {
      for (let j = i + 1; j < lots.length; j++) {
        min = Math.min(min, Math.hypot(lots[i].x - lots[j].x, lots[i].z - lots[j].z));
      }
    }
    expect(min).toBeGreaterThanOrEqual(LOT_PITCH - 3);
  });

  it("keeps districts in their fixed compass wedge, round the plaza", () => {
    const { districts } = computeLayout(assets);
    for (const d of districts) {
      expect(Math.hypot(d.cx, d.cz)).toBeGreaterThan(PLAZA_RADIUS);
      expect(slotAt(d.cx, d.cz)).toBe(DISTRICT_IDS.indexOf(d.id));
      expect(d.slot).toBe(DISTRICT_IDS.indexOf(d.id));
    }
    // Adding a holding to a district does not change where any district is.
    const more = computeLayout([...assets, { ...assets[0], id: "ZZ-NEW-2", isin: "ZZ-NEW-2" }]);
    expect(more.districts.map((d) => [d.id, d.cx, d.cz])).toEqual(districts.map((d) => [d.id, d.cx, d.cz]));
  });

  it("handles empty and single-district portfolios", () => {
    const empty = computeLayout([]);
    expect(empty.lots.size).toBe(0);
    expect(empty.filler.length).toBeGreaterThan(200);
    const funds = assets.filter((a) => a.archetype === "fund");
    const layout = computeLayout(funds);
    expect(layout.districts).toHaveLength(1);
    expect(layout.lots.size).toBe(funds.length);
  });

  it("falls back to free lots elsewhere when a district is over capacity, never dropping a holding", () => {
    const many = Array.from({ length: 70 }, (_, i) => ({ ...assets.find((a) => a.archetype === "cash")!, id: `ZZ-CASH-${i}`, isin: `ZZ-CASH-${i}` }));
    const layout = computeLayout(many);
    expect(layout.lots.size).toBe(70);
    const keys = new Set([...layout.lots.values()].map((l) => l.key));
    expect(keys.size).toBe(70);
  });

  it("faces each building towards the street its lot fronts, within its lot", () => {
    const layout = computeLayout(assets);
    for (const lot of layout.lots.values()) {
      expect(Math.hypot(lot.fx, lot.fz)).toBeCloseTo(1);
      expect(Math.sin(lot.rotationY)).toBeCloseTo(lot.fx);
      expect(Math.cos(lot.rotationY)).toBeCloseTo(lot.fz);
      // The street is ahead: moving along the front vector reaches the road before leaving the lot.
      const road = layout.roads.find((r) => r.edgeId === lot.edgeId)!;
      const a = { x: road.x1, z: road.z1 };
      const b = { x: road.x2, z: road.z2 };
      expect(distToSegment({ x: lot.x + lot.fx * 1, z: lot.z + lot.fz * 1 }, a, b)).toBeLessThan(distToSegment(lot, a, b));
    }
  });

  it("gives holdings the premium frontage first", () => {
    const layout = computeLayout(assets);
    const site = (k: string) => layout.blocks.flatMap((b) => b.lots).find((l) => l.key === k)!;
    for (const id of DISTRICT_IDS) {
      const mine = [...layout.lots.values()].filter((l) => l.district === id);
      if (mine.length === 0) continue;
      const premiumTotal = layout.blocks.flatMap((b) => b.lots).filter((l) => l.district === id && l.capable && l.premium).length;
      const premiumUsed = mine.filter((l) => site(l.key).premium).length;
      expect(premiumUsed, id).toBe(Math.min(mine.length, premiumTotal));
    }
  });
});

describe("the land", () => {
  const layout = computeLayout(demoAssets());
  const { terrain } = layout;

  it("is flat apart from the canal", () => {
    for (const [x, z] of [[0, 0], [60, 40], [-150, -150], [150, 150]] as const) expect(terrain.heightAt(x, z)).toBe(0);
    const { canal } = terrain.spec;
    expect(terrain.isWater(canal[0].x, 0)).toBe(true);
    expect(terrain.heightAt(canal[0].x, 0)).toBeLessThan(-1);
    // A bridge is flat across the water.
    expect(terrain.roadY(canal[0].x, 0)).toBe(0);
  });

  it("builds every holding and every generic building on dry ground", () => {
    for (const l of layout.lots.values()) expect(terrain.isWater(l.x, l.z), l.assetId).toBe(false);
    for (const f of layout.filler) expect(terrain.isWater(f.x, f.z)).toBe(false);
    for (const [x, z] of layout.treeSpots) expect(terrain.isWater(x, z)).toBe(false);
  });

  it("is a pure function of the template (heights included)", () => {
    const other = computeLayout([...demoAssets()].reverse());
    for (const [x, z] of [[10, 20], [-88, 5], [90, -60], [0, 0]] as const) {
      expect(other.terrain.heightAt(x, z)).toBe(terrain.heightAt(x, z));
    }
  });
});

describe("generic buildings", () => {
  const layout = computeLayout(demoAssets());
  const homes = (id: string) => layout.filler.filter((f) => f.district === id && ["block", "house", "villa"].includes(f.kind)).length;

  it("keep clear of the holdings", () => {
    for (const f of layout.filler) {
      for (const l of layout.lots.values()) {
        const dx = Math.abs(f.x - l.x);
        const dz = Math.abs(f.z - l.z);
        // Never inside a holding's lot: the lot is half a pitch each way at least.
        expect(dx > 6.5 || dz > 6.5).toBe(true);
      }
    }
  });

  it("keep clear of each other", () => {
    const fs = layout.filler;
    let min = Infinity;
    for (let i = 0; i < fs.length; i++) {
      for (let j = i + 1; j < fs.length; j++) {
        if (Math.abs(fs[i].x - fs[j].x) > 8) continue;
        min = Math.min(min, Math.hypot(fs[i].x - fs[j].x, fs[i].z - fs[j].z));
      }
    }
    expect(min).toBeGreaterThan(3);
  });

  it("stay off every road and pavement", () => {
    for (const f of layout.filler) {
      for (const r of layout.roads) {
        const ex = (r.x2 - r.x1) / Math.hypot(r.x2 - r.x1, r.z2 - r.z1);
        const ez = (r.z2 - r.z1) / Math.hypot(r.x2 - r.x1, r.z2 - r.z1);
        const len = Math.hypot(r.x2 - r.x1, r.z2 - r.z1);
        const along = (f.x - r.x1) * ex + (f.z - r.z1) * ez;
        const across = Math.abs(-(f.x - r.x1) * ez + (f.z - r.z1) * ex);
        const half = f.width / 2;
        expect(along > 0 && along < len && across < r.fullWidth / 2 + half - 0.5, `${f.x},${f.z} vs ${r.edgeId}`).toBe(false);
      }
    }
  });

  it("put homes in every district, and fewer of them downtown than in the suburbs", () => {
    for (const d of layout.districts) expect(homes(d.id), d.id).toBeGreaterThan(2);
    const share = (id: string) => homes(id) / Math.max(1, layout.filler.filter((f) => f.district === id).length);
    expect(share("finance")).toBeLessThan(share("retail"));
  });

  it("include skyscrapers, ordinary blocks, houses and villas, all smaller than the biggest landmark", () => {
    const kinds = new Set(layout.filler.map((f) => f.kind));
    for (const k of ["skyscraper", "block", "house", "villa"]) expect(kinds.has(k as never), k).toBe(true);
    for (const f of layout.filler) expect(f.width).toBeLessThan(5.01);
  });
});

describe("transport", () => {
  const layout = computeLayout(demoAssets());
  const { infra } = layout;

  it("has a railway with level crossings, a monorail loop with stations and traffic loops", () => {
    expect(infra.highways.length).toBeGreaterThanOrEqual(2);
    expect(infra.rail.path.length).toBeGreaterThanOrEqual(2);
    expect(infra.crossings.length).toBeGreaterThanOrEqual(3);
    const loop = infra.monorail.path;
    expect(loop[0]).toEqual(loop.at(-1));
    expect(infra.monorail.stations.length).toBe(7);
  });

  it("stands every monorail pillar in the central reservation of an avenue, clear of lanes, water and crossings", () => {
    const avenues = layout.roads.filter((r) => r.kind === "avenue" && r.fullWidth === 14);
    expect(infra.monorail.piers.length).toBeGreaterThanOrEqual(30);
    for (const p of infra.monorail.piers) {
      const on = avenues.find((r) => distToSegment(p, { x: r.x1, z: r.z1 }, { x: r.x2, z: r.z2 }) < 0.01);
      expect(on, `pier ${p.x},${p.z}`).toBeDefined();
      expect(layout.terrain.isWater(p.x, p.z)).toBe(false);
      expect(layout.terrain.canalDistance(p.x, p.z)).toBeGreaterThan(layout.terrain.spec.canalHalfWidth + 2);
      for (const c of infra.crossings) expect(Math.hypot(c.x - p.x, c.z - p.z)).toBeGreaterThan(5);
    }
  });

  it("keeps generic buildings and holdings out of the railway corridor", () => {
    const rail = infra.rail;
    for (const f of layout.filler) expect(distToPolyline(f.x, f.z, rail.path), `${f.x},${f.z}`).toBeGreaterThan(rail.clear / 2 + f.width / 2 - 1);
    for (const l of layout.lots.values()) expect(distToPolyline(l.x, l.z, rail.path)).toBeGreaterThan(rail.clear / 2 + 7);
  });

  it("puts the railway terminus beside the plaza and meets streets only at crossings", () => {
    expect(Math.hypot(infra.railTerminus.x, infra.railTerminus.z)).toBeLessThan(45);
    for (const road of layout.roads) {
      if (road.kind === "bridge") continue;
      const hits = distToPolyline(road.x1, road.z1, infra.rail.path) < 0.01 || distToPolyline(road.x2, road.z2, infra.rail.path) < 0.01;
      if (hits) expect(infra.crossings.some((c) => Math.hypot(c.x - road.x1, c.z - road.z1) < 0.01 || Math.hypot(c.x - road.x2, c.z - road.z2) < 0.01)).toBe(true);
    }
  });
});
