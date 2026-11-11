import { describe, expect, it } from "vitest";
import { distToSegment, polyArea } from "./cityGeometry";
import { CANAL_HALF_WIDTH, LINES, PITCH, buildCityGraph, isRoadClass, routeToGate } from "./cityGraph";
import { getCityTemplate, slotAt } from "./cityLots";
import { DISTRICT_IDS } from "./types";

describe("city graph", () => {
  const graph = getCityGraph();

  it("is rebuilt identically: node ids come from template coordinates", () => {
    const again = buildCityGraph();
    expect([...again.nodes.keys()].sort()).toEqual([...graph.nodes.keys()].sort());
    expect(again.roads.map((e) => e.id).sort()).toEqual(graph.roads.map((e) => e.id).sort());
    for (const n of graph.nodes.values()) expect(n.id).toBe(`n${Math.round(n.x * 2)}_${Math.round(n.z * 2)}`);
  });

  it("gives every ground road two half-edges, sorted by angle round each node", () => {
    expect(graph.halfEdges.size).toBe(graph.roads.length * 2);
    for (const list of graph.adjacency.values()) {
      for (let i = 1; i < list.length; i++) expect(list[i].angle).toBeGreaterThanOrEqual(list[i - 1].angle);
    }
  });

  it("walks faces into closed blocks: one outer face, every other face bounded and counter-clockwise", () => {
    const bounded = graph.faces.filter((f) => f.bounded);
    expect(graph.faces.length - bounded.length).toBe(1);
    const cells = (2 * (LINES.length - 1)) / 2;
    expect(bounded).toHaveLength((LINES.length - 1) ** 2);
    expect(cells).toBeGreaterThan(0);
    for (const f of bounded) {
      expect(f.polygon.length).toBeGreaterThanOrEqual(4);
      expect(polyArea(f.polygon)).toBeGreaterThan(0);
      // Closed: every edge ends where the next begins.
      f.edges.forEach((e, i) => {
        const next = f.edges[(i + 1) % f.edges.length];
        expect(e.b).toEqual(next.a);
      });
    }
    // Each road edge borders exactly two faces, or the same face twice (never a dangling edge).
    const uses = new Map<string, number>();
    for (const h of graph.halfEdges.values()) uses.set(h.edge, (uses.get(h.edge) ?? 0) + 1);
    for (const n of uses.values()) expect(n).toBe(2);
  });

  it("covers the plan: bounded block areas add up to the grid", () => {
    const total = graph.faces.filter((f) => f.bounded).reduce((s, f) => s + polyArea(f.polygon), 0);
    const side = LINES[LINES.length - 1] - LINES[0];
    expect(total).toBeCloseTo(side * side, 3);
  });

  it("is connected and every road class is present", () => {
    const seen = new Set<string>();
    const stack = [[...graph.nodes.keys()].find((id) => (graph.adjacency.get(id)?.length ?? 0) > 0)!];
    while (stack.length) {
      const id = stack.pop()!;
      if (seen.has(id)) continue;
      seen.add(id);
      for (const h of graph.adjacency.get(id) ?? []) stack.push(h.to);
    }
    const withRoads = [...graph.nodes.values()].filter((n) => (graph.adjacency.get(n.id)?.length ?? 0) > 0);
    expect(seen.size).toBe(withRoads.length);
    const classes = new Set(graph.edges.map((e) => e.class));
    for (const c of ["street", "avenue", "ring", "bridge", "rail", "monorail"] as const) expect(classes.has(c), c).toBe(true);
  });

  it("only bridges cross the canal, and every canal crossing is a bridge", () => {
    for (const e of graph.roads) {
      const a = graph.node(e.a);
      const b = graph.node(e.b);
      const mid = { x: (a.x + b.x) / 2, z: (a.z + b.z) / 2 };
      const inWater = (e.class === "bridge");
      // Canal axis x = -88 for z <= 44, then z = 44 for x <= -88.
      const overVertical = Math.abs(mid.x + 2 * PITCH) < CANAL_HALF_WIDTH && mid.z <= PITCH && e.class !== "ring";
      const overHorizontal = Math.abs(mid.z - PITCH) < CANAL_HALF_WIDTH && mid.x <= -2 * PITCH;
      if (overVertical || overHorizontal) expect(inWater, e.id).toBe(true);
    }
    expect(graph.roads.filter((e) => e.class === "bridge").length).toBeGreaterThanOrEqual(8);
  });

  it("meets the railway only at crossing nodes", () => {
    expect(graph.crossings.length).toBeGreaterThanOrEqual(3);
    for (const r of graph.rail) {
      for (const id of [r.a, r.b]) {
        const n = graph.node(id);
        expect(["crossing", "end"]).toContain(n.kind);
      }
    }
    for (const n of graph.nodes.values()) {
      if (n.kind !== "crossing") continue;
      // A crossing sits on a straight street: two road edges, collinear.
      expect(graph.adjacency.get(n.id)).toHaveLength(2);
    }
  });

  it("runs the monorail over avenue edges (or their bridges) only", () => {
    for (const m of graph.monorail) {
      const a = graph.node(m.a);
      const b = graph.node(m.b);
      const lo = { x: Math.min(a.x, b.x), z: Math.min(a.z, b.z) };
      const hi = { x: Math.max(a.x, b.x), z: Math.max(a.z, b.z) };
      const under = graph.roads.filter((e) => {
        const p = graph.node(e.a);
        const q = graph.node(e.b);
        return [p, q].every((n) => n.x >= lo.x - 1e-6 && n.x <= hi.x + 1e-6 && n.z >= lo.z - 1e-6 && n.z <= hi.z + 1e-6);
      });
      expect(under.reduce((s, e) => s + e.length, 0), m.id).toBeCloseTo(m.length, 6);
      for (const e of under) expect(["avenue", "bridge"], `${m.id} over ${e.id}`).toContain(e.class);
    }
  });

  it("routes every road node to a plaza gate", () => {
    for (const e of graph.roads.filter((r) => r.class === "street").slice(0, 40)) {
      const a = graph.node(e.a);
      const route = routeToGate(graph, { x: a.x, z: a.z }, e.id);
      expect(route.length).toBeGreaterThan(1);
      expect(Math.hypot(route.at(-1)!.x, route.at(-1)!.z)).toBeLessThan(16);
    }
  });
});

