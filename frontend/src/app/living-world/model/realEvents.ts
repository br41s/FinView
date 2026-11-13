import type { LivingWorldEvent } from "@/lib/types";
import { bucketFor, scoreEvent } from "./priority";
import {
  EVENT_TYPE_CATEGORY,
  type Confidence,
  type Direction,
  type EventType,
  type WorldAsset,
  type WorldEvent,
} from "./types";

/**
 * API facts → the town's events. The backend sends only what happened (a stored daily
 * move, a buy, a sell, a dividend) with exact figures; the wording and the priority live
 * here, scored by the same rule as every other event (`priority.ts`). Nothing is
 * advice: titles state what happened, never what to do about it.
 *
 * Fail-closed: a type or a confidence this build does not know is dropped, not guessed.
 */

const REAL_TYPES = [
  "price_move_up",
  "price_move_down",
  "position_added",
  "position_reduced",
  "position_closed",
  "dividend_paid",
  "week52_high",
  "week52_low",
  "volume_spike",
  "stock_split",
  "shares_received",
  "dividend_raised",
  "dividend_cut",
  "annual_report",
  "geo_alert",
  "technical_signal",
] as const satisfies readonly EventType[];
type RealType = (typeof REAL_TYPES)[number];

const isRealType = (t: string): t is RealType => (REAL_TYPES as readonly string[]).includes(t);
const isRealConfidence = (c: string): c is Extract<Confidence, "verified" | "reported" | "derived"> =>
  c === "verified" || c === "reported" || c === "derived";

const DIRECTION: Record<RealType, Direction> = {
  price_move_up: "positive",
  price_move_down: "negative",
  position_added: "neutral",
  position_reduced: "neutral",
  position_closed: "neutral",
  dividend_paid: "positive",
  week52_high: "positive",
  week52_low: "negative",
  volume_spike: "neutral",
  stock_split: "neutral",
  shares_received: "neutral",
  dividend_raised: "positive",
  dividend_cut: "negative",
  annual_report: "neutral",
  // A geo signal's thesis is a reading, not a move that happened: shown, never coloured as one.
  geo_alert: "neutral",
  technical_signal: "neutral",
};

const DURATION_MS = { normal: 12_000, important: 18_000, critical: 26_000 } as const;

const esNum = (n: number) => n.toFixed(2).replace(".", ",");

function copy(type: RealType, name: string, m: LivingWorldEvent["metrics"]): { title: string; summary: string } {
  switch (type) {
    case "price_move_up":
    case "price_move_down": {
      const c = typeof m.change_pct === "number" ? Math.abs(m.change_pct) : null;
      const verb = type === "price_move_up" ? "sube" : "baja";
      return {
        title: c === null ? `${name} ${verb}` : `${name} ${verb} un ${esNum(c)} %`,
        summary: "Cierre frente al de la sesión anterior, en la divisa en que cotiza.",
      };
    }
    case "dividend_paid":
      return { title: `Dividendo cobrado de ${name}`, summary: "Abono registrado en el libro de operaciones." };
    case "position_added":
      return { title: `Compra: ${name}`, summary: "Operación registrada en el libro de operaciones." };
    case "position_reduced":
      return { title: `Venta parcial: ${name}`, summary: "Operación registrada en el libro de operaciones." };
    case "position_closed":
      return { title: `Posición cerrada: ${name}`, summary: "Ya no queda nada de este valor en ningún bróker." };
    case "week52_high":
      return { title: `${name} cierra en máximos de 52 semanas`, summary: "Cierre por encima de todos los del último año, según el histórico de Zonas Clave." };
    case "week52_low":
      return { title: `${name} cierra en mínimos de 52 semanas`, summary: "Cierre por debajo de todos los del último año, según el histórico de Zonas Clave." };
    case "volume_spike": {
      const r = typeof m.volume_ratio === "number" ? `${esNum(m.volume_ratio)}×` : "muy por encima de";
      return { title: `Volumen inusual en ${name}: ${r} la media`, summary: "Acciones negociadas en la última sesión frente a la media de las 20 anteriores." };
    }
    case "stock_split": {
      const r = typeof m.ratio === "number" ? m.ratio : null;
      const label = r === null ? "" : r >= 1 ? ` ${trim(r)}:1` : ` 1:${trim(1 / r)}`;
      return {
        title: r !== null && r < 1 ? `Contrasplit de ${name}${label}` : `Split de ${name}${label}`,
        summary: "Cambia el número de acciones y su precio, no lo que vale tu posición.",
      };
    }
    case "shares_received":
      return { title: `Acciones recibidas: ${name}`, summary: "Llegaron sin una compra, por una operación corporativa (una escisión, por ejemplo)." };
    case "dividend_raised":
    case "dividend_cut": {
      const c = typeof m.change_pct === "number" ? ` (${m.change_pct > 0 ? "+" : "−"}${esNum(Math.abs(m.change_pct))} %)` : "";
      return {
        title: `${name} paga ${type === "dividend_raised" ? "más" : "menos"} dividendo por acción${c}`,
        summary: "Neto cobrado por acción frente al cobrado hace un año, en euros (incluye el efecto de la divisa).",
      };
    }
    case "annual_report": {
      const fy = typeof m.fiscal_year === "number" ? ` (ejercicio ${m.fiscal_year})` : "";
      return { title: `Nuevo informe anual de ${name}${fy}`, summary: "FinView ha leído su informe; la fecha es la de lectura, no la de publicación." };
    }
    case "geo_alert": {
      // The backend folds every signal about one holding on one day into one event.
      const n = typeof m.signal_count === "number" && m.signal_count > 1 ? m.signal_count : 1;
      // Never more lines than signals: the count is the backend's, the text is external.
      const all = typeof m.headlines === "string" ? m.headlines.split("\n").filter(Boolean).slice(0, n) : [];
      const one = typeof m.headline === "string" && m.headline ? m.headline : null;
      return {
        title: n > 1 ? `${n} alertas geopolíticas: ${name}` : `Alerta geopolítica: ${name}`,
        summary:
          n > 1 && all.length > 0
            ? all.join(" · ")
            : (one ?? "Una señal geopolítica enviada menciona este valor."),
      };
    }
    case "technical_signal": {
      const z = typeof m.zone === "string" && m.zone ? ` (${m.zone})` : "";
      return { title: `${name} llega a una zona clave${z}`, summary: "Alerta de Zonas Clave enviada para este valor." };
    }
  }
}

