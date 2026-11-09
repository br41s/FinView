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
  radius: number;
  /** Connected surface-road network: outer arterial loop and city exits. */
  highways: Corridor[];
  /** Ground railway from the industrial district to the central interchange. */
  rail: Pt[];
  railTerminus: Pt;
  /** District entrances in their clockwise urban order; SkyTrain serves each of them. */
  districtStops: Pt[];
}

function nearestPointOnPath(target: Pt, path: readonly Pt[]): { x: number; z: number; angle: number } {
  let best = { x: path[0].x, z: path[0].z, angle: 0 };
  let bestD = Infinity;
  for (let i = 1; i < path.length; i++) {
    const a = path[i - 1];
    const b = path[i];
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const len2 = dx * dx + dz * dz;
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((target.x - a.x) * dx + (target.z - a.z) * dz) / len2));
    const x = a.x + dx * t;
    const z = a.z + dz * t;
    const d = Math.hypot(target.x - x, target.z - z);
    if (d < bestD) {
      bestD = d;
      best = { x, z, angle: Math.atan2(dx, dz) };
    }
  }
  return best;
}

export function computeInfra(s: InfraSpec): Infra {
  const stops = [...s.districtStops].sort((a, b) => Math.atan2(a.z, a.x) - Math.atan2(b.z, b.x));
  const avgR = stops.length
    ? stops.reduce((acc, p) => acc + Math.hypot(p.x, p.z), 0) / stops.length
    : Math.max(MONORAIL_RADIUS, s.radius * 0.45);
  // Elegant outer perimeter loop that smoothly encircles the town
  const loopRadius = Math.max(MONORAIL_RADIUS + 10, avgR * 1.02);

  const loop: Pt[] = [];
  const STEPS = 64;
  for (let i = 0; i <= STEPS; i++) {
    const a = (i / STEPS) * Math.PI * 2;
    loop.push({ x: Math.cos(a) * loopRadius * 1.02, z: Math.sin(a) * loopRadius * 0.98 });
  }
  loop[loop.length - 1] = { ...loop[0] };

  const stations = stops.length >= 4
    ? stops.map((stop) => nearestPointOnPath(stop, loop))
    : [
        nearestPointOnPath(polar(0, loopRadius), loop),
        nearestPointOnPath(polar(Math.PI / 2, loopRadius), loop),
        nearestPointOnPath(polar(Math.PI, loopRadius), loop),
        nearestPointOnPath(polar((3 * Math.PI) / 2, loopRadius), loop),
      ];

  return {
    highways: s.highways,
    rail: { path: s.rail, clear: RAIL_WIDTH + 4 },
    monorail: {
      path: loop,
      clear: MONORAIL_WIDTH + 4,
      stations,
      closed: true,
    },
    railTerminus: s.railTerminus,
  };
}
