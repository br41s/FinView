import type { V } from "./cityGeometry";
import { carriage, type CityGraph, type GEdge, type GNode, type HalfEdge } from "./cityGraph";
import { hashString, seeded } from "./rng";

/**
 * Road traffic (pure). Two layers:
 *
 * 1. `buildLaneNetwork(graph)`: right-hand lanes cut from the street graph. Every road edge has
 *    `lanes / 2` lanes per direction, offset from the centre line (and clear of an avenue's
 *    median); each lane is a `Piece` trimmed back to the junction mouth. Inside a junction every
 *    legal movement is a short curve (`turn` piece) from one lane to another, and two turns that
 *    come within a vehicle's width of each other (or end in the same lane) are recorded as
 *    conflicting.
 * 2. `TrafficSim`: a fixed-step simulation of vehicles on that network. Each one follows its
 *    leader with the Intelligent Driver Model, stops at a stop line while its way is red or its
 *    junction exit is full, and may only enter a junction when no conflicting movement is already
 *    inside it. Signals alternate by axis (with an all-red gap); the conflict rule is the safety
 *    net behind them, so two vehicles can never be inside the same patch of asphalt, whatever the
 *    phases do. Level crossings hold traffic at a stop line while a train is due.
 *
 * Everything is a deterministic function of the seed and the number of steps: no Math.random, no
 * wall clock. The renderer only reads poses.
 */

// --- tuning ----------------------------------------------------------------------------------

/** Asphalt of a junction mouth starts this far past the crossing road's carriageway (kerb fillet). */
const FILLET = 3;
/** Stop line distance before a lane's end: short of the zebra that sits at the mouth. */
export const STOP_BACK = 2.8;
/** Stop line before a level crossing, measured from the crossing node (barriers stand at 3.6). */
export const CROSSING_STOP = 5.4;
/** Two junction movements closer than this conflict (vehicle width plus margin). */
const CONFLICT_DIST = 1.9;
/** Movements that cross or turn sweep more than their centre line (long vehicles swing wide). */
const CONFLICT_DIST_SWEEP = 3.3;
export const FIXED_DT = 1 / 30;
const MAX_STEPS_PER_FRAME = 4;

export const SIGNAL = { green: 8, allRed: 1.5 } as const;
const SIGNAL_CYCLE = 2 * (SIGNAL.green + SIGNAL.allRed);

const IDM = { accel: 2.6, brake: 3.4, headway: 0.9, minGap: 1.0 } as const;

export type VehicleKind = "sedan" | "hatch" | "taxi" | "van" | "truck" | "bus";

/** Drawn size is the model's (about 2.4 long for a sedan) times `scale`: toy cars are chunky next to the lanes. */
export const VEHICLE_SPEC: Record<VehicleKind, { length: number; width: number; speed: number; weight: number; scale: number }> = {
  sedan: { length: 2.4 * 1.35, width: 1.05 * 1.35, speed: 1, weight: 34, scale: 1.35 },
  hatch: { length: 2.1 * 1.35, width: 1.05 * 1.35, speed: 1, weight: 28, scale: 1.35 },
  taxi: { length: 2.4 * 1.35, width: 1.05 * 1.35, speed: 1.05, weight: 10, scale: 1.35 },
  van: { length: 2.7 * 1.3, width: 1.15 * 1.3, speed: 0.92, weight: 11, scale: 1.3 },
  truck: { length: 3.7 * 1.25, width: 1.25 * 1.25, speed: 0.85, weight: 7, scale: 1.25 },
  bus: { length: 5.6 * 1.2, width: 1.35 * 1.2, speed: 0.8, weight: 10, scale: 1.2 },
};
export const VEHICLE_KINDS = Object.keys(VEHICLE_SPEC) as VehicleKind[];

const LANE_SPEED: Record<string, number> = { street: 6.5, ring: 8, avenue: 9.5, bridge: 6, rail: 6, monorail: 6 };

// --- network ---------------------------------------------------------------------------------

export type Control = "none" | "signal" | "crossing";
export type Movement = "L" | "S" | "R";

