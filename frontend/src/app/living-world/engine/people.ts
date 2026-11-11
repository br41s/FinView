import * as THREE from "three";
import type { Profession } from "../model/pedestrians";
import { PROFESSIONS } from "../model/pedestrians";
import { GeoBuilder, KIND, LIMB, createToyMaterial } from "./toyMaterial";

/**
 * Chibi pedestrians: a big head on a small body, one merged geometry per profession (so a profession
 * is one draw call however many walkers there are), drawn as `InstancedMesh`es.
 *
 *  - worker: orange hard hat, blue overalls over a red-brown shirt, carrying a brick
 *  - executive: dark pinstripe suit, red tie, brown briefcase
 *  - courier: orange hoodie, dark backpack, a cardboard parcel in both arms
 *  - analyst: round glasses, brown vest, yellow tie, a clipboard
 *
 * The walk is in the vertex shader (legs and arms swing about the hip and shoulder from `aLimb`, the
 * body bobs), so the CPU only writes a matrix and three numbers per walker. The instance colour is the
 * skin tone; the hair colour is derived from it in the shader.
 */

const SKIN = [0xf5d0b0, 0xe6b48c, 0xc98c5e, 0x9a6540, 0x6e4529, 0xf8dcc4];
const EYE = 0x20242c;

const HIP = 0.5;

function figure(b: GeoBuilder, o: { shirt: number; trousers: number; sleeves?: number; shoes?: number; arms?: boolean }) {
  const sleeves = o.sleeves ?? o.shirt;
  const shoes = o.shoes ?? 0x2b2622;
  // Legs and shoes swing about the hip.
  for (const [s, limb] of [[-1, LIMB.legL], [1, LIMB.legR]] as const) {
    b.cyl(0.085, 0.09, HIP - 0.08, s * 0.13, 0.09, 0, o.trousers, 7, { limb, open: true });
    b.box(0.17, 0.1, 0.27, s * 0.13, 0, 0.04, shoes, { limb });
  }
  // Torso.
  b.box(0.46, 0.46, 0.3, 0, HIP - 0.04, 0, o.shirt);
  // Arms swing about the shoulder; hands are skin.
  if (o.arms !== false) {
    for (const [s, limb] of [[-1, LIMB.armL], [1, LIMB.armR]] as const) {
      b.cyl(0.065, 0.06, 0.4, s * 0.3, 0.52, 0, sleeves, 7, { limb, open: true });
      b.ellipsoid(0.07, 0.07, 0.07, s * 0.3, 0.5, 0, 0xffffff, { limb, kind: KIND.paint }, 5, 4);
    }
  }
  // Head: big, with eyes and cheeks.
  b.ellipsoid(0.33, 0.31, 0.31, 0, 1.12, 0, 0xffffff, { kind: KIND.paint }, 9, 6);
  for (const s of [-1, 1]) {
    b.ellipsoid(0.045, 0.06, 0.03, s * 0.12, 1.14, 0.29, EYE, {}, 5, 4);
  }
}

function hair(b: GeoBuilder) {
  b.cap(0.335, 0, 1.13, -0.01, 0xffffff, { kind: KIND.hair }, Math.PI * 0.5);
}

function worker(): THREE.BufferGeometry {
  const b = new GeoBuilder();
  figure(b, { shirt: 0x9a4b3a, trousers: 0x2f5fb0, shoes: 0x3a2c22 });
  // Overalls: bib and straps over the shirt.
  b.box(0.4, 0.34, 0.32, 0, 0.42, 0.005, 0x2f5fb0);
  for (const s of [-1, 1]) b.box(0.07, 0.3, 0.32, s * 0.15, 0.78, 0, 0x2f5fb0);
  b.box(0.16, 0.1, 0.02, 0, 0.55, 0.16, 0x244a8c);
  // Hard hat.
  b.cap(0.37, 0, 1.19, 0, 0xff8a1f, { kind: KIND.fixed }, Math.PI * 0.47);
  b.cyl(0.4, 0.4, 0.045, 0, 1.16, 0, 0xff8a1f, 10);
  b.box(0.09, 0.08, 0.4, 0, 1.44, 0, 0xe87812);
  // A brick in the right hand.
  b.box(0.26, 0.13, 0.13, 0.3, 0.4, 0.13, 0xb5523a, { limb: LIMB.armR });
  return b.build();
}