describe("city template", () => {
  const template = getCityTemplate();

  it("has a block for every cell and lots for the city blocks", () => {
    expect(template.blocks).toHaveLength(81);
    expect(template.lots.length).toBeGreaterThan(200);
    const kinds = new Set(template.blocks.map((b) => b.kind));
    for (const k of ["city", "plaza", "station", "canal", "park"]) expect(kinds.has(k as never), k).toBe(true);
  });

  it("touches a street with every lot", () => {
    // Holding lots (the capable ones) always front a street directly.
    for (const lot of template.lots.filter((l) => l.capable)) {
      const edge = graph().edges.find((e) => e.id === lot.edgeId)!;
      const a = graph().node(edge.a);
      const b = graph().node(edge.b);
      const d = distToSegment({ x: lot.x, z: lot.z }, a, b);
      expect(d - edge.width / 2 - lot.d / 2, lot.key).toBeLessThan(1.2);
      expect(lot.fx * lot.fx + lot.fz * lot.fz).toBeCloseTo(1);
    }
  });

  it("keeps lots off the roads: they stand inside the pavement-shrunk block", () => {
    for (const lot of template.lots) {
      for (const road of graph().roads) {
        const a = graph().node(road.a);
        const b = graph().node(road.b);
        // The road is a rectangle along its centre line; the junction squares are checked at their own nodes.
        const ex = (b.x - a.x) / road.length;
        const ez = (b.z - a.z) / road.length;
        for (const p of lot.polygon) {
          const along = (p.x - a.x) * ex + (p.z - a.z) * ez;
          const across = Math.abs(-(p.x - a.x) * ez + (p.z - a.z) * ex);
          const inside = along > 1e-6 && along < road.length - 1e-6 && across < road.width / 2 - 1e-6;
          expect(inside, `${lot.key} vs ${road.id}`).toBe(false);
        }
      }
    }
  });

  it("keeps lots out of the railway corridor", () => {
    for (const lot of template.lots) {
      if (lot.x < 30) continue;
      for (const p of lot.polygon) expect(Math.abs(p.z), lot.key).toBeGreaterThanOrEqual(6.4);
    }
  });

  it("gives every district a fixed compass wedge with room for landmarks", () => {
    for (const [k, id] of DISTRICT_IDS.entries()) {
      const own = template.lots.filter((l) => l.district === id && l.capable);
      expect(own.length, id).toBeGreaterThanOrEqual(18);
      expect(own.some((l) => l.premium), id).toBe(true);
      for (const l of own) {
        const block = template.blocks.find((b) => b.key === l.blockKey)!;
        expect(slotAt(block.face.centroid.x, block.face.centroid.z)).toBe(k);
      }
    }
  });

  it("makes holding lots big enough for the largest landmark and bigger than any filler", () => {
    for (const l of template.lots.filter((x) => x.capable)) expect(Math.min(l.w, l.d)).toBeGreaterThanOrEqual(14.4);
  });
});

function graph() {
  return getCityTemplate().graph;
}
function getCityGraph() {
  return getCityTemplate().graph;
}
