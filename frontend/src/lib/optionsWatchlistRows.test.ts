import { describe, expect, it } from "vitest";
import {
  buildWatchlistRows,
  groupLotsByTicker,
  type RowPosition,
  type RowWatchlistItem,
} from "./optionsWatchlistRows";

function pos(ticker: string | null, isin: string, broker = "DEGIRO"): RowPosition {
  return { ticker, isin, broker };
}

function wl(id: number, ticker: string, enabled = true): RowWatchlistItem {
  return { id, ticker, name: `${ticker} Co`, enabled };
}

describe("groupLotsByTicker", () => {
  it("collapses the same ticker held at several brokers into one entry", () => {
    const result = groupLotsByTicker(
      [pos("SAN.MC", "ES0113900J37", "DEGIRO"), pos("SAN.MC", "ES0113900J37", "IBKR")],
      new Set(),
      new Set(),
    );
    expect(result.size).toBe(1);
    expect(result.get("SAN.MC")?.map((p) => p.broker)).toEqual(["DEGIRO", "IBKR"]);
  });

  it("falls back to the ISIN when the position has no ticker", () => {
    const result = groupLotsByTicker([pos(null, "US0378331005")], new Set(), new Set());
    expect([...result.keys()]).toEqual(["US0378331005"]);
  });

  it("uppercases tickers so casing can't split one holding into two", () => {
    const result = groupLotsByTicker(
      [pos("aapl", "US0378331005"), pos("AAPL", "US0378331005", "IBKR")],
      new Set(),
      new Set(),
    );
    expect(result.size).toBe(1);
    expect(result.get("AAPL")).toHaveLength(2);
  });

  it("drops hidden tickers and tickers with no options chain", () => {
    const result = groupLotsByTicker(
      [pos("AAPL", "US0378331005"), pos("HIDE", "X1"), pos("NOOPT", "X2")],
      new Set(["HIDE"]),
      new Set(["NOOPT"]),
    );
    expect([...result.keys()]).toEqual(["AAPL"]);
  });
});

describe("buildWatchlistRows", () => {
  it("marks watchlist tickers that are held, and leaves the rest without lots", () => {
    const rows = buildWatchlistRows(
      [wl(1, "AAPL"), wl(2, "TSLA")],
      [pos("AAPL", "US0378331005")],
      new Set(),
      new Set(),
    );
    expect(rows.map((r) => [r.item.ticker, r.lots.length])).toEqual([
      ["AAPL", 1],
      ["TSLA", 0],
    ]);
  });

  it("orders held tickers first, then alphabetically within each group", () => {
    const rows = buildWatchlistRows(
      [wl(1, "ZZZ"), wl(2, "AAA"), wl(3, "MMM"), wl(4, "BBB")],
      [pos("MMM", "X1"), pos("ZZZ", "X2")],
      new Set(),
      new Set(),
    );
    expect(rows.map((r) => r.item.ticker)).toEqual(["MMM", "ZZZ", "AAA", "BBB"]);
  });

  it("does not reorder when only sentiment-ish data would have changed", () => {
    // Ordering must depend on holdings + ticker alone, never on snapshot data,
    // so a cycle landing mid-session can't reshuffle rows under the cursor.
    const watchlist = [wl(1, "BBB"), wl(2, "AAA")];
    const first = buildWatchlistRows(watchlist, [], new Set(), new Set());
    const second = buildWatchlistRows(watchlist, [], new Set(), new Set());
    expect(first.map((r) => r.item.ticker)).toEqual(second.map((r) => r.item.ticker));
    expect(first.map((r) => r.item.ticker)).toEqual(["AAA", "BBB"]);
  });

  it("keeps a watchlist ticker whose position is hidden, but without lots", () => {
    // Hiding a position removes it from the watchlist via the API; if the two
    // ever disagree, the row must still render rather than vanish silently.
    const rows = buildWatchlistRows(
      [wl(1, "AAPL")],
      [pos("AAPL", "US0378331005")],
      new Set(["AAPL"]),
      new Set(),
    );
    expect(rows).toHaveLength(1);
    expect(rows[0].lots).toEqual([]);
  });

  it("returns an empty list when the watchlist is empty, even with positions", () => {
    expect(buildWatchlistRows([], [pos("AAPL", "X1")], new Set(), new Set())).toEqual([]);
  });
});
