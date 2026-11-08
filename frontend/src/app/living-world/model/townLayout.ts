import { ARCHETYPE_DISTRICT } from "./archetypes";
import { computeInfra, type Infra } from "./infra";
import { hash2, hashString } from "./rng";
import { MAX_FOOTPRINT } from "./scale";
import { PLATEAU_HEIGHT, RIVER_HALF_WIDTH, chaikin, createTerrain, distToPolyline, type Pt, type Terrain } from "./terrain";
import { DISTRICT_IDS, type DistrictId, type WorldAsset } from "./types";

/**
 * Town layout (spec §8): a city that grew around a central square, with a river bending
 * round it, a plateau for the funds and treasury districts and mountains behind.
 *
 * Districts have a fixed place on the compass (their index in `DISTRICT_IDS`), so adding a
 * holding never turns the town. A district is a patch of street grid, slightly rotated from
 * its neighbours; holdings take slots of it by hash and the rest of the grid, plus the land
 * between districts, is filled with generic buildings (`FillerSpot`) so there is no bare
 * ground between "areas". The layout is a pure function of the asset ids: it never reads
 * weights, prices or events, so a price refresh cannot move a building.
 */

/** Distance between lot centres: largest footprint + a street. */
export const LOT_PITCH = MAX_FOOTPRINT + 2.5;
export const PLAZA_RADIUS = 16;

const DISTRICT_GAP = 6;
/** Extra room where the river runs between two districts (banks included). */
const RIVER_GAP = 28;
/** Extra room at the plateau's cliff edge. */
const CLIFF_GAP = 14;
/** The river runs between these compass slots (6|0 and 1|2); the cliff is 4|5. */
const SLOT_COUNT = DISTRICT_IDS.length;
const BASE_ANGLE = -Math.PI / 2;
const FABRIC_PITCH = 7.6;

export interface Lot {
  assetId: string;
  district: DistrictId;
  x: number;
  z: number;
  /** Faces the central square, in quarter turns of the district's own grid. */
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
  if (m.plateau) return u < 0.5 ? "villa" : u < 0.82 ? "house" : "tower";
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
  for (const a of assets) {
    const d = ARCHETYPE_DISTRICT[a.archetype];
    const list = byDistrict.get(d);
    if (list) list.push(a.id);
    else byDistrict.set(d, [a.id]);
  }

  // Size of each compass slot; an absent district is a slot of zero size.
  const slots = DISTRICT_IDS.map((id, slot) => {
    const count = byDistrict.get(id)?.length ?? 0;
    if (count === 0) return { id, slot, count, cap: 0, cols: 0, rows: 0, extent: 0 };
    const cap = capacityFor(count);
    const cols = Math.ceil(Math.sqrt(cap));
    const rows = Math.ceil(cap / cols);
    return { id, slot, count, cap, cols, rows, extent: 0.5 * Math.hypot(cols * LOT_PITCH, rows * LOT_PITCH) };
  });
  const maxExtent = Math.max(0, ...slots.map((s) => s.extent));

  // Gap between slot k and k+1 on the ring; wider where the river or the cliff passes.
  const gapAfter = (k: number) => (k === 6 || k === 1 ? RIVER_GAP : k === 4 ? CLIFF_GAP : DISTRICT_GAP);
  const spacing = (k: number, ring: number) => {
    const next = slots[(k + 1) % SLOT_COUNT];
    const need = slots[k].extent + next.extent + gapAfter(k);
    return 2 * Math.asin(Math.min(1, need / (2 * ring)));
  };
  const clearance = Math.max(
    PLAZA_RADIUS + 22,
    ...slots.filter((s) => s.count > 0).map((s) => PLAZA_RADIUS + 22 + s.extent),
  );
  // Smallest ring at which the districts fit round the compass, then at least the clearance.
  let lo = clearance;
  let hi = 2000;
  for (let i = 0; i < 40; i++) {
    const mid = (lo + hi) / 2;
    const sum = slots.reduce((acc, _s, k) => acc + spacing(k, mid), 0);
    if (sum > 2 * Math.PI) lo = mid;
    else hi = mid;
  }
  const ring = Math.max(hi, clearance);
  const raw = slots.map((_s, k) => spacing(k, ring));
  const slack = (2 * Math.PI - raw.reduce((a, b) => a + b, 0)) / SLOT_COUNT;
  const angles: number[] = [];
  let a = BASE_ANGLE;
  for (let k = 0; k < SLOT_COUNT; k++) {
    angles.push(a);
    a += raw[k] + slack;
  }

  const districts: DistrictLayout[] = [];
  const lots = new Map<string, Lot>();
  const free: Array<{ d: DistrictLayout; lx: number; lz: number; slot: number }> = [];

  const radius = ring + maxExtentOr(maxExtent);

