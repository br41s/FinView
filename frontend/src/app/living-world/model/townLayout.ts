import { ARCHETYPE_DISTRICT } from "./archetypes";
import { PITCH, CANAL_HALF_WIDTH, CANAL_RUN_OUT, CANAL_X, CANAL_Z, carriage, nearestOnEdge, routeToGate, type CityGraph, type EdgeClass } from "./cityGraph";
import { getCityTemplate, slotAngle, type Block, type LotSite } from "./cityLots";
import { computeInfra, type Infra } from "./infra";
import { hash2, hashString } from "./rng";
import { MAX_FOOTPRINT } from "./scale";
import { createTerrain, type Pt, type Terrain } from "./terrain";
import { DISTRICT_IDS, type DistrictId, type WorldAsset } from "./types";

/**
 * Town layout: a toy city on one orthogonal street grid (see `cityGraph.ts`). The skeleton
 * (streets, blocks, lots, canal, railway, monorail) is the same for every portfolio; this
 * module only decides which lot each holding stands on and which scenery fills the rest.
 *
 * - Districts own a fixed compass wedge (their index in DISTRICT_IDS), so adding a holding
 *   never turns or moves the town.
 * - A holding's lot comes from a hash of its id: premium frontage (ring road, avenues) first,
 *   then the rest of its district, each asset ranking the free lots by its own hash. Nothing
 *   here reads weights, prices or events.
 * - Free lots fill with generic buildings facing the street. They stay smaller than holdings.
 */

/** Largest holding plus a street: kept as the unit holdings are spaced in. */
export const LOT_PITCH = MAX_FOOTPRINT + 2.5;
export const PLAZA_RADIUS = 16;

export interface Lot {
  assetId: string;
  district: DistrictId;
  x: number;
  z: number;
  /** Faces the street: the building front is (sin, cos) of this angle. */
  rotationY: number;
  col: number;
  row: number;
  /** Position relative to the district centre. */
  lx: number;
  lz: number;
  /** Unit vector towards the street the lot fronts. */
  fx: number;
  fz: number;
  /** Template lot key, frontage street and the point of its centre line the door opens to. */
  key: string;
  edgeId: string;
  front: Pt;
  /** Lot size: along the street and deep. */
  w: number;
  d: number;
}

export type DistrictShape = "highrise" | "campus" | "industrial" | "high-street" | "garden";

export interface DistrictLayout {
  id: DistrictId;
  slot: number;
  /** Centre of the district's lots. */
  cx: number;
  cz: number;
  theta: number;
  shape: DistrictShape;
  cols: number;
  rows: number;
  /** Radius enclosing the district's lots. */
  extent: number;
  assetCount: number;
  halfW: number;
  halfH: number;
  /** The plaza gate on the district's side. */
  gateX: number;
  gateZ: number;
  gateLX: number;
  gateLZ: number;
}

export interface RoadSegment {
  x1: number;
  z1: number;
  x2: number;
  z2: number;
  path: Pt[];
  /** Carriageway width (between pavements). */
  width: number;
  /** Kerb to kerb across both pavements, and each pavement. */
  fullWidth: number;
  walk: number;
  kind: EdgeClass;
  sidewalk: boolean;
  edgeId: string;
}

export interface GreenSpace {
  kind: "city-park" | "pocket-park" | "greenway" | "pocket-plaza";
  x: number;
  z: number;
  radiusX: number;
  radiusZ: number;
  halfW: number;
  halfD: number;
  rotationY: number;
  blockKey: string;
  pond?: { x: number; z: number; radiusX: number; radiusZ: number };
}

export type CivicKind = "bank" | "newsKiosk" | "observatory" | "townHall";
export interface CivicSite {
  kind: CivicKind;
  x: number;
  z: number;
}

/** Generic scenery: homes, offices, towers. Not holdings, never clickable (spec: landmarks vs fabric). */
export type FillerKind = "skyscraper" | "tower" | "block" | "house" | "villa" | "shed";
export interface FillerSpot {
  kind: FillerKind;
  x: number;
  z: number;
  rotationY: number;
  /** Footprint side in world units. */
  width: number;
  /** 0.8–1.3: how much taller than the prototype. */
  tall: number;
  /** 0–1 palette pick. */
  tone: number;
  district: DistrictId | null;
}

