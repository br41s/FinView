import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { TIERS, type Tier } from "../model/scale";
import { HEIGHT_RANGE, towerSpec } from "../model/towerSpec";
import { ARCHETYPES } from "../model/types";
import { NOMINAL, composeSite } from "./buildingFactory";

/** Geometry-level checks: budgets, sanity of the attributes and the winding of every face. */
const BUDGET: Record<Tier, number> = { outpost: 1500, small: 2400, campus: 3200, major: 4000 };
const ids = ["ES0113211835", "US0378331005", "ZZ1000007919", "FR0000120271"];

function geometryOf(a: (typeof ARCHETYPES)[number], id: string, tier: Tier) {
  const spec = towerSpec(a, id, tier);
  return { spec, ...composeSite(spec, NOMINAL[tier], false) };
}

describe("composeSite", () => {
  it("stays within the triangle budget of every tier", () => {
    const over: string[] = [];
    for (const a of ARCHETYPES) {
      for (const t of TIERS) {
        for (const id of ids) {
          const { triangles } = geometryOf(a, id, t);
          if (triangles > BUDGET[t]) over.push(`${a} ${t} ${id}: ${triangles}`);
        }
      }
    }
    expect(over).toEqual([]);
  });

  it("reaches the height of its tier, inside its plot", () => {
    const bad: string[] = [];
    for (const a of ARCHETYPES) {
      for (const t of TIERS) {
        for (const id of ids) {
          const { geometry, top } = geometryOf(a, id, t);
          // The tallest element reaches (almost) the spec's height: no holding is a low box.
          if (top < HEIGHT_RANGE[t][0] * 0.92) bad.push(`${a} ${t} ${id}: top ${top.toFixed(2)}`);
          geometry.computeBoundingBox();
          const bb = geometry.boundingBox!;
          const half = NOMINAL[t] * 0.62;
          const out = Math.max(-bb.min.x, bb.max.x, -bb.min.z, bb.max.z);
          if (out > half) bad.push(`${a} ${t} ${id}: reaches ${out.toFixed(2)} > ${half.toFixed(2)}`);
          if (!Array.from(geometry.getAttribute("position").array).every(Number.isFinite)) bad.push(`${a} ${t} ${id}: NaN`);
        }
      }
    }
    expect(bad).toEqual([]);
  });

  it("carries the attributes the facade shader reads, on every vertex", () => {
    const { geometry } = geometryOf("tech", ids[0], "major");
    const n = geometry.getAttribute("position").count;
    for (const name of ["normal", "color", "aKind", "aArc"]) expect(geometry.getAttribute(name).count, name).toBe(n);
    const kinds = new Set(Array.from(geometry.getAttribute("aKind").array));
    expect(kinds.has(1) || kinds.has(3)).toBe(true);
  });

  it("faces outwards: the winding agrees with the normals on (almost) every triangle", () => {
    for (const a of ARCHETYPES) {
      for (const t of ["small", "major"] as const) {
        const { geometry } = geometryOf(a, ids[1], t);
        const g = geometry.index ? geometry.toNonIndexed() : geometry;
        const p = g.getAttribute("position");
        const nr = g.getAttribute("normal");
        const A = new THREE.Vector3();
        const B = new THREE.Vector3();
        const C = new THREE.Vector3();
        const N = new THREE.Vector3();
        let bad = 0;
        let total = 0;
        for (let i = 0; i < p.count; i += 3) {
          A.fromBufferAttribute(p, i);
          B.fromBufferAttribute(p, i + 1);
          C.fromBufferAttribute(p, i + 2);
          const face = B.clone().sub(A).cross(C.clone().sub(A));
          if (face.lengthSq() < 1e-10) continue;
          N.fromBufferAttribute(nr, i).add(new THREE.Vector3().fromBufferAttribute(nr, i + 1)).add(new THREE.Vector3().fromBufferAttribute(nr, i + 2));
          total++;
          if (face.dot(N) < 0) bad++;
        }
        expect(bad / total, `${a} ${t}: ${bad}/${total} inverted`).toBeLessThan(0.02);
      }
    }
  });

  it("is deterministic and unique per ISIN", () => {
    const sig = (id: string) => {
      const { geometry } = geometryOf("banking", id, "major");
      const p = geometry.getAttribute("position");
      return `${p.count}:${p.getY(p.count - 1).toFixed(3)}:${p.getX(7).toFixed(3)}`;
    };
    expect(sig(ids[0])).toBe(sig(ids[0]));
    expect(new Set(ids.map(sig)).size).toBe(ids.length);
  });
});
