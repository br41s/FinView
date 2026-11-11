import * as THREE from "three";
import { DISTRICT_LABEL } from "../model/archetypes";
import { valueNoise } from "../model/rng";
import { WATER_Y, type Pt, type Terrain } from "../model/terrain";
import { PLAZA_RADIUS, type CivicKind, type WorldLayout } from "../model/townLayout";
import { accentFor, Builder } from "./buildingFactory";
import type { WorldAsset } from "../model/types";
import { buildFillers, type Fillers } from "./fillers";
import { buildRoads } from "./roads";

/** Land, water, streets, plaza, civic buildings, trees and text labels: the static stage. */

const STREET = 0x646973;
const WHITE = 0xf4f1ea;
const DARK = 0x3b4048;

function offsetPath(line: readonly Pt[], offset: number): Pt[] {
  return line.map((point, i) => {
    const previous = line[Math.max(0, i - 1)];
    const next = line[Math.min(line.length - 1, i + 1)];
    const dx = next.x - previous.x;
    const dz = next.z - previous.z;
    const length = Math.hypot(dx, dz) || 1;
    const nx = -dz / length;
    const nz = dx / length;
    return { x: point.x + nx * offset, z: point.z + nz * offset };
  });
}

export interface Town {
  group: THREE.Group;
  trees: THREE.InstancedMesh;
  fillers: Fillers;
  districtLabels: THREE.Sprite[];
  /** Positions of the civic buildings, so choreography can send vans to the bank. */
  civic: Map<CivicKind, THREE.Vector3>;
  setTreeCount(n: number): void;
  update?(dtMs: number): void;
  dispose(): void;
}

function mat(hex: number) {
  return new THREE.MeshLambertMaterial({ color: hex, flatShading: true });
}

export function makeLabel(text: string, opts: { font?: number; bg?: string; fg?: string } = {}): THREE.Sprite {
  const font = opts.font ?? 30;
  const pad = 14;
  const c = document.createElement("canvas");
  const ctx = c.getContext("2d")!;
  ctx.font = `600 ${font}px system-ui, sans-serif`;
  const w = Math.ceil(ctx.measureText(text).width) + pad * 2;
  const h = font + pad * 1.2;
  c.width = w;
  c.height = h;
  ctx.font = `600 ${font}px system-ui, sans-serif`;
  ctx.fillStyle = opts.bg ?? "rgba(255,252,243,0.92)";
  ctx.beginPath();
  ctx.roundRect(0, 0, w, h, h / 2);
  ctx.fill();
  ctx.fillStyle = opts.fg ?? "#2d3340";
  ctx.textBaseline = "middle";
  ctx.fillText(text, pad, h / 2 + 1);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 2;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  // World height of one label line; width follows the text so the aspect is kept.
  sprite.userData.aspect = w / h;
  sprite.scale.set((w / h) * 1, 1, 1);
  sprite.renderOrder = 10;
  return sprite;
}

/**
 * Camera-facing illuminated company sign generated locally from its ticker/name and
 * deterministic site accent (matching its corporate profile). Uses no external assets.
 */
export function makeBrandLabel(asset: WorldAsset): THREE.Sprite {
  const width = 640;
  const height = 184;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  const accent = new THREE.Color(accentFor(asset.id, asset));
  const accentCss = "#" + accent.getHexString();
  const ticker = (asset.ticker?.trim() || asset.name.split(/[^A-Za-z0-9]+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("") || "•")
    .toUpperCase()
    .slice(0, 12);
  const initials = asset.name.split(/[^A-Za-z0-9]+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || ticker.slice(0, 1);

  // Coloured luminous frame.
  ctx.shadowColor = accentCss;
  ctx.shadowBlur = 20;
  ctx.fillStyle = accentCss;
  ctx.beginPath();
  ctx.roundRect(7, 7, width - 14, height - 14, 30);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Dark enamel face, illuminated accent rail and initials medallion.
  ctx.fillStyle = "#111c2b";
  ctx.beginPath();
  ctx.roundRect(15, 15, width - 30, height - 30, 24);
  ctx.fill();
  ctx.fillStyle = accentCss;
  ctx.beginPath();
  ctx.roundRect(15, 15, 14, height - 30, 7);
  ctx.fill();
  ctx.beginPath();
  ctx.arc(91, 92, 54, 0, Math.PI * 2);
  ctx.fill();

  ctx.fillStyle = "#ffffff";
  ctx.textAlign = "center";
  ctx.textBaseline = "middle";
  ctx.font = "800 58px system-ui, sans-serif";
  ctx.fillText(initials.slice(0, 2), 91, 94, 88);

  ctx.textAlign = "left";
  ctx.textBaseline = "alphabetic";
  let fontSize = 64;
  ctx.font = "800 " + fontSize + "px system-ui, sans-serif";
  while (fontSize > 40 && ctx.measureText(ticker).width > 330) {
    fontSize -= 2;
    ctx.font = "800 " + fontSize + "px system-ui, sans-serif";
  }
  ctx.fillStyle = "#ffffff";
  ctx.fillText(ticker, 166, 91, 330);

  if (asset.weightPct !== null && Number.isFinite(asset.weightPct)) {
    const badge = `${asset.weightPct.toFixed(1).replace(".", ",")} %`;
    ctx.font = "700 26px system-ui, sans-serif";
    const bw = Math.ceil(ctx.measureText(badge).width) + 28;
    const bx = width - 34 - bw;
    ctx.fillStyle = accentCss;
    ctx.beginPath();
    ctx.roundRect(bx, 42, bw, 44, 14);
    ctx.fill();
    ctx.fillStyle = "#ffffff";
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(badge, bx + bw / 2, 65);
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
  }

  ctx.fillStyle = "#d3dfec";
  ctx.font = "600 27px system-ui, sans-serif";
  ctx.fillText(asset.name, 168, 139, 430);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false, toneMapped: false }),
  );
  sprite.userData.aspect = width / height;
  sprite.scale.set((width / height) * 0.84, 0.84, 1);
  sprite.renderOrder = 11;
  return sprite;
}

