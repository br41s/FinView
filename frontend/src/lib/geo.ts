// Geo-Intel shared types + market anchor geometry.
// (Lives in lib/ because src/data/ is gitignored; the original Lovable mock file
// stays there for local reference only — production imports come from here.)

/** What a Spanish retail account can actually do with the instrument.
 *  `cash_eu` = buyable as cash anywhere; `options_only` = US ETF without a KID,
 *  so only reachable through IBKR options; `not_tradable` = no retail route. */
export type GeoTradability = "cash_eu" | "options_only" | "not_tradable";

/** How wide an instrument is: a company tied to one country, one country's
 *  market, or something no single country owns. A property of the instrument,
 *  not of the event — a Taiwan signal can carry China's market as "national". */
export type GeoTier = "local" | "national" | "international";

export type GeoSignalTicker = {
  symbol: string;
  direction: "bullish" | "bearish" | "neutral";
  priceAtSignal: number | null;
  /** Optional on the wire: signals persisted before the scoping work carry no
   *  tradability, and an unknown instrument is assumed buyable rather than
   *  painted as dead. */
  tradability?: GeoTradability;
  /** Nearest EU-listed equivalent, e.g. "SGLN / 4GLD (physical gold ETC)". */
  alternate?: string | null;
  /** Optional on the wire: an API older than the country layer sends none. */
  tier?: GeoTier;
  /** The leg read against its own noise; null until an audit has read it. */
  state?: GeoLegState | null;
  /** % move since the signal, at the last audit. */
  liveChangePct?: number | null;
};

export type GeoLegState = "confirms" | "contradicts" | "flat";

/** One tier of a basket, read as a whole. `pending` = no leg read yet;
 *  `unreadable` = read, and decided nothing (no measurable move, or a tie). */
export type GeoTierState = "pending" | "confirmed" | "contradicted" | "unreadable";

export type GeoTierStep = {
  tier: GeoTier;
  state: GeoTierState;
  legs: number;
  confirms: number;
  contradicts: number;
};

/** How wide the event that fired the rule is. Optional on the wire. */
export type GeoRuleScope = "site" | "local" | "regional" | "global";

