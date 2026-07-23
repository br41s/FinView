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
  status: "active" | "resolved";
  source?: string; // ingest feed key (usgs|EONET|gdelt|…)
  sourceUrl?: string | null; // link to the underlying source event, when captured
};

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
