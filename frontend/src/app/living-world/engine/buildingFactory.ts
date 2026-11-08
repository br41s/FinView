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
export const NOMINAL: Record<Tier, number> = { outpost: 3.4, small: 4.4, campus: 5.4, major: 6.8 };

export interface Site {
  group: THREE.Group;
  mesh: THREE.Mesh;
  material: THREE.MeshLambertMaterial;
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

/** A paved plot every site stands on, so a building reads as a lot and not as a prop. */
function plot(c: Ctx) {
  const s = c.n * 1.12;
  c.b.box(s, 0.12, s, 0, 0, 0, GROUND_PAD);
}

const RECIPES: Record<Archetype, (c: Ctx) => void> = {
  retail({ b, k, n, accent }) {
    b.box(n * 0.62, 1.4, n * 0.46, -n * 0.08, 0.12, -n * 0.1, WHITE);
    b.box(n * 0.66, 0.16, n * 0.5, -n * 0.08, 1.52, -n * 0.1, accent);
    for (let i = 0; i < 4; i++) {
      b.box(n * 0.15, 0.12, 0.55, -n * 0.34 + i * n * 0.17, 1.0, n * 0.17, i % 2 ? WHITE : accent);
    }
    if (k > 1) {
      b.box(n * 0.38, 1.0, n * 0.3, n * 0.27, 0.12, -n * 0.3, GREY);
      b.box(n * 0.24, 0.5, 0.1, n * 0.27, 0.12, -n * 0.14, DARK);
    }
    if (k > 2) {
      b.box(n * 0.28, 1.1, n * 0.26, -n * 0.32, 0.12, n * 0.26, 0xf3d6c4);
      b.box(n * 0.3, 0.12, n * 0.28, -n * 0.32, 1.22, n * 0.26, accent);
    }
    if (k > 3) {
      b.box(0.9, 0.5, 0.5, n * 0.3, 0.12, n * 0.3, accent);
      b.box(0.4, 0.4, 0.5, n * 0.3 + 0.65, 0.12, n * 0.3, GLASS);
    }
  },
  tech({ b, k, n, accent }) {
    b.box(n * 0.34, 2.6, n * 0.34, -n * 0.12, 0.12, -n * 0.1, GLASS);
    b.box(n * 0.36, 0.14, n * 0.36, -n * 0.12, 2.72, -n * 0.1, accent);
    if (k > 1) {
      b.box(n * 0.5, 0.9, n * 0.28, n * 0.1, 0.12, n * 0.22, WHITE);
      b.box(n * 0.5, 0.1, n * 0.3, n * 0.1, 1.02, n * 0.22, GLASS);
    }
    if (k > 2) {
      b.box(n * 0.3, 1.6, n * 0.3, n * 0.3, 0.12, -n * 0.28, 0xdfe6ee);
      b.cyl(0.35, 0.05, 0.25, n * 0.3, 1.72, -n * 0.28, GREY);
    }
    if (k > 3) {
      b.box(n * 0.28, 0.8, n * 0.22, -n * 0.34, 0.12, n * 0.3, DARK);
      b.cyl(0.18, 0.18, 0.1, -n * 0.34, 0.92, n * 0.3, accent);
    }
  },
  semis({ b, k, n, accent }) {
    b.box(n * 0.78, 1.0, n * 0.4, 0, 0.12, -n * 0.08, 0xe9eef2);
    for (let i = 0; i < 4; i++) b.box(n * 0.16, 0.12, n * 0.42, -n * 0.3 + i * n * 0.2, 1.12, -n * 0.08, i % 2 ? GLASS : accent);
    if (k > 1) {
      b.cyl(0.35, 0.35, 1.5, n * 0.3, 0.12, n * 0.28, GREY);
      b.cyl(0.35, 0.35, 0.12, n * 0.3, 1.62, n * 0.28, accent);
    }
    if (k > 2) b.box(n * 0.28, 0.8, n * 0.24, -n * 0.3, 0.12, n * 0.3, WHITE);
    if (k > 3) b.cyl(0.14, 0.2, 2.6, n * 0.4, 0.12, -n * 0.34, DARK);
  },
  energy({ b, k, n, accent }) {
    b.cyl(n * 0.17, n * 0.17, 1.1, -n * 0.22, 0.12, -n * 0.1, WHITE, 14);
    b.cyl(n * 0.17, n * 0.17, 0.08, -n * 0.22, 1.22, -n * 0.1, accent, 14);
    if (k > 1) {
      b.cyl(n * 0.15, n * 0.15, 0.9, n * 0.12, 0.12, -n * 0.18, WHITE, 14);
      b.box(n * 0.5, 0.1, 0.12, -n * 0.05, 0.5, -n * 0.1, DARK);
    }
    if (k > 2) {
      b.cyl(0.12, 0.18, 2.4, n * 0.34, 0.12, -n * 0.3, GREY);
      b.sphere(0.14, n * 0.34, 2.5, -n * 0.3, 0xf29d38);
    }
    if (k > 3) {
      b.box(n * 0.4, 0.15, n * 0.26, 0, 0.9, n * 0.3, accent);
      b.cyl(0.07, 0.07, 0.8, -n * 0.14, 0.12, n * 0.3, DARK, 6);
      b.cyl(0.07, 0.07, 0.8, n * 0.14, 0.12, n * 0.3, DARK, 6);
    }
    if (k === 1) {
      b.box(n * 0.4, 0.15, n * 0.24, 0, 0.9, n * 0.3, accent);
      b.cyl(0.06, 0.06, 0.78, -n * 0.14, 0.12, n * 0.3, DARK, 6);
    }
  },
  mining({ b, k, n, accent }) {
    b.cyl(n * 0.4, n * 0.44, 0.2, 0, 0.12, 0, 0xa98b6a, 14);
    b.cyl(n * 0.3, n * 0.34, 0.2, 0, 0.32, 0, 0x8d7357, 14);
    b.cyl(n * 0.2, n * 0.24, 0.2, 0, 0.52, 0, 0x6d5a45, 14);
    if (k > 1) {
      b.tilted(n * 0.7, 0.18, 0.3, n * 0.05, 1.0, n * 0.26, DARK, 0.28);
      b.cone(0.5, 0.7, -n * 0.34, 0.12, n * 0.3, 0x7d7f86);
    }
    if (k > 2) {
      b.box(0.9, 0.5, 0.7, n * 0.3, 0.12, -n * 0.28, accent);
      b.box(0.1, 1.4, 0.1, n * 0.3, 0.62, -n * 0.28, DARK);
    }
    if (k > 3) {
      b.box(n * 0.5, 0.08, 0.2, 0, 0.12, -n * 0.42, DARK);
      b.box(0.8, 0.4, 0.4, -n * 0.1, 0.2, -n * 0.42, accent);
    }
  },
  banking({ b, k, n, accent }) {
    b.box(n * 0.62, 1.5, n * 0.42, 0, 0.12, -n * 0.08, 0xf1ead8);
    for (let i = 0; i < 5; i++) b.cyl(0.1, 0.1, 1.5, -n * 0.24 + i * n * 0.12, 0.12, n * 0.17, WHITE, 8);
    b.box(n * 0.68, 0.18, n * 0.48, 0, 1.62, -n * 0.06, accent);
    b.cone(n * 0.34, 0.5, 0, 1.8, -n * 0.08, 0xd8cdb0, 4);
    if (k > 1) b.box(n * 0.3, 1.0, n * 0.26, n * 0.34, 0.12, -n * 0.3, 0xdbe3ea);
    if (k > 2) {
      b.box(n * 0.28, 0.9, n * 0.24, -n * 0.34, 0.12, -n * 0.32, 0xdbe3ea);
      b.box(n * 0.3, 0.1, n * 0.26, -n * 0.34, 1.02, -n * 0.32, accent);
    }
    if (k > 3) {
      b.box(0.7, 0.4, 0.4, n * 0.34, 0.12, n * 0.3, GREY);
      b.box(0.3, 0.3, 0.4, n * 0.34 + 0.5, 0.12, n * 0.3, DARK);
    }
  },
  health({ b, k, n, accent }) {
    b.box(n * 0.5, 1.2, n * 0.4, -n * 0.1, 0.12, -n * 0.1, WHITE);
    b.box(n * 0.06, 0.5, 0.06, -n * 0.1, 1.36, n * 0.1, 0xd8423f);
    b.box(0.5, 0.14, 0.14, -n * 0.1, 1.54, n * 0.1, 0xd8423f);
    b.box(n * 0.52, 0.14, n * 0.42, -n * 0.1, 1.32, -n * 0.1, accent);
    if (k > 1) b.sphere(n * 0.17, n * 0.3, 0.12, n * 0.22, GLASS);
    if (k > 2) {
      b.box(n * 0.36, 0.9, n * 0.26, n * 0.28, 0.12, -n * 0.3, 0xe7f0f4);
      b.cyl(0.18, 0.18, 1.3, n * 0.4, 0.12, -n * 0.3, GREY);
    }
    if (k > 3) b.box(n * 0.3, 0.7, n * 0.22, -n * 0.34, 0.12, n * 0.3, 0xe7f0f4);
  },
  consumer({ b, k, n, accent }) {
    b.box(n * 0.56, 1.0, n * 0.4, -n * 0.1, 0.12, -n * 0.14, 0xe9d3b0);
    for (let i = 0; i < 3; i++) b.tilted(n * 0.18, 0.1, n * 0.42, -n * 0.28 + i * n * 0.18, 1.3, -n * 0.14, ROOF_RED, 0.5);
    b.cyl(0.38, 0.38, 1.8, n * 0.3, 0.12, -n * 0.2, WHITE, 12);
    b.cone(0.38, 0.3, n * 0.3, 1.92, -n * 0.2, accent, 12);
    if (k > 1) {
      b.cyl(0.38, 0.38, 1.5, n * 0.3, 0.12, n * 0.08, WHITE, 12);
      b.cone(0.38, 0.3, n * 0.3, 1.62, n * 0.08, accent, 12);
    }
    if (k > 2) {
      b.box(n * 0.36, 0.8, n * 0.26, -n * 0.3, 0.12, n * 0.28, 0xf3d6c4);
      b.box(n * 0.4, 0.1, n * 0.3, -n * 0.3, 0.92, n * 0.28, accent);
    }
    if (k > 3) {
      b.box(0.9, 0.5, 0.5, n * 0.1, 0.12, n * 0.34, accent);
      b.cyl(0.1, 0.1, 0.3, -n * 0.05, 0.12, n * 0.34, GLASS, 6);
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

/** Company-specific accent so neighbours of one archetype are tellable apart. */
export function accentFor(id: string): number {
  const h = (hashString(id) % 360) / 360;
  return hex(new THREE.Color().setHSL(h, 0.55, 0.52));
}

export function createSite(asset: WorldAsset, tier: Tier, unknown: boolean): Site {
  const nominal = NOMINAL[tier];
  const accent = accentFor(asset.id);
  const b = new Builder();
  const ctx: Ctx = { b, k: componentCount(tier), n: nominal, accent, rnd: seeded(hashString(asset.id)) };
  plot(ctx);
  RECIPES[asset.archetype](ctx);

  // The company sign: a post and a board in the accent colour.
  const sx = nominal * 0.5;
  const sz = nominal * 0.5;
  b.cyl(0.04, 0.04, 0.9, sx, 0.12, sz, DARK, 5);
  b.box(0.62, 0.34, 0.07, sx, 0.72, sz, accent);

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
  const group = new THREE.Group();
  group.add(mesh);
  return { group, mesh, material, nominal, top: b.top, sign: new THREE.Vector3(sx, 0.9, sz) };
}

export function disposeSite(s: Site) {
  s.mesh.geometry.dispose();
  s.material.dispose();
}
