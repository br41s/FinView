// Geo-Intel shared types + market anchor geometry.
// (Lives in lib/ because src/data/ is gitignored; the original Lovable mock file
// stays there for local reference only — production imports come from here.)

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
  tickers: string[];
  timestamp: string;
  status: "active" | "resolved";
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
