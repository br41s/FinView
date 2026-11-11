import { expect, it } from "vitest";
import { getCityGraph } from "./cityGraph";
import { FIXED_DT, TrafficSim, buildLaneNetwork, type Vehicle } from "./traffic";

// Scratch diagnostics (agents may not delete files); safe to remove.
function overlaps(a: Vehicle, b: Vehicle): boolean {
  const rect = (v: Vehicle) => {
    const hx = Math.sin(v.heading);
    const hz = Math.cos(v.heading);
    return { c: { x: v.x, z: v.z }, u: { x: hx, z: hz }, w: { x: -hz, z: hx }, hl: v.length / 2 - 0.05, hw: v.width / 2 - 0.05 };
  };
  const A = rect(a);
  const B = rect(b);
  const d = { x: B.c.x - A.c.x, z: B.c.z - A.c.z };
  for (const axis of [A.u, A.w, B.u, B.w]) {
    const dist = Math.abs(d.x * axis.x + d.z * axis.z);
    const ra = A.hl * Math.abs(A.u.x * axis.x + A.u.z * axis.z) + A.hw * Math.abs(A.w.x * axis.x + A.w.z * axis.z);
    const rb = B.hl * Math.abs(B.u.x * axis.x + B.u.z * axis.z) + B.hw * Math.abs(B.w.x * axis.x + B.w.z * axis.z);
    if (dist > ra + rb) return false;
  }
  return true;
}

it("diagnoses overlaps", () => {
  const net = buildLaneNetwork(getCityGraph());
  const sim = new TrafficSim(net, { seed: 3 });
  sim.warm(220);
  const out: string[] = [];
  for (let i = 0; i < 2700 && out.length < 4; i++) {
    sim.advance(FIXED_DT);
    if (i % 6) continue;
    const vs = sim.vehicles.filter((v) => v.scale > 0);
    for (let a = 0; a < vs.length; a++) {
      for (let b = a + 1; b < vs.length; b++) {
        if (Math.hypot(vs[a].x - vs[b].x, vs[a].z - vs[b].z) < 8 && overlaps(vs[a], vs[b])) {
          const f = (v: Vehicle) => `${v.kind}#${v.id} ${v.piece.kind}${v.piece.id}${v.piece.kind === "turn" ? v.piece.movement : ""} s=${v.s.toFixed(1)} len=${v.length.toFixed(1)} v=${v.v.toFixed(1)} box=${v.box?.id ?? "-"} trail=${v.trail.map((t) => t.kind[0] + t.id).join(",")} node=${v.piece.node}`;
          out.push(`t=${sim.time.toFixed(1)}\n  ${f(vs[a])}\n  ${f(vs[b])}`);
        }
      }
    }
  }
  expect(out.join("\n")).toBe("");
});
