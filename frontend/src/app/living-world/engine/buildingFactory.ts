import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { hashString, seeded } from "../model/rng";
import { componentCount, type Tier } from "../model/scale";
import type { Archetype, WorldAsset } from "../model/types";

/**
 * Portfolio company buildings (spec §9.3).
 *
 * Visual rule: Portfolio holdings are the vibrant, full-colour protagonists of the city,
 * contrasting sharply against the grayscale "atrezzo" city fabric. Each site stands on a
 * colour-trimmed corporate plaza podium and merges its entire complex into ONE mesh with
 * vertex colours, keeping ~100 companies at ~100 draw calls regardless of architectural detail.
 */

/** Footprint a tier is modelled at; the engine scales the group to the real footprint. */
export const NOMINAL: Record<Tier, number> = { outpost: 3.6, small: 5.0, campus: 7.4, major: 10.4 };

export interface Site {
  group: THREE.Group;
  mesh: THREE.Mesh;
  material: THREE.MeshLambertMaterial;
  brandPlate: THREE.Mesh;
  brandMaterial: THREE.MeshBasicMaterial;
  nominal: number;
  /** Height of the tallest part at nominal scale, for markers above the roof. */
  top: number;
  /** Where the company sign stands (local, nominal scale). */
  sign: THREE.Vector3;
}

export class Builder {
  private parts: THREE.BufferGeometry[] = [];
  top = 0;
  private color = new THREE.Color();

  private push(g: THREE.BufferGeometry, x: number, y: number, z: number, hex: number, ry = 0, rz = 0) {
    if (ry) g.rotateY(ry);
    if (rz) g.rotateZ(rz);
    g.translate(x, y, z);
    g.deleteAttribute("uv");
    this.color.set(hex);
    const n = g.getAttribute("position").count;
    const c = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) {
      c[i * 3] = this.color.r;
      c[i * 3 + 1] = this.color.g;
      c[i * 3 + 2] = this.color.b;
    }
    g.setAttribute("color", new THREE.BufferAttribute(c, 3));
    g.computeBoundingBox();
    this.top = Math.max(this.top, g.boundingBox!.max.y);
    this.parts.push(g);
  }

  /** `y` is the bottom of the box. */
  box(w: number, h: number, d: number, x: number, y: number, z: number, hex: number, ry = 0) {
    this.push(new THREE.BoxGeometry(w, h, d), x, y + h / 2, z, hex, ry);
  }
  cyl(rt: number, rb: number, h: number, x: number, y: number, z: number, hex: number, seg = 10) {
    this.push(new THREE.CylinderGeometry(rt, rb, h, seg), x, y + h / 2, z, hex);
  }
  cone(r: number, h: number, x: number, y: number, z: number, hex: number, seg = 8) {
    this.push(new THREE.ConeGeometry(r, h, seg), x, y + h / 2, z, hex);
  }
  /** A four-sided pyramid roof with a square base of side `base`. */
  pyramid(base: number, h: number, x: number, y: number, z: number, hex: number) {
    this.push(new THREE.ConeGeometry(base / Math.SQRT2, h, 4), x, y + h / 2, z, hex, Math.PI / 4);
  }
  sphere(r: number, x: number, y: number, z: number, hex: number) {
    this.push(new THREE.SphereGeometry(r, 10, 8), x, y + r, z, hex);
  }
  /** A box tilted around Z, for conveyors, panels and blades. `y` is its centre. */
  tilted(w: number, h: number, d: number, x: number, y: number, z: number, hex: number, rz: number, ry = 0) {
    this.push(new THREE.BoxGeometry(w, h, d), x, y, z, hex, ry, rz);
  }

  build(): THREE.BufferGeometry {
    const merged = mergeGeometries(this.parts, false);
    this.parts.forEach((g) => g.dispose());
    this.parts = [];
    merged.computeBoundingSphere();
    return merged;
  }
}

interface Ctx {
  b: Builder;
  /** Number of sub-buildings the tier unlocks (1–4+). */
  k: number;
  n: number;
  accent: number;
  rnd: () => number;
}

const hex = (c: THREE.Color) => c.getHex();
const WHITE = 0xfaf7f0;
const GREY = 0xb9c0c8;
const DARK = 0x353c47;
const GLASS = 0x5ab9ea;
const GLASS_BRIGHT = 0x8be0ff;
const GROUND_PAD = 0xf3ede0;
const GOLD = 0xf0b938;
const PLANTER_GREEN = 0x399c58;

/**
 * Corporate plaza base: grounded foundation, corporate-coloured perimeter curb,
 * forecourt paving, and landscaped corner planters so every portfolio site immediately
 * pops from the grayscale city fabric.
 */
function plot(c: Ctx) {
  const s = c.n * 1.12;
  // Sub-grade foundation skirt so sloped ground never leaves a gap.
  c.b.box(s + 0.16, 0.24, s + 0.16, 0, -0.18, 0, DARK);
  // Colored corporate perimeter frame.
  c.b.box(s + 0.08, 0.08, s + 0.08, 0, 0.04, 0, c.accent);
  // Warm travertine/limestone corporate plaza deck.
  c.b.box(s, 0.12, s, 0, 0.06, 0, GROUND_PAD);
  // Forecourt promenade and accent entrance carpet.
  c.b.box(s * 0.88, 0.035, 0.28, 0, 0.17, s * 0.35, 0xd8d0bc);
  c.b.box(0.38, 0.04, s * 0.34, 0, 0.17, s * 0.31, c.accent);
  // Landscaped corner planters with vibrant greenery.
  for (const side of [-1, 1]) {
    const px = side * s * 0.38;
    const pz = s * 0.38;
    c.b.box(0.56, 0.14, 0.38, px, 0.17, pz, WHITE);
    c.b.box(0.48, 0.12, 0.3, px, 0.28, pz, PLANTER_GREEN);
  }
}

function facadeWindows(b: Builder, columns: number, floors: number, width: number, winW: number, winH: number, x: number, y: number, z: number, glass = GLASS) {
  for (let row = 0; row < floors; row++) {
    for (let col = 0; col < columns; col++) {
      const px = x - width / 2 + ((col + 0.5) * width) / columns;
      b.box(winW, winH, 0.05, px, y + row * (winH + 0.14), z, glass);
      b.box(winW + 0.07, 0.055, 0.065, px, y + row * (winH + 0.14) - 0.055, z, WHITE);
    }
  }
}

