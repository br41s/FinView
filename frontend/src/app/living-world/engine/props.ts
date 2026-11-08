import * as THREE from "three";
import { DISTRICT_LABEL } from "../model/archetypes";
import { seeded, valueNoise } from "../model/rng";
import { pointAlong, routeLength } from "../model/routes";
import { WATER_Y, distToPolyline, type Pt, type Terrain } from "../model/terrain";
import { LOT_PITCH, PLAZA_RADIUS, toWorld, type CivicKind, type WorldLayout } from "../model/townLayout";
import { accentFor, Builder } from "./buildingFactory";
import type { WorldAsset } from "../model/types";
import { buildFillers, type Fillers } from "./fillers";

/** Land, water, streets, plaza, civic buildings, trees and text labels: the static stage. */

const STREET = 0x8d9097;
const LANE = 0xb3b5b3;
const WHITE = 0xf4f1ea;
const DARK = 0x4a4f5a;

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
 * deterministic site accent. It uses no external logo assets or network requests.
 */
export function makeBrandLabel(asset: WorldAsset): THREE.Sprite {
  const width = 640;
  const height = 184;
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const ctx = canvas.getContext("2d")!;
  const accent = new THREE.Color(accentFor(asset.id));
  const accentCss = "#" + accent.getHexString();
  const ticker = (asset.ticker?.trim() || asset.name.split(/[^A-Za-z0-9]+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("") || "•")
    .toUpperCase()
    .slice(0, 12);
  const initials = asset.name.split(/[^A-Za-z0-9]+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("").toUpperCase() || ticker.slice(0, 1);

  // Coloured luminous frame.
  ctx.shadowColor = accentCss;
  ctx.shadowBlur = 18;
  ctx.fillStyle = accentCss;
  ctx.beginPath();
  ctx.roundRect(7, 7, width - 14, height - 14, 30);
  ctx.fill();
  ctx.shadowBlur = 0;

  // Dark enamel face, illuminated accent rail and initials medallion.
  ctx.fillStyle = "#172638";
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
  let fontSize = 66;
  ctx.font = "800 " + fontSize + "px system-ui, sans-serif";
  while (fontSize > 42 && ctx.measureText(ticker).width > 430) {
    fontSize -= 2;
    ctx.font = "800 " + fontSize + "px system-ui, sans-serif";
  }
  ctx.fillStyle = "#ffffff";
  ctx.fillText(ticker, 166, 91, 430);

  ctx.fillStyle = "#c7d3e1";
  ctx.font = "600 27px system-ui, sans-serif";
  ctx.fillText(asset.name, 168, 139, 430);

  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  texture.anisotropy = 4;
  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({ map: texture, transparent: true, depthWrite: false, toneMapped: false }),
  );
  sprite.userData.aspect = width / height;
  sprite.scale.set((width / height) * 0.82, 0.82, 1);
  sprite.renderOrder = 11;
  return sprite;
}

export function disposeLabel(s: THREE.Sprite) {
  s.material.map?.dispose();
  s.material.dispose();
}

function civicGeometry(kind: CivicKind): THREE.BufferGeometry {
  const b = new Builder();
  b.cyl(2.2, 2.4, 0.15, 0, 0, 0, 0xe8dcc0, 14);
  if (kind === "bank") {
    b.box(3.4, 2.0, 2.6, 0, 0.15, 0, 0xf1ead8);
    for (let i = 0; i < 4; i++) b.cyl(0.14, 0.14, 2.0, -1.2 + i * 0.8, 0.15, 1.5, WHITE, 8);
    b.box(3.7, 0.22, 2.9, 0, 2.15, 0, 0xd9a82b);
    b.cyl(0.5, 0.5, 0.1, 0, 2.4, 0, 0xe6b422, 12);
  } else if (kind === "newsKiosk") {
    b.box(2.0, 1.2, 1.6, 0, 0.15, 0, 0xf3d6c4);
    for (let i = 0; i < 5; i++) b.box(0.42, 0.12, 2.0, -0.84 + i * 0.42, 1.4, 0.1, i % 2 ? WHITE : 0xd8423f);
    b.box(1.4, 0.5, 0.06, 0, 0.55, 0.85, 0xfff7e0);
  } else if (kind === "observatory") {
    b.cyl(1.0, 1.2, 1.6, 0, 0.15, 0, 0xe9eef2, 12);
    b.sphere(1.05, 0, 1.75, 0, 0x8fc7e8);
    b.box(0.12, 1.0, 0.12, 0, 2.7, 0, DARK);
  } else {
    b.box(3.0, 1.6, 2.2, 0, 0.15, 0, 0xefe0c4);
    b.box(3.2, 0.2, 2.4, 0, 1.75, 0, 0xc9604f);
    b.box(0.9, 1.4, 0.9, 0, 1.95, 0, 0xefe0c4);
    b.cone(0.75, 0.8, 0, 3.3, 0, 0xc9604f, 4);
    b.cyl(0.28, 0.28, 0.06, 0, 2.4, 0.46, WHITE, 12);
  }
  return b.build();
}

function treeGeometry(): THREE.BufferGeometry {
  const b = new Builder();
  b.cyl(0.08, 0.1, 0.5, 0, 0, 0, 0x7a5a3e, 5);
  b.cone(0.45, 0.8, 0, 0.4, 0, 0x4f9a5a, 7);
  b.cone(0.34, 0.65, 0, 0.9, 0, 0x62ad68, 7);
  return b.build();
}


const smooth = (a: number, b: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - a) / (b - a)));
  return t * t * (3 - 2 * t);
};

