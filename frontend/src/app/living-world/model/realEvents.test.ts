import { describe, expect, it } from "vitest";
import type { LivingWorldEvent } from "@/lib/types";
import { demoAssets } from "./fixtures";
import { toWorldEvents } from "./realEvents";

const assets = demoAssets().slice(0, 3);
const [held] = assets;

const raw = (over: Partial<LivingWorldEvent>): LivingWorldEvent => ({
  id: "tx:1",
  event_type: "position_added",
  isin: held.isin,
  name: held.name,
  occurred_on: "2026-11-10",
  source_type: "ledger",
  confidence: "verified",
  metrics: { quantity: 10, value_eur: 1000, account: "IBKR" },
  ...over,
});

describe("toWorldEvents", () => {
  it("anchors an event to the building of its ISIN and keeps the exact figures", () => {
    const [e] = toWorldEvents([raw({})], assets);
    expect(e.id).toBe("real:tx:1");
    expect(e.assetId).toBe(held.id);
    expect(e.title).toBe(`Compra: ${held.name}`);
    expect(e.category).toBe("portfolio");
    expect(e.confidence).toBe("verified");
    expect(e.metrics).toEqual({ quantity: 10, value_eur: 1000, account: "IBKR" });
    expect(e.occurredAt).toBe("2026-11-10T00:00:00.000Z");
  });

  it("states a price move with its sign as a word, never as advice", () => {
    const [up, down] = toWorldEvents(
      [
        raw({ id: "px:a:2026-11-12", event_type: "price_move_up", occurred_on: "2026-11-12", confidence: "derived", metrics: { change_pct: 3.456 } }),
        raw({ id: "px:a:2026-11-11", event_type: "price_move_down", occurred_on: "2026-11-11", confidence: "derived", metrics: { change_pct: -5 } }),
      ],
      assets,
    );
    expect(up.title).toBe(`${held.name} sube un 3,46 %`);
    expect(up.direction).toBe("positive");
    expect(down.title).toBe(`${held.name} baja un 5,00 %`);
    expect(down.direction).toBe("negative");
    for (const e of [up, down]) expect(e.title + e.summary).not.toMatch(/compra|vend|mant[eé]n|recomend/i);
  });

  it("keeps a closed position in the feed without a building", () => {
    const [e] = toWorldEvents([raw({ event_type: "position_closed", isin: "XX0000000000", name: "Vendida SA" })], assets);
    expect(e.assetId).toBeNull();
    expect(e.title).toBe("Posición cerrada: Vendida SA");
  });

  it("drops a type or confidence it does not know instead of guessing", () => {
    expect(toWorldEvents([raw({ event_type: "merger" }), raw({ confidence: "demo" })], assets)).toEqual([]);
  });

  it("lists newest first", () => {
    const events = toWorldEvents(
      [raw({ id: "tx:old", occurred_on: "2026-11-06" }), raw({ id: "tx:new", occurred_on: "2026-11-12" })],
      assets,
    );
    expect(events.map((e) => e.id)).toEqual(["real:tx:new", "real:tx:old"]);
  });

  it("scores a bigger move higher, through the shared priority rule", () => {
    const [small, big] = toWorldEvents(
      [
        raw({ id: "px:s", event_type: "price_move_up", occurred_on: "2026-11-12", confidence: "derived", metrics: { change_pct: 2 } }),
        raw({ id: "px:b", event_type: "price_move_up", occurred_on: "2026-11-11", confidence: "derived", metrics: { change_pct: 8 } }),
      ],
      assets,
    );
    expect(big.priorityScore).toBeGreaterThan(small.priorityScore);
  });

  it("keeps the real moment of an alert and the date of what has none", () => {
    const [geo, report] = toWorldEvents(
      [
        raw({ id: "geo:1", event_type: "geo_alert", confidence: "derived", occurred_on: "2026-11-11", occurred_at: "2026-11-11T08:30:00Z", metrics: { headline: "Huelga en el puerto", importance: 80 } }),
        raw({ id: "report:1", event_type: "annual_report", occurred_on: "2026-11-10", occurred_at: null, metrics: { fiscal_year: 2025 } }),
      ],
      assets,
    );
    expect(geo.occurredAt).toBe("2026-11-11T08:30:00.000Z");
    expect(geo.summary).toBe("Huelga en el puerto");
    expect(geo.direction).toBe("neutral");
    expect(report.occurredAt).toBe("2026-11-10T00:00:00.000Z");
    expect(report.title).toBe(`Nuevo informe anual de ${held.name} (ejercicio 2025)`);
  });

  it("lists every headline of a day's grouped geo alerts", () => {
    const [grouped, single] = toWorldEvents(
      [
        raw({ id: "geo:a", event_type: "geo_alert", confidence: "derived", occurred_on: "2026-11-11", occurred_at: "2026-11-11T15:00:00Z", metrics: { headline: "Arancel", headlines: "Arancel\nSequía\nHuelga", signal_count: 3, importance: 80 } }),
        raw({ id: "geo:b", event_type: "geo_alert", confidence: "derived", occurred_on: "2026-11-10", occurred_at: "2026-11-10T08:00:00Z", metrics: { headline: "Cierre", headlines: "Cierre", signal_count: 1 } }),
      ],
      assets,
    );
    expect(grouped.title).toBe(`3 alertas geopolíticas: ${held.name}`);
    expect(grouped.summary).toBe("Arancel · Sequía · Huelga");
    expect(single.title).toBe(`Alerta geopolítica: ${held.name}`);
    expect(single.summary).toBe("Cierre");
  });

  it("names a split and a reverse split by their ratio", () => {
    const [split, reverse] = toWorldEvents(
      [
        raw({ id: "s1", event_type: "stock_split", confidence: "reported", occurred_on: "2026-11-12", metrics: { ratio: 4 } }),
        raw({ id: "s2", event_type: "stock_split", confidence: "reported", occurred_on: "2026-11-11", metrics: { ratio: 0.1 } }),
      ],
      assets,
    );
    expect(split.title).toBe(`Split de ${held.name} 4:1`);
    expect(split.confidence).toBe("reported");
    expect(reverse.title).toBe(`Contrasplit de ${held.name} 1:10`);
  });

  it("states a dividend change per share with its sign", () => {
    const [cut] = toWorldEvents(
      [raw({ id: "d1", event_type: "dividend_cut", confidence: "derived", metrics: { change_pct: -25.5 } })],
      assets,
    );
    expect(cut.title).toBe(`${held.name} paga menos dividendo por acción (−25,50 %)`);
    expect(cut.direction).toBe("negative");
  });
});