export interface WorldLayout {
  lots: Map<string, Lot>;
  districts: DistrictLayout[];
  roads: RoadSegment[];
  graph: CityGraph;
  blocks: Block[];
  civic: CivicSite[];
  filler: FillerSpot[];
  greenSpaces: GreenSpace[];
  /** Deterministic tree positions [x, z, scale], best-spread first. */
  treeSpots: Array<[number, number, number]>;
  terrain: Terrain;
  /** Monorail, railway and ambient traffic loops. */
  infra: Infra;
  /** Radius of the whole town around the origin, for "fit to view". */
  radius: number;
}

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

/** Share of homes among a district's generic buildings; the rest are offices and sheds. */
const RESIDENTIAL: Record<DistrictId, number> = {
  retail: 0.6,
  tech: 0.45,
  industry: 0.25,
  finance: 0.25,
  health: 0.55,
  funds: 0.75,
  treasury: 0.75,
};

interface Mix {
  /** 0 at the square, 1 far out. */
  cbd: number;
  residential: number;
  garden: boolean;
  industrial: boolean;
}

/** Pick a generic building: towers near the square, homes everywhere, villas in the gardens. */
function pickKind(u: number, m: Mix): FillerKind {
  if (m.garden) return u < 0.5 ? "villa" : u < 0.82 ? "house" : "tower";
  if (m.industrial) return u < 0.5 ? "shed" : u < 0.72 ? "block" : u < 0.88 ? "tower" : "house";
  const w = {
    skyscraper: m.cbd * Math.max(0.15, 1.15 - m.residential),
    tower: 0.22 + 0.25 * m.cbd,
    block: 0.18 + m.residential * 0.75,
    house: (1 - m.cbd) * (0.1 + 0.7 * m.residential),
  };
  const total = w.skyscraper + w.tower + w.block + w.house;
  let t = u * total;
  for (const k of ["skyscraper", "tower", "block", "house"] as const) {
    t -= w[k];
    if (t <= 0) return k;
  }
  return "block";
}

/** Generic buildings stay smaller than the holdings (3.4–7): size must keep meaning weight. */
export const WIDTH: Record<FillerKind, [number, number]> = {
  skyscraper: [2.8, 3.8],
  tower: [3.2, 4.0],
  block: [3.4, 4.2],
  house: [2.4, 3.0],
  villa: [3.8, 4.6],
  shed: [4.2, 5.0],
};
export const TALL: Record<FillerKind, [number, number]> = {
  skyscraper: [0.8, 1.7],
  tower: [0.55, 1.0],
  block: [0.55, 0.95],
  house: [0.8, 1.0],
  villa: [0.85, 1.05],
  shed: [0.8, 1.0],
};

function filler(kind: FillerKind, x: number, z: number, rotationY: number, seed: string, district: DistrictId | null, room: number): FillerSpot {
  const h = hashString(seed);
  const a = (h & 0xffff) / 0xffff;
  const b = ((h >>> 16) & 0xffff) / 0xffff;
  const [w0, w1] = WIDTH[kind];
  const [t0, t1] = TALL[kind];
  const width = Math.min(w0 + (w1 - w0) * a, room);
  return { kind, x, z, rotationY, width, tall: t0 + (t1 - t0) * b, tone: ((h >>> 8) & 0xff) / 255, district };
}

const CITY_RADIUS = PITCH * 4.5 + 52;

/** Lot of the template -> the asset's Lot. */
function toLot(assetId: string, district: DistrictId, s: LotSite, cx: number, cz: number): Lot {
  return {
    assetId,
    district,
    x: s.x,
    z: s.z,
    rotationY: s.rotationY,
    col: Math.round(s.x / PITCH),
    row: Math.round(s.z / PITCH),
    lx: s.x - cx,
    lz: s.z - cz,
    fx: s.fx,
    fz: s.fz,
    key: s.key,
    edgeId: s.edgeId,
    front: s.front,
    w: s.w,
    d: s.d,
  };
}

// --- the layout ----------------------------------------------------------------------

