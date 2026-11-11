import type { V } from "./cityGeometry";
import { carriage, type CityGraph, type GEdge, type HalfEdge } from "./cityGraph";
import { districtAt } from "./cityLots";
import { hashString, seeded } from "./rng";
import type { DistrictId } from "./types";

/**
 * Pedestrians on the pavements (pure). Every road half-edge has a pavement on its right and one on
 * its left; a walker owns one side for good. At a junction it hugs the corner (a right-hand walker
 * takes the road that follows the one it came from in clockwise order, a left-hand one the other
 * way), which is a walk round the edge of a city block: it never steps onto the asphalt, so cars
 * and walkers cannot meet. Corners are rounded with a short curve inside the junction's pavement.
 *
 * Which of the four professions a walker has comes from the district it spawns in; how many walkers
 * are out comes from the hour. Both are deterministic in the seed.
 */

export type Profession = "worker" | "executive" | "courier" | "analyst";
export const PROFESSIONS: readonly Profession[] = ["worker", "executive", "courier", "analyst"];

/** The profession most often seen in each district. */
export const DISTRICT_PROFESSION: Record<DistrictId, Profession> = {
  industry: "worker",
  finance: "executive",
  treasury: "executive",
  retail: "courier",
  tech: "analyst",
  health: "analyst",
  funds: "analyst",
};

export interface WalkPiece {
  id: number;
  pts: V[];
  cum: number[];
  length: number;
  /** The piece a walker moves on to at the end. */
  next: WalkPiece | null;
  /** Lateral room left by the pavement (half of it either side of the centre line). */
  room: number;
  node: string;
}

export interface WalkNet {
  pieces: WalkPiece[];
}

const dirOf = (a: V, b: V, len: number): V => ({ x: (b.x - a.x) / len, z: (b.z - a.z) / len });

/** Distance from a node at which an arm's pavement strip ends: the junction's pavement square. */
function walkStop(graph: CityGraph, edgeOf: (h: HalfEdge) => GEdge, nodeId: string, arm: HalfEdge): number {
  const node = graph.node(nodeId);
  if (node.kind !== "junction" && node.kind !== "bend") return 0;
  const arms = graph.adjacency.get(nodeId)!;
  const n = arms.length;
  const i = arms.indexOf(arm);
  let best = 0;
  for (const j of [(i + 1) % n, (i - 1 + n) % n]) {
    if (j === i) continue;
    const o = arms[j];
    if (Math.abs(Math.cos(arm.angle - o.angle)) < 0.2) best = Math.max(best, edgeOf(o).width / 2);
  }
  return best;
}

function quad(p0: V, c: V, p1: V, n: number): V[] {
  const out: V[] = [];
  for (let i = 0; i <= n; i++) {
    const t = i / n;
    const u = 1 - t;
    out.push({ x: u * u * p0.x + 2 * u * t * c.x + t * t * p1.x, z: u * u * p0.z + 2 * u * t * c.z + t * t * p1.z });
  }
  return out;
}

function intersect(p: V, dp: V, q: V, dq: V): V | null {
  const den = dp.x * dq.z - dp.z * dq.x;
  if (Math.abs(den) < 1e-6) return null;
  const t = ((q.x - p.x) * dq.z - (q.z - p.z) * dq.x) / den;
  return { x: p.x + dp.x * t, z: p.z + dp.z * t };
}