function executive(): THREE.BufferGeometry {
  const b = new GeoBuilder();
  const SUIT = 0x23283a;
  figure(b, { shirt: SUIT, trousers: SUIT, shoes: 0x17191f });
  hair(b);
  // Pinstripes.
  for (const x of [-0.16, -0.08, 0, 0.08, 0.16]) {
    b.box(0.014, 0.4, 0.012, x, 0.5, 0.152, 0x59627e);
    b.box(0.014, 0.4, 0.012, x, 0.5, -0.152, 0x59627e);
  }
  // Shirt collar and a red tie.
  b.box(0.16, 0.2, 0.012, 0, 0.74, 0.153, 0xf5f3ee);
  b.box(0.07, 0.07, 0.04, 0, 0.9, 0.16, 0xd1343b);
  b.box(0.065, 0.26, 0.02, 0, 0.62, 0.165, 0xd1343b);
  // Briefcase in the right hand.
  b.box(0.1, 0.26, 0.34, 0.33, 0.16, 0.0, 0x8a5a32, { limb: LIMB.armR });
  b.box(0.04, 0.05, 0.14, 0.33, 0.42, 0, 0x4e3220, { limb: LIMB.armR });
  return b.build();
}

function courier(): THREE.BufferGeometry {
  const b = new GeoBuilder();
  const HOOD = 0xf08a2c;
  figure(b, { shirt: HOOD, trousers: 0x39404e, shoes: 0x1f2229, arms: false });
  // Arms hold the parcel: angled forward, no swing.
  for (const s of [-1, 1]) {
    b.cyl(0.065, 0.06, 0.4, s * 0.29, 0.56, 0.11, HOOD, 7, { rx: -1.0, open: true });
    b.ellipsoid(0.07, 0.07, 0.07, s * 0.27, 0.62, 0.29, 0xffffff, { kind: KIND.paint }, 7, 5);
  }
  // Hood behind the head, pocket on the front.
  b.ellipsoid(0.34, 0.3, 0.26, 0, 1.12, -0.13, HOOD, {}, 8, 6);
  b.box(0.3, 0.1, 0.02, 0, 0.5, 0.152, 0xd97620);
  // Dark backpack and a cardboard parcel with tape.
  b.box(0.34, 0.4, 0.18, 0, 0.5, -0.25, 0x2a2f3a);
  b.box(0.06, 0.4, 0.02, -0.14, 0.52, -0.155, 0x1d2129);
  b.box(0.06, 0.4, 0.02, 0.14, 0.52, -0.155, 0x1d2129);
  b.box(0.34, 0.3, 0.3, 0, 0.52, 0.36, 0xc89a62);
  b.box(0.06, 0.305, 0.31, 0, 0.52, 0.36, 0xe8d8b0);
  return b.build();
}

function analyst(): THREE.BufferGeometry {
  const b = new GeoBuilder();
  figure(b, { shirt: 0xf6f3ee, trousers: 0x5a6272, shoes: 0x2b2622 });
  hair(b);
  // Brown vest over the shirt, yellow tie.
  b.box(0.4, 0.38, 0.33, 0, 0.5, 0.0, 0x7a4f2c);
  b.box(0.1, 0.2, 0.03, 0, 0.7, 0.158, 0xf6f3ee);
  b.box(0.06, 0.07, 0.04, 0, 0.88, 0.17, 0xf2c230);
  b.box(0.06, 0.24, 0.02, 0, 0.66, 0.175, 0xf2c230);
  // Round glasses.
  for (const s of [-1, 1]) b.torus(0.085, 0.017, s * 0.13, 1.14, 0.3, 0x26292f);
  b.box(0.06, 0.016, 0.016, 0, 1.15, 0.3, 0x26292f);
  // Clipboard in the left hand.
  b.box(0.3, 0.38, 0.03, -0.31, 0.27, 0.09, 0xb88a55, { limb: LIMB.armL, rx: 0.2 });
  b.box(0.25, 0.32, 0.012, -0.31, 0.3, 0.115, 0xf8f6f0, { limb: LIMB.armL, rx: 0.2 });
  b.box(0.1, 0.05, 0.02, -0.31, 0.62, 0.1, 0x8d8f96, { limb: LIMB.armL });
  return b.build();
}