function solarArray(b: Builder, x: number, z: number, cols: number, rows: number, size: number, y: number, color = 0x2268a8) {
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      b.tilted(size, 0.055, size * 0.72, x + col * size * 1.12, y, z + row * size * 0.9, color, -0.18);
    }
  }
}

function helipad(b: Builder, x: number, y: number, z: number, size = 1.0) {
  b.box(size, 0.06, size, x, y, z, 0x242830);
  b.cyl(size * 0.42, size * 0.42, 0.07, x, y + 0.01, z, 0xf0c030, 16);
  b.cyl(size * 0.35, size * 0.35, 0.08, x, y + 0.02, z, 0x242830, 16);
  b.box(0.06, 0.09, size * 0.4, x - size * 0.13, y + 0.03, z, WHITE);
  b.box(0.06, 0.09, size * 0.4, x + size * 0.13, y + 0.03, z, WHITE);
  b.box(size * 0.26, 0.09, 0.06, x, y + 0.03, z, WHITE);
}

const RECIPES: Record<Archetype, (c: Ctx) => void> = {
  retail({ b, k, n, accent }) {
    // Vibrant flagship store: glazed double-height shopfront, striped awnings, rooftop beacon.
    const x = -n * 0.08;
    const z = -n * 0.1;
    b.box(n * 0.66, 1.64, n * 0.5, x, 0.16, z, WHITE);
    b.box(n * 0.7, 0.16, n * 0.54, x, 1.8, z, accent);
    facadeWindows(b, 4, 1, n * 0.58, 0.34, 0.6, x, 0.28, z + n * 0.255, GLASS_BRIGHT);
    b.box(0.3, 0.92, 0.06, x + 0.08, 0.18, z + n * 0.265, accent);
    b.box(n * 0.72, 0.12, 0.48, x, 1.0, z + n * 0.02, accent);
    for (let i = 0; i < 6; i++) {
      b.box(n * 0.11, 0.13, 0.5, x - n * 0.33 + i * n * 0.132, 1.0, z + n * 0.02, i % 2 ? WHITE : accent);
    }
    // Upper showroom floor and illuminated rooftop crown.
    b.box(n * 0.55, 0.68, n * 0.38, x, 1.96, z - 0.02, 0xfaf2e4);
    b.box(n * 0.58, 0.1, n * 0.41, x, 2.64, z - 0.02, accent);
    facadeWindows(b, 4, 1, n * 0.48, 0.27, 0.36, x, 2.08, z + n * 0.18, GLASS);
    if (k > 1) {
      b.box(n * 0.32, 1.12, n * 0.28, n * 0.31, 0.16, -n * 0.28, 0xf4efe6);
      b.box(n * 0.34, 0.12, n * 0.3, n * 0.31, 1.28, -n * 0.28, accent);
      b.box(n * 0.18, 0.58, 0.05, n * 0.31, 0.26, -n * 0.13, GLASS_BRIGHT);
    }
    if (k > 2) {
      b.box(n * 0.28, 1.2, n * 0.28, -n * 0.32, 0.16, n * 0.28, 0xf7e6d4);
      b.pyramid(n * 0.32, 0.26, -n * 0.32, 1.36, n * 0.28, accent);
      b.box(n * 0.12, 0.42, 0.07, -n * 0.32, 0.32, n * 0.43, DARK);
    }
    if (k > 3) {
      b.box(0.92, 0.45, 0.56, n * 0.27, 0.16, n * 0.34, accent);
      b.box(0.46, 0.38, 0.5, n * 0.27 + 0.52, 0.16, n * 0.34, GLASS_BRIGHT);
      b.cyl(0.12, 0.12, 0.36, n * 0.27 + 0.52, 0.16, n * 0.34, DARK, 8);
    }
  },
  tech({ b, k, n, accent }) {
    // Glass-and-steel headquarters with skybridge, data-centre wing and glowing dome.
    const x = -n * 0.12, z = -n * 0.1, w = n * 0.39;
    b.box(w, 2.85, w, x, 0.16, z, GLASS);
    b.box(w + 0.14, 0.15, w + 0.14, x, 3.01, z, accent);
    facadeWindows(b, 4, 5, w * 0.82, 0.2, 0.28, x, 0.34, z + w / 2 + 0.03, GLASS_BRIGHT);
    for (let i = 0; i < 3; i++) b.box(0.06, 2.6, 0.09, x - w * 0.35 + i * w * 0.35, 0.24, z + w / 2 + 0.07, WHITE);
    b.box(w * 0.78, 0.1, w * 0.72, x, 3.16, z, DARK);
    b.cyl(0.055, 0.055, 0.92, x, 3.26, z, WHITE, 6);
    b.sphere(0.14, x, 4.08, z, accent);
    if (k > 1) {
      b.box(n * 0.52, 1.02, n * 0.3, n * 0.1, 0.16, n * 0.22, WHITE);
      b.box(n * 0.54, 0.1, n * 0.32, n * 0.1, 1.18, n * 0.22, accent);
      for (let i = 0; i < 5; i++) b.box(0.18, 0.46, 0.06, n * 0.1 - n * 0.22 + i * 0.11, 0.34, n * 0.38, GLASS_BRIGHT);
    }
    if (k > 2) {
      b.box(n * 0.34, 1.65, n * 0.32, n * 0.32, 0.16, -n * 0.28, 0xe8f2fa);
      b.box(n * 0.36, 0.13, n * 0.34, n * 0.32, 1.81, -n * 0.28, accent);
      for (let i = 0; i < 4; i++) b.cyl(0.12, 0.12, 0.54, n * 0.32 - n * 0.12 + i * 0.08, 1.94, -n * 0.28, GLASS, 8);
    }
    if (k > 3) {
      b.box(n * 0.28, 0.84, n * 0.22, -n * 0.34, 0.16, n * 0.3, DARK);
      solarArray(b, -n * 0.34, n * 0.3, 3, 1, 0.23, 1.04);
    }
  },
  semis({ b, k, n, accent }) {
    // Precision EUV fab campus: ultra-clean white hall, accent trusses, nitrogen tanks and scrubbers.
    b.box(n * 0.78, 1.28, n * 0.44, 0, 0.16, -n * 0.08, WHITE);
    b.box(n * 0.82, 0.14, n * 0.48, 0, 1.44, -n * 0.08, accent);
    facadeWindows(b, 5, 1, n * 0.68, 0.22, 0.64, 0, 0.3, n * 0.15, GLASS_BRIGHT);
    for (let i = 0; i < 4; i++) {
      b.box(n * 0.14, 0.15, 0.46, -n * 0.3 + i * n * 0.2, 1.58, -n * 0.08, i % 2 ? GLASS_BRIGHT : accent);
      b.cyl(0.16, 0.16, 0.46, -n * 0.27 + i * n * 0.18, 1.73, -n * 0.3, WHITE, 10);
    }
    if (k > 1) {
      b.cyl(0.36, 0.36, 1.62, n * 0.31, 0.16, n * 0.28, WHITE, 12);
      b.cyl(0.37, 0.37, 0.14, n * 0.31, 1.78, n * 0.28, accent, 12);
      b.box(n * 0.5, 0.11, 0.13, -n * 0.05, 0.6, -n * 0.1, accent);
    }
    if (k > 2) {
      b.box(n * 0.32, 0.88, n * 0.28, -n * 0.3, 0.16, n * 0.3, WHITE);
      b.box(n * 0.34, 0.1, n * 0.3, -n * 0.3, 1.04, n * 0.3, accent);
      for (let i = 0; i < 3; i++) b.box(0.16, 0.52, 0.06, -n * 0.3 - 0.16 + i * 0.16, 0.28, n * 0.45, GLASS_BRIGHT);
    }
    if (k > 3) {
      b.cyl(0.14, 0.2, 2.65, n * 0.4, 0.16, -n * 0.34, DARK);
      b.box(0.7, 0.38, 0.52, n * 0.3, 0.16, n * 0.34, accent);
      b.box(0.72, 0.12, 0.54, n * 0.3, 0.54, n * 0.34, WHITE);
    }
  },
  energy({ b, k, n, accent }) {
    // Industrial energy campus: gleaming storage spheres/tanks, colored pipe racks and flare stack.
    const tank = (x: number, z: number, radius: number, height: number) => {
      b.cyl(radius, radius, height, x, 0.16, z, WHITE, 16);
      b.cyl(radius + 0.02, radius + 0.02, 0.1, x, 0.16 + height * 0.72, z, accent, 16);
      b.sphere(radius, x, 0.16 + height, z, WHITE);
      b.cyl(radius * 0.24, radius * 0.24, 0.12, x, 0.16 + height * 1.14, z, accent, 8);
    };
    tank(-n * 0.22, -n * 0.1, n * 0.17, 1.2);
    if (k > 1) tank(n * 0.15, -n * 0.22, n * 0.14, 1.0);
    b.box(n * 0.46, 0.13, 0.16, -n * 0.05, 0.56, n * 0.26, DARK);
    for (let i = 0; i < 4; i++) b.cyl(0.05, 0.05, 0.84, -n * 0.25 + i * n * 0.16, 0.16, n * 0.28, GREY, 6);
    b.box(n * 0.58, 0.1, 0.12, 0, 1.0, n * 0.28, accent);
    if (k > 2) {
      b.cyl(0.13, 0.18, 2.65, n * 0.36, 0.16, -n * 0.3, DARK, 10);
      b.sphere(0.18, n * 0.36, 2.82, -n * 0.3, 0xff9224);
      b.cyl(0.12, 0.12, 1.3, -n * 0.38, 0.16, -n * 0.32, WHITE, 8);
      b.cyl(0.13, 0.13, 0.12, -n * 0.38, 1.46, -n * 0.32, accent, 8);
    }
    if (k > 3) {
      b.box(n * 0.4, 0.72, n * 0.28, 0, 0.16, n * 0.36, WHITE);
      b.box(n * 0.42, 0.12, n * 0.3, 0, 0.88, n * 0.36, accent);
      for (let i = 0; i < 5; i++) b.box(0.08, 0.44, 0.04, -n * 0.16 + i * 0.08, 0.26, n * 0.51, GLASS_BRIGHT);
    }
  },
  mining({ b, k, n, accent }) {
    // Terraced mineral complex with copper/gold ore benches, accent conveyor and processing plant.
    b.cyl(n * 0.43, n * 0.46, 0.22, 0, 0.16, 0, 0xb88b58, 14);
    b.cyl(n * 0.34, n * 0.38, 0.22, 0, 0.38, 0, 0x9c7244, 14);
    b.cyl(n * 0.24, n * 0.28, 0.22, 0, 0.6, 0, 0x7d5a36, 14);
    b.cyl(n * 0.13, n * 0.17, 0.2, 0, 0.82, 0, GOLD, 14);
    if (k > 1) {
      b.tilted(n * 0.72, 0.18, 0.3, n * 0.04, 1.15, n * 0.28, accent, 0.3);
      b.box(0.16, 1.04, 0.16, -n * 0.28, 0.16, n * 0.3, WHITE);
      b.box(0.16, 0.84, 0.16, n * 0.32, 0.16, n * 0.3, WHITE);
      b.cone(0.52, 0.74, -n * 0.34, 0.16, n * 0.3, 0xd49b4b, 7);
    }
    if (k > 2) {
      b.box(0.92, 0.54, 0.72, n * 0.3, 0.16, -n * 0.28, accent);
      b.box(0.12, 1.45, 0.12, n * 0.3, 0.7, -n * 0.28, DARK);
      b.box(0.66, 0.2, 0.18, n * 0.3, 0.82, -n * 0.28, GOLD);
      b.cyl(0.22, 0.22, 0.54, n * 0.28, 0.16, -n * 0.08, WHITE, 8);
    }
    if (k > 3) {
      b.box(n * 0.5, 0.1, 0.22, 0, 0.16, -n * 0.42, DARK);
      b.box(0.82, 0.44, 0.42, -n * 0.1, 0.26, -n * 0.42, accent);
      b.cyl(0.11, 0.11, 0.78, -n * 0.35, 0.16, -n * 0.36, GOLD, 8);
    }
  },
  banking({ b, k, n, accent }) {
    // Grand financial headquarters with marble portico, columns, golden medallion and glass annex.
    b.box(n * 0.68, 1.64, n * 0.44, 0, 0.16, -n * 0.08, 0xf7f0df);
    b.box(n * 0.78, 0.18, n * 0.52, 0, 1.8, -n * 0.06, accent);
    for (let i = 0; i < 6; i++) {
      const x = -n * 0.3 + i * n * 0.12;
      b.cyl(0.11, 0.14, 1.62, x, 0.16, n * 0.18, WHITE, 10);
      b.cyl(0.17, 0.17, 0.1, x, 1.76, n * 0.18, GOLD, 10);
      b.cyl(0.17, 0.17, 0.1, x, 0.16, n * 0.18, GOLD, 10);
    }
    b.pyramid(n * 0.82, 0.58, 0, 1.98, -n * 0.08, accent);
    b.box(n * 0.34, 0.08, 0.09, 0, 2.56, n * 0.13, accent);
    b.cyl(0.36, 0.36, 0.1, 0, 2.58, n * 0.17, GOLD, 14);
    b.box(n * 0.74, 0.12, 0.62, 0, 0.16, n * 0.32, 0xe2d8c3);
    b.box(n * 0.62, 0.12, 0.48, 0, 0.28, n * 0.32, WHITE);
    if (k > 1) {
      b.box(n * 0.3, 1.15, n * 0.26, n * 0.34, 0.16, -n * 0.3, GLASS);
      b.box(n * 0.32, 0.1, n * 0.28, n * 0.34, 1.31, -n * 0.3, accent);
      facadeWindows(b, 3, 2, n * 0.24, 0.16, 0.24, n * 0.34, 0.32, -n * 0.16, GLASS_BRIGHT);
    }
    if (k > 2) {
      b.box(n * 0.28, 1.04, n * 0.24, -n * 0.34, 0.16, -n * 0.32, WHITE);
      b.box(n * 0.3, 0.12, n * 0.26, -n * 0.34, 1.2, -n * 0.32, accent);
    }
    if (k > 3) {
      b.box(0.72, 0.44, 0.42, n * 0.34, 0.16, n * 0.3, accent);
      b.box(0.32, 0.34, 0.4, n * 0.34 + 0.5, 0.16, n * 0.3, GOLD);
    }
  },
  health({ b, k, n, accent }) {
    // Biotech & hospital campus: crisp white wings, aqua/emerald labs, ruby cross & biodome.
    b.box(n * 0.56, 1.52, n * 0.42, -n * 0.1, 0.16, -n * 0.1, WHITE);
    b.box(n * 0.58, 0.14, n * 0.44, -n * 0.1, 1.68, -n * 0.1, accent);
    facadeWindows(b, 4, 2, n * 0.48, 0.16, 0.28, -n * 0.1, 0.32, n * 0.12, GLASS_BRIGHT);
    b.box(n * 0.09, 0.58, 0.09, -n * 0.1, 1.82, n * 0.12, 0xe63946);
    b.box(0.58, 0.14, 0.09, -n * 0.1, 2.04, n * 0.12, 0xe63946);
    if (k > 1) {
      b.box(n * 0.34, 1.16, n * 0.3, n * 0.3, 0.16, -n * 0.26, 0xebf7fa);
      b.box(n * 0.36, 0.1, n * 0.32, n * 0.3, 1.32, -n * 0.26, accent);
      facadeWindows(b, 3, 2, n * 0.28, 0.13, 0.22, n * 0.3, 0.32, -n * 0.1, GLASS_BRIGHT);
      b.sphere(n * 0.18, n * 0.3, 0.16, n * 0.22, GLASS_BRIGHT);
    }
    if (k > 2) {
      b.box(n * 0.36, 0.96, n * 0.27, -n * 0.32, 0.16, n * 0.3, WHITE);
      b.box(n * 0.4, 0.12, n * 0.3, -n * 0.32, 1.12, n * 0.3, 0x2ec4b6);
      b.cyl(0.18, 0.18, 1.35, n * 0.42, 0.16, -n * 0.3, WHITE, 10);
    }
    if (k > 3) {
      b.box(n * 0.3, 0.76, n * 0.24, -n * 0.34, 0.16, -n * 0.3, WHITE);
      b.box(0.82, 0.14, 0.44, n * 0.28, 0.16, n * 0.38, WHITE);
      b.box(0.28, 0.26, 0.07, n * 0.28, 0.28, n * 0.58, accent);
    }
  },
  consumer({ b, k, n, accent }) {
    // Consumer-goods flagship plant: warm sandstone hall, branded silos and dispatch fleet.
    b.box(n * 0.7, 1.34, n * 0.46, -n * 0.08, 0.16, -n * 0.12, 0xf6e2c3);
    b.box(n * 0.74, 0.14, n * 0.5, -n * 0.08, 1.5, -n * 0.12, accent);
    facadeWindows(b, 5, 1, n * 0.62, 0.19, 0.5, -n * 0.08, 0.38, n * 0.12, GLASS_BRIGHT);
    b.box(n * 0.16, 0.8, 0.08, -n * 0.08, 0.26, n * 0.245, accent);
    b.cyl(n * 0.14, n * 0.14, 1.7, n * 0.3, 0.16, -n * 0.2, WHITE, 12);
    b.cyl(n * 0.15, n * 0.15, 0.12, n * 0.3, 1.78, -n * 0.2, accent, 12);
    b.cone(n * 0.14, 0.26, n * 0.3, 1.9, -n * 0.2, GOLD, 12);
    if (k > 1) {
      b.cyl(n * 0.12, n * 0.12, 1.4, n * 0.02, 0.16, n * 0.28, WHITE, 12);
      b.cyl(n * 0.13, n * 0.13, 0.1, n * 0.02, 1.48, n * 0.28, accent, 12);
      b.box(n * 0.38, 0.12, 0.16, n * 0.1, 0.76, n * 0.27, accent);
    }
    if (k > 2) {
      b.box(n * 0.36, 0.88, n * 0.28, -n * 0.32, 0.16, n * 0.28, WHITE);
      b.box(n * 0.4, 0.12, n * 0.3, -n * 0.32, 1.04, n * 0.28, accent);
      for (let i = 0; i < 3; i++) b.box(0.12, 0.36, 0.05, -n * 0.42 + i * 0.16, 0.28, n * 0.43, GLASS_BRIGHT);
    }
    if (k > 3) {
      b.box(0.95, 0.5, 0.55, n * 0.25, 0.16, n * 0.36, accent);
      b.box(0.46, 0.4, 0.5, n * 0.25 + 0.58, 0.16, n * 0.36, GLASS_BRIGHT);
      b.cyl(0.1, 0.1, 0.34, n * 0.25 + 0.58, 0.16, n * 0.36, DARK, 6);
    }
  },
  telecom({ b, k, n, accent }) {
    b.box(n * 0.42, 0.88, n * 0.32, -n * 0.18, 0.16, n * 0.1, WHITE);
    b.box(n * 0.44, 0.12, n * 0.34, -n * 0.18, 1.04, n * 0.1, accent);
    b.cone(0.56, 3.45, n * 0.1, 0.16, -n * 0.18, accent, 4);
    b.cone(0.2, 1.25, n * 0.1, 3.55, -n * 0.18, GOLD, 4);
    if (k > 1) {
      b.sphere(0.34, -n * 0.3, 1.0, n * 0.1, GLASS_BRIGHT);
      b.cyl(0.045, 0.045, 0.52, -n * 0.3, 1.0, n * 0.1, accent, 6);
    }
    if (k > 2) {
      b.box(n * 0.3, 0.76, n * 0.24, n * 0.28, 0.16, n * 0.28, WHITE);
      b.box(n * 0.32, 0.1, n * 0.26, n * 0.28, 0.92, n * 0.28, accent);
    }
    if (k > 3) b.cone(0.42, 2.45, -n * 0.32, 0.16, -n * 0.3, accent, 4);
  },
  utilities({ b, k, n, accent }) {
    const turbine = (x: number, z: number, h: number) => {
      b.cyl(0.075, 0.16, h, x, 0.16, z, WHITE, 8);
      b.sphere(0.15, x, h + 0.04, z, accent);
      for (let i = 0; i < 3; i++) b.tilted(0.11, 1.35, 0.045, x, h + 0.74, z + 0.16, WHITE, (i * 2 * Math.PI) / 3 + 0.4, 0);
    };
    turbine(-n * 0.2, -n * 0.1, 2.5);
    b.box(n * 0.36, 0.76, n * 0.28, n * 0.2, 0.16, n * 0.2, WHITE);
    b.box(n * 0.38, 0.12, n * 0.3, n * 0.2, 0.92, n * 0.2, accent);
    if (k > 1) turbine(n * 0.24, -n * 0.26, 2.2);
    if (k > 2) for (let i = 0; i < 3; i++) b.tilted(n * 0.22, 0.055, n * 0.18, -n * 0.28 + i * n * 0.26, 0.54, n * 0.34, 0x1d70b8, -0.5);
    if (k > 3) {
      turbine(-n * 0.36, -n * 0.34, 2.0);
      b.box(n * 0.22, 0.54, n * 0.18, n * 0.38, 0.16, -n * 0.04, accent);
    }
  },
  realestate({ b, k, n, accent }) {
    b.box(n * 0.42, 2.1, n * 0.34, -n * 0.18, 0.16, -n * 0.1, 0xf7ebd6);
    b.box(n * 0.44, 0.14, n * 0.36, -n * 0.18, 2.26, -n * 0.1, accent);
    facadeWindows(b, 3, 4, n * 0.34, 0.18, 0.28, -n * 0.18, 0.34, -n * 0.1 + n * 0.175, GLASS_BRIGHT);
    if (k > 1) {
      b.box(n * 0.32, 1.48, n * 0.3, n * 0.26, 0.16, n * 0.04, WHITE);
      b.box(n * 0.34, 0.12, n * 0.32, n * 0.26, 1.64, n * 0.04, accent);
    }
    if (k > 2) {
      b.box(n * 0.34, 0.96, n * 0.24, -n * 0.14, 0.16, n * 0.3, 0xf8dfca);
      b.box(n * 0.36, 0.1, n * 0.26, -n * 0.14, 1.12, n * 0.3, accent);
    }
    if (k > 3) b.box(n * 0.26, 1.78, n * 0.24, n * 0.3, 0.16, -n * 0.32, GLASS);
  },
  fund({ b, k, n, accent }) {
    b.cyl(n * 0.43, n * 0.45, 0.18, 0, 0.16, 0, 0xf4eee0, 18);
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2;
      b.cyl(0.075, 0.075, 1.24, Math.cos(a) * n * 0.34, 0.34, Math.sin(a) * n * 0.34, WHITE, 6);
    }
    b.cyl(n * 0.41, n * 0.41, 0.12, 0, 1.58, 0, accent, 18);
    b.sphere(n * 0.24 + k * 0.03, 0, 1.66, 0, GLASS_BRIGHT);
    b.cyl(n * 0.18, n * 0.18, 0.08, 0, 1.62, 0, GOLD, 16);
  },
  cash({ b, k, n, accent }) {
    b.box(n * 0.62, 1.06, n * 0.46, 0, 0.16, -n * 0.06, 0xf2ead7);
    b.cyl(0.42, 0.42, 0.16, 0, 0.54, n * 0.18, GOLD, 16);
    b.box(n * 0.66, 0.16, n * 0.5, 0, 1.22, -n * 0.06, accent);
    for (let i = 0; i < Math.min(k + 1, 5); i++) {
      b.cyl(0.23, 0.23, 0.1, n * 0.32 + (i % 2) * 0.05, 0.16 + i * 0.1, n * 0.3, GOLD, 12);
    }
  },
  crypto({ b, k, n, accent }) {
    b.cyl(n * 0.32, n * 0.36, 0.22, 0, 0.16, 0, 0x24293e, 6);
    b.cyl(n * 0.15, n * 0.21, 1.68, 0, 0.38, 0, accent, 6);
    for (let i = 0; i < Math.min(k + 1, 4); i++) {
      const a = (i / 4) * Math.PI * 2 + 0.4;
      b.box(0.36, 0.36, 0.36, Math.cos(a) * n * 0.32, 1.04 + (i % 2) * 0.42, Math.sin(a) * n * 0.32, i % 2 ? 0x3ef2de : 0xf58cff, a);
    }
  },
};

