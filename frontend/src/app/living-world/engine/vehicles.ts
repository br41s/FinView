import * as THREE from "three";
import { hashString } from "../model/rng";
import type { Point } from "../model/routes";
import { TrafficSim, VEHICLE_KINDS, VEHICLE_SPEC, getLaneNetwork, offsetPolyline, trafficLevel, type VehicleKind } from "../model/traffic";
import type { GNode } from "../model/cityGraph";
import type { WorldLayout } from "../model/townLayout";
import { GeoBuilder, KIND, createToyMaterial } from "./toyMaterial";

/**
 * Cars, taxis, vans, delivery trucks and buses: procedural rounded toy vehicles, one instanced mesh
 * per kind (a draw call each), driven by the lane simulation in `model/traffic.ts`.
 *
 * The paint takes the instance colour; glass, tyres and trim keep their own. Headlights and
 * taillights are emissive (they come on with the city night, brake lights with braking) through the
 * shared toy material. Event vans (`sendVan`) are scripted: they follow a route on the right-hand
 * lane, and the ambient traffic brakes for them (and they for it).
 */

const CAR_PAINT = [0xe0463a, 0xf08a2c, 0xf2c230, 0x3fae6a, 0x2aa6b8, 0x3a78d8, 0x8a63d2, 0xe86a9a, 0xf3f1ea, 0xc9ced6, 0x4a5160, 0x7bc96f];
const VAN_PAINT = [0xf3f1ea, 0x3a78d8, 0xe0463a, 0xf2c230, 0x3fae6a];
const BUS_PAINT = [0xe8553d, 0x2f8fd8, 0x39a96b, 0xf29a2e];
const TAXI = 0xf5c518;
const TYRE = 0x23262c;
const TRIM = 0x34373e;
const GLASS = 0x32465c;
const LAMP = 0xfff1c4;
const BRAKE_LAMP = 0xff2e2e;

function wheels(b: GeoBuilder, r: number, xs: number, zs: number[], width = 0.16) {
  for (const z of zs) {
    for (const s of [-1, 1]) {
      b.cyl(r, r, width, s * xs, r - width / 2, z, TYRE, 10, { rz: Math.PI / 2, kind: KIND.fixed });
    }
  }
}

function lamps(b: GeoBuilder, w: number, y: number, front: number, back: number) {
  for (const s of [-1, 1]) {
    b.box(0.22, 0.1, 0.06, s * (w / 2 - 0.2), y, front, LAMP, { kind: KIND.head });
    b.box(0.2, 0.1, 0.06, s * (w / 2 - 0.2), y, back, BRAKE_LAMP, { kind: KIND.tail });
  }
}

function car(len: number, cabLen: number, cabShift: number, tall = 0): THREE.BufferGeometry {
  const b = new GeoBuilder();
  const w = 1.05;
  wheels(b, 0.21, w / 2 - 0.04, [len / 2 - 0.55, -(len / 2 - 0.55)]);
  b.roundBox(w, 0.42, len, 0.17, 0, 0.17, 0, 0xffffff, { kind: KIND.paint });
  b.box(w - 0.04, 0.1, 0.1, 0, 0.2, len / 2 - 0.02, TRIM);
  b.box(w - 0.04, 0.1, 0.1, 0, 0.2, -len / 2 + 0.02, TRIM);
  b.roundBox(w - 0.2, 0.4 + tall, cabLen, 0.15, 0, 0.55, cabShift, 0xffffff, { kind: KIND.paint });
  // Glass: a band round the cabin, a touch proud of the paint.
  b.box(w - 0.14, 0.2 + tall * 0.6, cabLen - 0.34, 0, 0.66, cabShift, GLASS, { kind: KIND.glass });
  b.box(w - 0.36, 0.2 + tall * 0.6, cabLen + 0.04, 0, 0.66, cabShift, GLASS, { kind: KIND.glass });
  lamps(b, w, 0.36, len / 2 - 0.02, -len / 2 + 0.02);
  return b.build();
}

