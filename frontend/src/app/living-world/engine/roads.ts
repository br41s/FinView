import * as THREE from "three";
import { carriage, type CityGraph, type GEdge, type GNode } from "../model/cityGraph";
import type { V } from "../model/cityGeometry";
import type { Block } from "../model/cityLots";
import type { WorldLayout } from "../model/townLayout";
import { Builder } from "./buildingFactory";

/**
 * Streets, junctions, crosswalks, pavements, bridges and park paths, built from the street
 * graph. Everything flat is one vertex-coloured mesh (a handful of layers a few centimetres
 * apart), the small furniture another: two draw calls for the whole street network.
 *
 * Junctions are real geometry, not overlapping ribbons: the roads meeting at a node are sorted
 * by angle, the offset side lines of neighbouring roads are intersected to get the corner
 * points, and the polygon is fan-triangulated from the node. The asphalt corners are rounded
 * with a kerb fillet; the pavement polygon keeps square corners so it meets the block ground.
 *
 * Triangle winding is fixed per triangle (the normal is forced to point up), so a strip can
 * never face down and be culled: that bug once made every road invisible from above.
 */

const LIFT = { block: 0.05, walk: 0.1, road: 0.15, mark: 0.19, median: 0.24 } as const;
const COLOR = {
  walk: 0xcdd1d6,
  road: 0x434850,
  avenue: 0x3a3e46,
  dash: 0xe9e6d6,
  zebra: 0xf0f2f5,
  median: 0xd3d7dc,
  grass: 0x86b774,
  stone: 0xd8dce2,
  block: 0xd7dade,
  plaza: 0xe2e5ea,
  station: 0xcbd0d6,
  path: 0xe8e4d6,
  pond: 0x52b6d6,
  dark: 0x3b4048,
} as const;
const FILLET = 3;
const BLOCK_COLOR: Partial<Record<Block["kind"], number>> = {
  city: COLOR.block,
  plaza: COLOR.plaza,
  station: COLOR.station,
  "pocket-plaza": COLOR.plaza,
};

class Flat {
  private pos: number[] = [];
  private col: number[] = [];

  tri(a: V, b: V, c: V, y: number, hex: number) {
    const ny = (b.z - a.z) * (c.x - a.x) - (b.x - a.x) * (c.z - a.z);
    if (Math.abs(ny) < 1e-9) return;
    const [p, q] = ny > 0 ? [b, c] : [c, b];
    const color = new THREE.Color(hex);
    for (const v of [a, p, q]) {
      this.pos.push(v.x, y, v.z);
      this.col.push(color.r, color.g, color.b);
    }
  }

  /** Fan from `centre` (any point the polygon can see: its centroid, or the node of a junction). */
  fan(points: readonly V[], centre: V, y: number, hex: number) {
    const clean = points.filter((p, i) => Math.hypot(p.x - points[(i + 1) % points.length].x, p.z - points[(i + 1) % points.length].z) > 1e-4);
    for (let i = 0; i < clean.length; i++) this.tri(centre, clean[i], clean[(i + 1) % clean.length], y, hex);
  }

  poly(points: readonly V[], y: number, hex: number) {
    const c = points.reduce((s, p) => ({ x: s.x + p.x / points.length, z: s.z + p.z / points.length }), { x: 0, z: 0 });
    this.fan(points, c, y, hex);
  }

  /** Rectangle from a to b, `half` to each side. */
  strip(a: V, b: V, half: number, y: number, hex: number) {
    const dx = b.x - a.x;
    const dz = b.z - a.z;
    const l = Math.hypot(dx, dz) || 1;
    const nx = (-dz / l) * half;
    const nz = (dx / l) * half;
    const p1 = { x: a.x + nx, z: a.z + nz };
    const p2 = { x: a.x - nx, z: a.z - nz };
    const p3 = { x: b.x - nx, z: b.z - nz };
    const p4 = { x: b.x + nx, z: b.z + nz };
    this.tri(p1, p2, p3, y, hex);
    this.tri(p1, p3, p4, y, hex);
  }

