import { ARCHETYPE_DISTRICT } from "./archetypes";
import { computeInfra, type Infra } from "./infra";
import { hash2, hashString } from "./rng";
import { MAX_FOOTPRINT } from "./scale";
import { PLATEAU_HEIGHT, RIVER_HALF_WIDTH, chaikin, createTerrain, distToPolyline, type Pt, type Terrain } from "./terrain";
import { DISTRICT_IDS, type DistrictId, type WorldAsset } from "./types";

/**
 * Town layout: a cohesive living city structured around a vibrant central square,
 * an arterial boulevard ring, organic district neighbourhoods with structured urban blocks,
 * and seamless pedestrian and transit corridors.
 *
 * Visual & Urban Rule:
 * - Buildings are organized into coherent urban blocks (manzanas) lining the streets and
 *   sidewalks rather than floating randomly in fields.
 * - Portfolio holdings occupy prime street frontages and plazas.
 * - Monochromatic "atrezzo" buildings fill out the street walls and neighbourhood blocks.
 * - All placements are deterministic pure functions of asset IDs so price updates never move sites.
 */

/** Distance between lot centres: largest footprint + a street. */
export const LOT_PITCH = MAX_FOOTPRINT + 2.5;
export const PLAZA_RADIUS = 16;

const DISTRICT_GAP = 6;
/** Extra room where the river runs between two districts (banks included). */
const RIVER_GAP = 28;
/** Extra room at the plateau's cliff edge. */
const CLIFF_GAP = 14;
const SLOT_COUNT = DISTRICT_IDS.length;
const BASE_ANGLE = -Math.PI / 2;
const FABRIC_PITCH = 7.6;

export interface Lot {
  assetId: string;
  district: DistrictId;
  x: number;
  z: number;
  /** Faces the street / central access in quarter turns of the district's own grid. */
  rotationY: number;
  col: number;
  row: number;
  /** Position inside the district grid, relative to its centre (before rotation). */
  lx: number;
  lz: number;
  /** Front direction in the district's grid, an axis unit vector. */
  fx: number;
  fz: number;
}

export type DistrictShape = "highrise" | "campus" | "industrial" | "high-street" | "garden";

export interface DistrictLayout {
  id: DistrictId;
  slot: number;
  cx: number;
  cz: number;
  /** Local orientation; each neighbourhood has its own street grain. */
  theta: number;
  shape: DistrictShape;
  cols: number;
  rows: number;
  /** Conservative radius enclosing its organic parcel cluster. */
  extent: number;
  assetCount: number;
  halfW: number;
  halfH: number;
  /** Inner access point, joined to both the local street ring and the city arterial. */
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
  width: number;
  kind: "arterial" | "boulevard" | "local" | "exit";
  sidewalk: boolean;
  districtId?: DistrictId;
}

export interface GreenSpace {
  kind: "city-park" | "pocket-park" | "greenway";
  x: number;
  z: number;
  radiusX: number;
  radiusZ: number;
  rotationY: number;
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
  civic: CivicSite[];
  filler: FillerSpot[];
  greenSpaces: GreenSpace[];
  terrain: Terrain;
  /** Expressways, railway and monorail. */
  infra: Infra;
  /** Radius of the whole town around the origin, for "fit to view". */
  radius: number;
}

/** Lot capacity grows in steps of 4 with ~60 % slack: the rest of the grid is housing. */
export function capacityFor(count: number): number {
  return Math.max(4, Math.ceil((count * 1.6) / 4) * 4);
}

// --- geometry helpers --------------------------------------------------------------

export function toWorld(d: Pick<DistrictLayout, "cx" | "cz" | "theta">, lx: number, lz: number): Pt {
  const c = Math.cos(d.theta);
  const s = Math.sin(d.theta);
  return { x: d.cx + lx * c - lz * s, z: d.cz + lx * s + lz * c };
}

export function toLocal(d: Pick<DistrictLayout, "cx" | "cz" | "theta">, x: number, z: number): Pt {
  const c = Math.cos(d.theta);
  const s = Math.sin(d.theta);
  const dx = x - d.cx;
  const dz = z - d.cz;
  return { x: dx * c + dz * s, z: -dx * s + dz * c };
}

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};
const polar = (angle: number, r: number): Pt => ({ x: Math.cos(angle) * r, z: Math.sin(angle) * r });

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
  plateau: boolean;
  industrial: boolean;
}

