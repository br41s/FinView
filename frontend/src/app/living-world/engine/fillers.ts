import * as THREE from "three";
import { hash2, seeded } from "../model/rng";
import type { Terrain } from "../model/terrain";
import { TALL, WIDTH, type FillerKind, type FillerSpot } from "../model/townLayout";
import { Builder } from "./buildingFactory";
import { fillerColours } from "./fillerPalette";
import { createFacadeMaterial } from "./materials";
import { loft } from "./towers";

/**
 * Generic "atrezzo" buildings: the homes, apartment blocks, offices, sheds and background
 * high-rises that give the city coherent urban fabric.
 *
 * Visual rule: saturated, toy-like colour (coloured glass towers, warm masonry blocks, coloured
 * roofs on homes), a different palette family per kind (`fillerPalette.ts`). They stay subordinate
 * to the holdings through size alone (WIDTH_SCALE / HEIGHT_SCALE), never through grey.
 *
 * Vertex colours here are only shades: the facade material multiplies them by a per-instance wall
 * colour (kind 0), glass colour (kind 1, with window grid) or accent colour (kind 2, roofs).
 * Floors are exactly 1.0 tall and start on whole numbers, so the shader's window rows line up with
 * the storeys. One InstancedMesh per kind keeps all fillers within 6 draw calls; three kinds
 * (skyscraper, tower, house) have a second silhouette (round, stepped, gabled) that takes about
 * half of their spots, picked by a stable hash: 9 draw calls in all.
 */

const WALL = 0xffffff;
const WALL_MID = 0xeceef2;
const WALL_DARK = 0xd2d5dc;
const GLASS_A = 0xffffff;
const GLASS_B = 0xe4ecf5;
const ROOF_A = 0xdcdcdc;
const ROOF_B = 0xb4b4b4;
const PLINTH = 0xaeb3bc;

// Portfolio holdings are the landmarks. Keep decorative buildings subordinate in width
// and height while giving them crisp, believable 2–5 storey urban proportions.
const WIDTH_SCALE = 0.88;
export const HEIGHT_SCALE: Record<FillerKind, number> = {
  skyscraper: 0.27,
  tower: 0.38,
  block: 0.44,
  house: 0.56,
  villa: 0.52,
  shed: 0.48,
};
export const FILLER_WIDTH_SCALE = WIDTH_SCALE;

/** Grounded plinth so filler buildings sit cleanly on sloped terrain without floating edges. */
function plinth(b: Builder, w: number, d: number) {
  b.kind = 0;
  b.box(w + 0.12, 0.24, d + 0.12, 0, -0.18, 0, PLINTH);
}

/** Alternating glass bands and wall spandrels; `floors` storeys of exactly 1.0 from whole-number `y0`. */
function storeys(b: Builder, w: number, d: number, y0: number, floors: number, glass = GLASS_A, slab = WALL) {
  for (let i = 0; i < floors; i++) {
    const y = y0 + i;
    b.kind = 1;
    b.box(w, 0.68, d, 0, y, 0, glass);
    b.kind = 0;
    b.box(w + 0.04, 0.32, d + 0.04, 0, y + 0.68, 0, slab);
  }
  return y0 + floors;
}

const wall = (b: Builder) => void (b.kind = 0);
const glass = (b: Builder) => void (b.kind = 1);
const accent = (b: Builder) => void (b.kind = 2);

type Recipe = (b: Builder) => void;