export function buildWalkNet(graph: CityGraph): WalkNet {
  const edgeById = new Map(graph.edges.map((e) => [e.id, e]));
  const edgeOf = (h: HalfEdge) => edgeById.get(h.edge)!;
  const pieces: WalkPiece[] = [];
  const bySide = new Map<string, { line: [V, V]; dir: V; piece: WalkPiece; h: HalfEdge }>();

  const halves = [...graph.halfEdges.values()].sort((p, q) => (p.id < q.id ? -1 : 1));
  for (const h of halves) {
    const e = edgeOf(h);
    const a = graph.node(h.from);
    const b = graph.node(h.to);
    const d = dirOf(a, b, e.length);
    const startStop = walkStop(graph, edgeOf, h.from, h);
    const endStop = walkStop(graph, edgeOf, h.to, graph.halfEdges.get(h.twin)!);
    for (const side of [1, -1] as const) {
      const off = (carriage(e) / 2 + e.walk / 2) * side;
      const nx = -d.z * off;
      const nz = d.x * off;
      const s0 = Math.min(startStop, e.length / 2 - 0.2);
      const s1 = Math.max(e.length - endStop, e.length / 2 + 0.2);
      const p0 = { x: a.x + d.x * s0 + nx, z: a.z + d.z * s0 + nz };
      const p1 = { x: a.x + d.x * s1 + nx, z: a.z + d.z * s1 + nz };
      const piece: WalkPiece = { id: pieces.length, pts: [p0, p1], cum: [], length: 0, next: null, room: Math.max(0.2, e.walk - 0.9), node: h.to };
      pieces.push(piece);
      bySide.set(`${h.id}|${side}`, { line: [p0, p1], dir: d, piece, h });
    }
  }

  // Connect each pavement to the one it continues on round the corner.
  for (const [key, from] of bySide) {
    const side = Number(key.split("|")[1]) as 1 | -1;
    const h = from.h;
    const arms = graph.adjacency.get(h.to)!;
    if (arms.length < 2) continue;
    const back = arms.findIndex((x) => x.id === h.twin);
    const n = arms.length;
    const out = arms[(back + (side === 1 ? -1 : 1) + n) % n];
    const to = bySide.get(`${out.id}|${side}`);
    if (!to) continue;
    const p0 = from.line[1];
    const p1 = to.line[0];
    const c = intersect(p0, from.dir, p1, to.dir);
    const gap = Math.hypot(p1.x - p0.x, p1.z - p0.z);
    if (gap > 0.05) {
      const near = c && Math.hypot(c.x - p0.x, c.z - p0.z) < gap * 1.6 && Math.hypot(c.x - p1.x, c.z - p1.z) < gap * 1.6;
      let curve: V[] = [p0, p1];
      if (c && near) {
        // Hugging the inside of a turn rounds the corner; on the outside it goes round the
        // kerb corner (a chamfer through the pavement's outer corner), never across the asphalt.
        const turn = from.dir.x * to.dir.z - from.dir.z * to.dir.x;
        const inner = (side === 1 && turn > 0) || (side === -1 && turn < 0);
        if (inner) curve = quad(p0, c, p1, 6);
        else {
          const k = 1.4;
          curve = [p0, { x: c.x - from.dir.x * k, z: c.z - from.dir.z * k }, { x: c.x + to.dir.x * k, z: c.z + to.dir.z * k }, p1];
        }
      }
      from.piece.pts.push(...curve.slice(1));
    }
    from.piece.next = to.piece;
  }

  for (const p of pieces) {
    p.cum = [0];
    for (let i = 1; i < p.pts.length; i++) p.cum.push(p.cum[i - 1] + Math.hypot(p.pts[i].x - p.pts[i - 1].x, p.pts[i].z - p.pts[i - 1].z));
    p.length = p.cum[p.cum.length - 1];
  }
  return { pieces };
}

let cachedWalk: { graph: CityGraph; net: WalkNet } | null = null;
export function getWalkNet(graph: CityGraph): WalkNet {
  if (!cachedWalk || cachedWalk.graph !== graph) cachedWalk = { graph, net: buildWalkNet(graph) };
  return cachedWalk.net;
}

export function walkSample(p: WalkPiece, s: number): { x: number; z: number; heading: number } {
  const pts = p.pts;
  const last = pts.length - 1;
  const t = Math.min(Math.max(s, 0), p.length);
  let i = 1;
  while (i < last && p.cum[i] < t) i++;
  const a = pts[i - 1];
  const b = pts[i];
  const seg = p.cum[i] - p.cum[i - 1] || 1;
  const f = Math.min(1, Math.max(0, (t - p.cum[i - 1]) / seg));
  return { x: a.x + (b.x - a.x) * f, z: a.z + (b.z - a.z) * f, heading: Math.atan2(b.x - a.x, b.z - a.z) };
}

