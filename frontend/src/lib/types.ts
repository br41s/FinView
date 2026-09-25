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
  calculation_version: string | null;
}

export interface FIFOAdjustment {
  id: number;
  fiscal_year: number;
  isin: string;
  name: string;
  broker_pl_eur: string;
  fifo_pl_eur: string;
  adjustment_eur: string;
  broker_gains_eur: string | null;
  broker_losses_eur: string | null;
  fifo_gains_eur: string | null;
  fifo_losses_eur: string | null;
  calculation_version: string | null;
  note: string;
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
// Shapes below mirror backend/api/schemas.py; the chart endpoints now declare
// those models, so this file follows them rather than the other way round.
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
  isin: string | null;
  name: string;
  country: string | null;
  gross: string;
  withholding: string;
  net: string;
  count: number;
}

export interface CapitalGainsBreakdown {
  isin: string | null;
  name: string;
  gains: string;
  losses: string;
  net: string;
  trades: number;
}

export interface PatrimonioComposition {
  casilla: number;
  description: string | null;
  amount: string;
  fiscal_year: number;
}

export interface DividendYield {
  isin: string;
  name: string;
  ticker: string | null;
  country: string | null;
  total_dividends: string;
  /** null when the open position's cost basis is unknown (as on the portfolio page). */
  total_invested: string | null;
  qty_remaining: string;
  latest_price: string;
  current_value: string;
  yield_on_cost: string | null;
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
  isin: string | null;
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

// Fiscal onboarding — savings-base estimate (v1 individual)
export interface FiscalProfile {
  fiscal_year: number;
  age: number | null;
  disability: "general" | "severe" | null;
  descendants: number;
  general_base: string;
  prior_rcm_loss: string;
  prior_gp_loss: string;
  updated_at?: string | null;
}

export type ManualCategory = "INTEREST" | "DIVIDEND" | "GAIN" | "LOSS" | "RCM";

export interface ManualSavingsIncome {
  id: number;
  fiscal_year: number;
  category: ManualCategory; // RCM is legacy (pre interest/dividend split)
  label: string;
  amount_eur: string;
  withholding_eur: string;
}

export interface SavingsEstimate {
  fiscal_year: number;
  rates_year_used: number;
  rcm_net: string;
  gp_net: string;
  savings_base: string;
  rcm_carryforward: string;
  gp_carryforward: string;
  prior_rcm_loss_applied: string;
  prior_gp_loss_applied: string;
  personal_minimum: string;
  minimum_on_savings: string;
  gross_quota: string;
  quota: string;
  withholdings: string;
  cash_withholdings: string;
  domestic_withholdings: string;
  double_taxation_credit: string;
  double_taxation_credit_applied: string;
  withholding_breakdown_complete: boolean;
  incomplete_withholding_transactions: number;
  result: string; // >0 a ingresar · <0 a devolver
  brackets: { from: string; to: string; rate: string; tax: string }[];
  casillas: Record<string, string>;
}
