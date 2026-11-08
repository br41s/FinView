import * as THREE from "three";
import { seeded } from "../model/rng";
import type { Terrain } from "../model/terrain";
import type { FillerKind, FillerSpot } from "../model/townLayout";
import { Builder } from "./buildingFactory";

/**
 * Generic buildings: the homes, offices and towers that make the town a city. They are
 * scenery, not holdings: muted colours, no labels, never clickable. One InstancedMesh per
 * kind, so a few hundred of them cost a handful of draw calls.
 *
 * Prototypes are modelled on a 1 x 1 footprint; each instance scales x/z by its width and y
 * by its own height factor, and tints the walls through the instance colour.
 */

const GLASS = 0x56677c;
const GLASS_LIGHT = 0x8aa2b8;
const SLAB = 0xf4f1ea;
const ROOF = 0xc9694f;

// Portfolio holdings are the landmarks. Keep decorative buildings clearly subordinate.
const WIDTH_SCALE = 0.86;
const HEIGHT_SCALE: Record<FillerKind, number> = {
  skyscraper: 0.08,
  tower: 0.2,
  block: 0.3,
  house: 0.45,
  villa: 0.42,
  shed: 0.38,
};

/** Floors as alternating glass and slab, so a stretched tower still reads as storeys. */
function storeys(b: Builder, w: number, y0: number, floors: number, floorH: number, glass = GLASS) {
  for (let i = 0; i < floors; i++) {
    b.box(w, floorH * 0.7, w, 0, y0 + i * floorH, 0, glass);
    b.box(w + 0.04, floorH * 0.3, w + 0.04, 0, y0 + i * floorH + floorH * 0.7, 0, SLAB);
  }
  return y0 + floors * floorH;
}

const RECIPE: Record<FillerKind, (b: Builder) => void> = {
  skyscraper(b) {
    b.box(1.0, 1.6, 1.0, 0, 0, 0, SLAB);
    const top = storeys(b, 0.78, 1.6, 15, 1.1, GLASS_LIGHT);
    b.box(0.58, 1.6, 0.58, 0, top, 0, SLAB);
    b.box(0.34, 1.0, 0.34, 0, top + 1.6, 0, GLASS);
    b.cyl(0.02, 0.03, 3.2, 0, top + 2.6, 0, 0x4a4f5a, 4);
  },
  tower(b) {
    b.box(1.0, 1.0, 1.0, 0, 0, 0, SLAB);
    const top = storeys(b, 0.86, 1.0, 8, 1.1);
    b.box(0.9, 0.3, 0.9, 0, top, 0, SLAB);
    b.box(0.35, 0.5, 0.35, 0.15, top + 0.3, 0.1, 0xb9bec7);
  },
  block(b) {
    const top = storeys(b, 0.94, 0, 5, 1.05);
    b.box(1.0, 0.25, 1.0, 0, top, 0, SLAB);
    b.box(0.3, 0.45, 0.3, -0.2, top + 0.25, 0.15, 0xb9bec7);
    b.box(0.22, 0.3, 0.5, 0.25, top + 0.25, -0.1, 0xb9bec7);
  },
  house(b) {
    b.box(0.8, 1.35, 0.7, 0, 0, 0, SLAB);
    b.box(0.2, 0.34, 0.02, -0.2, 0.55, 0.36, GLASS_LIGHT);
    b.box(0.2, 0.34, 0.02, 0.2, 0.55, 0.36, GLASS_LIGHT);
    b.box(0.2, 0.55, 0.02, 0, 0, 0.36, 0x8b5e3c);
    b.pyramid(1.0, 0.9, 0, 1.35, 0, ROOF);
  },
  villa(b) {
    b.box(1.2, 0.06, 1.2, 0, 0, 0, 0x7fc06e);
    b.box(0.8, 1.2, 0.5, -0.1, 0.06, 0.05, SLAB);
    b.box(0.5, 0.8, 0.4, 0.3, 0.06, -0.02, SLAB);
    b.box(0.9, 0.12, 0.6, -0.1, 1.26, 0.05, 0x9aa3ad);
    b.box(0.2, 0.34, 0.02, -0.3, 0.6, 0.31, GLASS_LIGHT);
    b.box(0.2, 0.34, 0.02, 0.1, 0.6, 0.31, GLASS_LIGHT);
    b.box(0.5, 0.05, 0.28, 0.05, 0.06, 0.4, 0x5fb8de);
  },
  shed(b) {
    b.box(1.0, 1.3, 0.72, 0, 0, 0, SLAB);
    for (let i = 0; i < 3; i++) b.tilted(0.34, 0.07, 0.74, -0.3 + i * 0.3, 1.45, 0, 0x8d949d, 0.5);
    b.box(0.28, 0.7, 0.02, 0.2, 0, 0.37, 0x6b7280);
    b.cyl(0.07, 0.07, 1.0, 0.38, 1.3, -0.22, 0xb9bec7, 6);
  },
};