export interface Piece {
  id: number;
  kind: "lane" | "turn";
  pts: V[];
  cum: number[];
  length: number;
  /** Lane: half-edge id and lane index (0 = next to the median, last = next to the kerb). */
  half: string;
  lane: number;
  lanesOnHalf: number;
  /** Lane: the node it ends at; turn: the node it crosses. */
  node: string;
  limit: number;
  /** Lane: what holds traffic at its end, and where (distance along the piece). */
  control: Control;
  stopAt: number;
  /** 0 when the lane runs mostly along x, 1 along z (signals alternate by axis). */
  axis: 0 | 1;
  /** Lane: the movements that leave it. Turn: `[]`. */
  turns: Piece[];
  /** Turn: the lane it leaves, the lane it joins, its movement. */
  from: Piece | null;
  to: Piece | null;
  movement: Movement;
  /** Turn: other movements at the same node it must not share asphalt with, and those that
   *  leave the same lane (they overlap only at their start; followers handle that). */
  conflicts: Set<number>;
  siblings: Piece[];
}

export interface LaneNetwork {
  graph: CityGraph;
  pieces: Piece[];
  lanes: Piece[];
  turns: Piece[];
  lanesOf: Map<string, Piece[]>;
  /** Node id -> signal phase offset. */
  signalOffset: Map<string, number>;
}

export function sampleAt(p: Pick<Piece, "pts" | "cum" | "length">, s: number): { x: number; z: number; heading: number } {
  const pts = p.pts;
  const last = pts.length - 1;
  if (p.length <= 1e-9 || s <= 0) {
    const a = pts[0];
    const b = pts[Math.min(1, last)];
    return { x: a.x, z: a.z, heading: Math.atan2(b.x - a.x, b.z - a.z) };
  }
  if (s >= p.length) {
    const a = pts[Math.max(0, last - 1)];
    const b = pts[last];
    return { x: b.x, z: b.z, heading: Math.atan2(b.x - a.x, b.z - a.z) };
  }
  let i = 1;
  while (i < last && p.cum[i] < s) i++;
  const a = pts[i - 1];
  const b = pts[i];
  const seg = p.cum[i] - p.cum[i - 1] || 1;
  const t = (s - p.cum[i - 1]) / seg;
  return { x: a.x + (b.x - a.x) * t, z: a.z + (b.z - a.z) * t, heading: Math.atan2(b.x - a.x, b.z - a.z) };
}

function finish(pts: V[]): { pts: V[]; cum: number[]; length: number } {
  const cum = [0];
  for (let i = 1; i < pts.length; i++) cum.push(cum[i - 1] + Math.hypot(pts[i].x - pts[i - 1].x, pts[i].z - pts[i - 1].z));
  return { pts, cum, length: cum[cum.length - 1] };
}

function segDist(a: V, b: V, c: V, d: V): number {
  // Minimum distance between segments ab and cd (planar).
  const r = { x: b.x - a.x, z: b.z - a.z };
  const s = { x: d.x - c.x, z: d.z - c.z };
  const den = r.x * s.z - r.z * s.x;
  if (Math.abs(den) > 1e-9) {
    const t = ((c.x - a.x) * s.z - (c.z - a.z) * s.x) / den;
    const u = ((c.x - a.x) * r.z - (c.z - a.z) * r.x) / den;
    if (t >= 0 && t <= 1 && u >= 0 && u <= 1) return 0;
  }
  const pd = (p: V, q: V, w: V) => {
    const dx = w.x - q.x;
    const dz = w.z - q.z;
    const l2 = dx * dx + dz * dz;
    const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((p.x - q.x) * dx + (p.z - q.z) * dz) / l2));
    return Math.hypot(p.x - (q.x + dx * t), p.z - (q.z + dz * t));
  };
  return Math.min(pd(a, c, d), pd(b, c, d), pd(c, a, b), pd(d, a, b));
}

function polylineDist(a: readonly V[], b: readonly V[]): number {
  let best = Infinity;
  for (let i = 1; i < a.length; i++) for (let j = 1; j < b.length; j++) best = Math.min(best, segDist(a[i - 1], a[i], b[j - 1], b[j]));
  return best;
}

function bezier(p0: V, d0: V, p3: V, d1: V, n: number): V[] {
  const chord = Math.hypot(p3.x - p0.x, p3.z - p0.z);
  const k = chord * 0.4;
  const p1 = { x: p0.x + d0.x * k, z: p0.z + d0.z * k };
  const p2 = { x: p3.x - d1.x * k, z: p3.z - d1.z * k };
  const out: V[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const u = 1 - t;
    const a = u * u * u;
    const b = 3 * u * u * t;
    const c = 3 * u * t * t;
    const d = t * t * t;
    out.push({ x: a * p0.x + b * p1.x + c * p2.x + d * p3.x, z: a * p0.z + b * p1.z + c * p2.z + d * p3.z });
  }
  return out;
}

