/**
 * Timetables of the two trains (pure): a function of the simulation clock, never an integrated
 * state, so the renderer, the level-crossing barriers and the road traffic all read the same
 * answer for the same time.
 *
 * - The ground train shuttles between the two ends of the railway: it waits at a terminus, pulls
 *   out, runs at cruising speed, brakes into the other terminus and comes back.
 * - The monorail circles the loop and stops at every station: brake in, dwell with the doors open,
 *   pull out. A second train runs the same timetable half a period later.
 */

export interface Kinematics {
  /** Cruising speed and acceleration/braking, in world units per second. */
  vmax: number;
  acc: number;
}

/** Time to cover `length` from rest to rest, and the distance covered after `tau` seconds. */
export function legTime(length: number, k: Kinematics): number {
  const da = (k.vmax * k.vmax) / (2 * k.acc);
  if (length >= 2 * da) return (2 * k.vmax) / k.acc + (length - 2 * da) / k.vmax;
  return (2 * Math.sqrt(length * k.acc)) / k.acc;
}

export function legAt(length: number, k: Kinematics, tau: number): { dist: number; speed: number } {
  const total = legTime(length, k);
  const t = Math.min(Math.max(0, tau), total);
  const da = (k.vmax * k.vmax) / (2 * k.acc);
  const cruise = length >= 2 * da;
  const vpeak = cruise ? k.vmax : Math.sqrt(length * k.acc);
  const ta = vpeak / k.acc;
  const tc = cruise ? (length - 2 * da) / k.vmax : 0;
  if (t < ta) return { dist: 0.5 * k.acc * t * t, speed: k.acc * t };
  if (t < ta + tc) return { dist: da + k.vmax * (t - ta), speed: k.vmax };
  const rest = total - t;
  return { dist: length - 0.5 * k.acc * rest * rest, speed: k.acc * rest };
}

export interface TrainState {
  /** Shuttle: centre of the train along the track. Loop: its head along the loop. */
  pos: number;
  speed: number;
  /** +1 outward / around, -1 coming back. */
  dir: 1 | -1;
  dwelling: boolean;
  /** Door opening 0..1 while it waits in a station. */
  doors: number;
  /** Index of the leg (shuttle: 0 out, 1 back; loop: the station it is leaving or has just left). */
  leg: number;
}

interface Cycle {
  legs: number[];
  dwell: number;
  k: Kinematics;
  /** Start time of each leg's dwell within the period. */
  starts: number[];
  period: number;
}

function makeCycle(legs: number[], dwell: number, k: Kinematics): Cycle {
  const starts: number[] = [];
  let t = 0;
  for (const l of legs) {
    starts.push(t);
    t += dwell + legTime(l, k);
  }
  return { legs, dwell, k, starts, period: t };
}

const smooth = (x: number) => {
  const t = Math.min(1, Math.max(0, x));
  return t * t * (3 - 2 * t);
};

function cycleAt(c: Cycle, time: number): { leg: number; dwelling: boolean; dist: number; speed: number; doors: number } {
  const t = ((time % c.period) + c.period) % c.period;
  let leg = c.legs.length - 1;
  for (let i = 0; i < c.legs.length; i++) {
    if (i === c.legs.length - 1 || t < c.starts[i + 1]) {
      leg = i;
      break;
    }
  }
  const local = t - c.starts[leg];
  if (local < c.dwell) {
    const doors = Math.min(smooth(local / 1.2), smooth((c.dwell - local) / 1.2));
    return { leg, dwelling: true, dist: 0, speed: 0, doors };
  }
  const m = legAt(c.legs[leg], c.k, local - c.dwell);
  return { leg, dwelling: false, dist: m.dist, speed: m.speed, doors: 0 };
}

export interface Shuttle {
  period: number;
  /** Track length the centre of the train travels (track minus the train itself). */
  travel: number;
  trainLength: number;
  at(t: number): TrainState;
}

/** A train that shuttles along a track of `trackLength`, its centre moving over `trackLength - trainLength`. */
export function createShuttle(trackLength: number, trainLength: number, k: Kinematics, dwell: number): Shuttle {
  const travel = trackLength - trainLength;
  const cycle = makeCycle([travel, travel], dwell, k);
  return {
    period: cycle.period,
    travel,
    trainLength,
    at(t) {
      const s = cycleAt(cycle, t);
      const out = s.leg === 0;
      return {
        pos: trainLength / 2 + (out ? s.dist : travel - s.dist),
        speed: s.speed,
        dir: out ? 1 : -1,
        dwelling: s.dwelling,
        doors: s.doors,
        leg: s.leg,
      };
    },
  };
}

/**
 * Is a level crossing at `at` (distance along the track) closed at time `t`? It closes `warn`
 * seconds before the train reaches the barriers and opens once its tail has cleared them.
 */
export function crossingClosed(shuttle: Shuttle, at: number, t: number, warn = 6, margin = 4.5): boolean {
  for (let dt = 0; dt <= warn; dt += 0.5) {
    if (Math.abs(shuttle.at(t + dt).pos - at) < shuttle.trainLength / 2 + margin) return true;
  }
  return false;
}

export interface Loop {
  period: number;
  trainLength: number;
  at(t: number, offset?: number): TrainState;
}

/**
 * A train on a closed loop that stops at the stations (distances along the loop, any order).
 * `pos` is the head's distance along the loop. A second train uses `offset = period / 2`.
 */
export function createLoop(loopLength: number, stations: readonly number[], trainLength: number, k: Kinematics, dwell: number): Loop {
  const sorted = [...stations].sort((a, b) => a - b);
  const legs = sorted.map((s, i) => {
    const next = sorted[(i + 1) % sorted.length] + (i === sorted.length - 1 ? loopLength : 0);
    return next - s;
  });
  const cycle = makeCycle(legs.length ? legs : [loopLength], dwell, k);
  const base = legs.length ? sorted : [0];
  return {
    period: cycle.period,
    trainLength,
    at(t, offset = 0) {
      const s = cycleAt(cycle, t + offset);
      return {
        pos: (((base[s.leg] + s.dist) % loopLength) + loopLength) % loopLength,
        speed: s.speed,
        dir: 1,
        dwelling: s.dwelling,
        doors: s.doors,
        leg: s.leg,
      };
    },
  };
}