  // Terrain first: it only needs the compass and the sizes, never the lots.
  const gapAngle = (k: number) => {
    const next = (k + 1) % SLOT_COUNT;
    const to = angles[next] + (next === 0 ? 2 * Math.PI : 0);
    // The middle of the free gap, not of the angle: a large district leaves less room beside it.
    const w = (slots[k].extent + gapAfter(k) / 2) / (slots[k].extent + slots[next].extent + gapAfter(k));
    return angles[k] + (to - angles[k]) * w;
  };
  const ps = gapAngle(4);
  const pe = gapAngle(6);
  const funds = [slots[5].extent, slots[6].extent];
  const fundsExt = Math.max(0, ...funds) || 24;
  const rA = PLAZA_RADIUS + 11;
  const phi1 = pe;
  const phi2 = gapAngle(1);
  const lakeDist = radius + 6;
  const riverRaw: Pt[] = [
    polar(phi1 + 0.03, lakeDist),
    polar(phi1 - 0.02, ring + 6),
    polar(phi1 + 0.02, rA + 10),
  ];
  const steps = 10;
  for (let i = 0; i <= steps; i++) riverRaw.push(polar(phi1 + ((phi2 - phi1) * i) / steps, rA + Math.sin(i * 1.3) * 1.2));
  riverRaw.push(polar(phi2 - 0.02, rA + 10), polar(phi2 + 0.02, ring + 6), polar(phi2 - 0.03, radius + 26), polar(phi2 + 0.02, radius + 70));
  const terrain = createTerrain({
    cityRadius: radius,
    plazaRadius: PLAZA_RADIUS,
    plateauAngle: (ps + pe) / 2,
    plateauHalfAngle: (pe - ps) / 2,
    plateauInner: Math.max(PLAZA_RADIUS + 22, ring - fundsExt - 8),
    plateauOuter: ring + fundsExt + 10,
    river: chaikin(riverRaw, 3),
    lake: { ...polar(phi1, lakeDist + 8), r: 15 },
    seed: 7,
  });

  const infra = computeInfra({ plaza: PLAZA_RADIUS, radius, gap: gapAngle, plateauStart: ps, plateauEnd: pe });
  const corridors = [...infra.highways, infra.rail, infra.monorail];
  /** Within a transport corridor (plus `extra`): nothing is built there. */
  const nearInfra = (x: number, z: number, extra: number) => corridors.some((c) => distToPolyline(x, z, c.path) < c.clear / 2 + extra);

  slots.forEach((s, k) => {
    if (s.count === 0) return;
    const p = polar(angles[k], ring);
    const theta = (((k * 5 + 2) % 7) - 3) * 0.06;
    const halfW = (s.cols * LOT_PITCH) / 2;
    const halfH = (s.rows * LOT_PITCH) / 2;
    // The grid corner nearest the origin, found in the district's own axes.
    const base = { cx: p.x, cz: p.z, theta };
    const o = toLocal(base, 0, 0);
    const gateLX = (o.x >= 0 ? 1 : -1) * halfW;
    const gateLZ = (o.z >= 0 ? 1 : -1) * halfH;
    const gate = toWorld(base, gateLX, gateLZ);
    const d: DistrictLayout = {
      id: s.id,
      slot: k,
      cx: p.x,
      cz: p.z,
      theta,
      cols: s.cols,
      rows: s.rows,
      extent: s.extent,
      assetCount: s.count,
      halfW,
      halfH,
      gateX: gate.x,
      gateZ: gate.z,
      gateLX,
      gateLZ,
    };
    districts.push(d);

    // Open addressing from a hash of the id; ids are visited in sorted order so the
    // result does not depend on the order the holdings arrived in.
    const taken = new Array<boolean>(s.cap).fill(false);
    for (const id of [...byDistrict.get(s.id)!].sort()) {
      let slot = hashString(id) % s.cap;
      while (taken[slot]) slot = (slot + 1) % s.cap;
      taken[slot] = true;
      const col = slot % s.cols;
      const row = Math.floor(slot / s.cols);
      const lx = (col - (s.cols - 1) / 2) * LOT_PITCH;
      const lz = (row - (s.rows - 1) / 2) * LOT_PITCH;
      const w = toWorld(d, lx, lz);
      // Face the square, in quarter turns of the district's own grid.
      const toSquare = Math.atan2(-w.x, -w.z) + theta;
      const quarter = Math.round(toSquare / (Math.PI / 2)) * (Math.PI / 2);
      lots.set(id, {
        assetId: id,
        district: s.id,
        x: w.x,
        z: w.z,
        rotationY: quarter - theta,
        col,
        row,
        lx,
        lz,
        fx: Math.round(Math.sin(quarter)),
        fz: Math.round(Math.cos(quarter)),
      });
    }
    taken.forEach((t, slot) => {
      if (!t) free.push({ d, lx: ((slot % s.cols) - (s.cols - 1) / 2) * LOT_PITCH, lz: (Math.floor(slot / s.cols) - (s.rows - 1) / 2) * LOT_PITCH, slot });
    });
  });