function taxi(): THREE.BufferGeometry {
  const b = new GeoBuilder();
  const len = 2.4;
  const w = 1.05;
  wheels(b, 0.21, w / 2 - 0.04, [len / 2 - 0.55, -(len / 2 - 0.55)]);
  b.roundBox(w, 0.42, len, 0.17, 0, 0.17, 0, 0xffffff, { kind: KIND.paint });
  b.roundBox(w - 0.2, 0.4, 1.15, 0.15, 0, 0.55, -0.12, 0xffffff, { kind: KIND.paint });
  b.box(w - 0.14, 0.2, 0.81, 0, 0.66, -0.12, GLASS, { kind: KIND.glass });
  b.box(w - 0.36, 0.2, 1.19, 0, 0.66, -0.12, GLASS, { kind: KIND.glass });
  b.box(0.4, 0.12, 0.2, 0, 0.94, -0.12, 0xfff7d6, { kind: KIND.lit });
  b.box(w + 0.01, 0.07, 1.2, 0, 0.36, 0, 0x1d1f24, { kind: KIND.fixed });
  lamps(b, w, 0.36, len / 2 - 0.02, -len / 2 + 0.02);
  return b.build();
}

function van(): THREE.BufferGeometry {
  const b = new GeoBuilder();
  const len = 2.7;
  const w = 1.15;
  wheels(b, 0.23, w / 2 - 0.04, [len / 2 - 0.6, -(len / 2 - 0.6)], 0.18);
  b.roundBox(w, 0.45, len, 0.17, 0, 0.18, 0, 0xffffff, { kind: KIND.paint });
  b.roundBox(w - 0.04, 0.62, 2.0, 0.17, 0, 0.55, -0.3, 0xffffff, { kind: KIND.paint });
  b.box(w - 0.12, 0.26, 0.62, 0, 0.78, 0.42, GLASS, { kind: KIND.glass });
  b.box(w - 0.42, 0.26, 0.74, 0, 0.78, 0.42, GLASS, { kind: KIND.glass });
  lamps(b, w, 0.38, len / 2 - 0.02, -len / 2 + 0.02);
  return b.build();
}

function truck(): THREE.BufferGeometry {
  const b = new GeoBuilder();
  const len = 3.7;
  const w = 1.25;
  wheels(b, 0.26, w / 2 - 0.04, [1.3, -0.2, -1.3], 0.2);
  b.box(w - 0.1, 0.18, len - 0.1, 0, 0.22, 0, TRIM);
  b.roundBox(w, 0.78, 1.05, 0.18, 0, 0.36, len / 2 - 0.58, 0xffffff, { kind: KIND.paint });
  b.box(w - 0.12, 0.28, 0.55, 0, 0.88, len / 2 - 0.32, GLASS, { kind: KIND.glass });
  b.box(w - 0.4, 0.28, 0.66, 0, 0.88, len / 2 - 0.32, GLASS, { kind: KIND.glass });
  b.roundBox(w, 1.05, 2.45, 0.1, 0, 0.4, -0.6, 0xf1efe8, { kind: KIND.fixed });
  b.box(w + 0.01, 0.18, 2.3, 0, 0.82, -0.6, 0xffffff, { kind: KIND.paint });
  lamps(b, w, 0.46, len / 2 - 0.02, -len / 2 + 0.02);
  return b.build();
}

function bus(): THREE.BufferGeometry {
  const b = new GeoBuilder();
  const len = 5.6;
  const w = 1.35;
  wheels(b, 0.3, w / 2 - 0.05, [1.8, -1.8], 0.22);
  b.roundBox(w, 1.3, len, 0.22, 0, 0.28, 0, 0xffffff, { kind: KIND.paint });
  b.box(w + 0.01, 0.3, len - 0.1, 0, 0.3, 0, TRIM);
  // Window band along both sides, and a big windscreen.
  b.box(w + 0.02, 0.46, len - 0.9, 0, 0.9, -0.05, 0xdce9f2, { kind: KIND.lit });
  b.box(w - 0.3, 0.52, len + 0.02, 0, 0.9, -0.0, 0xdce9f2, { kind: KIND.lit });
  b.box(w - 0.1, 0.44, 0.06, 0, 0.9, len / 2 + 0.005, GLASS, { kind: KIND.glass });
  b.box(w - 0.5, 0.14, 0.08, 0, 1.46, len / 2 - 0.04, 0xffd36b, { kind: KIND.lit });
  b.roundBox(w - 0.2, 0.1, len - 0.5, 0.05, 0, 1.56, 0, 0xe9edf0, { kind: KIND.fixed });
  // Pillars between the windows: paint strips.
  for (let i = 0; i < 5; i++) {
    const z = -len / 2 + 1.0 + i * 0.95;
    b.box(w + 0.03, 0.5, 0.07, 0, 0.88, z, 0xffffff, { kind: KIND.paint });
  }
  lamps(b, w, 0.5, len / 2 - 0.02, -len / 2 + 0.02);
  return b.build();
}

