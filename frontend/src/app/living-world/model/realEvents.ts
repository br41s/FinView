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
] as const satisfies readonly EventType[];
type RealType = (typeof REAL_TYPES)[number];

const isRealType = (t: string): t is RealType => (REAL_TYPES as readonly string[]).includes(t);
const isRealConfidence = (c: string): c is Extract<Confidence, "verified" | "derived"> =>
  c === "verified" || c === "derived";

const DIRECTION: Record<RealType, Direction> = {
  price_move_up: "positive",
  price_move_down: "negative",
  position_added: "neutral",
  position_reduced: "neutral",
  position_closed: "neutral",
  dividend_paid: "positive",
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
  }
}

const SOURCE_WHY: Record<RealType, string> = {
  price_move_up: "Calculado a partir de dos cierres guardados; solo se muestran movimientos de al menos un 2 %.",
  price_move_down: "Calculado a partir de dos cierres guardados; solo se muestran movimientos de al menos un 2 %.",
  position_added: "Procede de tus operaciones importadas.",
  position_reduced: "Procede de tus operaciones importadas.",
  position_closed: "Procede de tus operaciones importadas.",
  dividend_paid: "Procede de tus operaciones importadas.",
};

export function toWorldEvent(raw: LivingWorldEvent, byIsin: ReadonlyMap<string, WorldAsset>): WorldEvent | null {
  if (!isRealType(raw.event_type) || !isRealConfidence(raw.confidence)) return null;
  const type = raw.event_type;
  // A closed position has no building any more: the event stays in the feed, unanchored.
  const asset = byIsin.get(raw.isin) ?? null;
  const breakdown = scoreEvent(type, raw.metrics, asset, raw.confidence);
  const severity = bucketFor(breakdown.score);
  const { title, summary } = copy(type, raw.name, raw.metrics);
  // Only a date is known (a session or a trade date): the start of that day, in UTC.
  const at = `${raw.occurred_on}T00:00:00.000Z`;
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
