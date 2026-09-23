import { describe, expect, it } from "vitest";
import { fmt, fmtCompact, fmtDateTime, fmtPct } from "./format";

describe("fmt", () => {
  it("formats with es-ES separators and fixed decimals", () => {
    expect(fmt(1234.5)).toBe("1234,50");
    expect(fmt(1234567.891, 1)).toBe("1.234.567,9");
    expect(fmt(87.844, 0)).toBe("88");
  });
  it("parses decimal strings from the fiscal API", () => {
    expect(fmt("12.5")).toBe("12,50");
  });
  it("returns an em dash for absent or unparsable input", () => {
    expect(fmt(null)).toBe("—");
    expect(fmt(undefined)).toBe("—");
    expect(fmt("abc")).toBe("—");
  });
});

describe("fmtPct", () => {
  it("treats the input as percent units already", () => {
    expect(fmtPct(87.84)).toBe("87.8%");
    expect(fmtPct(0.1234 * 100)).toBe("12.3%");
  });
  it("returns an em dash for absent input", () => {
    expect(fmtPct(null)).toBe("—");
  });
});

describe("fmtCompact", () => {
  it("scales to B / M / k with the euro prefix", () => {
    expect(fmtCompact(1_250_000_000)).toBe("€1.3B");
    expect(fmtCompact(340_500_000)).toBe("€340.5M");
    expect(fmtCompact(750_000)).toBe("€750k");
    expect(fmtCompact(12.4)).toBe("€12");
    expect(fmtCompact(null)).toBe("—");
  });
});

describe("fmtDateTime", () => {
  it("matches the inline toLocaleString call it replaces", () => {
    const iso = "2026-09-23T14:05:00Z";
    expect(fmtDateTime(iso)).toBe(new Date(iso).toLocaleString("es-ES"));
  });
});
