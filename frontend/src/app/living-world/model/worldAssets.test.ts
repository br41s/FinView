import { describe, expect, it } from "vitest";
import type { LivingWorldAsset, LivingWorldResponse } from "@/lib/types";
import { sceneSignature, toWorldAsset, toWorldAssets } from "./worldAssets";

const row = (over: Partial<LivingWorldAsset> = {}): LivingWorldAsset => ({
  isin: "ES0000000001",
  ticker: "TST",
  name: "Test SA",
  country: "España",
  brokers: ["ING", "TR"],
  asset_type: "equity",
  sector: "Technology",
  classified: true,
  archetype_override: null,
  market_value_eur: 1200,
  weight_pct: 4.2,
  total_cost_eur: 1000,
  unrealized_pl_eur: 200,
  day_change_pct: null,
  status: "open",
  closed_on: null,
  invested_eur: null,
  sold_eur: null,
  dividends_eur: null,
  ...over,
});

describe("toWorldAsset", () => {
  it("keeps one building per ISIN with its brokers", () => {
    const a = toWorldAsset(row());
    expect(a.id).toBe("ES0000000001");
    expect(a.brokers).toEqual(["ING", "TR"]);
    expect(a.archetype).toBe("tech");
  });

  it("never turns an unknown figure into zero", () => {
    const a = toWorldAsset(row({ market_value_eur: null, weight_pct: null, total_cost_eur: null, unrealized_pl_eur: null }));
    expect([a.marketValueEur, a.weightPct, a.totalCostEur, a.unrealizedPlEur, a.dayChangePct]).toEqual([
      null, null, null, null, null,
    ]);
  });

  it("draws an ETF as the fund pavilion whatever its Yahoo sector says", () => {
    expect(toWorldAsset(row({ asset_type: "etf", sector: "Technology" })).archetype).toBe("fund");
  });

  it("an unclassified company keeps the default building and says so", () => {
    const a = toWorldAsset(row({ sector: null, classified: false }));
    expect(a.classified).toBe(false);
    expect(a.archetype).toBe("consumer");
  });

  it("applies a curated override but ignores an archetype it does not know", () => {
    expect(toWorldAsset(row({ archetype_override: "semis" })).archetype).toBe("semis");
    expect(toWorldAsset(row({ archetype_override: "spaceport" })).archetype).toBe("tech");
  });

  it("keeps a closed position's ledger figures, and trusts no closure without a date", () => {
    const ruin = toWorldAsset(
      row({ status: "closed", closed_on: "2025-09-03", invested_eur: 1000, sold_eur: 1200, dividends_eur: 25.5, market_value_eur: null, weight_pct: null }),
    );
    expect(ruin.closed).toEqual({ on: "2025-09-03", investedEur: 1000, soldEur: 1200, dividendsEur: 25.5 });
    expect(toWorldAsset(row({ status: "closed", closed_on: null })).closed).toBeNull();
    expect(toWorldAsset(row()).closed).toBeNull();
  });

  it("falls back to a company for an asset type it does not know", () => {
    expect(toWorldAsset(row({ asset_type: "warrant" })).assetType).toBe("equity");
  });

  it("maps a whole response in order", () => {
    const res: LivingWorldResponse = {
      summary: {
        positions: 2, valued: 2, cost_known: 2, valuation_complete: true,
        total_market_value: 2400, classified: 2, closed: 0, prices_as_of: "2026-11-07",
      },
      assets: [row(), row({ isin: "ES0000000002" })],
      events: [],
    };
    expect(toWorldAssets(res).map((a) => a.id)).toEqual(["ES0000000001", "ES0000000002"]);
  });
});

describe("sceneSignature", () => {
  const base = [toWorldAsset(row()), toWorldAsset(row({ isin: "ES0000000002", name: "Other" }))];

  it("changes when a holding is sold out of, so the building is rebuilt as ruins", () => {
    const sold = [toWorldAsset(row({ status: "closed", closed_on: "2025-09-03" })), base[1]];
    expect(sceneSignature(sold)).not.toBe(sceneSignature(base));
  });

  it("ignores order, prices and sub-0.1 weight drift", () => {
    const drift = [
      toWorldAsset(row({ isin: "ES0000000002", name: "Other", market_value_eur: 5 })),
      toWorldAsset(row({ weight_pct: 4.23, market_value_eur: 1300, unrealized_pl_eur: 300 })),
    ];
    expect(sceneSignature(drift)).toBe(sceneSignature(base));
  });

  it("changes when the set, a class, a name or a visible weight changes", () => {
    const sig = sceneSignature(base);
    expect(sceneSignature(base.slice(0, 1))).not.toBe(sig);
    expect(sceneSignature([base[0], toWorldAsset(row({ isin: "ES0000000002", name: "Other", sector: "Energy" }))])).not.toBe(sig);
    expect(sceneSignature([toWorldAsset(row({ name: "Renamed" })), base[1]])).not.toBe(sig);
    expect(sceneSignature([toWorldAsset(row({ weight_pct: 5.5 })), base[1]])).not.toBe(sig);
  });

  it("tells an unknown weight from a small one", () => {
    expect(sceneSignature([toWorldAsset(row({ weight_pct: null }))])).not.toBe(
      sceneSignature([toWorldAsset(row({ weight_pct: 0 }))]),
    );
  });
});