type CompanyIdentity = "iberdrola" | "bbva" | "santander" | "inditex" | "telefonica" | "repsol";

interface CompanyProfile {
  identity: CompanyIdentity;
  accent: number;
  minComponents: number;
}

function companyProfile(asset: Pick<WorldAsset, "ticker" | "name">): CompanyProfile | null {
  const name = asset.name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
  const ticker = (asset.ticker ?? "").toUpperCase().replace(/[^A-Z]/g, "");
  if (name.includes("IBERDROLA") || ticker === "IBE") {
    return { identity: "iberdrola", accent: 0x3fa834, minComponents: 7 };
  }
  if (name.includes("BBVA") || name.includes("BANCO BILBAO VIZCAYA") || ticker === "BBVA") {
    return { identity: "bbva", accent: 0x0a78d6, minComponents: 6 };
  }
  if (name.includes("SANTANDER") || name.includes("BANCO SANTANDER") || (ticker === "SAN" && name.includes("BANCO"))) {
    return { identity: "santander", accent: 0xec0000, minComponents: 6 };
  }
  if (name.includes("INDITEX") || name.includes("INDUSTRIA DE DISENO TEXTIL") || ticker === "ITX") {
    return { identity: "inditex", accent: 0x1e64d8, minComponents: 5 };
  }
  if (name.includes("TELEFONICA") || ticker === "TEF") {
    return { identity: "telefonica", accent: 0x0066ff, minComponents: 5 };
  }
  if (name.includes("REPSOL") || ticker === "REP") {
    return { identity: "repsol", accent: 0xff6b00, minComponents: 5 };
  }
  return null;
}

