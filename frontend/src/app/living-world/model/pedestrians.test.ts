import { describe, expect, it } from "vitest";
import { carriage, getCityGraph } from "./cityGraph";
import { DISTRICT_PROFESSION, PROFESSIONS, WalkerSim, buildWalkNet, crowdLevel, walkSample } from "./pedestrians";

const graph = getCityGraph();
const net = buildWalkNet(graph);

/** How far a point is inside the asphalt of the road it overlaps (0 or less = on the pavement or off the roads). */
function intrusion(x: number, z: number): number {
  let worst = 0;
  for (const e of graph.roads) {
    const a = graph.node(e.a);
    const b = graph.node(e.b);
    const dx = (b.x - a.x) / e.length;
    const dz = (b.z - a.z) / e.length;
    const t = (x - a.x) * dx + (z - a.z) * dz;
    if (t < 0 || t > e.length) continue;
    // Where the road narrows (a bridge head) the walkway steps across the end of the wider asphalt.
    const step = (n: string) => graph.node(n).kind === "bridgehead";
    if ((step(e.a) && t < 1.2) || (step(e.b) && e.length - t < 1.2)) continue;
    const lateral = Math.abs((x - a.x) * -dz + (z - a.z) * dx);
    worst = Math.max(worst, carriage(e) / 2 - lateral);
  }
  return worst;
}

describe("pavement network", () => {
  it("has a pavement on each side of every road half-edge, each leading on to another", () => {
    expect(net.pieces.length).toBe(graph.halfEdges.size * 2);
    for (const p of net.pieces) {
      expect(p.next).not.toBeNull();
      const end = p.pts[p.pts.length - 1];
      const start = p.next!.pts[0];
      expect(Math.hypot(end.x - start.x, end.z - start.z)).toBeLessThan(1e-6);
      expect(p.length).toBeGreaterThan(0);
    }
  });

  it("keeps clear of the asphalt along the whole circuit, corners included", () => {
    for (const p of net.pieces) {
      for (let s = 0; s <= p.length; s += 0.5) {
        const pt = walkSample(p, s);
        const inside = intrusion(pt.x, pt.z);
        if (inside > 0.1) throw new Error(`piece ${p.id} s=${s} at ${pt.x.toFixed(2)},${pt.z.toFixed(2)} inside=${inside.toFixed(2)} node=${p.node}`);
      }
    }
  });

  it("walks round a city block and comes back to where it started", () => {
    for (const start of net.pieces.slice(0, 40)) {
      let p = start;
      let n = 0;
      do {
        p = p.next!;
        n++;
      } while (p !== start && n < 400);
      expect(p).toBe(start);
    }
  });
});

describe("walkers", () => {
  it("are deterministic, stay on the pavements and keep moving", () => {
    const a = new WalkerSim(net, 5);
    const b = new WalkerSim(net, 5);
    a.populate(120);
    b.populate(120);
    for (let i = 0; i < 1200; i++) {
      a.step(1 / 30, 1);
      b.step(1 / 30, 1);
    }
    expect(a.walkers.map((w) => w.x.toFixed(4))).toEqual(b.walkers.map((w) => w.x.toFixed(4)));
    for (const w of a.walkers) {
      const inside = intrusion(w.x, w.z);
      if (inside > 0.1) throw new Error(`walker ${w.id} piece ${w.piece.id} at ${w.x.toFixed(2)},${w.z.toFixed(2)} lane=${w.lane.toFixed(2)} inside=${inside.toFixed(2)}`);
    }
    const before = a.walkers.map((w) => w.x + w.z);
    a.step(1, 1);
    expect(a.walkers.filter((w, i) => w.x + w.z !== before[i]).length).toBeGreaterThan(100);
  });

  it("show all four professions, led by the district's own", () => {
    const sim = new WalkerSim(net, 9);
    sim.populate(300);
    for (const prof of PROFESSIONS) expect(sim.walkers.filter((w) => w.profession === prof).length).toBeGreaterThan(15);
    expect(new Set(Object.values(DISTRICT_PROFESSION))).toEqual(new Set(PROFESSIONS));
  });

  it("thin out at night and swell at rush hour", () => {
    const sim = new WalkerSim(net, 3);
    sim.populate(200);
    const out = (h: number) => {
      sim.step(0.01, crowdLevel(h));
      return sim.walkers.filter((w) => w.moving).length;
    };
    expect(out(3)).toBeLessThan(out(8.5) * 0.4);
    expect(out(8.5)).toBeGreaterThan(150);
  });
});
