/**
 * How fast the bear market arrives.
 *
 * This is the one knob that decides how the game feels, so it lives alone and
 * is easy to change: a flat rate is relaxing, a steep ramp is frantic. The
 * garden compounds — more plants pay more coins — so the bears have to keep up
 * or a good player never loses.
 */

export const START_BEARS_PER_MINUTE = 5;
/** Added for every full minute played. */
export const GROWTH_PER_MINUTE = 3;
export const MAX_BEARS_PER_MINUTE = 18;

/** Bears arriving per minute once `elapsedMs` of play have passed. */
export function bearsPerMinute(elapsedMs: number): number {
  const minutes = Math.max(0, elapsedMs) / 60_000;
  return Math.min(MAX_BEARS_PER_MINUTE, START_BEARS_PER_MINUTE + GROWTH_PER_MINUTE * minutes);
}