/** Wall tints per kind: soft, muted, so the holdings (saturated) stay the landmarks. */
const TINTS: Record<FillerKind, number[]> = {
  skyscraper: [0xdfe9f2, 0xe9eef3, 0xd6e0e8, 0xf2f2f2],
  tower: [0xe8e2d6, 0xdde6ec, 0xeadfd9, 0xe3e8dd],
  block: [0xf0e0c8, 0xe9cfc0, 0xd9e4d2, 0xe6d9e8, 0xf2ead2],
  house: [0xf4e6cf, 0xefd6c2, 0xe3ecd6, 0xf1e0e0, 0xdbe6ef],
  villa: [0xfbf4e6, 0xf3ece0, 0xeaf0f2],
  shed: [0xc9ced6, 0xd5cdbd, 0xbfc7c0],
};

export interface Fillers {
  group: THREE.Group;
  /** Draw this share of the buildings (spread evenly over the town). */
  setDensity(share: number): void;
  dispose(): void;
}

export function buildFillers(spots: readonly FillerSpot[], terrain: Terrain): Fillers {
  const group = new THREE.Group();
  const disposables: Array<{ dispose(): void }> = [];
  const meshes: THREE.InstancedMesh[] = [];
  const material = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true });
  disposables.push(material);

  // A stable shuffle, so that drawing 45 % of each kind thins the town evenly.
  const rng = seeded(0xf111);
  const order = spots.map((s, i) => ({ s, k: rng(), i })).sort((a, b) => a.k - b.k || a.i - b.i).map((o) => o.s);

  const m4 = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
  const pos = new THREE.Vector3();
  const sc = new THREE.Vector3();
  const col = new THREE.Color();

  for (const kind of Object.keys(RECIPE) as FillerKind[]) {
    const items = order.filter((s) => s.kind === kind);
    if (items.length === 0) continue;
    const b = new Builder();
    RECIPE[kind](b);
    const geo = b.build();
    disposables.push(geo);
    const mesh = new THREE.InstancedMesh(geo, material, items.length);
    items.forEach((s, i) => {
      q.setFromAxisAngle(up, s.rotationY);
      pos.set(s.x, terrain.heightAt(s.x, s.z), s.z);
      sc.set(s.width * WIDTH_SCALE, s.tall * HEIGHT_SCALE[kind], s.width * WIDTH_SCALE);
      m4.compose(pos, q, sc);
      mesh.setMatrixAt(i, m4);
      const palette = TINTS[kind];
      mesh.setColorAt(i, col.set(palette[Math.floor(s.tone * palette.length) % palette.length]));
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.castShadow = kind === "skyscraper" || kind === "tower" || kind === "block";
    mesh.receiveShadow = true;
    mesh.userData.total = items.length;
    mesh.computeBoundingSphere();
    group.add(mesh);
    meshes.push(mesh);
  }

  return {
    group,
    setDensity(share) {
      for (const m of meshes) m.count = Math.max(0, Math.round((m.userData.total as number) * Math.min(1, Math.max(0, share))));
    },
    dispose() {
      disposables.forEach((d) => d.dispose());
      meshes.forEach((m) => m.dispose());
    },
  };
}
