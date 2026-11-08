import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { hashString, seeded } from "../model/rng";
import { componentCount, type Tier } from "../model/scale";
import type { Archetype, WorldAsset } from "../model/types";

/**
 * Procedural, toy-like buildings (spec §9.3). Each site is ONE merged mesh with vertex
 * colours, so 100 companies cost ~100 draw calls however detailed they are. The factory
 * is the seam where Phase 4 can swap in authored glTF kits: it only has to return a `Site`.
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
  /** Number of sub-buildings the tier unlocks (1–4). */
  k: number;
  n: number;
  accent: number;
  rnd: () => number;
}

const hex = (c: THREE.Color) => c.getHex();
const WHITE = 0xf4f1ea;
const GREY = 0xb9bcc2;
const DARK = 0x4a4f5a;
const GLASS = 0x8fc7e8;
const ROOF_RED = 0xc9604f;
const GROUND_PAD = 0xd9d2bd;
const GOLD = 0xd5ac53;

/** A paved plot every site stands on, so a building reads as a lot and not as a prop. */
function plot(c: Ctx) {
  const s = c.n * 1.12;
  c.b.box(s, 0.12, s, 0, 0, 0, GROUND_PAD);
  // Distinct paving strips and front plaza so each holding reads as a developed site.
  c.b.box(s * 0.88, 0.035, 0.24, 0, 0.13, s * 0.34, 0xc4bea9);
  c.b.box(0.24, 0.035, s * 0.76, -s * 0.34, 0.13, 0, 0xc4bea9);
}

function facadeWindows(b: Builder, columns: number, floors: number, width: number, winW: number, winH: number, x: number, y: number, z: number, glass = GLASS) {
  for (let row = 0; row < floors; row++) {
    for (let col = 0; col < columns; col++) {
      const px = x - width / 2 + ((col + 0.5) * width) / columns;
      b.box(winW, winH, 0.045, px, y + row * (winH + 0.14), z, glass);
      b.box(winW + 0.07, 0.055, 0.06, px, y + row * (winH + 0.14) - 0.055, z, WHITE);
    }
  }
}

function solarArray(b: Builder, x: number, z: number, cols: number, rows: number, size: number, y: number, color = 0x416a9b) {
  for (let row = 0; row < rows; row++) {
    for (let col = 0; col < cols; col++) {
      b.tilted(size, 0.055, size * 0.72, x + col * size * 1.12, y, z + row * size * 0.9, color, -0.18);
    }
  }
}

