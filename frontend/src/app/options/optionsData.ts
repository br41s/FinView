import type { TechnicalSignal } from "@/lib/api";

import type { Alert, AgentStatus, Position, Snapshot, Unusual, WatchlistItem } from "./types";

/**
 * The options page's server data and the load flags around it, as one reducer.
 *
 * Every mutation the page makes to this data is an action here, dispatched
 * after the API call it mirrors has succeeded. Keeping the transitions pure is
 * what makes them testable: removing a ticker also drops its alerts and
 * unusual activity, hiding one adds it to the hidden set, and a failed load
 * only raises its own error. `useOptionsData` owns the effects and the API
 * calls; the page only reads this state and calls its actions.
 */
export interface OptionsData {
  positions: Position[];
  snapshots: Snapshot[];
  alerts: Alert[];
  unusual: Unusual[];
  watchlist: WatchlistItem[];
  agentStatus: AgentStatus | null;
  hiddenTickers: Set<string>;
  noOptionsTickers: Set<string>;
  techSignals: TechnicalSignal[];
  /** Positions have loaded (or failed) and the options-chain check has run. */
  availabilityChecked: boolean;
  loadingOptions: boolean;
  errorPositions: string | null;
  errorOptions: string | null;
  /** Bumped by a retry; the options loads depend on it. */
  retryOptions: number;
}

export interface OptionsBundle {
  snapshots: Snapshot[];
  alerts: Alert[];
  unusual: Unusual[];
  watchlist: WatchlistItem[];
  agentStatus: AgentStatus;
  hidden: string[];
}

export type OptionsAction =
  | { type: "positionsLoaded"; positions: Position[] }
  | { type: "positionsFailed"; error: string }
  | { type: "noOptionsLoaded"; tickers: string[] }
  | { type: "availabilityChecked" }
  | { type: "optionsLoaded"; bundle: OptionsBundle }
  | { type: "optionsFailed"; error: string }
  | { type: "optionsSettled" }
  | { type: "optionsRetried" }
  | { type: "techSignalsLoaded"; signals: TechnicalSignal[] }
  | { type: "agentStatusLoaded"; status: AgentStatus }
  | { type: "watchlistLoaded"; watchlist: WatchlistItem[] }
  | { type: "tickerRemoved"; id: number; ticker?: string }
  | { type: "tickerHidden"; ticker: string }
  | { type: "itemToggled"; id: number }
  | { type: "alertAcked"; id: number }
  | { type: "allAlertsAcked" };

export const initialOptionsData: OptionsData = {
  positions: [],
  snapshots: [],
  alerts: [],
  unusual: [],
  watchlist: [],
  agentStatus: null,
  hiddenTickers: new Set(),
  noOptionsTickers: new Set(),
  techSignals: [],
  availabilityChecked: false,
  loadingOptions: true,
  errorPositions: null,
  errorOptions: null,
  retryOptions: 0,
};

export function optionsDataReducer(state: OptionsData, action: OptionsAction): OptionsData {
  switch (action.type) {
    case "positionsLoaded":
      return { ...state, positions: action.positions };
    case "positionsFailed":
      return { ...state, errorPositions: action.error };
    case "noOptionsLoaded":
      return { ...state, noOptionsTickers: new Set(action.tickers) };
    case "availabilityChecked":
      return { ...state, availabilityChecked: true };
    case "optionsLoaded": {
      const b = action.bundle;
      return {
        ...state,
        snapshots: b.snapshots,
        alerts: b.alerts,
        unusual: b.unusual,
        watchlist: b.watchlist,
        agentStatus: b.agentStatus,
        hiddenTickers: new Set(b.hidden),
      };
    }
    case "optionsFailed":
      return { ...state, errorOptions: action.error };
    case "optionsSettled":
      return { ...state, loadingOptions: false };
    case "optionsRetried":
      // The banner clears on the retry itself, not when the reload lands.
      return { ...state, errorOptions: null, retryOptions: state.retryOptions + 1 };
    case "techSignalsLoaded":
      return { ...state, techSignals: action.signals };
    case "agentStatusLoaded":
      return { ...state, agentStatus: action.status };
    case "watchlistLoaded":
      return { ...state, watchlist: action.watchlist };
    case "tickerRemoved": {
      const { id, ticker } = action;
      const watchlist = state.watchlist.filter((w) => w.id !== id);
      if (!ticker) return { ...state, watchlist };
      return {
        ...state,
        watchlist,
        alerts: state.alerts.filter((a) => a.ticker !== ticker),
        unusual: state.unusual.filter((u) => u.ticker !== ticker),
      };
    }
    case "tickerHidden":
      return { ...state, hiddenTickers: new Set([...state.hiddenTickers, action.ticker]) };
    case "itemToggled":
      return {
        ...state,
        watchlist: state.watchlist.map((item) =>
          item.id === action.id ? { ...item, enabled: !item.enabled } : item,
        ),
      };
    case "alertAcked":
      return {
        ...state,
        alerts: state.alerts.map((a) => (a.id === action.id ? { ...a, acknowledged: true } : a)),
      };
    case "allAlertsAcked":
      return { ...state, alerts: state.alerts.map((a) => ({ ...a, acknowledged: true })) };
  }
}
