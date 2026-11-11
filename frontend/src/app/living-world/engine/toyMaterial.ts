import * as THREE from "three";
import { mergeGeometries } from "three/addons/utils/BufferGeometryUtils.js";
import { facadeShared } from "./materials";

/**
 * Pieces shared by the little moving things of the town (cars, buses, trains, pedestrians): a
 * geometry builder that writes the per-vertex attributes their shaders read, and the shader patches.
 *
 * Per vertex: `color` (the part's own colour), `aKind` (what the part is) and `aLimb` (which limb
 * of a pedestrian it belongs to, so the vertex shader can swing it).
 *
 * `aKind`: 0 paint (takes the instance colour: car paint, a pedestrian's skin), 1 fixed colour,
 * 2 headlight, 3 taillight, 4 glass, 5 lit window, 6 hair (derived from the skin tone).
 */
export const KIND = { paint: 0, fixed: 1, head: 2, tail: 3, glass: 4, lit: 5, hair: 6 } as const;
export const LIMB = { none: 0, legR: 1, legL: 2, armR: 3, armL: 4 } as const;

export interface PartOpts {
  kind?: number;
  limb?: number;
  ry?: number;
  rx?: number;
  rz?: number;
}

export class GeoBuilder {
  private parts: THREE.BufferGeometry[] = [];
  private col = new THREE.Color();

  private push(g0: THREE.BufferGeometry, x: number, y: number, z: number, hex: number, o: PartOpts) {
    const g = g0.index ? g0.toNonIndexed() : g0;
    if (g !== g0) g0.dispose();
    g.deleteAttribute("uv");
    if (o.rx) g.rotateX(o.rx);
    if (o.rz) g.rotateZ(o.rz);
    if (o.ry) g.rotateY(o.ry);
    g.translate(x, y, z);
    const n = g.getAttribute("position").count;
    this.col.set(hex);
    const c = new Float32Array(n * 3);
    for (let i = 0; i < n; i++) c.set([this.col.r, this.col.g, this.col.b], i * 3);
    g.setAttribute("color", new THREE.BufferAttribute(c, 3));
    g.setAttribute("aKind", new THREE.BufferAttribute(new Float32Array(n).fill(o.kind ?? KIND.fixed), 1));
    g.setAttribute("aLimb", new THREE.BufferAttribute(new Float32Array(n).fill(o.limb ?? LIMB.none), 1));
    this.parts.push(g);
  }

  /** `y` is the bottom. */
  box(w: number, h: number, d: number, x: number, y: number, z: number, hex: number, o: PartOpts = {}) {
    this.push(new THREE.BoxGeometry(w, h, d), x, y + h / 2, z, hex, o);
  }

  /** A box with rounded edges and corners (a box whose vertices are pushed onto a rounded shell). */
  roundBox(w: number, h: number, d: number, r: number, x: number, y: number, z: number, hex: number, o: PartOpts = {}) {
    const g = new THREE.BoxGeometry(2, 2, 2, 3, 3, 3);
    const pos = g.getAttribute("position");
    const nor = g.getAttribute("normal");
    const half = [w / 2, h / 2, d / 2];
    const rr = Math.min(r, ...half) * 0.999;
    const tmp = [0, 0, 0];
    for (let i = 0; i < pos.count; i++) {
      const c = [pos.getX(i), pos.getY(i), pos.getZ(i)];
      const inner = [0, 0, 0];
      for (let a = 0; a < 3; a++) {
        const edge = Math.abs(c[a]) > 0.99;
        tmp[a] = Math.sign(c[a]) * (edge ? half[a] : half[a] - rr);
        inner[a] = Math.sign(c[a]) * (half[a] - rr);
        if (!edge) inner[a] = tmp[a];
      }
      const dir = [tmp[0] - inner[0], tmp[1] - inner[1], tmp[2] - inner[2]];
      const len = Math.hypot(dir[0], dir[1], dir[2]);
      if (len > 1e-6) {
        pos.setXYZ(i, inner[0] + (dir[0] / len) * rr, inner[1] + (dir[1] / len) * rr, inner[2] + (dir[2] / len) * rr);
        nor.setXYZ(i, dir[0] / len, dir[1] / len, dir[2] / len);
      } else pos.setXYZ(i, tmp[0], tmp[1], tmp[2]);
    }
    this.push(g, x, y + h / 2, z, hex, o);
  }

