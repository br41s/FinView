import { classifyArchetype } from "./archetypes";
import { bucketFor, scoreEvent } from "./priority";
import { hashString, seeded } from "./rng";
import {
  EVENT_TYPE_CATEGORY,
  type Archetype,
  type AssetType,
  type Confidence,
  type Direction,
  type EventType,
  type WorldAsset,
  type WorldEvent,
} from "./types";

/**
 * Phase 0 data: ~100 FICTIONAL holdings and demo events. Nothing here is real, nothing
 * is written anywhere, and the UI says so permanently. Names are invented on purpose so
 * a screenshot can never be mistaken for somebody's actual portfolio.
 */

const COUNTS: Record<Archetype, number> = {
  retail: 10,
  tech: 12,
  semis: 5,
  energy: 7,
  mining: 7,
  banking: 10,
  health: 10,
  consumer: 11,
  telecom: 4,
  utilities: 6,
  realestate: 4,
  fund: 9,
  cash: 2,
  crypto: 3,
};

interface Profile {
  assetType: AssetType;
  sector: string | null;
  industry: string | null;
  suffixes: string[];
}

const PROFILE: Record<Archetype, Profile> = {
  retail: { assetType: "equity", sector: "Consumer Cyclical", industry: "Apparel Retail", suffixes: ["Moda", "Textil", "Stores", "Boutiques"] },
  tech: { assetType: "equity", sector: "Technology", industry: "Software - Infrastructure", suffixes: ["Systems", "Software", "Cloud", "Labs"] },
  semis: { assetType: "equity", sector: "Technology", industry: "Semiconductors", suffixes: ["Silicon", "Chips", "Foundry"] },
  energy: { assetType: "equity", sector: "Energy", industry: "Oil & Gas Integrated", suffixes: ["Petróleo", "Energía", "Oil"] },
  mining: { assetType: "equity", sector: "Basic Materials", industry: "Copper", suffixes: ["Minera", "Metales", "Resources"] },
  banking: { assetType: "equity", sector: "Financial Services", industry: "Banks - Diversified", suffixes: ["Banco", "Capital", "Financial"] },
  health: { assetType: "equity", sector: "Healthcare", industry: "Drug Manufacturers - General", suffixes: ["Pharma", "Biotech", "Health"] },
  consumer: { assetType: "equity", sector: "Consumer Defensive", industry: "Beverages - Non-Alcoholic", suffixes: ["Foods", "Bebidas", "Alimentación"] },
  telecom: { assetType: "equity", sector: "Communication Services", industry: "Telecom Services", suffixes: ["Telecom", "Móvil", "Network"] },
  utilities: { assetType: "equity", sector: "Utilities", industry: "Utilities - Renewable", suffixes: ["Eólica", "Renovables", "Power"] },
  realestate: { assetType: "equity", sector: "Real Estate", industry: "REIT - Diversified", suffixes: ["Inmuebles", "Properties", "Socimi"] },
  fund: { assetType: "etf", sector: null, industry: null, suffixes: ["Global ETF", "Index Fund", "Sector ETF"] },
  cash: { assetType: "cash", sector: null, industry: null, suffixes: ["Efectivo", "Depósito"] },
  crypto: { assetType: "crypto", sector: null, industry: null, suffixes: ["Coin", "Token"] },
};

const PREFIXES = [
  "Aurelia", "Nortek", "Valdor", "Brisa", "Kestrel", "Montalvo", "Ortega", "Lumen", "Cobalto", "Zafiro",
  "Altamira", "Tramonto", "Ibérica", "Helios", "Quasar", "Mirador", "Solera", "Vertex", "Ónix", "Nácar",
  "Fénix", "Atlas", "Boreal", "Cierzo", "Duero", "Estrella", "Faro", "Garnacha", "Horizonte", "Isla",
  "Jara", "Kálamo", "Laurel", "Meseta", "Nube", "Ocaso", "Pinar", "Ribera", "Sierra", "Tilo",
];
const COUNTRIES = ["España", "Estados Unidos", "Alemania", "Francia", "Países Bajos", "Reino Unido", "Japón", "Suiza", "Italia", "Dinamarca"];
const BROKERS = ["TR", "DEGIRO", "IBKR", "ING", "BBVA", "eToro"];

