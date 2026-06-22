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
 * Client-side slice of OHLC bars by scope, anchored on the last bar. Data is
 * daily, so 1D shows the last few trading days rather than a single candle.
 */
export function sliceOhlc(bars: OhlcBar[], scope: ChartScope): OhlcBar[] {
  if (scope === "MAX" || bars.length === 0) return bars;
  const last = new Date(bars[bars.length - 1].date + "T12:00:00");
  const cutoff = new Date(last);
  if (scope === "1D") cutoff.setDate(last.getDate() - 5);
  else if (scope === "1W") cutoff.setDate(last.getDate() - 7);
  else if (scope === "1M") cutoff.setMonth(last.getMonth() - 1);
  else if (scope === "1A") cutoff.setFullYear(last.getFullYear() - 1);
  else if (scope === "5A") cutoff.setFullYear(last.getFullYear() - 5);
  const cutoffStr = cutoff.toISOString().slice(0, 10);
  const filtered = bars.filter((b) => b.date >= cutoffStr);
  return filtered.length >= 2 ? filtered : bars.slice(-5);
}
