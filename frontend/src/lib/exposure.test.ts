import { describe, expect, it } from "vitest";

import {
  type ExposureBucket,
  coveredPct,
  isUnknownBucket,
  estimateNote,
  estimatedPct,
  estimatedSourceNote,
  measureName,
  shareOf,
  shouldRefreshAgain,
  sourceName,
} from "./exposure";

function bucket(key: string, pct: number): ExposureBucket {
  return { key, label: key, value_eur: pct, pct, holdings: [] };
}

describe("shouldRefreshAgain", () => {
  it("continues while a step reads reports and some are still due", () => {
    expect(shouldRefreshAgain({ checked: 3, pending: 5 })).toBe(true);
  });

  it("stops when nothing is due", () => {
    expect(shouldRefreshAgain({ checked: 3, pending: 0 })).toBe(false);
  });

  it("stops when a step made no progress, so a failing source is not hammered", () => {
    expect(shouldRefreshAgain({ checked: 0, pending: 5 })).toBe(false);
  });
});

describe("coveredPct", () => {
  it("is the share outside the no-data bucket", () => {
    expect(coveredPct([bucket("utilities", 62.5), bucket("no_data", 37.5)])).toBe(62.5);
  });

  it("is 100 when every position has a report", () => {
    expect(coveredPct([bucket("technology", 100)])).toBe(100);
  });

  it("counts unassigned segments as covered: the report was read", () => {
    expect(coveredPct([bucket("unassigned", 20), bucket("energy", 80)])).toBe(100);
  });
});

describe("labels", () => {
  it("marks both don't-know buckets", () => {
    expect(isUnknownBucket("no_data")).toBe(true);
    expect(isUnknownBucket("unassigned")).toBe(true);
    expect(isUnknownBucket("spain")).toBe(false);
  });

  it("names each source", () => {
    expect(sourceName("sec")).toBe("SEC 10-K");
    expect(sourceName("esef")).toBe("Informe anual ESEF");
    expect(sourceName(null)).toBe("—");
  });

  it("names the measure a bank, insurer or property company is split by", () => {
    expect(measureName("bank_gross_income")).toBe("margen bruto");
    expect(measureName("insurance_revenue")).toBe("ingresos de seguros");
    expect(measureName("rental_income")).toBe("ingresos por alquiler");
  });

  it("marks every listing-based line as an estimate", () => {
    expect(estimateNote("sector")).toBe("sector de cotización en Yahoo Finance (estimado)");
    expect(estimateNote("geography")).toBe("país del ISIN (estimado)");
    expect(estimatedSourceNote(["sector"])).toBe("Sector estimado por su cotización (Yahoo Finance)");
    expect(estimatedSourceNote(["geography"])).toBe("Región estimada por el país del ISIN");
    expect(estimatedSourceNote(["sector", "geography"])).toMatch(/^Sector y región estimados/);
    expect(estimatedSourceNote([])).toBeNull();
  });

  it("measures the estimated share of the charted value", () => {
    const holding = (value_eur: number, basis: "report" | "listing" | null) => ({
      isin: "X", name: "X", ticker: null, value_eur, basis, measure: null, segments: [],
    });
    const buckets: ExposureBucket[] = [
      { key: "financials", label: "Finanzas", value_eur: 75, pct: 75,
        holdings: [holding(50, "report"), holding(25, "listing")] },
      { key: "no_data", label: "Sin datos", value_eur: 25, pct: 25, holdings: [holding(25, null)] },
    ];
    expect(estimatedPct(buckets)).toBe(25);
    expect(estimatedPct([])).toBe(0);
  });

  it("says what a segment's share is a share of", () => {
    expect(shareOf("revenue")).toBe("de sus ingresos");
    expect(shareOf("bank_gross_income")).toBe("de su margen bruto");
    expect(shareOf("insurance_revenue")).toBe("de sus ingresos de seguros");
    expect(shareOf(null)).toBe("de sus ingresos");
  });
});
