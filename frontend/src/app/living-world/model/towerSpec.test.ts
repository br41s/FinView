import { describe, expect, it } from "vitest";
import { TIERS } from "./scale";
import { EXTRA_COUNT, HEIGHT_RANGE, accentColour, hslHex, towerSpec } from "./towerSpec";
import { ARCHETYPES } from "./types";

const ids = Array.from({ length: 40 }, (_, i) => `ES${String(1_000_000_000 + i * 7919)}`);

describe("towerSpec", () => {
  it("is deterministic: the same archetype, id and tier give the same spec", () => {
    for (const a of ARCHETYPES) {
      for (const t of TIERS) expect(towerSpec(a, ids[3], t)).toEqual(towerSpec(a, ids[3], t));
    }
  });

  it("gives different ISINs different buildings", () => {
    for (const a of ARCHETYPES) {
      const seen = new Set(ids.map((id) => JSON.stringify(towerSpec(a, id, "campus").main)));
      expect(seen.size).toBeGreaterThan(ids.length * 0.9);
    }
  });

  it("only ever adds parts as the tier grows (each tier is a prefix of the next)", () => {
    for (const a of ARCHETYPES) {
      for (const id of ids.slice(0, 8)) {
        let prev = towerSpec(a, id, "outpost").parts;
        expect(prev.length).toBe(EXTRA_COUNT.outpost);
        for (const t of TIERS.slice(1)) {
          const next = towerSpec(a, id, t).parts;
          expect(next.length).toBeGreaterThan(prev.length);
          expect(next.slice(0, prev.length)).toEqual(prev);
          prev = next;
        }
      }
    }
  });

  it("keeps the identity of a holding across tiers (family, plan, colours, mirror)", () => {
    for (const a of ARCHETYPES) {
      const o = towerSpec(a, ids[5], "outpost");
      for (const t of TIERS) {
        const s = towerSpec(a, ids[5], t);
        expect(s.main.family).toBe(o.main.family);
        expect(s.main.plan).toBe(o.main.plan);
        expect(s.accent).toBe(o.accent);
        expect(s.glass).toBe(o.glass);
        expect(s.mirror).toBe(o.mirror);
      }
    }
  });

  it("rises with the tier: the tallest element of any larger tier is above every smaller one", () => {
    for (let i = 1; i < TIERS.length; i++) {
      expect(HEIGHT_RANGE[TIERS[i]][0]).toBeGreaterThan(HEIGHT_RANGE[TIERS[i - 1]][1]);
    }
    for (const a of ARCHETYPES) {
      for (const id of ids.slice(0, 10)) {
        for (const t of TIERS) {
          const h = towerSpec(a, id, t).main.height;
          expect(h).toBeGreaterThanOrEqual(HEIGHT_RANGE[t][0]);
          expect(h).toBeLessThanOrEqual(HEIGHT_RANGE[t][1]);
        }
      }
    }
  });

  it("lets a brand accent win over the archetype palette", () => {
    expect(towerSpec("banking", ids[0], "major", 0xec0000).accent).toBe(0xec0000);
  });

  it("makes utilities and energy complexes of several industrial structures", () => {
    const u = towerSpec("utilities", ids[1], "major");
    const kinds = u.parts.map((p) => p.kind);
    for (const k of ["turbineHall", "substation", "wind", "solar", "cooling"]) expect(kinds).toContain(k);
    expect(u.main.family).toBe("stack");
    expect(u.main.chimneys).toBeGreaterThanOrEqual(2);
  });

  it("builds banks as a tower with a low hall and a plaza", () => {
    const kinds = towerSpec("banking", ids[1], "small").parts.map((p) => p.kind);
    expect(kinds).toContain("hall");
    expect(kinds).toContain("plaza");
  });
});

describe("colours", () => {
  it("hslHex is a valid hex and matches known values", () => {
    expect(hslHex(0, 1, 0.5)).toBe(0xff0000);
    expect(hslHex(1 / 3, 1, 0.5)).toBe(0x00ff00);
    expect(hslHex(-1 / 3 + 1, 1, 0.5)).toBe(0x0000ff);
  });
  it("accent is stable per id and varies between ids", () => {
    expect(accentColour("tech", ids[0])).toBe(accentColour("tech", ids[0]));
    expect(new Set(ids.map((id) => accentColour("tech", id))).size).toBeGreaterThan(30);
  });
});
