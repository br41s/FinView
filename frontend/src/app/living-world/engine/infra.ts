import * as THREE from "three";
import { MONORAIL_DECK, MONORAIL_WIDTH, RAIL_WIDTH, type Pier } from "../model/infra";
import { pointAlong, routeLength, type Point } from "../model/routes";
import { seeded } from "../model/rng";
import type { WorldLayout } from "../model/townLayout";
import { Builder } from "./buildingFactory";
import { ribbon } from "./props";

/**
 * Transport: elevated expressways with traffic, a railway with a shuttle train, and a
 * monorail loop on pillars.
 *
 * Visual rule: Ambient city transport and highway vehicles belong to the grayscale "atrezzo"
 * layer (sleek monochrome slate, silver and charcoal tones) so they never compete with
 * portfolio company buildings or corporate event vans.
 */

export interface InfraSystem {
  group: THREE.Group;
  readonly monoCars: THREE.InstancedMesh;
  getMonorailPosition(trainIdx?: number): { x: number; y: number; z: number; heading: number };
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

function carGeometry(): THREE.BufferGeometry {
  const b = new Builder();
  b.box(0.95, 0.42, 1.9, 0, 0.12, 0, 0xffffff);
  b.box(0.8, 0.34, 1.0, 0, 0.54, -0.1, 0x383d45);
  return b.build();
}

function coachGeometry(len: number, wide: number, tall: number): THREE.BufferGeometry {
  const b = new Builder();
  b.box(wide, tall, len, 0, 0.35, 0, 0xffffff);
  b.box(wide + 0.04, tall * 0.34, len - 0.5, 0, 0.35 + tall * 0.42, 0, 0x383d45);
  b.box(wide - 0.2, 0.15, len - 0.2, 0, 0.35 + tall, 0, 0xc8cdd4);
  return b.build();
}

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

interface Car {
  line: number;
  dist: number;
  speed: number;
  lane: number;
  forward: boolean;
  loop: boolean;
}

export function buildInfra(layout: WorldLayout): InfraSystem {
  const group = new THREE.Group();
  const disposables: Array<{ dispose(): void }> = [];
  const own = <T extends { dispose(): void }>(x: T) => (disposables.push(x), x);
  const t = layout.terrain;
  const { infra } = layout;
  const mat = own(new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true }));
  let reduced = false;

  // Ambient traffic drives on the ground roads, on top of the asphalt (0.15).
  const highwayY = (x: number, z: number) => t.roadY(x, z) + 0.17;
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
  // The terminus: a platform with a monochrome architectural canopy beside the square.
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
  // Platform beside the track (the track keeps its own width), a buffer stop at the end of the line.
  stationAt(term, tp.x + 10, tp.z + 4.4, th + 0.12, tAng, 16, 4.2);
  term.box(0.5, 0.9, 2.2, tp.x - 0.6, th + 0.18, tp.z, 0x7a2f2f);
  term.box(0.7, 0.2, 2.6, tp.x - 0.6, th + 1.0, tp.z, 0xd8dce2);
  // Level crossings: rubber decking over the street, a barrier and a signal either side.
  for (const c of infra.crossings) {
    term.box(5.2, 0.05, 9, c.x, th + 0.15, c.z, 0x2f3338);
    for (const sx of [-1, 1]) {
      for (const sz of [-1, 1]) {
        const px = c.x + sx * 3.4;
        const pz = c.z + sz * 5.3;
        term.cyl(0.09, 0.09, 1.9, px, th + 0.1, pz, 0x3b4048, 6);
        term.sphere(0.2, px, th + 2.0, pz, 0xd23b3b);
        // Striped arm, raised: it stands along the street, clear of the carriageway.
        term.box(0.14, 0.14, 1.8, px - sx * 0.4, th + 1.1, pz - sz * 1.0, 0xf4f4f4, 0);
        term.box(0.15, 0.15, 0.6, px - sx * 0.4, th + 1.1, pz - sz * 0.5, 0xd23b3b, 0);
      }
    }
  }
  group.add(new THREE.Mesh(own(term.build()), mat));

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

  // --- ambient grayscale traffic ---------------------------------------------------
  const rng = seeded(0xca75);
  const CARS = 56;
  const cars: Car[] = [];
  const lens = infra.highways.map((c) => routeLength(c.path));
  const totalLen = lens.reduce((a, b) => a + b, 0);
  for (let i = 0; i < CARS; i++) {
    let r = rng() * totalLen;
    let line = 0;
    while (line < lens.length - 1 && r > lens[line]) r -= lens[line++];
    const path = infra.highways[line].path;
    const loop = Math.hypot(path[0].x - path[path.length - 1].x, path[0].z - path[path.length - 1].z) < 0.05;
    cars.push({ line, dist: r, speed: 7 + rng() * 5, lane: infra.highways[line].lane ?? 1.3, forward: rng() < 0.5, loop });
  }
  const carGeo = own(carGeometry());
  const carMesh = new THREE.InstancedMesh(carGeo, mat, CARS);
  // Pure grayscale palette for ambient highway vehicles ("atrezzo").
  const palette = [0x2b2e34, 0x3e424a, 0x565b64, 0x727882, 0x9197a1, 0xb4bac4, 0xd8dce2];
  const color = new THREE.Color();
  cars.forEach((_c, i) => carMesh.setColorAt(i, color.set(palette[Math.floor(rng() * palette.length)])));
  if (carMesh.instanceColor) carMesh.instanceColor.needsUpdate = true;
  carMesh.frustumCulled = false;
  carMesh.castShadow = true;
  group.add(carMesh);

  // Rolling stock in monochrome silver/graphite so ambient transit stays subordinate.
  const COACHES = 5;
  const MONO_TRAINS = 2;
  const MONO_CARS = 3;
  const stockGeo = own(coachGeometry(3.4, 1.9, 1.5));
  const trainMesh = new THREE.InstancedMesh(stockGeo, mat, COACHES);
  const monoGeo = own(coachGeometry(3.0, 1.3, 1.1));
  const monoCars = new THREE.InstancedMesh(monoGeo, mat, MONO_TRAINS * MONO_CARS);
  for (let i = 0; i < COACHES; i++) trainMesh.setColorAt(i, color.set(i === 0 ? 0x454952 : 0xd4d8de));
  for (let i = 0; i < MONO_TRAINS * MONO_CARS; i++) monoCars.setColorAt(i, color.set(i % MONO_CARS === 0 ? 0x5c616b : 0xe2e5ea));
  for (const m of [trainMesh, monoCars]) {
    if (m.instanceColor) m.instanceColor.needsUpdate = true;
    m.frustumCulled = false;
    m.castShadow = true;
    group.add(m);
  }
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
  const monoHeads = [0, loopLen / 2];
  let railHead = 0;
  let railDir = 1;
  let railWait = 0;

  const m4 = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
  const pos = new THREE.Vector3();
  const one = new THREE.Vector3(1, 1, 1);

  const place = (mesh: THREE.InstancedMesh, i: number, x: number, y: number, z: number, heading: number) => {
    q.setFromAxisAngle(up, heading);
    pos.set(x, y, z);
    m4.compose(pos, q, one);
    mesh.setMatrixAt(i, m4);
  };

  const along = (line: readonly Point[], d: number, offset = 0) => {
    const p = pointAlong(line, d);
    return { x: p.x + Math.cos(p.heading) * offset, z: p.z - Math.sin(p.heading) * offset, heading: p.heading };
  };

  const poseAll = () => {
    cars.forEach((c, i) => {
      const line = infra.highways[c.line].path;
      const len = lens[c.line];
      const d = c.loop ? ((c.dist % len) + len) % len : Math.min(len, Math.max(0, c.dist));
      const p = along(line, d, c.forward ? c.lane : -c.lane);
      place(carMesh, i, p.x, highwayY(p.x, p.z) + 0.1, p.z, c.forward ? p.heading : p.heading + Math.PI);
    });
    carMesh.instanceMatrix.needsUpdate = true;

    for (let i = 0; i < COACHES; i++) {
      const d = Math.min(railLen, Math.max(0, railHead - railDir * i * 3.7));
      const p = pointAlong(rail, d);
      place(trainMesh, i, p.x, t.roadY(p.x, p.z) + 0.2, p.z, railDir === 1 ? p.heading : p.heading + Math.PI);
    }
    trainMesh.instanceMatrix.needsUpdate = true;

    monoHeads.forEach((head, tIdx) => {
      for (let i = 0; i < MONO_CARS; i++) {
        const d = (((head - i * 3.4) % loopLen) + loopLen) % loopLen;
        const p = pointAlong(mono.path, d);
        place(monoCars, tIdx * MONO_CARS + i, p.x, monorailY(p.x, p.z) + 0.2, p.z, p.heading);
      }
    });
    monoCars.instanceMatrix.needsUpdate = true;
  };
  poseAll();

  const getMonorailPosition = (trainIdx = 0) => {
    const head = monoHeads[trainIdx % monoHeads.length] ?? 0;
    const p = pointAlong(mono.path, head);
    return { x: p.x, y: monorailY(p.x, p.z) + 0.6, z: p.z, heading: p.heading };
  };

  return {
    group,
    monoCars,
    getMonorailPosition,
    setReducedMotion(v) {
      reduced = v;
    },
    update(dtMs) {
      if (reduced) return;
      const dt = dtMs / 1000;
      for (const c of cars) {
        const len = lens[c.line];
        c.dist += (c.forward ? 1 : -1) * c.speed * dt;
        if (c.loop) {
          c.dist = ((c.dist % len) + len) % len;
        } else if (c.dist >= len) {
          c.dist = len;
          c.forward = false;
        } else if (c.dist <= 0) {
          c.dist = 0;
          c.forward = true;
        }
      }
      if (railWait > 0) railWait -= dt;
      else {
        railHead += railDir * 9 * dt;
        if (railDir === 1 && railHead >= railLen) {
          railHead = railLen;
          railDir = -1;
          railWait = 5;
        } else if (railDir === -1 && railHead <= 3.7 * (COACHES - 1)) {
          railHead = 3.7 * (COACHES - 1);
          railDir = 1;
          railWait = 5;
        }
      }
      for (let i = 0; i < monoHeads.length; i++) {
        let near = loopLen;
        for (const sd of stationDist) {
          const raw = Math.abs(monoHeads[i] - sd);
          near = Math.min(near, raw, loopLen - raw);
        }
        monoHeads[i] = (monoHeads[i] + (1.2 + 5.5 * smooth(0, 14, near)) * dt + loopLen) % loopLen;
      }
      poseAll();
    },
    dispose() {
      disposables.forEach((d) => d.dispose());
      carMesh.dispose();
      trainMesh.dispose();
      monoCars.dispose();
    },
  };
}