/** Company-specific corporate colours; other holdings receive a vibrant individual accent. */
export function accentFor(id: string, asset?: Pick<WorldAsset, "ticker" | "name">): number {
  const profile = asset ? companyProfile(asset) : null;
  if (profile) return profile.accent;
  const h = (hashString(id) % 360) / 360;
  return hex(new THREE.Color().setHSL(h, 0.76, 0.48));
}

function iberdrolaCampus({ b, n, accent }: Ctx) {
  // Iberdrola: flagship renewable-energy campus with green HQ tower, wind turbines, solar array & substation.
  const green = accent;
  const blue = 0x10769e;
  // Main energy-control building and two production halls.
  b.box(n * 0.64, 1.38, n * 0.42, -n * 0.1, 0.16, -n * 0.12, 0xf2f7f1);
  b.box(n * 0.68, 0.15, n * 0.46, -n * 0.1, 1.54, -n * 0.12, green);
  facadeWindows(b, 5, 2, n * 0.58, 0.2, 0.34, -n * 0.1, 0.34, n * 0.1, GLASS_BRIGHT);
  b.box(n * 0.32, 1.08, n * 0.27, n * 0.32, 0.16, -n * 0.28, 0xe8f2ec);
  b.box(n * 0.34, 0.12, n * 0.29, n * 0.32, 1.24, -n * 0.28, blue);
  b.box(n * 0.28, 0.92, n * 0.24, -n * 0.35, 0.16, n * 0.29, 0xedf5ee);
  b.box(n * 0.3, 0.12, n * 0.26, -n * 0.35, 1.08, n * 0.29, green);
  // Transformer yard, switchgear and high-voltage busbars.
  for (let i = 0; i < 4; i++) {
    const x = -n * 0.32 + i * n * 0.2;
    b.box(0.52, 0.64, 0.48, x, 0.16, -n * 0.42, 0xc9dad6);
    b.cyl(0.045, 0.045, 0.5, x - 0.12, 0.8, -n * 0.42, blue, 6);
    b.cyl(0.045, 0.045, 0.5, x + 0.12, 0.8, -n * 0.42, blue, 6);
    b.box(0.68, 0.09, 0.09, x, 1.32, -n * 0.42, green);
  }
  for (let i = 0; i < 5; i++) b.cyl(0.045, 0.045, 0.94, -n * 0.36 + i * n * 0.18, 0.16, n * 0.42, blue, 6);
  // Two tall wind turbines and photovoltaic solar bank.
  for (const [x, z, h] of [[n * 0.34, n * 0.28, 4.0], [-n * 0.38, -n * 0.34, 3.3]] as const) {
    b.cyl(0.075, 0.17, h, x, 0.16, z, WHITE, 8);
    b.sphere(0.16, x, h + 0.04, z, blue);
    for (let i = 3; i < 6; i++) b.tilted(0.11, 1.6, 0.045, x, h + 0.8, z + 0.17, green, (i * Math.PI * 2) / 3 + 0.4);
  }
  solarArray(b, -n * 0.28, n * 0.2, 4, 2, 0.42, 1.12, blue);
  b.cyl(0.48, 0.48, 1.36, n * 0.38, 0.16, -n * 0.04, WHITE, 16);
  b.cyl(0.51, 0.51, 0.1, n * 0.38, 1.44, -n * 0.04, green, 16);
}