/** How far back from a node a lane stops: the asphalt of the junction mouth. */
function armClear(graph: CityGraph, edgeOf: (h: HalfEdge) => GEdge, node: GNode, arm: HalfEdge): number {
  if (node.kind !== "junction" && node.kind !== "bend") return 0;
  const arms = graph.adjacency.get(node.id)!;
  const n = arms.length;
  const i = arms.indexOf(arm);
  let best = 0;
  for (const j of [(i + 1) % n, (i - 1 + n) % n]) {
    if (j === i) continue;
    const o = arms[j];
    if (Math.abs(Math.cos(arm.angle - o.angle)) < 0.2) best = Math.max(best, carriage(edgeOf(o)) / 2 + FILLET);
  }
  return best;
}

export function buildLaneNetwork(graph: CityGraph): LaneNetwork {
  const edgeById = new Map(graph.edges.map((e) => [e.id, e]));
  const edgeOf = (h: HalfEdge) => edgeById.get(h.edge)!;
  const pieces: Piece[] = [];
  const lanes: Piece[] = [];
  const turns: Piece[] = [];
  const lanesOf = new Map<string, Piece[]>();

  const blank = (kind: Piece["kind"], pts: V[]): Piece => {
    const p: Piece = {
      id: pieces.length, kind, ...finish(pts), half: "", lane: 0, lanesOnHalf: 1, node: "", limit: 6, control: "none",
      stopAt: Infinity, axis: 0, turns: [], from: null, to: null, movement: "S", conflicts: new Set(), siblings: [],
    };
    pieces.push(p);
    return p;
  };

  // --- lanes -------------------------------------------------------------------------------
  const halves = [...graph.halfEdges.values()].sort((p, q) => (p.id < q.id ? -1 : 1));
  for (const h of halves) {
    const e = edgeOf(h);
    const a = graph.node(h.from);
    const b = graph.node(h.to);
    const dx = (b.x - a.x) / e.length;
    const dz = (b.z - a.z) / e.length;
    const rx = -dz;
    const rz = dx;
    const clearA = armClear(graph, edgeOf, a, h);
    const clearB = armClear(graph, edgeOf, b, graph.halfEdges.get(h.twin)!);
    const per = Math.max(1, Math.floor(e.lanes / 2));
    const laneW = (carriage(e) / 2 - e.median / 2) / per;
    const list: Piece[] = [];
    for (let k = 0; k < per; k++) {
      const off = e.median / 2 + (k + 0.5) * laneW;
      const start = { x: a.x + dx * clearA + rx * off, z: a.z + dz * clearA + rz * off };
      const end = { x: b.x - dx * clearB + rx * off, z: b.z - dz * clearB + rz * off };
      const lane = blank("lane", [start, end]);
      lane.half = h.id;
      lane.lane = k;
      lane.lanesOnHalf = per;
      lane.node = b.id;
      lane.limit = LANE_SPEED[e.class] ?? 6;
      lane.axis = Math.abs(dx) > Math.abs(dz) ? 0 : 1;
      if (b.kind === "crossing") {
        lane.control = "crossing";
        lane.stopAt = lane.length - CROSSING_STOP;
      }
      list.push(lane);
      lanes.push(lane);
    }
    lanesOf.set(h.id, list);
  }

  // --- junction movements ---------------------------------------------------------------------
  for (const node of [...graph.nodes.values()].sort((p, q) => (p.id < q.id ? -1 : 1))) {
    const arms = graph.adjacency.get(node.id) ?? [];
    if (arms.length < 2) continue;
    const here: Piece[] = [];
    for (const out of arms) {
      for (const outer of arms) {
        const inc = graph.halfEdges.get(outer.twin)!; // arrives at the node along `outer`'s edge
        if (outer === out || inc.from === out.to) continue; // no U-turns
        const din = { x: Math.cos(inc.angle), z: Math.sin(inc.angle) };
        const dout = { x: Math.cos(out.angle), z: Math.sin(out.angle) };
        const cross = din.x * dout.z - din.z * dout.x;
        const dot = din.x * dout.x + din.z * dout.z;
        const movement: Movement = Math.abs(cross) < 0.3 && dot > 0 ? "S" : cross > 0 ? "R" : "L";
        const ins = lanesOf.get(inc.id) ?? [];
        const outs = lanesOf.get(out.id) ?? [];
        for (const li of ins) {
          const ko = movement === "L" ? 0 : movement === "R" ? outs.length - 1 : Math.min(li.lane, outs.length - 1);
          const lo = outs[ko];
          const p0 = li.pts[1];
          const p3 = lo.pts[0];
          const gap = Math.hypot(p3.x - p0.x, p3.z - p0.z);
          const pts = gap < 0.05 ? [p0, p3] : movement === "S" && Math.abs((p3.x - p0.x) * din.z - (p3.z - p0.z) * din.x) < 0.05 ? [p0, p3] : bezier(p0, din, p3, dout, movement === "S" ? 6 : 8);
          const t = blank("turn", pts);
          t.node = node.id;
          t.from = li;
          t.to = lo;
          t.movement = movement;
          t.limit = Math.min(li.limit, lo.limit, movement === "S" ? 99 : 5);
          t.half = li.half;
          t.lane = li.lane;
          li.turns.push(t);
          here.push(t);
          turns.push(t);
        }
      }
    }
    for (let i = 0; i < here.length; i++) {
      for (let j = i + 1; j < here.length; j++) {
        const a = here[i];
        const b = here[j];
        if (a.from === b.from) {
          a.siblings.push(b);
          b.siblings.push(a);
          continue;
        }
        const da = { x: a.from!.pts[1].x - a.from!.pts[0].x, z: a.from!.pts[1].z - a.from!.pts[0].z };
        const db = { x: b.from!.pts[1].x - b.from!.pts[0].x, z: b.from!.pts[1].z - b.from!.pts[0].z };
        const la = Math.hypot(da.x, da.z) || 1;
        const lb = Math.hypot(db.x, db.z) || 1;
        const parallel = a.movement === "S" && b.movement === "S" && Math.abs(da.x * db.x + da.z * db.z) / (la * lb) > 0.9;
        if (a.to === b.to || polylineDist(a.pts, b.pts) < (parallel ? CONFLICT_DIST : CONFLICT_DIST_SWEEP)) {
          a.conflicts.add(b.id);
          b.conflicts.add(a.id);
        }
      }
    }
  }

  // Any node where two movements can meet gets a signal (and the conflict rule behind it).
  const contested = new Set<string>();
  for (const t of turns) if (t.conflicts.size > 0) contested.add(t.node);
  const signalOffset = new Map<string, number>();
  for (const l of lanes) {
    if (l.control === "none" && contested.has(l.node)) {
      l.control = "signal";
      l.stopAt = l.length - STOP_BACK;
    }
  }
  for (const id of contested) signalOffset.set(id, (hashString(id) % Math.floor(SIGNAL_CYCLE * 10)) / 10);
  return { graph, pieces, lanes, turns, lanesOf, signalOffset };
}

