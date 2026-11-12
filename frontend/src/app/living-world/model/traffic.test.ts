import { describe, expect, it } from "vitest";
import { distToSegment } from "./cityGeometry";
import { carriage, getCityGraph } from "./cityGraph";
import {
  FIXED_DT,
  TrafficSim,
  buildLaneNetwork,
  offsetPolyline,
  sampleAt,
  signalGreen,
  trafficLevel,
  type Piece,
  type Vehicle,
} from "./traffic";

const graph = getCityGraph();
const net = buildLaneNetwork(graph);

const run = (sim: TrafficSim, seconds: number, each?: () => void) => {
  const steps = Math.round(seconds / FIXED_DT);
  for (let i = 0; i < steps; i++) {
    sim.advance(FIXED_DT);
    each?.();
  }
};

/** Separating-axis test on two oriented rectangles (slightly shrunk). */
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

function firstOverlap(sim: TrafficSim): [Vehicle, Vehicle] | null {
  const vs = sim.vehicles.filter((v) => v.scale > 0);
  for (let i = 0; i < vs.length; i++) {
    for (let j = i + 1; j < vs.length; j++) {
      if (Math.hypot(vs[i].x - vs[j].x, vs[i].z - vs[j].z) < 7 && overlaps(vs[i], vs[j])) return [vs[i], vs[j]];
    }
  }
  return null;
}

describe("lane network", () => {
  it("has right-hand lanes: lanes of a half-edge sit to its right, clear of the median", () => {
    const h = graph.halfEdges.get([...graph.halfEdges.keys()].find((k) => k.endsWith(">") && graph.halfEdges.get(k)!.angle === 0)!)!;
    const a = graph.node(h.from);
    for (const lane of net.lanesOf.get(h.id)!) {
      // Heading +x: the right-hand side is +z.
      expect(lane.pts[0].z - a.z).toBeGreaterThan(0.5);
    }
    const twin = net.lanesOf.get(h.twin)!;
    for (const lane of twin) expect(lane.pts[0].z - a.z).toBeLessThan(-0.5);
  });

  it("gives every road half-edge lanes inside its carriageway, with the avenue median left clear", () => {
    for (const e of graph.roads) {
      for (const dir of [">", "<"]) {
        const lanes = net.lanesOf.get(e.id + dir)!;
        expect(lanes.length).toBe(Math.max(1, Math.floor(e.lanes / 2)));
        const a = graph.node(e.a);
        const b = graph.node(e.b);
        for (const lane of lanes) {
          for (const p of lane.pts) {
            const d = distToSegment(p, a, b);
            expect(d).toBeLessThanOrEqual(carriage(e) / 2 + 1e-6);
            expect(d).toBeGreaterThanOrEqual(e.median / 2 + 0.3);
          }
        }
      }
    }
  });

  it("connects every lane to the next: no dead ends, continuous endpoints, no U-turns", () => {
    for (const lane of net.lanes) {
      expect(lane.turns.length).toBeGreaterThan(0);
      for (const t of lane.turns) {
        const end = lane.pts[lane.pts.length - 1];
        expect(Math.hypot(t.pts[0].x - end.x, t.pts[0].z - end.z)).toBeLessThan(1e-6);
        const to = t.to!;
        expect(Math.hypot(t.pts[t.pts.length - 1].x - to.pts[0].x, t.pts[t.pts.length - 1].z - to.pts[0].z)).toBeLessThan(1e-6);
        const h = graph.halfEdges.get(lane.half)!;
        const o = graph.halfEdges.get(to.half)!;
        expect(o.to).not.toBe(h.from);
      }
    }
  });

  it("marks crossing movements as conflicts, parallel lanes as free", () => {
    const junction = [...graph.nodes.values()].find((n) => n.kind === "junction" && (graph.adjacency.get(n.id)?.length ?? 0) === 4)!;
    const here = net.turns.filter((t) => t.node === junction.id);
    const straight = here.filter((t) => t.movement === "S");
    // Perpendicular straights cross; the symmetrical one keeps its own lane group.
    const ns = straight.filter((t) => t.from!.axis === 1);
    const ew = straight.filter((t) => t.from!.axis === 0);
    expect(ns.length).toBeGreaterThan(0);
    for (const a of ns) for (const b of ew) expect(a.conflicts.has(b.id)).toBe(true);
    for (const a of ns) for (const b of ns) if (a !== b && a.from !== b.from && a.to !== b.to) expect(a.conflicts.has(b.id)).toBe(false);
  });

  it("alternates signals by axis with an all-red gap", () => {
    const node = [...graph.nodes.values()].find((n) => n.kind === "junction")!;
    let sawX = false;
    let sawZ = false;
    let both = false;
    let neither = false;
    for (let t = 0; t < 40; t += 0.1) {
      const x = signalGreen(net, node.id, 0, t);
      const z = signalGreen(net, node.id, 1, t);
      sawX ||= x;
      sawZ ||= z;
      both ||= x && z;
      neither ||= !x && !z;
    }
    expect(sawX && sawZ && neither).toBe(true);
    expect(both).toBe(false);
  });
});

