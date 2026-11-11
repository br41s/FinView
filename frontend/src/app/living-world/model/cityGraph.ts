import { clipHalfPlane, closestOnSegment, polyArea, polyCentroid, type V } from "./cityGeometry";

/**
 * The street skeleton of the town (pure). A planar graph on one global orthogonal grid:
 * a plaza block in the middle bounded by a ring road, avenues (one of them the monorail loop)
 * and a perimeter avenue, plain streets on every other grid line, a canal crossed by bridges and
 * a railway that meets the streets at level crossings.
 *
 * The skeleton is a function of the template constants below and of NOTHING ELSE: not of the
 * holdings, not of their number. Node ids come from integer template coordinates (never from
 * insertion order), so the same city is rebuilt bit for bit on every run. Only the assignment
 * of holdings to lots (townLayout.ts) depends on the asset ids.
 *
 * Blocks are extracted from the graph, not listed by hand: every ground edge becomes two
 * half-edges, outgoing half-edges are sorted by angle at each node, and walking `next` yields
 * the faces. Bounded faces are blocks (city blocks, the plaza, canal cells); the unbounded one is
 * the outside.
 */

/** Distance between grid lines. */
export const PITCH = 44;
/** Cells run from -GRID_N to +GRID_N on both axes (a (2N+1)^2 grid of blocks). */
export const GRID_N = 4;
/** Grid lines at half-integer multiples of PITCH. */
export const LINES: readonly number[] = Array.from({ length: 2 * GRID_N + 2 }, (_, i) => (i - GRID_N - 0.5) * PITCH);
const PERIMETER = LINES[LINES.length - 1];
/** Avenue loop (the monorail runs above it). */
export const LOOP = 110;
/** The plaza block is bounded by the ring road at this distance from the centre. */
export const RING = PITCH / 2;

/** The canal runs south along x = CANAL_X, then west along z = CANAL_Z; bridges cross it. */
export const CANAL_X = -2 * PITCH;
export const CANAL_Z = PITCH;
export const CANAL_HALF_WIDTH = 7;
/** Bridge heads stand on the banks, a little back from the water line. */
const BRIDGE_REACH = CANAL_HALF_WIDTH + 1;
/** The canal leaves the grid and runs out to the edge of the land. */
export const CANAL_RUN_OUT = 420;

/** Railway: a terminus beside the plaza, then east along z = 0 and out of town. */
export const RAIL_START_X = 33;
export const RAIL_END_X = 262;
export const RAIL_WIDTH = 2.6;
/** Half width kept clear of buildings round the railway (ballast, fences, crossings). */
export const RAIL_CLEAR_HALF = 6.5;

export type EdgeClass = "street" | "avenue" | "ring" | "bridge" | "rail" | "monorail";
export type NodeKind = "junction" | "bend" | "through" | "bridgehead" | "crossing" | "gate" | "end";

export interface GNode {
  id: string;
  x: number;
  z: number;
  kind: NodeKind;
}

export interface GEdge {
  id: string;
  a: string;
  b: string;
  class: EdgeClass;
  /** Total width, kerb to kerb across both pavements. */
  width: number;
  /** Pavement on each side. */
  walk: number;
  /** Central reservation (avenues): where the monorail pillars stand. */
  median: number;
  lanes: number;
  length: number;
}

export interface HalfEdge {
  id: string;
  from: string;
  to: string;
  edge: string;
  angle: number;
  twin: string;
  next: string;
  face: number;
}

export interface FaceEdge {
  a: V;
  b: V;
  edge: GEdge;
}

export interface Face {
  index: number;
  /** Closed ring of node ids, counter-clockwise. */
  nodes: string[];
  polygon: V[];
  edges: FaceEdge[];
  area: number;
  centroid: V;
  bounded: boolean;
}

export interface CityGraph {
  nodes: Map<string, GNode>;
  /** Every edge: ground roads, the railway and the monorail overlay. */
  edges: GEdge[];
  /** Ground roads only (street, avenue, ring, bridge). */
  roads: GEdge[];
  rail: GEdge[];
  monorail: GEdge[];
  halfEdges: Map<string, HalfEdge>;
  /** Outgoing half-edges of each node, sorted by angle. */
  adjacency: Map<string, HalfEdge[]>;
  faces: Face[];
  /** Plaza gates: the ring road's mid-edge nodes, one per side. */
  gates: GNode[];
  /** Rail crossings, with the heading of the street they cut. */
  crossings: GNode[];
  node(id: string): GNode;
}

