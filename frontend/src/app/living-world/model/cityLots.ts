import { clipHalfPlane, orientedBox, polyArea, closestOnSegment, type V } from "./cityGeometry";
import {
  CANAL_X,
  CANAL_Z,
  GRID_N,
  PITCH,
  RAIL_CLEAR_HALF,
  getCityGraph,
  insetFace,
  type CityGraph,
  type Face,
} from "./cityGraph";
import { hash2, hashString } from "./rng";
import { DISTRICT_IDS, type DistrictId } from "./types";

/**
 * Blocks and lots of the city template (pure). Each bounded face of the street graph is a
 * block; city blocks are shrunk by the pavement width of their streets, and split into lots
 * by a recursive oriented-box cut (jittered from a hash of the block key). Everything here is
 * a function of the template, so the lots exist whether or not a holding takes them.
 */

/** Holding lots are about this wide: the biggest building is 12.8 x 1.28 = 16.4. */
export const SPLIT_MAX = 24;
/** A lot narrower than this stays scenery: it cannot hold a landmark. */
export const HOLDING_MIN_SIDE = 14.4;

const BASE_ANGLE = -Math.PI / 2;
const SECTOR = (Math.PI * 2) / DISTRICT_IDS.length;

/** Fixed compass slot of a point: district k owns the wedge centred on BASE_ANGLE + k * 2PI/7. */
export function slotAt(x: number, z: number): number {
  const rel = (((Math.atan2(z, x) - BASE_ANGLE + SECTOR / 2) % (Math.PI * 2)) + Math.PI * 2) % (Math.PI * 2);
  return Math.min(DISTRICT_IDS.length - 1, Math.floor(rel / SECTOR));
}
export const districtAt = (x: number, z: number): DistrictId => DISTRICT_IDS[slotAt(x, z)];
export const slotAngle = (slot: number) => BASE_ANGLE + slot * SECTOR;

export type BlockKind = "city" | "plaza" | "station" | "canal" | "park" | "corner-park" | "pocket-plaza";

export interface LotSite {
  key: string;
  blockKey: string;
  district: DistrictId;
  /** Centre, frontage and depth in world units; `fx,fz` is the unit vector towards the street. */
  x: number;
  z: number;
  w: number;
  d: number;
  fx: number;
  fz: number;
  rotationY: number;
  polygon: V[];
  /** 3 ring road, 2 avenue, 1 street, 0 none. */
  rank: number;
  /** Fronts the ring road or an avenue: reserved first for holdings. */
  premium: boolean;
  /** Big enough, and on a street, to take a landmark. */
  capable: boolean;
  edgeId: string;
  /** Nearest point of the frontage street's centre line. */
  front: V;
}

export interface Block {
  key: string;
  i: number;
  j: number;
  kind: BlockKind;
  district: DistrictId;
  face: Face;
  /** Paved ground inside the pavements (convex). */
  plot: V[];
  /** What is left of the plot after keep-out strips (the railway). */
  plots: V[][];
  lots: LotSite[];
  centre: V;
  halfW: number;
  halfD: number;
}

export interface CityTemplate {
  graph: CityGraph;
  blocks: Block[];
  lots: LotSite[];
  lotByKey: Map<string, LotSite>;
}

const dot = (ax: number, az: number, bx: number, bz: number) => ax * bx + az * bz;

function cellKind(i: number, j: number): BlockKind {
  if (i === 0 && j === 0) return "plaza";
  if ((i === CANAL_X / PITCH && j <= CANAL_Z / PITCH) || (j === CANAL_Z / PITCH && i <= CANAL_X / PITCH)) return "canal";
  if (i === 1 && j === 0) return "station";
  if (Math.abs(i) === GRID_N && Math.abs(j) === GRID_N) return "corner-park";
  if (i === 2 && j === -2) return "park";
  if (Math.max(Math.abs(i), Math.abs(j)) >= 2 && !(j === 0 && i > 0)) {
    const u = hash2(i, j, 31);
    if (u < 0.085) return "park";
    if (u < 0.12) return "pocket-plaza";
  }
  return "city";
}

/** Recursive cut on the longest axis, jittered from a hash of the key. */
function splitPlot(poly: V[], key: string, out: Array<{ poly: V[]; key: string }>) {
  const box = orientedBox(poly);
  const longest = Math.max(box.hu, box.hv) * 2;
  if (longest <= SPLIT_MAX || key.length > 12) {
    out.push({ poly, key });
    return;
  }
  const alongU = box.hu >= box.hv;
  const ax = alongU ? box.ux : box.vx;
  const az = alongU ? box.uz : box.vz;
  const half = alongU ? box.hu : box.hv;
  const t = (hash2(hashString(key), key.length, 71) - 0.5) * 0.08;
  const cut = dot(box.cx, box.cz, ax, az) + t * 2 * half;
  splitPlot(clipHalfPlane(poly, ax, az, cut), key + "a", out);
  splitPlot(clipHalfPlane(poly, -ax, -az, -cut), key + "b", out);
}

