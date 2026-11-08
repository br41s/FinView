import type { DistrictLayout, Lot, RoadSegment } from "./townLayout";

export interface Point {
  x: number;
  z: number;
}

interface Projection {
  point: Point;
  segment: number;
  distance: number;
}

function project(line: readonly Point[], target: Point): Projection {
  let best: Projection = { point: line[0], segment: 0, distance: Infinity };
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1];
    const b = line[i];
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const len2 = dx * dx + dz * dz;
    const t = len2 === 0 ? 0 : Math.max(0, Math.min(1, ((target.x - a.x) * dx + (target.z - a.z) * dz) / len2));
    const point = { x: a.x + dx * t, z: a.z + dz * t };
    const distance = Math.hypot(target.x - point.x, target.z - point.z);
    if (distance < best.distance) best = { point, segment: i - 1, distance };
  }
  return best;
}

export function routeLength(p: readonly Point[]): number {
  let total = 0;
  for (let i = 1; i < p.length; i++) total += Math.hypot(p[i].x - p[i - 1].x, p[i].z - p[i - 1].z);
  return total;
}

/** Position along a polyline, clamped to its ends, plus the heading there. */
export function pointAlong(p: readonly Point[], dist: number): Point & { heading: number } {
  let left = Math.max(0, dist);
  for (let i = 1; i < p.length; i++) {
    const dx = p[i].x - p[i - 1].x;
    const dz = p[i].z - p[i - 1].z;
    const len = Math.hypot(dx, dz);
    if (left <= len || i === p.length - 1) {
      const t = len === 0 ? 1 : Math.min(1, left / len);
      return { x: p[i - 1].x + dx * t, z: p[i - 1].z + dz * t, heading: Math.atan2(dx, dz) };
    }
    left -= len;
  }
  return { x: p[0].x, z: p[0].z, heading: 0 };
}

function dedupe(points: Point[]): Point[] {
  return points.filter((p, i) => i === 0 || Math.hypot(p.x - points[i - 1].x, p.z - points[i - 1].z) > 1e-5);
}

function projectionToEndpoint(line: readonly Point[], p: Projection, forward: boolean): Point[] {
  const out: Point[] = [p.point];
  if (forward) {
    for (let i = p.segment + 1; i < line.length; i++) out.push(line[i]);
  } else {
    for (let i = p.segment; i >= 0; i--) out.push(line[i]);
  }
  return dedupe(out);
}

function nearestVertex(line: readonly Point[], point: Point): number {
  let index = 0;
  let distance = Infinity;
  for (let i = 0; i < line.length; i++) {
    const d = Math.hypot(line[i].x - point.x, line[i].z - point.z);
    if (d < distance) {
      distance = d;
      index = i;
    }
  }
  return index;
}

/** Shortest direction along a closed road, from one connected junction to another. */
function shortestLoopArc(line: readonly Point[], from: Point, to: Point): Point[] {
  const count = line.length > 2 && Math.hypot(line[0].x - line[line.length - 1].x, line[0].z - line[line.length - 1].z) < 1e-5
    ? line.length - 1
    : line.length;
  if (count < 2) return [from, to];
  const a = nearestVertex(line.slice(0, count), from);
  const b = nearestVertex(line.slice(0, count), to);
  const walk = (step: 1 | -1) => {
    const result: Point[] = [line[a]];
    let i = a;
    for (let guard = 0; guard <= count; guard++) {
      if (i === b) break;
      i = (i + step + count) % count;
      result.push(line[i]);
    }
    return result;
  };
  const forward = walk(1);
  const backward = walk(-1);
  const selected = routeLength(forward) <= routeLength(backward) ? forward : backward;
  selected[0] = from;
  selected[selected.length - 1] = to;
  return selected;
}

/**
 * Company access to the civic centre follows the local neighbourhood loop, its curved
 * boulevard, the arterial ring and a central boulevard. This is also the route used by
 * delivery vans and event visitors, so they no longer cut across the city diagonally.
 */
export function routeToPlaza(lot: Lot, district: DistrictLayout, roads: readonly RoadSegment[] = []): Point[] {
  const local = roads.find((road) => road.kind === "local" && road.districtId === district.id);
  const districtBoulevard = roads.find((road) => road.kind === "boulevard" && road.districtId === district.id);
  const arterial = roads.find((road) => road.kind === "arterial");
  const plazaConnector = roads
    .filter((road) => road.kind === "boulevard" && !road.districtId)
    .sort((a, b) => Math.hypot(a.path[0].x, a.path[0].z) - Math.hypot(b.path[0].x, b.path[0].z))[0];

  if (!local || !districtBoulevard || !arterial || !plazaConnector) {
    const gate = { x: district.gateX, z: district.gateZ };
    const dx = gate.x - lot.x;
    const dz = gate.z - lot.z;
    const mid = { x: lot.x + dx * 0.46 - dz * 0.1, z: lot.z + dz * 0.46 + dx * 0.1 };
    const length = Math.max(1, Math.hypot(gate.x, gate.z));
    const end = { x: gate.x * (14 / length), z: gate.z * (14 / length) };
    return dedupe([{ x: lot.x, z: lot.z }, mid, gate, end]);
  }

  const onLocal = project(local.path, lot);
  const forward = projectionToEndpoint(local.path, onLocal, true);
  const backward = projectionToEndpoint(local.path, onLocal, false);
  const localToGate = routeLength(forward) <= routeLength(backward) ? forward : backward;
  const gate = { x: district.gateX, z: district.gateZ };
  const arterialAnchor = districtBoulevard.path[0];
  const gateToArterial = [...districtBoulevard.path].reverse();
  gateToArterial[0] = gate;
  gateToArterial[gateToArterial.length - 1] = arterialAnchor;

  const plazaAnchor = plazaConnector.path[plazaConnector.path.length - 1];
  const arterialArc = shortestLoopArc(arterial.path, arterialAnchor, plazaAnchor);
  const toPlaza = [...plazaConnector.path].reverse();
  toPlaza[0] = plazaAnchor;

  const outwardX = lot.x - district.cx;
  const outwardZ = lot.z - district.cz;
  const outwardLength = Math.hypot(outwardX, outwardZ) || 1;
  const normalX = outwardX / outwardLength;
  const normalZ = outwardZ / outwardLength;
  const approach = {
    x: lot.x + (onLocal.point.x - lot.x) * 0.52 + normalX * 1.2,
    z: lot.z + (onLocal.point.z - lot.z) * 0.52 + normalZ * 1.2,
  };
  return dedupe([
    { x: lot.x, z: lot.z },
    approach,
    onLocal.point,
    ...localToGate.slice(1),
    ...gateToArterial.slice(1),
    ...arterialArc.slice(1),
    ...toPlaza.slice(1),
  ]);
}