function bbvaFinancialCampus({ b, n, accent }: Ctx) {
  // BBVA: signature blue-glass financial skyline ("La Vela" inspired flagship + companion towers).
  const cyan = 0x38c4f5;
  b.box(n * 0.92, 0.38, n * 0.72, 0, 0.16, 0, 0xdcebf5);
  b.box(n * 0.95, 0.14, n * 0.75, 0, 0.54, 0, accent);
  const towers = [
    { x: -n * 0.25, z: -n * 0.16, h: 4.3, w: 0.25 },
    { x: n * 0.08, z: -n * 0.12, h: 5.7, w: 0.29 },
    { x: n * 0.31, z: n * 0.16, h: 3.8, w: 0.23 },
  ];
  for (const tower of towers) {
    const width = n * tower.w;
    b.box(width, tower.h, width * 0.82, tower.x, 0.68, tower.z, 0x62b8e8);
    b.box(width + 0.14, 0.14, width * 0.92, tower.x, tower.h + 0.68, tower.z, accent);
    facadeWindows(b, 4, Math.max(3, Math.floor(tower.h / 0.8)), width * 0.82, 0.16, 0.28, tower.x, 0.9, tower.z + width * 0.42, 0xd4f4ff);
    b.box(width * 0.82, 0.1, width * 0.76, tower.x, tower.h + 0.82, tower.z, cyan);
  }
  // Financial plaza pavilion, sky-bridge and cyan helipad disc.
  b.box(n * 0.48, 0.34, n * 0.22, -n * 0.05, 0.72, n * 0.25, WHITE);
  b.cyl(0.6, 0.6, 0.08, -n * 0.25, 1.06, -n * 0.16, cyan, 20);
  b.box(n * 0.18, 0.54, n * 0.14, n * 0.34, 0.68, -n * 0.32, WHITE);
}

