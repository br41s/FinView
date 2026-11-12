import type { Visibility, WorldAsset, WorldEvent, WorldFilters } from "./types";

/**
 * Composable filters (spec §7.2). Filters narrow attention, they do not delete the
 * town: a non-matching building is `muted` by default and only `hidden` in isolate mode.
 */

const WINDOW_MS = { live: 15 * 60_000, "24h": 24 * 3_600_000, "7d": 7 * 24 * 3_600_000, "30d": 30 * 24 * 3_600_000 } as const;

/** Lower-case, accent-insensitive: "Nestlé" must be found by "nestle". */
export function normalise(s: string): string {
  return s
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .trim();
}

export function matchesQuery(asset: WorldAsset, query: string): boolean {
  const q = normalise(query);
  if (!q) return true;
  return (
    normalise(asset.name).includes(q) ||
    normalise(asset.ticker ?? "").includes(q) ||
    normalise(asset.isin).includes(q)
  );
}

/**
 * The UI clock ticks every 15 s (`useClock`), so "now" can trail the real time by that much:
 * an event emitted a second ago is later than the last tick and must not read as the future.
 */
export const CLOCK_SKEW_MS = 15_000;

function inWindow(e: WorldEvent, filters: WorldFilters, nowMs: number): boolean {
  const t = Date.parse(e.occurredAt);
  if (Number.isNaN(t)) return false;
  return t <= nowMs + CLOCK_SKEW_MS && nowMs - t <= WINDOW_MS[filters.window];
}

function hasEventConstraint(f: WorldFilters): boolean {
  return f.directions.length > 0 || f.categories.length > 0 || f.severities.length > 0;
}

/** Events that pass the time window and the event-level filters. */
export function filterEvents(
  events: readonly WorldEvent[],
  filters: WorldFilters,
  nowMs: number,
): WorldEvent[] {
  return events.filter(
    (e) =>
      inWindow(e, filters, nowMs) &&
      (filters.directions.length === 0 || filters.directions.includes(e.direction)) &&
      (filters.categories.length === 0 || filters.categories.includes(e.category)) &&
      (filters.severities.length === 0 || filters.severities.includes(e.severity)),
  );
}

function assetPasses(a: WorldAsset, f: WorldFilters): boolean {
  if (!matchesQuery(a, f.query)) return false;
  if (f.minWeightPct !== null && (a.weightPct === null || a.weightPct < f.minWeightPct)) {
    // Unknown weight is not "below the threshold": it is unknown, and unknown is not shown as small.
    return false;
  }
  if (f.assetTypes.length && !f.assetTypes.includes(a.assetType)) return false;
  if (f.archetypes.length && !f.archetypes.includes(a.archetype)) return false;
  if (f.countries.length && (a.country === null || !f.countries.includes(a.country))) return false;
  if (f.brokers.length && !a.brokers.some((b) => f.brokers.includes(b))) return false;
  if (f.favouritesOnly && !a.favourite) return false;
  return true;
}

/** Visibility of every asset under the filters, given the events currently known. */
export function applyFilters(
  assets: readonly WorldAsset[],
  events: readonly WorldEvent[],
  filters: WorldFilters,
  nowMs: number,
): Map<string, Visibility> {
  const needsEvents = filters.activeOnly || hasEventConstraint(filters);
  const withEvents = new Set<string>();
  if (needsEvents) {
    for (const e of filterEvents(events, filters, nowMs)) {
      if (e.assetId) withEvents.add(e.assetId);
    }
  }
  const out = new Map<string, Visibility>();
  for (const a of assets) {
    const ok = assetPasses(a, filters) && (!needsEvents || withEvents.has(a.id));
    out.set(a.id, ok ? "match" : filters.isolate ? "hidden" : "muted");
  }
  return out;
}

/** True when any filter narrows the view, for the "clear filters" affordance. */
export function hasActiveFilters(f: WorldFilters): boolean {
  return (
    f.query.trim() !== "" ||
    f.minWeightPct !== null ||
    f.assetTypes.length > 0 ||
    f.archetypes.length > 0 ||
    f.countries.length > 0 ||
    f.brokers.length > 0 ||
    f.directions.length > 0 ||
    f.categories.length > 0 ||
    f.severities.length > 0 ||
    f.favouritesOnly ||
    f.activeOnly
  );
}
