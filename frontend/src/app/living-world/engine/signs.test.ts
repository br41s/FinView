import * as THREE from "three";
import { describe, expect, it } from "vitest";
import { NOMINAL, signGeometry } from "./buildingFactory";

describe("company sign", () => {
  it.each(Object.entries(NOMINAL))("hangs the sign on the main tower of a %s building", (_tier, nominal) => {
    const mainTop = 30;
    const mainRadius = 4;
    const g = signGeometry(nominal, mainTop, mainRadius);
    // The facade plate plus two vertical blades, four vertices each.
    expect(g.getAttribute("position").count).toBe(3 * 4);

    const pos = g.getAttribute("position");
    const y = (i: number) => pos.getY(i);
    const all = Array.from({ length: pos.count }, (_, i) => i);
    // Nothing sits on the roof any more: no vertex rises above the main tower.
    expect(Math.max(...all.map(y))).toBeLessThanOrEqual(mainTop);
    // Both blades hang on the tower, between the street and the roof.
    for (let i = 4; i < pos.count; i++) {
      expect(y(i)).toBeGreaterThan(0);
      expect(y(i)).toBeLessThan(mainTop);
    }
    // Front blade on the street face, side blade on the right face, clear of the wall.
    for (let i = 4; i < 8; i++) expect(pos.getZ(i)).toBeCloseTo(mainRadius + 0.06, 5);
    for (let i = 8; i < 12; i++) expect(pos.getX(i)).toBeCloseTo(mainRadius + 0.06, 5);
  });

  it("rotates the texture so the text reads bottom-to-top", () => {
    const g = signGeometry(NOMINAL.major, 30, 4);
    const pos = g.getAttribute("position");
    const uv = g.getAttribute("uv");
    // The plane's top-left corner (first blade vertex) is its highest point.
    let top = 4;
    for (let i = 5; i < 8; i++) if (pos.getY(i) > pos.getY(top)) top = i;
    // Unrotated, that corner would carry the texture's top-left uv (0, 1).
    expect([uv.getX(top), uv.getY(top)]).not.toEqual([0, 1]);

    // Every blade vertex differs from the unrotated PlaneGeometry uvs.
    const plain = new THREE.PlaneGeometry(1, 1);
    const plainUv = plain.getAttribute("uv");
    for (let i = 0; i < 4; i++) {
      expect([uv.getX(4 + i), uv.getY(4 + i)]).not.toEqual([plainUv.getX(i), plainUv.getY(i)]);
    }
    plain.dispose();
    g.dispose();
  });

  it("keeps the blades within 70 % of a short tower", () => {
    const g = signGeometry(NOMINAL.major, 5, 4);
    const pos = g.getAttribute("position");
    const ys = Array.from({ length: 4 }, (_, i) => pos.getY(4 + i));
    expect(Math.max(...ys) - Math.min(...ys)).toBeLessThanOrEqual(5 * 0.7 + 1e-6);
    g.dispose();
  });
});