/** Pick a generic building: towers near the square, homes everywhere, villas on the plateau. */
function pickKind(u: number, m: Mix): FillerKind {
  if (m.plateau) return u < 0.52 ? "villa" : u < 0.82 ? "house" : "tower";
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
const WIDTH: Record<FillerKind, [number, number]> = {
  skyscraper: [2.8, 3.8],
  tower: [3.2, 4.0],
  block: [3.4, 4.2],
  house: [2.4, 3.0],
  villa: [3.8, 4.6],
  shed: [4.2, 5.0],
};
const TALL: Record<FillerKind, [number, number]> = {
  skyscraper: [0.8, 1.7],
  tower: [0.55, 1.0],
  block: [0.55, 0.95],
  house: [0.8, 1.0],
  villa: [0.85, 1.05],
  shed: [0.8, 1.0],
};

function filler(kind: FillerKind, x: number, z: number, rotationY: number, seed: string, district: DistrictId | null): FillerSpot {
  const h = hashString(seed);
  const a = (h & 0xffff) / 0xffff;
  const b = ((h >>> 16) & 0xffff) / 0xffff;
  const [w0, w1] = WIDTH[kind];
  const [t0, t1] = TALL[kind];
  return { kind, x, z, rotationY, width: w0 + (w1 - w0) * a, tall: t0 + (t1 - t0) * b, tone: ((h >>> 8) & 0xff) / 255, district };
}

// --- the layout ----------------------------------------------------------------------

export function computeLayout(assets: readonly WorldAsset[]): WorldLayout {
  const byDistrict = new Map<DistrictId, string[]>();
  for (const asset of assets) {
    const id = ARCHETYPE_DISTRICT[asset.archetype];
    const bucket = byDistrict.get(id);
    if (bucket) bucket.push(asset.id);
    else byDistrict.set(id, [asset.id]);
  }

  const shapeFor: Record<DistrictId, DistrictShape> = {
    retail: "high-street",
    tech: "campus",
    industry: "industrial",
    finance: "highrise",
    health: "campus",
    funds: "garden",
    treasury: "garden",
  };
  const aspectFor: Record<DistrictId, Pt> = {
    retail: { x: 1.34, z: 0.78 },
    tech: { x: 1.05, z: 1.08 },
    industry: { x: 1.48, z: 0.7 },
    finance: { x: 1.18, z: 0.86 },
    health: { x: 0.98, z: 1.12 },
    funds: { x: 0.92, z: 1.18 },
    treasury: { x: 0.82, z: 1.22 },
  };

  const slots = DISTRICT_IDS.map((id, slot) => {
    const count = byDistrict.get(id)?.length ?? 0;
    if (!count) return { id, slot, count, cap: 0, cols: 0, rows: 0, extent: 0 };
    const cap = capacityFor(count);
    const cols = Math.ceil(Math.sqrt(cap));
    const rows = Math.ceil(cap / cols);
    const extent = 0.5 * Math.hypot(cols * LOT_PITCH * 1.12, rows * LOT_PITCH * 1.12);
    return { id, slot, count, cap, cols, rows, extent };
  });
  const maxExtent = Math.max(0, ...slots.map((slot) => slot.extent));
  const gapAfter = (k: number) => (k === 6 || k === 1 ? RIVER_GAP : k === 4 ? CLIFF_GAP : DISTRICT_GAP);
  const spacing = (k: number, ring: number) => {
    const next = slots[(k + 1) % SLOT_COUNT];
    const needed = slots[k].extent + next.extent + gapAfter(k);
    return 2 * Math.asin(Math.min(1, needed / (2 * ring)));
  };
  const clearance = Math.max(
    PLAZA_RADIUS + 24,
    ...slots.filter((slot) => slot.count > 0).map((slot) => PLAZA_RADIUS + 24 + slot.extent),
  );
  let lo = clearance;
  let hi = 2200;
  for (let i = 0; i < 44; i++) {
    const mid = (lo + hi) / 2;
    const total = slots.reduce((sum, _slot, k) => sum + spacing(k, mid), 0);
    if (total > Math.PI * 2) lo = mid;
    else hi = mid;
  }
  const ring = Math.max(hi * 1.22, clearance * 1.1);
  const raw = slots.map((_slot, k) => spacing(k, ring));
  const slack = (Math.PI * 2 - raw.reduce((sum, n) => sum + n, 0)) / SLOT_COUNT;
  const angleJitter = [0.02, -0.055, 0.075, -0.035, 0.06, -0.07, 0.04];
  const radiusJitter = [1.02, 0.97, 1.045, 0.98, 1.035, 0.955, 1.015];
  const angles: number[] = [];
  let angle = BASE_ANGLE;
  for (let k = 0; k < SLOT_COUNT; k++) {
    angles.push(angle + angleJitter[k]);
    angle += raw[k] + slack;
  }

  const gapAngle = (k: number) => {
    const next = (k + 1) % SLOT_COUNT;
    const to = angles[next] + (next === 0 ? Math.PI * 2 : 0);
    const left = slots[k].extent;
    const right = slots[next].extent;
    const ratio = (left + gapAfter(k) / 2) / Math.max(1, left + right + gapAfter(k));
    return angles[k] + (to - angles[k]) * ratio;
  };
  const ps = gapAngle(4);
  const pe = gapAngle(6);
  const fundsExt = Math.max(slots[5].extent, slots[6].extent, 24);
  const radius = ring + maxExtentOr(maxExtent) + 74;

  const phi1 = pe;
  const phi2 = gapAngle(1);
  const lakeDist = radius + 2;
  const riverRaw: Pt[] = [
    polar(phi1 + 0.04, lakeDist),
    polar(phi1 - 0.025, ring + 10),
    polar(phi1 + 0.025, PLAZA_RADIUS + 26),
  ];
  for (let i = 0; i <= 16; i++) {
    const t = i / 16;
    const a = phi1 + (phi2 - phi1) * t;
    const r = PLAZA_RADIUS + 24 + Math.sin(t * Math.PI * 2.2) * 2.1 + Math.sin(t * Math.PI * 5) * 0.7;
    riverRaw.push(polar(a, r));
  }
  riverRaw.push(
    polar(phi2 - 0.025, PLAZA_RADIUS + 26),
    polar(phi2 + 0.025, ring + 10),
    polar(phi2 - 0.035, radius + 28),
    polar(phi2 + 0.02, radius + 76),
  );
  const terrain = createTerrain({
    cityRadius: radius,
    plazaRadius: PLAZA_RADIUS,
    plateauAngle: (ps + pe) / 2,
    plateauHalfAngle: (pe - ps) / 2,
    plateauInner: Math.max(PLAZA_RADIUS + 30, ring - fundsExt - 22),
    plateauOuter: ring + fundsExt + 24,
    river: chaikin(riverRaw, 3),
    lake: { ...polar(phi1, lakeDist + 7), r: 18 },
    seed: 17,
  });

  const districts: DistrictLayout[] = [];
  const lots = new Map<string, Lot>();
  const aspectForDistrict = aspectFor;

  slots.forEach((slot, k) => {
    if (!slot.count) return;
    const p = polar(angles[k], ring * radiusJitter[k]);
    const theta = (((k * 5 + 2) % 7) - 3) * 0.09 + (k % 2 ? 0.035 : -0.025);
    const aspect = aspectForDistrict[slot.id];
    const halfW = slot.extent * 0.72 * aspect.x;
    const halfH = slot.extent * 0.72 * aspect.z;
    const center = { cx: p.x, cz: p.z, theta };
    const gateAngle = Math.atan2(-p.z, -p.x);
    const gateLX = Math.cos(gateAngle - theta) * (slot.extent + 5);
    const gateLZ = Math.sin(gateAngle - theta) * (slot.extent + 5);
    const gate = toWorld(center, gateLX, gateLZ);
    districts.push({
      id: slot.id,
      slot: k,
      cx: p.x,
      cz: p.z,
      theta,
      shape: shapeFor[slot.id],
      cols: slot.cols,
      rows: slot.rows,
      extent: slot.extent,
      assetCount: slot.count,
      halfW,
      halfH,
      gateX: gate.x,
      gateZ: gate.z,
      gateLX,
      gateLZ,
    });
  });

  const greenSpaces: GreenSpace[] = [
    {
      kind: "city-park",
      ...polar(gapAngle(0), ring * 0.56),
      radiusX: 19,
      radiusZ: 24,
      rotationY: gapAngle(0) + 0.24,
      pond: {
        ...polar(gapAngle(0) + 0.16, ring * 0.56 + 3),
        radiusX: 8.4,
        radiusZ: 5.6,
      },
    },
    {
      kind: "pocket-park",
      ...polar(gapAngle(3), ring * 0.58),
      radiusX: 13,
      radiusZ: 17,
      rotationY: gapAngle(3) - 0.18,
    },
  ];

  const inGreenSpace = (x: number, z: number, extra = 0) => greenSpaces.some((space) => {
    const dx = x - space.x;
    const dz = z - space.z;
    const c = Math.cos(space.rotationY);
    const s = Math.sin(space.rotationY);
    const lx = dx * c + dz * s;
    const lz = -dx * s + dz * c;
    const rx = space.radiusX + extra;
    const rz = space.radiusZ + extra;
    return (lx * lx) / (rx * rx) + (lz * lz) / (rz * rz) < 1;
  });

  const loop: Pt[] = [];
  const LOOP_STEPS = 96;
  // Clean circular arterial boulevard connecting the central plaza to all districts
  const loopRadius = ring * 0.68;
  for (let i = 0; i <= LOOP_STEPS; i++) {
    const a = (i / LOOP_STEPS) * Math.PI * 2;
    loop.push({ x: Math.cos(a) * loopRadius, z: Math.sin(a) * loopRadius });
  }
  loop[loop.length - 1] = { ...loop[0] };

  const nearestOnLoop = (target: Pt) => {
    let best = loop[0];
    let bestDistance = Infinity;
    for (const point of loop) {
      const distance = Math.hypot(point.x - target.x, point.z - target.z);
      if (distance < bestDistance) {
        best = point;
        bestDistance = distance;
      }
    }
    return { x: best.x, z: best.z };
  };

  const roads: RoadSegment[] = [];
  const addRoad = (path: Pt[], width: number, kind: RoadSegment["kind"], sidewalk = true, districtId?: DistrictId) => {
    const first = path[0];
    const last = path[path.length - 1];
    roads.push({
      x1: first.x,
      z1: first.z,
      x2: last.x,
      z2: last.z,
      path,
      width,
      kind,
      sidewalk,
      districtId,
    });
  };
  addRoad(loop, 7.6, "arterial");

  const gateStops: Pt[] = [];
  for (const district of districts) {
    const gate = { x: district.gateX, z: district.gateZ };
    gateStops.push(gate);
    const anchor = nearestOnLoop(gate);
    const mid = { x: (anchor.x + gate.x) / 2, z: (anchor.z + gate.z) / 2 };
    const bend = {
      x: mid.x + (gate.z - anchor.z) * 0.14,
      z: mid.z - (gate.x - anchor.x) * 0.14,
    };
    addRoad(chaikin([anchor, bend, gate], 1), 6.2, "boulevard", true, district.id);

    // Compact urban block loop inside the district core (no huge outer ring)
    const bw = Math.min(20, Math.max(11, district.halfW * 0.48));
    const bh = Math.min(16, Math.max(9, district.halfH * 0.48));
    const c = Math.cos(district.theta);
    const s = Math.sin(district.theta);
    const corners = [
      { x: -bw, z: -bh },
      { x: bw, z: -bh },
      { x: bw, z: bh },
      { x: -bw, z: bh },
    ].map((pt) => ({
      x: district.cx + pt.x * c - pt.z * s,
      z: district.cz + pt.x * s + pt.z * c,
    }));
    const local = [gate, corners[0], corners[1], corners[2], corners[3], { ...gate }];
    addRoad(local, 4.4, "local", true, district.id);
  }

  for (const a of [-Math.PI * 0.48, Math.PI * 0.52]) {
    const target = polar(a, loopRadius);
    const anchor = nearestOnLoop(target);
    const start = polar(a + 0.03, PLAZA_RADIUS - 0.5);
    const p1 = polar(a - 0.05, PLAZA_RADIUS + (loopRadius - PLAZA_RADIUS) * 0.35);
    const p2 = polar(a + 0.05, PLAZA_RADIUS + (loopRadius - PLAZA_RADIUS) * 0.7);
    addRoad(chaikin([start, p1, p2, anchor], 1), 6.8, "boulevard");
  }

  for (const a of [0.18, Math.PI + 0.18]) {
    const startR = ring + maxExtent + 16;
    const start = polar(a, startR);
    const p1 = polar(a + 0.03, startR + 18);
    const p2 = polar(a - 0.02, startR + 36);
    const end = polar(a, radius + 64);
    addRoad(chaikin([start, p1, p2, end], 1), 7.6, "exit");
  }

  const industry = districts.find((d) => d.id === "industry");
  const railEnd = polar(Math.PI * 0.55, loopRadius + 10);
  const railPath = industry
    ? chaikin([
        { x: industry.gateX, z: industry.gateZ },
        { x: (industry.gateX + railEnd.x) * 0.5, z: (industry.gateZ + railEnd.z) * 0.5 + 4 },
        railEnd,
      ], 1)
    : [polar(Math.PI * 0.6, radius * 0.7), railEnd];

  const highways = [
    { path: loop, clear: 12.8 },
    ...roads.filter((road) => road.kind === "exit").map((road) => ({ path: road.path, clear: 13.0 })),
  ];
  const infra = computeInfra({
    plaza: PLAZA_RADIUS,
    radius,
    highways,
    rail: railPath,
    railTerminus: railEnd,
    districtStops: gateStops,
  });

  const nearInfra = (x: number, z: number, extra: number) =>
    [...infra.highways, infra.rail, infra.monorail].some((corridor) =>
      distToPolyline(x, z, corridor.path) < corridor.clear / 2 + extra,
    );
  const nearRoad = (x: number, z: number, extra: number) =>
    roads.some((road) => distToPolyline(x, z, road.path) < road.width / 2 + extra);
  const onPlateau = (x: number, z: number) => terrain.heightAt(x, z) > PLATEAU_HEIGHT - 0.7;

  // --- Urban Block & Lot Placement ---------------------------------------------------
  // In each district, lots and fillers are arranged in structured urban blocks (manzanas)
  // along the street network, ensuring cohesive street walls and active frontages.
  const lotsByDistrict = new Map<DistrictId, Lot[]>();
  for (const district of districts) {
    const ids = [...(byDistrict.get(district.id) ?? [])].sort();
    const localLots: Lot[] = [];
    const highDistrict = district.id === "funds" || district.id === "treasury";

    // 1. Generate structured urban block slot grid for this neighbourhood
    interface CandidateSlot {
      lx: number;
      lz: number;
      p: Pt;
      col: number;
      row: number;
      score: number;
    }
    const candidateSlots: CandidateSlot[] = [];
    const gridCols = Math.max(district.cols + 2, 5);
    const gridRows = Math.max(district.rows + 2, 5);

    for (let r = 0; r < gridRows; r++) {
      for (let c = 0; c < gridCols; c++) {
        const lx = (c - (gridCols - 1) / 2) * LOT_PITCH;
        const lz = (r - (gridRows - 1) / 2) * LOT_PITCH;
        const p = toWorld(district, lx, lz);

        // Verification of terrain, elevation and clearance constraints
        if (!terrain.buildable(p.x, p.z, 2.0)) continue;
        const h = terrain.heightAt(p.x, p.z);
        if (h <= -0.05) continue;
        if (highDistrict ? h <= PLATEAU_HEIGHT - 0.9 : h >= 0.95) continue;
        if (inGreenSpace(p.x, p.z, 3.8)) continue;
        // Strictly clear of transportation corridors (preserves safety margins)
        if (nearInfra(p.x, p.z, 3.8 + 14 / 4)) continue;

        // Proximity score: prefer slots with good street access and balanced block depth
        const distToGate = Math.hypot(p.x - district.gateX, p.z - district.gateZ);
        const distToCenter = Math.hypot(lx, lz);
        candidateSlots.push({ lx, lz, p, col: c, row: r, score: distToCenter * 0.6 + distToGate * 0.4 });
      }
    }

    // Sort candidate slots by prestige/accessibility score
    candidateSlots.sort((a, b) => a.score - b.score || a.col - b.col || a.row - b.row);

    // 2. Deterministically assign lots to candidate block slots
    for (const id of ids) {
      const seed = hashString(id);
      let chosen: CandidateSlot | null = null;

      // Deterministic search starting from hash
      const startIndex = candidateSlots.length > 0 ? (seed >>> 0) % candidateSlots.length : 0;
      for (let offset = 0; offset < candidateSlots.length; offset++) {
        const idx = (startIndex + offset) % candidateSlots.length;
        const candidate = candidateSlots[idx];
        if (localLots.some((lot) => Math.hypot(lot.x - candidate.p.x, lot.z - candidate.p.z) < LOT_PITCH - 1e-5)) {
          continue;
        }
        chosen = candidate;
        break;
      }

      // Safe fallback if block capacity expanded
      if (!chosen) {
        for (let attempt = 0; attempt < 2000 && !chosen; attempt++) {
          const col = attempt % (gridCols + 4);
          const row = Math.floor(attempt / (gridCols + 4));
          const lx = (col - (gridCols + 3) / 2) * LOT_PITCH;
          const lz = (row - (gridRows + 3) / 2) * LOT_PITCH;
          const p = toWorld(district, lx, lz);
          const h = terrain.heightAt(p.x, p.z);
          if (h <= -0.05 || !terrain.buildable(p.x, p.z, 1.8)) continue;
          if (highDistrict ? h <= PLATEAU_HEIGHT - 0.9 : h >= 0.95) continue;
          if (inGreenSpace(p.x, p.z, 3.5) || nearInfra(p.x, p.z, 3.8 + 14 / 4)) continue;
          if (localLots.some((lot) => Math.hypot(lot.x - p.x, lot.z - p.z) < LOT_PITCH - 1e-5)) continue;
          chosen = { lx, lz, p, col, row, score: attempt };
        }
      }

      if (!chosen) continue;

      const toAccess = Math.atan2(district.gateZ - chosen.p.z, district.gateX - chosen.p.x);
      const quarter = Math.round((toAccess + district.theta) / (Math.PI / 2)) * (Math.PI / 2);
      const lot: Lot = {
        assetId: id,
        district: district.id,
        x: chosen.p.x,
        z: chosen.p.z,
        rotationY: quarter - district.theta,
        col: chosen.col,
        row: chosen.row,
        lx: chosen.lx,
        lz: chosen.lz,
        fx: Math.round(Math.sin(quarter)),
        fz: Math.round(Math.cos(quarter)),
      };
      lots.set(id, lot);
      localLots.push(lot);
    }
    lotsByDistrict.set(district.id, localLots);
  }

  const civicKinds: CivicKind[] = ["bank", "newsKiosk", "observatory", "townHall"];
  const civic = civicKinds.map((kind, i) => {
    const a = Math.PI / 4 + (i * Math.PI) / 2;
    return { kind, x: Math.cos(a) * 9, z: Math.sin(a) * 9 };
  });

  // --- Filler Buildings (Atrezzo Manzanas & Urban Fabric) -----------------------------
  const fillerSpots: FillerSpot[] = [];
  const clearOfLots = (x: number, z: number, minDistance: number) =>
    [...lots.values()].every((lot) => Math.hypot(lot.x - x, lot.z - z) >= minDistance);
  const clearOfFillers = (x: number, z: number, minDistance: number) =>
    fillerSpots.every((spot) => Math.hypot(spot.x - x, spot.z - z) >= minDistance);
  const addFiller = (kind: FillerKind, x: number, z: number, seed: string, district: DistrictId | null) => {
    const theta = (hashString(seed) / 0xffffffff) * Math.PI * 2;
    fillerSpots.push(filler(kind, x, z, theta, seed, district));
  };

  // 1. Manzanas within districts: companion filler blocks alongside corporate holdings
  for (const district of districts) {
    const count = Math.max(9, Math.ceil(district.assetCount * 0.62));
    const isPlateau = district.id === "funds" || district.id === "treasury";
    let placed = 0;

    // First, place filler buildings in block gaps with guaranteed clearance
    for (let i = 0; i < count && placed < count; i++) {
      const seed = hashString(district.id + ":block:" + i);
      let found: Pt | null = null;
      for (let attempt = 0; attempt < 240; attempt++) {
        const u1 = hash2(seed, attempt, 711);
        const u2 = hash2(seed, attempt, 812);
        const col = Math.floor(u1 * (district.cols + 4)) - (district.cols + 3) / 2;
        const row = Math.floor(u2 * (district.rows + 4)) - (district.rows + 3) / 2;
        // Half-step offset so fillers naturally sit on the edges and corners of the holding grid
        const lx = (col + 0.5) * (LOT_PITCH * 0.65);
        const lz = (row + 0.5) * (LOT_PITCH * 0.65);
        const p = toWorld(district, lx, lz);

        if (!terrain.buildable(p.x, p.z, 2.0) || inGreenSpace(p.x, p.z, 2.0)) continue;
        const h = terrain.heightAt(p.x, p.z);
        if (h <= -0.05) continue;
        if (isPlateau ? h <= PLATEAU_HEIGHT - 0.9 : h >= 1.0) continue;
        if (nearInfra(p.x, p.z, 2.8) || nearRoad(p.x, p.z, 2.6)) continue;
        if (!clearOfLots(p.x, p.z, 5.8) || !clearOfFillers(p.x, p.z, 5.8)) continue;
        found = p;
        break;
      }
      if (!found) continue;

      const u = hash2(seed, i, 921);
      const mix: Mix = {
        cbd: district.id === "finance" ? 0.92 : district.id === "tech" ? 0.72 : 0.34,
        residential: RESIDENTIAL[district.id],
        plateau: onPlateau(found.x, found.z),
        industrial: district.id === "industry",
      };
      addFiller(pickKind(u, mix), found.x, found.z, district.id + ":" + i, district.id);
      placed++;
    }
  }

  // 2. City-wide urban fabric: boulevard corridors and outer street blocks
  const reach = radius + 18;
  const step = FABRIC_PITCH;
  const half = Math.ceil(reach / step);
  for (let gx = -half; gx <= half; gx++) {
    for (let gz = -half; gz <= half; gz++) {
      const seed = hash2(gx, gz, 909);
      const x = gx * step + (seed - 0.5) * 5.2;
      const z = gz * step + (hash2(gx, gz, 910) - 0.5) * 5.2;
      const r = Math.hypot(x, z);
      if (r < PLAZA_RADIUS + 7 || r > reach) continue;
      const density = 1 - smooth(radius * 0.66, radius + 14, r);
      if (hash2(gx, gz, 911) > 0.34 + 0.66 * density) continue;
      if (districts.some((d) => Math.hypot(x - d.cx, z - d.cz) < d.extent + 4)) continue;
      if (nearRoad(x, z, 3.4) || nearInfra(x, z, 3.4) || inGreenSpace(x, z, 3)) continue;
      if (!terrain.buildable(x, z, 3.2)) continue;
      if (terrain.heightAt(x, z) <= -0.05) continue;
      if (!clearOfLots(x, z, 5.8) || !clearOfFillers(x, z, 5.8)) continue;
      const near = [...districts].sort((a, b) => Math.hypot(x - a.cx, z - a.cz) - Math.hypot(x - b.cx, z - b.cz))[0] ?? null;
      const mix: Mix = {
        cbd: Math.max(0, 1 - smooth(PLAZA_RADIUS + 4, PLAZA_RADIUS + 90, r)) + (near?.id === "finance" ? 0.22 : 0),
        residential: near ? RESIDENTIAL[near.id] : 0.65,
        plateau: onPlateau(x, z),
        industrial: near?.id === "industry",
      };
      addFiller(pickKind(hash2(gx, gz, 912), mix), x, z, "outer:" + gx + ":" + gz, near?.id ?? null);
    }
  }

  return { lots, districts, roads, civic, filler: fillerSpots, greenSpaces, terrain, infra, radius };
}

function maxExtentOr(e: number): number {
  return e > 0 ? e : 0;
}

export { RIVER_HALF_WIDTH };
