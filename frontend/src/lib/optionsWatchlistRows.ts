export interface RowPosition {
  ticker: string | null;
  isin: string;
  broker: string;
}

export interface RowWatchlistItem {
  id: number;
  ticker: string;
  name: string;
  enabled: boolean;
}

export interface WatchlistRow<P extends RowPosition, W extends RowWatchlistItem> {
  item: W;
  /**
   * Every held lot for this ticker. A ticker can be held at several brokers at
   * once (FIFO is cross-broker), so this is a list, not a single position —
   * grouping by ticker is what keeps one row per ticker instead of one per lot.
   */
  lots: P[];
}

/**
 * Groups held positions by ticker, dropping hidden ones and any whose
 * underlying has no options chain.
 */
export function groupLotsByTicker<P extends RowPosition>(
  positions: readonly P[],
  hiddenTickers: ReadonlySet<string>,
  noOptionsTickers: ReadonlySet<string>,
): Map<string, P[]> {
  const byTicker = new Map<string, P[]>();
  for (const p of positions) {
    const ticker = (p.ticker || p.isin || "").toUpperCase();
    if (ticker === "") continue;
    if (hiddenTickers.has(ticker)) continue;
    if (noOptionsTickers.has(ticker)) continue;
    const lots = byTicker.get(ticker);
    if (lots) lots.push(p);
    else byTicker.set(ticker, [p]);
  }
  return byTicker;
}

/**
 * Builds the Options Monitor's unified list: one row per watchlist ticker,
 * enriched with the held lots (empty for tickers that are only tracked, not
 * owned). The watchlist is the spine because portfolio positions auto-sync into
 * it, making it a superset of what's held.
 *
 * Ordering is held-first then alphabetical — deliberately independent of
 * sentiment and alert counts, so an agent cycle landing mid-session doesn't
 * reshuffle the list under the user's cursor.
 */
export function buildWatchlistRows<P extends RowPosition, W extends RowWatchlistItem>(
  watchlist: readonly W[],
  positions: readonly P[],
  hiddenTickers: ReadonlySet<string>,
  noOptionsTickers: ReadonlySet<string>,
): WatchlistRow<P, W>[] {
  const lotsByTicker = groupLotsByTicker(positions, hiddenTickers, noOptionsTickers);
  return watchlist
    .map((item) => ({ item, lots: lotsByTicker.get(item.ticker.toUpperCase()) ?? [] }))
    .sort((a, b) => {
      const aRank = a.lots.length > 0 ? 0 : 1;
      const bRank = b.lots.length > 0 ? 0 : 1;
      return aRank - bRank || a.item.ticker.localeCompare(b.item.ticker);
    });
}
