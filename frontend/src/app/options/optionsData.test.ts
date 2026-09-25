import { describe, expect, it } from "vitest";

import { initialOptionsData, optionsDataReducer, type OptionsData } from "./optionsData";
import type { AgentStatus, Alert, Unusual, WatchlistItem } from "./types";

function item(id: number, ticker: string, enabled = true): WatchlistItem {
  return { id, ticker, name: ticker, enabled } as WatchlistItem;
}

function alert(id: number, ticker: string, acknowledged = false): Alert {
  return { id, ticker, acknowledged } as Alert;
}

function unusual(ticker: string): Unusual {
  return { ticker } as Unusual;
}

function state(over: Partial<OptionsData> = {}): OptionsData {
  return { ...initialOptionsData, ...over };
}

describe("optionsDataReducer", () => {
  it("removing a ticker drops its alerts and unusual activity too", () => {
    const s = state({
      watchlist: [item(1, "SAN.MC"), item(2, "TEF.MC")],
      alerts: [alert(10, "SAN.MC"), alert(11, "TEF.MC")],
      unusual: [unusual("SAN.MC"), unusual("TEF.MC")],
    });

    const next = optionsDataReducer(s, { type: "tickerRemoved", id: 1, ticker: "SAN.MC" });

    expect(next.watchlist.map((w) => w.id)).toEqual([2]);
    expect(next.alerts.map((a) => a.ticker)).toEqual(["TEF.MC"]);
    expect(next.unusual.map((u) => u.ticker)).toEqual(["TEF.MC"]);
  });

  it("removing by id alone leaves alerts and unusual alone", () => {
    const s = state({
      watchlist: [item(1, "SAN.MC")],
      alerts: [alert(10, "SAN.MC")],
      unusual: [unusual("SAN.MC")],
    });

    const next = optionsDataReducer(s, { type: "tickerRemoved", id: 1 });

    expect(next.watchlist).toEqual([]);
    expect(next.alerts).toBe(s.alerts);
    expect(next.unusual).toBe(s.unusual);
  });

  it("hiding adds to the hidden set without mutating the previous one", () => {
    const s = state({ hiddenTickers: new Set(["BBVA.MC"]) });

    const next = optionsDataReducer(s, { type: "tickerHidden", ticker: "SAN.MC" });

    expect([...next.hiddenTickers].sort()).toEqual(["BBVA.MC", "SAN.MC"]);
    expect([...s.hiddenTickers]).toEqual(["BBVA.MC"]);
  });

  it("toggling flips only the matching item", () => {
    const s = state({ watchlist: [item(1, "A", true), item(2, "B", true)] });

    const next = optionsDataReducer(s, { type: "itemToggled", id: 2 });

    expect(next.watchlist.map((w) => w.enabled)).toEqual([true, false]);
  });

  it("acks one alert, or all of them", () => {
    const s = state({ alerts: [alert(1, "A"), alert(2, "B")] });

    const one = optionsDataReducer(s, { type: "alertAcked", id: 2 });
    expect(one.alerts.map((a) => a.acknowledged)).toEqual([false, true]);

    const all = optionsDataReducer(s, { type: "allAlertsAcked" });
    expect(all.alerts.every((a) => a.acknowledged)).toBe(true);
  });

  it("a retry clears the banner at once and bumps the reload key", () => {
    const s = state({ errorOptions: "No se pudieron cargar los datos de opciones." });

    const next = optionsDataReducer(s, { type: "optionsRetried" });

    expect(next.errorOptions).toBeNull();
    expect(next.retryOptions).toBe(1);
    // Loading is not re-armed by a retry: the tabs keep their content.
    expect(next.loadingOptions).toBe(s.loadingOptions);
  });

  it("a load replaces the six options collections at once", () => {
    const next = optionsDataReducer(state(), {
      type: "optionsLoaded",
      bundle: {
        snapshots: [],
        alerts: [alert(1, "A")],
        unusual: [unusual("A")],
        watchlist: [item(1, "A")],
        agentStatus: { running: false } as AgentStatus,
        hidden: ["X"],
      },
    });

    expect(next.alerts).toHaveLength(1);
    expect(next.watchlist).toHaveLength(1);
    expect(next.agentStatus?.running).toBe(false);
    expect(next.hiddenTickers.has("X")).toBe(true);
    // Settling is its own action: a failed load must still clear the spinner.
    expect(next.loadingOptions).toBe(true);
  });

  it("a failed positions load raises only its own error", () => {
    const next = optionsDataReducer(state(), { type: "positionsFailed", error: "x" });

    expect(next.errorPositions).toBe("x");
    expect(next.errorOptions).toBeNull();
    expect(next.availabilityChecked).toBe(false);
  });
});