function santanderFinancialCampus({ b, n, accent }: Ctx) {
  // Santander: red-crowned horizontal corporate campus with grand classical colonnade and twin wings.
  const ivory = 0xfaf3e6;
  b.box(n * 0.88, 1.82, n * 0.42, 0, 0.16, -n * 0.08, ivory);
  b.box(n * 0.94, 0.18, n * 0.48, 0, 1.98, -n * 0.08, accent);
  b.pyramid(n * 0.96, 0.52, 0, 2.16, -n * 0.08, accent);
  // Classical portico spanning the central facade.
  for (let i = 0; i < 8; i++) {
    const x = -n * 0.36 + i * n * 0.103;
    b.cyl(0.105, 0.14, 1.72, x, 0.16, n * 0.15, WHITE, 12);
    b.cyl(0.17, 0.17, 0.1, x, 1.84, n * 0.15, GOLD, 12);
    b.cyl(0.17, 0.17, 0.1, x, 0.16, n * 0.15, GOLD, 12);
  }
  b.box(n * 0.98, 0.16, 0.26, 0, 1.98, n * 0.15, WHITE);
  // Wide side wings with crimson roof cornices.
  b.box(n * 0.26, 1.3, n * 0.7, -n * 0.36, 0.16, -n * 0.27, ivory);
  b.box(n * 0.26, 1.3, n * 0.7, n * 0.36, 0.16, -n * 0.27, ivory);
  b.box(n * 0.29, 0.14, n * 0.73, -n * 0.36, 1.46, -n * 0.27, accent);
  b.box(n * 0.29, 0.14, n * 0.73, n * 0.36, 1.46, -n * 0.27, accent);
  facadeWindows(b, 7, 1, n * 0.78, 0.32, 0.44, 0, 0.58, n * 0.205, GLASS_BRIGHT);
  b.box(n * 0.84, 0.12, n * 0.24, 0, 0.16, n * 0.42, accent);
}

