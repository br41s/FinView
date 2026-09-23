/**
 * Portfolio page response types, transaction display constants and the
 * props shared by the two positions-list renderings.
 *
 * They lived at the top of page.tsx; nothing outside the portfolio page has
 * ever referenced them (`src/lib/types.ts` has no equivalent shapes).
 */

import type { OhlcBar } from "@/lib/api";
import type { ChartScope } from "@/lib/chartMarkers";
import type { GeoSignal } from "@/lib/geo";

export interface Position {
  isin: string;
  ticker: string | null;
  name: string;
  country: string | null;
  broker: string;
  quantity: number;
  avg_cost_eur: number | null;
  total_cost_eur: number | null;
  current_price_eur: number | null;
  market_value_eur: number | null;
  unrealized_pl_eur: number | null;
  unrealized_pl_pct: number | null;
  weight_pct: number | null;
}

export interface Summary {
  total_positions: number;
  unique_assets: number;
  brokers: number;
  total_invested: number | null;
  total_market_value: number | null;
  unrealized_pl: number | null;
  unrealized_pl_pct: number | null;
  cost_basis_complete: boolean;
  valuation_complete: boolean;
}

export interface AccountBreakdown {
  broker: string;
  account_id: number;
  quantity: number;
  cost_eur: number | null;
  value_eur: number | null;
}

export interface TxHistory {
  id: number;
  type: string;
  date: string;
  quantity: number;
  price: number;
  currency: string;
  net_eur: number;
}

export interface DividendByYear {
  year: number;
  gross_eur: number;
  net_eur: number;
  count: number;
}

export interface PositionDetail {
  isin: string;
  name: string;
  ticker: string | null;
  country: string | null;
  total_quantity: number;
  avg_cost_eur: number | null;
  total_cost_eur: number | null;
  current_price_eur: number | null;
  market_value_eur: number | null;
  unrealized_pl_eur: number | null;
  unrealized_pl_pct: number | null;
  accounts: AccountBreakdown[];
  transactions: TxHistory[];
  dividends_by_year: DividendByYear[];
  dividend_events?: { date: string; net_eur: number }[];
}

export const TX_LABELS: Record<string, string> = {
  BUY: "Compra",
  SELL: "Venta",
  DIVIDEND: "Dividendo",
  INTEREST: "Interés",
  FEE: "Comisión",
  SPINOFF: "Spinoff",
  CORPORATE_ACTION: "Acción corporativa",
};

export const TX_COLORS: Record<string, string> = {
  BUY: "bg-emerald-100 text-emerald-700",
  SELL: "bg-red-100 text-red-700",
  DIVIDEND: "bg-blue-100 text-blue-700",
};

/**
 * Every binding the desktop table and the mobile list read from the page.
 * Both renderings take exactly this shape so the page passes one prop set.
 */
export interface PositionsListProps {
  positions: Position[];
  pricesLoaded: boolean;
  expandedIsin: string | null;
  details: Map<string, PositionDetail>;
  loadingDetail: string | null;
  onExpand: (isin: string) => void;
  /** Highest-importance active geo signal per upper-cased ticker. */
  geoByTicker: Map<string, GeoSignal>;
  /** Upper-cased tickers already on the Zonas Clave watchlist. */
  zcWatchlist: Set<string>;
  /** Tickers whose "add to Zonas Clave" request is in flight. */
  zcAdding: Set<string>;
  onAddToZonas: (p: Position) => Promise<void>;
  /** OHLC cache keyed by `${isin}:${scope}`; forwarded to PositionDetailPanel. */
  ohlcByIsin: Map<string, OhlcBar[]>;
  chartScope: ChartScope;
  setChartScope: (scope: ChartScope) => void;
}