const GEOMETRY: Record<VehicleKind, () => THREE.BufferGeometry> = {
  sedan: () => car(2.4, 1.15, -0.12),
  hatch: () => car(2.1, 1.3, -0.2, 0.02),
  taxi,
  van,
  truck,
  bus,
};

const PAINT: Record<VehicleKind, number[]> = { sedan: CAR_PAINT, hatch: CAR_PAINT, taxi: [TAXI], van: VAN_PAINT, truck: VAN_PAINT, bus: BUS_PAINT };

interface Scripted {
  path: Point[];
  dist: number;
  total: number;
  turnAt: number;
  hold: number;
  held: boolean;
  stall: number;
  speed: number;
  tint: number;
  x: number;
  z: number;
  heading: number;
  moving: number;
  onDone: (() => void) | null;
}

const MAX_SCRIPTED = 10;
const LANE_OFFSET = 1.45;
/** Stand-off to the traffic ahead before a scripted van gives way. */
const GIVE_WAY = 3.2;

function pathLength(p: readonly Point[]): number {
  let n = 0;
  for (let i = 1; i < p.length; i++) n += Math.hypot(p[i].x - p[i - 1].x, p[i].z - p[i - 1].z);
  return n;
}

function along(p: readonly Point[], d: number): Point & { heading: number } {
  let left = Math.max(0, d);
  for (let i = 1; i < p.length; i++) {
    const dx = p[i].x - p[i - 1].x;
    const dz = p[i].z - p[i - 1].z;
    const l = Math.hypot(dx, dz);
    if (left <= l || i === p.length - 1) {
      const t = l === 0 ? 1 : Math.min(1, left / l);
      return { x: p[i - 1].x + dx * t, z: p[i - 1].z + dz * t, heading: Math.atan2(dx, dz) };
    }
    left -= l;
  }
  return { x: p[0].x, z: p[0].z, heading: 0 };
}

export class VehicleSystem {
  readonly group = new THREE.Group();
  readonly sim: TrafficSim;
  private meshes = new Map<VehicleKind, THREE.InstancedMesh>();
  private brake = new Map<VehicleKind, THREE.InstancedBufferAttribute>();
  private scripted: Scripted[] = [];
  private material = createToyMaterial({ paint: [-0.5, 0.5], brake: true, roughness: 0.38 });
  private maxVehicles = 0;
  private reduced = false;
  private hour = 8.5;
  private m = new THREE.Matrix4();
  private q = new THREE.Quaternion();
  private p = new THREE.Vector3();
  private s = new THREE.Vector3();
  private c = new THREE.Color();
  private up = new THREE.Vector3(0, 1, 0);

  constructor(
    layout: WorldLayout,
    private o: { maxVehicles: number; crossingClosed?: (node: GNode) => boolean; ground: (x: number, z: number) => number },
  ) {
    this.sim = new TrafficSim(getLaneNetwork(layout.graph), { seed: 0x7a11, crossingClosed: o.crossingClosed });
    this.maxVehicles = o.maxVehicles;
    const cap = o.maxVehicles + MAX_SCRIPTED + 4;
    for (const kind of VEHICLE_KINDS) {
      const n = kind === "sedan" || kind === "hatch" ? cap : Math.ceil(cap * 0.45) + 6;
      const geo = GEOMETRY[kind]();
      const attr = new THREE.InstancedBufferAttribute(new Float32Array(n), 1);
      attr.setUsage(THREE.DynamicDrawUsage);
      geo.setAttribute("aBrake", attr);
      const mesh = new THREE.InstancedMesh(geo, this.material, n);
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      for (let i = 0; i < n; i++) mesh.setColorAt(i, this.c.set(0xffffff));
      mesh.count = 0;
      mesh.frustumCulled = false;
      mesh.castShadow = true;
      mesh.name = `vehicles-${kind}`;
      this.group.add(mesh);
      this.meshes.set(kind, mesh);
      this.brake.set(kind, attr);
    }
    this.sim.setTarget(this.targetCount());
    this.sim.warm(this.targetCount());
    this.write();
  }

  private targetCount(): number {
    return Math.round(this.maxVehicles * trafficLevel(this.hour));
  }