function inditexFashionHQ({ b, n, accent }: Ctx) {
  // Inditex: Ultra-sleek minimalist architectural glass pavilion, catwalk gallery, illuminated fashion cube, logistics dispatch bay.
  const navy = accent;
  const darkGlass = 0x223547;
  b.box(n * 0.72, 2.1, n * 0.48, -n * 0.08, 0.16, -n * 0.1, WHITE);
  b.box(n * 0.76, 0.16, n * 0.52, -n * 0.08, 2.26, -n * 0.1, navy);
  facadeWindows(b, 5, 2, n * 0.64, 0.28, 0.54, -n * 0.08, 0.38, n * 0.145, GLASS_BRIGHT);
  b.box(n * 0.6, 0.14, n * 0.38, -n * 0.08, 2.42, -n * 0.1, darkGlass);
  b.box(n * 0.52, 0.45, 0.08, -n * 0.08, 2.56, n * 0.09, navy);
  b.box(n * 0.38, 1.15, n * 0.32, n * 0.31, 0.16, -n * 0.26, 0xf0ece1);
  b.box(n * 0.4, 0.12, n * 0.34, n * 0.31, 1.31, -n * 0.26, navy);
  for (let i = 0; i < 3; i++) {
    b.box(0.18, 0.46, 0.06, n * 0.31 - 0.16 + i * 0.16, 0.26, -n * 0.09, DARK);
  }
  b.box(n * 0.22, 0.42, n * 0.22, n * 0.12, 0.82, -n * 0.22, GLASS_BRIGHT);
}

function telefonicaTechCampus({ b, n, accent }: Ctx) {
  // Telefónica: High-tech communications complex ("Distrito Telefónica"), glass tower cluster, satellite dish array, antenna spire.
  const blue = accent;
  b.box(n * 0.48, 3.4, n * 0.44, -n * 0.14, 0.16, -n * 0.12, 0x1a4674);
  b.box(n * 0.52, 0.18, n * 0.48, -n * 0.14, 3.56, -n * 0.12, blue);
  facadeWindows(b, 4, 6, n * 0.42, 0.18, 0.28, -n * 0.14, 0.38, n * 0.105, GLASS_BRIGHT);
  b.cyl(0.06, 0.08, 1.8, -n * 0.14, 3.74, -n * 0.12, WHITE, 6);
  b.sphere(0.16, -n * 0.14, 5.54, -n * 0.12, 0x00f0ff);
  b.box(n * 0.42, 1.25, n * 0.34, n * 0.28, 0.16, -n * 0.24, 0xedf3f8);
  b.box(n * 0.44, 0.12, n * 0.36, n * 0.28, 1.41, -n * 0.24, blue);
  for (const [x, z] of [[n * 0.22, -n * 0.24], [n * 0.34, -n * 0.24]] as const) {
    b.cyl(0.04, 0.04, 0.35, x, 1.53, z, DARK, 6);
    b.sphere(0.18, x, 1.88, z, WHITE);
  }
  b.box(n * 0.36, 0.88, n * 0.32, -n * 0.28, 0.16, n * 0.28, WHITE);
  b.box(n * 0.38, 0.12, n * 0.34, -n * 0.28, 1.04, n * 0.28, blue);
  solarArray(b, -n * 0.28, n * 0.28, 3, 2, 0.22, 1.16, blue);
}