let cachedNet: LaneNetwork | null = null;
export function getLaneNetwork(graph: CityGraph): LaneNetwork {
  if (!cachedNet || cachedNet.graph !== graph) cachedNet = buildLaneNetwork(graph);
  return cachedNet;
}

// --- signals ---------------------------------------------------------------------------------

/** Is the x axis (0) or the z axis (1) green at this node and time? Between phases both are red. */
export function signalGreen(net: LaneNetwork, nodeId: string, axis: 0 | 1, t: number, lead = 0): boolean {
  const c = (((t + (net.signalOffset.get(nodeId) ?? 0)) % SIGNAL_CYCLE) + SIGNAL_CYCLE) % SIGNAL_CYCLE;
  const start = axis === 0 ? 0 : SIGNAL.green + SIGNAL.allRed;
  const rel = c - start;
  return rel >= 0 && rel + lead < SIGNAL.green;
}

/** Green, amber (last 1.2 s of green) or red, for drawing lamps. */
export function signalColour(net: LaneNetwork, nodeId: string, axis: 0 | 1, t: number): "green" | "amber" | "red" {
  if (!signalGreen(net, nodeId, axis, t)) return "red";
  return signalGreen(net, nodeId, axis, t, 1.2) ? "green" : "amber";
}

// --- simulation -------------------------------------------------------------------------------