export function disposeLabel(s: THREE.Sprite) {
  s.material.map?.dispose();
  s.material.dispose();
}

function civicGeometry(kind: CivicKind): THREE.BufferGeometry {
  const b = new Builder();
  b.cyl(2.2, 2.4, 0.15, 0, 0, 0, 0xd8dce2, 14);
  if (kind === "bank") {
    b.box(3.4, 2.0, 2.6, 0, 0.15, 0, 0xe8ebf0);
    for (let i = 0; i < 4; i++) b.cyl(0.14, 0.14, 2.0, -1.2 + i * 0.8, 0.15, 1.5, WHITE, 8);
    b.box(3.7, 0.22, 2.9, 0, 2.15, 0, 0xd9a82b);
    b.cyl(0.5, 0.5, 0.1, 0, 2.4, 0, 0xe6b422, 12);
  } else if (kind === "newsKiosk") {
    b.box(2.0, 1.2, 1.6, 0, 0.15, 0, 0xdce0e6);
    for (let i = 0; i < 5; i++) b.box(0.42, 0.12, 2.0, -0.84 + i * 0.42, 1.4, 0.1, i % 2 ? WHITE : 0x5c626d);
    b.box(1.4, 0.5, 0.06, 0, 0.55, 0.85, 0xeef2f6);
  } else if (kind === "observatory") {
    b.cyl(1.0, 1.2, 1.6, 0, 0.15, 0, 0xdfe3e8, 12);
    b.sphere(1.05, 0, 1.75, 0, 0x9aa2ad);
    b.box(0.12, 1.0, 0.12, 0, 2.7, 0, DARK);
  } else {
    b.box(3.0, 1.6, 2.2, 0, 0.15, 0, 0xe2e5ea);
    b.box(3.2, 0.2, 2.4, 0, 1.75, 0, 0x686e78);
    b.box(0.9, 1.4, 0.9, 0, 1.95, 0, 0xe2e5ea);
    b.cone(0.75, 0.8, 0, 3.3, 0, 0x525760, 4);
    b.cyl(0.28, 0.28, 0.06, 0, 2.4, 0.46, WHITE, 12);
  }
  return b.build();
}

function treeGeometry(): THREE.BufferGeometry {
  const b = new Builder();
  b.cyl(0.08, 0.1, 0.5, 0, 0, 0, 0x6b533e, 5);
  b.cone(0.45, 0.8, 0, 0.4, 0, 0x4f9458, 7);
  b.cone(0.34, 0.65, 0, 0.9, 0, 0x62a668, 7);
  return b.build();
}

const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

/** Ground colour: a level lawn, sand on the canal banks and the canal bed. */
function groundColor(h: number, x: number, z: number, out: THREE.Color): THREE.Color {
  const n = valueNoise(x * 0.05, z * 0.05, 5) * 0.08 - 0.04;
  out.set(0x98c987);
  if (h < -0.05) out.lerp(new THREE.Color(0xe0d4aa), smooth(-0.05, -0.5, h)); // bank
  if (h < -0.6) out.set(0xc7ba94); // canal bed
  out.offsetHSL(0, 0, n);
  return out;
}

