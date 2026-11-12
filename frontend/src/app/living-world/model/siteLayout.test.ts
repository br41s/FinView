import { describe, expect, it } from "vitest";
import { TIERS } from "./scale";
import { placeParts } from "./siteLayout";
import { towerSpec } from "./towerSpec";
import { ARCHETYPES } from "./types";

const ids = ["ES0113211835", "US0378331005", "ZZ1000007919", "FR0000120271", "DE0007164600"];

describe("placeParts", () => {
  it("gives every part a slot of its own, within the plot", () => {
    for (const a of ARCHETYPES) {
      for (const id of ids) {
        const placed = placeParts(towerSpec(a, id, "major"));
        expect(placed.length).toBe(7);
        const keys = placed.map((p) => `${p.slot.x}:${p.slot.z}`);
        expect(new Set(keys).size).toBe(keys.length);
        for (const { slot } of placed) {
          expect(Math.abs(slot.x) + slot.w / 2).toBeLessThanOrEqual(0.5 + 1e-9);
          expect(Math.abs(slot.z) + slot.d / 2).toBeLessThanOrEqual(0.5 + 1e-9);
        }
      }
    }
  });

  it("never moves a part when a bigger tier adds more", () => {
    for (const a of ARCHETYPES) {
      for (const id of ids) {
        let prev = placeParts(towerSpec(a, id, "outpost"));
        for (const t of TIERS.slice(1)) {
          const next = placeParts(towerSpec(a, id, t));
          expect(next.slice(0, prev.length)).toEqual(prev);
          prev = next;
        }
      }
    }
  });

  it("keeps the front band low: slots near the street never reach the main structure", () => {
    for (const a of ARCHETYPES) {
      for (const { slot } of placeParts(towerSpec(a, ids[0], "major"))) {
        // The main structure stands at z = -0.02 and is at most ~0.42 wide: nothing overlaps it in z AND x.
        const overlapsMain = Math.abs(slot.x) - slot.w / 2 < 0.21 && Math.abs(slot.z + 0.02) - slot.d / 2 < 0.2;
        expect(overlapsMain).toBe(false);
      }
    }
  });

  it("mirrors left to right with the id, not with the tier", () => {
    const m = (t: "outpost" | "major") => placeParts(towerSpec("tech", ids[2], t)).map((p) => Math.sign(p.slot.x));
    expect(m("outpost")[0]).toBe(m("major")[0]);
  });
});
