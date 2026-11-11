import * as THREE from "three";

/**
 * Stylised materials for the town.
 *
 * `createFacadeMaterial` is a MeshStandardMaterial patched with `onBeforeCompile`: glass parts
 * (flagged per vertex by the `aKind` attribute that `Builder` writes) get a window grid with
 * mullions, a vertical gradient, sky reflections and, at night, lit windows. Walls and roofs stay
 * plain. It works on merged vertex-coloured geometry (one landmark site per material) and on
 * `InstancedMesh` (fillers carry per-instance wall colour, glass colour and seed).
 *
 * Glass is deliberately OPAQUE: the look comes from the environment map and the shader, not from
 * transparency (transparent depth-writing meshes are drawn twice by the AO pass).
 */

/** Shared by every facade material; the renderer drives them once per frame. */
export const facadeShared = {
  uNight: { value: 0 },
  envMap: null as THREE.Texture | null,
};

const live = new Set<THREE.MeshStandardMaterial>();

/** Scales how strongly glass reflects the sky (it is dim at night). */
export function setFacadeEnvIntensity(v: number) {
  for (const m of live) m.envMapIntensity = v;
}

/** 0 = day, 1 = night. Lit windows fade in with it. */
export function setFacadeNight(night: number) {
  facadeShared.uNight.value = night;
}

export interface FacadeOptions {
  /** Instanced buildings read wall colour, glass colour and seed from instance attributes. */
  instanced: boolean;
  /** Seed for the lit-window pattern of a non-instanced building. */
  seed?: number;
  /** Window cells per local unit across a facade and up it; `mullions` draws the bars between them. */
  grid?: { cols: number; rows: number; mullions: boolean };
  /** Share of colour kept when grading: >1 is punchier. */
  saturation?: number;
  /** Brightness multiplier for lit windows. */
  windowGlow?: number;
  /** 0..1: darkens the lower edge of every window cell, so storeys read as floor plates. */
  spandrel?: number;
  /** Diagonal lattice (diagrid) drawn on kind-3 glass: bar colour, period in window cells, half-width in periods. */
  lattice?: { hex: number; period: number; width: number };
}

const VERT_PARS = /* glsl */ `
#include <common>
attribute float aKind;
attribute float aArc;
varying float vKind;
varying float vArc;
varying vec3 vLPos;
varying vec3 vLNorm;
#ifdef FACADE_INSTANCED
attribute vec3 aWall;
attribute vec3 aGlass;
attribute float aSeed;
varying vec3 vWall;
varying vec3 vGlass;
varying float vSeed;
#endif
`;

const VERT_BODY = /* glsl */ `
#include <begin_vertex>
vKind = aKind;
vArc = aArc;
vLPos = position;
vLNorm = normal;
#ifdef FACADE_INSTANCED
vWall = aWall;
vGlass = aGlass;
vSeed = aSeed;
#endif
`;

const FRAG_PARS = /* glsl */ `
#include <common>
varying float vKind;
varying float vArc;
varying vec3 vLPos;
varying vec3 vLNorm;
#ifdef FACADE_INSTANCED
varying vec3 vWall;
varying vec3 vGlass;
varying float vSeed;
#else
uniform float uSeed;
#endif
uniform float uNight;
uniform vec3 uGrid;
uniform float uSat;
uniform float uGlow;
uniform vec3 uExtra;
uniform vec3 uLat;
float fHash(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
`;

