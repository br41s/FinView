"use client";

import { useEffect, useReducer, useRef } from "react";

import { api } from "@/lib/api";
import { bestEffort } from "@/lib/bestEffort";
import { selectPositionsToSync } from "@/lib/optionsWatchlistSync";

import { initialOptionsData, optionsDataReducer, type OptionsData } from "./optionsData";
import type { AgentStatus, Alert, Position, Snapshot, Unusual, WatchlistItem } from "./types";

/**
 * The options page's server data: its loads, the watchlist auto-sync, and every
 * mutation, as actions. Returns read-only state and commands, never a setter —
 * the transitions live in `optionsDataReducer`.
 *
 * Held by the page, not a tab: both tabs and the stats cards read the same
 * alerts and watchlist, and Radix unmounts inactive `TabsContent`.
 */
export interface OptionsDataHook extends OptionsData {
  retryOptionsLoad: () => void;
  /** Trigger an agent cycle and wait for it, then reload everything. */
  runCycle: () => Promise<void>;
  toggleAgent: () => Promise<void>;
  addTicker: (ticker: string, name?: string) => Promise<void>;
  removeTicker: (id: number, ticker?: string) => Promise<void>;
  hidePosition: (ticker: string) => Promise<void>;
  toggleItem: (id: number) => Promise<void>;
  ackAlert: (id: number) => Promise<void>;
  ackAll: () => Promise<void>;
}

async function fetchOptionsBundle() {
  const [snapshots, alerts, unusual, watchlist, agentStatus, hidden] = await Promise.all([
    api.options.snapshots() as Promise<Snapshot[]>,
    api.options.alerts() as Promise<Alert[]>,
    api.options.unusual() as Promise<Unusual[]>,
    api.options.watchlist() as Promise<WatchlistItem[]>,
    api.options.agentStatus() as Promise<AgentStatus>,
    api.options.hiddenPortfolioTickers() as Promise<string[]>,
  ]);
  return { snapshots, alerts, unusual, watchlist, agentStatus, hidden };
}

