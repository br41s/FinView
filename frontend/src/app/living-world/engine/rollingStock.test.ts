import { describe, expect, it } from "vitest";
import { PROFESSIONS } from "../model/pedestrians";
import { VEHICLE_KINDS } from "../model/traffic";
import { personGeometry } from "./people";
import { vehicleGeometry } from "./vehicles";

const tris = (g: { getAttribute(n: string): { count: number } }) => g.getAttribute("position").count / 3;

describe("moving things stay cheap (they are drawn hundreds of times, and again in the shadow and AO passes)", () => {
  it.each(VEHICLE_KINDS)("%s fits its triangle budget and carries the shader attributes", (kind) => {
    const g = vehicleGeometry(kind);
    expect(tris(g)).toBeLessThan(kind === "bus" ? 900 : 560);
    for (const a of ["position", "normal", "color", "aKind", "aLimb"]) expect(g.getAttribute(a)).toBeDefined();
  });

  it.each(PROFESSIONS)("%s fits its triangle budget", (prof) => {
    const g = personGeometry(prof);
    expect(tris(g)).toBeLessThan(600);
    expect(g.getAttribute("aLimb")).toBeDefined();
  });
});
