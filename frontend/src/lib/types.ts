export interface DashboardStats {
  total_transactions: number;
  total_dividends_eur: string;
  total_gains_eur: string;
  total_losses_eur: string;
  net_pl_eur: string;
  accounts: number;
  imports: number;
  fiscal_years: number[];
}

export interface ImportResult {
  status: string;
  message?: string;
  import_id?: number;
  fiscal_year?: number;
  counts?: Record<string, number>;
}

export interface ImportRecord {
  id: number;
  filename: string;
  broker: string;
  fiscal_year: number | null;
  imported_at: string;
  record_count: number;
}

export interface Casilla {
  modelo: number;
  casilla: number;
  description: string;
  amount_eur: string;
  broker: string | null;
}

export interface FiscalSummary {
  fiscal_year: number;
  total_dividends_gross: string;
  total_dividends_net: string;
  total_withholdings: string;
  total_gains: string;
  total_losses: string;
  net_capital_gains: string;
  casillas: Casilla[];
}

export interface DividendSummary {
  isin: string;
  name: string;
  country: string | null;
  total_gross_eur: string;
  total_withholding_eur: string;
  total_net_eur: string;
  payment_count: number;
}

export interface CapitalGain {
  id: number;
  isin: string;
  buy_date: string;
  sell_date: string;
  quantity: string;
  cost_basis_eur: string;
  proceeds_eur: string;
  realized_pl_eur: string;
  holding_period: string | null;
}

export interface Transaction {
  id: number;
  type: string;
  trade_date: string;
  isin: string | null;
  name: string;
  country: string | null;
  quantity: string;
  price: string;
  currency: string;
  gross_amount: string;
  fees: string;
  withholding_tax: string;
  net_amount_eur: string;
  casilla: number | null;
  holding_period: string | null;
}

// Chart types
export interface DividendsByCountry {
  country: string;
  gross: string;
  withholding: string;
  net: string;
  count: number;
}

export interface DividendsMonthly {
  month: string;
  gross: string;
  withholding: string;
  net: string;
  count: number;
}

export interface TopDividendPayer {
  isin: string;
  name: string;
  country: string;
  gross: string;
  withholding: string;
  net: string;
  count: number;
}

export interface CapitalGainsBreakdown {
  isin: string;
  name: string;
  gains: string;
  losses: string;
  net: string;
  trades: number;
}

export interface PatrimonioComposition {
  casilla: number;
  description: string;
  amount: string;
  fiscal_year: number;
}

export interface DividendYield {
  isin: string;
  name: string;
  country: string;
  total_dividends: string;
  total_invested: string;
  qty_remaining: string;
  latest_price: string;
  current_value: string;
  yield_on_cost: string;
  yield_on_value: string;
  payment_count: number;
}

export interface WithholdingsByCountry {
  country: string;
  gross: string;
  withholding: string;
  net: string;
  effective_rate: string;
}
