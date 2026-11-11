import { describe, expect, it } from "vitest";
import { towerSpec } from "../model/towerSpec";
import { ARCHETYPES } from "../model/types";
import { NOMINAL, composeSite } from "./buildingFactory";
import { fillerMaxExtent } from "./fillers";

/**
 * Size = weight: the scenery must stay smaller than the smallest holding. A weightless holding is
 * drawn at the outpost's nominal footprint x 1.28 (see scene.ts), so that is the yardstick.
 */
const SCALE = 1.28;

describe("fillers vs the smallest holding", () => {
  it("never rise above the lowest outpost of any archetype", () => {
    const { height } = fillerMaxExtent();
    let lowest = Infinity;
    for (const a of ARCHETYPES) {
      for (let i = 0; i < 40; i++) {
        const id = `ZZ${1_000_000_000 + i * 7919}`;
        lowest = Math.min(lowest, composeSite(towerSpec(a, id, "outpost"), NOMINAL.outpost, false).top * SCALE);
      }
    }
    expect(height).toBeLessThan(lowest);
  });

  it("never exceed the plot of an outpost in width", () => {
    const { width } = fillerMaxExtent();
    expect(width).toBeLessThan(NOMINAL.outpost * 1.18 * SCALE);
  });
});
