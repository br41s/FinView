import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { hashString } from "../model/rng";
import { type Tier } from "../model/scale";
import { placeParts } from "../model/siteLayout";
import { FACADE_ROWS, accentColour, towerSpec, type TowerSpec } from "../model/towerSpec";
import type { WorldAsset } from "../model/types";
import { buildMain, DECK_TOP } from "./mains";
import { createFacadeMaterial } from "./materials";
import { buildPart } from "./parts";
import { DARK, DECK, SITE_COLS, WHITE } from "./towers";

/**
 * Portfolio company buildings (spec §9.3).
 *
 * Visual rule: holdings are the landmarks of the city. Each one is a UNIQUE complex: the spec
 * (`model/towerSpec.ts`, from archetype + ISIN + tier) picks the silhouette of its main structure
 * (`engine/mains.ts`: twisting tower, gherkin with a diagrid, setbacks, helipad cylinder, twin slabs
 * with a sky-bridge, lattice mast, dome, arena, power-plant stacks...) and the extra structures that
 * grow with the tier (`engine/parts.ts`, placed by `model/siteLayout.ts`). It stands on a
 * colour-trimmed plaza and merges everything into ONE mesh with vertex colours, so ~100 companies
 * stay ~100 draw calls whatever the architecture.
 */

/** Footprint a tier is modelled at; the engine scales the group to the real footprint. */
export const NOMINAL: Record<Tier, number> = { outpost: 3.6, small: 5.0, campus: 7.4, major: 10.4 };

export interface Site {
  group: THREE.Group;
  mesh: THREE.Mesh;
  material: THREE.MeshStandardMaterial;
  brandPlate: THREE.Mesh;
  brandMaterial: THREE.MeshBasicMaterial;
  nominal: number;
  /** Height of the tallest part at nominal scale, for markers above the roof. */
  top: number;
  /** Where the company sign stands (local, nominal scale). */
  sign: THREE.Vector3;
  /** Top of the roof lantern (local, nominal scale): labels and markers float above it. */
  signTop: number;
}

/** Window colours of the landmark recipes: parts painted with these get the glass treatment. */
const GLASS_HEXES = new Set([0x5ab9ea, 0x8be0ff, 0xd4f4ff]);

/** `aArc` of a part that has no arc length of its own: the facade shader then picks the axis from the facing. */
export const ARC_NONE = -1e4;

export class Builder {
  private parts: THREE.BufferGeometry[] = [];
  top = 0;
  private color = new THREE.Color();
  /** 1 = curtain-wall glass, 2 = accent (roofs), 3 = glass with a diagrid; window colours are glass anyway. */
  kind: 0 | 1 | 2 | 3 = 0;