/** Ground colour from height, slope and the shore: sand, lawn, forest, rock and snow. */
function groundColor(h: number, slope: number, x: number, z: number, out: THREE.Color): THREE.Color {
  const n = valueNoise(x * 0.09, z * 0.09, 5) * 0.14 - 0.07;
  out.set(0x9fd18b);
  if (h > 5) out.lerp(new THREE.Color(0xa9d98f), smooth(5, 6, h)); // the plateau lawn
  if (h < 0.35) out.lerp(new THREE.Color(0xe6d8a6), 1 - smooth(-0.5, 0.35, h)); // beach
  if (h < -0.4) out.set(0xcdbf94); // seabed
  const forest = smooth(6.5, 9, h) * (1 - smooth(24, 30, h));
  out.lerp(new THREE.Color(0x6aa56f), forest * 0.8);
  out.lerp(new THREE.Color(0x9b958a), smooth(0.45, 1.0, slope));
  out.lerp(new THREE.Color(0xf3f6f8), smooth(33, 44, h));
  out.offsetHSL(0, 0, n);
  return out;
}

function terrainGeometry(t: Terrain): THREE.BufferGeometry {
  const S = t.extent;
  const step = 3;
  const n = Math.ceil((2 * S) / step);
  const verts = n + 1;
  const pos = new Float32Array(verts * verts * 3);
  const colors = new Float32Array(verts * verts * 3);
  const c = new THREE.Color();
  for (let i = 0; i < verts; i++) {
    for (let j = 0; j < verts; j++) {
      const x = -S + i * step;
      const z = -S + j * step;
      const h = t.heightAt(x, z);
      const slope = Math.hypot(t.heightAt(x + 2, z) - t.heightAt(x - 2, z), t.heightAt(x, z + 2) - t.heightAt(x, z - 2)) / 4;
      const k = (i * verts + j) * 3;
      pos[k] = x;
      pos[k + 1] = h;
      pos[k + 2] = z;
      groundColor(h, slope, x, z, c);
      colors[k] = c.r;
      colors[k + 1] = c.g;
      colors[k + 2] = c.b;
    }
  }
  const index: number[] = [];
  for (let i = 0; i < n; i++) {
    for (let j = 0; j < n; j++) {
      const a = i * verts + j;
      const b = a + 1;
      const d = a + verts;
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

/** Deck and parapets for the stretches of a road that cross water. */
function bridges(line: readonly Pt[], t: Terrain, width: number): THREE.BufferGeometry | null {
  const b = new Builder();
  let any = false;
  for (let i = 1; i < line.length; i++) {
    const a = line[i - 1];
    const c = line[i];
    const len = Math.hypot(c.x - a.x, c.z - a.z);
    const k = Math.max(1, Math.ceil(len / 3));
    const ry = Math.atan2(c.x - a.x, c.z - a.z);
    for (let s = 0; s < k; s++) {
      const x = a.x + ((c.x - a.x) * (s + 0.5)) / k;
      const z = a.z + ((c.z - a.z) * (s + 0.5)) / k;
      if (t.heightAt(x, z) > -0.3) continue;
      any = true;
      const y = t.roadY(x, z);
      const piece = len / k + 0.1;
      b.box(width + 1.2, 0.6, piece, x, y - 0.55, z, 0xbfc0c4, ry);
      const ox = Math.cos(ry) * (width / 2 + 0.45);
      const oz = -Math.sin(ry) * (width / 2 + 0.45);
      b.box(0.3, 0.7, piece, x + ox, y + 0.05, z + oz, 0xe8e6e0, ry);
      b.box(0.3, 0.7, piece, x - ox, y + 0.05, z - oz, 0xe8e6e0, ry);
    }
  }
  return any ? b.build() : null;
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
    own(new THREE.MeshLambertMaterial({ color: 0x6cc3e0 })),
  );
  water.rotation.x = -Math.PI / 2;
  water.position.y = WATER_Y;
  group.add(water);

  // Connected streets: the outer arterial, curved district feeders and local neighbourhood loops.
  // Roads are built from the same connected polylines used by the traffic and transit systems.
  const streetDetails = new Builder();
  for (const road of layout.roads) {
    const isMajor = road.kind === "arterial" || road.kind === "exit";
    const roadColor = isMajor ? 0x454a52 : road.kind === "boulevard" ? 0x555b62 : STREET;
    const roadMesh = new THREE.Mesh(own(ribbon(road.path, road.width, 0.12, roadColor, t.roadY)), vcMat);
    roadMesh.receiveShadow = true;
    group.add(roadMesh);

    if (road.sidewalk) {
      for (const side of [-1, 1]) {
        const offset = side * (road.width / 2 + 1.05);
        const walk = offsetPath(road.path, offset);
        const sidewalk = new THREE.Mesh(own(ribbon(walk, 1.55, 0.15, 0xd7c9ad, t.roadY)), vcMat);
        sidewalk.receiveShadow = true;
        group.add(sidewalk);
        const curb = new THREE.Mesh(own(ribbon(offsetPath(road.path, offset - side * 0.76), 0.18, 0.19, 0xeee8d8, t.roadY)), vcMat);
        group.add(curb);
      }
    }

    const total = routeLength(road.path);
    if (road.width >= 6) {
      for (let d = 5; d < total - 6; d += isMajor ? 6.2 : 4.6) {
        const p = pointAlong(road.path, d);
        streetDetails.box(road.width >= 8 ? 1.25 : 0.86, 0.035, 0.12, p.x, t.roadY(p.x, p.z) + 0.2, p.z, 0xf0eee4, p.heading);
      }
    }

    // Lamps on the main avenues, spaced by real path distance rather than endpoint chords.
    if (road.kind === "arterial" || road.kind === "boulevard" || road.kind === "exit") {
      const spacing = road.kind === "arterial" ? 28 : 22;
      for (let d = spacing * 0.5; d < total; d += spacing) {
        const p = pointAlong(road.path, d);
        const nx = Math.cos(p.heading);
        const nz = -Math.sin(p.heading);
        for (const side of [-1, 1]) {
          const x = p.x + nx * side * (road.width / 2 + 2.05);
          const z = p.z + nz * side * (road.width / 2 + 2.05);
          const y = t.roadY(x, z);
          streetDetails.cyl(0.045, 0.055, 2.3, x, y + 0.08, z, DARK, 6);
          streetDetails.box(0.55, 0.07, 0.07, x + Math.sin(p.heading) * 0.2, y + 2.25, z + Math.cos(p.heading) * 0.2, DARK, p.heading);
          streetDetails.sphere(0.13, x + Math.sin(p.heading) * 0.4, y + 2.2, z + Math.cos(p.heading) * 0.4, 0xf7df9e);
        }
      }
    }

    const bridge = bridges(road.path, t, road.width);
    if (bridge) {
      const mesh = new THREE.Mesh(own(bridge), vcMat);
      mesh.castShadow = true;
      mesh.receiveShadow = true;
      group.add(mesh);
    }
  }
  if (layout.roads.length > 0) {
    const details = new THREE.Mesh(own(streetDetails.build()), vcMat);
    details.castShadow = true;
    details.receiveShadow = true;
    group.add(details);
  }

  // Parks and pocket gardens have their own landscape, paths, benches and pond.
  for (const park of layout.greenSpaces) {
    const baseY = t.heightAt(park.x, park.z) + 0.12;
    const lawn = new THREE.Mesh(
      own(new THREE.CircleGeometry(1, 40)),
      own(mat(park.kind === "city-park" ? 0x78ad69 : 0x8fbb76)),
    );
    lawn.rotation.x = -Math.PI / 2;
    lawn.rotation.z = park.rotationY;
    lawn.scale.set(park.radiusX, park.radiusZ, 1);
    lawn.position.set(park.x, baseY, park.z);
    lawn.receiveShadow = true;
    group.add(lawn);

    // A pale walking loop breaks up the lawn and links both sides of the park.
    const pathLine: Pt[] = [];
    for (let i = 0; i <= 32; i++) {
      const a = (i / 32) * Math.PI * 2;
      const x = Math.cos(a) * park.radiusX * 0.72;
      const z = Math.sin(a) * park.radiusZ * 0.72;
      const c = Math.cos(park.rotationY);
      const s = Math.sin(park.rotationY);
      pathLine.push({ x: park.x + x * c - z * s, z: park.z + x * s + z * c });
    }
    const parkPath = new THREE.Mesh(own(ribbon(pathLine, 1.25, 0.18, 0xdcccae, t.roadY)), vcMat);
    group.add(parkPath);

    if (park.pond) {
      const pond = new THREE.Mesh(
        own(new THREE.CircleGeometry(1, 40)),
        own(mat(0x54b8d6)),
      );
      pond.rotation.x = -Math.PI / 2;
      pond.scale.set(park.pond.radiusX, park.pond.radiusZ, 1);
      pond.position.set(park.pond.x, t.heightAt(park.pond.x, park.pond.z) + 0.17, park.pond.z);
      group.add(pond);
      const shore = new THREE.Mesh(
        own(new THREE.RingGeometry(0.96, 1.13, 40)),
        own(mat(0xcbbd9d)),
      );
      shore.rotation.x = -Math.PI / 2;
      shore.scale.set(park.pond.radiusX, park.pond.radiusZ, 1);
      shore.position.copy(pond.position);
      shore.position.y += 0.025;
      group.add(shore);
    }

    // Benches and low park lamps provide human-scale detail.
    const parkProps = new Builder();
    for (const side of [-1, 1]) {
      const x = park.x + Math.cos(park.rotationY) * side * park.radiusX * 0.48;
      const z = park.z + Math.sin(park.rotationY) * side * park.radiusX * 0.48;
      parkProps.box(2.1, 0.14, 0.58, x, baseY, z, 0x8c6847, park.rotationY);
      parkProps.box(2.1, 0.68, 0.12, x, baseY + 0.12, z - 0.22, 0x9d7953, park.rotationY);
      parkProps.cyl(0.04, 0.05, 1.8, x + 2.5, baseY, z, DARK, 6);
      parkProps.sphere(0.13, x + 2.5, baseY + 1.78, z, 0xf5dfa0);
    }
    const propMesh = new THREE.Mesh(own(parkProps.build()), vcMat);
    propMesh.castShadow = true;
    group.add(propMesh);
  }

  // Central square: paving, the market bell, and the four civic buildings.
  const plaza = new THREE.Mesh(own(new THREE.CylinderGeometry(PLAZA_RADIUS - 1, PLAZA_RADIUS - 1, 0.12, 40)), own(mat(0xe8dcc0)));
  plaza.position.y = 0.08;
  plaza.receiveShadow = true;
  group.add(plaza);

  const bellGeo = (() => {
    const b = new Builder();
    b.cyl(1.4, 1.6, 0.3, 0, 0, 0, 0xcfc7b4, 16);
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

  // Trees: parks inside town, forest on the hills. Deterministic, on free dry ground.
  const rng = seeded(0x51ee);
  const spots: Array<[number, number, number]> = [];
  const reach = t.extent * 0.85;
  const near = layout.filler.map((f) => [f.x, f.z] as const);
  let guard = 0;
  while (spots.length < maxTrees * 2 && guard++ < maxTrees * 60) {
    const a = rng() * Math.PI * 2;
    const r = Math.sqrt(rng()) * reach;
    const x = Math.cos(a) * r;
    const z = Math.sin(a) * r;
    const h = t.heightAt(x, z);
    if (h < 0.3 || h > 26) continue;
    if (r < PLAZA_RADIUS + 1) continue;
    if (layout.districts.some((d) => {
      const dx = x - d.cx;
      const dz = z - d.cz;
      return Math.hypot(dx, dz) < d.extent + 2 && inGrid(d, x, z);
    })) continue;
    if (layout.roads.some((road) => distToPolyline(x, z, road.path) < road.width / 2 + 2.2)) continue;
    if (near.some(([fx, fz]) => Math.hypot(fx - x, fz - z) < 4.2)) continue;
    spots.push([x, z, 0.7 + rng() * 0.9]);
  }
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
    const s = makeLabel(`${DISTRICT_LABEL[d.id]} · ${d.assetCount}`, { font: 34, bg: "rgba(45,51,64,0.82)", fg: "#fffaf0" });
    s.position.set(d.cx, t.heightAt(d.cx, d.cz) + 7, d.cz - d.halfH - 3);
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
    dispose() {
      disposables.forEach((d) => d.dispose());
      fillers.dispose();
      trees.dispose();
      districtLabels.forEach(disposeLabel);
    },
  };
}

function inGrid(d: { cx: number; cz: number; theta: number; halfW: number; halfH: number }, x: number, z: number): boolean {
  const c = Math.cos(d.theta);
  const s = Math.sin(d.theta);
  const lx = (x - d.cx) * c + (z - d.cz) * s;
  const lz = -(x - d.cx) * s + (z - d.cz) * c;
  return Math.abs(lx) < d.halfW + 2 && Math.abs(lz) < d.halfH + 2;
}

function distToSegment(px: number, pz: number, x1: number, z1: number, x2: number, z2: number): number {
  const dx = x2 - x1;
  const dz = z2 - z1;
  const l2 = dx * dx + dz * dz;
  const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - x1) * dx + (pz - z1) * dz) / l2));
  return Math.hypot(px - (x1 + t * dx), pz - (z1 + t * dz));
}
