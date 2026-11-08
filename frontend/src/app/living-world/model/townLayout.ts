import { ARCHETYPE_DISTRICT } from "./archetypes";
import { hashString } from "./rng";
import { MAX_FOOTPRINT } from "./scale";
import { DISTRICT_IDS, type DistrictId, type WorldAsset } from "./types";

/**
 * Town layout (spec §8): one compact town, districts on a ring around a central square.
 *
 * The layout is a pure function of the asset ids. It never reads weights, prices or
 * events, so a price refresh cannot move a building; only a changed set of holdings
 * can. Every lot has the same pitch (the largest footprint plus a street), so a
 * building that grows a tier never collides with its neighbour.
 */

/** Distance between lot centres: largest footprint + a street. */
export const LOT_PITCH = MAX_FOOTPRINT + 2.5;
export const PLAZA_RADIUS = 16;
const DISTRICT_GAP = 7;

export interface Lot {
  assetId: string;
  district: DistrictId;
  x: number;
  z: number;
  /** Quarter-turn, front facing the central square. */
  rotationY: number;
  col: number;
  row: number;
}

export interface DistrictLayout {
  id: DistrictId;
  cx: number;
  cz: number;
  cols: number;
  rows: number;
  /** Radius of the circle that encloses the district's lot grid. */
  extent: number;
  assetCount: number;
  /** Half-sizes of the paved pad (lots plus the outer street). */
  halfW: number;
  halfH: number;
  /** Pad corner closest to the plaza: where the boulevard meets the district. */
  gateX: number;
  gateZ: number;
}

export interface RoadSegment {
  x1: number;
  z1: number;
  x2: number;
  z2: number;
}

export type CivicKind = "bank" | "newsKiosk" | "observatory" | "townHall";
export interface CivicSite {
  kind: CivicKind;
  x: number;
  z: number;
}

export interface WorldLayout {
  lots: Map<string, Lot>;
  districts: DistrictLayout[];
  roads: RoadSegment[];
  civic: CivicSite[];
  /** Radius of the whole town around the origin, for "fit to view". */
  radius: number;
}

/** Lot capacity grows in steps of 4 with ~25 % slack, so streets are not all full. */
export function capacityFor(count: number): number {
  return Math.max(4, Math.ceil((count * 1.25) / 4) * 4);
}

export function computeLayout(assets: readonly WorldAsset[]): WorldLayout {
  const byDistrict = new Map<DistrictId, string[]>();
  for (const a of assets) {
    const d = ARCHETYPE_DISTRICT[a.archetype];
    const list = byDistrict.get(d);
    if (list) list.push(a.id);
    else byDistrict.set(d, [a.id]);
  }

  const present = DISTRICT_IDS.filter((d) => (byDistrict.get(d)?.length ?? 0) > 0);
  const n = present.length;

  const sizes = present.map((id) => {
    const count = byDistrict.get(id)!.length;
    const cap = capacityFor(count);
    const cols = Math.ceil(Math.sqrt(cap));
    const rows = Math.ceil(cap / cols);
    const extent = 0.5 * Math.hypot(cols * LOT_PITCH, rows * LOT_PITCH);
    return { id, count, cap, cols, rows, extent };
  });

  // Ring radius: clear the plaza, and keep neighbours (equal-angle chord) apart.
  let ringRadius = 0;
  for (let i = 0; i < n; i++) {
    ringRadius = Math.max(ringRadius, PLAZA_RADIUS + sizes[i].extent + DISTRICT_GAP);
    if (n > 1) {
      const next = sizes[(i + 1) % n];
      const need = sizes[i].extent + next.extent + DISTRICT_GAP;
      const chordFactor = n === 2 ? 2 : 2 * Math.sin(Math.PI / n);
      ringRadius = Math.max(ringRadius, need / chordFactor);
    }
  }

  const districts: DistrictLayout[] = [];
  const lots = new Map<string, Lot>();

  sizes.forEach((s, i) => {
    const angle = -Math.PI / 2 + (2 * Math.PI * i) / n;
    const cx = n === 1 ? 0 : Math.cos(angle) * ringRadius;
    const cz = n === 1 ? ringRadius : Math.sin(angle) * ringRadius;
    const halfW = (s.cols * LOT_PITCH) / 2;
    const halfH = (s.rows * LOT_PITCH) / 2;
    // Toward the origin; a district sitting on an axis picks the +side, deterministically.
    const sx = cx > 0 ? -1 : 1;
    const sz = cz > 0 ? -1 : 1;
    districts.push({
      id: s.id,
      cx,
      cz,
      cols: s.cols,
      rows: s.rows,
      extent: s.extent,
      assetCount: s.count,
      halfW,
      halfH,
      gateX: cx + sx * halfW,
      gateZ: cz + sz * halfH,
    });

    // Open addressing from a hash of the id; ids are visited in sorted order so the
    // result does not depend on the order the holdings arrived in.
    const taken = new Array<boolean>(s.cap).fill(false);
    const ids = [...byDistrict.get(s.id)!].sort();
    for (const id of ids) {
      let slot = hashString(id) % s.cap;
      while (taken[slot]) slot = (slot + 1) % s.cap;
      taken[slot] = true;
      const col = slot % s.cols;
      const row = Math.floor(slot / s.cols);
      const x = cx + (col - (s.cols - 1) / 2) * LOT_PITCH;
      const z = cz + (row - (s.rows - 1) / 2) * LOT_PITCH;
      const facing = Math.atan2(-x, -z);
      lots.set(id, {
        assetId: id,
        district: s.id,
        x,
        z,
        rotationY: Math.round(facing / (Math.PI / 2)) * (Math.PI / 2),
        col,
        row,
      });
    }
  });

  // One boulevard per district, from the plaza to the pad corner facing it.
  const roads: RoadSegment[] = districts.map((d) => ({ x1: 0, z1: 0, x2: d.gateX, z2: d.gateZ }));

  const civicKinds: CivicKind[] = ["bank", "newsKiosk", "observatory", "townHall"];
  const civic = civicKinds.map((kind, i) => {
    const a = Math.PI / 4 + (i * Math.PI) / 2;
    return { kind, x: Math.cos(a) * 9, z: Math.sin(a) * 9 };
  });

  const radius = n === 0 ? PLAZA_RADIUS : ringRadius + Math.max(...sizes.map((s) => s.extent));
  return { lots, districts, roads, civic, radius };
}