/** 4 → «4», 1.5 → «1,5». */
const trim = (n: number) => String(Math.round(n * 100) / 100).replace(".", ",");

const SOURCE_WHY: Record<RealType, string> = {
  price_move_up: "Calculado a partir de dos cierres guardados; solo se muestran movimientos de al menos un 2 %.",
  price_move_down: "Calculado a partir de dos cierres guardados; solo se muestran movimientos de al menos un 2 %.",
  position_added: "Procede de tus operaciones importadas.",
  position_reduced: "Procede de tus operaciones importadas.",
  position_closed: "Procede de tus operaciones importadas.",
  dividend_paid: "Procede de tus operaciones importadas.",
  week52_high: "Calculado con los cierres que guarda Zonas Clave; solo para valores de tu lista de Zonas Clave.",
  week52_low: "Calculado con los cierres que guarda Zonas Clave; solo para valores de tu lista de Zonas Clave.",
  volume_spike: "Calculado con el volumen que guarda Zonas Clave; se muestra a partir de 2,5 veces la media.",
  stock_split: "Dato de Yahoo Finance que FinView guarda para vigilar splits.",
  shares_received: "Procede de tus operaciones importadas: primera vez que este valor aparece, sin compra.",
  dividend_raised: "Calculado con tus dividendos importados; solo cambios de al menos un 15 %.",
  dividend_cut: "Calculado con tus dividendos importados; solo cambios de al menos un 15 %.",
  annual_report: "Procede del lector de informes anuales de FinView.",
  geo_alert: "Señal geopolítica de FinView que ya se envió y nombra este valor.",
  technical_signal: "Alerta de Zonas Clave que ya se te envió.",
};

export function toWorldEvent(raw: LivingWorldEvent, byIsin: ReadonlyMap<string, WorldAsset>): WorldEvent | null {
  if (!isRealType(raw.event_type) || !isRealConfidence(raw.confidence)) return null;
  const type = raw.event_type;
  // A closed position has no building any more: the event stays in the feed, unanchored.
  const asset = byIsin.get(raw.isin) ?? null;
  const breakdown = scoreEvent(type, raw.metrics, asset, raw.confidence);
  const severity = bucketFor(breakdown.score);
  const { title, summary } = copy(type, raw.name, raw.metrics);
  // The real moment when the source has it (a geo or Zonas Clave alert); otherwise only a date
  // is known (a session or a trade date): the start of that day, in UTC.
  const at = raw.occurred_at && !Number.isNaN(Date.parse(raw.occurred_at))
    ? new Date(raw.occurred_at).toISOString()
    : `${raw.occurred_on}T00:00:00.000Z`;
  return {
    id: `real:${raw.id}`,
    assetId: asset ? asset.id : null,
    ticker: asset?.ticker ?? null,
    eventType: type,
    category: EVENT_TYPE_CATEGORY[type],
    severity,
    direction: DIRECTION[type],
    title,
    summary,
    occurredAt: at,
    observedAt: at,
    sourceType: raw.source_type,
    sourceRef: raw.id,
    sourceUrl: null,
    metrics: raw.metrics,
    confidence: raw.confidence,
    dedupeKey: `real:${raw.id}`,
    displayDurationMs: DURATION_MS[severity],
    priorityScore: breakdown.score,
    why:
      `Puntuación ${esNum(breakdown.score)} = base ${breakdown.base} × magnitud ${esNum(breakdown.magnitude)} ` +
      `× relevancia ${esNum(breakdown.relevance)} × confianza ${breakdown.confidence}. ${SOURCE_WHY[type]}`,
  };
}

/** Newest first, as the feed lists them. */
export function toWorldEvents(raw: readonly LivingWorldEvent[], assets: readonly WorldAsset[]): WorldEvent[] {
  const byIsin = new Map(assets.map((a) => [a.isin, a]));
  return raw
    .map((r) => toWorldEvent(r, byIsin))
    .filter((e): e is WorldEvent => e !== null)
    .sort((a, b) => Date.parse(b.occurredAt) - Date.parse(a.occurredAt));
}
