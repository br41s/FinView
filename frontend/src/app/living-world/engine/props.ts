import * as THREE from "three";
import { DISTRICT_LABEL } from "../model/archetypes";
import { PLAZA_RADIUS, type CivicKind, type WorldLayout } from "../model/townLayout";
import { seeded } from "../model/rng";
import type { DistrictId } from "../model/types";
import { Builder } from "./buildingFactory";

/** Ground, streets, plaza, civic buildings, trees and text labels: the static stage. */

const DISTRICT_TINT: Record<DistrictId, number> = {
  retail: 0xa6d68f,
  tech: 0x9ad3b0,
  industry: 0xc3c78a,
  finance: 0xa9cf9c,
  health: 0xaedbc6,
  funds: 0xb4d3a0,
  treasury: 0xc9d79a,
};

const STREET = 0xb7b3a6;
const WHITE = 0xf4f1ea;
const DARK = 0x4a4f5a;

export interface Town {
  group: THREE.Group;
  trees: THREE.InstancedMesh;
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

export function buildTown(layout: WorldLayout, maxTrees: number): Town {
  const group = new THREE.Group();
  const disposables: Array<{ dispose(): void }> = [];
  const own = <T extends { dispose(): void }>(x: T) => (disposables.push(x), x);

  const R = layout.radius + 26;

  // The island: green top, earth sides, water all round.
  const islandGeo = own(new THREE.CylinderGeometry(R, R * 0.94, 3, 64));
  const island = new THREE.Mesh(islandGeo, [own(mat(0x8b6f55)), own(mat(0x9fd18b)), own(mat(0x6b5440))]);
  island.position.y = -1.5;
  island.receiveShadow = true;
  group.add(island);

  const waterGeo = own(new THREE.CircleGeometry(R * 4, 48));
  const water = new THREE.Mesh(waterGeo, own(new THREE.MeshLambertMaterial({ color: 0x86cdea })));
  water.rotation.x = -Math.PI / 2;
  water.position.y = -2.2;
  group.add(water);

  // District grass patches (a tint per district) and the paved pad under the lots.
  const padMat = own(mat(STREET));
  for (const d of layout.districts) {
    const patch = new THREE.Mesh(
      own(new THREE.BoxGeometry(d.halfW * 2 + 7, 0.06, d.halfH * 2 + 7)),
      own(mat(DISTRICT_TINT[d.id])),
    );
    patch.position.set(d.cx, 0.03, d.cz);
    patch.receiveShadow = true;
    group.add(patch);
    const pad = new THREE.Mesh(own(new THREE.BoxGeometry(d.halfW * 2, 0.1, d.halfH * 2)), padMat);
    pad.position.set(d.cx, 0.06, d.cz);
    pad.receiveShadow = true;
    group.add(pad);
  }

  // Boulevards.
  const roadMat = own(mat(STREET));
  for (const r of layout.roads) {
    const len = Math.hypot(r.x2 - r.x1, r.z2 - r.z1);
    const road = new THREE.Mesh(own(new THREE.BoxGeometry(4, 0.08, len)), roadMat);
    road.position.set((r.x1 + r.x2) / 2, 0.07, (r.z1 + r.z2) / 2);
    road.rotation.y = Math.atan2(r.x2 - r.x1, r.z2 - r.z1);
    road.receiveShadow = true;
    group.add(road);
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
  const bell = new THREE.Mesh(bellGeo, own(new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true })));
  bell.position.y = 0.14;
  bell.castShadow = true;
  group.add(bell);

  const civic = new Map<CivicKind, THREE.Vector3>();
  const civicMat = own(new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true }));
  for (const c of layout.civic) {
    const geo = own(civicGeometry(c.kind));
    const m = new THREE.Mesh(geo, civicMat);
    m.position.set(c.x, 0.14, c.z);
    m.rotation.y = Math.atan2(-c.x, -c.z);
    m.castShadow = true;
    m.receiveShadow = true;
    group.add(m);
    civic.set(c.kind, new THREE.Vector3(c.x, 0, c.z));
  }

  // Trees, scattered deterministically on free ground.
  const rng = seeded(0x51ee);
  const spots: Array<[number, number, number]> = [];
  let guard = 0;
  while (spots.length < maxTrees && guard++ < maxTrees * 40) {
    const a = rng() * Math.PI * 2;
    const r = Math.sqrt(rng()) * (R - 3);
    const x = Math.cos(a) * r;
    const z = Math.sin(a) * r;
    if (Math.hypot(x, z) < PLAZA_RADIUS + 1) continue;
    if (layout.districts.some((d) => Math.abs(x - d.cx) < d.halfW + 2 && Math.abs(z - d.cz) < d.halfH + 2)) continue;
    if (layout.roads.some((rd) => distToSegment(x, z, rd.x1, rd.z1, rd.x2, rd.z2) < 3.2)) continue;
    spots.push([x, z, 0.7 + rng() * 0.9]);
  }
  const treeGeo = own(treeGeometry());
  const trees = new THREE.InstancedMesh(treeGeo, own(new THREE.MeshLambertMaterial({ vertexColors: true, flatShading: true })), Math.max(1, spots.length));
  const m4 = new THREE.Matrix4();
  spots.forEach(([x, z, s], i) => {
    m4.compose(new THREE.Vector3(x, 0, z), new THREE.Quaternion(), new THREE.Vector3(s, s, s));
    trees.setMatrixAt(i, m4);
  });
  trees.count = spots.length;
  trees.castShadow = true;
  group.add(trees);

  // District names, visible from far away.
  const districtLabels: THREE.Sprite[] = [];
  for (const d of layout.districts) {
    const s = makeLabel(`${DISTRICT_LABEL[d.id]} · ${d.assetCount}`, { font: 34, bg: "rgba(45,51,64,0.82)", fg: "#fffaf0" });
    s.position.set(d.cx, 4, d.cz - d.halfH - 3);
    s.userData.district = d.id;
    group.add(s);
    districtLabels.push(s);
  }

  return {
    group,
    trees,
    districtLabels,
    civic,
    setTreeCount(n) {
      trees.count = Math.min(n, spots.length);
    },
    dispose() {
      disposables.forEach((d) => d.dispose());
      trees.dispose();
      districtLabels.forEach(disposeLabel);
    },
  };
}

function distToSegment(px: number, pz: number, x1: number, z1: number, x2: number, z2: number): number {
  const dx = x2 - x1;
  const dz = z2 - z1;
  const l2 = dx * dx + dz * dz;
  const t = l2 === 0 ? 0 : Math.max(0, Math.min(1, ((px - x1) * dx + (pz - z1) * dz) / l2));
  return Math.hypot(px - (x1 + t * dx), pz - (z1 + t * dz));
}