export const nodeId = (x: number, z: number) => `n${Math.round(x * 2)}_${Math.round(z * 2)}`;

const ROAD_CLASSES: ReadonlySet<EdgeClass> = new Set(["street", "avenue", "ring", "bridge"]);
export const isRoadClass = (c: EdgeClass) => ROAD_CLASSES.has(c);

const PROFILE = {
  street: { width: 9, walk: 1.8, median: 0, lanes: 2 },
  ring: { width: 12, walk: 2, median: 0, lanes: 4 },
  loop: { width: 14, walk: 1.9, median: 2.2, lanes: 4 },
  perimeter: { width: 12, walk: 2, median: 0, lanes: 4 },
} as const;

/** Width of the carriageway (between pavements). */
export const carriage = (e: Pick<GEdge, "width" | "walk">) => e.width - 2 * e.walk;

export function buildCityGraph(): CityGraph {
  const nodes = new Map<string, GNode>();
  const kindHint = new Map<string, NodeKind>();
  const addNode = (x: number, z: number, hint?: NodeKind) => {
    const id = nodeId(x, z);
    if (!nodes.has(id)) nodes.set(id, { id, x, z, kind: "through" });
    if (hint && !kindHint.has(id)) kindHint.set(id, hint);
    return id;
  };

  // --- ground roads: every grid line, split at every extra node ---------------------------
  const edges: GEdge[] = [];
  const edgeKey = (a: string, b: string, c: string) => (a < b ? `${c}:${a}~${b}` : `${c}:${b}~${a}`);
  const addEdge = (a: string, b: string, cls: EdgeClass, p: { width: number; walk: number; median: number; lanes: number }) => {
    const na = nodes.get(a)!;
    const nb = nodes.get(b)!;
    edges.push({
      id: edgeKey(a, b, cls),
      a,
      b,
      class: cls,
      width: p.width,
      walk: p.walk,
      median: p.median,
      lanes: p.lanes,
      length: Math.hypot(nb.x - na.x, nb.z - na.z),
    });
  };

  for (const axis of ["x", "z"] as const) {
    for (const c of LINES) {
      // `along` is the coordinate that varies; `c` is fixed.
      const points = new Map<number, NodeKind | undefined>();
      for (const v of LINES) points.set(v, undefined);
      if (Math.abs(c) === RING) points.set(0, "gate");
      if (axis === "x" && c >= 3 * PITCH / 2) points.set(0, "crossing"); // x = 66, 110, 154, 198 meets the rail
      // Canal crossings: bridge heads on both banks.
      const heads: [number, number] | null =
        axis === "z" && c <= CANAL_Z
          ? [CANAL_X - BRIDGE_REACH, CANAL_X + BRIDGE_REACH]
          : axis === "x" && c <= CANAL_X
            ? [CANAL_Z - BRIDGE_REACH, CANAL_Z + BRIDGE_REACH]
            : null;
      if (heads) for (const h of heads) points.set(h, "bridgehead");
      const along = [...points.keys()].sort((p, q) => p - q);
      const at = (v: number) => (axis === "x" ? { x: c, z: v } : { x: v, z: c });
      for (const v of along) {
        const p = at(v);
        addNode(p.x, p.z, points.get(v));
      }
      for (let i = 1; i < along.length; i++) {
        const p = at(along[i - 1]);
        const q = at(along[i]);
        const mid = (along[i - 1] + along[i]) / 2;
        const a = nodeId(p.x, p.z);
        const b = nodeId(q.x, q.z);
        if (heads && along[i - 1] === heads[0] && along[i] === heads[1]) {
          addEdge(a, b, "bridge", PROFILE.street);
          continue;
        }
        const perimeter = Math.abs(c) === PERIMETER;
        const ring = Math.abs(c) === RING && Math.abs(mid) < RING;
        const loop = Math.abs(c) === LOOP && Math.abs(mid) < LOOP;
        if (perimeter) addEdge(a, b, "avenue", PROFILE.perimeter);
        else if (ring) addEdge(a, b, "ring", PROFILE.ring);
        else if (loop) addEdge(a, b, "avenue", PROFILE.loop);
        else addEdge(a, b, "street", PROFILE.street);
      }
    }
  }

  // --- railway ------------------------------------------------------------------------------
  const railXs = [RAIL_START_X, ...LINES.filter((x) => x >= 3 * PITCH / 2), RAIL_END_X];
  for (const x of railXs) addNode(x, 0, x === RAIL_START_X || x === RAIL_END_X ? "end" : "crossing");
  for (let i = 1; i < railXs.length; i++) {
    addEdge(nodeId(railXs[i - 1], 0), nodeId(railXs[i], 0), "rail", { width: RAIL_WIDTH + 1.2, walk: 0, median: 0, lanes: 1 });
  }

  // --- monorail overlay: the avenue loop, as one closed chain of edges -----------------------
  const stops = LINES.filter((v) => Math.abs(v) <= LOOP);
  const chain: Array<[number, number]> = [];
  for (const x of stops) chain.push([x, -LOOP]);
  for (const z of stops.slice(1)) chain.push([LOOP, z]);
  for (const x of [...stops].reverse().slice(1)) chain.push([x, LOOP]);
  for (const z of [...stops].reverse().slice(1, -1)) chain.push([-LOOP, z]);
  for (let i = 0; i < chain.length; i++) {
    const [ax, az] = chain[i];
    const [bx, bz] = chain[(i + 1) % chain.length];
    addEdge(nodeId(ax, az), nodeId(bx, bz), "monorail", { width: 1.6, walk: 0, median: 0, lanes: 1 });
  }

  const roads = edges.filter((e) => isRoadClass(e.class));
  const rail = edges.filter((e) => e.class === "rail");
  const monorail = edges.filter((e) => e.class === "monorail");

  // --- node kinds ---------------------------------------------------------------------------
  const incident = new Map<string, GEdge[]>();
  for (const e of roads) {
    for (const id of [e.a, e.b]) {
      const list = incident.get(id);
      if (list) list.push(e);
      else incident.set(id, [e]);
    }
  }
  const other = (e: GEdge, id: string) => nodes.get(e.a === id ? e.b : e.a)!;
  for (const n of nodes.values()) {
    const hint = kindHint.get(n.id);
    const inc = incident.get(n.id) ?? [];
    if (hint) n.kind = hint;
    else if (inc.length >= 3) n.kind = "junction";
    else if (inc.length === 2) {
      const p = other(inc[0], n.id);
      const q = other(inc[1], n.id);
      const cross = (p.x - n.x) * (q.z - n.z) - (p.z - n.z) * (q.x - n.x);
      n.kind = Math.abs(cross) > 1e-6 ? "bend" : "through";
    } else n.kind = "end";
  }

  // --- half-edges, adjacency, faces ---------------------------------------------------------
  const halfEdges = new Map<string, HalfEdge>();
  const adjacency = new Map<string, HalfEdge[]>();
  const sortedRoads = [...roads].sort((p, q) => (p.id < q.id ? -1 : 1));
  for (const e of sortedRoads) {
    const a = nodes.get(e.a)!;
    const b = nodes.get(e.b)!;
    const fwd: HalfEdge = { id: `${e.id}>`, from: e.a, to: e.b, edge: e.id, angle: Math.atan2(b.z - a.z, b.x - a.x), twin: `${e.id}<`, next: "", face: -1 };
    const bwd: HalfEdge = { id: `${e.id}<`, from: e.b, to: e.a, edge: e.id, angle: Math.atan2(a.z - b.z, a.x - b.x), twin: `${e.id}>`, next: "", face: -1 };
    halfEdges.set(fwd.id, fwd);
    halfEdges.set(bwd.id, bwd);
    for (const h of [fwd, bwd]) {
      const list = adjacency.get(h.from);
      if (list) list.push(h);
      else adjacency.set(h.from, [h]);
    }
  }
  for (const list of adjacency.values()) list.sort((p, q) => p.angle - q.angle || (p.id < q.id ? -1 : 1));
  for (const h of halfEdges.values()) {
    const around = adjacency.get(h.to)!;
    const k = around.findIndex((x) => x.id === h.twin);
    h.next = around[(k - 1 + around.length) % around.length].id;
  }

  const edgeById = new Map(edges.map((e) => [e.id, e]));
  const faces: Face[] = [];
  for (const start of [...halfEdges.values()].sort((p, q) => (p.id < q.id ? -1 : 1))) {
    if (start.face >= 0) continue;
    const index = faces.length;
    const ring: HalfEdge[] = [];
    let h = start;
    for (let guard = 0; guard < halfEdges.size + 2; guard++) {
      h.face = index;
      ring.push(h);
      h = halfEdges.get(h.next)!;
      if (h === start) break;
    }
    const polygon = ring.map((x) => ({ x: nodes.get(x.from)!.x, z: nodes.get(x.from)!.z }));
    const area = polyArea(polygon);
    faces.push({
      index,
      nodes: ring.map((x) => x.from),
      polygon,
      edges: ring.map((x) => ({
        a: { x: nodes.get(x.from)!.x, z: nodes.get(x.from)!.z },
        b: { x: nodes.get(x.to)!.x, z: nodes.get(x.to)!.z },
        edge: edgeById.get(x.edge)!,
      })),
      area,
      centroid: polyCentroid(polygon),
      bounded: area > 1e-6,
    });
  }

  const gates = [...nodes.values()].filter((n) => n.kind === "gate").sort((p, q) => (p.id < q.id ? -1 : 1));
  const crossings = [...nodes.values()]
    .filter((n) => n.kind === "crossing" && n.z === 0)
    .sort((p, q) => p.x - q.x);

  return {
    nodes,
    edges,
    roads,
    rail,
    monorail,
    halfEdges,
    adjacency,
    faces,
    gates,
    crossings,
    node: (id) => nodes.get(id)!,
  };
}

