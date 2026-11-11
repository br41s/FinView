import { describe, expect, it } from "vitest";
import type { FillerKind } from "../model/townLayout";
import { fillerColours, fillerPalette } from "./fillerPalette";
import { QUALITY } from "./quality";
import { skyAt, sunPosition, SKY_KEYS } from "./skyModel";

const KINDS: FillerKind[] = ["skyscraper", "tower", "block", "house", "villa", "shed"];

function saturation(hex: number): number {
  const r = ((hex >> 16) & 255) / 255;
  const g = ((hex >> 8) & 255) / 255;
  const b = (hex & 255) / 255;
  const max = Math.max(r, g, b);
  const min = Math.min(r, g, b);
  return max === 0 ? 0 : (max - min) / max;
}

describe("filler palettes", () => {
  it("picks the same colours for the same tone, and every tone from 0 to 1 is valid", () => {
    for (const kind of KINDS) {
      for (let i = 0; i <= 100; i++) {
        const tone = i / 100;
        const a = fillerColours(kind, tone);
        expect(a).toBe(fillerColours(kind, tone));
        expect(fillerPalette(kind)).toContain(a);
      }
      // Out-of-range tones are clamped instead of indexing past the list.
      expect(fillerColours(kind, -1)).toBe(fillerPalette(kind)[0]);
      expect(fillerColours(kind, 7)).toBe(fillerPalette(kind).at(-1));
    }
  });

  it("is colourful, not grey: every glass/accent colour is clearly saturated", () => {
    for (const kind of KINDS) {
      for (const c of fillerPalette(kind)) expect(saturation(c.glass)).toBeGreaterThan(0.55);
    }
  });

  it("gives every kind several looks, and no two kinds share the same family", () => {
    for (const kind of KINDS) expect(fillerPalette(kind).length).toBeGreaterThanOrEqual(3);
    const glassOf = (k: FillerKind) => new Set(fillerPalette(k).map((c) => c.glass));
    for (let i = 0; i < KINDS.length; i++) {
      for (let j = i + 1; j < KINDS.length; j++) {
        const a = glassOf(KINDS[i]);
        const shared = [...glassOf(KINDS[j])].filter((g) => a.has(g));
        expect(shared.length).toBeLessThan(a.size);
      }
    }
  });
});

describe("sky model", () => {
  it("is full night at midnight and broad daylight at noon", () => {
    expect(skyAt(0).night).toBe(1);
    expect(skyAt(2).night).toBe(1);
    expect(skyAt(12).night).toBe(0);
    expect(skyAt(15).night).toBe(0);
  });

  it("wraps around the clock", () => {
    expect(skyAt(36).horizon).toEqual(skyAt(12).horizon);
    expect(skyAt(-1).night).toBeCloseTo(skyAt(23).night, 10);
  });

  it("has no jumps: neighbouring minutes differ by little", () => {
    let prev = skyAt(0);
    for (let m = 1; m <= 24 * 60; m++) {
      const s = skyAt(m / 60);
      expect(Math.abs(s.night - prev.night)).toBeLessThan(0.02);
      expect(Math.abs(s.sunIntensity - prev.sunIntensity)).toBeLessThan(0.02);
      prev = s;
    }
  });

  it("keys are ordered and span the whole day", () => {
    expect(SKY_KEYS[0].hour).toBe(0);
    expect(SKY_KEYS.at(-1)!.hour).toBe(24);
    for (let i = 1; i < SKY_KEYS.length; i++) expect(SKY_KEYS[i].hour).toBeGreaterThan(SKY_KEYS[i - 1].hour);
    // The sky at the two ends of the day is the same, so the wrap is seamless.
    expect(skyAt(23.999).horizon[2]).toBeCloseTo(skyAt(0).horizon[2], 3);
  });

  it("keeps the sun above a minimum elevation, so shadows never go flat", () => {
    for (let h = 0; h < 24; h += 0.5) {
      const [x, y, z] = sunPosition(h, 100);
      expect(y).toBeGreaterThanOrEqual(30);
      expect(Math.hypot(x, y, z)).toBeGreaterThan(0);
    }
  });
});

describe("quality tiers", () => {
  it("low draws straight to the canvas; medium and high run the post chain", () => {
    expect(QUALITY.low.post).toBeNull();
    expect(QUALITY.medium.post).not.toBeNull();
    expect(QUALITY.high.post).not.toBeNull();
  });

  it("each tier is at least as expensive as the one below", () => {
    const m = QUALITY.medium.post!;
    const h = QUALITY.high.post!;
    expect(h.aoSamples).toBeGreaterThanOrEqual(m.aoSamples);
    expect(h.aoDenoiseSamples).toBeGreaterThanOrEqual(m.aoDenoiseSamples);
    expect(QUALITY.low.shadowMapSize).toBeLessThan(QUALITY.medium.shadowMapSize);
    expect(QUALITY.medium.shadowMapSize).toBeLessThan(QUALITY.high.shadowMapSize);
    expect(QUALITY.low.trees).toBeLessThan(QUALITY.medium.trees);
    expect(QUALITY.medium.trees).toBeLessThan(QUALITY.high.trees);
  });

  it("only the top tier pays for bloom, and AO is always half resolution", () => {
    expect(QUALITY.medium.post!.bloom).toBe(false);
    expect(QUALITY.high.post!.bloom).toBe(true);
    expect(QUALITY.medium.post!.aoHalfRes && QUALITY.high.post!.aoHalfRes).toBe(true);
  });

  it("low has no shadows, the others do", () => {
    expect(QUALITY.low.shadows).toBe(false);
    expect(QUALITY.medium.shadows && QUALITY.high.shadows).toBe(true);
  });
});
