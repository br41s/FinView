/**
 * Portfolio weight → building footprint (spec §4.3).
 *
 * Size says "how much of the portfolio", never "how did the price do today": the input
 * is the weight, not a price change. The curve is piecewise-linear between tier
 * boundaries so a big position cannot dwarf every small one, and it is continuous so a
 * position crossing a boundary does not jump.
 */

export type Tier = "outpost" | "small" | "campus" | "major";
export const TIERS: readonly Tier[] = ["outpost", "small", "campus", "major"];

/** [tier, lower weight bound %, footprint at the lower bound] */
const STEPS: ReadonlyArray<readonly [Tier, number, number]> = [
  ["outpost", 0, 3.4],
  ["small", 1, 4.2],
  ["campus", 3, 5.2],
  ["major", 7, 6.2],
];
/** Weight at/after which the footprint stops growing, and the footprint there. */
const CAP_WEIGHT = 15;
const CAP_SIZE = 7;

/** Largest footprint; the layout sizes its lots from this. */
export const MAX_FOOTPRINT = CAP_SIZE;

/** An unknown valuation is drawn as the smallest site, marked unknown by the caller. */
export function footprintFor(weightPct: number | null): number {
  if (weightPct === null || !Number.isFinite(weightPct) || weightPct <= 0) return STEPS[0][2];
  if (weightPct >= CAP_WEIGHT) return CAP_SIZE;
  for (let i = STEPS.length - 1; i >= 0; i--) {
    const [, lo, sizeLo] = STEPS[i];
    if (weightPct >= lo) {
      const hi = i + 1 < STEPS.length ? STEPS[i + 1][1] : CAP_WEIGHT;
      const sizeHi = i + 1 < STEPS.length ? STEPS[i + 1][2] : CAP_SIZE;
      return sizeLo + ((weightPct - lo) / (hi - lo)) * (sizeHi - sizeLo);
    }
  }
  return STEPS[0][2];
}

export function tierFor(weightPct: number | null): Tier {
  if (weightPct === null || !Number.isFinite(weightPct)) return "outpost";
  let tier: Tier = "outpost";
  for (const [t, lo] of STEPS) if (weightPct >= lo) tier = t;
  return tier;
}

/**
 * Tier with hysteresis: a weight hovering on a boundary must not make a building
 * flicker between components. Moves only once the weight is `margin` points past it.
 */
export function tierWithHysteresis(prev: Tier, weightPct: number | null, margin = 0.25): Tier {
  const next = tierFor(weightPct);
  if (next === prev || weightPct === null) return next;
  const pi = TIERS.indexOf(prev);
  const ni = TIERS.indexOf(next);
  if (ni > pi) {
    // Growing: require clearing the lower bound of the new tier by the margin.
    return weightPct >= STEPS[pi + 1][1] + margin ? next : prev;
  }
  // Shrinking: require dropping below the lower bound of the current tier by the margin.
  return weightPct < STEPS[pi][1] - margin ? next : prev;
}

/** How many sub-buildings a site shows (outpost 1 … major 4). */
export function componentCount(tier: Tier): number {
  return TIERS.indexOf(tier) + 1;
}

/** Frame-rate independent exponential approach, for smooth resizes. */
export function approach(current: number, target: number, dtMs: number, halfLifeMs = 400): number {
  if (dtMs <= 0) return current;
  const k = 1 - Math.pow(0.5, dtMs / halfLifeMs);
  const next = current + (target - current) * k;
  return Math.abs(target - next) < 1e-3 ? target : next;
}