export function useOptionsData(): OptionsDataHook {
  const [state, dispatch] = useReducer(optionsDataReducer, initialOptionsData);
  const {
    positions,
    watchlist,
    agentStatus,
    hiddenTickers,
    noOptionsTickers,
    availabilityChecked,
    loadingOptions,
    retryOptions,
  } = state;

  // Technical (zone-break) signals. These come from Zonas Clave, the trigger
  // layer — they belong in the Monitor because acting on a trigger is what this
  // page is for. Best-effort: the options alerts stand on their own without them.
  useEffect(() => {
    api.zonasClav
      .signals()
      .then((signals) => dispatch({ type: "techSignalsLoaded", signals }))
      .catch(bestEffort("technical signals panel"));
  }, [retryOptions]);

  // Load portfolio positions with skip_prices=true — no yfinance calls, instant response
  useEffect(() => {
    api.portfolio
      .positions(true)
      .then(async (pos) => {
        const loaded = pos as Position[];
        dispatch({ type: "positionsLoaded", positions: loaded });
        if (loaded.length === 0) return;
        const tickers = [...new Set(loaded.map((p) => (p.ticker || p.isin).toUpperCase()))];
        try {
          const { no_options } = await api.options.checkAvailability(tickers);
          dispatch({ type: "noOptionsLoaded", tickers: no_options });
        } catch (e) {
          // Positions remain visible if the check fails.
          bestEffort("options availability check")(e);
        }
      })
      .catch((e) => {
        console.error("Failed to load positions:", e);
        dispatch({ type: "positionsFailed", error: "No se pudieron cargar las posiciones de cartera." });
      })
      .finally(() => dispatch({ type: "availabilityChecked" }));
  }, []);

  // Load options data in parallel (independent of positions)
  useEffect(() => {
    fetchOptionsBundle()
      .then((bundle) => dispatch({ type: "optionsLoaded", bundle }))
      .catch((e) => {
        console.error("Failed to load options data:", e);
        dispatch({ type: "optionsFailed", error: "No se pudieron cargar los datos de opciones." });
      })
      .finally(() => dispatch({ type: "optionsSettled" }));
  }, [retryOptions]);

  // Auto-sync: portfolio positions get added to the options watchlist so
  // Sentimiento/P-C Ratio/IV vs HV populate without a manual click. Waits for
  // the availability check (so we skip tickers with no options chain).
  // `watchlist` is intentionally NOT a dependency: it changes every time this
  // effect adds something (and whenever the user removes a ticker via the
  // Trash2 button), which would otherwise immediately re-add anything the
  // user just removed. Instead, `syncedTickersRef` remembers every ticker
  // this effect has ever seen on the watchlist (added by it or already
  // there), so a manual removal sticks — the effect only re-fires when the
  // portfolio itself changes. The current list is read through
  // `watchlistRef`, kept in sync by the effect above it, so the effect sees
  // the latest value without depending on it.
  const syncedTickersRef = useRef<Set<string>>(new Set());
  const watchlistRef = useRef(watchlist);
  useEffect(() => {
    watchlistRef.current = watchlist;
  }, [watchlist]);
  useEffect(() => {
    if (!availabilityChecked || loadingOptions || positions.length === 0) return;
    const watchlistSet = new Set(watchlistRef.current.map((w) => w.ticker));
    for (const ticker of watchlistSet) syncedTickersRef.current.add(ticker);
    const toAdd = selectPositionsToSync(
      positions,
      watchlistSet,
      hiddenTickers,
      noOptionsTickers,
      syncedTickersRef.current,
    );
    if (toAdd.size === 0) return;
    let cancelled = false;
    (async () => {
      for (const { ticker, name } of toAdd.values()) {
        if (cancelled) return;
        try {
          await api.options.addToWatchlist(ticker, name);
          syncedTickersRef.current.add(ticker);
        } catch (e) {
          // E.g. already added by a concurrent sync; settles on the next pass.
          bestEffort(`options watchlist sync ${ticker}`)(e);
        }
      }
      if (cancelled) return;
      const wl = (await api.options.watchlist()) as WatchlistItem[];
      if (!cancelled) dispatch({ type: "watchlistLoaded", watchlist: wl });
    })();
    return () => {
      cancelled = true;
    };
  }, [availabilityChecked, loadingOptions, positions, hiddenTickers, noOptionsTickers]);

  async function refreshWatchlist() {
    const wl = (await api.options.watchlist()) as WatchlistItem[];
    dispatch({ type: "watchlistLoaded", watchlist: wl });
  }

  async function runCycle() {
    const before = agentStatus?.total_cycles ?? 0;
    const result = await api.options.runCycle();
    // Local mode returns immediately and needs polling. Cloud Run returns
    // only after the request-scoped cycle has completed.
    if (result.status === "started") {
      for (let attempt = 0; attempt < 100; attempt++) {
        await new Promise((resolve) => setTimeout(resolve, 3000));
        const status = (await api.options.agentStatus()) as AgentStatus;
        dispatch({ type: "agentStatusLoaded", status });
        if (status.total_cycles > before) break;
      }
    }
    dispatch({ type: "optionsLoaded", bundle: await fetchOptionsBundle() });
  }

  async function toggleAgent() {
    if (agentStatus?.running) {
      await api.options.stopAgent();
    } else {
      await api.options.startAgent();
    }
    const status = (await api.options.agentStatus()) as AgentStatus;
    dispatch({ type: "agentStatusLoaded", status });
  }

  async function addTicker(ticker: string, name?: string) {
    await api.options.addToWatchlist(ticker, name);
    await refreshWatchlist();
  }

  async function removeTicker(id: number, ticker?: string) {
    await api.options.removeFromWatchlist(id);
    dispatch({ type: "tickerRemoved", id, ticker });
  }

  async function hidePosition(ticker: string) {
    // Remove from watchlist if present
    const item = watchlist.find((w) => w.ticker === ticker);
    if (item) await removeTicker(item.id, ticker);
    // Persist exclusion from options monitor
    await api.options.hidePortfolioTicker(ticker);
    dispatch({ type: "tickerHidden", ticker });
  }

  async function toggleItem(id: number) {
    await api.options.toggleWatchlistItem(id);
    dispatch({ type: "itemToggled", id });
  }

  async function ackAlert(id: number) {
    await api.options.ackAlert(id);
    dispatch({ type: "alertAcked", id });
  }

  async function ackAll() {
    await api.options.ackAllAlerts();
    dispatch({ type: "allAlertsAcked" });
  }

  return {
    ...state,
    retryOptionsLoad: () => dispatch({ type: "optionsRetried" }),
    runCycle,
    toggleAgent,
    addTicker,
    removeTicker,
    hidePosition,
    toggleItem,
    ackAlert,
    ackAll,
  };
}