  setReducedMotion(v: boolean) {
    this.reduced = v;
  }

  /** Quality tier: the most vehicles on the road at the busiest hour. */
  setMaxVehicles(n: number) {
    this.maxVehicles = Math.min(n, this.o.maxVehicles);
    this.sim.setTarget(this.targetCount());
  }

  get count(): number {
    return this.sim.count + this.scripted.length;
  }

  /** An event van: drives `route` on the right-hand lane, waits at the end, then comes back. */
  sendVan(route: readonly Point[], tint: number, speed: number, onDone?: () => void) {
    if (this.scripted.length >= MAX_SCRIPTED || route.length < 2) {
      onDone?.();
      return;
    }
    // Start at the door of the street, not inside the building.
    const base = route.length > 3 ? route.slice(1) : route.slice();
    const out = offsetPolyline(base, LANE_OFFSET);
    const back = offsetPolyline([...base].reverse(), LANE_OFFSET);
    const path = [...out, ...back];
    const turnAt = pathLength(out);
    const start = path[0];
    this.scripted.push({
      path, dist: 0, total: pathLength(path), turnAt, hold: 0, held: false, stall: 0, speed,
      tint, x: start.x, z: start.z, heading: 0, moving: 0, onDone: onDone ?? null,
    });
  }

  private stepScripted(dt: number) {
    for (const v of this.scripted) {
      if (v.hold > 0) {
        v.hold -= dt;
        v.moving = 0;
      } else {
        const gap = this.sim.gapAhead(v.x, v.z, v.heading, 6, 1.1);
        let go = gap > GIVE_WAY;
        if (!go) {
          v.stall += dt;
          if (v.stall > 3) go = true; // never block an event on a jammed street
        } else v.stall = 0;
        v.moving = go ? 1 : 0;
        if (go) {
          v.dist = Math.min(v.total, v.dist + v.speed * dt);
          if (!v.held && v.dist >= v.turnAt) {
            v.held = true;
            v.hold = 1.6;
            v.onDone?.();
            v.onDone = null;
          }
        }
      }
      const pt = along(v.path, v.dist);
      v.x = pt.x;
      v.z = pt.z;
      v.heading = pt.heading;
    }
    this.scripted = this.scripted.filter((v) => v.dist < v.total - 0.01);
  }

  update(dtMs: number, hour: number) {
    this.hour = hour;
    const dt = dtMs / 1000;
    if (!this.reduced) {
      this.sim.setTarget(this.targetCount());
      this.stepScripted(dt);
      this.sim.setExternals(this.scripted.map((v) => ({ x: v.x, z: v.z, heading: v.heading, length: 2.7 * VEHICLE_SPEC.van.scale, speed: v.moving * v.speed })));
      this.sim.advance(dt);
    }
    this.write();
  }

  private write() {
    const counts = new Map<VehicleKind, number>();
    const put = (kind: VehicleKind, x: number, z: number, heading: number, scale: number, colour: number, braking: boolean) => {
      const mesh = this.meshes.get(kind)!;
      const i = counts.get(kind) ?? 0;
      if (i >= mesh.instanceMatrix.count) return;
      counts.set(kind, i + 1);
      this.q.setFromAxisAngle(this.up, heading);
      this.p.set(x, this.o.ground(x, z) + 0.16, z);
      const k = Math.max(0.001, scale) * VEHICLE_SPEC[kind].scale;
      this.s.set(k, k, k);
      this.m.compose(this.p, this.q, this.s);
      mesh.setMatrixAt(i, this.m);
      mesh.setColorAt(i, this.c.set(colour));
      this.brake.get(kind)!.setX(i, braking ? 1 : 0);
    };
    for (const v of this.sim.vehicles) {
      const palette = PAINT[v.kind];
      put(v.kind, v.x, v.z, v.heading, v.scale, palette[hashString(`c${v.id}`) % palette.length], v.braking);
    }
    for (const v of this.scripted) put("van", v.x, v.z, v.heading, 1, v.tint, v.moving === 0);
    for (const kind of VEHICLE_KINDS) {
      const mesh = this.meshes.get(kind)!;
      mesh.count = counts.get(kind) ?? 0;
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      this.brake.get(kind)!.needsUpdate = true;
    }
  }

  dispose() {
    for (const mesh of this.meshes.values()) {
      mesh.geometry.dispose();
      mesh.dispose();
    }
    this.material.dispose();
  }
}
