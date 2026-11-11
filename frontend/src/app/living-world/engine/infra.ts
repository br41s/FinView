import * as THREE from "three";
import { nodeId, type GNode } from "../model/cityGraph";
import { MONORAIL_DECK, MONORAIL_WIDTH, RAIL_WIDTH, type Pier } from "../model/infra";
import { pointAlong, routeLength, type Point } from "../model/routes";
import type { WorldLayout } from "../model/townLayout";
import { createLoop, createShuttle, crossingClosed, type TrainState } from "../model/trainSchedule";
import { Builder } from "./buildingFactory";
import { ribbon } from "./props";
import { GeoBuilder, KIND, createToyMaterial } from "./toyMaterial";

/**
 * Transport: the railway with its shuttle train and level crossings, and the monorail loop on
 * pillars with its two trains. Road traffic lives in `vehicles.ts`.
 *
 * Both trains follow timetables from `model/trainSchedule.ts`, pure functions of this module's clock:
 * the ground train waits at a terminus, pulls out and runs to the other end and back; the monorail
 * brakes into every station, dwells with its doors open, and departs. The level-crossing barriers
 * read the same timetable, so they close before the train arrives and open after its tail has gone,
 * and the road traffic reads the same barrier state through `crossingClosed`.
 */

export interface InfraSystem {
  group: THREE.Group;
  readonly monoCars: THREE.InstancedMesh;
  getMonorailPosition(trainIdx?: number): { x: number; y: number; z: number; heading: number };
  getGroundTrainPosition(): { x: number; y: number; z: number; heading: number };
  /** Is the level crossing at this graph node closed to road traffic? */
  crossingClosed(node: GNode): boolean;
  update(dtMs: number): void;
  setReducedMotion(v: boolean): void;
  dispose(): void;
}

const CONCRETE = 0xbec3cb;
const ASPHALT = 0x454952;
const PARAPET = 0xe2e5ea;

/** Boxes laid along a polyline so a curved deck keeps its thickness and its parapets. */
function deck(
  b: Builder,
  line: readonly Point[],
  width: number,
  thick: number,
  y: (x: number, z: number) => number,
  opts: { parapet?: boolean; top?: number; slab?: number } = {},
) {
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1];
    const c = line[i];
    const len = Math.hypot(c.x - a.x, c.z - a.z);
    const k = Math.max(1, Math.ceil(len / 3));
    const ry = Math.atan2(c.x - a.x, c.z - a.z);
    const nx = Math.cos(ry);
    const nz = -Math.sin(ry);
    for (let s = 0; s < k; s++) {
      const x = a.x + ((c.x - a.x) * (s + 0.5)) / k;
      const z = a.z + ((c.z - a.z) * (s + 0.5)) / k;
      const piece = len / k + 0.25;
      const h = y(x, z);
      b.box(width, thick, piece, x, h - thick, z, opts.slab ?? CONCRETE, ry);
      b.box(width - 0.5, 0.1, piece, x, h, z, opts.top ?? ASPHALT, ry);
      if (opts.parapet) {
        const o = width / 2 - 0.2;
        b.box(0.3, 0.55, piece, x + nx * o, h, z + nz * o, PARAPET, ry);
        b.box(0.3, 0.55, piece, x - nx * o, h, z - nz * o, PARAPET, ry);
      }
    }
  }
}

/**
 * Pillars at the positions the model chose (the avenue's central reservation, never a lane):
 * a column from the ground to a cross-head just under the deck.
 */
function pillars(b: Builder, piers: readonly Pier[], deckY: (x: number, z: number) => number, ground: (x: number, z: number) => number) {
  for (const p of piers) {
    const g = ground(p.x, p.z);
    const top = deckY(p.x, p.z) - 0.85;
    b.cyl(0.38, 0.5, top - g - 0.5, p.x, g, p.z, CONCRETE, 10);
    b.box(2.6, 0.5, 1.0, p.x, top - 0.5, p.z, CONCRETE, p.heading + Math.PI / 2);
  }
}

// --- rolling stock ------------------------------------------------------------------------------

