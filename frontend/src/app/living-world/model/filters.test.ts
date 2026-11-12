import { describe, expect, it } from "vitest";
import { CLOCK_SKEW_MS, applyFilters, filterEvents, hasActiveFilters, matchesQuery, normalise } from "./filters";
import { demoAssets, generateDemoEvents } from "./fixtures";
import { EMPTY_FILTERS, type WorldFilters } from "./types";

const NOW = Date.parse("2026-11-08T12:00:00Z");
const assets = demoAssets();
const events = generateDemoEvents(assets, { nowMs: NOW, seed: 3, count: 200, spanMs: 7 * 86_400_000 });
const f = (patch: Partial<WorldFilters>): WorldFilters => ({ ...EMPTY_FILTERS, ...patch });
const count = (m: Map<string, string>, v: string) => [...m.values()].filter((x) => x === v).length;

describe("search", () => {
  it("is accent- and case-insensitive over name, ticker and ISIN", () => {
    expect(normalise("Nestlé")).toBe("nestle");
    const a = { ...assets[0], name: "Nestlé Foods", ticker: "NESN", isin: "CH0038863350" };
    expect(matchesQuery(a, "NESTLE")).toBe(true);
    expect(matchesQuery(a, "nesn")).toBe(true);
    expect(matchesQuery(a, "ch0038")).toBe(true);
    expect(matchesQuery(a, "zzz")).toBe(false);
    expect(matchesQuery(a, "   ")).toBe(true);
  });
});

describe("applyFilters over 100+ holdings", () => {
  it("matches everything with no filters", () => {
    const m = applyFilters(assets, events, EMPTY_FILTERS, NOW);
    expect(m.size).toBe(assets.length);
    expect(count(m, "match")).toBe(assets.length);
  });

  it("mutes non-matching buildings by default and hides them in isolate mode", () => {
    const muted = applyFilters(assets, events, f({ archetypes: ["tech"] }), NOW);
    const hidden = applyFilters(assets, events, f({ archetypes: ["tech"], isolate: true }), NOW);
    const techs = assets.filter((a) => a.archetype === "tech").length;
    expect(count(muted, "match")).toBe(techs);
    expect(count(muted, "muted")).toBe(assets.length - techs);
    expect(count(muted, "hidden")).toBe(0);
    expect(count(hidden, "hidden")).toBe(assets.length - techs);
  });

  it("composes filters with AND", () => {
    const both = applyFilters(assets, events, f({ archetypes: ["banking"], favouritesOnly: true }), NOW);
    for (const a of assets) {
      expect(both.get(a.id) === "match").toBe(a.archetype === "banking" && a.favourite);
    }
  });

  it("does not treat an unknown weight as a small one", () => {
    const m = applyFilters(assets, events, f({ minWeightPct: 0.0001 }), NOW);
    for (const a of assets.filter((x) => x.weightPct === null)) expect(m.get(a.id)).toBe("muted");
  });

  it("matches a broker held at, without duplicating the building", () => {
    const m = applyFilters(assets, events, f({ brokers: ["IBKR"] }), NOW);
    for (const a of assets) expect(m.get(a.id) === "match").toBe(a.brokers.includes("IBKR"));
  });

  it("activeOnly keeps only buildings with an event inside the window", () => {
    const m = applyFilters(assets, events, f({ activeOnly: true, window: "24h" }), NOW);
    const active = new Set(filterEvents(events, f({ window: "24h" }), NOW).map((e) => e.assetId));
    for (const a of assets) expect(m.get(a.id) === "match").toBe(active.has(a.id));
  });

  it("an event-level filter keeps only assets with such an event", () => {
    const m = applyFilters(assets, events, f({ directions: ["negative"], window: "7d" }), NOW);
    const hit = new Set(events.filter((e) => e.direction === "negative").map((e) => e.assetId));
    for (const a of assets) expect(m.get(a.id) === "match").toBe(hit.has(a.id));
  });
});

describe("filterEvents", () => {
  it("never returns an event from the future or outside the window", () => {
    for (const w of ["live", "24h", "7d", "30d"] as const) {
      const span = { live: 15 * 60_000, "24h": 86_400_000, "7d": 7 * 86_400_000, "30d": 30 * 86_400_000 }[w];
      for (const e of filterEvents(events, f({ window: w }), NOW)) {
        const t = Date.parse(e.occurredAt);
        expect(t).toBeLessThanOrEqual(NOW + CLOCK_SKEW_MS);
        expect(NOW - t).toBeLessThanOrEqual(span);
      }
    }
  });

  it("keeps an event emitted after the last clock tick", () => {
    const fresh = { ...events[0], occurredAt: new Date(NOW + 4_000).toISOString() };
    expect(filterEvents([fresh], f({ window: "live" }), NOW)).toHaveLength(1);
    const future = { ...events[0], occurredAt: new Date(NOW + 60_000).toISOString() };
    expect(filterEvents([future], f({ window: "live" }), NOW)).toHaveLength(0);
  });

  it("narrows monotonically: live ⊆ 24h ⊆ 7d", () => {
    const n = (w: "live" | "24h" | "7d" | "30d") => filterEvents(events, f({ window: w }), NOW).length;
    expect(n("live")).toBeLessThanOrEqual(n("24h"));
    expect(n("24h")).toBeLessThanOrEqual(n("7d"));
    expect(n("7d")).toBeLessThanOrEqual(n("30d"));
  });
});

describe("hasActiveFilters", () => {
  it("ignores the window and isolate, which are views and not restrictions", () => {
    expect(hasActiveFilters(EMPTY_FILTERS)).toBe(false);
    expect(hasActiveFilters(f({ window: "7d", isolate: true }))).toBe(false);
    expect(hasActiveFilters(f({ query: "x" }))).toBe(true);
  });
});