const TOTAL_VALUE_EUR = 250_000;

export function demoAssets(seed = 7): WorldAsset[] {
  const rng = seeded(seed);
  const pick = <T>(xs: readonly T[]): T => xs[Math.floor(rng() * xs.length)];

  const plan: Archetype[] = [];
  (Object.keys(COUNTS) as Archetype[]).forEach((a) => {
    for (let i = 0; i < COUNTS[a]; i++) plan.push(a);
  });

  // Zipf-like weights, shuffled so size is not correlated with archetype order.
  const raw = plan.map((_, i) => 1 / Math.pow(i + 1, 0.9));
  for (let i = raw.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [raw[i], raw[j]] = [raw[j], raw[i]];
  }
  // Three holdings with no valuation: the world must show them as unknown, not tiny.
  const unknown = new Set([plan.length - 3, 11, 42].map((i) => i % plan.length));
  const knownSum = raw.reduce((s, w, i) => (unknown.has(i) ? s : s + w), 0);

  const names = new Set<string>();
  return plan.map((archetype, i) => {
    const p = PROFILE[archetype];
    let name = "";
    do {
      name = `${pick(PREFIXES)} ${pick(p.suffixes)}`;
      if (names.has(name)) name = `${name} ${i}`;
    } while (names.has(name));
    names.add(name);

    const isUnknown = unknown.has(i);
    const weightPct = isUnknown ? null : (raw[i] / knownSum) * 100;
    const marketValueEur = weightPct === null ? null : (weightPct / 100) * TOTAL_VALUE_EUR;
    const plRatio = rng() * 0.8 - 0.2;
    const costKnown = marketValueEur !== null && rng() > 0.06;
    const dayChange = (rng() + rng() + rng() - 1.5) * 4;
    const nBrokers = p.assetType === "equity" && rng() > 0.78 ? 2 : 1;
    const brokers = [...new Set(Array.from({ length: nBrokers }, () => pick(BROKERS)))];

    const asset: WorldAsset = {
      id: `ZZ${String(1_000_000_000 + i * 7919)}`,
      isin: `ZZ${String(1_000_000_000 + i * 7919)}`,
      ticker: p.assetType === "cash" ? null : name.replace(/[^A-Za-z]/g, "").slice(0, 4).toUpperCase(),
      name,
      country: p.assetType === "cash" || p.assetType === "crypto" ? null : pick(COUNTRIES),
      assetType: p.assetType,
      sector: p.sector,
      industry: p.industry,
      archetype: "consumer", // replaced below by the real classifier
      brokers,
      marketValueEur,
      weightPct,
      dayChangePct: marketValueEur === null || rng() < 0.03 ? null : dayChange,
      totalCostEur: costKnown ? marketValueEur! / (1 + plRatio) : null,
      unrealizedPlEur: costKnown ? marketValueEur! - marketValueEur! / (1 + plRatio) : null,
      favourite: rng() < 0.08,
    };
    asset.archetype = classifyArchetype(asset);
    return asset;
  });
}

// --- demo events ------------------------------------------------------------------

const pct = (x: number) => `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(1).replace(".", ",")} %`;

const OPERATING: EventType[] = [
  "price_move_up", "price_move_down", "price_move_up", "price_move_down", "earnings_beat", "earnings_miss",
  "dividend_declared", "dividend_paid", "site_expansion", "technical_signal", "options_alert",
  "position_added", "position_reduced",
];
const FUND_TYPES: EventType[] = ["price_move_up", "price_move_down", "dividend_paid", "technical_signal", "position_added"];
const CRYPTO_TYPES: EventType[] = ["price_move_up", "price_move_down", "technical_signal"];