const LAMP = 0xfff1c4;
const BRAKE_LAMP = 0xff3a3a;
const DOOR_LAMP = 0x58f08c;
const GLASS = 0x32465c;
const DARK = 0x2b2f36;

/** Ground train: a red locomotive and four cream coaches with a blue stripe, 22 long, nose to +z. */
const TRAIN_LENGTH = 22;
function groundTrainGeometry(): THREE.BufferGeometry {
  const b = new GeoBuilder();
  const w = 1.9;
  const vehicle = (z0: number, len: number, loco: boolean) => {
    const zc = z0 - len / 2;
    b.box(w - 0.3, 0.3, len - 0.3, 0, 0.18, zc, DARK);
    b.roundBox(w, 1.5, len, 0.26, 0, 0.36, zc, loco ? 0xd9443a : 0xf1e9d8, { kind: KIND.fixed });
    b.box(w + 0.02, 0.2, len - 0.3, 0, 0.72, zc, loco ? 0xf2c230 : 0x2f6fd6);
    b.roundBox(w - 0.35, 0.12, len - 0.5, 0.05, 0, 1.84, zc, loco ? 0x9aa1ab : 0xdfe3e8);
    if (!loco) {
      for (const s of [-1, 1]) {
        b.box(w + 0.03, 0.5, len - 0.9, 0, 1.08, zc, 0xdce9f2, { kind: KIND.lit });
        b.box(0.02, 0.62, 0.05, s * (w / 2 + 0.02), 0.94, zc + len / 2 - 0.6, DOOR_LAMP, { kind: KIND.tail });
        b.box(0.02, 0.62, 0.05, s * (w / 2 + 0.02), 0.94, zc - len / 2 + 0.6, DOOR_LAMP, { kind: KIND.tail });
      }
    }
  };
  vehicle(TRAIN_LENGTH / 2, 4.6, true);
  for (let i = 0; i < 4; i++) vehicle(TRAIN_LENGTH / 2 - 4.9 - i * 4.25, 3.9, false);
  const nose = TRAIN_LENGTH / 2;
  b.box(w - 0.5, 0.5, 0.06, 0, 1.05, nose + 0.005, GLASS, { kind: KIND.glass });
  for (const s of [-1, 1]) {
    b.box(0.26, 0.14, 0.06, s * (w / 2 - 0.3), 0.56, nose + 0.01, LAMP, { kind: KIND.head });
    b.box(0.26, 0.14, 0.06, s * (w / 2 - 0.3), 0.56, -nose - 0.01, BRAKE_LAMP, { kind: KIND.tail });
  }
  return b.build();
}

/** One monorail car, 3.4 long, nose to +z, with a doorway on each side at its middle. */
const MONO_CAR = 3.4;
function monorailCarGeometry(): THREE.BufferGeometry {
  const b = new GeoBuilder();
  const w = 1.5;
  b.box(w - 0.5, 0.25, MONO_CAR - 0.5, 0, 0.12, 0, DARK);
  b.roundBox(w, 1.2, MONO_CAR - 0.04, 0.34, 0, 0.3, 0, 0xffffff, { kind: KIND.paint });
  b.box(w + 0.02, 0.44, MONO_CAR - 0.7, 0, 0.88, 0, 0xdce9f2, { kind: KIND.lit });
  b.box(w - 0.3, 0.5, MONO_CAR + 0.0, 0, 0.88, 0, 0xdce9f2, { kind: KIND.lit });
  b.roundBox(w - 0.4, 0.14, MONO_CAR - 0.6, 0.06, 0, 1.46, 0, 0xdfe3e8);
  for (const s of [-1, 1]) {
    b.box(0.03, 0.9, 0.86, s * (w / 2 + 0.005), 0.34, 0, GLASS, { kind: KIND.glass });
    b.box(0.02, 0.5, 0.04, s * (w / 2 + 0.035), 0.9, 0.5, DOOR_LAMP, { kind: KIND.tail });
    b.box(0.26, 0.12, 0.06, s * (w / 2 - 0.3), 0.6, MONO_CAR / 2 - 0.02, LAMP, { kind: KIND.head });
    b.box(0.26, 0.12, 0.06, s * (w / 2 - 0.3), 0.6, -MONO_CAR / 2 + 0.02, BRAKE_LAMP, { kind: KIND.tail });
  }
  return b.build();
}

