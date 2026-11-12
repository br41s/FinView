import type { Confidence, EventType, Severity, WorldAsset } from "./types";

/**
 * Event priority (spec §5.5): deterministic and explainable, never an LLM judgement.
 *
 *   score = base(type) × magnitude × portfolioRelevance × confidence
 *
 * A high score means "worth looking at first", never "buy" or "sell".
 * Every factor is returned so the card can show why an event is Important.
 */

const EVENT_BASE: Record<EventType, number> = {
  price_move_up: 1,
  price_move_down: 1,
  earnings_beat: 2,
  earnings_miss: 2,
  dividend_declared: 1,
  dividend_paid: 1.2,
  site_expansion: 1.5,
  technical_signal: 1,
  options_alert: 1,
  position_added: 0.8,
  position_reduced: 0.8,
  position_closed: 1.5,
  week52_high: 1.3,
  week52_low: 1.3,
  volume_spike: 1,
  stock_split: 1.2,
  shares_received: 1.2,
  dividend_raised: 1.3,
  dividend_cut: 1.5,
  annual_report: 1,
  geo_alert: 1.2,
};

const CONFIDENCE_FACTOR: Record<Confidence, number> = {
  verified: 1,
  reported: 0.8,
  derived: 0.7,
  // Demo events are scored like verified ones so the fictional town shows realistic severities.
  demo: 1,
};

export interface PriorityBreakdown {
  base: number;
  magnitude: number;
  relevance: number;
  confidence: number;
  score: number;
}

const clamp = (x: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, x));

/**
 * 1 at a 2 % move / 5 % surprise, 3 at 6x that, 0.5 at almost nothing. A missing figure
 * is neutral (1): an unknown magnitude must not be invented in either direction.
 */
export function magnitudeFactor(
  type: EventType,
  metrics: Record<string, number | string | null>,
): number {
  const num = (k: string) => (typeof metrics[k] === "number" ? (metrics[k] as number) : null);
  if (type === "price_move_up" || type === "price_move_down") {
    const c = num("change_pct");
    return c === null ? 1 : clamp(Math.abs(c) / 2, 0.5, 3);
  }
  if (type === "dividend_raised" || type === "dividend_cut") {
    const c = num("change_pct");
    return c === null ? 1 : clamp(Math.abs(c) / 15, 0.5, 3);
  }
  if (type === "volume_spike") {
    const r = num("volume_ratio");
    return r === null ? 1 : clamp(r / 2.5, 0.5, 3);
  }
  if (type === "geo_alert") {
    const i = num("importance");
    return i === null ? 1 : clamp(i / 60, 0.5, 3);
  }
  if (type === "earnings_beat" || type === "earnings_miss") {
    const s = num("surprise_pct");
    return s === null ? 1 : clamp(Math.abs(s) / 5, 0.5, 3);
  }
  return 1;
}

/** 0.5 for a trace position, up to 2 at 10 % of the portfolio. Unknown weight → 1. */
export function relevanceFactor(weightPct: number | null): number {
  if (weightPct === null || !Number.isFinite(weightPct)) return 1;
  return 0.5 + (clamp(weightPct, 0, 10) / 10) * 1.5;
}

export function scoreEvent(
  type: EventType,
  metrics: Record<string, number | string | null>,
  asset: Pick<WorldAsset, "weightPct"> | null,
  confidence: Confidence,
): PriorityBreakdown {
  const base = EVENT_BASE[type];
  const magnitude = magnitudeFactor(type, metrics);
  const relevance = relevanceFactor(asset ? asset.weightPct : null);
  const conf = CONFIDENCE_FACTOR[confidence];
  return { base, magnitude, relevance, confidence: conf, score: base * magnitude * relevance * conf };
}

/** Bucket boundaries. Raw scores stay available; only the label depends on these. */
export const IMPORTANT_AT = 2;
export const CRITICAL_AT = 6;

/**
 * The one place where "how much noise with ~100 holdings" is decided. Brais confirmed the
 * 2 / 6 thresholds (2026-11-08). They give roughly: a 3 % move on a 2 % position ≈ 1.2
 * (normal), a 6 % move on a 5 % position ≈ 3.5 (important), a large earnings miss on a big
 * position ≈ 8 (critical). Revisit with real event volumes in Phase 1; a non-linear rule
 * (percentile of recent scores) is the alternative if the real stream is too loud.
 */
export function bucketFor(score: number): Severity {
  if (score >= CRITICAL_AT) return "critical";
  if (score >= IMPORTANT_AT) return "important";
  return "normal";
}
