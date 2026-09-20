import { describe, expect, it } from "vitest";
import {
  formatAccuracyLine,
  type GeoAccuracy,
  type GeoCheckpointHorizon,
  type GeoHorizonAccuracy,
} from "./geo";

const NOW = new Date("2026-09-20T12:00:00Z").getTime();

function bucket(over: Partial<GeoHorizonAccuracy> = {}): GeoHorizonAccuracy {
  return { correct: 0, incorrect: 0, neutral: 0, pending: 0, accuracy: null, ...over };
}

function data(
  horizons: Partial<Record<GeoCheckpointHorizon, GeoHorizonAccuracy>>,
  since = "2026-08-21T12:00:00Z",
): GeoAccuracy {
  return { since, horizons, rules: [] };
}

describe("formatAccuracyLine", () => {
  it("says nothing before the first fetch lands", () => {
    expect(formatAccuracyLine(null, NOW)).toBeNull();
  });

  it("renders every horizon, the window and the sample size", () => {
    const line = formatAccuracyLine(
      data({
        "1h": bucket({ correct: 12, incorrect: 88, accuracy: 0.12 }),
        "6h": bucket({ correct: 18, incorrect: 82, accuracy: 0.18 }),
        "1d": bucket({ correct: 30, incorrect: 70, accuracy: 0.3 }),
        "3d": bucket({ correct: 41, incorrect: 59, accuracy: 0.41 }),
        "7d": bucket({ correct: 45, incorrect: 55, accuracy: 0.45 }),
      }),
      NOW,
    );
    expect(line).toBe(
      "Aciertos (30 d): 1h 12 % · 6h 18 % · 1d 30 % · 3d 41 % · 7d 45 % · n=500",
    );
  });

  it("shows a dash, never 0 %, for a horizon with nothing measurable", () => {
    // The distinction the dots lost: unmeasured is not a zero hit rate.
    const line = formatAccuracyLine(
      data({ "1h": bucket({ neutral: 9, pending: 3 }) }),
      NOW,
    );
    expect(line).toContain("1h —");
    expect(line).not.toContain("0 %");
  });

  it("keeps a real 0 % distinct from no measurement", () => {
    const line = formatAccuracyLine(
      data({ "1h": bucket({ correct: 0, incorrect: 7, accuracy: 0 }) }),
      NOW,
    );
    expect(line).toContain("1h 0 %");
    expect(line).toContain("6h —");
  });

  it("leaves NEUTRAL and PENDING out of the sample size", () => {
    const line = formatAccuracyLine(
      data({
        "1d": bucket({ correct: 2, incorrect: 3, neutral: 40, pending: 20, accuracy: 0.4 }),
      }),
      NOW,
    );
    expect(line).toContain("n=5");
  });

  it("dashes every horizon when the backend returns an empty matrix", () => {
    expect(formatAccuracyLine(data({}), NOW)).toBe(
      "Aciertos (30 d): 1h — · 6h — · 1d — · 3d — · 7d — · n=0",
    );
  });

  it("derives the window from `since` rather than assuming 30 days", () => {
    const line = formatAccuracyLine(data({}, "2026-09-13T12:00:00Z"), NOW);
    expect(line).toContain("Aciertos (7 d)");
  });

  it("never reports a zero-day window", () => {
    const line = formatAccuracyLine(data({}, "2026-09-20T11:00:00Z"), NOW);
    expect(line).toContain("Aciertos (1 d)");
  });

  it("rounds the percentage to whole points", () => {
    const line = formatAccuracyLine(
      data({ "1h": bucket({ correct: 1, incorrect: 2, accuracy: 1 / 3 }) }),
      NOW,
    );
    expect(line).toContain("1h 33 %");
  });
});
