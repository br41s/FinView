import { chaikin, type Pt } from "./terrain";

/**
 * Transport (pure): an elevated expressway ring round the town, an elevated expressway that
 * hugs the square on the south side, a surface railway into a terminus beside the square,
 * and a monorail loop on pillars circling it. They run along the corridors between
 * districts, so they never need a building to move.
 */

export interface Corridor {
  /** Centre line. */
  path: Pt[];
  /** Total width kept clear of buildings. */
  clear: number;
}

export interface MonorailStation {
  x: number;
  z: number;
  angle: number;
}

export interface Infra {
  highways: Corridor[];
  rail: Corridor;
  /** The monorail is a closed loop; the last point returns to the first. */
  monorail: Corridor & { stations: MonorailStation[]; closed: true };
  railTerminus: Pt;
}

export const HIGHWAY_WIDTH = 6;
export const RAIL_WIDTH = 2.6;
export const MONORAIL_WIDTH = 1.6;
export const MONORAIL_RADIUS = 34;
/** Deck heights above sea level (the highway rises where the ground does). */
export const HIGHWAY_DECK = 8;
export const MONORAIL_DECK = 15;

const polar = (a: number, r: number): Pt => ({ x: Math.cos(a) * r, z: Math.sin(a) * r });

export interface InfraSpec {
  plaza: number;
  /** Radius of the outer town; the ring road runs just beyond it. */
  radius: number;
  /** Angle of the middle of each gap between compass slots k and k+1. */
  gap: (k: number) => number;
  /** The plateau sector, in unwrapped angles (start < end). */
  plateauStart: number;
  plateauEnd: number;
}

export function computeInfra(s: InfraSpec): Infra {
  const rh = s.radius + 7;

  // Ring road: everywhere except the plateau side.
  const a0 = s.plateauEnd + 0.12;
  const a1 = s.plateauStart + 2 * Math.PI - 0.12;
  const ring: Pt[] = [];
  const n = Math.max(8, Math.round(((a1 - a0) * rh) / 14));
  for (let i = 0; i <= n; i++) {
    const a = a0 + ((a1 - a0) * i) / n;
    ring.push(polar(a, rh + Math.sin(i * 0.7) * 2.2));
  }

  // The south expressway: out along the 2|3 gap, round the square at r = 24, out along the 4|5 gap.
  const g1 = s.gap(2);
  let g2 = s.gap(4);
  if (g2 < g1) g2 += 2 * Math.PI;
  const ru = s.plaza + 8;
  const u: Pt[] = [polar(g1, rh), polar(g1, ru + 16)];
  const m = 8;
  for (let i = 0; i <= m; i++) u.push(polar(g1 + ((g2 - g1) * i) / m, ru));
  u.push(polar(g2, ru + 16), polar(g2, rh));

  // Railway: along the 3|4 gap from the coast to a terminus beside the square.
  const gr = s.gap(3);
  const terminus = polar(gr, s.plaza + 7);
  const rail: Pt[] = [polar(gr, s.radius + 16), polar(gr, s.plaza + 8)];

  // Monorail: a loop round the square with four stations.
  const loop: Pt[] = [];
  const steps = 36;
  for (let i = 0; i < steps; i++) loop.push(polar((i / steps) * 2 * Math.PI + 0.35, MONORAIL_RADIUS));
  loop.push(loop[0]);
  const stations: MonorailStation[] = [0, 1, 2, 3].map((k) => {
    const angle = 0.35 + (k * Math.PI) / 2 + Math.PI / 4;
    return { ...polar(angle, MONORAIL_RADIUS), angle };
  });

  return {
    highways: [
      { path: chaikin(ring, 1), clear: HIGHWAY_WIDTH + 4 },
      { path: chaikin(u, 2), clear: HIGHWAY_WIDTH + 2 },
    ],
    rail: { path: rail, clear: RAIL_WIDTH + 4 },
    monorail: { path: loop, clear: MONORAIL_WIDTH + 3, stations, closed: true },
    railTerminus: terminus,
  };
}