export interface Walker {
  id: number;
  profession: Profession;
  piece: WalkPiece;
  s: number;
  speed: number;
  /** Lateral shift from the pavement centre line, within its room. */
  lane: number;
  /** Activity threshold: out and about while the hour's crowd level is above it. */
  u: number;
  /** Seed for looks (skin tone, walk phase). */
  seed: number;
  x: number;
  z: number;
  heading: number;
  moving: boolean;
}

/** Share of the walkers who are out at this hour: crowds at rush hours, a few at night. */
export function crowdLevel(hour: number): number {
  const h = ((hour % 24) + 24) % 24;
  const bump = (c: number, w: number) => Math.exp(-(((h - c) / w) ** 2));
  return Math.min(1, 0.12 + 0.7 * bump(8.5, 1.5) + 0.7 * bump(18.2, 2.0) + 0.45 * bump(13, 2.6));
}

export class WalkerSim {
  readonly walkers: Walker[] = [];
  private rnd: () => number;
  private weights: Array<{ piece: WalkPiece; w: number }> = [];

  constructor(readonly net: WalkNet, seed = 1) {
    this.rnd = seeded(seed);
    // Crowd the middle of town more than the outskirts.
    this.weights = net.pieces
      .filter((p) => p.length > 6 && p.next)
      .map((p) => {
        const m = p.pts[Math.floor(p.pts.length / 2)];
        const r = Math.max(Math.abs(m.x), Math.abs(m.z));
        return { piece: p, w: p.length * (0.35 + 1.4 * Math.exp(-((r / 120) ** 2))) };
      });
  }

  private pick(): WalkPiece {
    const total = this.weights.reduce((a, b) => a + b.w, 0);
    let r = this.rnd() * total;
    for (const e of this.weights) {
      r -= e.w;
      if (r <= 0) return e.piece;
    }
    return this.weights[0].piece;
  }

  /** (Re)fill with `n` walkers. */
  populate(n: number) {
    this.walkers.length = 0;
    for (let i = 0; i < n; i++) {
      const piece = this.pick();
      const s = this.rnd() * piece.length;
      const here = walkSample(piece, s);
      const district = districtAt(here.x, here.z);
      const primary = DISTRICT_PROFESSION[district];
      // The district's own profession is the most likely, but all four are always in the street.
      const r = this.rnd() * 6;
      const profession = r < 3 ? primary : PROFESSIONS[Math.floor(this.rnd() * PROFESSIONS.length)];
      const seed = hashString(`walker:${i}`);
      const w: Walker = {
        id: i, profession, piece, s,
        speed: 1.15 + this.rnd() * 0.7,
        lane: (this.rnd() - 0.5) * Math.min(0.7, piece.room * 0.8),
        u: (i + 0.5) / n,
        seed, x: here.x, z: here.z, heading: here.heading, moving: true,
      };
      this.walkers.push(w);
      this.pose(w);
    }
  }

  pose(w: Walker) {
    const p = walkSample(w.piece, w.s);
    // Shift sideways by `lane`, perpendicular to the direction of travel.
    w.x = p.x + Math.cos(p.heading) * w.lane;
    w.z = p.z - Math.sin(p.heading) * w.lane;
    w.heading = p.heading;
  }

  step(dt: number, crowd: number) {
    for (const w of this.walkers) {
      w.moving = w.u < crowd;
      if (!w.moving) continue;
      w.s += w.speed * dt;
      let guard = 0;
      while (w.s >= w.piece.length && guard++ < 4) {
        if (!w.piece.next) {
          w.s = w.piece.length;
          break;
        }
        w.s -= w.piece.length;
        w.piece = w.piece.next;
        w.lane = Math.max(-w.piece.room * 0.4, Math.min(w.piece.room * 0.4, w.lane));
      }
      this.pose(w);
    }
  }
}
