/**
 * Portfolio page response types and transaction display constants.
 *
 * They lived at the top of page.tsx; nothing outside the portfolio page has
 * ever referenced them (`src/lib/types.ts` has no equivalent shapes).
 */

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
