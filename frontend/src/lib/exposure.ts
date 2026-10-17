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

/** Where a holding's split on one axis comes from: its annual report, or, for a stock
 *  no report breaks down, its listing (100% in its ISIN's country and in its sector on
 *  Yahoo Finance). The listing is an estimate and every place that shows it says so. */
export type Basis = "report" | "listing";
export type Axis = "sector" | "geography";

export interface ExposureHolding {
  isin: string;
  name: string;
  ticker: string | null;
  value_eur: number;
  basis: Basis | null;
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
  estimated: Axis[];
  listing_sector: string | null;
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

/** What a listing-based line is, after its label. */
export function estimateNote(axis: Axis): string {
  return axis === "sector"
    ? "sector de cotización en Yahoo Finance (estimado)"
    : "país del ISIN (estimado)";
}

/** The source-list note for a position whose split is partly or wholly estimated. */
export function estimatedSourceNote(estimated: Axis[]): string | null {
  const sector = estimated.includes("sector");
  const region = estimated.includes("geography");
  if (sector && region) return "Sector y región estimados: sector de cotización (Yahoo Finance) y país del ISIN";
  if (sector) return "Sector estimado por su cotización (Yahoo Finance)";
  if (region) return "Región estimada por el país del ISIN";
  return null;
}

/** Share of the charted value whose split is an estimate from the listing. */
export function estimatedPct(buckets: ExposureBucket[]): number {
  const total = buckets.reduce((sum, b) => sum + b.value_eur, 0);
  if (total <= 0) return 0;
  const listed = buckets
    .flatMap((b) => b.holdings)
    .filter((h) => h.basis === "listing")
    .reduce((sum, h) => sum + h.value_eur, 0);
  return Math.round((listed / total) * 1000) / 10;
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
