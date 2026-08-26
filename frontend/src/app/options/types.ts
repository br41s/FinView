/**
 * Backtest-domain types, shared by the tab and its hook.
 *
 * They lived in page.tsx alongside every other type on the page; nothing
 * outside the backtest tab has ever referenced them.
 */

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