const RECIPES: Record<Archetype, (c: Ctx) => void> = {
  retail({ b, k, n, accent }) {
    // Flagship store: deep glazed shopfront, awnings, display windows and a delivery bay.
    const x = -n * 0.08;
    const z = -n * 0.1;
    b.box(n * 0.66, 1.58, n * 0.5, x, 0.12, z, WHITE);
    b.box(n * 0.7, 0.14, n * 0.53, x, 1.7, z, accent);
    facadeWindows(b, 4, 1, n * 0.58, 0.34, 0.58, x, 0.25, z + n * 0.255, GLASS);
    b.box(0.28, 0.9, 0.055, x + 0.08, 0.16, z + n * 0.265, 0x725746);
    b.box(n * 0.72, 0.12, 0.48, x, 0.96, z + n * 0.02, accent);
    for (let i = 0; i < 6; i++) b.box(n * 0.11, 0.12, 0.5, x - n * 0.33 + i * n * 0.132, 0.96, z + n * 0.02, i % 2 ? WHITE : accent);
    // Upper shop floor and a small rooftop sign panel.
    b.box(n * 0.55, 0.62, n * 0.38, x, 1.82, z - 0.02, 0xf0e7d8);
    facadeWindows(b, 4, 1, n * 0.48, 0.27, 0.34, x, 1.96, z + n * 0.18, GLASS);
    if (k > 1) {
      b.box(n * 0.32, 1.05, n * 0.28, n * 0.31, 0.12, -n * 0.28, 0xd4d9d8);
      b.box(n * 0.34, 0.11, n * 0.3, n * 0.31, 1.17, -n * 0.28, accent);
      b.box(n * 0.18, 0.55, 0.05, n * 0.31, 0.24, -n * 0.13, GLASS);
    }
    if (k > 2) {
      b.box(n * 0.28, 1.15, n * 0.28, -n * 0.32, 0.12, n * 0.28, 0xf3d6c4);
      b.pyramid(n * 0.32, 0.22, -n * 0.32, 1.27, n * 0.28, accent);
      b.box(n * 0.12, 0.4, 0.07, -n * 0.32, 0.3, n * 0.43, DARK);
    }
    if (k > 3) {
      b.box(0.9, 0.42, 0.55, n * 0.27, 0.12, n * 0.34, accent);
      b.box(0.46, 0.35, 0.5, n * 0.27 + 0.52, 0.12, n * 0.34, GLASS);
      b.cyl(0.12, 0.12, 0.34, n * 0.27 + 0.52, 0.12, n * 0.34, DARK, 8);
    }
  },
  tech({ b, k, n, accent }) {
    // Glass-and-steel headquarters with a separate data-centre wing and rooftop hardware.
    const x = -n * 0.12, z = -n * 0.1, w = n * 0.38;
    b.box(w, 2.72, w, x, 0.12, z, GLASS);
    b.box(w + 0.12, 0.13, w + 0.12, x, 2.84, z, accent);
    facadeWindows(b, 4, 5, w * 0.82, 0.2, 0.28, x, 0.3, z + w / 2 + 0.03, 0x9ed4e6);
    for (let i = 0; i < 3; i++) b.box(0.055, 2.45, 0.08, x - w * 0.35 + i * w * 0.35, 0.22, z + w / 2 + 0.07, WHITE);
    b.box(w * 0.78, 0.08, w * 0.72, x, 2.96, z, DARK);
    b.cyl(0.055, 0.055, 0.9, x, 3.04, z, GREY, 6);
    b.sphere(0.12, x, 3.85, z, accent);
    if (k > 1) {
      b.box(n * 0.52, 0.95, n * 0.3, n * 0.1, 0.12, n * 0.22, WHITE);
      b.box(n * 0.54, 0.08, n * 0.32, n * 0.1, 1.08, n * 0.22, GLASS);
      for (let i = 0; i < 5; i++) b.box(0.18, 0.42, 0.055, n * 0.1 - n * 0.22 + i * 0.11, 0.32, n * 0.38, 0x5f7380);
    }
    if (k > 2) {
      b.box(n * 0.34, 1.55, n * 0.32, n * 0.32, 0.12, -n * 0.28, 0xdfe6ee);
      b.box(n * 0.36, 0.12, n * 0.34, n * 0.32, 1.7, -n * 0.28, accent);
      for (let i = 0; i < 4; i++) b.cyl(0.12, 0.12, 0.52, n * 0.32 - n * 0.12 + i * 0.08, 1.82, -n * 0.28, GREY, 8);
    }
    if (k > 3) {
      b.box(n * 0.28, 0.8, n * 0.22, -n * 0.34, 0.12, n * 0.3, DARK);
      solarArray(b, -n * 0.34, n * 0.3, 3, 1, 0.23, 0.98);
    }
  },
  semis({ b, k, n, accent }) {
    // Precision fab campus: broad cleanroom, air filtration, cooling stacks and service bay.
    b.box(n * 0.78, 1.2, n * 0.44, 0, 0.12, -n * 0.08, 0xe9eef2);
    b.box(n * 0.82, 0.12, n * 0.48, 0, 1.34, -n * 0.08, WHITE);
    facadeWindows(b, 5, 1, n * 0.68, 0.22, 0.62, 0, 0.28, n * 0.15, GLASS);
    for (let i = 0; i < 4; i++) {
      b.box(n * 0.14, 0.14, 0.46, -n * 0.3 + i * n * 0.2, 1.48, -n * 0.08, i % 2 ? GLASS : accent);
      b.cyl(0.16, 0.16, 0.42, -n * 0.27 + i * n * 0.18, 1.62, -n * 0.3, GREY, 10);
    }
    if (k > 1) {
      b.cyl(0.35, 0.35, 1.55, n * 0.31, 0.12, n * 0.28, GREY, 12);
      b.cyl(0.35, 0.35, 0.12, n * 0.31, 1.68, n * 0.28, accent, 12);
      b.box(n * 0.5, 0.1, 0.12, -n * 0.05, 0.56, -n * 0.1, DARK);
    }
    if (k > 2) {
      b.box(n * 0.32, 0.82, n * 0.28, -n * 0.3, 0.12, n * 0.3, WHITE);
      for (let i = 0; i < 3; i++) b.box(0.16, 0.52, 0.06, -n * 0.3 - 0.16 + i * 0.16, 0.25, n * 0.45, GLASS);
    }
    if (k > 3) {
      b.cyl(0.14, 0.2, 2.6, n * 0.4, 0.12, -n * 0.34, DARK);
      b.box(0.7, 0.36, 0.52, n * 0.3, 0.12, n * 0.34, accent);
      b.box(0.72, 0.12, 0.54, n * 0.3, 0.5, n * 0.34, WHITE);
    }
  },
  energy({ b, k, n, accent }) {
    // Industrial energy campus: storage tanks, pipe racks, separators and a flare stack.
    const tank = (x: number, z: number, radius: number, height: number) => {
      b.cyl(radius, radius, height, x, 0.12, z, WHITE, 16);
      b.cyl(radius + 0.015, radius + 0.015, 0.075, x, 0.12 + height * 0.72, z, accent, 16);
      b.sphere(radius, x, 0.12 + height, z, 0xe8ece4);
      b.cyl(radius * 0.22, radius * 0.22, 0.1, x, 0.12 + height * 1.13, z, GREY, 8);
    };
    tank(-n * 0.22, -n * 0.1, n * 0.17, 1.15);
    if (k > 1) tank(n * 0.15, -n * 0.22, n * 0.14, 0.95);
    b.box(n * 0.46, 0.12, 0.16, -n * 0.05, 0.52, n * 0.26, DARK);
    for (let i = 0; i < 4; i++) b.cyl(0.045, 0.045, 0.8, -n * 0.25 + i * n * 0.16, 0.12, n * 0.28, GREY, 6);
    b.box(n * 0.58, 0.08, 0.1, 0, 0.95, n * 0.28, accent);
    if (k > 2) {
      b.cyl(0.13, 0.18, 2.6, n * 0.36, 0.12, -n * 0.3, GREY, 10);
      b.sphere(0.16, n * 0.36, 2.75, -n * 0.3, 0xf29d38);
      b.cyl(0.12, 0.12, 1.25, -n * 0.38, 0.12, -n * 0.32, DARK, 8);
      b.cyl(0.12, 0.12, 0.1, -n * 0.38, 1.4, -n * 0.32, accent, 8);
    }
    if (k > 3) {
      b.box(n * 0.4, 0.68, n * 0.28, 0, 0.12, n * 0.36, 0xe1e4df);
      b.box(n * 0.42, 0.1, n * 0.3, 0, 0.82, n * 0.36, accent);
      for (let i = 0; i < 5; i++) b.box(0.08, 0.42, 0.04, -n * 0.16 + i * 0.08, 0.22, n * 0.51, GLASS);
    }
  },
  mining({ b, k, n, accent }) {
    // Open-pit mine with stepped benches, ore stockpiles, conveyor and crusher plant.
    b.cyl(n * 0.43, n * 0.46, 0.2, 0, 0.12, 0, 0xa98b6a, 14);
    b.cyl(n * 0.34, n * 0.38, 0.2, 0, 0.32, 0, 0x8d7357, 14);
    b.cyl(n * 0.24, n * 0.28, 0.2, 0, 0.52, 0, 0x6d5a45, 14);
    b.cyl(n * 0.13, n * 0.17, 0.18, 0, 0.72, 0, 0x4c4c45, 14);
    if (k > 1) {
      b.tilted(n * 0.72, 0.18, 0.3, n * 0.04, 1.1, n * 0.28, DARK, 0.3);
      b.box(0.16, 1.0, 0.16, -n * 0.28, 0.12, n * 0.3, GREY);
      b.box(0.16, 0.8, 0.16, n * 0.32, 0.12, n * 0.3, GREY);
      b.cone(0.52, 0.7, -n * 0.34, 0.12, n * 0.3, 0x7d7f86, 7);
    }
    if (k > 2) {
      b.box(0.9, 0.5, 0.7, n * 0.3, 0.12, -n * 0.28, accent);
      b.box(0.1, 1.4, 0.1, n * 0.3, 0.62, -n * 0.28, DARK);
      b.box(0.65, 0.18, 0.16, n * 0.3, 0.75, -n * 0.28, GREY);
      b.cyl(0.22, 0.22, 0.5, n * 0.28, 0.12, -n * 0.08, 0x8e8c84, 8);
    }
    if (k > 3) {
      b.box(n * 0.5, 0.08, 0.2, 0, 0.12, -n * 0.42, DARK);
      b.box(0.8, 0.4, 0.4, -n * 0.1, 0.2, -n * 0.42, accent);
      b.cyl(0.11, 0.11, 0.75, -n * 0.35, 0.12, -n * 0.36, GREY, 8);
    }
  },
  banking({ b, k, n, accent }) {
    // Classical financial headquarters with a deep portico, columns, steps and clock.
    b.box(n * 0.68, 1.58, n * 0.44, 0, 0.12, -n * 0.08, 0xf1ead8);
    b.box(n * 0.78, 0.16, n * 0.52, 0, 1.72, -n * 0.06, accent);
    for (let i = 0; i < 6; i++) {
      const x = -n * 0.3 + i * n * 0.12;
      b.cyl(0.11, 0.14, 1.58, x, 0.12, n * 0.18, WHITE, 10);
      b.cyl(0.17, 0.17, 0.09, x, 1.7, n * 0.18, 0xe4dccb, 10);
      b.cyl(0.17, 0.17, 0.09, x, 0.12, n * 0.18, 0xe4dccb, 10);
    }
    b.pyramid(n * 0.82, 0.56, 0, 1.9, -n * 0.08, 0xd8cdb0);
    b.box(n * 0.32, 0.06, 0.08, 0, 2.48, n * 0.13, accent);
    b.cyl(0.34, 0.34, 0.08, 0, 2.5, n * 0.17, GOLD, 14);
    b.box(n * 0.74, 0.12, 0.62, 0, 0.12, n * 0.32, 0xbdb39f);
    b.box(n * 0.62, 0.12, 0.48, 0, 0.24, n * 0.32, 0xd8cdb0);
    if (k > 1) {
      b.box(n * 0.3, 1.05, n * 0.26, n * 0.34, 0.12, -n * 0.3, 0xdbe3ea);
      facadeWindows(b, 3, 2, n * 0.24, 0.16, 0.23, n * 0.34, 0.28, -n * 0.16, GLASS);
    }
    if (k > 2) {
      b.box(n * 0.28, 0.96, n * 0.24, -n * 0.34, 0.12, -n * 0.32, 0xdbe3ea);
      b.box(n * 0.3, 0.1, n * 0.26, -n * 0.34, 1.12, -n * 0.32, accent);
    }
    if (k > 3) {
      b.box(0.7, 0.4, 0.4, n * 0.34, 0.12, n * 0.3, GREY);
      b.box(0.3, 0.3, 0.4, n * 0.34 + 0.5, 0.12, n * 0.3, DARK);
    }
  },
  health({ b, k, n, accent }) {
    // Hospital and research campus: clean wings, glazed labs, rooftop cross and access wing.
    b.box(n * 0.56, 1.45, n * 0.42, -n * 0.1, 0.12, -n * 0.1, WHITE);
    b.box(n * 0.58, 0.12, n * 0.44, -n * 0.1, 1.58, -n * 0.1, accent);
    facadeWindows(b, 4, 2, n * 0.48, 0.16, 0.28, -n * 0.1, 0.28, n * 0.12, GLASS);
    b.box(n * 0.08, 0.55, 0.08, -n * 0.1, 1.74, n * 0.12, 0xd8423f);
    b.box(0.55, 0.13, 0.08, -n * 0.1, 1.94, n * 0.12, 0xd8423f);
    if (k > 1) {
      b.box(n * 0.34, 1.1, n * 0.3, n * 0.3, 0.12, -n * 0.26, 0xe7f0f4);
      facadeWindows(b, 3, 2, n * 0.28, 0.13, 0.22, n * 0.3, 0.28, -n * 0.1, GLASS);
      b.sphere(n * 0.17, n * 0.3, 0.12, n * 0.22, GLASS);
    }
    if (k > 2) {
      b.box(n * 0.36, 0.92, n * 0.27, -n * 0.32, 0.12, n * 0.3, 0xe7f0f4);
      b.box(n * 0.4, 0.12, n * 0.3, -n * 0.32, 1.06, n * 0.3, 0x8ec8c4);
      b.cyl(0.18, 0.18, 1.3, n * 0.42, 0.12, -n * 0.3, GREY, 10);
    }
    if (k > 3) {
      b.box(n * 0.3, 0.72, n * 0.24, -n * 0.34, 0.12, -n * 0.3, WHITE);
      b.box(0.8, 0.12, 0.42, n * 0.28, 0.12, n * 0.38, 0xe7f0f4);
      b.box(0.26, 0.24, 0.06, n * 0.28, 0.24, n * 0.58, accent);
    }
  },
  consumer({ b, k, n, accent }) {
    // Consumer-goods maker: production hall, packaging silos and a dispatch dock.
    b.box(n * 0.7, 1.28, n * 0.46, -n * 0.08, 0.12, -n * 0.12, 0xe9d3b0);
    b.box(n * 0.74, 0.12, n * 0.5, -n * 0.08, 1.42, -n * 0.12, accent);
    facadeWindows(b, 5, 1, n * 0.62, 0.19, 0.48, -n * 0.08, 0.34, n * 0.12, GLASS);
    b.box(n * 0.16, 0.78, 0.08, -n * 0.08, 0.24, n * 0.245, DARK);
    // Tall package-shaped tanks make the product sector distinct from retail premises.
    b.cyl(n * 0.14, n * 0.14, 1.65, n * 0.3, 0.12, -n * 0.2, WHITE, 12);
    b.cyl(n * 0.14, n * 0.14, 0.1, n * 0.3, 1.72, -n * 0.2, accent, 12);
    b.cone(n * 0.14, 0.24, n * 0.3, 1.82, -n * 0.2, WHITE, 12);
    if (k > 1) {
      b.cyl(n * 0.12, n * 0.12, 1.35, n * 0.02, 0.12, n * 0.28, WHITE, 12);
      b.cyl(n * 0.13, n * 0.13, 0.09, n * 0.02, 1.42, n * 0.28, accent, 12);
      b.box(n * 0.38, 0.12, 0.16, n * 0.1, 0.72, n * 0.27, DARK);
    }
    if (k > 2) {
      b.box(n * 0.36, 0.84, n * 0.28, -n * 0.32, 0.12, n * 0.28, 0xf3d6c4);
      b.box(n * 0.4, 0.1, n * 0.3, -n * 0.32, 0.98, n * 0.28, accent);
      for (let i = 0; i < 3; i++) b.box(0.12, 0.34, 0.05, -n * 0.42 + i * 0.16, 0.24, n * 0.43, GLASS);
    }
    if (k > 3) {
      b.box(0.95, 0.48, 0.55, n * 0.25, 0.12, n * 0.36, accent);
      b.box(0.46, 0.38, 0.5, n * 0.25 + 0.58, 0.12, n * 0.36, GLASS);
      b.cyl(0.1, 0.1, 0.32, n * 0.25 + 0.58, 0.12, n * 0.36, DARK, 6);
    }
  },
  telecom({ b, k, n, accent }) {
    b.box(n * 0.4, 0.8, n * 0.3, -n * 0.18, 0.12, n * 0.1, 0xdde3ea);
    b.cone(0.55, 3.4, n * 0.1, 0.12, -n * 0.18, accent, 4);
    b.cone(0.18, 1.2, n * 0.1, 3.5, -n * 0.18, GREY, 4);
    if (k > 1) {
      b.sphere(0.32, -n * 0.3, 0.92, n * 0.1, WHITE);
      b.cyl(0.04, 0.04, 0.5, -n * 0.3, 0.92, n * 0.1, DARK, 5);
    }
    if (k > 2) b.box(n * 0.3, 0.7, n * 0.24, n * 0.28, 0.12, n * 0.28, 0xdde3ea);
    if (k > 3) b.cone(0.4, 2.4, -n * 0.32, 0.12, -n * 0.3, accent, 4);
  },
  utilities({ b, k, n, accent }) {
    const turbine = (x: number, z: number, h: number) => {
      b.cyl(0.07, 0.16, h, x, 0.12, z, WHITE, 8);
      b.sphere(0.14, x, h + 0.02, z, GREY);
      for (let i = 0; i < 3; i++) b.tilted(0.1, 1.3, 0.04, x, h + 0.7, z + 0.16, WHITE, (i * 2 * Math.PI) / 3 + 0.4, 0);
    };
    turbine(-n * 0.2, -n * 0.1, 2.4);
    b.box(n * 0.34, 0.7, n * 0.26, n * 0.2, 0.12, n * 0.2, 0xdfe6ee);
    if (k > 1) turbine(n * 0.24, -n * 0.26, 2.1);
    if (k > 2) for (let i = 0; i < 3; i++) b.tilted(n * 0.22, 0.05, n * 0.18, -n * 0.28 + i * n * 0.26, 0.5, n * 0.34, 0x2f5f9b, -0.5);
    if (k > 3) {
      turbine(-n * 0.36, -n * 0.34, 1.9);
      b.box(n * 0.2, 0.5, n * 0.16, n * 0.38, 0.12, -n * 0.04, accent);
    }
  },
  realestate({ b, k, n, accent }) {
    b.box(n * 0.4, 2.0, n * 0.34, -n * 0.18, 0.12, -n * 0.1, 0xefe4d2);
    b.box(n * 0.42, 0.12, n * 0.36, -n * 0.18, 2.12, -n * 0.1, accent);
    if (k > 1) {
      b.box(n * 0.3, 1.4, n * 0.3, n * 0.26, 0.12, n * 0.04, 0xe4ebf0);
      b.box(n * 0.32, 0.1, n * 0.32, n * 0.26, 1.52, n * 0.04, accent);
    }
    if (k > 2) b.box(n * 0.34, 0.9, n * 0.24, -n * 0.14, 0.12, n * 0.3, 0xf3d6c4);
    if (k > 3) b.box(n * 0.26, 1.7, n * 0.24, n * 0.3, 0.12, -n * 0.32, GLASS);
  },
  fund({ b, k, n, accent }) {
    b.cyl(n * 0.42, n * 0.44, 0.15, 0, 0.12, 0, 0xe9e4d6, 18);
    for (let i = 0; i < 8; i++) {
      const a = (i / 8) * Math.PI * 2;
      b.cyl(0.07, 0.07, 1.2, Math.cos(a) * n * 0.34, 0.27, Math.sin(a) * n * 0.34, WHITE, 6);
    }
    b.cyl(n * 0.4, n * 0.4, 0.1, 0, 1.47, 0, accent, 18);
    b.sphere(n * 0.22 + k * 0.03, 0, 1.52, 0, GLASS);
  },
  cash({ b, k, n, accent }) {
    b.box(n * 0.6, 1.0, n * 0.46, 0, 0.12, -n * 0.06, 0xcfc7b4);
    b.cyl(0.4, 0.4, 0.14, 0, 0.5, n * 0.18, GREY, 16);
    b.box(n * 0.64, 0.14, n * 0.5, 0, 1.12, -n * 0.06, accent);
    for (let i = 0; i < Math.min(k + 1, 5); i++) b.cyl(0.22, 0.22, 0.09, n * 0.32 + (i % 2) * 0.05, 0.12 + i * 0.09, n * 0.3, 0xe6b422, 12);
  },
  crypto({ b, k, n, accent }) {
    b.cyl(n * 0.3, n * 0.34, 0.2, 0, 0.12, 0, 0x2b2f44, 6);
    b.cyl(n * 0.14, n * 0.2, 1.6, 0, 0.32, 0, accent, 6);
    for (let i = 0; i < Math.min(k + 1, 4); i++) {
      const a = (i / 4) * Math.PI * 2 + 0.4;
      b.box(0.34, 0.34, 0.34, Math.cos(a) * n * 0.32, 1.0 + (i % 2) * 0.4, Math.sin(a) * n * 0.32, i % 2 ? 0x6ee7d8 : 0xf0a1ff, a);
    }
  },
};

