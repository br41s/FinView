/**
 * Portfolio exposure by sector and region, from each issuer's own annual report
 * (`GET /portfolio/exposure`). The backend reads SEC 10-K filings and ESEF
 * segment notes and publishes a breakdown only when its lines add up to the
 * report's total revenue; everything it cannot vouch for is the "no_data" bucket.
 */

export interface ExposureSegment {
  label: string;
  pct: number;
}

export interface ExposureHolding {
  isin: string;
  name: string;
  ticker: string | null;
  value_eur: number;
  segments: ExposureSegment[];
}

export interface ExposureBucket {
  key: string;
  label: string;
  value_eur: number;
  pct: number;
  holdings: ExposureHolding[];
}

export type SourceStatus =
  | "pending"
  | "ok"
  | "no_issuer"
  | "no_filing"
  | "no_revenue"
  | "no_segments"
  | "unreconciled";

export interface ExposureSource {
  isin: string;
  name: string;
  status: SourceStatus;
  detail: string;
  fiscal_year: number | null;
  source: "sec" | "esef" | null;
  url: string | null;
  axis_status: Record<string, string> | null;
}

export interface Exposure {
  total_value_eur: number;
  unpriced: { isin: string; name: string }[];
  sector: ExposureBucket[];
  geography: ExposureBucket[];
  sources: ExposureSource[];
  pending: number;
}

export interface ExposureRefresh {
  checked: number;
  pending: number;
}

export const NO_DATA = "no_data";
export const UNASSIGNED = "unassigned";

/** Buckets that say "we don't know", drawn in a neutral colour after the rest. */
export function isUnknownBucket(key: string): boolean {
  return key === NO_DATA || key === UNASSIGNED;
}

/** Another refresh step only while it makes progress: a step that checked
 *  nothing is waiting on a failing source, and asking again would just repeat it. */
export function shouldRefreshAgain(step: ExposureRefresh): boolean {
  return step.pending > 0 && step.checked > 0;
}

export function sourceName(source: ExposureSource["source"]): string {
  if (source === "sec") return "SEC 10-K";
  if (source === "esef") return "Informe anual ESEF";
  return "—";
}

/** Share of the portfolio the reports actually explain, for the card subtitle. */
export function coveredPct(buckets: ExposureBucket[]): number {
  const unknown = buckets.find((b) => b.key === NO_DATA)?.pct ?? 0;
  return Math.max(0, Math.round((100 - unknown) * 10) / 10);
}