let cached: CityGraph | null = null;
/** The skeleton never changes, so it is built once. */
export function getCityGraph(): CityGraph {
  return (cached ??= buildCityGraph());
}

// --- routing ---------------------------------------------------------------------------------

/** Radius at which a route reaches the paved plaza, short of the plaza edge (16). */
const PLAZA_STOP = 14.5;

/**
 * Shortest way along the ground roads from a point on `edgeId` to the nearest plaza gate, then
 * a few steps onto the plaza. The point joins the edge's two end nodes, so the route may leave
 * either way. Pure Dijkstra: ties break on node id, so the route never depends on map order.
 */
export function routeToGate(graph: CityGraph, front: V, edgeId: string): V[] {
  const edge = graph.edges.find((e) => e.id === edgeId);
  if (!edge) return [front];
  const dist = new Map<string, number>();
  const prev = new Map<string, string | null>();
  const open = new Set<string>();
  for (const id of [edge.a, edge.b]) {
    const n = graph.node(id);
    dist.set(id, Math.hypot(n.x - front.x, n.z - front.z));
    prev.set(id, null);
    open.add(id);
  }
  const roadIds = new Set(graph.roads.map((e) => e.id));
  const gateIds = new Set(graph.gates.map((g) => g.id));
  let goal: string | null = null;
  while (open.size > 0) {
    let best: string | null = null;
    for (const id of open) {
      if (best === null || dist.get(id)! < dist.get(best)! || (dist.get(id)! === dist.get(best)! && id < best)) best = id;
    }
    open.delete(best!);
    if (gateIds.has(best!)) {
      goal = best!;
      break;
    }
    for (const h of graph.adjacency.get(best!) ?? []) {
      if (!roadIds.has(h.edge)) continue;
      const e = graph.edges.find((x) => x.id === h.edge)!;
      const d = dist.get(best!)! + e.length;
      if (d < (dist.get(h.to) ?? Infinity) - 1e-9) {
        dist.set(h.to, d);
        prev.set(h.to, best!);
        open.add(h.to);
      }
    }
  }
  if (!goal) return [front];
  const chain: V[] = [];
  for (let id: string | null = goal; id; id = prev.get(id) ?? null) {
    const n = graph.node(id);
    chain.push({ x: n.x, z: n.z });
  }
  chain.reverse();
  const g = graph.node(goal);
  const len = Math.hypot(g.x, g.z) || 1;
  const end = { x: (g.x / len) * PLAZA_STOP, z: (g.z / len) * PLAZA_STOP };
  return [front, ...chain, end];
}

/** The point of `edge` nearest to p (on its centre line). */
export function nearestOnEdge(graph: CityGraph, edge: GEdge, p: V): V {
  const a = graph.node(edge.a);
  const b = graph.node(edge.b);
  const c = closestOnSegment(p, a, b);
  return { x: c.x, z: c.z };
}

/** Convex block polygon shrunk by each bounding edge's half width. */
export function insetFace(face: Face): V[] {
  let poly = face.polygon;
  for (const fe of face.edges) {
    const dx = fe.b.x - fe.a.x;
    const dz = fe.b.z - fe.a.z;
    const l = Math.hypot(dx, dz) || 1;
    // Interior is on the left of a counter-clockwise edge: left normal = (-dz, dx).
    const nx = -dz / l;
    const nz = dx / l;
    const keepInside = fe.a.x * nx + fe.a.z * nz + fe.edge.width / 2;
    poly = clipHalfPlane(poly, -nx, -nz, -keepInside);
  }
  return poly;
}