type CompanyIdentity = "iberdrola" | "bbva" | "santander";

interface CompanyProfile {
  identity: CompanyIdentity;
  accent: number;
  minComponents: number;
}

function companyProfile(asset: Pick<WorldAsset, "ticker" | "name">): CompanyProfile | null {
  const name = asset.name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
  const ticker = (asset.ticker ?? "").toUpperCase().replace(/[^A-Z]/g, "");
  if (name.includes("IBERDROLA") || ticker === "IBE") {
    return { identity: "iberdrola", accent: 0x4b9d3f, minComponents: 7 };
  }
  if (name.includes("BBVA") || name.includes("BANCO BILBAO VIZCAYA") || ticker === "BBVA") {
    return { identity: "bbva", accent: 0x0874c9, minComponents: 6 };
  }
  if (name.includes("SANTANDER") || name.includes("BANCO SANTANDER") || (ticker === "SAN" && name.includes("BANCO"))) {
    return { identity: "santander", accent: 0xec0000, minComponents: 6 };
  }
  return null;
}

/** Company-specific corporate colours; other holdings receive a stable individual accent. */
export function accentFor(id: string, asset?: Pick<WorldAsset, "ticker" | "name">): number {
  const profile = asset ? companyProfile(asset) : null;
  if (profile) return profile.accent;
  const h = (hashString(id) % 360) / 360;
  return hex(new THREE.Color().setHSL(h, 0.55, 0.52));
}