export type GeoRule = {
  id: string;
  description: string; // what happened
  thesis: string; // why it moves markets
  confidence: number; // 0-1
  category?: string; // event bucket, e.g. "earthquake"
  trigger?: string; // the condition that fired, e.g. "mag>=6.5 near chile_mining"
  scope?: GeoRuleScope; // how wide the event is; absent on rows written before scoping
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
  country?: string | null; // the country the source reported, when it named one
  importance: number; // 0-100
  confidence: number; // 0-1
  riskScore: number; // 0-10
  direction: "bullish" | "bearish" | "neutral";
  tickers: GeoSignalTicker[];
  /** The basket read tier by tier, narrowest first; absent on an older API. */
  ladder?: GeoTierStep[];
  rules: GeoRule[];
  checkpoints: GeoCheckpoint[];
  timestamp: string;
  notifiedAt?: string | null; // when a channel actually delivered it; null = never
  status: "active" | "resolved";
  // Live rating from the last audit run (every 4 h): the basket scored against
  // the latest price. Only while active; the checkpoints stay the record.
  liveScore?: number | null; // 0-100
  liveOutcome?: "CORRECT" | "INCORRECT" | "NEUTRAL" | null;
  liveRatedAt?: string | null;
  source?: string; // ingest feed key (usgs|EONET|gdelt|…)
  sourceUrl?: string | null; // link to the underlying source event, when captured
  generated?: boolean; // thesis proposed by the LLM for an event no rule covers
  narrative?: string | null; // the LLM's reasoning, when generated
  thesis?: string | null; // effect → flow → instrument, when generated
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

export type GeoTierAccuracy = {
  confirmed: number;
  contradicted: number;
  unreadable: number;
  /** confirmed / (confirmed + contradicted); null = nothing decisive yet. */
  accuracy: number | null;
};

/** Whether a confirmed narrow tier came with a confirmed wider one: `rate`
 *  against `baseline`, over `n` signals. A measurement — nothing acts on it. */
export type GeoLadderStep = {
  narrow: GeoTier;
  wide: GeoTier;
  n: number;
  confirmed: number;
  rate: number | null;
  baseline: number | null;
};

export type GeoAccuracy = {
  since: string;
  horizons: Partial<Record<GeoCheckpointHorizon, GeoHorizonAccuracy>>;
  rules: GeoRuleAccuracy[];
  tiers?: Partial<Record<GeoTier, GeoTierAccuracy>>;
  ladder?: GeoLadderStep[];
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

// ── Tradability, scope and thesis chain (the Phase 2 scoping read) ──
// 24 US-domiciled ETFs carried 61 % of all rule→ticker edges and rendered
// exactly like XOM, so the desk read "buy GLD" off a chip that a Spanish
// retail account cannot buy as cash. These are the pure bits of that fix.

export type TradabilityHint = {
  /** Short marker for the chip; null when there is nothing to say. */
  badge: string | null;
  /** Full explanation for the chip's tooltip; null when tradable as cash. */
  tooltip: string | null;
  /** Paint the chip as unreachable (dimmed, dashed). */
  muted: boolean;
};

const NO_HINT: TradabilityHint = { badge: null, tooltip: null, muted: false };

/**
 * What to draw on a ticker chip for a Spanish retail account.
 *
 * `options_only` is **not dimmed** — the instrument exists and is quoted, it
 * just cannot be bought in cash by an EU retail account (no KID). Only
 * `not_tradable` is dimmed. The text describes availability; it never says
 * where or how to trade, because FinView shows data and does not advise. An absent `tradability` (older signal rows) reads
 * as cash: assuming "unknown = dead" would grey out most of the feed.
 */
export function tradabilityHint(
  t: Pick<GeoSignalTicker, "tradability" | "alternate">,
): TradabilityHint {
  const alt = t.alternate?.trim()
    ? `equivalente UCITS/UE: ${t.alternate.trim()}`
    : "sin equivalente UCITS/UE";
  switch (t.tradability) {
    case "options_only":
      return {
        badge: "opc.",
        tooltip: `ETF de EE. UU. sin KID: no disponible al contado para minoristas en la UE — ${alt}`,
        muted: false,
      };
    case "not_tradable":
      // The more severe state needs a legible marker: `title=` does not exist on touch.
      return { badge: "s/ruta", tooltip: `No disponible para minoristas en la UE — ${alt}`, muted: true };
    default:
      return NO_HINT;
  }
}

const SCOPE_LABELS: Record<GeoRuleScope, string> = {
  site: "sitio",
  local: "local",
  regional: "regional",
  global: "global",
};

/** Header badge for the FRED regime. Mirrors the options AnalysisTab badge;
 *  here it is not annotation-only — a risk-off regime adds one point of risk
 *  to *new* conflict / chokepoint / sanctions events (a tracked signal keeps
 *  the risk it was born with), and the tooltip says so. */
export function macroRegimeBadge(
  macro?: { regime: string; vix: number | null; as_of: string | null } | null,
): { label: string; tone: "warn" | "ok" | "muted"; title: string } | null {
  if (!macro?.regime) return null;
  const vix = macro.vix == null ? "n/d" : macro.vix.toFixed(1);
  const asOf = macro.as_of ? ` · FRED ${macro.as_of}` : "";
  if (macro.regime === "risk_off") {
    return {
      label: "Régimen: risk-off",
      tone: "warn",
      title: `VIX ${vix}${asOf}. Los nuevos eventos geopolíticos suman +1 de riesgo en este régimen.`,
    };
  }
  if (macro.regime === "risk_on") {
    return { label: "Régimen: risk-on", tone: "ok", title: `VIX ${vix}${asOf}.` };
  }
  return { label: "Régimen: neutral", tone: "muted", title: `VIX ${vix}${asOf}.` };
}

const TIERS: { tier: GeoTier; label: string; title: string }[] = [
  { tier: "local", label: "Local", title: "Empresas ligadas a un solo país." },
  { tier: "national", label: "Nacional", title: "El mercado de un país, a través de su ETF." },
  {
    tier: "international",
    label: "Internacional",
    title: "Materias primas, sectores y activos que no dependen de un solo país.",
  },
];

export type TickerTierGroup = {
  tier: GeoTier | null;
  label: string | null;
  title: string | null;
  tickers: GeoSignalTicker[];
  /** How the tier reads as a whole; null when the API sent no ladder. */
  step: GeoTierStep | null;
};

/**
 * The basket split by how wide each instrument is, narrowest first.
 * A tier with no instrument is left out. When no ticker carries a tier — an API
 * older than the country layer — the basket comes back as one unlabelled group,
 * so the panel renders exactly as it did rather than filing everything under
 * "Internacional".
 */
export function groupByTier(
  tickers: GeoSignalTicker[],
  ladder: GeoTierStep[] = [],
): TickerTierGroup[] {
  if (!tickers.some((t) => t.tier)) {
    return tickers.length
      ? [{ tier: null, label: null, title: null, tickers, step: null }]
      : [];
  }
  return TIERS.map(({ tier, label, title }) => ({
    tier,
    label,
    title,
    tickers: tickers.filter((t) => (t.tier ?? "international") === tier),
    step: ladder.find((s) => s.tier === tier) ?? null,
  })).filter((group) => group.tickers.length > 0);
}

export type TierStateBadge = {
  text: string;
  tone: "ok" | "bad" | "warn" | "muted";
  title: string;
};

/**
 * How a tier reads, in the words the live rating already uses ("a favor").
 * It reports where prices went against the written thesis and nothing more:
 * a confirmed tier is not a reason to act, and the copy must not read as one.
 */
export function tierStateBadge(step?: GeoTierStep | null): TierStateBadge | null {
  if (!step) return null;
  const of = (n: number) => `${n} de ${step.legs}`;
  switch (step.state) {
    case "confirmed":
      return {
        text: "a favor",
        tone: "ok",
        title: `${of(step.confirms)} se movieron como describe la tesis.`,
      };
    case "contradicted":
      return {
        text: "en contra",
        tone: "bad",
        title: `${of(step.contradicts)} se movieron en contra de la tesis.`,
      };
    case "unreadable":
      return {
        text: "sin lectura",
        tone: "warn",
        title: "Sin movimiento medible, o lecturas repartidas a partes iguales.",
      };
    case "pending":
      return { text: "pendiente", tone: "muted", title: "Aún sin lectura de precios." };
    default:
      return null;
  }
}

/** Spanish tag for a rule's scope; null when the row predates scoping. */
export function scopeLabel(scope?: string): string | null {
  return SCOPE_LABELS[scope as GeoRuleScope] ?? null;
}

/**
 * A written thesis is a chain — physical effect → price/flow → instrument —
 * joined with " → " on the wire. Split so the panel can space the links out
 * instead of running them together; an unchained thesis comes back as a single
 * segment and renders exactly as it did before.
 */
export function thesisSegments(thesis: string): string[] {
  return thesis
    .split("→")
    .map((part) => part.trim())
    .filter(Boolean);
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