function repsolEnergyHub({ b, n, accent }: Ctx) {
  // Repsol: Signature orange-red energy transition campus, multi-tiered circular innovation lab, hydrogen spheres and canopy.
  const orange = accent;
  const red = 0xd9261c;
  b.box(n * 0.68, 1.54, n * 0.46, -n * 0.08, 0.16, -n * 0.12, WHITE);
  b.box(n * 0.74, 0.16, n * 0.52, -n * 0.08, 1.7, -n * 0.12, orange);
  b.box(n * 0.76, 0.08, n * 0.54, -n * 0.08, 1.86, -n * 0.12, red);
  facadeWindows(b, 5, 2, n * 0.6, 0.22, 0.38, -n * 0.08, 0.38, n * 0.115, GLASS_BRIGHT);
  b.cyl(n * 0.26, n * 0.28, 1.25, n * 0.32, 0.16, -n * 0.24, 0xf6efe5, 18);
  b.cyl(n * 0.28, n * 0.28, 0.12, n * 0.32, 1.41, -n * 0.24, orange, 18);
  b.sphere(n * 0.16, n * 0.32, 1.47, -n * 0.24, GLASS_BRIGHT);
  for (const [x, z] of [[n * 0.28, n * 0.26], [n * 0.12, n * 0.34]] as const) {
    b.cyl(0.08, 0.12, 0.32, x, 0.16, z, DARK, 8);
    b.sphere(0.28, x, 0.48, z, WHITE);
    b.cyl(0.29, 0.29, 0.06, x, 0.76, z, orange, 16);
  }
}

export function createSite(asset: WorldAsset, tier: Tier, unknown: boolean): Site {
  const nominal = NOMINAL[tier];
  const profile = companyProfile(asset);
  const accent = accentFor(asset.id, asset);
  const b = new Builder();
  const componentTotal = Math.max(componentCount(tier), profile?.minComponents ?? 1);
  const ctx: Ctx = { b, k: componentTotal, n: nominal, accent, rnd: seeded(hashString(asset.id)) };
  plot(ctx);
  if (profile?.identity === "iberdrola") iberdrolaCampus(ctx);
  else if (profile?.identity === "bbva") bbvaFinancialCampus(ctx);
  else if (profile?.identity === "santander") santanderFinancialCampus(ctx);
  else if (profile?.identity === "inditex") inditexFashionHQ(ctx);
  else if (profile?.identity === "telefonica") telefonicaTechCampus(ctx);
  else if (profile?.identity === "repsol") repsolEnergyHub(ctx);
  else RECIPES[asset.archetype](ctx);

  if (tier === "major" || tier === "campus") {
    if (asset.archetype === "banking" || asset.archetype === "tech" || profile?.identity === "bbva" || profile?.identity === "santander") {
      helipad(b, 0, b.top, 0, Math.min(1.4, nominal * 0.24));
    }
  }

  // Roadside corporate totem anchoring the plot at street level.
  const sx = nominal * 0.5;
  const sz = nominal * 0.5;
  b.cyl(0.05, 0.05, 1.1, sx, 0.16, sz, DARK, 6);
  b.box(0.86, 0.46, 0.1, sx, 0.88, sz, accent);
  b.box(0.72, 0.09, 0.11, sx, 1.13, sz, WHITE);

  // Unknown valuation: a hazard-yellow diamond on a pole. Never a smaller, quieter site.
  if (unknown) {
    b.cyl(0.03, 0.03, 1.1, -nominal * 0.5, 0.16, sz, DARK, 5);
    b.box(0.4, 0.4, 0.06, -nominal * 0.5, 1.04, sz, 0xf2c230, Math.PI / 4);
  }

  const geometry = b.build();
  const material = new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;

  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 164;
  const canvasCtx = canvas.getContext("2d")!;
  const accentHex = "#" + new THREE.Color(accent).getHexString();
  canvasCtx.fillStyle = accentHex;
  canvasCtx.beginPath();
  canvasCtx.roundRect(4, 4, 504, 156, 22);
  canvasCtx.fill();
  canvasCtx.fillStyle = "#101b29";
  canvasCtx.beginPath();
  canvasCtx.roundRect(12, 12, 488, 140, 17);
  canvasCtx.fill();
  canvasCtx.fillStyle = accentHex;
  canvasCtx.beginPath();
  canvasCtx.roundRect(12, 12, 14, 140, 8);
  canvasCtx.fill();
  const ticker = (asset.ticker?.trim() || asset.name.split(/[^A-Za-z0-9]+/).filter(Boolean).slice(0, 2).map((x) => x[0]).join("") || "•").toUpperCase().slice(0, 12);
  canvasCtx.fillStyle = "#ffffff";
  canvasCtx.textBaseline = "middle";
  let signFontSize = 62;
  canvasCtx.font = "800 " + signFontSize + "px system-ui, sans-serif";
  while (signFontSize > 28 && canvasCtx.measureText(ticker).width > 430) {
    signFontSize -= 2;
    canvasCtx.font = "800 " + signFontSize + "px system-ui, sans-serif";
  }
  canvasCtx.fillText(ticker, 36, 66, 430);
  canvasCtx.fillStyle = "#dbe7f3";
  canvasCtx.font = "600 23px system-ui, sans-serif";
  canvasCtx.fillText(asset.name, 36, 124, 430);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  const brandMaterial = new THREE.MeshBasicMaterial({ map: texture, toneMapped: false, side: THREE.DoubleSide });
  const brandPlate = new THREE.Mesh(new THREE.PlaneGeometry(1.76, 0.56), brandMaterial);
  brandPlate.position.set(0, Math.max(1.08, Math.min(b.top * 0.72, 2.25)), nominal * 0.27);
  brandPlate.renderOrder = 3;

  const group = new THREE.Group();
  group.add(mesh, brandPlate);
  return { group, mesh, material, brandPlate, brandMaterial, nominal, top: b.top, sign: new THREE.Vector3(sx, 0.9, sz) };
}

export function disposeSite(s: Site) {
  s.mesh.geometry.dispose();
  s.material.dispose();
  s.brandPlate.geometry.dispose();
  s.brandMaterial.map?.dispose();
  s.brandMaterial.dispose();
}