export function computeLayout(assets: readonly WorldAsset[]): WorldLayout {
  const template = getCityTemplate();
  const { graph, blocks } = template;

  const byDistrict = new Map<DistrictId, string[]>();
  for (const asset of assets) {
    const id = ARCHETYPE_DISTRICT[asset.archetype];
    const bucket = byDistrict.get(id);
    if (bucket) bucket.push(asset.id);
    else byDistrict.set(id, [asset.id]);
  }

  const terrain = createTerrain({
    canal: [
      { x: CANAL_X, z: -CANAL_RUN_OUT },
      { x: CANAL_X, z: CANAL_Z },
      { x: -CANAL_RUN_OUT, z: CANAL_Z },
    ],
    canalHalfWidth: CANAL_HALF_WIDTH,
    extent: CANAL_RUN_OUT,
  });
  const infra = computeInfra(graph, terrain.spec.canal);

  // --- holdings -> lots --------------------------------------------------------------------
  // Every asset ranks the free lots of its district by its own hash (premium frontage first);
  // assets claim in the order of their own hash, so the result never depends on input order.
  const taken = new Map<string, string>();
  const placed = new Map<string, { site: LotSite; district: DistrictId }>();
  const overflow: Array<{ id: string; district: DistrictId }> = [];
  for (const district of DISTRICT_IDS) {
    const ids = [...(byDistrict.get(district) ?? [])].sort();
    const own = template.lots.filter((l) => l.district === district && l.capable);
    const order = ids.map((id) => ({ id, h: hashString(id) })).sort((a, b) => a.h - b.h || (a.id < b.id ? -1 : 1));
    for (const { id, h } of order) {
      const free = own
        .filter((l) => !taken.has(l.key))
        .map((l) => ({ l, s: hash2(h, hashString(l.key), 9) }))
        .sort((a, b) => Number(!a.l.premium) - Number(!b.l.premium) || a.s - b.s || (a.l.key < b.l.key ? -1 : 1));
      const pick = free[0]?.l;
      if (!pick) {
        overflow.push({ id, district });
        continue;
      }
      taken.set(pick.key, id);
      placed.set(id, { site: pick, district });
    }
  }
  // Beyond a district's own capacity: the nearest free lots to its wedge, never another's twice.
  for (const { id, district } of overflow) {
    const ang = slotAngle(DISTRICT_IDS.indexOf(district));
    const anchor = { x: Math.cos(ang) * 120, z: Math.sin(ang) * 120 };
    const pick = template.lots
      .filter((l) => l.capable && !taken.has(l.key))
      .sort((a, b) => Math.hypot(a.x - anchor.x, a.z - anchor.z) - Math.hypot(b.x - anchor.x, b.z - anchor.z) || (a.key < b.key ? -1 : 1))[0];
    if (!pick) continue;
    taken.set(pick.key, id);
    placed.set(id, { site: pick, district });
  }

  // --- districts -------------------------------------------------------------------------------
  const shapeFor: Record<DistrictId, DistrictShape> = {
    retail: "high-street",
    tech: "campus",
    industry: "industrial",
    finance: "highrise",
    health: "campus",
    funds: "garden",
    treasury: "garden",
  };
  const districts: DistrictLayout[] = [];
  DISTRICT_IDS.forEach((id, slot) => {
    const count = byDistrict.get(id)?.length ?? 0;
    if (!count) return;
    const own = template.lots.filter((l) => l.district === id && l.capable);
    const cx = own.reduce((s, l) => s + l.x, 0) / own.length;
    const cz = own.reduce((s, l) => s + l.z, 0) / own.length;
    const extent = Math.max(...own.map((l) => Math.hypot(l.x - cx, l.z - cz))) + 10;
    const gate = [...graph.gates].sort((a, b) => Math.hypot(a.x - cx, a.z - cz) - Math.hypot(b.x - cx, b.z - cz))[0];
    const side = Math.ceil(Math.sqrt(own.length));
    districts.push({
      id,
      slot,
      cx,
      cz,
      theta: 0,
      shape: shapeFor[id],
      cols: side,
      rows: Math.ceil(own.length / side),
      extent,
      assetCount: count,
      halfW: Math.max(...own.map((l) => Math.abs(l.x - cx))) + 8,
      halfH: Math.max(...own.map((l) => Math.abs(l.z - cz))) + 8,
      gateX: gate.x,
      gateZ: gate.z,
      gateLX: gate.x - cx,
      gateLZ: gate.z - cz,
    });
  });

  const lots = new Map<string, Lot>();
  for (const [id, { site, district }] of placed) {
    const d = districts.find((x) => x.id === district)!;
    lots.set(id, toLot(id, district, site, d.cx, d.cz));
  }

  // --- roads ---------------------------------------------------------------------------------------
  const roads: RoadSegment[] = graph.roads.map((e) => {
    const a = graph.node(e.a);
    const b = graph.node(e.b);
    return {
      x1: a.x,
      z1: a.z,
      x2: b.x,
      z2: b.z,
      path: [{ x: a.x, z: a.z }, { x: b.x, z: b.z }],
      width: carriage(e),
      fullWidth: e.width,
      walk: e.walk,
      kind: e.class,
      sidewalk: true,
      edgeId: e.id,
    };
  });

  // --- parks, plazas, civic -----------------------------------------------------------------
  const greenSpaces: GreenSpace[] = [];
  for (const b of blocks) {
    if (b.kind === "city" || b.kind === "plaza" || b.kind === "station") continue;
    const kind: GreenSpace["kind"] =
      b.kind === "park" ? (b.key === "b2_-2" ? "city-park" : "pocket-park") : b.kind === "pocket-plaza" ? "pocket-plaza" : "greenway";
    greenSpaces.push({
      kind,
      x: b.centre.x,
      z: b.centre.z,
      radiusX: b.halfW,
      radiusZ: b.halfD,
      halfW: b.halfW,
      halfD: b.halfD,
      rotationY: 0,
      blockKey: b.key,
      pond: kind === "city-park" ? { x: b.centre.x + 4, z: b.centre.z - 2, radiusX: 9, radiusZ: 6 } : undefined,
    });
  }
  const civicKinds: CivicKind[] = ["bank", "newsKiosk", "observatory", "townHall"];
  const civic = civicKinds.map((kind, i) => {
    const a = Math.PI / 4 + (i * Math.PI) / 2;
    return { kind, x: Math.cos(a) * 9, z: Math.sin(a) * 9 };
  });

  // --- generic buildings in every lot no holding took --------------------------------------------
  const fillerSpots: FillerSpot[] = [];
  const blockOf = new Map(blocks.map((b) => [b.key, b]));
  for (const lot of template.lots) {
    if (taken.has(lot.key)) continue;
    const block = blockOf.get(lot.blockKey)!;
    const nx = Math.max(1, Math.round(lot.w / 6.4));
    const nz = Math.max(1, Math.round(lot.d / 6.4));
    const cw = lot.w / nx;
    const cd = lot.d / nz;
    const tx = -lot.fz;
    const tz = lot.fx;
    const r = Math.hypot(lot.x, lot.z);
    const mix: Mix = {
      cbd: 1 - smooth(30, 170, r) + (lot.district === "finance" ? 0.2 : 0),
      residential: RESIDENTIAL[lot.district],
      garden: lot.district === "funds" || lot.district === "treasury",
      industrial: lot.district === "industry" || block.j === 0,
    };
    for (let a = 0; a < nx; a++) {
      for (let b = 0; b < nz; b++) {
        const seed = `${lot.key}:${a}:${b}`;
        const hs = hashString(seed);
        if (hash2(hs, 1, 3) < 0.08) continue;
        const along = (a + 0.5) * cw - lot.w / 2 + (hash2(hs, 2, 3) - 0.5) * 0.8;
        const deep = (b + 0.5) * cd - lot.d / 2 + (hash2(hs, 3, 3) - 0.5) * 0.8;
        // `deep` grows towards the street: the first row stands on the pavement line.
        const x = lot.x + tx * along + lot.fx * deep;
        const z = lot.z + tz * along + lot.fz * deep;
        const kind = pickKind(hash2(hs, 4, 3), mix);
        fillerSpots.push(filler(kind, x, z, lot.rotationY, seed, lot.district, Math.min(cw, cd) * 0.8));
      }
    }
  }

  return {
    lots,
    districts,
    roads,
    graph,
    blocks,
    civic,
    filler: fillerSpots,
    greenSpaces,
    treeSpots: treeSpots(graph, blocks, terrain),
    terrain,
    infra,
    radius: CITY_RADIUS,
  };
}

