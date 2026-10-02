import { describe, expect, it } from "vitest";

import {
  MAX_BEARS_PER_MINUTE,
  START_BEARS_PER_MINUTE,
  bearsPerMinute,
} from "./difficulty";

describe("bearsPerMinute", () => {
  it("starts at the opening rate", () => {
    expect(bearsPerMinute(0)).toBe(START_BEARS_PER_MINUTE);
  });

  it("never gets easier as time passes", () => {
    let previous = bearsPerMinute(0);
    for (let ms = 0; ms <= 20 * 60_000; ms += 15_000) {
      const rate = bearsPerMinute(ms);
      expect(rate).toBeGreaterThanOrEqual(previous);
      previous = rate;
    }
  });

  it("stops rising at the cap, so a long game stays playable", () => {
    expect(bearsPerMinute(60 * 60_000)).toBe(MAX_BEARS_PER_MINUTE);
  });

  it("treats a negative clock as the start", () => {
    expect(bearsPerMinute(-5000)).toBe(START_BEARS_PER_MINUTE);
  });
});