const RECIPES: Record<FillerKind, Recipe[]> = {
  skyscraper: [(b) => {
    plinth(b, 1.0, 1.0);
    wall(b);
    // Podium + stepped high-rise with mechanical penthouse.
    b.box(1.0, 1.94, 1.0, 0, 0.06, 0, WALL_MID);
    const mid = storeys(b, 0.8, 0.8, 2, 7, GLASS_B, WALL);
    const upper = storeys(b, 0.64, 0.64, mid, 4, GLASS_A, WALL_MID);
    wall(b);
    b.box(0.68, 0.28, 0.68, 0, upper, 0, WALL_DARK);
    accent(b);
    b.box(0.42, 1.1, 0.42, 0, upper + 0.28, 0, ROOF_A);
    wall(b);
    b.cyl(0.025, 0.035, 1.3, 0, upper + 1.38, 0, ROOF_B, 5);
  },
  // A round tower: a drum podium, glass shaft with slab rings, a domed crown.
  (b) => {
    plinth(b, 1.0, 1.0);
    wall(b);
    b.cyl(0.5, 0.52, 1.94, 0, 0.06, 0, WALL_MID, 14);
    const floors = 8;
    glass(b);
    loft(b, { plan: "ellipse", w: 0.84, d: 0.84, cx: 0, cz: 0, y0: 2, h: floors, hex: GLASS_B, kind: 1, cols: 5, colMultiple: 1, segs: 1 });
    wall(b);
    for (let i = 0; i < floors; i++) b.cyl(0.43, 0.43, 0.3, 0, 2 + i + 0.68, 0, WALL, 10);
    accent(b);
    b.cyl(0.45, 0.45, 0.26, 0, 2 + floors, 0, ROOF_A, 12);
    b.sphere(0.2, 0, 2 + floors + 0.2, 0, ROOF_A);
    wall(b);
    b.cyl(0.02, 0.03, 1.1, 0, 2 + floors + 0.6, 0, ROOF_B, 5);
  }],
  tower: [
    (b) => {
      plinth(b, 1.0, 1.0);
      wall(b);
      b.box(0.98, 0.94, 0.98, 0, 0.06, 0, WALL_MID);
      const top = storeys(b, 0.86, 0.86, 1, 7, GLASS_A, WALL);
      wall(b);
      b.box(0.9, 0.28, 0.9, 0, top, 0, WALL_DARK);
      accent(b);
      b.box(0.38, 0.55, 0.38, 0.14, top + 0.28, 0.1, ROOF_A);
      wall(b);
      b.box(0.24, 0.35, 0.24, -0.2, top + 0.28, -0.14, WALL_DARK);
    },
    // Stepped: three setbacks, each with its own roof terrace.
    (b) => {
      plinth(b, 1.0, 1.0);
      wall(b);
      b.box(0.98, 0.94, 0.98, 0, 0.06, 0, WALL_MID);
      let y = 1;
      let w = 0.86;
      for (const fl of [4, 3, 2]) {
        y = storeys(b, w, w, y, fl, GLASS_A, WALL);
        accent(b);
        b.box(w + 0.1, 0.18, w + 0.1, 0, y, 0, ROOF_A);
        wall(b);
        y += 0.18;
        w *= 0.72;
      }
      b.cyl(0.02, 0.03, 0.9, 0.04, y, 0, ROOF_B, 5);
    },
  ],
  block: [
    (b) => {
      plinth(b, 1.0, 0.88);
      const top = storeys(b, 0.94, 0.82, 0, 5, GLASS_B, WALL);
      accent(b);
      b.box(0.98, 0.24, 0.86, 0, top, 0, ROOF_A);
      wall(b);
      b.box(0.32, 0.42, 0.3, -0.2, top + 0.24, 0.12, WALL_DARK);
      b.box(0.24, 0.28, 0.44, 0.24, top + 0.24, -0.08, WALL_MID);
    },
  ],
  house: [
    (b) => {
      plinth(b, 0.86, 0.76);
      wall(b);
      b.box(0.82, 1.32, 0.72, 0, 0.06, 0, WALL);
      glass(b);
      b.box(0.2, 0.34, 0.03, -0.2, 0.6, 0.36, GLASS_A);
      b.box(0.2, 0.34, 0.03, 0.2, 0.6, 0.36, GLASS_A);
      accent(b);
      b.box(0.2, 0.56, 0.03, 0, 0.06, 0.36, ROOF_B);
      b.pyramid(0.98, 0.82, 0, 1.38, 0, ROOF_A);
      wall(b);
      b.box(0.14, 0.48, 0.14, 0.22, 1.65, -0.12, WALL_DARK);
    },
    // Gabled: a ridge roof with a chimney, a porch and a water tank on the side.
    (b) => {
      plinth(b, 0.86, 0.76);
      wall(b);
      b.box(0.82, 1.2, 0.72, 0, 0.06, 0, WALL);
      glass(b);
      b.box(0.2, 0.34, 0.03, -0.22, 0.6, 0.36, GLASS_A);
      b.box(0.2, 0.34, 0.03, 0.22, 0.6, 0.36, GLASS_A);
      accent(b);
      b.box(0.2, 0.56, 0.03, 0, 0.06, 0.36, ROOF_B);
      b.gable(0.92, 0.7, 0.8, 0, 1.26, 0, ROOF_A);
      b.box(0.5, 0.06, 0.16, 0, 0.66, 0.42, ROOF_B);
      wall(b);
      b.box(0.12, 0.5, 0.12, -0.26, 1.5, -0.1, WALL_DARK);
      b.cyl(0.1, 0.1, 0.22, 0.34, 1.6, -0.2, WALL_DARK, 6);
    },
  ],
  villa: [
    (b) => {
      // Courtyard villa: terrace, two white volumes, cantilevered coloured roofs, glass lap pool.
      plinth(b, 1.16, 1.16);
      wall(b);
      b.box(1.14, 0.08, 1.14, 0, 0.06, 0, WALL_MID);
      b.box(0.8, 1.18, 0.5, -0.1, 0.14, 0.04, WALL);
      b.box(0.5, 0.82, 0.42, 0.3, 0.14, -0.02, WALL_MID);
      accent(b);
      b.box(0.9, 0.14, 0.58, -0.1, 1.32, 0.04, ROOF_A);
      b.box(0.56, 0.12, 0.48, 0.3, 0.96, -0.02, ROOF_B);
      glass(b);
      b.box(0.22, 0.36, 0.03, -0.28, 0.64, 0.3, GLASS_A);
      b.box(0.22, 0.36, 0.03, 0.1, 0.64, 0.3, GLASS_A);
      b.box(0.48, 0.04, 0.28, 0.06, 0.14, 0.39, GLASS_B);
    },
  ],
  shed: [
    (b) => {
      plinth(b, 1.04, 0.78);
      wall(b);
      b.box(1.0, 1.28, 0.74, 0, 0.06, 0, WALL);
      accent(b);
      for (let i = 0; i < 3; i++) {
        b.tilted(0.34, 0.08, 0.76, -0.3 + i * 0.3, 1.42, 0, ROOF_A, 0.48);
      }
      b.box(0.3, 0.72, 0.03, 0.2, 0.06, 0.38, ROOF_B);
      wall(b);
      b.cyl(0.075, 0.085, 1.05, 0.36, 1.34, -0.22, WALL_DARK, 6);
      // A water tank on legs.
      for (const [dx, dz] of [[-1, -1], [1, -1], [-1, 1], [1, 1]] as const) b.box(0.025, 0.4, 0.025, -0.3 + dx * 0.08, 1.32, 0.05 + dz * 0.08, WALL_DARK);
      b.cyl(0.13, 0.13, 0.3, -0.3, 1.72, 0.05, WALL_MID, 8);
    },
  ],
};