/** The plain: a tensor grid, coarse away from the canal and fine across it. */
function terrainGeometry(t: Terrain): THREE.BufferGeometry {
  const { xs, zs } = t.groundAxes();
  const nx = xs.length;
  const nz = zs.length;
  const pos = new Float32Array(nx * nz * 3);
  const colors = new Float32Array(nx * nz * 3);
  const c = new THREE.Color();
  for (let i = 0; i < nx; i++) {
    for (let j = 0; j < nz; j++) {
      const h = t.heightAt(xs[i], zs[j]);
      const k = (i * nz + j) * 3;
      pos[k] = xs[i];
      pos[k + 1] = h;
      pos[k + 2] = zs[j];
      groundColor(h, xs[i], zs[j], c);
      colors[k] = c.r;
      colors[k + 1] = c.g;
      colors[k + 2] = c.b;
    }
  }
  const index: number[] = [];
  for (let i = 0; i < nx - 1; i++) {
    for (let j = 0; j < nz - 1; j++) {
      const a = i * nz + j;
      const b = a + 1;
      const d = a + nz;
      const e = d + 1;
      index.push(a, b, d, b, e, d);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.BufferAttribute(colors, 3));
  g.setIndex(index);
  g.computeVertexNormals();
  return g;
}

/** A flat strip draped over the ground along `line`, for roads and rails. */
export function ribbon(line: readonly Pt[], width: number, lift: number, hex: number, y: (x: number, z: number) => number): THREE.BufferGeometry {
  const pos: number[] = [];
  const idx: number[] = [];
  const col = new THREE.Color(hex);
  const colors: number[] = [];
  // Resample every ~2.5 units so the strip follows hills and bridges.
  const pts: Pt[] = [];
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1];
    const b = line[i];
    const len = Math.hypot(b.x - a.x, b.z - a.z);
    const k = Math.max(1, Math.ceil(len / 2.5));
    for (let s = i === 1 ? 0 : 1; s <= k; s++) pts.push({ x: a.x + ((b.x - a.x) * s) / k, z: a.z + ((b.z - a.z) * s) / k });
  }
  pts.forEach((p, i) => {
    const prev = pts[Math.max(0, i - 1)];
    const next = pts[Math.min(pts.length - 1, i + 1)];
    let dx = next.x - prev.x;
    let dz = next.z - prev.z;
    const l = Math.hypot(dx, dz) || 1;
    dx /= l;
    dz /= l;
    const nx = -dz * (width / 2);
    const nz = dx * (width / 2);
    const h = y(p.x, p.z) + lift;
    pos.push(p.x + nx, h, p.z + nz, p.x - nx, h, p.z - nz);
    colors.push(col.r, col.g, col.b, col.r, col.g, col.b);
    if (i > 0) {
      const a = (i - 1) * 2;
      // Counter-clockwise seen from above, so the strip faces up.
      idx.push(a, a + 2, a + 1, a + 1, a + 2, a + 3);
    }
  });
  const g = new THREE.BufferGeometry();
  g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

