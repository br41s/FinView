import type { EventType, WorldEvent } from "./types";

/**
 * When an event happens, and so how the town acts it out.
 *
 * - `instant`: it happens at a moment (a price move, a signal). It is performed each time it
 *   is observed, once, and listed with how long ago it was.
 * - `all_day`: it belongs to a day, not a moment (a dividend paid on its pay date, results on
 *   their report day, a trade whose time FinView does not know). It is listed as «Todo el
 *   día» and performed for the whole of that day: the building celebrates, or worries, from
 *   midnight to midnight.
 */
export type EventTiming = "instant" | "all_day";

export const EVENT_TIMING: Record<EventType, EventTiming> = {
  price_move_up: "instant",
  price_move_down: "instant",
  technical_signal: "instant",
  options_alert: "instant",
  earnings_beat: "all_day",
  earnings_miss: "all_day",
  dividend_declared: "all_day",
  dividend_paid: "all_day",
  site_expansion: "all_day",
  position_added: "all_day",
  position_reduced: "all_day",
  position_closed: "all_day",
};

export const isAllDay = (e: Pick<WorldEvent, "eventType">): boolean => EVENT_TIMING[e.eventType] === "all_day";

/** The calendar day an event belongs to (YYYY-MM-DD, as dated by its source). */
export const eventDay = (e: Pick<WorldEvent, "occurredAt">): string => e.occurredAt.slice(0, 10);

/** Today in the viewer's own calendar, YYYY-MM-DD. */
export function localDay(nowMs: number): string {
  const d = new Date(nowMs);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

/** The all-day events whose day is today: what the town keeps performing right now. */
export function activeAllDay(events: readonly WorldEvent[], nowMs: number): WorldEvent[] {
  const today = localDay(nowMs);
  return events.filter((e) => e.assetId !== null && isAllDay(e) && eventDay(e) === today);
}

/** A key that only changes when the set of active all-day events does (to avoid scene churn). */
export const activeKey = (events: readonly WorldEvent[]): string =>
  events
    .map((e) => e.id)
    .sort()
    .join("|");

const MONTHS = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sept", "oct", "nov", "dic"];

/** «12 nov», or with the year when it is not the current one. */
export function shortDay(day: string, nowMs: number): string {
  const [y, m, d] = day.split("-").map(Number);
  const label = `${d} ${MONTHS[m - 1]}`;
  return y === new Date(nowMs).getFullYear() ? label : `${label} ${y}`;
}

/** How long ago an instant happened: «ahora», «hace 5 min», «hace 3 h», «hace 2 d». */
export function ago(iso: string, nowMs: number): string {
  const m = Math.max(0, Math.round((nowMs - Date.parse(iso)) / 60000));
  if (m < 1) return "ahora";
  if (m < 60) return `hace ${m} min`;
  const h = Math.round(m / 60);
  return h < 48 ? `hace ${h} h` : `hace ${Math.round(h / 24)} d`;
}

/**
 * When, in the feed. An all-day event has no time of day, so it is never «hace 10 h»: it is
 * «Todo el día · hoy», «… · ayer» or «… · 9 nov».
 */
export function whenLabel(e: Pick<WorldEvent, "eventType" | "occurredAt">, nowMs: number): string {
  if (!isAllDay(e)) return ago(e.occurredAt, nowMs);
  const day = eventDay(e);
  const today = localDay(nowMs);
  const yesterday = localDay(new Date(nowMs).setDate(new Date(nowMs).getDate() - 1));
  const rel = day === today ? "hoy" : day === yesterday ? "ayer" : shortDay(day, nowMs);
  return `Todo el día · ${rel}`;
}

/** How a building lives through its all-day events (acted out in `engine/choreography.ts`). */
export type DayMood = "party" | "work" | "concerned";

const MOOD: Partial<Record<EventType, DayMood>> = {
  dividend_paid: "party",
  dividend_declared: "party",
  earnings_beat: "party",
  site_expansion: "party",
  position_added: "work",
  position_reduced: "work",
  earnings_miss: "concerned",
  // position_closed: the building is in ruins, which says it already.
};

const RANK: Record<DayMood, number> = { work: 0, concerned: 1, party: 2 };

/**
 * One mood per building for today: the strongest of its all-day events. A dividend on the
 * day of a sale is a party; results that disappoint outrank routine trades.
 */
export function dayMoods(active: readonly WorldEvent[]): Map<string, DayMood> {
  const out = new Map<string, DayMood>();
  for (const e of active) {
    const mood = MOOD[e.eventType];
    if (!mood || e.assetId === null) continue;
    const have = out.get(e.assetId);
    if (!have || RANK[mood] > RANK[have]) out.set(e.assetId, mood);
  }
  return out;
}
