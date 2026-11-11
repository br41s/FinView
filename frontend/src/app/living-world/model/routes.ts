import { routeFromLot, type DistrictLayout, type Lot, type RoadSegment, type WorldLayout } from "./townLayout";

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

/** Offset a company-to-centre route onto the pavement beside each road segment. */
export function sidewalkRoute(route: readonly Point[], roads: readonly RoadSegment[], side: 1 | -1 = 1): Point[] {
  if (route.length < 2 || roads.length === 0) return [...route];
  return route.map((point, i) => {
    const previous = route[Math.max(0, i - 1)];
    const next = route[Math.min(route.length - 1, i + 1)];
    const dx = next.x - previous.x;
    const dz = next.z - previous.z;
    const length = Math.hypot(dx, dz) || 1;
    const normalX = -dz / length;
    const normalZ = dx / length;
    let nearest: RoadSegment | null = null;
    let nearestDistance = Infinity;
    for (const road of roads) {
      const candidate = project(road.path, point);
      if (candidate.distance < nearestDistance) {
        nearestDistance = candidate.distance;
        nearest = road;
      }
    }
    const offset = nearest ? nearest.width / 2 + nearest.walk / 2 : 3.6;
    return { x: point.x + normalX * offset * side, z: point.z + normalZ * offset * side };
  });
}

/**
 * A holding's route to the plaza: out of its door onto the street it fronts, then the shortest
 * way along the street graph to the nearest plaza gate, then a few steps onto the plaza. It is
 * also the route of delivery vans and event visitors, so they follow real streets.
 */
export function routeToPlaza(lot: Lot, _district: DistrictLayout, layout: Pick<WorldLayout, "graph">): Point[] {
  return dedupe(routeFromLot(layout, lot));
}
