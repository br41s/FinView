/**
 * Living World: shared vocabulary.
 *
 * Everything under `model/` is pure TypeScript (no DOM, no Three.js) so vitest can
 * pin it in the node environment. The renderer in `engine/` only draws what these
 * types describe, the same split as `src/game/garden/` (`sim.ts` vs `scene.ts`).
 *
 * Nullability is meaningful: `null` means "FinView does not know", never zero.
 */

export const ARCHETYPES = [
  "retail",
  "tech",
  "semis",
  "energy",
  "mining",
  "banking",
  "health",
  "consumer",
  "telecom",
  "utilities",
  "realestate",
  "fund",
  "cash",
  "crypto",
] as const;
export type Archetype = (typeof ARCHETYPES)[number];

export const DISTRICT_IDS = [
  "retail",
  "tech",
  "industry",
  "finance",
  "health",
  "funds",
  "treasury",
] as const;
export type DistrictId = (typeof DISTRICT_IDS)[number];

export type AssetType = "equity" | "etf" | "fund" | "bond" | "cash" | "crypto" | "alternative";

/** One canonical instrument. Brokers are folded into `brokers`, never duplicated. */
export interface WorldAsset {
  /** Stable key: the ISIN where one exists. */
  id: string;
  isin: string;
  ticker: string | null;
  name: string;
  country: string | null;
  assetType: AssetType;
  /** Free-text sector as the data source reports it; null when unknown. */
  sector: string | null;
  industry: string | null;
  archetype: Archetype;
  /** False when neither a stored listing, an annual report nor a curated override told us what it is. */
  classified: boolean;
  brokers: string[];
  marketValueEur: number | null;
  weightPct: number | null;
  dayChangePct: number | null;
  totalCostEur: number | null;
  unrealizedPlEur: number | null;
  favourite: boolean;
  /** Sold out of: the building stands in ruins and keeps what the ledger says. Null while held. */
  closed: ClosedHolding | null;
}

/** What a closed position leaves behind, from the ledger, in euros as booked. */
export interface ClosedHolding {
  /** ISO date of the last sale. */
  on: string;
  investedEur: number | null;
  soldEur: number | null;
  dividendsEur: number | null;
}

export type EventCategory = "market" | "corporate" | "portfolio" | "technical" | "options";
export type Severity = "normal" | "important" | "critical";
export type Direction = "positive" | "negative" | "neutral";
export type Confidence = "verified" | "reported" | "derived" | "demo";

export type EventType =
  | "price_move_up"
  | "price_move_down"
  | "earnings_beat"
  | "earnings_miss"
  | "dividend_declared"
  | "dividend_paid"
  | "site_expansion"
  | "technical_signal"
  | "options_alert"
  | "position_added"
  | "position_reduced"
  | "position_closed"
  | "week52_high"
  | "week52_low"
  | "volume_spike"
  | "stock_split"
  | "shares_received"
  | "dividend_raised"
  | "dividend_cut"
  | "annual_report"
  | "geo_alert";

export const EVENT_TYPE_CATEGORY: Record<EventType, EventCategory> = {
  price_move_up: "market",
  price_move_down: "market",
  earnings_beat: "corporate",
  earnings_miss: "corporate",
  dividend_declared: "corporate",
  dividend_paid: "portfolio",
  site_expansion: "corporate",
  technical_signal: "technical",
  options_alert: "options",
  position_added: "portfolio",
  position_reduced: "portfolio",
  position_closed: "portfolio",
  week52_high: "market",
  week52_low: "market",
  volume_spike: "market",
  stock_split: "corporate",
  shares_received: "portfolio",
  dividend_raised: "corporate",
  dividend_cut: "corporate",
  annual_report: "corporate",
  geo_alert: "market",
};

/** Normalised event, spec §5.3. `occurredAt` and `observedAt` are ISO-8601 UTC. */
export interface WorldEvent {
  id: string;
  assetId: string | null;
  ticker: string | null;
  eventType: EventType;
  category: EventCategory;
  severity: Severity;
  direction: Direction;
  title: string;
  summary: string;
  occurredAt: string;
  observedAt: string;
  sourceType: string;
  sourceRef: string | null;
  sourceUrl: string | null;
  /** Exact figures, never only prose. Unknown values stay null. */
  metrics: Record<string, number | string | null>;
  confidence: Confidence;
  dedupeKey: string;
  displayDurationMs: number;
  /** Raw priority score and the rule that bucketed it, so a severity is explainable. */
  priorityScore: number;
  /** Deterministic trigger, shown under "¿Por qué ha ocurrido?". */
  why: string;
}

export type TimeWindow = "live" | "24h" | "7d" | "30d";

export interface WorldFilters {
  query: string;
  /** Minimum portfolio weight in %. null = all holdings. */
  minWeightPct: number | null;
  assetTypes: AssetType[];
  archetypes: Archetype[];
  countries: string[];
  brokers: string[];
  directions: Direction[];
  categories: EventCategory[];
  severities: Severity[];
  window: TimeWindow;
  favouritesOnly: boolean;
  /** Only buildings with at least one event inside the window. */
  activeOnly: boolean;
  /** Hide non-matching buildings instead of muting them. */
  isolate: boolean;
}

export const EMPTY_FILTERS: WorldFilters = {
  query: "",
  minWeightPct: null,
  assetTypes: [],
  archetypes: [],
  countries: [],
  brokers: [],
  directions: [],
  categories: [],
  severities: [],
  // The widest window: real events are imported weeks after they happen, and a town that
  // opens on 24 h looked dead even with a month of activity behind it.
  window: "30d",
  favouritesOnly: false,
  activeOnly: false,
  isolate: false,
};

export type Visibility = "match" | "muted" | "hidden";