function doorLeafGeometry(): THREE.BufferGeometry {
  const b = new GeoBuilder();
  b.box(0.04, 0.88, 0.43, 0, 0, 0, 0x9fb4c8);
  return b.build();
}

function barrierArmGeometry(): THREE.BufferGeometry {
  // One unit long along +x from the pivot: the instance matrix scales it to the road.
  const b = new GeoBuilder();
  const stripes = 10;
  for (let i = 0; i < stripes; i++) {
    b.box(1 / stripes, 0.14, 0.14, (i + 0.5) / stripes, -0.07, 0, i % 2 ? 0xf4f4f4 : 0xd23b3b);
  }
  return b.build();
}

export function buildInfra(layout: WorldLayout): InfraSystem {
  const group = new THREE.Group();
  const disposables: Array<{ dispose(): void }> = [];
  const own = <T extends { dispose(): void }>(x: T) => (disposables.push(x), x);
  const t = layout.terrain;
  const { infra, graph } = layout;
  const mat = own(new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true }));
  const toy = own(createToyMaterial({ paint: [-0.5, 0.5], brake: true, roughness: 0.42 }));
  let reduced = false;
  let clock = 0;

  const monorailY = (x: number, z: number) => Math.max(MONORAIL_DECK, t.roadY(x, z) + 6);

  // --- railway ---------------------------------------------------------------------
  const rb = new Builder();
  const rail = infra.rail.path;
  const railLen = routeLength(rail);
  for (let d = 0.6; d < railLen; d += 1.3) {
    const p = pointAlong(rail, d);
    rb.box(2.0, 0.1, 0.35, p.x, t.roadY(p.x, p.z) + 0.18, p.z, 0x626770, p.heading);
  }
  const railMesh = new THREE.Mesh(own(rb.build()), mat);
  railMesh.receiveShadow = true;
  group.add(railMesh);
  const bed = new THREE.Mesh(own(ribbon(rail, RAIL_WIDTH + 1.2, 0.12, 0xa8aeb7, t.roadY)), mat);
  bed.receiveShadow = true;
  group.add(bed);
  for (const side of [-0.72, 0.72]) {
    const off = rail.map((p, i) => {
      const n = rail[Math.min(rail.length - 1, i + 1)];
      const q = rail[Math.max(0, i - 1)];
      const dx = n.x - q.x;
      const dz = n.z - q.z;
      const l = Math.hypot(dx, dz) || 1;
      return { x: p.x + (-dz / l) * side, z: p.z + (dx / l) * side };
    });
    group.add(new THREE.Mesh(own(ribbon(off, 0.14, 0.2, 0x4b5059, t.roadY)), mat));
  }
  // The termini: a platform with a canopy beside the square, and another at the far end.
  const term = new Builder();
  const tp = infra.railTerminus;
  const th = t.roadY(tp.x, tp.z);
  const tAng = Math.atan2(rail[1].x - rail[0].x, rail[1].z - rail[0].z);
  const stationAt = (b: Builder, x: number, z: number, y: number, ry: number, len: number, w: number) => {
    b.box(w, 0.35, len, x, y, z, 0xd4d8de, ry);
    b.box(w + 0.6, 0.18, len + 0.6, x, y + 2.3, z, 0x5c616b, ry);
    for (const o of [-len / 2 + 0.5, len / 2 - 0.5]) {
      const dx = Math.sin(ry) * o;
      const dz = Math.cos(ry) * o;
      b.cyl(0.12, 0.12, 2.2, x + dx, y + 0.35, z + dz, 0x3b4048, 6);
    }
    b.box(w * 0.5, 1.4, 2.0, x, y + 0.35, z, 0xe2e5ea, ry);
  };
  // Platform beside the track (the track keeps its own width), a buffer stop at each end of the line.
  stationAt(term, tp.x + 11, tp.z + 4.4, th + 0.12, tAng, 18, 4.2);
  const endP = rail[rail.length - 1];
  stationAt(term, endP.x - 11, endP.z + 4.4, th + 0.12, tAng, 18, 4.2);
  term.box(0.5, 0.9, 2.2, tp.x - 0.6, th + 0.18, tp.z, 0x7a2f2f);
  term.box(0.7, 0.2, 2.6, tp.x - 0.6, th + 1.0, tp.z, 0xd8dce2);
  term.box(0.5, 0.9, 2.2, endP.x + 0.6, th + 0.18, endP.z, 0x7a2f2f);
  term.box(0.7, 0.2, 2.6, endP.x + 0.6, th + 1.0, endP.z, 0xd8dce2);

  // Level crossings: rubber decking over the street, and a pole + barrier arm + signal each side.
  interface Crossing {
    node: GNode;
    at: number;
    lift: number;
    target: number;
    closed: boolean;
  }
  const crossings: Crossing[] = [];
  const arms: Array<{ x: number; z: number; sx: number; sz: number; len: number }> = [];
  for (const c of infra.crossings) {
    const node = graph.node(nodeId(c.x, c.z));
    const roads = (graph.adjacency.get(node.id) ?? []).map((h) => graph.edges.find((e) => e.id === h.edge)!);
    const e = roads.reduce((a, b) => (b.width > a.width ? b : a), roads[0]);
    const poleX = e ? e.width / 2 - e.walk / 2 : 3.6;
    const deckW = e ? e.width - 2 * e.walk + 0.6 : 6;
    // The rail runs along x: the decking is as wide as the carriageway (x) and as deep as the track (z).
    term.box(deckW, 0.05, 4.2, c.x, th + 0.15, c.z, 0x2f3338);
    for (const sx of [-1, 1]) {
      for (const sz of [-1, 1]) {
        const px = c.x + sx * poleX;
        const pz = c.z + sz * 3.6;
        term.cyl(0.09, 0.09, 1.9, px, th + 0.1, pz, 0x3b4048, 6);
        arms.push({ x: px, z: pz, sx, sz, len: poleX - 0.15 });
      }
    }
    crossings.push({ node, at: c.x - rail[0].x, lift: 1, target: 1, closed: false });
  }
  group.add(new THREE.Mesh(own(term.build()), mat));

  // Barrier arms (instanced, lowered and raised every frame) and their flashing lamps.
  const armMesh = new THREE.InstancedMesh(own(barrierArmGeometry()), mat, Math.max(1, arms.length));
  armMesh.count = arms.length;
  armMesh.frustumCulled = false;
  armMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  group.add(armMesh);
  const lampMesh = new THREE.InstancedMesh(
    own(new THREE.SphereGeometry(0.22, 8, 6)),
    own(new THREE.MeshBasicMaterial({ toneMapped: false })),
    Math.max(1, arms.length),
  );
  lampMesh.count = arms.length;
  lampMesh.frustumCulled = false;
  lampMesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
  for (let i = 0; i < arms.length; i++) lampMesh.setColorAt(i, new THREE.Color(0x5a1414));
  group.add(lampMesh);

  // --- monorail --------------------------------------------------------------------
  const mb = new Builder();
  const mono = infra.monorail;
  deck(mb, mono.path, MONORAIL_WIDTH, 0.8, monorailY, { top: 0x626770, slab: 0xd4d8de });
  pillars(mb, mono.piers, monorailY, t.heightAt);
  for (const st of mono.stations) {
    const ry = st.angle;
    stationAt(mb, st.x, st.z, monorailY(st.x, st.z) + 0.1, ry, 9, 4.2);
  }
  const monoMesh = new THREE.Mesh(own(mb.build()), mat);
  monoMesh.castShadow = true;
  group.add(monoMesh);

  // --- rolling stock ---------------------------------------------------------------
  const brakeAttr = (n: number) => {
    const a = new THREE.InstancedBufferAttribute(new Float32Array(n), 1);
    a.setUsage(THREE.DynamicDrawUsage);
    return a;
  };
  const white = new THREE.Color(0xffffff);

  const trainGeo = own(groundTrainGeometry());
  const trainDoors = brakeAttr(1);
  trainGeo.setAttribute("aBrake", trainDoors);
  const trainMesh = new THREE.InstancedMesh(trainGeo, toy, 1);
  trainMesh.setColorAt(0, white);
  trainMesh.frustumCulled = false;
  trainMesh.castShadow = true;
  group.add(trainMesh);

  const MONO_TRAINS = 2;
  const MONO_CARS = 3;
  const monoGeo = own(monorailCarGeometry());
  const monoDoors = brakeAttr(MONO_TRAINS * MONO_CARS);
  monoGeo.setAttribute("aBrake", monoDoors);
  const monoCars = new THREE.InstancedMesh(monoGeo, toy, MONO_TRAINS * MONO_CARS);
  const monoPaint = [0x2f8fd8, 0xe9edf0, 0xe9edf0, 0xf29a2e, 0xe9edf0, 0xe9edf0];
  const color = new THREE.Color();
  for (let i = 0; i < MONO_TRAINS * MONO_CARS; i++) monoCars.setColorAt(i, color.set(monoPaint[i]));
  monoCars.frustumCulled = false;
  monoCars.castShadow = true;
  group.add(monoCars);
  const leafMesh = new THREE.InstancedMesh(own(doorLeafGeometry()), toy, MONO_TRAINS * MONO_CARS * 4);
  for (let i = 0; i < leafMesh.count; i++) leafMesh.setColorAt(i, white);
  leafMesh.frustumCulled = false;
  group.add(leafMesh);

  // Timetables.
  const loopLen = routeLength(mono.path);
  const stationDist = mono.stations.map((st) => {
    let best = 0;
    let bestD = Infinity;
    for (let d = 0; d < loopLen; d += 1) {
      const p = pointAlong(mono.path, d);
      const dd = Math.hypot(p.x - st.x, p.z - st.z);
      if (dd < bestD) {
        bestD = dd;
        best = d;
      }
    }
    return best;
  });
  const MONO_LEN = MONO_CARS * MONO_CAR;
  // A train stops with its middle on the platform: its head is half a train past the station.
  const monoLoop = createLoop(loopLen, stationDist.map((d) => (d + MONO_LEN / 2) % loopLen), MONO_LEN, { vmax: 7, acc: 1.5 }, 7);
  const shuttle = createShuttle(routeLength(rail), TRAIN_LENGTH, { vmax: 11, acc: 1.8 }, 9);
  // Start the clock with the ground train just out of the terminus and the monorails under way.
  clock = 13;

  const m4 = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
  const pos = new THREE.Vector3();
  const one = new THREE.Vector3(1, 1, 1);
  const sc = new THREE.Vector3();

  const place = (mesh: THREE.InstancedMesh, i: number, x: number, y: number, z: number, heading: number) => {
    q.setFromAxisAngle(up, heading);
    pos.set(x, y, z);
    m4.compose(pos, q, one);
    mesh.setMatrixAt(i, m4);
  };

  const monoState = (idx: number): TrainState => monoLoop.at(clock, idx * (monoLoop.period / 2));

  const poseAll = () => {
    // Ground train.
    const gs = shuttle.at(clock);
    place(trainMesh, 0, rail[0].x + gs.pos, t.roadY(0, 0) + 0.2, rail[0].z, gs.dir === 1 ? Math.PI / 2 : -Math.PI / 2);
    trainDoors.setX(0, gs.doors > 0.5 ? 1 : 0);
    trainDoors.needsUpdate = true;
    trainMesh.instanceMatrix.needsUpdate = true;

    // Monorail trains: cars follow the loop behind the head, doors slide while it dwells.
    for (let tIdx = 0; tIdx < MONO_TRAINS; tIdx++) {
      const s = monoState(tIdx);
      for (let i = 0; i < MONO_CARS; i++) {
        const d = (((s.pos - MONO_CAR * (i + 0.5)) % loopLen) + loopLen) % loopLen;
        const p = pointAlong(mono.path, d);
        const y = monorailY(p.x, p.z) + 0.1;
        const slot = tIdx * MONO_CARS + i;
        place(monoCars, slot, p.x, y, p.z, p.heading);
        monoDoors.setX(slot, s.doors > 0.5 ? 1 : 0);
        // Door leaves: two per side, sliding apart along the car by the door opening.
        q.setFromAxisAngle(up, p.heading);
        let k = slot * 4;
        for (const side of [-1, 1]) {
          for (const half of [-1, 1]) {
            const lx = side * (0.75 + 0.03);
            const lz = half * (0.215 + s.doors * 0.5);
            sc.set(1, 1, 1);
            pos.set(lx, 0.34, lz).applyQuaternion(q);
            pos.x += p.x;
            pos.y += y;
            pos.z += p.z;
            m4.compose(pos, q, sc);
            leafMesh.setMatrixAt(k++, m4);
          }
        }
      }
    }
    monoDoors.needsUpdate = true;
    monoCars.instanceMatrix.needsUpdate = true;
    leafMesh.instanceMatrix.needsUpdate = true;
  };

  const qz = new THREE.Quaternion();
  const zAxis = new THREE.Vector3(0, 0, 1);
  const poseBarriers = (dt: number) => {
    const flash = Math.floor(clock * 2.4) % 2 === 0;
    for (const c of crossings) {
      c.closed = crossingClosed(shuttle, c.at, clock);
      c.target = c.closed ? 0 : 1;
      c.lift += (c.target - c.lift) * Math.min(1, dt * 2.6);
    }
    // Arms are stored in crossing order, four per crossing.
    crossings.forEach((c, ci) => {
      for (let k = 0; k < 4; k++) {
        const i = ci * 4 + k;
        const arm = arms[i];
        // 0 = lying across the road, 1.35 = nearly upright; the arm points at the road's centre line.
        q.setFromAxisAngle(up, arm.sx > 0 ? Math.PI : 0);
        q.multiply(qz.setFromAxisAngle(zAxis, c.lift * 1.35));
        pos.set(arm.x, th + 1.1, arm.z);
        sc.set(arm.len, 1, 1);
        m4.compose(pos, q, sc);
        armMesh.setMatrixAt(i, m4);
        pos.set(arm.x, th + 2.05, arm.z);
        q.identity();
        m4.compose(pos, q, one);
        lampMesh.setMatrixAt(i, m4);
        const warn = c.closed || c.lift < 0.95;
        lampMesh.setColorAt(i, color.set(warn && flash === (k % 2 === 0) ? 0xff2a2a : 0x4a1212));
      }
    });
    armMesh.instanceMatrix.needsUpdate = true;
    lampMesh.instanceMatrix.needsUpdate = true;
    if (lampMesh.instanceColor) lampMesh.instanceColor.needsUpdate = true;
  };
  poseAll();
  poseBarriers(1);
  for (const c of crossings) c.lift = c.target;

  const getMonorailPosition = (trainIdx = 0) => {
    const s = monoState(trainIdx % MONO_TRAINS);
    const p = pointAlong(mono.path, (((s.pos - MONO_LEN / 2) % loopLen) + loopLen) % loopLen);
    return { x: p.x, y: monorailY(p.x, p.z) + 0.6, z: p.z, heading: p.heading };
  };

  return {
    group,
    monoCars,
    getMonorailPosition,
    getGroundTrainPosition() {
      const gs = shuttle.at(clock);
      return { x: rail[0].x + gs.pos, y: t.roadY(0, 0) + 1.2, z: rail[0].z, heading: gs.dir === 1 ? Math.PI / 2 : -Math.PI / 2 };
    },
    crossingClosed(node) {
      const c = crossings.find((x) => x.node.id === node.id);
      return c ? c.closed : false;
    },
    setReducedMotion(v) {
      reduced = v;
    },
    update(dtMs) {
      if (reduced) return;
      const dt = dtMs / 1000;
      clock += dt;
      poseAll();
      poseBarriers(dt);
    },
    dispose() {
      disposables.forEach((d) => d.dispose());
      trainMesh.dispose();
      monoCars.dispose();
      leafMesh.dispose();
      armMesh.dispose();
      lampMesh.dispose();
    },
  };
}