describe("traffic simulation", () => {
  it("is deterministic for a seed and different for another", () => {
    const a = new TrafficSim(net, { seed: 7 });
    const b = new TrafficSim(net, { seed: 7 });
    const c = new TrafficSim(net, { seed: 8 });
    for (const s of [a, b, c]) {
      s.warm(40);
      run(s, 12);
    }
    const key = (s: TrafficSim) => s.vehicles.map((v) => `${v.id}:${v.x.toFixed(4)},${v.z.toFixed(4)}`).join("|");
    expect(key(a)).toBe(key(b));
    expect(key(a)).not.toBe(key(c));
  });

  it.each([3, 21, 77])("never lets two vehicles overlap, in lanes or in junctions (seed %i)", (seed) => {
    const sim = new TrafficSim(net, { seed });
    sim.warm(220);
    let checked = 0;
    let bad: [Vehicle, Vehicle] | null = null;
    run(sim, 90, () => {
      if (!bad && ++checked % 6 === 0) bad = firstOverlap(sim);
    });
    expect(bad).toBeNull();
    expect(sim.count).toBeGreaterThan(150);
  });

  it("keeps traffic flowing: few stuck vehicles after a minute and a half", () => {
    const sim = new TrafficSim(net, { seed: 5 });
    sim.warm(200);
    run(sim, 90);
    const slow = sim.vehicles.filter((v) => v.stuckT > 25).length;
    expect(slow / sim.count).toBeLessThan(0.08);
    const moving = sim.vehicles.filter((v) => v.v > 1).length;
    expect(moving / sim.count).toBeGreaterThan(0.35);
  });

  it("keeps every vehicle on the road", () => {
    const sim = new TrafficSim(net, { seed: 9 });
    sim.warm(160);
    // Segments and half-widths are resolved once; the scan runs every 6th step like the sibling tests.
    const roads = graph.roads.map((e) => ({ a: graph.node(e.a), b: graph.node(e.b), half: carriage(e) / 2 }));
    let checked = 0;
    let worst = 0;
    run(sim, 60, () => {
      if (++checked % 6 !== 0) return;
      for (const v of sim.vehicles) {
        let near = Infinity;
        for (const r of roads) {
          const d = distToSegment({ x: v.x, z: v.z }, r.a, r.b) - r.half;
          if (d < near) near = d;
        }
        if (near > worst) worst = near;
      }
    });
    expect(worst).toBeLessThan(1.6);
  });

  const laneEnding = (nodeId: string, axis: 0 | 1): Piece =>
    net.lanes.find((l) => l.node === nodeId && l.axis === axis && l.control === "signal" && l.length > 22 && l.lane === 0)!;

  it("stops at a red light and goes on green", () => {
    const node = [...graph.nodes.values()].find((n) => n.kind === "junction" && (graph.adjacency.get(n.id)?.length ?? 0) === 4)!;
    const lane = laneEnding(node.id, 0);
    let green = false;
    const sim = new TrafficSim(net, { seed: 1, signal: () => green });
    const v = sim.spawn(lane, lane.stopAt - 20, "sedan", 6)!;
    run(sim, 12);
    expect(v.piece).toBe(lane);
    expect(v.s).toBeLessThan(lane.stopAt);
    expect(v.v).toBeLessThan(0.2);
    green = true;
    run(sim, 8);
    expect(v.piece).not.toBe(lane);
  });

  it("queues behind the leader at a red light without touching it", () => {
    const node = [...graph.nodes.values()].find((n) => n.kind === "junction" && (graph.adjacency.get(n.id)?.length ?? 0) === 4)!;
    const lane = laneEnding(node.id, 1);
    const sim = new TrafficSim(net, { seed: 2, signal: () => false });
    const cars = [0, 1, 2].map((i) => sim.spawn(lane, lane.stopAt - 8 - i * 9, i === 1 ? "bus" : "sedan", 5)!);
    run(sim, 14);
    expect(cars.every((c) => c.v < 0.2)).toBe(true);
    for (let i = 1; i < cars.length; i++) {
      expect(cars[i - 1].s - cars[i - 1].length - cars[i].s).toBeGreaterThan(0.2);
    }
    expect(cars[0].s).toBeLessThan(lane.stopAt);
  });

  it("holds traffic at a level crossing while a train is due, then lets it go", () => {
    const lane = net.lanes.find((l) => l.control === "crossing" && l.length > 14)!;
    let closed = true;
    const sim = new TrafficSim(net, { seed: 4, crossingClosed: () => closed });
    const v = sim.spawn(lane, lane.stopAt - 10, "van", 6)!;
    run(sim, 12);
    expect(v.piece).toBe(lane);
    expect(v.v).toBeLessThan(0.2);
    expect(v.s).toBeLessThan(lane.stopAt);
    closed = false;
    run(sim, 8);
    expect(v.piece).not.toBe(lane);
  });

  it("never admits two conflicting movements at once", () => {
    const sim = new TrafficSim(net, { seed: 11 });
    sim.warm(240);
    run(sim, 60, () => {
      const inside = sim.vehicles.filter((v) => v.piece.kind === "turn" && v.piece.node && v.piece.length > 4);
      for (let i = 0; i < inside.length; i++) {
        for (let j = i + 1; j < inside.length; j++) {
          const a = inside[i].piece;
          const b = inside[j].piece;
          if (a.node === b.node && a !== b) expect(a.conflicts.has(b.id)).toBe(false);
        }
      }
    });
  });

  it("follows the target density up and down", () => {
    const sim = new TrafficSim(net, { seed: 6 });
    sim.setTarget(60);
    run(sim, 20);
    expect(sim.active).toBe(60);
    sim.setTarget(25);
    run(sim, 40);
    expect(sim.active).toBe(25);
    expect(sim.count).toBeLessThan(40);
  });

  it("stops for an external actor in its way", () => {
    const lane = net.lanes.find((l) => l.length > 30)!;
    const sim = new TrafficSim(net, { seed: 12 });
    const v = sim.spawn(lane, 8, "sedan", 5)!;
    const f = sampleAt(lane, 22);
    sim.setExternals([{ x: f.x, z: f.z, heading: f.heading, length: 2.6, speed: 0 }]);
    run(sim, 8);
    expect(v.s).toBeLessThan(22 - 1.3);
    expect(v.v).toBeLessThan(0.3);
  });
});

describe("helpers", () => {
  it("traffic level peaks at the rush hours and drops at night", () => {
    expect(trafficLevel(8.3)).toBeGreaterThan(0.8);
    expect(trafficLevel(18)).toBeGreaterThan(0.8);
    expect(trafficLevel(3)).toBeLessThan(0.4);
    expect(trafficLevel(27)).toBeCloseTo(trafficLevel(3), 6);
  });

  it("offsets a polyline to the right of travel", () => {
    const out = offsetPolyline([{ x: 0, z: 0 }, { x: 10, z: 0 }, { x: 20, z: 0 }], 2);
    for (const p of out) expect(p.z).toBeCloseTo(2, 6);
    const corner = offsetPolyline([{ x: 0, z: 0 }, { x: 10, z: 0 }, { x: 10, z: 10 }], 1);
    expect(corner[1].x).toBeCloseTo(9, 6);
    expect(corner[1].z).toBeCloseTo(1, 6);
  });
});
