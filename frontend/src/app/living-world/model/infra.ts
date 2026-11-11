import { CANAL_HALF_WIDTH, LOOP, PITCH, RAIL_END_X, RAIL_START_X, RAIL_WIDTH as GRAPH_RAIL_WIDTH, type CityGraph } from "./cityGraph";
import { slotAngle } from "./cityLots";
import { distToPolyline, type Pt } from "./terrain";

/**
 * Transport (pure), derived from the street graph: a monorail loop on pillars above the
 * avenue loop (pillars stand in the central reservation, never in a traffic lane), a ground
 * railway from a terminus beside the plaza out of town along its own corridor, with a level
 * crossing wherever it meets a street, and ambient traffic loops along the ring road, the
 * avenue loop and the perimeter avenue.
 */

export interface Corridor {
  /** Centre line. */
  path: Pt[];
  /** Total width kept clear of buildings. */
  clear: number;
  /** Lane offset for ambient traffic (road corridors only). */
  lane?: number;
}

export interface MonorailStation {
  x: number;
  z: number;
  angle: number;
}

export interface Pier {
  x: number;
  z: number;
  heading: number;
}

export interface LevelCrossing {
  x: number;
  z: number;
  /** Heading of the street that crosses the railway. */
  streetHeading: number;
}

export interface Infra {
  /** Traffic loops on the ground roads (the old name is kept for the renderer). */
  highways: Corridor[];
  rail: Corridor;
  /** The monorail is a closed loop; the last point returns to the first. */
  monorail: Corridor & { stations: MonorailStation[]; closed: true; piers: Pier[] };
  railTerminus: Pt;
  crossings: LevelCrossing[];
}

export const RAIL_WIDTH = GRAPH_RAIL_WIDTH;
export const MONORAIL_WIDTH = 1.6;
/** Deck height above the ground. */
export const MONORAIL_DECK = 15;

/** Closed Chaikin: rounds every corner of a closed loop (first point repeated at the end). */
function roundedLoop(corners: readonly Pt[], passes: number): Pt[] {
  let pts = [...corners];
  for (let k = 0; k < passes; k++) {
    const next: Pt[] = [];
    for (let i = 0; i < pts.length; i++) {
      const a = pts[i];
      const b = pts[(i + 1) % pts.length];
      next.push({ x: a.x * 0.75 + b.x * 0.25, z: a.z * 0.75 + b.z * 0.25 }, { x: a.x * 0.25 + b.x * 0.75, z: a.z * 0.25 + b.z * 0.75 });
    }
    pts = next;
  }
  return [...pts, { ...pts[0] }];
}

/** Corners of a square plus a point every PITCH along the sides, so rounding stays at the corners. */
const square = (r: number): Pt[] => {
  const n = Math.max(1, Math.round((2 * r) / PITCH));
  const out: Pt[] = [];
  for (let i = 0; i < n; i++) out.push({ x: -r + (2 * r * i) / n, z: -r });
  for (let i = 0; i < n; i++) out.push({ x: r, z: -r + (2 * r * i) / n });
  for (let i = 0; i < n; i++) out.push({ x: r - (2 * r * i) / n, z: r });
  for (let i = 0; i < n; i++) out.push({ x: -r, z: r - (2 * r * i) / n });
  return out;
};

export function computeInfra(graph: CityGraph, canal: readonly Pt[]): Infra {
  // --- monorail: the chain of monorail edges, in order ---------------------------------------
  const chain = graph.monorail.map((e) => graph.node(e.a));
  const corners = chain.map((n) => ({ x: n.x, z: n.z }));
  // Nodes along a side are collinear, so rounding only changes the four corners.
  const loop = roundedLoop(corners, 2);

  const crossingNodes = graph.crossings;
  const awayFromCrossings = (p: Pt, r: number) => crossingNodes.every((c) => Math.hypot(c.x - p.x, c.z - p.z) > r);
  const awayFromCanal = (p: Pt) => distToPolyline(p.x, p.z, canal) > CANAL_HALF_WIDTH + 3;

  // Stations: one at the avenue loop edge nearest to each district's compass direction. Edges
  // that cross the railway or the canal are skipped (no room for a platform).
  const usable = graph.monorail.map((e, idx) => {
    const a = graph.node(e.a);
    const b = graph.node(e.b);
    const mid = { x: (a.x + b.x) / 2, z: (a.z + b.z) / 2 };
    return { idx, a, b, mid, ok: awayFromCrossings(mid, 9) && awayFromCanal(mid) };
  });
  const taken = new Set<number>();
  const stations: MonorailStation[] = [];
  const stationEdge = new Set<number>();
  for (let slot = 0; slot < 7; slot++) {
    const ang = slotAngle(slot);
    const s = LOOP / Math.max(Math.abs(Math.cos(ang)), Math.abs(Math.sin(ang)));
    const hit = { x: Math.cos(ang) * s, z: Math.sin(ang) * s };
    const best = usable
      .filter((u) => u.ok && !taken.has(u.idx))
      .sort((p, q) => Math.hypot(p.mid.x - hit.x, p.mid.z - hit.z) - Math.hypot(q.mid.x - hit.x, q.mid.z - hit.z) || p.idx - q.idx)[0];
    if (!best) continue;
    taken.add(best.idx);
    stationEdge.add(best.idx);
    stations.push({ x: best.mid.x, z: best.mid.z, angle: Math.atan2(best.b.x - best.a.x, best.b.z - best.a.z) });
  }

  // Pillars: three candidates per edge (a quarter, the middle, three quarters), dropped where a
  // pillar would stand in the water or on a level crossing; platforms get a pillar at each end.
  const piers: Pier[] = [];
  graph.monorail.forEach((e, idx) => {
    const a = graph.node(e.a);
    const b = graph.node(e.b);
    const heading = Math.atan2(b.x - a.x, b.z - a.z);
    const at = (d: number): Pier => ({ x: a.x + ((b.x - a.x) * d) / e.length, z: a.z + ((b.z - a.z) * d) / e.length, heading });
    const offsets = stationEdge.has(idx) ? [e.length / 2 - 6.5, e.length / 2 + 6.5] : [11, e.length / 2, e.length - 11];
    for (const d of offsets) {
      const p = at(d);
      if (awayFromCrossings(p, 6) && awayFromCanal(p)) piers.push(p);
    }
  });

  // --- railway ---------------------------------------------------------------------------------
  const rail: Pt[] = [{ x: RAIL_START_X, z: 0 }, { x: RAIL_END_X, z: 0 }];
  const crossings = crossingNodes
    .filter((c) => c.x > RAIL_START_X && c.x < RAIL_END_X)
    .map((c) => ({ x: c.x, z: c.z, streetHeading: 0 }));

  // --- ambient traffic ---------------------------------------------------------------------------
  const ring = roundedLoop(square(PITCH / 2), 2);
  const perimeter = roundedLoop(square(PITCH * 4.5), 2);

  return {
    highways: [
      { path: ring, clear: 12, lane: 2.4 },
      { path: loop, clear: 14, lane: 3.2 },
      { path: perimeter, clear: 12, lane: 2.4 },
    ],
    rail: { path: rail, clear: RAIL_WIDTH + 4 },
    monorail: { path: loop, clear: 14, stations, closed: true, piers },
    railTerminus: rail[0],
    crossings,
  };
}
