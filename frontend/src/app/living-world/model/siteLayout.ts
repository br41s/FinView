import { hashString, seeded } from "./rng";
import type { PartSpec, TowerSpec, Zone } from "./towerSpec";

/**
 * Where the extra parts of a holding stand on its plot. Slots are in units of the nominal
 * footprint `n`, centred on the plot, +z towards the street (the sign and the entrance). The main
 * structure stands at the middle (z = -0.02) and never reaches the slots; the front band stays low.
 * Pure and stateless: the order of the slots in a zone is shuffled by the id, parts are placed in
 * the order they were added, so a part never moves when a tier adds another.
 */

export interface Slot {
  x: number;
  z: number;
  w: number;
  d: number;
}

export const SLOTS: Record<Zone, readonly Slot[]> = {
  front: [
    { x: -0.3, z: 0.31, w: 0.3, d: 0.22 },
    { x: 0.3, z: 0.31, w: 0.3, d: 0.22 },
    { x: 0, z: 0.31, w: 0.26, d: 0.22 },
  ],
  flank: [
    { x: -0.38, z: -0.02, w: 0.2, d: 0.36 },
    { x: 0.38, z: -0.02, w: 0.2, d: 0.36 },
  ],
  back: [
    { x: -0.27, z: -0.37, w: 0.26, d: 0.2 },
    { x: 0.27, z: -0.37, w: 0.26, d: 0.2 },
    { x: 0, z: -0.4, w: 0.2, d: 0.16 },
  ],
};

const OVERFLOW: readonly Zone[] = ["front", "flank", "back"];

export interface Placement {
  part: PartSpec;
  slot: Slot;
}

export function placeParts(spec: TowerSpec): Placement[] {
  const r = seeded(hashString(spec.id + ":slots"));
  const order = {} as Record<Zone, Slot[]>;
  for (const z of OVERFLOW) {
    const list = SLOTS[z].map((s) => ({ s, k: r() }));
    list.sort((a, b) => a.k - b.k);
    order[z] = list.map((o) => o.s);
  }
  const used = new Set<Slot>();
  const out: Placement[] = [];
  for (const part of spec.parts) {
    const pool = [order[part.zone], ...OVERFLOW.filter((z) => z !== part.zone).map((z) => order[z])];
    let slot: Slot | undefined;
    for (const zone of pool) {
      slot = zone.find((s) => !used.has(s));
      if (slot) break;
    }
    if (!slot) continue;
    used.add(slot);
    out.push({ part, slot: spec.mirror ? { ...slot, x: -slot.x } : slot });
  }
  return out;
}
