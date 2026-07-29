import { describe, expect, it } from "vitest";
import { getAccountValueDisplay } from "./portfolioValues";

describe("getAccountValueDisplay", () => {
  it("preserves a zero market value instead of falling back to cost", () => {
    expect(getAccountValueDisplay(0, 125)).toEqual({ amount: 0, kind: "market" });
  });

  it("uses cost only when market value is unknown", () => {
    expect(getAccountValueDisplay(null, 125)).toEqual({ amount: 125, kind: "cost" });
  });

  it("returns no display value when both amounts are unknown", () => {
    expect(getAccountValueDisplay(null, null)).toBeNull();
  });
});