  build(): THREE.BufferGeometry {
    const g = new THREE.BufferGeometry();
    const n = this.pos.length / 3;
    g.setAttribute("position", new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute("color", new THREE.Float32BufferAttribute(this.col, 3));
    g.setAttribute("normal", new THREE.Float32BufferAttribute(Array.from({ length: n * 3 }, (_, i) => (i % 3 === 1 ? 1 : 0)), 3));
    g.computeBoundingSphere();
    return g;
  }
}

interface Arm {
  edge: GEdge;
  dx: number;
  dz: number;
  angle: number;
  h: number;
}

interface Junction {
  polygon: V[];
  /** Distance along each edge (from the node) where its ribbon starts. */
  stops: Map<string, number>;
}

const TAU = Math.PI * 2;
const norm = (a: number) => ((a % TAU) + TAU) % TAU;

/** Corner points, optional kerb fillets and mouth positions of the roads that meet at `node`. */
function junctionAt(graph: CityGraph, node: GNode, level: "walk" | "road", radius: number): Junction | null {
  const arms: Arm[] = (graph.adjacency.get(node.id) ?? []).map((h) => {
    const edge = graph.edges.find((e) => e.id === h.edge)!;
    const half = (level === "walk" ? edge.width : carriage(edge)) / 2;
    return { edge, dx: Math.cos(h.angle), dz: Math.sin(h.angle), angle: h.angle, h: half };
  });
  const n = arms.length;
  if (n < 2) return null;

  // Wedge i spans from arm i to the next arm counter-clockwise.
  interface Wedge {
    corner: V;
    ti: number;
    uj: number;
    phi: number;
    straight: boolean;
  }
  const wedges: Wedge[] = arms.map((a, i) => {
    const b = arms[(i + 1) % n];
    const phi = norm(b.angle - a.angle) || TAU;
    const straight = Math.abs(phi - Math.PI) < 1e-3;
    const nLx = -a.dz;
    const nLz = a.dx;
    if (straight) {
      return { corner: { x: node.x + nLx * a.h, z: node.z + nLz * a.h }, ti: 0, uj: 0, phi, straight };
    }
    const ti = (b.h + a.h * Math.cos(phi)) / Math.sin(phi);
    const uj = (a.h + b.h * Math.cos(phi)) / Math.sin(phi);
    return { corner: { x: node.x + ti * a.dx + nLx * a.h, z: node.z + ti * a.dz + nLz * a.h }, ti, uj, phi, straight };
  });

  const tau = (w: Wedge) => (radius > 0 && !w.straight && w.phi < Math.PI ? radius / Math.tan(w.phi / 2) : 0);
  const stops = new Map<string, number>();
  arms.forEach((a, i) => {
    const left = wedges[i];
    const right = wedges[(i - 1 + n) % n];
    stops.set(a.edge.id, Math.max(0, left.ti + tau(left), right.uj + tau(right)));
  });

  const polygon: V[] = [];
  arms.forEach((a, i) => {
    const s = stops.get(a.edge.id)!;
    const nLx = -a.dz;
    const nLz = a.dx;
    polygon.push({ x: node.x + s * a.dx - nLx * a.h, z: node.z + s * a.dz - nLz * a.h });
    polygon.push({ x: node.x + s * a.dx + nLx * a.h, z: node.z + s * a.dz + nLz * a.h });
    const w = wedges[i];
    const b = arms[(i + 1) % n];
    const t = tau(w);
    if (t > 0) {
      const ti = { x: w.corner.x + t * a.dx, z: w.corner.z + t * a.dz };
      const tj = { x: w.corner.x + t * b.dx, z: w.corner.z + t * b.dz };
      const bx = a.dx + b.dx;
      const bz = a.dz + b.dz;
      const bl = Math.hypot(bx, bz) || 1;
      const k = radius / Math.sin(w.phi / 2);
      const o = { x: w.corner.x + (bx / bl) * k, z: w.corner.z + (bz / bl) * k };
      polygon.push(ti);
      const a0 = Math.atan2(ti.z - o.z, ti.x - o.x);
      let d = Math.atan2(tj.z - o.z, tj.x - o.x) - a0;
      while (d > Math.PI) d -= TAU;
      while (d < -Math.PI) d += TAU;
      for (let s2 = 1; s2 < 6; s2++) polygon.push({ x: o.x + radius * Math.cos(a0 + (d * s2) / 6), z: o.z + radius * Math.sin(a0 + (d * s2) / 6) });
      polygon.push(tj);
    } else {
      polygon.push(w.corner);
    }
  });
  return { polygon, stops };
}

export interface Roads {
  group: THREE.Group;
  dispose(): void;
}

export function buildRoads(layout: WorldLayout): Roads {
  const { graph, blocks } = layout;
  const flat = new Flat();
  const details = new Builder();

  // --- block ground ---------------------------------------------------------------------------
  for (const b of blocks) {
    const color = BLOCK_COLOR[b.kind];
    if (color === undefined) continue;
    for (const plot of b.plots) if (plot.length >= 3) flat.poly(plot, LIFT.block, color);
  }

  // --- junction polygons and ribbon stops ---------------------------------------------------
  const stopsWalk = new Map<string, number>();
  const stopsRoad = new Map<string, number>();
  const junctionNodes: GNode[] = [];
  for (const node of graph.nodes.values()) {
    if (node.kind !== "junction" && node.kind !== "bend") continue;
    junctionNodes.push(node);
    const walk = junctionAt(graph, node, "walk", 0);
    const road = junctionAt(graph, node, "road", FILLET);
    if (!walk || !road) continue;
    flat.fan(walk.polygon, node, LIFT.walk, COLOR.walk);
    for (const [e, s] of walk.stops) stopsWalk.set(`${node.id}|${e}`, s);
    for (const [e, s] of road.stops) stopsRoad.set(`${node.id}|${e}`, s);
    // Asphalt of the junction: avenue colour if any avenue meets here.
    const major = (graph.adjacency.get(node.id) ?? []).some((h) => graph.edges.find((e) => e.id === h.edge)!.class === "avenue");
    flat.fan(road.polygon, node, LIFT.road, major ? COLOR.avenue : COLOR.road);
  }

  // --- ribbons ------------------------------------------------------------------------------------
  const zebra = (node: GNode, edge: GEdge, dir: V, from: number) => {
    const half = carriage(edge) / 2 - 0.5;
    const count = Math.floor((half * 2) / 1.1);
    for (let k = 0; k < count; k++) {
      const off = -half + 0.55 + k * 1.1;
      const cx = node.x + dir.x * (from + 1.1) - dir.z * off;
      const cz = node.z + dir.z * (from + 1.1) + dir.x * off;
      flat.strip({ x: cx - dir.x * 1.1, z: cz - dir.z * 1.1 }, { x: cx + dir.x * 1.1, z: cz + dir.z * 1.1 }, 0.27, LIFT.mark, COLOR.zebra);
    }
  };

  const nodeById = graph.nodes;
  for (const edge of graph.roads) {
    const a = nodeById.get(edge.a)!;
    const b = nodeById.get(edge.b)!;
    const dx = (b.x - a.x) / edge.length;
    const dz = (b.z - a.z) / edge.length;
    const dir = { x: dx, z: dz };
    const sw = (n: GNode) => stopsWalk.get(`${n.id}|${edge.id}`) ?? 0;
    const sr = (n: GNode) => stopsRoad.get(`${n.id}|${edge.id}`) ?? 0;
    const at = (d: number): V => ({ x: a.x + dx * d, z: a.z + dz * d });
    const major = edge.class === "avenue" || edge.class === "ring";

    if (edge.length - sw(a) - sw(b) > 0.1) flat.strip(at(sw(a)), at(edge.length - sw(b)), edge.width / 2, LIFT.walk, COLOR.walk);
    if (edge.length - sr(a) - sr(b) > 0.1) flat.strip(at(sr(a)), at(edge.length - sr(b)), carriage(edge) / 2, LIFT.road, major ? COLOR.avenue : COLOR.road);

    // Crosswalks at the mouth of every junction leg.
    for (const [node, from, d0] of [[a, sr(a), dir], [b, sr(b), { x: -dx, z: -dz }]] as const) {
      if ((node.kind === "junction" || node.kind === "bend") && edge.length > from + 8) zebra(node, edge, d0, from);
    }

    // Centre dashes (or lane dashes and a planted median on avenues).
    const lo = Math.max(sr(a), sw(a)) + 4.2;
    const hi = edge.length - Math.max(sr(b), sw(b)) - 4.2;
    if (hi - lo > 4) {
      if (edge.median > 0) {
        const mid = hi - lo;
        details.box(edge.median + 0.5, 0.16, mid, a.x + dx * (lo + mid / 2), LIFT.road, a.z + dz * (lo + mid / 2), COLOR.median, Math.atan2(dx, dz));
        details.box(edge.median - 0.5, 0.2, mid - 0.4, a.x + dx * (lo + mid / 2), LIFT.road, a.z + dz * (lo + mid / 2), 0x8fb27f, Math.atan2(dx, dz));
        for (const side of [-1, 1]) {
          const off = (edge.median / 2 + (carriage(edge) - edge.median) / 4) * side;
          for (let d = lo; d + 2.2 < hi; d += 5.2) {
            flat.strip(
              { x: a.x + dx * d - dz * off, z: a.z + dz * d + dx * off },
              { x: a.x + dx * (d + 2.2) - dz * off, z: a.z + dz * (d + 2.2) + dx * off },
              0.09,
              LIFT.mark,
              COLOR.dash,
            );
          }
        }
      } else {
        for (let d = lo; d + 2.2 < hi; d += 5) flat.strip(at(d), at(d + 2.2), 0.1, LIFT.mark, COLOR.dash);
      }
    }

    // Bridges: a deck slab under the road, railings, and abutment blocks on the banks.
    if (edge.class === "bridge") {
      const ry = Math.atan2(dx, dz);
      const mx = (a.x + b.x) / 2;
      const mz = (a.z + b.z) / 2;
      details.box(edge.width + 0.6, 0.7, edge.length + 0.8, mx, -0.62, mz, 0xaeb4bc, ry);
      for (const side of [-1, 1]) {
        const off = (edge.width / 2 + 0.05) * side;
        details.box(0.28, 0.14, edge.length, mx - dz * off, 0.95, mz + dx * off, 0xe4e7ec, ry);
        for (let d = 1; d < edge.length; d += 3.2) {
          details.box(0.22, 0.95, 0.22, a.x + dx * d - dz * off, 0.1, a.z + dz * d + dx * off, 0xe4e7ec, ry);
        }
      }
    }

    // Street lamps on the pavements of avenues and the ring road.
    if (major && edge.length > 20) {
      for (let d = 10; d < edge.length - 9; d += 22) {
        for (const side of [-1, 1]) {
          const off = (edge.width / 2 - 0.55) * side;
          const x = a.x + dx * d - dz * off;
          const z = a.z + dz * d + dx * off;
          details.cyl(0.05, 0.065, 2.6, x, LIFT.walk, z, COLOR.dark, 6);
          // The arm reaches over the carriageway.
          const ux = dz * side;
          const uz = -dx * side;
          details.box(0.1, 0.08, 0.9, x + ux * 0.45, 2.55, z + uz * 0.45, COLOR.dark, Math.atan2(ux, uz));
          details.sphere(0.17, x + ux * 0.9, 2.5, z + uz * 0.9, 0xf1f4f8);
        }
      }
    }
  }

  // Crossings of the plaza: the ring road's mid-edge nodes (gates) get a zebra into the square.
  for (const gate of graph.gates) {
    const h = (graph.adjacency.get(gate.id) ?? [])[0];
    if (!h) continue;
    const edge = graph.edges.find((e) => e.id === h.edge)!;
    const dir = { x: Math.cos(h.angle), z: Math.sin(h.angle) };
    zebra(gate, edge, dir, -1.1);
  }

  // --- parks: paths and a pond ---------------------------------------------------------------
  for (const park of layout.greenSpaces) {
    const { x, z, halfW, halfD } = park;
    if (park.kind === "greenway") {
      // A promenade along the canal cell, on the side away from the water.
      continue;
    }
    const w = park.kind === "pocket-plaza" ? 0 : 1.15;
    if (w > 0) {
      flat.strip({ x: x - halfW, z }, { x: x + halfW, z }, w, LIFT.walk, COLOR.path);
      flat.strip({ x, z: z - halfD }, { x, z: z + halfD }, w, LIFT.walk, COLOR.path);
      const ring: V[] = Array.from({ length: 20 }, (_, i) => ({ x: x + Math.cos((i / 20) * TAU) * 4.2, z: z + Math.sin((i / 20) * TAU) * 4.2 }));
      flat.poly(ring, LIFT.walk + 0.01, COLOR.path);
    }
    if (park.pond) {
      const p = park.pond;
      const pts: V[] = Array.from({ length: 28 }, (_, i) => ({ x: p.x + Math.cos((i / 28) * TAU) * p.radiusX, z: p.z + Math.sin((i / 28) * TAU) * p.radiusZ }));
      const rim: V[] = Array.from({ length: 28 }, (_, i) => ({ x: p.x + Math.cos((i / 28) * TAU) * (p.radiusX + 0.7), z: p.z + Math.sin((i / 28) * TAU) * (p.radiusZ + 0.7) }));
      flat.fan(rim, { x: p.x, z: p.z }, LIFT.walk + 0.02, COLOR.stone);
      flat.fan(pts, { x: p.x, z: p.z }, LIFT.walk + 0.04, COLOR.pond);
    }
    // Benches beside the paths.
    for (const [bx, bz, ry] of [[x + 6, z + 2.4, Math.PI / 2], [x - 6, z - 2.4, Math.PI / 2], [x + 2.4, z - 7, 0], [x - 2.4, z + 7, 0]] as const) {
      details.box(0.5, 0.14, 2, bx, 0.12, bz, 0x686e78, ry);
      details.box(0.12, 0.6, 2, bx + (ry === 0 ? -0.22 : 0), 0.22, bz + (ry === 0 ? 0 : 0.22), 0x7c828c, ry);
    }
  }

  const group = new THREE.Group();
  const disposables: Array<{ dispose(): void }> = [];
  const mat = new THREE.MeshLambertMaterial({ vertexColors: true });
  disposables.push(mat);
  const flatGeo = flat.build();
  disposables.push(flatGeo);
  const flatMesh = new THREE.Mesh(flatGeo, mat);
  flatMesh.receiveShadow = true;
  group.add(flatMesh);

  const detailGeo = details.build();
  disposables.push(detailGeo);
  const detailMesh = new THREE.Mesh(detailGeo, new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true }));
  disposables.push(detailMesh.material as THREE.Material);
  detailMesh.castShadow = true;
  detailMesh.receiveShadow = true;
  group.add(detailMesh);

  return {
    group,
    dispose() {
      disposables.forEach((d) => d.dispose());
    },
  };
}
