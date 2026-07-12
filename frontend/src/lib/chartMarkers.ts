// Shared helpers for the position price charts (portfolio list + detail page).
import type { OhlcBar } from "@/lib/api";
import type { PriceMarker } from "@/components/charts/PriceChart";

interface TxLike {
  type: string;
  date: string;
}

const MARKER_CFG = {
  BUY: { position: "belowBar", color: "#22c55e", shape: "arrowUp", letter: "C" },
  SELL: { position: "aboveBar", color: "#ef4444", shape: "arrowDown", letter: "V" },
  DIVIDEND: { position: "belowBar", color: "#3b82f6", shape: "circle", letter: "D" },
} as const;

type MarkerCat = keyof typeof MARKER_CFG;

/**
 * Build chart markers from transactions: buys (▲), sells (▼) and dividends (●).
 * Same-day transactions of the same category collapse into one marker whose
 * label carries the count (e.g. "C3"), so DCA / multi-fill days don't pile up.
 */
export function executionMarkers(txs: TxLike[]): PriceMarker[] {
  const groups = new Map<string, { cat: MarkerCat; date: string; count: number }>();
  for (const t of txs) {
    if (!(t.type in MARKER_CFG)) continue;
    const cat = t.type as MarkerCat;
    const date = t.date.slice(0, 10);
    const key = `${date}:${cat}`;
    const g = groups.get(key);
    if (g) g.count += 1;
    else groups.set(key, { cat, date, count: 1 });
  }
  return Array.from(groups.values()).map((g) => {
    const c = MARKER_CFG[g.cat];
    return {
      date: g.date,
      position: c.position,
      color: c.color,
      shape: c.shape,
      text: g.count > 1 ? `${c.letter}${g.count}` : c.letter,
    };
  });
}

export type ChartScope = "1D" | "1W" | "1M" | "1A" | "5A" | "MAX";
export const CHART_SCOPES: ChartScope[] = ["1D", "1W", "1M", "1A", "5A", "MAX"];

/**
 * yfinance (period, interval) to request per scope, passed straight through
 * to GET /charts/price-history. Short scopes use intraday intervals — daily
 * bars alone give 1D/1W/1M almost nothing to plot — capped at what yfinance
 * actually allows for each interval (backend re-validates the same limits).
 */
export const SCOPE_PARAMS: Record<ChartScope, { period: string; interval: string }> = {
  "1D": { period: "1d", interval: "5m" },
  "1W": { period: "5d", interval: "15m" },
  "1M": { period: "1mo", interval: "1h" },
  "1A": { period: "1y", interval: "1d" },
  "5A": { period: "5y", interval: "1d" },
  MAX: { period: "max", interval: "1d" },
};

/**
 * Snap day-keyed markers (buy/sell/dividend) onto the exact bar time of the
 * fetched series. Needed because intraday series carry a per-bar timestamp,
 * not a whole-day key — a marker whose day isn't in the fetched window (e.g.
 * a 3-year-old trade viewed at 1D scope) is dropped, matching what's visible.
 */
export function alignMarkersToBars(markers: PriceMarker[], bars: OhlcBar[]): PriceMarker[] {
  if (bars.length === 0) return [];
  const firstBarOfDay = new Map<string, OhlcBar>();
  for (const b of bars) {
    if (!firstBarOfDay.has(b.date)) firstBarOfDay.set(b.date, b);
  }
  const aligned: PriceMarker[] = [];
  for (const m of markers) {
    const bar = firstBarOfDay.get(String(m.date).slice(0, 10));
    if (!bar) continue;
    aligned.push({ ...m, date: bar.time ?? bar.date });
  }
  return aligned;
}