// After this chunk `diffuseColor` holds the vertex colour. Wall/glass tints, window grid, gradient.
const FRAG_COLOR = /* glsl */ `
#include <color_fragment>
#ifdef FACADE_INSTANCED
float fSeed = vSeed;
diffuseColor.rgb *= mix(vWall, vGlass, step(0.5, vKind));
#else
float fSeed = uSeed;
#endif
float fWall = smoothstep(0.6, 0.35, abs(vLNorm.y));
float fIsGlass = step(0.5, vKind) * step(vKind, 1.5) + step(2.5, vKind) * step(vKind, 3.5);
float fGlass = fIsGlass * fWall;
// Curved shells carry their own arc length (aArc, a whole number of window columns round the
// ring); anything else picks the horizontal axis from the facing.
float fHoriz = vArc > -1000.0 ? vArc : (abs(vLNorm.x) > abs(vLNorm.z) ? vLPos.z : vLPos.x);
vec2 fCell = vec2(fHoriz * uGrid.x, vLPos.y * uGrid.y);
vec2 fId = floor(fCell) + vec2(fSeed * 37.1, fSeed * 91.7);
vec2 fF = fract(fCell);
float fPane = uGrid.z > 0.5 ? smoothstep(0.0, 0.08, fF.x) * smoothstep(1.0, 0.92, fF.x) : 1.0;
fPane *= mix(1.0, smoothstep(0.0, 0.16, fF.y), uExtra.x);
float fVar = fHash(fId + 3.7);
float fL = dot(diffuseColor.rgb, vec3(0.2126, 0.7152, 0.0722));
diffuseColor.rgb = mix(vec3(fL), diffuseColor.rgb, uSat);
vec3 fGlassCol = diffuseColor.rgb * (1.0 + 0.24 * fVar) * (0.96 + 0.42 * clamp(vLPos.y * 0.07, 0.0, 1.0));
fGlassCol *= mix(0.5, 1.0, fPane);
diffuseColor.rgb = mix(diffuseColor.rgb, fGlassCol, fGlass);
// Diagrid: two families of diagonals across the window cells (kind 3 only).
float fLat = 0.0;
if (uExtra.y > 0.5 && vKind > 2.5) {
  vec2 lc = fCell / uExtra.y;
  float s1 = fract(lc.x + lc.y);
  float s2 = fract(lc.x - lc.y);
  float dl = min(min(s1, 1.0 - s1), min(s2, 1.0 - s2));
  float aa = max(fwidth(lc.x), fwidth(lc.y)) * 0.7 + 0.01;
  fLat = (1.0 - smoothstep(uExtra.z - aa, uExtra.z + aa, dl)) * fGlass;
  diffuseColor.rgb = mix(diffuseColor.rgb, uLat, fLat);
}
// Walls get a faint ground-contact darkening so they sit on the street.
diffuseColor.rgb *= mix(1.0, 0.8 + 0.2 * smoothstep(0.0, 1.4, vLPos.y), (1.0 - step(0.5, vKind)) * fWall);
`;

const FRAG_ROUGH = /* glsl */ `
#include <roughnessmap_fragment>
roughnessFactor = mix(roughnessFactor, 0.2, fGlass);
`;

const FRAG_METAL = /* glsl */ `
#include <metalnessmap_fragment>
metalnessFactor = mix(metalnessFactor, 0.28, fGlass * (1.0 - fLat));
`;

// The sky map is for reflections only: ambient light comes from the hemisphere light, which every
// other material in the town shares, so the glass does not end up brighter than its neighbours.
const FRAG_IBL = /* glsl */ `
#include <lights_fragment_maps>
iblIrradiance = vec3(0.0);
`;

const FRAG_EMISSIVE = /* glsl */ `
#include <emissivemap_fragment>
{
  float fR = fHash(fId + 11.3);
  float fOn = step(0.4, fR);
  vec3 fWarm = mix(vec3(1.0, 0.7, 0.36), vec3(0.72, 0.88, 1.0), step(0.88, fHash(fId + 7.1)));
  totalEmissiveRadiance += fWarm * fOn * fPane * fGlass * (1.0 - fLat) * uNight * uGlow * (0.65 + 0.7 * fHash(fId + 1.9));
  // A thin bright rim on glass seen at a grazing angle.
  float fFres = pow(1.0 - clamp(dot(normalize(vViewPosition), normal), 0.0, 1.0), 3.0);
  totalEmissiveRadiance += fGlass * fFres * vec3(0.5, 0.72, 1.0) * 0.16 * (1.0 - uNight * 0.85);
}
`;