function typesFor(a: WorldAsset): EventType[] | null {
  if (a.assetType === "cash") return null;
  if (a.assetType === "crypto") return CRYPTO_TYPES;
  if (a.assetType === "etf" || a.assetType === "fund" || a.assetType === "bond") return FUND_TYPES;
  return OPERATING;
}

const DIRECTION: Record<EventType, Direction | "by-sign"> = {
  price_move_up: "positive",
  price_move_down: "negative",
  earnings_beat: "positive",
  earnings_miss: "negative",
  dividend_declared: "positive",
  dividend_paid: "positive",
  site_expansion: "positive",
  technical_signal: "neutral",
  options_alert: "neutral",
  position_added: "neutral",
  position_reduced: "neutral",
  position_closed: "neutral",
};

interface Draft {
  title: string;
  summary: string;
  metrics: WorldEvent["metrics"];
  sourceType: string;
}

function draft(type: EventType, a: WorldAsset, r: () => number): Draft {
  switch (type) {
    case "price_move_up":
    case "price_move_down": {
      const mag = 2 + r() * 7;
      const change = type === "price_move_up" ? mag : -mag;
      return {
        title: `${a.name} ${change > 0 ? "sube" : "baja"} ${pct(Math.abs(change)).replace("+", "")}`,
        summary: "Variación diaria según la última cotización disponible.",
        metrics: { change_pct: Number(change.toFixed(2)), price: Number((10 + r() * 90).toFixed(2)), currency: "EUR", period: "1d" },
        sourceType: "price_cache",
      };
    }
    case "earnings_beat":
    case "earnings_miss": {
      const s = (type === "earnings_beat" ? 1 : -1) * (2 + r() * 12);
      const estimate = 0.4 + r() * 2;
      return {
        title: `${a.name} ${s > 0 ? "supera" : "no alcanza"} las previsiones del trimestre`,
        summary: "Resultado publicado frente al consenso de analistas.",
        metrics: { actual: Number((estimate * (1 + s / 100)).toFixed(2)), estimate: Number(estimate.toFixed(2)), surprise_pct: Number(s.toFixed(1)), unit: "EUR/acción", period: "T3 2026" },
        sourceType: "demo_filing",
      };
    }
    case "dividend_declared": {
      const dps = 0.1 + r() * 0.9;
      return {
        title: `${a.name} anuncia dividendo de ${dps.toFixed(2).replace(".", ",")} €`,
        summary: "Dividendo declarado; aún no cobrado.",
        metrics: { dps: Number(dps.toFixed(2)), currency: "EUR", ex_date: "2026-11-20", pay_date: "2026-12-05" },
        sourceType: "demo_filing",
      };
    }
    case "dividend_paid": {
      const gross = 20 + r() * 180;
      return {
        title: `Dividendo cobrado de ${a.name}`,
        summary: "Abono registrado en el libro de operaciones.",
        metrics: { gross_eur: Number(gross.toFixed(2)), withholding_eur: Number((gross * 0.19).toFixed(2)), net_eur: Number((gross * 0.81).toFixed(2)) },
        sourceType: "ledger",
      };
    }
    case "site_expansion":
      return {
        title: `${a.name} abre un nuevo centro`,
        summary: "Hecho corporativo de ejemplo: ampliación de capacidad.",
        metrics: { site: "centro regional", region: "Iberia" },
        sourceType: "demo_filing",
      };
    case "technical_signal":
      return {
        title: `Señal técnica en ${a.ticker ?? a.name}`,
        summary: "Cercanía a una zona de soporte, tomada de Zonas Clave sin recalcular.",
        metrics: { zone: "soporte", distance_pct: Number((0.3 + r() * 2).toFixed(1)), score: Math.round(55 + r() * 40) },
        sourceType: "zonas_clave",
      };
    case "options_alert":
      return {
        title: `Actividad inusual en opciones de ${a.ticker ?? a.name}`,
        summary: "Contexto de derivados, no actividad operativa de la empresa.",
        metrics: { alert: "prima inusual", strike: Number((10 + r() * 90).toFixed(0)), volume_ratio: Number((2 + r() * 4).toFixed(1)) },
        sourceType: "options_monitor",
      };
    case "position_added":
    case "position_reduced":
    case "position_closed": {
      const verb = type === "position_added" ? "Compra" : type === "position_reduced" ? "Venta parcial" : "Posición cerrada";
      return {
        title: `${verb}: ${a.name}`,
        summary: "Movimiento registrado en el libro de operaciones.",
        metrics: { quantity: Math.round(5 + r() * 95), value_eur: Number((200 + r() * 3000).toFixed(0)), account: pickBroker(a, r) },
        sourceType: "ledger",
      };
    }
  }
}

