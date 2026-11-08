import { describe, expect, it } from "vitest";
import { ARCHETYPE_DISTRICT, classifyArchetype } from "./archetypes";
import { demoAssets, generateDemoEvents } from "./fixtures";
import { ARCHETYPES, EVENT_TYPE_CATEGORY } from "./types";

const NOW = Date.parse("2026-11-08T12:00:00Z");

describe("demoAssets", () => {
  const assets = demoAssets();

  it("builds ~100 unique holdings covering every archetype", () => {
    expect(assets.length).toBe(100);
    expect(new Set(assets.map((a) => a.id)).size).toBe(100);
    expect(new Set(assets.map((a) => a.name)).size).toBe(100);
    for (const a of ARCHETYPES) expect(assets.some((x) => x.archetype === a)).toBe(true);
  });

  it("is deterministic for a seed", () => {
    expect(demoAssets(7)).toEqual(demoAssets(7));
    expect(demoAssets(8)).not.toEqual(demoAssets(7));
  });

  it("keeps unknown values null instead of zero, and weights of the known ones sum to 100", () => {
    const unknown = assets.filter((a) => a.weightPct === null);
    expect(unknown.length).toBeGreaterThan(0);
    for (const a of unknown) expect(a.marketValueEur).toBeNull();
    const sum = assets.reduce((s, a) => s + (a.weightPct ?? 0), 0);
    expect(sum).toBeCloseTo(100, 6);
    expect(assets.some((a) => a.totalCostEur === null && a.marketValueEur !== null)).toBe(true);
  });

  it("uses only fictional ISINs", () => {
    for (const a of assets) expect(a.isin.startsWith("ZZ")).toBe(true);
  });
});

describe("classifyArchetype", () => {
  it("draws funds, cash and crypto as such, never as operating companies", () => {
    const base = { sector: "Technology", industry: "Semiconductors" };
    expect(classifyArchetype({ ...base, assetType: "etf" })).toBe("fund");
    expect(classifyArchetype({ ...base, assetType: "cash" })).toBe("cash");
    expect(classifyArchetype({ ...base, assetType: "crypto" })).toBe("crypto");
    expect(classifyArchetype({ ...base, assetType: "etf" }, "banking")).toBe("fund");
  });

  it("lets industry beat sector and an explicit override beat both", () => {
    const e = { assetType: "equity" as const };
    expect(classifyArchetype({ ...e, sector: "Technology", industry: "Semiconductors" })).toBe("semis");
    expect(classifyArchetype({ ...e, sector: "Technology", industry: null })).toBe("tech");
    expect(classifyArchetype({ ...e, sector: "Technology", industry: "Semiconductors" }, "banking")).toBe("banking");
  });

  it("falls back to a generic company when the sector is unknown", () => {
    expect(classifyArchetype({ assetType: "equity", sector: null, industry: null })).toBe("consumer");
  });

  it("maps every archetype to a district", () => {
    for (const a of ARCHETYPES) expect(ARCHETYPE_DISTRICT[a]).toBeTruthy();
  });
});

describe("generateDemoEvents", () => {
  const assets = demoAssets();

  it("is deterministic and has unique ids and dedupe keys", () => {
    const a = generateDemoEvents(assets, { nowMs: NOW, seed: 5, count: 150, spanMs: 7 * 86_400_000 });
    const b = generateDemoEvents(assets, { nowMs: NOW, seed: 5, count: 150, spanMs: 7 * 86_400_000 });
    expect(a).toEqual(b);
    expect(new Set(a.map((e) => e.id)).size).toBe(150);
    expect(new Set(a.map((e) => e.dedupeKey)).size).toBe(150);
  });

  it("distinguishes occurred from observed time and labels everything as demo", () => {
    for (const e of generateDemoEvents(assets, { nowMs: NOW, seed: 5, count: 50, spanMs: 86_400_000 })) {
      expect(Date.parse(e.observedAt)).toBeGreaterThan(Date.parse(e.occurredAt));
      expect(e.confidence).toBe("demo");
      expect(e.why).toMatch(/demostración/);
      expect(e.category).toBe(EVENT_TYPE_CATEGORY[e.eventType]);
    }
  });

  it("never invents operating events for cash or fund assets", () => {
    const byId = new Map(assets.map((a) => [a.id, a]));
    const operating = new Set(["earnings_beat", "earnings_miss", "site_expansion", "dividend_declared", "options_alert"]);
    for (const e of generateDemoEvents(assets, { nowMs: NOW, seed: 6, count: 400, spanMs: 86_400_000 })) {
      const a = byId.get(e.assetId!)!;
      expect(a.assetType).not.toBe("cash");
      if (a.assetType !== "equity") expect(operating.has(e.eventType)).toBe(false);
    }
  });

  it("spans every severity so the UI can be exercised", () => {
    const sev = new Set(generateDemoEvents(assets, { nowMs: NOW, seed: 2, count: 600, spanMs: 7 * 86_400_000 }).map((e) => e.severity));
    expect(sev).toEqual(new Set(["normal", "important", "critical"]));
  });
});
