import { describe, expect, it } from "vitest";

import { betaPct, mentionsText, quotesNote, releaseEs } from "./aiExposure";

describe("mentionsText", () => {
  it("is null until the report is read", () => {
    expect(mentionsText({ mentions: null, per_10k_words: null })).toBeNull();
  });

  it("gives the count and its density in Spanish number format", () => {
    expect(mentionsText({ mentions: 85, per_10k_words: 71.5 })).toBe(
      "85 menciones · 71,5 por 10.000 palabras",
    );
  });

  it("uses the singular and drops the density for zero", () => {
    expect(mentionsText({ mentions: 1, per_10k_words: 0.4 })).toBe(
      "1 mención · 0,4 por 10.000 palabras",
    );
    expect(mentionsText({ mentions: 0, per_10k_words: 0 })).toBe("0 menciones");
  });
});

describe("quotesNote", () => {
  it("explains rejected quotes without showing them", () => {
    expect(quotesNote({ mentions: 4, quotes_status: "unverified" })).toMatch(/no coincidían/);
  });

  it("tells a report that never names AI from one whose mentions say nothing", () => {
    expect(quotesNote({ mentions: 0, quotes_status: "none" })).toMatch(/no menciona/);
    expect(quotesNote({ mentions: 3, quotes_status: "none" })).toMatch(/no describen/);
  });

  it("is null when there are quotes to show", () => {
    expect(quotesNote({ mentions: 3, quotes_status: "ok" })).toBeNull();
  });
});

describe("releaseEs", () => {
  it("names the BLS release in Spanish", () => {
    expect(releaseEs("May 2025")).toBe("mayo de 2025");
  });

  it("leaves a format it does not know as it is", () => {
    expect(releaseEs("2025Q2")).toBe("2025Q2");
  });
});

describe("betaPct", () => {
  it("shows the share of tasks as a whole percentage", () => {
    expect(betaPct(0.3412)).toBe("34 %");
  });
});