function describeLot(poly: V[], face: Face, key: string, blockKey: string, district: DistrictId): LotSite {
  const box = orientedBox(poly);
  const c: V = { x: box.cx, z: box.cz };
  type Cand = { rank: number; overlap: number; edgeId: string; nx: number; nz: number; dx: number; dz: number; a: V; b: V };
  const cands: Cand[] = [];
  let nearest: Cand | null = null;
  let nearestGap = Infinity;
  for (const fe of face.edges) {
    const dx = fe.b.x - fe.a.x;
    const dz = fe.b.z - fe.a.z;
    const l = Math.hypot(dx, dz);
    const ex = dx / l;
    const ez = dz / l;
    const nx = -ez;
    const nz = ex;
    const hN = Math.abs(dot(box.ux, box.uz, nx, nz)) * box.hu + Math.abs(dot(box.vx, box.vz, nx, nz)) * box.hv;
    const hA = Math.abs(dot(box.ux, box.uz, ex, ez)) * box.hu + Math.abs(dot(box.vx, box.vz, ex, ez)) * box.hv;
    const gap = dot(c.x - fe.a.x, c.z - fe.a.z, nx, nz) - fe.edge.width / 2 - hN;
    const t = dot(c.x - fe.a.x, c.z - fe.a.z, ex, ez);
    const overlap = Math.min(t + hA, l) - Math.max(t - hA, 0);
    const rank = fe.edge.class === "ring" ? 3 : fe.edge.class === "avenue" ? 2 : 1;
    const cand: Cand = { rank, overlap, edgeId: fe.edge.id, nx: -nx, nz: -nz, dx: ex, dz: ez, a: fe.a, b: fe.b };
    if (gap < nearestGap) {
      nearestGap = gap;
      nearest = cand;
    }
    if (gap <= 1.0 && overlap >= 1.0) cands.push(cand);
  }
  cands.sort((p, q) => q.rank - p.rank || q.overlap - p.overlap || (p.edgeId < q.edgeId ? -1 : 1));
  let pick = cands[0] ?? nearest!;
  // A corner lot fronts either of its streets: let a hash of the lot choose between equals.
  const tied = cands.filter((x) => x.rank === pick.rank && Math.abs(x.overlap - pick.overlap) < 1.5);
  if (tied.length > 1 && hash2(hashString(key), 3, 5) < 0.5) pick = tied[1];
  const w = 2 * (Math.abs(dot(box.ux, box.uz, pick.dx, pick.dz)) * box.hu + Math.abs(dot(box.vx, box.vz, pick.dx, pick.dz)) * box.hv);
  const d = 2 * (Math.abs(dot(box.ux, box.uz, pick.nx, pick.nz)) * box.hu + Math.abs(dot(box.vx, box.vz, pick.nx, pick.nz)) * box.hv);
  const near = closestOnSegment(c, pick.a, pick.b);
  const hasFront = cands.length > 0;
  return {
    key,
    blockKey,
    district,
    x: c.x,
    z: c.z,
    w,
    d,
    fx: pick.nx,
    fz: pick.nz,
    rotationY: Math.atan2(pick.nx, pick.nz),
    polygon: poly,
    rank: hasFront ? pick.rank : 0,
    premium: hasFront && pick.rank >= 2,
    capable: hasFront && Math.min(w, d) >= HOLDING_MIN_SIDE,
    edgeId: pick.edgeId,
    front: { x: near.x, z: near.z },
  };
}

export function buildCityTemplate(): CityTemplate {
  const graph = getCityGraph();
  const blocks: Block[] = [];
  for (const face of graph.faces) {
    if (!face.bounded) continue;
    const i = Math.round(face.centroid.x / PITCH);
    const j = Math.round(face.centroid.z / PITCH);
    const kind = cellKind(i, j);
    const key = `b${i}_${j}`;
    const plot = insetFace(face);
    let plots: V[][] = [plot];
    if (kind === "city" && j === 0 && i > 0) {
      // The railway runs down the middle of this row: keep the lots clear of it.
      plots = [clipHalfPlane(plot, 0, -1, -RAIL_CLEAR_HALF), clipHalfPlane(plot, 0, 1, -RAIL_CLEAR_HALF)];
    }
    const district = districtAt(face.centroid.x, face.centroid.z);
    const xs = plot.map((p) => p.x);
    const zs = plot.map((p) => p.z);
    const block: Block = {
      key,
      i,
      j,
      kind,
      district,
      face,
      plot,
      plots,
      lots: [],
      centre: { x: (Math.min(...xs) + Math.max(...xs)) / 2, z: (Math.min(...zs) + Math.max(...zs)) / 2 },
      halfW: (Math.max(...xs) - Math.min(...xs)) / 2,
      halfD: (Math.max(...zs) - Math.min(...zs)) / 2,
    };
    if (kind === "city") {
      plots.forEach((p, pi) => {
        if (p.length < 3 || polyArea(p) < 20) return;
        const pieces: Array<{ poly: V[]; key: string }> = [];
        splitPlot(p, `${key}.${pi}`, pieces);
        for (const piece of pieces) block.lots.push(describeLot(piece.poly, face, piece.key, key, district));
      });
    }
    blocks.push(block);
  }
  blocks.sort((p, q) => (p.key < q.key ? -1 : 1));
  const lots = blocks.flatMap((b) => b.lots);
  return { graph, blocks, lots, lotByKey: new Map(lots.map((l) => [l.key, l])) };
}

let cached: CityTemplate | null = null;
export function getCityTemplate(): CityTemplate {
  return (cached ??= buildCityTemplate());
}

