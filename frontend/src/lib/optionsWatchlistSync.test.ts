import { describe, expect, it } from "vitest";
import { selectPositionsToSync, type SyncablePosition } from "./optionsWatchlistSync";

function pos(ticker: string | null, isin: string, name = "Test Co"): SyncablePosition {
  return { ticker, isin, name };
}

describe("selectPositionsToSync", () => {
  it("returns every eligible position on a clean slate", () => {
    const result = selectPositionsToSync(
      [pos("AAPL", "US0378331005"), pos("MSFT", "US5949181045")],
      new Set(),
      new Set(),
      new Set(),
      new Set(),
    );
    expect([...result.keys()].sort()).toEqual(["AAPL", "MSFT"]);
  });

  it("filters out tickers already on the watchlist", () => {
    const result = selectPositionsToSync(
      [pos("AAPL", "US0378331005"), pos("MSFT", "US5949181045")],
      new Set(["AAPL"]),
      new Set(),
      new Set(),
      new Set(),
    );
    expect([...result.keys()]).toEqual(["MSFT"]);
  });

  it("filters out hidden tickers", () => {
    const result = selectPositionsToSync(
      [pos("AAPL", "US0378331005")],
      new Set(),
      new Set(["AAPL"]),
      new Set(),
      new Set(),
    );
    expect(result.size).toBe(0);
  });

  it("filters out tickers with no options available", () => {
    const result = selectPositionsToSync(
      [pos("AAPL", "US0378331005")],
      new Set(),
      new Set(),
      new Set(["AAPL"]),
      new Set(),
    );
    expect(result.size).toBe(0);
  });

  it("does not re-add a ticker the user already removed (sticky via alreadySynced)", () => {
    // Regression test: watchlistTickers no longer contains AAPL (user removed
    // it), but alreadySynced still does — it must stay excluded.
    const result = selectPositionsToSync(
      [pos("AAPL", "US0378331005")],
      new Set(),
      new Set(),
      new Set(),
      new Set(["AAPL"]),
    );
    expect(result.size).toBe(0);
  });

  it("normalizes ticker case so equivalent positions collapse to one entry", () => {
    const result = selectPositionsToSync(
      [pos("san.mc", "ES0113900J37", "Santander A"), pos("SAN.MC", "ES0113900J37", "Santander B")],
      new Set(),
      new Set(),
      new Set(),
      new Set(),
    );
    expect([...result.keys()]).toEqual(["SAN.MC"]);
  });

  it("falls back to the (uppercased) ISIN when ticker is missing", () => {
    const result = selectPositionsToSync(
      [pos(null, "es0113900j37")],
      new Set(),
      new Set(),
      new Set(),
      new Set(),
    );
    expect([...result.keys()]).toEqual(["ES0113900J37"]);
  });

  it("excludes a position with neither ticker nor isin instead of throwing", () => {
    const result = selectPositionsToSync(
      [pos(null, "")],
      new Set(),
      new Set(),
      new Set(),
      new Set(),
    );
    expect(result.size).toBe(0);
  });

  it("returns an empty map (early-exit condition) when nothing is eligible", () => {
    const result = selectPositionsToSync(
      [pos("AAPL", "US0378331005")],
      new Set(["AAPL"]),
      new Set(),
      new Set(),
      new Set(),
    );
    expect(result.size).toBe(0);
  });
});