function iberdrolaCampus({ b, n, accent }: Ctx) {
  // Iberdrola: a renewable-energy operating campus rather than a single windmill.
  const green = accent;
  const blue = 0x126a8b;
  // Main energy-control building and two production halls.
  b.box(n * 0.64, 1.25, n * 0.42, -n * 0.1, 0.12, -n * 0.12, 0xe8eee7);
  b.box(n * 0.68, 0.12, n * 0.46, -n * 0.1, 1.4, -n * 0.12, green);
  facadeWindows(b, 5, 1, n * 0.58, 0.2, 0.56, -n * 0.1, 0.32, n * 0.1, GLASS);
  b.box(n * 0.32, 1.0, n * 0.27, n * 0.32, 0.12, -n * 0.28, 0xdfe8e4);
  b.box(n * 0.34, 0.11, n * 0.29, n * 0.32, 1.14, -n * 0.28, blue);
  b.box(n * 0.28, 0.84, n * 0.24, -n * 0.35, 0.12, n * 0.29, 0xe6ece7);
  b.box(n * 0.3, 0.1, n * 0.26, -n * 0.35, 1.0, n * 0.29, green);
  // Transformer yard, switchgear and pipe/cable racks.
  for (let i = 0; i < 4; i++) {
    const x = -n * 0.32 + i * n * 0.2;
    b.box(0.52, 0.62, 0.48, x, 0.12, -n * 0.42, 0xb8c7c4);
    b.cyl(0.045, 0.045, 0.48, x - 0.12, 0.74, -n * 0.42, blue, 6);
    b.cyl(0.045, 0.045, 0.48, x + 0.12, 0.74, -n * 0.42, blue, 6);
    b.box(0.68, 0.08, 0.08, x, 1.25, -n * 0.42, green);
  }
  for (let i = 0; i < 5; i++) b.cyl(0.045, 0.045, 0.9, -n * 0.36 + i * n * 0.18, 0.12, n * 0.42, blue, 6);
  // Two wind turbines and a bank of photovoltaic panels.
  for (const [x, z, h] of [[n * 0.34, n * 0.28, 3.8], [-n * 0.38, -n * 0.34, 3.1]] as const) {
    b.cyl(0.07, 0.16, h, x, 0.12, z, WHITE, 8);
    b.sphere(0.15, x, h + 0.02, z, blue);
    for (let i = 0; i < 3; i++) b.tilted(0.1, 1.55, 0.045, x, h + 0.76, z + 0.17, green, (i * Math.PI * 2) / 3 + 0.4);
  }
  solarArray(b, -n * 0.28, n * 0.2, 4, 2, 0.42, 1.05, blue);
  b.cyl(0.48, 0.48, 1.3, n * 0.38, 0.12, -n * 0.04, 0xc8d2cc, 16);
  b.cyl(0.5, 0.5, 0.08, n * 0.38, 1.35, -n * 0.04, green, 16);
}