  /** `y` is the bottom; the axis is vertical unless rotated. */
  cyl(rTop: number, rBot: number, h: number, x: number, y: number, z: number, hex: number, seg = 8, o: PartOpts = {}) {
    this.push(new THREE.CylinderGeometry(rTop, rBot, h, seg), x, y + h / 2, z, hex, o);
  }

  /** `y` is the centre. */
  ellipsoid(rx: number, ry: number, rz: number, x: number, y: number, z: number, hex: number, o: PartOpts = {}, ws = 10, hs = 8) {
    const g = new THREE.SphereGeometry(1, ws, hs);
    g.scale(rx, ry, rz);
    this.push(g, x, y, z, hex, o);
  }

  /** `y` is the centre. */
  torus(r: number, tube: number, x: number, y: number, z: number, hex: number, o: PartOpts = {}) {
    this.push(new THREE.TorusGeometry(r, tube, 5, 10), x, y, z, hex, o);
  }

  cone(r: number, h: number, x: number, y: number, z: number, hex: number, seg = 6, o: PartOpts = {}) {
    this.push(new THREE.ConeGeometry(r, h, seg), x, y + h / 2, z, hex, o);
  }

  /** A sphere cap (hard hats, hair). `y` is the centre of the full sphere. */
  cap(r: number, x: number, y: number, z: number, hex: number, o: PartOpts = {}, theta = Math.PI / 2) {
    this.push(new THREE.SphereGeometry(r, 10, 6, 0, Math.PI * 2, 0, theta), x, y, z, hex, o);
  }

  build(): THREE.BufferGeometry {
    const merged = mergeGeometries(this.parts, false);
    this.parts.forEach((p) => p.dispose());
    this.parts = [];
    merged.computeBoundingSphere();
    return merged;
  }
}

// --- shaders ---------------------------------------------------------------------------------

const VERT_PARS = /* glsl */ `
#include <common>
attribute float aKind;
attribute float aLimb;
varying float vKind;
#ifdef WALK
attribute vec3 aAnim;
uniform float uTime;
#endif
#ifdef BRAKE
attribute float aBrake;
varying float vBrake;
#endif
`;

const VERT_COLOR = /* glsl */ `
#include <color_vertex>
vKind = aKind;
#ifdef USE_INSTANCING_COLOR
  vColor.rgb = color.rgb;
  if (aKind > PAINT_LO && aKind < PAINT_HI) vColor.rgb *= instanceColor.rgb;
  #ifdef PEOPLE
  if (aKind > 5.5) vColor.rgb = hairColour(instanceColor.rgb);
  #endif
#endif
#ifdef BRAKE
vBrake = aBrake;
#endif
`;

const VERT_WALK = /* glsl */ `
#include <begin_vertex>
#ifdef WALK
{
  float ph = uTime * aAnim.z + aAnim.x;
  float sw = sin(ph) * aAnim.y;
  float ang = 0.0;
  float pivot = 0.5;
  if (aLimb > 0.5 && aLimb < 1.5) ang = sw * 0.75;
  else if (aLimb > 1.5 && aLimb < 2.5) ang = -sw * 0.75;
  else if (aLimb > 2.5 && aLimb < 3.5) { ang = -sw * 0.65; pivot = 0.92; }
  else if (aLimb > 3.5) { ang = sw * 0.65; pivot = 0.92; }
  float c = cos(ang);
  float s = sin(ang);
  float dy = transformed.y - pivot;
  float zz = transformed.z;
  transformed.y = pivot + dy * c - zz * s;
  transformed.z = dy * s + zz * c;
  transformed.y += abs(sin(ph)) * 0.05 * aAnim.y;
}
#endif
`;