export interface Vehicle {
  id: number;
  kind: VehicleKind;
  length: number;
  width: number;
  /** Index into the renderer's palette. */
  colour: number;
  piece: Piece;
  trail: Piece[];
  /** Front bumper, distance along `piece`. */
  s: number;
  v: number;
  v0: number;
  /** The movement chosen for the end of the current lane. */
  next: Piece | null;
  /** Junction movement this vehicle has been granted (held until its rear leaves it). */
  holds: Piece[];
  waitT: number;
  stuckT: number;
  age: number;
  leaving: boolean;
  /** Render scale 0..1: grows after spawning, shrinks before removal. */
  scale: number;
  braking: boolean;
  x: number;
  z: number;
  heading: number;
  rnd: () => number;
}

export interface External {
  x: number;
  z: number;
  /** Heading as (sin, cos) of the yaw. */
  heading: number;
  length: number;
  speed: number;
}

export interface TrafficOptions {
  seed?: number;
  /** Is the level crossing at this node closed (a train is due or passing)? */
  crossingClosed?: (node: GNode) => boolean;
  /** Replaces the real signals (tests). */
  signal?: (nodeId: string, axis: 0 | 1, t: number) => boolean;
}

export class TrafficSim {
  readonly vehicles: Vehicle[] = [];
  time = 0;
  private nextId = 1;
  /** null = nobody manages the population (tests place vehicles by hand). */
  private target: number | null = null;
  private acc = 0;
  private spawnCool = 0;
  private rnd: () => number;
  private occupants = new Map<number, Vehicle[]>();
  private boxes = new Map<string, Vehicle[]>();
  private waiters = new Map<string, Vehicle[]>();
  private externals: External[] = [];
  private weights: number[];
  private spawnable: Piece[];
  private spawnTotal: number;

  constructor(readonly net: LaneNetwork, private opts: TrafficOptions = {}) {
    this.rnd = seeded(opts.seed ?? 1);
    this.weights = VEHICLE_KINDS.map((k) => VEHICLE_SPEC[k].weight);
    this.spawnable = net.lanes.filter((l) => l.length > 14);
    this.spawnTotal = this.spawnable.reduce((s, l) => s + l.length, 0);
  }

  get count(): number {
    return this.vehicles.length;
  }

  /** Vehicles that count towards the target (not on their way out). */
  get active(): number {
    let n = 0;
    for (const v of this.vehicles) if (!v.leaving) n++;
    return n;
  }

  setTarget(n: number) {
    this.target = Math.max(0, Math.floor(n));
  }

  setExternals(list: readonly External[]) {
    this.externals = list.slice();
  }

  /** Put a vehicle on a lane piece (null when the spot is not free). */
  spawn(piece: Piece, s: number, kind: VehicleKind, speed = 0, colour?: number, margin = 1.5): Vehicle | null {
    const spec = VEHICLE_SPEC[kind];
    if (s < spec.length + 0.5) s = spec.length + 0.5;
    for (const o of this.vehiclesOn(piece)) {
      if (Math.abs(o.s - s) < Math.max(o.length, spec.length) + margin) return null;
    }
    const rnd = seeded(hashString(`veh:${this.nextId}:${piece.id}`));
    const v: Vehicle = {
      id: this.nextId++, kind, length: spec.length, width: spec.width,
      colour: colour ?? Math.floor(this.rnd() * 1000),
      piece, trail: [], s, v: speed,
      v0: piece.limit * spec.speed * (0.82 + 0.3 * rnd()),
      next: null, holds: [], waitT: 0, stuckT: 0, age: 0, leaving: false, scale: 0, braking: false,
      x: 0, z: 0, heading: 0, rnd,
    };
    v.next = this.choose(v);
    this.vehicles.push(v);
    this.pose(v);
    return v;
  }

  private vehiclesOn(piece: Piece): Vehicle[] {
    const out: Vehicle[] = [];
    for (const v of this.vehicles) if (v.piece === piece) out.push(v);
    return out;
  }

  private pickKind(): VehicleKind {
    const total = this.weights.reduce((a, b) => a + b, 0);
    let r = this.rnd() * total;
    for (let i = 0; i < VEHICLE_KINDS.length; i++) {
      r -= this.weights[i];
      if (r <= 0) return VEHICLE_KINDS[i];
    }
    return "sedan";
  }

