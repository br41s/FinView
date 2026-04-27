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

export interface DataIssue {
  id: number;
  issue_type: string;
  severity: string;
  isin: string | null;
  name: string;
  description: string;
  status: string;
  auto_resolution: string | null;
  resolution_data: string | null;
}

export interface ImportResult {
  status: string;
  message?: string;
  import_id?: number;
  fiscal_year?: number;
  counts?: Record<string, number>;
  issues?: DataIssue[];
}

export interface ImportRecord {
  id: number;
  filename: string;
  broker: string;
  fiscal_year: number | null;
  imported_at: string;
  record_count: number;
}

export interface BrokerAmount {
  broker: string;
  amount_eur: string;
}

export interface Casilla {
  modelo: number;
  casilla: number;
  description: string;
  amount_eur: string;
  brokers: BrokerAmount[];
  fifo_adjustment_eur: string | null;
  tr_reference_amount: string | null;
  validation_status: string | null;
}

export interface CrossBrokerLot {
  id: number;
  fiscal_year: number;
  isin: string;
  name: string;
  buy_broker: string;
  sell_broker: string;
  quantity: string;
  cost_basis_eur: string;
  proceeds_eur: string;
  realized_pl_eur: string;
  holding_period: string | null;
  casilla: number;
}

export interface FIFOAdjustment {
  id: number;
  fiscal_year: number;
  isin: string;
  name: string;
  broker_pl_eur: string;
  fifo_pl_eur: string;
  adjustment_eur: string;
  note: string;
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
  name: string;
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
  currency: string;
  original_price: string | null;
  fx_rate: string | null;
}

export interface WithholdingsByCountry {
  country: string;
  gross: string;
  withholding: string;
  net: string;
  effective_rate: string;
}

export interface CompanyDividendsYearly {
  isin: string;
  name: string;
  ticker: string;
  years: Record<string, string>;
  total: string;
}

export interface OptionAssignment {
  id: number;
  fiscal_year: number;
  assignment_date: string;
  underlying: string;
  option_symbol: string;
  option_type: string; // PUT / CALL
  strike: string;
  stock_quantity: string;
  stock_isin: string;
  premium_eur: string;
}

// Cross-validation types
export interface CrossValidationRow {
  modelo: number;
  casilla: number;
  description: string;
  finview_amount: string;
  compare_amount: string;
  tr_amount: string | null;
  difference: string | null;
  status: string;
  is_multi_broker: boolean;
  brokers: BrokerAmount[];
}

export interface CrossValidationResult {
  fiscal_year: number;
  rows: CrossValidationRow[];
  total_match: number;
  total_mismatch: number;
  total_no_ref: number;
}

// Yearly comparison types
export interface YearlyMetrics {
  fiscal_year: number;
  dividends_gross: string;
  gains: string;
  losses: string;
  net_capital: string;
  withholdings: string;
  brokers: number;
  positions: number;
}

export interface YearlyComparisonResult {
  years: YearlyMetrics[];
}
