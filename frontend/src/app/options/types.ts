/**
 * Types shared by the Options page and the tabs, cards and hooks beside it.
 *
 * All of them lived in page.tsx. The page-level shapes (positions, snapshots,
 * alerts, unusual activity, agent status, watchlist items) are here because
 * the watchlist and monitor tabs read them through explicit props; the
 * backtest-domain types below are read only by that tab and its hook.
 */

// ── Page-level shapes ───────────────────────────────────────────────

export interface Position {
  isin: string;
  ticker: string | null;
  name: string;
  country: string | null;
  broker: string;
  quantity: number;
  avg_cost_eur: number;
  total_cost_eur: number;
  current_price_eur: number | null;
  market_value_eur: number | null;
  unrealized_pl_eur: number | null;
  unrealized_pl_pct: number | null;
  weight_pct: number | null;
}

export interface Snapshot {
  id: number;
  timestamp: string;
  ticker: string;
  current_price: string | number;
  call_volume: number;
  put_volume: number;
  put_call_ratio_volume: string | number | null;
  avg_call_iv: string | number | null;
  avg_put_iv: string | number | null;
  historical_volatility: string | number | null;
  iv_skew: string | number | null;
  market_sentiment: string | null;
}

export interface Alert {
  id: number;
  timestamp: string;
  ticker: string;
  alert_type: string;
  message: string;
  severity: string;
  acknowledged: boolean;
  regime_alignment?: string | null;
}

export interface Unusual {
  id: number;
  timestamp: string;
  ticker: string;
  option_type: string;
  strike: string | number;
  expiration: string;
  volume: number;
  open_interest: number;
  vol_oi_ratio: string | number;
  implied_volatility: string | number | null;
  last_price: string | number | null;
}

export interface AgentStatus {
  running: boolean;
  external_scheduler: boolean;
  interval_minutes: number;
  last_cycle: string | null;
  total_cycles: number;
}

export interface WatchlistItem {
  id: number;
  ticker: string;
  name: string;
  enabled: boolean;
  created_at: string;
}

// ── Backtest domain ─────────────────────────────────────────────────

export type AlignBucket = { correct: number; total: number; accuracy_pct: number | null };

export interface BacktestSignal {
  id: number;
  recorded_at: string;
  ticker: string;
  signal_type: string;
  direction: string;
  price_at_signal: string | number;
  alert_message: string;
  price_at_1d: string | number | null;
  price_at_3d: string | number | null;
  price_at_7d: string | number | null;
  outcome_1d: string | null;
  outcome_3d: string | null;
  outcome_7d: string | null;
}

export interface BacktestHorizonStats {
  evaluated: number;
  correct: number;
  incorrect: number;
  neutral: number;
  accuracy_pct: number | null;
}

export interface BacktestStats {
  total: number;
  evaluated: number;
  by_horizon: Record<string, BacktestHorizonStats>;
  by_signal_type: Record<string, { correct: number; total: number; accuracy_pct: number | null }>;
  by_alignment?: Record<string, { correct: number; total: number; accuracy_pct: number | null }>;
}

export interface Calibration {
  window_days: number;
  since: string;
  total: number;
  evaluated_7d: number;
  newest: string | null;
  by_type_alignment: Record<string, Record<string, AlignBucket>>;
  dedup_health: Record<
    string,
    { rows: number; ticker_days: number; rows_per_ticker_day: number | null }
  >;
}