const FRAG_PARS = /* glsl */ `
#include <common>
varying float vKind;
#ifdef BRAKE
varying float vBrake;
#endif
uniform float uNight;
`;

const FRAG_ROUGH = /* glsl */ `
#include <roughnessmap_fragment>
float glassMask = step(3.5, vKind) * step(vKind, 5.5);
roughnessFactor = mix(roughnessFactor, 0.12, glassMask);
`;

const FRAG_METAL = /* glsl */ `
#include <metalnessmap_fragment>
metalnessFactor = mix(metalnessFactor, 0.35, glassMask);
`;

const FRAG_IBL = /* glsl */ `
#include <lights_fragment_maps>
radiance *= (1.0 - 0.85 * uNight);
iblIrradiance = vec3(0.0);
`;

const FRAG_EMISSIVE = /* glsl */ `
#include <emissivemap_fragment>
{
  float head = step(1.5, vKind) * step(vKind, 2.5);
  float tail = step(2.5, vKind) * step(vKind, 3.5);
  float lit = step(4.5, vKind) * step(vKind, 5.5);
  totalEmissiveRadiance += vColor.rgb * head * (0.12 + 2.2 * uNight);
  #ifdef BRAKE
  totalEmissiveRadiance += vColor.rgb * tail * (0.1 + 0.9 * uNight + 1.8 * vBrake);
  #else
  totalEmissiveRadiance += vColor.rgb * tail * (0.1 + 0.9 * uNight);
  #endif
  totalEmissiveRadiance += vec3(1.0, 0.85, 0.55) * lit * (0.06 + 0.9 * uNight);
}
`;

export interface ToyOptions {
  /** Instanced pedestrians: `aAnim` drives a walk cycle in the vertex shader. */
  walk?: boolean;
  /** Instanced vehicles: `aBrake` lights the taillights. */
  brake?: boolean;
  /** `aKind` range (exclusive) whose vertices take the instance colour. */
  paint: [number, number];
  roughness?: number;
}

/** Shared by every patched material; the world loop advances it. */
export const toyShared = { uTime: { value: 0 } };

export function createToyMaterial(o: ToyOptions): THREE.MeshStandardMaterial {
  const mat = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: o.roughness ?? 0.5,
    metalness: 0.0,
    envMap: facadeShared.envMap,
    envMapIntensity: 0.9,
  });
  const defines: Record<string, string | number> = { PAINT_LO: o.paint[0].toFixed(1), PAINT_HI: o.paint[1].toFixed(1) };
  if (o.walk) {
    defines.WALK = "";
    defines.PEOPLE = "";
  }
  if (o.brake) defines.BRAKE = "";
  mat.defines = defines;
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uNight = facadeShared.uNight;
    shader.uniforms.uTime = toyShared.uTime;
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", VERT_PARS + (o.walk ? HAIR_FN : ""))
      .replace("#include <color_vertex>", VERT_COLOR)
      .replace("#include <begin_vertex>", VERT_WALK);
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", FRAG_PARS)
      .replace("#include <roughnessmap_fragment>", FRAG_ROUGH)
      .replace("#include <metalnessmap_fragment>", FRAG_METAL)
      .replace("#include <lights_fragment_maps>", FRAG_IBL)
      .replace("#include <emissivemap_fragment>", FRAG_EMISSIVE);
  };
  mat.customProgramCacheKey = () => `toy-${o.walk ? "w" : "v"}${o.brake ? "b" : ""}`;
  return mat;
}

// Hair colour is picked from the instance colour (a skin tone) so the same skin always has the same
// hair, without a second instance attribute.
const HAIR_FN = /* glsl */ `
vec3 hairColour(vec3 skin) {
  float k = fract(skin.r * 17.0 + skin.g * 31.0 + skin.b * 7.0);
  if (k < 0.2) return vec3(0.10, 0.07, 0.05);
  if (k < 0.4) return vec3(0.28, 0.16, 0.08);
  if (k < 0.6) return vec3(0.52, 0.32, 0.14);
  if (k < 0.8) return vec3(0.82, 0.62, 0.26);
  return vec3(0.55, 0.14, 0.10);
}
`;