function pickBroker(a: WorldAsset, r: () => number): string {
  return a.brokers[Math.floor(r() * a.brokers.length)] ?? "—";
}

export interface DemoEventOptions {
  nowMs: number;
  seed: number;
  count: number;
  /** Events are spread over [now − span, now], biased to the recent end. 0 = all "now". */
  spanMs: number;
  idPrefix?: string;
}

/** Deterministic: same inputs → same events, ids and dedupe keys. */
export function generateDemoEvents(assets: readonly WorldAsset[], o: DemoEventOptions): WorldEvent[] {
  const r = seeded(o.seed);
  const eligible = assets.filter((a) => typesFor(a) !== null);
  // Big positions make news more often in a real portfolio's feed; a third of the demo
  // events go to the ten largest so Important and Critical severities actually occur.
  const top = [...eligible].sort((x, y) => (y.weightPct ?? -1) - (x.weightPct ?? -1)).slice(0, 10);
  const prefix = o.idPrefix ?? "demo";
  const out: WorldEvent[] = [];
  for (let i = 0; i < o.count; i++) {
    const pool = r() < 0.35 ? top : eligible;
    const a = pool[Math.floor(r() * pool.length)];
    const types = typesFor(a)!;
    const type = types[Math.floor(r() * types.length)];
    const d = draft(type, a, r);
    const age = o.spanMs * r() * r();
    const occurredMs = Math.round(o.nowMs - age);
    const confidence: Confidence = "demo";
    const breakdown = scoreEvent(type, d.metrics, a, confidence);
    const severity = bucketFor(breakdown.score);
    const dir = DIRECTION[type];
    const id = `${prefix}-${o.seed}-${i}`;
    out.push({
      id,
      assetId: a.id,
      ticker: a.ticker,
      eventType: type,
      category: EVENT_TYPE_CATEGORY[type],
      severity,
      direction: dir === "by-sign" ? "neutral" : dir,
      title: d.title,
      summary: d.summary,
      occurredAt: new Date(occurredMs).toISOString(),
      observedAt: new Date(occurredMs + 60_000).toISOString(),
      sourceType: d.sourceType,
      sourceRef: `demo:${hashString(id).toString(16)}`,
      sourceUrl: null,
      metrics: d.metrics,
      confidence,
      dedupeKey: `${prefix}:${a.id}:${type}:${id}`,
      displayDurationMs: severity === "critical" ? 26_000 : severity === "important" ? 18_000 : 12_000,
      priorityScore: breakdown.score,
      why:
        `Puntuación ${breakdown.score.toFixed(2).replace(".", ",")} = base ${breakdown.base} × magnitud ` +
        `${breakdown.magnitude.toFixed(2).replace(".", ",")} × relevancia ${breakdown.relevance.toFixed(2).replace(".", ",")} ` +
        `× confianza ${breakdown.confidence}. Evento de demostración: no procede de ninguna fuente real.`,
    });
  }
  return out.sort((x, y) => Date.parse(y.occurredAt) - Date.parse(x.occurredAt));
}
