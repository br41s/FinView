import * as THREE from "three";
import { seeded } from "../model/rng";
import type { Terrain } from "../model/terrain";
import type { FillerKind, FillerSpot } from "../model/townLayout";
import { Builder } from "./buildingFactory";

/**
 * Generic "atrezzo" buildings: the homes, apartment blocks, offices, sheds and background
 * high-rises that give the city coherent urban fabric.
 *
 * Visual rule: 100% stylized architectural grayscale (monochrome concrete, slate, zinc and
 * graphite glass), never clickable, no labels. This ensures portfolio holdings (full colour,
 * saturated accents, illuminated signage) pop immediately as the protagonists of the scene.
 *
 * One InstancedMesh per kind keeps all filler buildings within 6 draw calls total.
 */

const SLAB_LIGHT = 0xe4e7eb;
const SLAB_MID = 0xccd0d6;
const SLAB_DARK = 0xa7adb5;
const GLASS_DARK = 0x3b3f46;
const GLASS_MID = 0x525760;
const ROOF_SLATE = 0x626770;
const ROOF_DARK = 0x454950;
const PLINTH_GREY = 0x7c828b;

// Portfolio holdings are the landmarks. Keep decorative buildings subordinate in width
// while giving them believable architectural proportions (not squashed pancakes).
const WIDTH_SCALE = 1.12;
const HEIGHT_SCALE: Record<FillerKind, number> = {
  skyscraper: 1.18,
  tower: 1.05,
  block: 0.95,
  house: 0.92,
  villa: 0.88,
  shed: 0.84,
};

/** Grounded plinth so filler buildings sit cleanly on sloped terrain without floating edges. */
function plinth(b: Builder, w: number, d: number) {
  b.box(w + 0.12, 0.24, d + 0.12, 0, -0.18, 0, PLINTH_GREY);
}

/** Alternating dark-slate glass bands and monochrome concrete spandrels. */
function storeys(b: Builder, w: number, d: number, y0: number, floors: number, floorH: number, glass = GLASS_DARK, slab = SLAB_LIGHT) {
  for (let i = 0; i < floors; i++) {
    const y = y0 + i * floorH;
    b.box(w, floorH * 0.68, d, 0, y, 0, glass);
    b.box(w + 0.04, floorH * 0.32, d + 0.04, 0, y + floorH * 0.68, 0, slab);
  }
  return y0 + floors * floorH;
}

const RECIPE: Record<FillerKind, (b: Builder) => void> = {
  skyscraper(b) {
    plinth(b, 1.0, 1.0);
    // Podium + stepped monochrome high-rise with mechanical penthouse.
    b.box(1.0, 1.5, 1.0, 0, 0.06, 0, SLAB_MID);
    b.box(0.92, 0.9, 0.92, 0, 0.3, 0, GLASS_DARK);
    const mid = storeys(b, 0.8, 0.8, 1.56, 9, 1.05, GLASS_MID, SLAB_LIGHT);
    const upper = storeys(b, 0.64, 0.64, mid, 5, 1.0, GLASS_DARK, SLAB_MID);
    b.box(0.68, 0.28, 0.68, 0, upper, 0, SLAB_DARK);
    b.box(0.42, 1.1, 0.42, 0, upper + 0.28, 0, ROOF_SLATE);
    b.cyl(0.025, 0.035, 2.2, 0, upper + 1.38, 0, ROOF_DARK, 5);
  },
  tower(b) {
    plinth(b, 1.0, 1.0);
    b.box(0.98, 1.0, 0.98, 0, 0.06, 0, SLAB_MID);
    const top = storeys(b, 0.86, 0.86, 1.06, 7, 1.05, GLASS_DARK, SLAB_LIGHT);
    b.box(0.9, 0.28, 0.9, 0, top, 0, SLAB_DARK);
    b.box(0.38, 0.55, 0.38, 0.14, top + 0.28, 0.1, ROOF_SLATE);
    b.box(0.24, 0.35, 0.24, -0.2, top + 0.28, -0.14, PLINTH_GREY);
  },
  block(b) {
    plinth(b, 1.0, 0.88);
    const top = storeys(b, 0.94, 0.82, 0.06, 5, 1.0, GLASS_MID, SLAB_LIGHT);
    b.box(0.98, 0.24, 0.86, 0, top, 0, ROOF_SLATE);
    b.box(0.32, 0.42, 0.3, -0.2, top + 0.24, 0.12, SLAB_DARK);
    b.box(0.24, 0.28, 0.44, 0.24, top + 0.24, -0.08, PLINTH_GREY);
  },
  house(b) {
    plinth(b, 0.86, 0.76);
    b.box(0.82, 1.32, 0.72, 0, 0.06, 0, SLAB_LIGHT);
    b.box(0.2, 0.34, 0.03, -0.2, 0.6, 0.36, GLASS_DARK);
    b.box(0.2, 0.34, 0.03, 0.2, 0.6, 0.36, GLASS_DARK);
    b.box(0.2, 0.56, 0.03, 0, 0.06, 0.36, ROOF_DARK);
    b.pyramid(0.98, 0.82, 0, 1.38, 0, ROOF_SLATE);
    b.box(0.14, 0.48, 0.14, 0.22, 1.65, -0.12, SLAB_DARK);
  },
  villa(b) {
    // Monochrome architectural courtyard villa (grey terrace, slate lap pool, cantilevered roof).
    plinth(b, 1.16, 1.16);
    b.box(1.14, 0.08, 1.14, 0, 0.06, 0, SLAB_MID);
    b.box(0.8, 1.18, 0.5, -0.1, 0.14, 0.04, SLAB_LIGHT);
    b.box(0.5, 0.82, 0.42, 0.3, 0.14, -0.02, SLAB_MID);
    b.box(0.9, 0.14, 0.58, -0.1, 1.32, 0.04, ROOF_SLATE);
    b.box(0.56, 0.12, 0.48, 0.3, 0.96, -0.02, ROOF_DARK);
    b.box(0.22, 0.36, 0.03, -0.28, 0.64, 0.3, GLASS_DARK);
    b.box(0.22, 0.36, 0.03, 0.1, 0.64, 0.3, GLASS_DARK);
    b.box(0.48, 0.04, 0.28, 0.06, 0.14, 0.39, GLASS_MID);
  },
  shed(b) {
    plinth(b, 1.04, 0.78);
    b.box(1.0, 1.28, 0.74, 0, 0.06, 0, SLAB_MID);
    for (let i = 0; i < 3; i++) {
      b.tilted(0.34, 0.08, 0.76, -0.3 + i * 0.3, 1.42, 0, ROOF_SLATE, 0.48);
    }
    b.box(0.3, 0.72, 0.03, 0.2, 0.06, 0.38, ROOF_DARK);
    b.cyl(0.075, 0.085, 1.05, 0.36, 1.34, -0.22, PLINTH_GREY, 6);
  },
};

/** Pure achromatic grayscale instance tints so filler buildings never compete with holdings. */
const TINTS: Record<FillerKind, number[]> = {
  skyscraper: [0xdde0e4, 0xcfd4da, 0xc2c7cf, 0xe8ebef],
  tower: [0xd8dce1, 0xc8cdd4, 0xbbc1c9, 0xe2e5e9],
  block: [0xd4d8de, 0xc4c9d0, 0xb8bec6, 0xdfe3e8],
  house: [0xdce0e5, 0xced3d9, 0xc1c6ce, 0xe6e9ed],
  villa: [0xe2e5ea, 0xd5d9df, 0xc8cdd4],
  shed: [0xbfc4cc, 0xb2b7c0, 0xcbd0d7],
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