function bbvaFinancialCampus({ b, n, accent }: Ctx) {
  // BBVA: blue-glass financial mini-city, several towers around a shared podium.
  const cyan = 0x36b8e8;
  b.box(n * 0.92, 0.35, n * 0.72, 0, 0.12, 0, 0xcedde8);
  b.box(n * 0.94, 0.12, n * 0.74, 0, 0.48, 0, accent);
  const towers = [
    { x: -n * 0.25, z: -n * 0.16, h: 4.1, w: 0.25 },
    { x: n * 0.08, z: -n * 0.12, h: 5.4, w: 0.28 },
    { x: n * 0.31, z: n * 0.16, h: 3.6, w: 0.23 },
  ];
  for (const tower of towers) {
    const width = n * tower.w;
    b.box(width, tower.h, width * 0.82, tower.x, 0.6, tower.z, 0x8dc8e3);
    b.box(width + 0.12, 0.12, width * 0.9, tower.x, tower.h + 0.6, tower.z, accent);
    facadeWindows(b, 4, Math.max(3, Math.floor(tower.h / 0.8)), width * 0.82, 0.16, 0.28, tower.x, 0.82, tower.z + width * 0.42, 0xc9efff);
    b.box(width * 0.82, 0.08, width * 0.76, tower.x, tower.h + 0.76, tower.z, 0xd9edf5);
  }
  // Financial plaza, bridge-like connector and rooftop helipad.
  b.box(n * 0.48, 0.3, n * 0.22, -n * 0.05, 0.68, n * 0.25, 0xdce9ef);
  b.cyl(0.58, 0.58, 0.06, -n * 0.25, 0.98, -n * 0.16, cyan, 20);
  b.box(n * 0.18, 0.5, n * 0.14, n * 0.34, 0.6, -n * 0.32, 0xeff4f7);
}