/** Where a holding's door opens and the way from there to the plaza, along the street graph. */
export function routeFromLot(layout: Pick<WorldLayout, "graph">, lot: Lot): Pt[] {
  const edge = layout.graph.edges.find((e) => e.id === lot.edgeId);
  const front = edge ? nearestOnEdge(layout.graph, edge, lot) : lot.front;
  return [{ x: lot.x, z: lot.z }, ...routeToGate(layout.graph, front, lot.edgeId)];
}

// --- trees -------------------------------------------------------------------------------------

function treeSpots(graph: CityGraph, blocks: readonly Block[], terrain: Terrain): Array<[number, number, number]> {
  const gardens: Array<[number, number, number]> = [];
  const lines: Array<[number, number, number]> = [];
  const out: Array<[number, number, number]> = [];
  const scale = (x: number, z: number, k: number) => 0.75 + hash2(Math.round(x * 4), Math.round(z * 4), k) * 0.8;

  // Parks and the banks of the canal.
  for (const b of blocks) {
    if (b.kind === "city" || b.kind === "plaza" || b.kind === "station" || b.kind === "pocket-plaza") continue;
    const step = b.kind === "canal" ? 8 : 6.5;
    for (let x = b.centre.x - b.halfW + 3; x < b.centre.x + b.halfW - 2; x += step) {
      for (let z = b.centre.z - b.halfD + 3; z < b.centre.z + b.halfD - 2; z += step) {
        const jx = x + (hash2(Math.round(x), Math.round(z), 41) - 0.5) * 3.5;
        const jz = z + (hash2(Math.round(x), Math.round(z), 42) - 0.5) * 3.5;
        if (hash2(Math.round(x), Math.round(z), 43) < 0.28) continue;
        if (terrain.canalDistance(jx, jz) < CANAL_HALF_WIDTH + 4.5) continue;
        // The forced city park keeps its pond and lawn clear.
        if (b.key === "b2_-2" && Math.hypot(jx - (b.centre.x + 4), jz - (b.centre.z - 2)) < 11) continue;
        gardens.push([jx, jz, scale(jx, jz, 44)]);
      }
    }
  }

  // Street trees on the pavements of streets and avenues.
  for (const e of graph.roads) {
    if (e.class === "bridge" || e.class === "ring") continue;
    const a = graph.node(e.a);
    const b = graph.node(e.b);
    const dx = (b.x - a.x) / e.length;
    const dz = (b.z - a.z) / e.length;
    const off = e.width / 2 - e.walk / 2;
    for (let d = 14; d < e.length - 13; d += 12) {
      for (const side of [-1, 1]) {
        const x = a.x + dx * d - dz * off * side;
        const z = a.z + dz * d + dx * off * side;
        if (hash2(Math.round(x), Math.round(z), 45) < 0.35) continue;
        if (e.class === "avenue" && e.median > 0) continue;
        lines.push([x, z, scale(x, z, 46)]);
      }
    }
  }

  // Open country beyond the perimeter avenue.
  for (let gx = -CANAL_RUN_OUT; gx <= CANAL_RUN_OUT; gx += 16) {
    for (let gz = -CANAL_RUN_OUT; gz <= CANAL_RUN_OUT; gz += 16) {
      const x = gx + (hash2(gx, gz, 47) - 0.5) * 12;
      const z = gz + (hash2(gx, gz, 48) - 0.5) * 12;
      if (Math.max(Math.abs(x), Math.abs(z)) < PITCH * 4.5 + 12) continue;
      if (hash2(gx, gz, 49) < 0.62) continue;
      if (terrain.canalDistance(x, z) < CANAL_HALF_WIDTH + 5) continue;
      if (x > 0 && Math.abs(z) < 9) continue;
      out.push([x, z, scale(x, z, 50)]);
    }
  }
  const shuffle = (list: Array<[number, number, number]>, salt: number) =>
    list.map((t, i) => ({ t, k: hash2(i, salt, 51) })).sort((p, q) => p.k - q.k).map((o) => o.t);
  // One park tree for every two street or country trees, so a low quality setting still has parks.
  const g = shuffle(gardens, 53);
  const rest = shuffle([...lines, ...out], 52);
  const merged: Array<[number, number, number]> = [];
  for (let i = 0, gi = 0, ri = 0; gi < g.length || ri < rest.length; i++) {
    if ((i % 3 === 0 && gi < g.length) || ri >= rest.length) merged.push(g[gi++]);
    else merged.push(rest[ri++]);
  }
  return merged;
}