  private spawnRandom(): boolean {
    for (let attempt = 0; attempt < 6; attempt++) {
      let r = this.rnd() * this.spawnTotal;
      let lane = this.spawnable[0];
      for (const l of this.spawnable) {
        r -= l.length;
        if (r <= 0) {
          lane = l;
          break;
        }
      }
      const kind = this.pickKind();
      const spec = VEHICLE_SPEC[kind];
      const hi = Math.min(lane.length - 1, lane.stopAt - 1);
      const lo = spec.length + 1;
      if (hi <= lo) continue;
      const s = lo + this.rnd() * (hi - lo);
      if (this.spawn(lane, s, kind, lane.limit * 0.6, undefined, 6)) return true;
    }
    return false;
  }

  /** Fill the road to `n` vehicles at once (a fresh town starts populated). */
  warm(n: number) {
    this.target = n;
    for (let i = 0; i < n * 3 && this.active < n; i++) {
      if (this.spawnRandom()) this.vehicles[this.vehicles.length - 1].scale = 1;
    }
  }

  /** Pick the movement for the end of the current lane. */
  private choose(v: Vehicle): Piece | null {
    const opts = v.piece.kind === "lane" ? v.piece.turns : [];
    if (opts.length === 0) return null;
    const w = opts.map((t) => {
      let k = t.movement === "S" ? 0.62 : t.movement === "R" ? 0.22 : 0.16;
      const n = t.from!.lanesOnHalf;
      if (n > 1 && t.movement === "L" && t.from!.lane > 0) k *= 0.25;
      if (n > 1 && t.movement === "R" && t.from!.lane < n - 1) k *= 0.25;
      return k;
    });
    const total = w.reduce((a, b) => a + b, 0);
    let r = v.rnd() * total;
    for (let i = 0; i < opts.length; i++) {
      r -= w[i];
      if (r <= 0) return opts[i];
    }
    return opts[opts.length - 1];
  }

  /** Advance by `seconds` of real time (fixed internal steps, bounded per call). */
  advance(seconds: number) {
    this.acc += Math.min(seconds, MAX_STEPS_PER_FRAME * FIXED_DT);
    let n = 0;
    while (this.acc >= FIXED_DT && n < MAX_STEPS_PER_FRAME) {
      this.step(FIXED_DT);
      this.acc -= FIXED_DT;
      n++;
    }
    if (this.acc > FIXED_DT) this.acc = 0;
  }

  /** Distance to the nearest vehicle ahead of (x, z) within `range` and `half` either side. */
  gapAhead(x: number, z: number, heading: number, range: number, half: number, ignore?: Vehicle): number {
    const hx = Math.sin(heading);
    const hz = Math.cos(heading);
    let best = Infinity;
    for (const o of this.vehicles) {
      if (o === ignore) continue;
      const rx = o.x - x;
      const rz = o.z - z;
      const ahead = rx * hx + rz * hz;
      const side = Math.abs(rx * -hz + rz * hx);
      if (ahead > 0 && ahead < range + o.length && side < half + o.width / 2) best = Math.min(best, ahead - o.length / 2);
    }
    return best;
  }

  private pose(v: Vehicle) {
    const f = sampleAt(v.piece, v.s);
    let back = v.s - v.length;
    let piece = v.piece;
    let i = 0;
    while (back < 0 && i < v.trail.length) {
      piece = v.trail[i++];
      back += piece.length;
    }
    const r = sampleAt(piece, Math.max(0, back));
    v.x = (f.x + r.x) / 2;
    v.z = (f.z + r.z) / 2;
    const dx = f.x - r.x;
    const dz = f.z - r.z;
    v.heading = dx * dx + dz * dz > 0.04 ? Math.atan2(dx, dz) : f.heading;
  }

  private list(p: Piece): Vehicle[] {
    return this.occupants.get(p.id) ?? [];
  }

  /** Free length at the start of `lane`, minus what vehicles already granted entry will need. */
  private roomAt(lane: Piece, me: Vehicle): number {
    let free = lane.length;
    for (const o of this.list(lane)) free = Math.min(free, o.s - o.length);
    for (const users of this.boxes.values()) {
      for (const u of users) if (u !== me && u.piece !== lane && u.holds.some((h) => h.to === lane)) free -= u.length + 1;
    }
    return free;
  }