const GEOMETRY: Record<Profession, () => THREE.BufferGeometry> = { worker, executive, courier, analyst };

/** One pedestrian's merged geometry (exported for the triangle budget test). */
export const personGeometry = (prof: Profession): THREE.BufferGeometry => GEOMETRY[prof]();

export interface PersonPose {
  x: number;
  y: number;
  z: number;
  yaw: number;
  scale: number;
  /** Index into the skin palette. */
  skin: number;
  /** 0 standing .. 1 walking. */
  walk: number;
  phase: number;
  /** Which agent this is, for picking. */
  owner: number;
}

export class PeopleRenderer {
  readonly meshes: THREE.InstancedMesh[] = [];
  private anim: THREE.InstancedBufferAttribute[] = [];
  private counts: number[] = [];
  private owners: Int32Array[] = [];
  private material = createToyMaterial({ walk: true, paint: [-0.5, 0.5], roughness: 0.75 });
  private m = new THREE.Matrix4();
  private q = new THREE.Quaternion();
  private p = new THREE.Vector3();
  private s = new THREE.Vector3();
  private c = new THREE.Color();
  private up = new THREE.Vector3(0, 1, 0);
  private ray = new THREE.Raycaster();

  constructor(readonly capacity: number) {
    for (const prof of PROFESSIONS) {
      const geo = GEOMETRY[prof]();
      const attr = new THREE.InstancedBufferAttribute(new Float32Array(capacity * 3), 3);
      attr.setUsage(THREE.DynamicDrawUsage);
      geo.setAttribute("aAnim", attr);
      const mesh = new THREE.InstancedMesh(geo, this.material, capacity);
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage);
      for (let i = 0; i < capacity; i++) mesh.setColorAt(i, this.c.set(0xffffff));
      mesh.count = 0;
      mesh.frustumCulled = false;
      mesh.castShadow = true;
      mesh.name = `people-${prof}`;
      this.meshes.push(mesh);
      this.anim.push(attr);
      this.counts.push(0);
      this.owners.push(new Int32Array(capacity).fill(-1));
    }
  }

  begin() {
    this.counts.fill(0);
  }

  add(prof: Profession, o: PersonPose) {
    const k = PROFESSIONS.indexOf(prof);
    const i = this.counts[k];
    if (i >= this.capacity) return;
    this.counts[k] = i + 1;
    this.q.setFromAxisAngle(this.up, o.yaw);
    this.p.set(o.x, o.y, o.z);
    this.s.set(o.scale, o.scale, o.scale);
    this.m.compose(this.p, this.q, this.s);
    const mesh = this.meshes[k];
    mesh.setMatrixAt(i, this.m);
    mesh.setColorAt(i, this.c.set(SKIN[o.skin % SKIN.length]));
    this.anim[k].setXYZ(i, o.phase, o.walk, 7.4);
    this.owners[k][i] = o.owner;
  }

  end() {
    this.meshes.forEach((mesh, k) => {
      mesh.count = this.counts[k];
      mesh.instanceMatrix.needsUpdate = true;
      if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
      this.anim[k].needsUpdate = true;
    });
  }

  /** The agent under a pointer ray, or -1. */
  pick(raycaster: THREE.Raycaster): number {
    let best = -1;
    let bestD = Infinity;
    this.ray.ray.copy(raycaster.ray);
    this.ray.near = raycaster.near;
    this.ray.far = raycaster.far;
    this.meshes.forEach((mesh, k) => {
      if (!mesh.visible || mesh.count === 0) return;
      const hit = this.ray.intersectObject(mesh, false)[0];
      if (hit && hit.instanceId !== undefined && hit.distance < bestD) {
        bestD = hit.distance;
        best = this.owners[k][hit.instanceId];
      }
    });
    return best;
  }

  setVisible(v: boolean) {
    for (const m of this.meshes) m.visible = v;
  }

  dispose() {
    for (const mesh of this.meshes) {
      mesh.geometry.dispose();
      mesh.dispose();
    }
    this.material.dispose();
  }
}