export function buildTown(layout: WorldLayout, maxTrees: number): Town {
  const group = new THREE.Group();
  const disposables: Array<{ dispose(): void }> = [];
  const own = <T extends { dispose(): void }>(x: T) => (disposables.push(x), x);
  const t = layout.terrain;
  const vcMat = own(new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true }));

  // The land: one heightfield with vertex colours (shore, lawns, forest, rock, snow).
  const land = new THREE.Mesh(own(terrainGeometry(t)), own(new THREE.MeshLambertMaterial({ vertexColors: true })));
  land.receiveShadow = true;
  group.add(land);

  // Sea, lake and river are one water surface; the ground dips below it where they are.
  const water = new THREE.Mesh(
    own(new THREE.CircleGeometry(t.extent * 6, 48)),
    own(new THREE.MeshLambertMaterial({ color: 0x62bce0 })),
  );
  water.rotation.x = -Math.PI / 2;
  water.position.y = WATER_Y;
  group.add(water);

  // Streets, junctions, crosswalks, bridges, block ground and park paths (engine/roads.ts).
  const roads = buildRoads(layout);
  group.add(roads.group);

  // Central square: architectural stone paving, market bell, and the four civic buildings.
  const plaza = new THREE.Mesh(own(new THREE.CylinderGeometry(PLAZA_RADIUS - 1, PLAZA_RADIUS - 1, 0.12, 40)), own(mat(0xdadfe6)));
  plaza.position.y = 0.08;
  plaza.receiveShadow = true;
  group.add(plaza);

  // Central plaza fountain: tiered stone basin, turquoise water surface and animated spray
  const fountainBase = new THREE.Mesh(
    own(new THREE.CylinderGeometry(4.2, 4.5, 0.42, 28)),
    own(mat(0xf2f4f8)),
  );
  fountainBase.position.set(0, 0.28, 0);
  fountainBase.castShadow = true;
  fountainBase.receiveShadow = true;
  group.add(fountainBase);

  const fountainWater = new THREE.Mesh(
    own(new THREE.CircleGeometry(4.0, 28)),
    own(new THREE.MeshBasicMaterial({ color: 0x48c2e0, transparent: true, opacity: 0.88, toneMapped: false })),
  );
  fountainWater.rotation.x = -Math.PI / 2;
  fountainWater.position.set(0, 0.5, 0);
  group.add(fountainWater);

  const fountainTier = new THREE.Mesh(
    own(new THREE.CylinderGeometry(1.4, 1.6, 0.75, 18)),
    own(mat(0xe5e9f0)),
  );
  fountainTier.position.set(0, 0.65, 0);
  fountainTier.castShadow = true;
  group.add(fountainTier);

  const fountainSpray = new THREE.Mesh(
    own(new THREE.ConeGeometry(0.55, 1.4, 12)),
    own(new THREE.MeshBasicMaterial({ color: 0xc4f4ff, transparent: true, opacity: 0.72, toneMapped: false })),
  );
  fountainSpray.position.set(0, 1.45, 0);
  group.add(fountainSpray);

  let fountainTime = 0;

  const bellGeo = (() => {
    const b = new Builder();
    b.cyl(1.4, 1.6, 0.3, 0, 0, 0, 0xc4c9d1, 16);
    b.cyl(0.12, 0.12, 2.4, 0, 0.3, 0, DARK, 6);
    b.cone(0.55, 0.7, 0, 2.2, 0, 0xe6b422, 12);
    return b.build();
  })();
  own(bellGeo);
  const bell = new THREE.Mesh(bellGeo, vcMat);
  bell.position.y = 0.14;
  bell.castShadow = true;
  group.add(bell);

  const civic = new Map<CivicKind, THREE.Vector3>();
  for (const c of layout.civic) {
    const geo = own(civicGeometry(c.kind));
    const m = new THREE.Mesh(geo, vcMat);
    m.position.set(c.x, 0.14, c.z);
    m.rotation.y = Math.atan2(-c.x, -c.z);
    m.castShadow = true;
    m.receiveShadow = true;
    group.add(m);
    civic.set(c.kind, new THREE.Vector3(c.x, 0, c.z));
  }

  // Homes, offices and towers between and inside the districts.
  const fillers = buildFillers(layout.filler, t);
  group.add(fillers.group);

  // Trees: parks, canal banks, pavements and the country beyond (positions come from the layout).
  const spots = layout.treeSpots;
  const treeGeo = own(treeGeometry());
  const trees = new THREE.InstancedMesh(treeGeo, vcMat, Math.max(1, spots.length));
  const m4 = new THREE.Matrix4();
  spots.forEach(([x, z, sc], i) => {
    m4.compose(new THREE.Vector3(x, t.heightAt(x, z), z), new THREE.Quaternion(), new THREE.Vector3(sc, sc, sc));
    trees.setMatrixAt(i, m4);
  });
  trees.count = Math.min(maxTrees, spots.length);
  trees.castShadow = true;
  group.add(trees);

  // District names, visible from far away.
  const districtLabels: THREE.Sprite[] = [];
  for (const d of layout.districts) {
    const s = makeLabel(`${DISTRICT_LABEL[d.id]} · ${d.assetCount}`, { font: 34, bg: "rgba(38,43,52,0.86)", fg: "#f4f6f9" });
    s.position.set(d.cx, t.heightAt(d.cx, d.cz) + 22, d.cz);
    s.userData.district = d.id;
    group.add(s);
    districtLabels.push(s);
  }

  return {
    group,
    trees,
    fillers,
    districtLabels,
    civic,
    setTreeCount(n) {
      trees.count = Math.min(n, spots.length);
    },
    update(dtMs: number) {
      fountainTime += dtMs / 1000;
      const sprayPulse = 1.0 + Math.sin(fountainTime * 5.2) * 0.18;
      fountainSpray.scale.set(sprayPulse, 0.85 + Math.sin(fountainTime * 6.5) * 0.22, sprayPulse);
      (fountainWater.material as THREE.MeshBasicMaterial).opacity = 0.82 + Math.sin(fountainTime * 3.4) * 0.09;
    },
    dispose() {
      disposables.forEach((d) => d.dispose());
      roads.dispose();
      fillers.dispose();
      trees.dispose();
      districtLabels.forEach(disposeLabel);
    },
  };
}
