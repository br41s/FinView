/**
 * Portfolio exposure by sector and region, from each issuer's own annual report
 * (`GET /portfolio/exposure`). The backend reads SEC 10-K filings and ESEF
 * segment notes and publishes a breakdown only when its lines add up to the
 * report's tagged total; everything it cannot vouch for is the "no_data" bucket.
 */

/** What a report's segment figures are. Revenue for almost every issuer; banks,
 *  insurers and property companies tag no revenue line, so their breakdown is of
 *  margen bruto, insurance revenue or rental income, and the UI says which. */
export type Measure = "revenue" | "bank_gross_income" | "insurance_revenue" | "rental_income";

const MEASURE_NAME: Record<Measure, string> = {
  revenue: "ingresos",
  bank_gross_income: "margen bruto",
  insurance_revenue: "ingresos de seguros",
  rental_income: "ingresos por alquiler",
};

export function measureName(measure: Measure): string {
  return MEASURE_NAME[measure];
}

/** "40 % de sus ingresos", "40 % de su margen bruto": the possessive agrees with it. */
export function shareOf(measure: Measure | null): string {
  const m = measure ?? "revenue";
  return `de ${m === "bank_gross_income" ? "su" : "sus"} ${MEASURE_NAME[m]}`;
}

export interface ExposureSegment {
  label: string;
  pct: number;
}

export interface ExposureHolding {
  isin: string;
  name: string;
  ticker: string | null;
  value_eur: number;
  measure: Measure | null;
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
  measure: Measure | null;
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