/** The tallest and widest a filler gets in the town (spire and all), in world units: the size rule's yardstick. */
export function fillerMaxExtent(): { height: number; width: number } {
  let height = 0;
  let width = 0;
  for (const kind of Object.keys(RECIPES) as FillerKind[]) {
    for (const recipe of RECIPES[kind]) {
      const b = new Builder();
      recipe(b);
      height = Math.max(height, b.top * TALL[kind][1] * HEIGHT_SCALE[kind]);
      width = Math.max(width, (WIDTH[kind][1] + 0.12) * WIDTH_SCALE);
      b.build().dispose();
    }
  }
  return { height, width };
}

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
  const material = createFacadeMaterial({
    instanced: true,
    grid: { cols: 5, rows: 1, mullions: true },
    saturation: 1.12,
    windowGlow: 1.6,
  });
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

  // A second silhouette takes about half of the spots of a kind, by a hash that never changes.
  const variantOf = (s: FillerSpot, count: number) => (count === 1 ? 0 : Math.floor(hash2(Math.round(s.x * 10), Math.round(s.z * 10), 3) * count));

  const batches = (Object.keys(RECIPES) as FillerKind[]).flatMap((kind) =>
    RECIPES[kind].map((recipe, v) => ({ kind, recipe, items: order.filter((s) => s.kind === kind && variantOf(s, RECIPES[kind].length) === v) })),
  );
  for (const { kind, recipe, items } of batches) {
    if (items.length === 0) continue;
    const b = new Builder();
    recipe(b);
    const geo = b.build();
    disposables.push(geo);
    const wallAttr = new Float32Array(items.length * 3);
    const glassAttr = new Float32Array(items.length * 3);
    const seedAttr = new Float32Array(items.length);
    const mesh = new THREE.InstancedMesh(geo, material, items.length);
    items.forEach((s, i) => {
      q.setFromAxisAngle(up, s.rotationY);
      pos.set(s.x, terrain.heightAt(s.x, s.z), s.z);
      sc.set(s.width * WIDTH_SCALE, s.tall * HEIGHT_SCALE[kind], s.width * WIDTH_SCALE);
      m4.compose(pos, q, sc);
      mesh.setMatrixAt(i, m4);
      const c = fillerColours(kind, s.tone);
      col.set(c.wall).toArray(wallAttr, i * 3);
      col.set(c.glass).toArray(glassAttr, i * 3);
      seedAttr[i] = hash2(Math.round(s.x * 10), Math.round(s.z * 10), 7);
    });
    geo.setAttribute("aWall", new THREE.InstancedBufferAttribute(wallAttr, 3));
    geo.setAttribute("aGlass", new THREE.InstancedBufferAttribute(glassAttr, 3));
    geo.setAttribute("aSeed", new THREE.InstancedBufferAttribute(seedAttr, 1));
    mesh.instanceMatrix.needsUpdate = true;
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
