// Geo-Intel shared types + market anchor geometry.
// (Lives in lib/ because src/data/ is gitignored; the original Lovable mock file
// stays there for local reference only — production imports come from here.)

export type GeoSignalTicker = {
  symbol: string;
  direction: "bullish" | "bearish" | "neutral";
  priceAtSignal: number | null;
};

export type GeoRule = {
  id: string;
  description: string; // what happened
  thesis: string; // why it moves markets
  confidence: number; // 0-1
  category?: string; // event bucket, e.g. "earthquake"
  trigger?: string; // the condition that fired, e.g. "mag>=6.5 near chile_mining"
};

export type GeoCheckpointHorizon = "1h" | "6h" | "1d" | "3d" | "7d";

export type GeoCheckpoint = {
  horizon: GeoCheckpointHorizon;
  targetAt: string;
  score: number | null; // 0-100
  outcome: "CORRECT" | "INCORRECT" | "NEUTRAL" | null; // null = pending
  detail: string | null;
  evaluatedAt: string | null;
};

export type GeoSignal = {
  id: string;
  headline: string;
  category:
    | "earthquake"
    | "cyclone"
    | "fire"
    | "volcano"
    | "conflict"
    | "maritime"
    | "weather";
  lat: number;
  lng: number;
  location: string;
  importance: number; // 0-100
  confidence: number; // 0-1
  riskScore: number; // 0-10
  direction: "bullish" | "bearish" | "neutral";
  tickers: GeoSignalTicker[];
  rules: GeoRule[];
  checkpoints: GeoCheckpoint[];
  timestamp: string;
  notifiedAt?: string | null; // when a channel actually delivered it; null = never
  status: "active" | "resolved";
  source?: string; // ingest feed key (usgs|EONET|gdelt|…)
  sourceUrl?: string | null; // link to the underlying source event, when captured
};

// ── Checkpoint accuracy (GET /geo/accuracy) ─────────────────────────
// The only reading of the outcome loop used to be five dots per signal, so a
// scorer comparing a daily close against itself could fail thousands of
// checkpoints at exactly 0 without anyone seeing a number.

export type GeoHorizonAccuracy = {
  correct: number;
  incorrect: number;
  neutral: number;
  pending: number;
  /** correct / (correct + incorrect). NEUTRAL is excluded — "nothing
   *  measurable moved" is not a failed thesis. null = nothing measured. */
  accuracy: number | null;
};

export type GeoRuleAccuracy = {
  ruleId: string;
  category: string;
  baseConfidence: number;
  confidenceMod: number; // auditor-learned, -0.30..+0.30
  totalSignals: number;
  correctSignals: number;
  accuracy: number | null;
};

export type GeoAccuracy = {
  since: string;
  horizons: Partial<Record<GeoCheckpointHorizon, GeoHorizonAccuracy>>;
  rules: GeoRuleAccuracy[];
};

const HORIZON_ORDER: GeoCheckpointHorizon[] = ["1h", "6h", "1d", "3d", "7d"];

const DAY = 86_400_000;

/**
 * One line of hit rate for the Ideas header, e.g.
 * `Aciertos (30 d): 1h 12 % · 6h 18 % · 1d 30 % · 3d 41 % · 7d 45 % · n=123`
 *
 * A horizon with nothing measurable reads `—`, never `0 %`: no measurement is
 * not a zero hit rate, and conflating the two is the same mistake that painted
 * NEUTRAL checkpoints as failures. `n` is the sample the percentages rest on —
 * measured checkpoints (correct + incorrect) across every horizon — so a rate
 * computed from four data points is visibly not evidence.
 *
 * Pure, with `now` injected, for the same reason geoHealth is.
 */
export function formatAccuracyLine(
  data: GeoAccuracy | null,
  now: number = Date.now(),
): string | null {
  if (!data) return null;
  const days = Math.max(1, Math.round((now - new Date(data.since).getTime()) / DAY));
  const parts = HORIZON_ORDER.map((h) => {
    const rate = data.horizons[h]?.accuracy;
    return `${h} ${rate == null ? "—" : `${Math.round(rate * 100)} %`}`;
  });
  const measured = HORIZON_ORDER.reduce((sum, h) => {
    const bucket = data.horizons[h];
    return sum + (bucket ? bucket.correct + bucket.incorrect : 0);
  }, 0);
  return `Aciertos (${days} d): ${parts.join(" · ")} · n=${measured}`;
}

export const MARKET_ANCHORS: Record<
  string,
  { lng: number; lat: number; label: string }
> = {
  NYSE: { lng: -74.0113, lat: 40.7069, label: "NYSE" },
  LSE: { lng: -0.0982, lat: 51.5155, label: "LSE" },
  TSE: { lng: 139.7745, lat: 35.6824, label: "TSE" },
  HKEX: { lng: 114.1577, lat: 22.2849, label: "HKEX" },
};

export function anchorForSignal(s: GeoSignal) {
  if (s.lng < -30) return MARKET_ANCHORS.NYSE;
  if (s.lng < 60) return MARKET_ANCHORS.LSE;
  if (s.lng < 110) return MARKET_ANCHORS.HKEX;
  return MARKET_ANCHORS.TSE;
}