  private canEnter(v: Vehicle, line: Piece): boolean {
    const next = v.next!;
    if (line.control === "crossing") {
      const node = this.net.graph.node(line.node);
      return !(this.opts.crossingClosed?.(node) ?? false);
    }
    const green = this.opts.signal
      ? this.opts.signal(line.node, line.axis, this.time)
      : signalGreen(this.net, line.node, line.axis, this.time, 0.7);
    if (!green) return false;
    if (this.roomAt(next.to!, v) < v.length + 1.0) return false;
    for (const u of this.boxes.get(line.node) ?? []) if (u !== v && u.holds.some((h) => next.conflicts.has(h.id))) return false;
    // A movement that has waited longer, and is on green, goes first.
    for (const w of this.waiters.get(line.node) ?? []) {
      if (w === v || !w.next || !next.conflicts.has(w.next.id)) continue;
      if (w.waitT > v.waitT || (w.waitT === v.waitT && w.id < v.id)) return false;
    }
    return true;
  }

  private step(dt: number) {
    this.time += dt;
    this.spawnCool -= dt;

    // Index who is where.
    this.occupants.clear();
    this.boxes.clear();
    this.waiters.clear();
    for (const v of this.vehicles) {
      const l = this.occupants.get(v.piece.id);
      if (l) l.push(v);
      else this.occupants.set(v.piece.id, [v]);
      for (const h of v.holds) {
        const b = this.boxes.get(h.node);
        if (b) {
          if (!b.includes(v)) b.push(v);
        } else this.boxes.set(h.node, [v]);
      }
      if (v.waitT > 0 && !v.holds.some((h) => h.from === v.piece) && v.next && v.piece.control === "signal") {
        const w = this.waiters.get(v.piece.node);
        if (w) w.push(v);
        else this.waiters.set(v.piece.node, [v]);
      }
    }

    // Spawn / despawn towards the target density.
    const active = this.active;
    if (this.target === null) {
      // unmanaged
    } else if (active < this.target && this.spawnCool <= 0) {
      if (this.spawnRandom()) this.spawnCool = 0.12;
    } else if (active > this.target) {
      let pick: Vehicle | null = null;
      for (const v of this.vehicles) if (!v.leaving && (!pick || v.id > pick.id)) pick = v;
      if (pick) pick.leaving = true;
    }

    // Accelerations from the state at the start of the step.
    const acc = new Map<Vehicle, number>();
    const cap = new Map<Vehicle, number>();
    const order = [...this.vehicles].sort((a, b) => b.waitT - a.waitT || a.id - b.id);
    for (const v of order) {
      let gap = Infinity;
      let vl = 0;
      const consider = (g: number, speed: number) => {
        if (g < gap) {
          gap = g;
          vl = speed;
        }
      };
      for (const o of this.list(v.piece)) if (o !== v && (o.s > v.s || (o.s === v.s && o.id > v.id))) consider(o.s - o.length - v.s, o.v);
      if (v.piece.kind === "turn") {
        // Movements that left the same lane share their first metres: a follower must see them too.
        for (const sib of v.piece.siblings) for (const o of this.list(sib)) if (o.s > v.s) consider(o.s - o.length - v.s, o.v);
      }
      const toEnd = v.piece.length - v.s;
      const nx = v.piece.kind === "lane" ? v.next : v.piece.to;
      if (nx) {
        let dist = toEnd;
        const scan = (p: Piece) => {
          for (const o of this.list(p)) consider(dist + o.s - o.length, o.v);
        };
        scan(nx);
        if (nx.kind === "turn") {
          for (const sib of nx.siblings) scan(sib);
          dist += nx.length;
          if (nx.to) scan(nx.to);
        }
      }
      for (const e of this.externals) {
        const rx = e.x - v.x;
        const rz = e.z - v.z;
        const hx = Math.sin(v.heading);
        const hz = Math.cos(v.heading);
        const ahead = rx * hx + rz * hz;
        const side = Math.abs(rx * -hz + rz * hx);
        if (ahead > 0 && ahead < 12 && side < 1.5) consider(ahead - e.length / 2 - v.length / 2, e.speed);
      }

      // Stop lines.
      const line = v.piece;
      let virtual = Infinity;
      if (line.kind === "lane" && line.control !== "none" && v.next && !v.holds.some((h) => h.from === line)) {
        const toLine = line.stopAt - v.s;
        const lookahead = Math.max(6, (v.v * v.v) / (2 * IDM.brake) + 3);
        if (toLine > lookahead) {
          virtual = toLine;
        } else if (toLine > -0.6 && !this.canEnter(v, line)) {
          virtual = Math.max(0.05, toLine);
          if (v.v < 0.4 && toLine < 2.2) v.waitT += dt;
        } else {
          if (line.control === "signal") {
            v.holds.push(v.next);
            const b = this.boxes.get(line.node);
            if (b) b.push(v);
            else this.boxes.set(line.node, [v]);
          }
          v.waitT = 0;
        }
      }
      if (virtual < gap) {
        gap = virtual;
        vl = 0;
      }

      const dv = v.v - vl;
      const sStar = IDM.minGap + Math.max(0, v.v * IDM.headway + (v.v * dv) / (2 * Math.sqrt(IDM.accel * IDM.brake)));
      const free = 1 - Math.pow(v.v / v.v0, 4);
      const inter = gap === Infinity ? 0 : (sStar / Math.max(gap, 0.1)) ** 2;
      const a = Math.max(-IDM.brake * 3, IDM.accel * (free - inter));
      acc.set(v, a);
      cap.set(v, gap === Infinity ? Infinity : Math.max(0, (gap - 0.3) / dt));
      v.braking = a < -0.8 || v.v < 0.2;
    }

    // Integrate and move along the pieces.
    const gone: Vehicle[] = [];
    for (const v of this.vehicles) {
      v.age += dt;
      v.scale = v.leaving ? Math.max(0, v.scale - dt * 2.5) : Math.min(1, v.scale + dt * 2.5);
      v.v = Math.min(Math.max(0, v.v + acc.get(v)! * dt), cap.get(v)!, v.piece.limit * 1.4);
      v.stuckT = v.v < 0.1 ? v.stuckT + dt : 0;
      v.s += v.v * dt;
      let guard = 0;
      while (v.s >= v.piece.length && guard++ < 6) {
        const nx: Piece | null = v.piece.kind === "lane" ? v.next : v.piece.to;
        if (!nx) {
          gone.push(v);
          break;
        }
        v.s -= v.piece.length;
        v.trail.unshift(v.piece);
        if (v.trail.length > 3) v.trail.pop();
        v.piece = nx;
        if (nx.kind === "lane") v.next = this.choose(v);
      }
      if (v.holds.length) v.holds = v.holds.filter((h) => !(v.piece === h.to && v.s - v.length >= 0));
      if (v.leaving && v.scale <= 0) gone.push(v);
      else if (v.stuckT > 60 && !v.leaving) {
        v.leaving = true;
        v.scale = 0;
      }
      this.pose(v);
    }
    if (gone.length) {
      for (const g of gone) {
        const i = this.vehicles.indexOf(g);
        if (i >= 0) this.vehicles.splice(i, 1);
      }
    }
  }
}

