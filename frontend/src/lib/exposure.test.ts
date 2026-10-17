import { describe, expect, it } from "vitest";

import {
  type ExposureBucket,
  coveredPct,
  isUnknownBucket,
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
});