  private push(g: THREE.BufferGeometry, x: number, y: number, z: number, hex: number, ry = 0, rz = 0) {
    if (ry) g.rotateY(ry);
    if (rz) g.rotateZ(rz);
    g.translate(x, y, z);
    g.deleteAttribute("uv");
    this.color.set(hex);
    const n = g.getAttribute("position").count;
    if (!g.getAttribute("color")) {
      const c = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) {
        c[i * 3] = this.color.r;
        c[i * 3 + 1] = this.color.g;
        c[i * 3 + 2] = this.color.b;
      }
      g.setAttribute("color", new THREE.BufferAttribute(c, 3));
    }
    if (!g.getAttribute("aArc")) g.setAttribute("aArc", new THREE.BufferAttribute(new Float32Array(n).fill(ARC_NONE), 1));
    g.setAttribute("aKind", new THREE.BufferAttribute(new Float32Array(n).fill(this.kind || (GLASS_HEXES.has(hex) ? 1 : 0)), 1));
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
  /** A gable roof: eaves `w` x `d` at `y`, ridge `h` above along x. Faces are oriented away from its centre. */
  gable(w: number, h: number, d: number, x: number, y: number, z: number, hex: number) {
    const hw = w / 2;
    const hd = d / 2;
    const P = {
      a: [-hw, 0, -hd], b: [hw, 0, -hd], c: [hw, 0, hd], e: [-hw, 0, hd], r1: [-hw, h, 0], r2: [hw, h, 0],
    } as const;
    const tris: Array<[readonly number[], readonly number[], readonly number[]]> = [
      [P.a, P.b, P.r2], [P.a, P.r2, P.r1], // back slope
      [P.e, P.r1, P.r2], [P.e, P.r2, P.c], // front slope
      [P.a, P.r1, P.e], // left end
      [P.b, P.c, P.r2], // right end
      [P.a, P.e, P.c], [P.a, P.c, P.b], // underside
    ];
    const pos: number[] = [];
    const centre = new THREE.Vector3(0, h / 3, 0);
    for (const [p, q, r] of tris) {
      const A = new THREE.Vector3(...p);
      const B = new THREE.Vector3(...q);
      const C = new THREE.Vector3(...r);
      const n = B.clone().sub(A).cross(C.clone().sub(A));
      const out = A.clone().add(B).add(C).divideScalar(3).sub(centre);
      const t = n.dot(out) < 0 ? [A, C, B] : [A, B, C];
      for (const v of t) pos.push(v.x, v.y, v.z);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.computeVertexNormals();
    this.push(g, x, y, z, hex);
  }
  /** A low-poly rounded blob (smooth-shaded icosphere) centred at `y`. */
  ico(r: number, x: number, y: number, z: number, hex: number, detail = 1) {
    this.push(new THREE.IcosahedronGeometry(r, detail), x, y, z, hex);
  }
  sphere(r: number, x: number, y: number, z: number, hex: number) {
    this.push(new THREE.SphereGeometry(r, 10, 8), x, y + r, z, hex);
  }
  /** A box tilted around Z, for conveyors, panels and blades. `y` is its centre. */
  tilted(w: number, h: number, d: number, x: number, y: number, z: number, hex: number, rz: number, ry = 0) {
    this.push(new THREE.BoxGeometry(w, h, d), x, y, z, hex, ry, rz);
  }

  /** Adds a geometry made elsewhere (position + normal, optionally colour and `aArc`), already in place. */
  custom(g: THREE.BufferGeometry, hex: number) {
    this.push(g, 0, 0, 0, hex);
  }

  /** Triangles queued so far (indexed and non-indexed parts). */
  triangles(): number {
    return this.parts.reduce((t, g) => t + (g.index ? g.index.count : g.getAttribute("position").count) / 3, 0);
  }

  build(): THREE.BufferGeometry {
    // Polyhedra are non-indexed, boxes and cylinders are indexed; the merge wants all or none.
    const mixed = this.parts.some((g) => !g.index) && this.parts.some((g) => g.index);
    const parts = mixed ? this.parts.map((g) => (g.index ? g.toNonIndexed() : g)) : this.parts;
    const merged = mergeGeometries(parts, false);
    this.parts.forEach((g) => g.dispose());
    this.parts = [];
    merged.computeBoundingSphere();
    return merged;
  }
}

const hex = (c: THREE.Color) => c.getHex();

type CompanyProfile = { accent: number };

/** Corporate colours of a few well-known issuers; everyone else draws from the archetype palette. */
function companyProfile(asset: Pick<WorldAsset, "ticker" | "name">): CompanyProfile | null {
  const name = asset.name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toUpperCase();
  const ticker = (asset.ticker ?? "").toUpperCase().replace(/[^A-Z]/g, "");
  if (name.includes("IBERDROLA") || ticker === "IBE") return { accent: 0x3fa834 };
  if (name.includes("BBVA") || name.includes("BANCO BILBAO VIZCAYA") || ticker === "BBVA") return { accent: 0x0a78d6 };
  if (name.includes("SANTANDER") || name.includes("BANCO SANTANDER") || (ticker === "SAN" && name.includes("BANCO"))) return { accent: 0xec0000 };
  if (name.includes("INDITEX") || name.includes("INDUSTRIA DE DISENO TEXTIL") || ticker === "ITX") return { accent: 0x1e64d8 };
  if (name.includes("TELEFONICA") || ticker === "TEF") return { accent: 0x0066ff };
  if (name.includes("REPSOL") || ticker === "REP") return { accent: 0xff6b00 };
  return null;
}

/** Brand colour for the few known issuers, else the archetype palette nudged by the id (stable per ISIN). */
export function accentFor(id: string, asset?: Pick<WorldAsset, "ticker" | "name"> & { archetype?: WorldAsset["archetype"] }): number {
  const profile = asset ? companyProfile(asset) : null;
  if (profile) return profile.accent;
  if (asset?.archetype) return accentColour(asset.archetype, id);
  const h = (hashString(id) % 360) / 360;
  return hex(new THREE.Color().setHSL(h, 0.76, 0.48));
}

/** Specs are built from the id and the tier only; the weight never reaches them. */
export function specFor(asset: Pick<WorldAsset, "id" | "archetype" | "ticker" | "name">, tier: Tier): TowerSpec {
  const profile = companyProfile(asset);
  return towerSpec(asset.archetype, asset.id, tier, profile?.accent);
}

/**
 * The plot every complex stands on: foundation, accent kerb, a travertine deck with an inlaid
 * border, an entrance path in the accent colour, hedges, trees and lamps at the corners.
 */
function plot(b: Builder, n: number, accent: number) {
  const s = n * 1.18;
  b.kind = 0;
  b.box(s + 0.2, 0.28, s + 0.2, 0, -0.2, 0, DARK);
  b.kind = 2;
  b.box(s + 0.1, 0.1, s + 0.1, 0, 0.05, 0, accent);
  b.kind = 0;
  b.box(s, 0.14, s, 0, 0.07, 0, DECK);
  b.box(s * 0.94, DECK_TOP - 0.14, s * 0.94, 0, 0.14, 0, 0xf6f0e2);
  // Inlaid border and the entrance path from the street to the foot of the main structure.
  b.box(s * 0.9, 0.012, 0.05, 0, DECK_TOP, s * 0.43, 0xd8d0bc);
  b.box(s * 0.9, 0.012, 0.05, 0, DECK_TOP, -s * 0.43, 0xd8d0bc);
  b.kind = 2;
  b.box(0.36, 0.02, s * 0.5, 0, DECK_TOP, s * 0.27, accent);
  b.kind = 0;
  // Hedges and trees at the corners, lamps by the entrance.
  for (const sx of [-1, 1]) {
    for (const sz of [-1, 1]) {
      const px = sx * s * 0.44;
      const pz = sz * s * 0.44;
      b.box(0.5, 0.2, 0.5, px, DECK_TOP, pz, 0xffffff);
      b.box(0.42, 0.14, 0.42, px, DECK_TOP + 0.2, pz, 0x399c58);
      b.ico(0.24, px, DECK_TOP + 0.52, pz, sz < 0 ? 0x2f9a58 : 0x56b56a, 0);
    }
    b.cyl(0.03, 0.03, 0.5, sx * 0.55, DECK_TOP, s * 0.46, DARK, 5);
    b.ico(0.07, sx * 0.55, DECK_TOP + 0.54, s * 0.46, 0xfff1b8, 0);
  }
}

/** The geometry of a holding's complex, built from its spec. Pure Three.js, no DOM: tests build it too. */
export function composeSite(spec: TowerSpec, n: number, unknown: boolean): { geometry: THREE.BufferGeometry; top: number; triangles: number } {
  const b = new Builder();
  plot(b, n, spec.accent);
  const main = buildMain({ b, n, spec });
  const ctx = { b, n, spec, mainTop: main.top };
  for (const { part, slot } of placeParts(spec)) {
    buildPart(part.kind, ctx, slot.x * n, slot.z * n, slot.w * n, slot.d * n, part.variant);
  }

  // Roadside corporate totem anchoring the plot at street level.
  const sx = n * 0.5;
  const sz = n * 0.5;
  b.kind = 0;
  b.cyl(0.05, 0.05, 1.1, sx, DECK_TOP, sz, DARK, 6);
  b.kind = 2;
  b.box(0.86, 0.46, 0.1, sx, 0.9, sz, spec.accent);
  b.kind = 0;
  b.box(0.72, 0.09, 0.11, sx, 1.15, sz, WHITE);
  // The sign wall the brand plate hangs on, in front of the entrance.
  b.box(2.0, 0.78, 0.12, 0, DECK_TOP, n * 0.5, DARK);
  b.kind = 2;
  b.box(2.06, 0.06, 0.14, 0, DECK_TOP + 0.78, n * 0.5, spec.accent);
  b.kind = 0;

  // Unknown valuation: a hazard-yellow diamond on a tall pole. Never a smaller, quieter site.
  if (unknown) {
    b.cyl(0.04, 0.04, 2.4, -n * 0.5, DECK_TOP, sz, DARK, 5);
    b.box(0.6, 0.6, 0.08, -n * 0.5, 2.25, sz, 0xf2c230, Math.PI / 4);
  }
  const triangles = b.triangles();
  const top = b.top;
  return { geometry: b.build(), top, triangles };
}

const SIGN_W = 512;
const SIGN_H = 164;

/** Initials for the emblem: «Iberdrola» → «IB», «Banco Santander» → «BS». */
function initials(name: string): string {
  const words = name.split(/[^A-Za-z0-9ÁÉÍÓÚÑáéíóúñ]+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return (words[0] ?? "•").slice(0, 2).toUpperCase();
}

/**
 * The company's sign: a generated emblem (its colour, its initials, one of four shapes picked
 * from its ISIN) and its ticker and name. An emblem, not the real logo: FinView has no
 * licensed source of logos, and a guessed one would be someone else's mark.
 */
function drawSign(asset: WorldAsset, accent: string): HTMLCanvasElement {
  const canvas = document.createElement("canvas");
  canvas.width = SIGN_W;
  canvas.height = SIGN_H;
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = accent;
  ctx.beginPath();
  ctx.roundRect(4, 4, SIGN_W - 8, SIGN_H - 8, 22);
  ctx.fill();
  // A lightbox: a pale panel lit from behind reads in sunlight and glows (bloom) at night,
  // where a dark plate with white letters disappeared.
  ctx.fillStyle = "#f7f9fc";
  ctx.beginPath();
  ctx.roundRect(12, 12, SIGN_W - 24, SIGN_H - 24, 17);
  ctx.fill();

  // Emblem.
  const cx = 86;
  const cy = SIGN_H / 2;
  const r = 56;
  const shape = hashString(asset.id) % 4;
  ctx.fillStyle = accent;
  ctx.strokeStyle = "#ffffff";
  ctx.lineWidth = 6;
  ctx.beginPath();
  if (shape === 0) ctx.arc(cx, cy, r, 0, Math.PI * 2);
  else if (shape === 1) ctx.roundRect(cx - r, cy - r, r * 2, r * 2, 18);
  else {
    const sides = shape === 2 ? 6 : 4;
    const turn = shape === 2 ? Math.PI / 6 : 0;
    for (let i = 0; i < sides; i++) {
      const a = turn + (i / sides) * Math.PI * 2;
      const x = cx + Math.cos(a) * r * 1.08;
      const y = cy + Math.sin(a) * r * 1.08;
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    }
    ctx.closePath();
  }
  ctx.fill();
  ctx.stroke();
  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = "900 46px system-ui, sans-serif";
  ctx.fillText(initials(asset.name), cx, cy + 2, r * 1.6);

  // Ticker and name.
  ctx.textAlign = "left";
  ctx.fillStyle = "#0f172a";
  const ticker = (asset.ticker?.trim() || initials(asset.name)).toUpperCase().slice(0, 12);
  let size = 58;
  ctx.font = `800 ${size}px system-ui, sans-serif`;
  while (size > 26 && ctx.measureText(ticker).width > 330) {
    size -= 2;
    ctx.font = `800 ${size}px system-ui, sans-serif`;
  }
  ctx.fillText(ticker, 166, 64, 330);
  ctx.fillStyle = "#475569";
  ctx.font = "600 24px system-ui, sans-serif";
  ctx.fillText(asset.name, 166, 120, 330);
  return canvas;
}

/**
 * Where the sign is shown, as one geometry (one draw call per building): a plate over the
 * entrance and a four-sided lantern on the roof, readable from any side of the town.
 */
// Both grow with the building: a fixed size vanished on the tallest holdings.
const lanternWidth = (nominal: number) => Math.min(4.4, Math.max(1.6, nominal * 0.42));
const plateWidth = (nominal: number) => Math.min(3.4, Math.max(1.76, nominal * 0.34));
const lanternTop = (nominal: number, top: number) => top + 0.08 + lanternWidth(nominal) * (SIGN_H / SIGN_W);

function signGeometry(nominal: number, top: number): THREE.BufferGeometry {
  const ratio = SIGN_H / SIGN_W;
  const pw = plateWidth(nominal);
  const plate = new THREE.PlaneGeometry(pw, pw * ratio);
  plate.translate(0, DECK_TOP + 0.12 + (pw * ratio) / 2, nominal * 0.5 + 0.075);
  const w = lanternWidth(nominal);
  const h = w * ratio;
  const faces: THREE.BufferGeometry[] = [plate];
  for (let k = 0; k < 4; k++) {
    const face = new THREE.PlaneGeometry(w, h);
    face.translate(0, 0, w / 2);
    face.rotateY((k * Math.PI) / 2);
    face.translate(0, top + 0.08 + h / 2, 0);
    faces.push(face);
  }
  const merged = mergeGeometries(faces, false)!;
  for (const f of faces) f.dispose();
  return merged;
}

export function createSite(asset: WorldAsset, tier: Tier, unknown: boolean): Site {
  const nominal = NOMINAL[tier];
  const spec = specFor(asset, tier);
  const accent = spec.accent;
  const { geometry, top } = composeSite(spec, nominal, unknown);
  const lat = new THREE.Color(spec.accent).lerp(new THREE.Color(0xffffff), 0.7).getHex();
  const material = createFacadeMaterial({
    instanced: false,
    seed: (hashString(asset.id) % 997) / 997,
    grid: { cols: SITE_COLS, rows: FACADE_ROWS, mullions: true },
    spandrel: 0.85,
    lattice: { hex: lat, period: 4, width: 0.06 },
    saturation: 1.22,
  });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;
  const texture = new THREE.CanvasTexture(drawSign(asset, "#" + new THREE.Color(accent).getHexString()));
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  // Unlit (no shading, no tone mapping): the sign reads the same at noon and, with the bloom,
  // glows at night. The plate on the facade and the lantern on the roof share it.
  const brandMaterial = new THREE.MeshBasicMaterial({ map: texture, toneMapped: false, side: THREE.DoubleSide });
  const brandPlate = new THREE.Mesh(signGeometry(nominal, top), brandMaterial);
  brandPlate.renderOrder = 3;

  const group = new THREE.Group();
  group.add(mesh, brandPlate);
  return { group, mesh, material, brandPlate, brandMaterial, nominal, top, sign: new THREE.Vector3(nominal * 0.5, 0.9, nominal * 0.5), signTop: lanternTop(nominal, top) };
}

export function disposeSite(s: Site) {
  s.mesh.geometry.dispose();
  s.material.dispose();
  s.brandPlate.geometry.dispose();
  s.brandMaterial.map?.dispose();
  s.brandMaterial.dispose();
}

const RUIN = { stone: 0x9c9184, dark: 0x6f665c, soot: 0x4f4a44, dust: 0x8a8076, rust: 0x8b5a3c, weed: 0x6f8f4e };

/**
 * A closed position: the building in ruins. It keeps its lot, its sign and its data (the
 * inspector still opens it), but nobody works there and nothing lights up: a holding the
 * user no longer has reads as such from anywhere in the town. Deterministic per ISIN.
 */
export function createRuins(asset: WorldAsset, tier: Tier): Site {
  const n = NOMINAL[tier];
  const h = n * 0.42;
  let seed = hashString(asset.id);
  const rnd = () => {
    seed = (Math.imul(seed ^ (seed >>> 15), 2246822507) + 0x6d2b79f5) >>> 0;
    return seed / 0xffffffff;
  };
  const b = new Builder();
  // Cracked foundation slab.
  b.box(n * 0.92, 0.22, n * 0.92, 0, 0, 0, RUIN.soot);
  b.box(n * 0.5, 0.06, n * 0.08, -n * 0.1, 0.22, n * 0.12, RUIN.dark, 0.4);
  // Two walls still standing, broken off at uneven heights (a jagged top).
  const wall = (x: number, z: number, len: number, alongX: boolean) => {
    const steps = 5;
    for (let i = 0; i < steps; i++) {
      const t = (i + 0.5) / steps - 0.5;
      const top = h * (0.35 + rnd() * 0.65) * (1 - Math.abs(t) * 0.6);
      const seg = len / steps - 0.04;
      const sx = alongX ? x + t * len : x;
      const sz = alongX ? z : z + t * len;
      b.box(alongX ? seg : 0.22, top, alongX ? 0.22 : seg, sx, 0.22, sz, i % 2 ? RUIN.stone : RUIN.dust);
      // Empty window holes: dark recesses in what is left.
      if (top > h * 0.5) b.box(alongX ? seg * 0.5 : 0.24, h * 0.14, alongX ? 0.24 : seg * 0.5, sx, 0.22 + top * 0.55, sz, RUIN.soot);
    }
  };
  wall(0, -n * 0.4, n * 0.8, true);
  wall(-n * 0.4, 0, n * 0.8, false);
  // A corner pillar and the stump of a third wall.
  b.box(0.36, h * 0.9, 0.36, n * 0.38, 0.22, -n * 0.38, RUIN.stone);
  b.box(n * 0.3, h * 0.2, 0.22, n * 0.2, 0.22, n * 0.4, RUIN.dust);
  // A fallen beam and rusted rebar.
  b.tilted(n * 0.55, 0.16, 0.16, n * 0.05, 0.45, n * 0.05, RUIN.rust, 0.35, 0.7);
  b.tilted(n * 0.4, 0.06, 0.06, -n * 0.15, 0.5, -n * 0.2, RUIN.rust, -0.6, 1.9);
  // Rubble heaps and a few weeds.
  for (let i = 0; i < 9; i++) {
    const x = (rnd() - 0.4) * n * 0.75;
    const z = (rnd() - 0.4) * n * 0.75;
    b.ico(0.18 + rnd() * 0.28, x, 0.3, z, rnd() < 0.5 ? RUIN.stone : RUIN.dust, 0);
  }
  for (let i = 0; i < 6; i++) b.cone(0.1, 0.35, (rnd() - 0.5) * n * 0.8, 0.22, (rnd() - 0.5) * n * 0.8, RUIN.weed, 4);
  const geometry = b.build();
  const top = b.top;

  const material = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.95, metalness: 0 });
  const mesh = new THREE.Mesh(geometry, material);
  mesh.castShadow = true;
  mesh.receiveShadow = true;