/** Smooth hourly traffic level 0..1 for the circadian clock: rush hours busy, deep night quiet. */
export function trafficLevel(hour: number): number {
  const h = ((hour % 24) + 24) % 24;
  const bump = (c: number, w: number) => Math.exp(-(((h - c) / w) ** 2));
  return Math.min(1, 0.28 + 0.62 * bump(8.3, 1.6) + 0.62 * bump(18, 2.0) + 0.3 * bump(13, 3.2));
}

/** Offset a polyline sideways (positive = to the right of the direction of travel), mitred. */
export function offsetPolyline(path: readonly V[], right: number): V[] {
  const unit = (a: V, b: V): V | null => {
    const l = Math.hypot(b.x - a.x, b.z - a.z);
    return l < 1e-9 ? null : { x: (b.x - a.x) / l, z: (b.z - a.z) / l };
  };
  return path.map((p, i) => {
    const d1 = i > 0 ? unit(path[i - 1], p) : null;
    const d2 = i < path.length - 1 ? unit(p, path[i + 1]) : null;
    const a = d1 ?? d2 ?? { x: 1, z: 0 };
    const b = d2 ?? d1 ?? a;
    // Right-hand normals are (-dz, dx); the mitre is their bisector, lengthened at corners.
    const n1 = { x: -a.z, z: a.x };
    const n2 = { x: -b.z, z: b.x };
    const bx = n1.x + n2.x;
    const bz = n1.z + n2.z;
    const bl = Math.hypot(bx, bz) || 1;
    const k = Math.min(1.8, 1 / Math.max(0.55, (bx / bl) * n1.x + (bz / bl) * n1.z));
    return { x: p.x + (bx / bl) * right * k, z: p.z + (bz / bl) * right * k };
  });
}