  // One boulevard per district, from the plaza to the grid corner facing it.
  const roads: RoadSegment[] = districts.map((d) => ({ x1: 0, z1: 0, x2: d.gateX, z2: d.gateZ }));

  const civicKinds: CivicKind[] = ["bank", "newsKiosk", "observatory", "townHall"];
  const civic = civicKinds.map((kind, i) => {
    const ang = Math.PI / 4 + (i * Math.PI) / 2;
    return { kind, x: Math.cos(ang) * 9, z: Math.sin(ang) * 9 };
  });

  // --- generic buildings --------------------------------------------------------------
  const fillerSpots: FillerSpot[] = [];
  const onPlateau = (x: number, z: number) => terrain.heightAt(x, z) > PLATEAU_HEIGHT - 0.4;
  const cbdAt = (x: number, z: number, d: DistrictLayout | null) =>
    Math.min(1, 1 - smooth(PLAZA_RADIUS + 4, PLAZA_RADIUS + 60, Math.hypot(x, z)) + (d?.id === "finance" ? 0.35 : 0));

  // Empty slots of each district's own grid.
  for (const f of free) {
    const w = toWorld(f.d, f.lx, f.lz);
    if (!terrain.buildable(w.x, w.z, 2.5) || nearInfra(w.x, w.z, 3)) continue;
    const seed = `${f.d.id}:${f.slot}`;
    const kind = pickKind(hash2(f.slot, f.d.slot, 11), {
      cbd: cbdAt(w.x, w.z, f.d),
      residential: RESIDENTIAL[f.d.id],
      plateau: onPlateau(w.x, w.z),
      industrial: f.d.id === "industry",
    });
    const quarter = Math.round((Math.atan2(-w.x, -w.z) + f.d.theta) / (Math.PI / 2)) * (Math.PI / 2);
    fillerSpots.push(filler(kind, w.x, w.z, quarter - f.d.theta, seed, f.d.id));
  }

  // The land between districts: a looser grid, thinning out towards the edge of town.
  const reach = radius + 18;
  const half = Math.ceil(reach / FABRIC_PITCH);
  for (let gx = -half; gx <= half; gx++) {
    for (let gz = -half; gz <= half; gz++) {
      const x = gx * FABRIC_PITCH + (hash2(gx, gz, 1) - 0.5) * 2;
      const z = gz * FABRIC_PITCH + (hash2(gx, gz, 2) - 0.5) * 2;
      const r = Math.hypot(x, z);
      if (r < PLAZA_RADIUS + 3 || r > reach) continue;
      const density = 1 - smooth(radius * 0.7, radius + 14, r);
      if (hash2(gx, gz, 3) > 0.5 + 0.5 * density) continue;
      if (districts.some((d) => {
        const l = toLocal(d, x, z);
        return Math.abs(l.x) < d.halfW + 2.5 && Math.abs(l.z) < d.halfH + 2.5;
      })) continue;
      if (roads.some((rd) => distToSegment(x, z, rd.x1, rd.z1, rd.x2, rd.z2) < 6)) continue;
      if (!terrain.buildable(x, z, 3.2) || nearInfra(x, z, 3.5)) continue;
      // Align with the nearest district's grid so neighbourhoods read as patches.
      let near: DistrictLayout | null = null;
      let best = Infinity;
      for (const d of districts) {
        const dd = Math.hypot(x - d.cx, z - d.cz);
        if (dd < best) {
          best = dd;
          near = d;
        }
      }
      const theta = near?.theta ?? 0;
      const quarter = Math.round((Math.atan2(-x, -z) + theta) / (Math.PI / 2)) * (Math.PI / 2);
      const kind = pickKind(hash2(gx, gz, 4), {
        cbd: cbdAt(x, z, near),
        residential: near ? RESIDENTIAL[near.id] : 0.6,
        plateau: onPlateau(x, z),
        industrial: near?.id === "industry" && best < (near?.extent ?? 0) + 14,
      });
      fillerSpots.push(filler(kind, x, z, quarter - theta, `f:${gx}:${gz}`, near?.id ?? null));
    }
  }

  return { lots, districts, roads, civic, filler: fillerSpots, terrain, infra, radius: districts.length === 0 ? PLAZA_RADIUS + 30 : radius };
}

function maxExtentOr(e: number): number {
  return e > 0 ? e : 0;
}

function distToSegment(px: number, pz: number, x1: number, z1: number, x2: number, z2: number): number {
  const dx = x2 - x1;
  const dz = z2 - z1;
  const l2 = dx * dx + dz * dz;
  const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - x1) * dx + (pz - z1) * dz) / l2));
  return Math.hypot(px - (x1 + t * dx), pz - (z1 + t * dz));
}

export { RIVER_HALF_WIDTH };