  // The old sign, faded and stamped, leaning against the front.
  const canvas = drawSign(asset, "#7d8590");
  const ctx = canvas.getContext("2d")!;
  ctx.fillStyle = "rgba(60, 56, 52, 0.55)";
  ctx.fillRect(0, 0, SIGN_W, SIGN_H);
  ctx.save();
  ctx.translate(SIGN_W / 2, SIGN_H / 2);
  ctx.rotate(-0.12);
  ctx.strokeStyle = "#c0392b";
  ctx.lineWidth = 7;
  ctx.strokeRect(-150, -40, 300, 80);
  ctx.fillStyle = "#e74c3c";
  ctx.font = "900 52px system-ui, sans-serif";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.fillText("CERRADA", 0, 4);
  ctx.restore();
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  // Lit like the stone (no glow): a closed company does not shine at night.
  const brandMaterial = new THREE.MeshBasicMaterial({ map: texture, color: 0xb8b2aa, side: THREE.DoubleSide });
  const plate = new THREE.PlaneGeometry(1.76, 1.76 * (SIGN_H / SIGN_W));
  plate.rotateX(-0.35);
  plate.rotateZ(0.08);
  plate.translate(0, 0.62, n * 0.47);
  const brandPlate = new THREE.Mesh(plate, brandMaterial);
  brandPlate.renderOrder = 3;

  const group = new THREE.Group();
  group.add(mesh, brandPlate);
  return { group, mesh, material, brandPlate, brandMaterial, nominal: n, top, sign: new THREE.Vector3(n * 0.5, 0.9, n * 0.5), signTop: top };
}