export function createFacadeMaterial(o: FacadeOptions): THREE.MeshStandardMaterial {
  const mat = new THREE.MeshStandardMaterial({
    vertexColors: true,
    roughness: 0.78,
    metalness: 0,
    envMap: facadeShared.envMap,
  });
  if (o.instanced) mat.defines = { FACADE_INSTANCED: "" };
  const seed = o.seed ?? 0;
  const grid = o.grid ?? { cols: 2.6, rows: 2.6, mullions: false };
  const sat = o.saturation ?? 1.18;
  const glow = o.windowGlow ?? 1.5;
  mat.onBeforeCompile = (shader) => {
    shader.uniforms.uNight = facadeShared.uNight;
    shader.uniforms.uSeed = { value: seed };
    shader.uniforms.uGrid = { value: new THREE.Vector3(grid.cols, grid.rows, grid.mullions ? 1 : 0) };
    shader.uniforms.uSat = { value: sat };
    shader.uniforms.uGlow = { value: glow };
    shader.uniforms.uExtra = { value: new THREE.Vector3(o.spandrel ?? 0, o.lattice?.period ?? 0, o.lattice?.width ?? 0) };
    shader.uniforms.uLat = { value: new THREE.Color(o.lattice?.hex ?? 0xffffff) };
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", VERT_PARS)
      .replace("#include <begin_vertex>", VERT_BODY);
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", FRAG_PARS)
      .replace("#include <color_fragment>", FRAG_COLOR)
      .replace("#include <roughnessmap_fragment>", FRAG_ROUGH)
      .replace("#include <metalnessmap_fragment>", FRAG_METAL)
      .replace("#include <lights_fragment_maps>", FRAG_IBL)
      .replace("#include <emissivemap_fragment>", FRAG_EMISSIVE);
  };
  mat.customProgramCacheKey = () => (o.instanced ? "facade-i" : "facade-s");
  live.add(mat);
  mat.addEventListener("dispose", () => live.delete(mat));
  return mat;
}

/**
 * A soft sky dome baked into a prefiltered environment map: blue above, bright at the horizon,
 * a warm green-grey bounce below. Glass reflects it. Dispose the returned texture with the world.
 */
export function createSkyEnvironment(renderer: THREE.WebGLRenderer): THREE.Texture {
  const c = document.createElement("canvas");
  c.width = 256;
  c.height = 128;
  const g = c.getContext("2d")!;
  const grad = g.createLinearGradient(0, 0, 0, 128);
  grad.addColorStop(0, "#3d86d8");
  grad.addColorStop(0.32, "#9fd0f2");
  grad.addColorStop(0.5, "#f4fbff");
  grad.addColorStop(0.56, "#cfd9cf");
  grad.addColorStop(1, "#7f9a78");
  g.fillStyle = grad;
  g.fillRect(0, 0, 256, 128);
  // A bright sun blob so metallic panes catch a highlight.
  const sun = g.createRadialGradient(150, 44, 0, 150, 44, 22);
  sun.addColorStop(0, "rgba(255,250,235,1)");
  sun.addColorStop(1, "rgba(255,250,235,0)");
  g.fillStyle = sun;
  g.fillRect(0, 0, 256, 128);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.mapping = THREE.EquirectangularReflectionMapping;
  const pmrem = new THREE.PMREMGenerator(renderer);
  const rt = pmrem.fromEquirectangular(tex);
  tex.dispose();
  pmrem.dispose();
  return rt.texture;
}

/** The visible sky: a screen-space gradient, redrawn when the circadian colours or pitch move. */
export class SkyBackdrop {
  readonly texture: THREE.CanvasTexture;
  private readonly canvas: HTMLCanvasElement;
  private readonly g: CanvasRenderingContext2D;
  private last = "";

  constructor() {
    this.canvas = document.createElement("canvas");
    this.canvas.width = 4;
    this.canvas.height = 256;
    this.g = this.canvas.getContext("2d")!;
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
  }

  /**
   * `horizon` and `zenith` are working-space colours. `horizonFrac` is where the horizon sits on
   * screen from the top (0 = top edge); everything below is the fog colour, so the far land melts
   * into the sky exactly where the gradient ends.
   */
  update(horizon: THREE.Color, zenith: THREE.Color, horizonFrac: number) {
    const h = "#" + horizon.getHexString();
    const z = "#" + zenith.getHexString();
    const hf = Math.min(1, Math.max(0, Math.round(horizonFrac * 256) / 256));
    const key = h + z + hf;
    if (key === this.last) return;
    this.last = key;
    this.g.fillStyle = h;
    this.g.fillRect(0, 0, 4, 256);
    if (hf > 0.004) {
      const grad = this.g.createLinearGradient(0, 0, 0, hf * 256);
      grad.addColorStop(0, z);
      grad.addColorStop(0.55, mixHex(z, h, 0.5));
      grad.addColorStop(1, h);
      this.g.fillStyle = grad;
      this.g.fillRect(0, 0, 4, Math.ceil(hf * 256));
    }
    this.texture.needsUpdate = true;
  }

  dispose() {
    this.texture.dispose();
  }
}

function mixHex(a: string, b: string, t: number): string {
  const ca = new THREE.Color(a);
  const cb = new THREE.Color(b);
  return "#" + ca.lerp(cb, t).getHexString();
}
