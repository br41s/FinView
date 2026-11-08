import { describe, expect, it } from "vitest";
import { CRITICAL_AT, IMPORTANT_AT, bucketFor, magnitudeFactor, relevanceFactor, scoreEvent } from "./priority";

describe("bucketFor", () => {
  it("buckets at the documented boundaries", () => {
    expect(bucketFor(IMPORTANT_AT - 0.001)).toBe("normal");
    expect(bucketFor(IMPORTANT_AT)).toBe("important");
    expect(bucketFor(CRITICAL_AT - 0.001)).toBe("important");
    expect(bucketFor(CRITICAL_AT)).toBe("critical");
  });

  it("keeps the thresholds ordered", () => {
    expect(IMPORTANT_AT).toBeLessThan(CRITICAL_AT);
  });
});

describe("factors", () => {
  it("scales a price move by its size and clamps it", () => {
    expect(magnitudeFactor("price_move_up", { change_pct: 2 })).toBe(1);
    expect(magnitudeFactor("price_move_down", { change_pct: -2 })).toBe(1);
    expect(magnitudeFactor("price_move_up", { change_pct: 0.01 })).toBe(0.5);
    expect(magnitudeFactor("price_move_up", { change_pct: 90 })).toBe(3);
  });

  it("treats a missing figure as neutral rather than inventing a magnitude", () => {
    expect(magnitudeFactor("price_move_up", {})).toBe(1);
    expect(magnitudeFactor("earnings_miss", { surprise_pct: null })).toBe(1);
    expect(relevanceFactor(null)).toBe(1);
  });

  it("weights relevance between 0.5 and 2", () => {
    expect(relevanceFactor(0)).toBe(0.5);
    expect(relevanceFactor(10)).toBe(2);
    expect(relevanceFactor(55)).toBe(2);
  });
});

describe("scoreEvent", () => {
  it("is the product of its factors and is deterministic", () => {
    const a = scoreEvent("earnings_miss", { surprise_pct: -10 }, { weightPct: 5 }, "verified");
    const b = scoreEvent("earnings_miss", { surprise_pct: -10 }, { weightPct: 5 }, "verified");
    expect(a).toEqual(b);
    expect(a.score).toBeCloseTo(a.base * a.magnitude * a.relevance * a.confidence, 12);
  });

  it("ranks a verified event above the same event reported second-hand", () => {
    const m = { change_pct: 4 };
    const v = scoreEvent("price_move_up", m, { weightPct: 3 }, "verified").score;
    const r = scoreEvent("price_move_up", m, { weightPct: 3 }, "reported").score;
    expect(v).toBeGreaterThan(r);
  });

  it("ranks the same event higher on a bigger position", () => {
    const m = { change_pct: 4 };
    expect(scoreEvent("price_move_up", m, { weightPct: 8 }, "verified").score).toBeGreaterThan(
      scoreEvent("price_move_up", m, { weightPct: 1 }, "verified").score,
    );
  });
});
