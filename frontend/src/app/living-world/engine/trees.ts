import * as THREE from "three";
import { seeded } from "../model/rng";
import type { Terrain } from "../model/terrain";
import { Builder } from "./buildingFactory";

/**
 * Low-poly trees as two InstancedMeshes (round broadleaf and conifer) sharing one swaying material.
 * Each instance gets its own colour multiplier (hue and brightness vary tree to tree) and its own
 * sway phase taken from its position. Spots are `[x, z, scale]`, already in priority order, so a
 * lower quality tier simply draws the first N.
 */
export interface Trees {
  /** Broadleaf trees. */
  round: THREE.InstancedMesh;
  /** Conifers (the hills and a share of the lowland). */
  pines: THREE.InstancedMesh;
  /** Draw only the first `n` spots, split across both meshes. */
  setCount(n: number): void;
  update(dtMs: number): void;
  dispose(): void;
}

function roundGeometry(): THREE.BufferGeometry {
  const b = new Builder();
  b.cyl(0.07, 0.11, 0.62, 0, 0, 0, 0x7a5a3e, 5);
  b.ico(0.5, 0, 0.78, 0, 0x4fb04a);
  b.ico(0.36, 0.2, 1.1, 0.06, 0x6cc25a);
  b.ico(0.32, -0.18, 1.0, -0.1, 0x5bb752);
  return b.build();
}

function pineGeometry(): THREE.BufferGeometry {
  const b = new Builder();
  b.cyl(0.06, 0.09, 0.4, 0, 0, 0, 0x6f5238, 5);
  b.cone(0.52, 0.8, 0, 0.3, 0, 0x2f8f58, 7);
  b.cone(0.4, 0.7, 0, 0.78, 0, 0x3aa263, 7);
  b.cone(0.26, 0.6, 0, 1.22, 0, 0x4bb572, 7);
  return b.build();
}

export function createTrees(spots: ReadonlyArray<readonly [number, number, number]>, terrain: Terrain, maxTrees: number): Trees {
  const timeUniform = { value: 0 };
  const material = new THREE.MeshLambertMaterial({ vertexColors: true });
  material.onBeforeCompile = (shader) => {
    shader.uniforms.uTreeTime = timeUniform;
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nuniform float uTreeTime;")
      .replace(
        "#include <begin_vertex>",
        /* glsl */ `#include <begin_vertex>
        float treePhase = instanceMatrix[3].x * 0.37 + instanceMatrix[3].z * 0.23;
        float treeH = clamp(position.y / 1.6, 0.0, 1.0);
        float treeSway = sin(uTreeTime * 1.6 + treePhase) * 0.05 + sin(uTreeTime * 2.9 + treePhase * 1.7) * 0.022;
        transformed.x += treeSway * treeH * treeH;
        transformed.z += treeSway * 0.55 * treeH * treeH;`,
      );
  };
  material.customProgramCacheKey = () => "tree-sway";

  const roundGeo = roundGeometry();
  const pineGeo = pineGeometry();
  const rng = seeded(0x7ee5);

  const roundIdx: number[] = [];
  const pineIdx: number[] = [];
  spots.forEach(([x, z], i) => {
    const h = terrain.heightAt(x, z);
    const pine = h > 8.5 || rng() < 0.22;
    (pine ? pineIdx : roundIdx).push(i);
  });

  const m4 = new THREE.Matrix4();
  const q = new THREE.Quaternion();
  const up = new THREE.Vector3(0, 1, 0);
  const pos = new THREE.Vector3();
  const sc = new THREE.Vector3();
  const col = new THREE.Color();

  const fill = (geo: THREE.BufferGeometry, idx: number[], pine: boolean) => {
    const mesh = new THREE.InstancedMesh(geo, material, Math.max(1, idx.length));
    idx.forEach((spot, k) => {
      const [x, z, s] = spots[spot];
      q.setFromAxisAngle(up, rng() * Math.PI * 2);
      pos.set(x, terrain.heightAt(x, z), z);
      sc.set(s, s * (0.9 + rng() * 0.3), s);
      m4.compose(pos, q, sc);
      mesh.setMatrixAt(k, m4);
      // Multiplier on the vertex greens: pines lean blue-green, broadleaf swings to lime and gold.
      const warm = rng();
      const v = 0.82 + rng() * 0.36;
      if (pine) col.setRGB(v * (0.85 + warm * 0.2), v * (0.95 + warm * 0.1), v * (0.9 + (1 - warm) * 0.2));
      else col.setRGB(v * (0.8 + warm * 0.5), v * (0.95 + warm * 0.12), v * (0.7 + (1 - warm) * 0.3));
      mesh.setColorAt(k, col);
    });
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true;
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.computeBoundingSphere();
    return mesh;
  };

  const round = fill(roundGeo, roundIdx, false);
  const pines = fill(pineGeo, pineIdx, true);
  round.userData.spots = roundIdx;
  pines.userData.spots = pineIdx;

  const setCount = (n: number) => {
    const upTo = Math.min(n, spots.length);
    const take = (idx: number[]) => {
      let c = 0;
      while (c < idx.length && idx[c] < upTo) c++;
      return c;
    };
    round.count = take(roundIdx);
    pines.count = take(pineIdx);
  };
  setCount(maxTrees);

  return {
    round,
    pines,
    setCount,
    update(dtMs) {
      timeUniform.value += dtMs / 1000;
    },
    dispose() {
      roundGeo.dispose();
      pineGeo.dispose();
      material.dispose();
      round.dispose();
      pines.dispose();
    },
  };
}
