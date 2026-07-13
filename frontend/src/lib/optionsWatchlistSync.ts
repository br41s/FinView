export interface SyncablePosition {
  ticker: string | null;
  isin: string;
  name: string;
}

export interface WatchlistSyncEntry {
  ticker: string;
  name: string;
}

/**
 * Pure filtering logic for the Options Monitor's portfolio→watchlist auto-sync.
 * A position is eligible once: it resolves to a non-empty ticker, isn't hidden
 * from the options monitor, has options available, isn't already tracked, and
 * hasn't already been synced before (so a manual watchlist removal — tracked
 * via `alreadySynced`, not `watchlistTickers` — sticks instead of being
 * silently re-added on the next sync pass).
 */
export function selectPositionsToSync(
  positions: readonly SyncablePosition[],
  watchlistTickers: ReadonlySet<string>,
  hiddenTickers: ReadonlySet<string>,
  noOptionsTickers: ReadonlySet<string>,
  alreadySynced: ReadonlySet<string>,
): Map<string, WatchlistSyncEntry> {
  const toAdd = new Map<string, WatchlistSyncEntry>();
  for (const p of positions) {
    const ticker = (p.ticker || p.isin || "").toUpperCase();
    if (ticker === "") continue;
    if (alreadySynced.has(ticker)) continue;
    if (hiddenTickers.has(ticker)) continue;
    if (noOptionsTickers.has(ticker)) continue;
    if (watchlistTickers.has(ticker)) continue;
    toAdd.set(ticker, { ticker, name: p.name });
  }
  return toAdd;
}
