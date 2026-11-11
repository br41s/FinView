import { describe, expect, it } from "vitest";
import { createLoop, createShuttle, crossingClosed, legAt, legTime } from "./trainSchedule";

const K = { vmax: 10, acc: 2 };

describe("leg kinematics", () => {
  it("covers exactly the leg, from rest to rest, with a trapezoid or a triangle", () => {
    for (const len of [4, 25, 120, 400]) {
      const T = legTime(len, K);
      expect(legAt(len, K, 0)).toEqual({ dist: 0, speed: 0 });
      expect(legAt(len, K, T).dist).toBeCloseTo(len, 6);
      expect(legAt(len, K, T).speed).toBeCloseTo(0, 6);
      let prev = 0;
      for (let t = 0; t <= T; t += T / 200) {
        const m = legAt(len, K, t);
        expect(m.dist).toBeGreaterThanOrEqual(prev - 1e-9);
        expect(m.speed).toBeLessThanOrEqual(K.vmax + 1e-9);
        prev = m.dist;
      }
    }
  });
});

describe("ground shuttle", () => {
  const train = createShuttle(229, 21, K, 8);
  it("stays on the track, dwells at both ends with the doors open, and repeats", () => {
    let dwelling = 0;
    for (let t = 0; t < train.period * 2; t += 0.25) {
      const s = train.at(t);
      expect(s.pos).toBeGreaterThanOrEqual(21 / 2 - 1e-6);
      expect(s.pos).toBeLessThanOrEqual(229 - 21 / 2 + 1e-6);
      if (s.dwelling) {
        dwelling++;
        expect(s.speed).toBe(0);
      }
      expect(train.at(t + train.period).pos).toBeCloseTo(s.pos, 6);
    }
    expect(dwelling).toBeGreaterThan(0);
    const mid = train.at(4);
    expect(mid.dwelling).toBe(true);
    expect(mid.doors).toBeGreaterThan(0.9);
  });
  it("moves smoothly: no jump between samples", () => {
    let prev = train.at(0).pos;
    for (let t = 0.05; t < train.period; t += 0.05) {
      const p = train.at(t).pos;
      expect(Math.abs(p - prev)).toBeLessThan(K.vmax * 0.05 + 1e-6);
      prev = p;
    }
  });
  it("closes a crossing before the train arrives and opens it after the tail has gone", () => {
    const crossing = 110;
    let closedFirst = -1;
    let reachedAt = -1;
    let openedAt = -1;
    for (let t = 8; t < train.period / 2 + 8; t += 0.1) {
      const closed = crossingClosed(train, crossing, t);
      const s = train.at(t);
      if (closed && closedFirst < 0) closedFirst = t;
      if (reachedAt < 0 && s.pos + 21 / 2 >= crossing) reachedAt = t;
      if (closedFirst >= 0 && !closed && openedAt < 0) openedAt = t;
    }
    expect(closedFirst).toBeGreaterThan(0);
    expect(reachedAt - closedFirst).toBeGreaterThan(3);
    expect(openedAt).toBeGreaterThan(reachedAt);
    // Far from any train the barrier is up.
    expect(crossingClosed(train, 110, 8.5)).toBe(false);
  });
});

describe("monorail loop", () => {
  const loop = createLoop(880, [100, 300, 410, 700], 10, K, 6);
  it("stops at every station and nowhere else, then goes around", () => {
    const seen = new Set<number>();
    let wasMoving = false;
    for (let t = 0; t < loop.period * 1.5; t += 0.1) {
      const s = loop.at(t);
      if (s.dwelling) {
        seen.add(Math.round(s.pos));
        expect(s.speed).toBe(0);
      } else wasMoving = true;
    }
    expect([...seen].sort((a, b) => a - b)).toEqual([100, 300, 410, 700]);
    expect(wasMoving).toBe(true);
  });
  it("runs a second train half a period behind without catching up", () => {
    for (let t = 0; t < loop.period * 2; t += 0.5) {
      const a = loop.at(t).pos;
      const b = loop.at(t, loop.period / 2).pos;
      const gap = (((b - a) % 880) + 880) % 880;
      expect(Math.min(gap, 880 - gap)).toBeGreaterThan(25);
    }
  });
});