function santanderFinancialCampus({ b, n, accent }: Ctx) {
  // Santander: a broad, traditional financial headquarters, long wings and a colonnade.
  const ivory = 0xf0e8d8;
  b.box(n * 0.88, 1.75, n * 0.42, 0, 0.12, -n * 0.08, ivory);
  b.box(n * 0.94, 0.16, n * 0.48, 0, 1.9, -n * 0.08, accent);
  b.pyramid(n * 0.96, 0.48, 0, 2.05, -n * 0.08, 0x80766a);
  // Classical portico spans the entire central facade.
  for (let i = 0; i < 8; i++) {
    const x = -n * 0.36 + i * n * 0.103;
    b.cyl(0.105, 0.14, 1.68, x, 0.12, n * 0.15, 0xfaf5e9, 12);
    b.cyl(0.17, 0.17, 0.09, x, 1.78, n * 0.15, 0xd8cbb4, 12);
    b.cyl(0.17, 0.17, 0.09, x, 0.12, n * 0.15, 0xd8cbb4, 12);
  }
  b.box(n * 0.98, 0.16, 0.26, 0, 1.92, n * 0.15, 0xfaf5e9);
  // Long side wings keep the complex wide and low instead of a single tower.
  b.box(n * 0.26, 1.24, n * 0.7, -n * 0.36, 0.12, -n * 0.27, ivory);
  b.box(n * 0.26, 1.24, n * 0.7, n * 0.36, 0.12, -n * 0.27, ivory);
  b.box(n * 0.28, 0.12, n * 0.72, -n * 0.36, 1.38, -n * 0.27, accent);
  b.box(n * 0.28, 0.12, n * 0.72, n * 0.36, 1.38, -n * 0.27, accent);
  facadeWindows(b, 7, 1, n * 0.78, 0.32, 0.42, 0, 0.54, n * 0.205, GLASS);
  b.box(n * 0.84, 0.12, n * 0.22, 0, 0.12, n * 0.42, 0xc8bba4);
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
  else RECIPES[asset.archetype](ctx);

  // A small roadside pylon anchors the plot in the town's street-level view.
  const sx = nominal * 0.5;
  const sz = nominal * 0.5;
  b.cyl(0.045, 0.045, 1.05, sx, 0.12, sz, DARK, 5);
  b.box(0.82, 0.42, 0.09, sx, 0.84, sz, accent);
  b.box(0.68, 0.08, 0.1, sx, 1.07, sz, WHITE);

  // Unknown valuation: a hazard-yellow diamond on a pole. Never a smaller, quieter site.
  if (unknown) {
    b.cyl(0.03, 0.03, 1.1, -nominal * 0.5, 0.12, sz, DARK, 5);
    b.box(0.4, 0.4, 0.06, -nominal * 0.5, 1.0, sz, 0xf2c230, Math.PI / 4);
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
  canvasCtx.fillStyle = "#" + new THREE.Color(accent).getHexString();
  canvasCtx.beginPath();
  canvasCtx.roundRect(4, 4, 504, 136, 22);
  canvasCtx.fill();
  canvasCtx.fillStyle = "#172638";
  canvasCtx.beginPath();
  canvasCtx.roundRect(12, 12, 488, 120, 17);
  canvasCtx.fill();
  const ticker = (asset.ticker?.trim() || asset.name.split(/[^A-Za-z0-9]+/).filter(Boolean).slice(0, 2).map((x) => x[0]).join("") || "•").toUpperCase().slice(0, 12);
  canvasCtx.fillStyle = "#ffffff";
  canvasCtx.textBaseline = "middle";
  let signFontSize = 62;
  canvasCtx.font = "800 " + signFontSize + "px system-ui, sans-serif";
  while (signFontSize > 28 && canvasCtx.measureText(ticker).width > 440) {
    signFontSize -= 2;
    canvasCtx.font = "800 " + signFontSize + "px system-ui, sans-serif";
  }
  canvasCtx.fillText(ticker, 30, 68, 440);
  canvasCtx.fillStyle = "#c7d3e1";
  canvasCtx.font = "600 22px system-ui, sans-serif";
  canvasCtx.fillText(asset.name, 30, 124, 440);
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  const brandMaterial = new THREE.MeshBasicMaterial({ map: texture, toneMapped: false, side: THREE.DoubleSide });
  const brandPlate = new THREE.Mesh(new THREE.PlaneGeometry(1.72, 0.55), brandMaterial);
  brandPlate.position.set(0, Math.max(1.05, Math.min(b.top * 0.72, 2.2)), nominal * 0.27);
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
