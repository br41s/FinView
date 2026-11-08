import { describe, expect, it } from "vitest";
import {
  createDirector,
  enqueue,
  replay,
  setConfig,
  setPaused,
  tick,
  type DirectorState,
} from "./director";
import { demoAssets, generateDemoEvents } from "./fixtures";
import type { Severity, WorldEvent } from "./types";

const NOW = Date.parse("2026-11-08T12:00:00Z");
const assets = demoAssets();

function ev(id: string, assetId: string | null, severity: Severity = "normal", score = 1, ms = 10_000): WorldEvent {
  return {
    ...generateDemoEvents(assets, { nowMs: NOW, seed: 1, count: 1, spanMs: 0 })[0],
    id,
    assetId,
    severity,
    priorityScore: score,
    dedupeKey: `k:${id}`,
    displayDurationMs: ms,
  };
}

const run = (s: DirectorState, ms: number, step = 100) => {
  let state = s;
  const started: string[] = [];
  const ended: string[] = [];
  for (let t = 0; t < ms; t += step) {
    const r = tick(state, step);
    state = r.state;
    started.push(...r.started.map((p) => p.id));
    ended.push(...r.ended.map((p) => p.id));
  }
  return { state, started, ended };
};

describe("director queue", () => {
  it("acts out a burst of 30 events without exceeding the concurrency caps", () => {
    const burst = generateDemoEvents(assets, { nowMs: NOW, seed: 9, count: 30, spanMs: 0, idPrefix: "b" });
    let s = enqueue(createDirector(), burst);
    let peakNormal = 0;
    let peakTotal = 0;
    // 30 events, 3 normal slots, 12-26 s each: well under 5 minutes of scene time.
    for (let i = 0; i < 3_000; i++) {
      s = tick(s, 100).state;
      peakTotal = Math.max(peakTotal, s.active.length);
      peakNormal = Math.max(peakNormal, s.active.filter((p) => p.severity === "normal").length);
    }
    expect(peakNormal).toBeLessThanOrEqual(3);
    // Critical may exceed maxTotal, so bound by the cap plus the criticals in the burst.
    const criticals = burst.filter((e) => e.severity === "critical").length;
    expect(peakTotal).toBeLessThanOrEqual(6 + criticals);
    expect(s.queue).toHaveLength(0);
    expect(s.active).toHaveLength(0);
  });

  it("starts the highest priority first, ties broken by time then id", () => {
    const s = enqueue(createDirector({ maxNormal: 1, maxTotal: 1 }), [
      ev("a", "A1", "normal", 1),
      ev("b", "A2", "normal", 5),
      ev("c", "A3", "normal", 5),
    ]);
    const { started } = tick(s, 100);
    expect(started.map((p) => p.events[0].id)).toEqual(["b"]);
  });

  it("is deterministic: the same inputs produce the same performances", () => {
    const burst = generateDemoEvents(assets, { nowMs: NOW, seed: 4, count: 25, spanMs: 0, idPrefix: "d" });
    const a = run(enqueue(createDirector(), burst), 20_000);
    const b = run(enqueue(createDirector(), [...burst].reverse()), 20_000);
    expect(b.started).toEqual(a.started);
  });

  it("acts an observation once even if it is delivered twice (polling)", () => {
    const e = ev("x", "A1");
    let s = enqueue(createDirector(), [e]);
    s = enqueue(s, [e]);
    expect(s.queue).toHaveLength(1);
    const { state } = run(s, 30_000);
    s = enqueue(state, [e]);
    expect(s.queue).toHaveLength(0);
  });
});

describe("coalescing", () => {
  it("merges events about one company into one scene and keeps every card", () => {
    const s = enqueue(createDirector(), [ev("1", "A1", "normal", 1), ev("2", "A1", "important", 3), ev("3", "A2")]);
    const r = tick(s, 100);
    expect(r.state.active).toHaveLength(2);
    const a1 = r.state.active.find((p) => p.assetId === "A1")!;
    expect(a1.events.map((e) => e.id).sort()).toEqual(["1", "2"]);
    expect(a1.severity).toBe("important");
    expect(a1.priority).toBe(3);
  });

  it("extends a live scene when a later event of the same company arrives", () => {
    let s = enqueue(createDirector(), [ev("1", "A1", "normal", 1, 5_000)]);
    s = tick(s, 1_000).state;
    s = enqueue(s, [ev("2", "A1", "normal", 1, 9_000)]);
    const r = tick(s, 1_000);
    expect(r.started).toHaveLength(0);
    expect(r.merged).toHaveLength(1);
    expect(r.state.active[0].endsAt).toBe(2_000 + 9_000);
  });

  it("never coalesces shared town events that belong to no company", () => {
    const s = enqueue(createDirector(), [ev("1", null), ev("2", null)]);
    expect(tick(s, 100).state.active).toHaveLength(2);
  });
});

describe("pause, quiet and camera", () => {
  it("freezes everything while paused", () => {
    let s = enqueue(createDirector(), [ev("1", "A1")]);
    s = setPaused(s, true);
    const r = tick(s, 5_000);
    expect(r.state.clock).toBe(0);
    expect(r.started).toHaveLength(0);
    expect(tick(setPaused(r.state, false), 100).started).toHaveLength(1);
  });

  it("quiet mode acts nothing out but remembers the observations", () => {
    let s = setConfig(createDirector(), { quiet: true });
    const e = ev("1", "A1");
    s = enqueue(s, [e]);
    expect(s.queue).toHaveLength(0);
    s = setConfig(s, { quiet: false });
    s = enqueue(s, [e]);
    expect(s.queue).toHaveLength(0);
  });

  it("only asks the camera to move for a critical event, and only when auto-focus is on", () => {
    const events = [ev("n", "A1", "normal"), ev("c", "A2", "critical", 9)];
    const off = tick(enqueue(createDirector(), events), 100).state.active;
    expect(off.some((p) => p.requestFocus)).toBe(false);
    const on = tick(enqueue(createDirector({ autoFocus: true }), events), 100).state.active;
    expect(on.filter((p) => p.requestFocus).map((p) => p.severity)).toEqual(["critical"]);
  });
});

describe("replay", () => {
  it("re-enacts an event without altering its facts, bypassing dedupe and quiet", () => {
    const e = ev("1", "A1");
    let s = enqueue(createDirector({ quiet: true }), [e]);
    const before = JSON.stringify(e);
    const r = replay(s, e);
    s = r.state;
    expect(r.started[0].replay).toBe(true);
    expect(r.started[0].events[0]).toBe(e);
    expect(JSON.stringify(e)).toBe(before);
  });

  it("merges into a live scene of the same company instead of duplicating it", () => {
    let s = enqueue(createDirector(), [ev("1", "A1")]);
    s = tick(s, 100).state;
    const r = replay(s, ev("2", "A1"));
    expect(r.state.active).toHaveLength(1);
    expect(r.merged).toHaveLength(1);
  });
});
