import { describe, expect, it } from "vitest";

import {
  BONUS_POINTS,
  COIN_LIFE_MS,
  REINVEST_EVERY,
  SLOT_COUNT,
  STARTING_LIVES,
  bearCentre,
  buildField,
  createGame,
  groundAt,
  plantTop,
  resizeGame,
  step,
  tap,
  type GameEvent,
  type GameState,
} from "./sim";

/** A fixed "random": every plant and bear behaves the same on every run. */
const half = () => 0.5;
const FRAME = 16;

function play(): GameState {
  return createGame(buildField(800, 400), "play", half);
}

/** Run frames until `done` says stop; returns every event seen. */
function run(state: GameState, done: (s: GameState, e: GameEvent[]) => boolean, maxMs = 120_000) {
  const seen: GameEvent[] = [];
  for (let t = 0; t < maxMs; t += FRAME) {
    const events = step(state, FRAME, half);
    seen.push(...events);
    if (done(state, events)) return seen;
  }
  throw new Error("condition never met");
}

const plantCount = (s: GameState) => s.plants.filter(Boolean).length;

describe("the field", () => {
  it("spreads the plots evenly inside the canvas", () => {
    const field = buildField(800, 400);
    expect(field.slots).toHaveLength(SLOT_COUNT);
    expect(field.slots[0]).toBeGreaterThan(0);
    expect(field.slots[SLOT_COUNT - 1]).toBeLessThan(800);
  });

  it("is a hill: the middle is higher than the edges", () => {
    const field = buildField(800, 400);
    // Canvas y grows downwards, so higher ground is a smaller y.
    expect(groundAt(field, 400)).toBeLessThan(groundAt(field, 0));
    expect(groundAt(field, 0)).toBeCloseTo(groundAt(field, 800));
  });

  it("scales with the canvas, so a phone and a monitor play alike", () => {
    expect(buildField(1600, 800).unit).toBeCloseTo(buildField(800, 400).unit * 2);
  });
});

describe("a new game", () => {
  it("starts with two plants, three lives and no score", () => {
    const state = play();
    expect(plantCount(state)).toBe(2);
    expect(state.lives).toBe(STARTING_LIVES);
    expect(state.score).toBe(0);
    expect(state.over).toBe(false);
  });
});

describe("dividends", () => {
  it("a plant pays a coin at its flower", () => {
    const state = play();
    const events = run(state, (_, e) => e.some((x) => x.type === "coin"));
    const coin = events.find((x) => x.type === "coin");
    expect(coin).toBeDefined();
    expect(state.coins.length).toBeGreaterThan(0);
  });

  it("a coin rises after it is paid", () => {
    const state = play();
    run(state, (s) => s.coins.length > 0);
    const before = state.coins[0].y;
    step(state, 200, half);
    expect(state.coins[0].y).toBeLessThan(before);
  });

  it("an uncaught coin is lost, and costs nothing but the coin", () => {
    const state = createGame(buildField(800, 400), "play", half);
    state.bearInMs = Number.POSITIVE_INFINITY; // keep the bears out of this test
    const events = run(state, (_, e) => e.some((x) => x.type === "miss"));
    expect(events.some((x) => x.type === "miss")).toBe(true);
    expect(state.score).toBe(0);
    expect(state.lives).toBe(STARTING_LIVES);
  });

  it("tapping a coin catches it and scores one", () => {
    const state = play();
    run(state, (s) => s.coins.length > 0);
    const coin = state.coins[0];
    const events = tap(state, { x: coin.x, y: coin.y }, half);
    expect(events.map((e) => e.type)).toContain("collect");
    expect(state.score).toBe(1);
    expect(state.coins.find((c) => c.id === coin.id)).toBeUndefined();
  });

  it("a tap on empty sky does nothing", () => {
    const state = play();
    expect(tap(state, { x: 5, y: 5 }, half)).toEqual([]);
    expect(state.score).toBe(0);
  });
});

/** Catch `n` coins as they appear, with no bears around. */
function catchCoins(state: GameState, n: number): GameEvent[] {
  state.bearInMs = Number.POSITIVE_INFINITY;
  const seen: GameEvent[] = [];
  let caught = 0;
  for (let t = 0; t < 600_000 && caught < n; t += FRAME) {
    step(state, FRAME, half);
    if (state.coins.length === 0) continue;
    const coin = state.coins[0];
    seen.push(...tap(state, { x: coin.x, y: coin.y }, half));
    caught += 1;
  }
  expect(caught).toBe(n);
  return seen;
}

describe("reinvesting", () => {
  it("every third coin plants a seedling while there is bare soil", () => {
    const state = play();
    const events = catchCoins(state, REINVEST_EVERY);
    expect(events.filter((e) => e.type === "plant")).toHaveLength(1);
    expect(plantCount(state)).toBe(3);
  });

  it("fills the plots from the middle outwards", () => {
    const state = play();
    const events = catchCoins(state, REINVEST_EVERY);
    const planted = events.find((e) => e.type === "plant");
    expect(planted).toEqual({ type: "plant", slot: 3 });
  });

  it("grows the smallest plant once every plot is taken", () => {
    const state = play();
    const events = catchCoins(state, REINVEST_EVERY * (SLOT_COUNT - 2 + 1));
    expect(plantCount(state)).toBe(SLOT_COUNT);
    expect(events.filter((e) => e.type === "grow")).toHaveLength(1);
    expect(state.plants.filter((p) => p?.level === 2)).toHaveLength(1);
  });

  it("pays a bonus when there is nothing left to grow", () => {
    const state = play();
    state.plants = state.plants.map(() => ({ level: 3, coinInMs: 1000, ageMs: 0 }));
    const events = catchCoins(state, REINVEST_EVERY);
    expect(events.some((e) => e.type === "bonus")).toBe(true);
    expect(state.score).toBe(REINVEST_EVERY + BONUS_POINTS);
  });

  it("a bonus does not shift when the next reinvestment comes", () => {
    const state = play();
    state.plants = state.plants.map(() => ({ level: 3, coinInMs: 1000, ageMs: 0 }));
    const events = catchCoins(state, REINVEST_EVERY * 2);
    expect(events.filter((e) => e.type === "bonus")).toHaveLength(2);
  });

  it("a bigger plant pays sooner: that is the compounding", () => {
    const paysIn = (level: 1 | 3) => {
      const state = play();
      state.bearInMs = Number.POSITIVE_INFINITY;
      state.plants = state.plants.map((_, i) => (i === 3 ? { level, coinInMs: 0, ageMs: 0 } : null));
      step(state, FRAME, half); // pays at once and schedules the next coin
      return state.plants[3]!.coinInMs;
    };
    expect(paysIn(3)).toBeLessThan(paysIn(1));
  });
});

describe("bears", () => {
  it("a bear walks in from outside the field", () => {
    const state = play();
    run(state, (s) => s.bears.length > 0);
    const bear = state.bears[0];
    expect(bear.state).toBe("walking");
    expect(bear.x < 0 || bear.x > state.field.width).toBe(true);
  });

  it("a bear that reaches a plant takes a bite and a life", () => {
    const state = play();
    const events = run(state, (_, e) => e.some((x) => x.type === "bite"));
    expect(events.some((x) => x.type === "bite")).toBe(true);
    expect(state.lives).toBe(STARTING_LIVES - 1);
    expect(plantCount(state)).toBe(1); // a seedling does not survive a bite
  });

  it("a bitten grown plant shrinks instead of dying", () => {
    const state = play();
    state.plants = state.plants.map((p) => (p ? { ...p, level: 3 } : null));
    run(state, (_, e) => e.some((x) => x.type === "bite"));
    expect(plantCount(state)).toBe(2);
    expect(state.plants.filter((p) => p?.level === 2)).toHaveLength(1);
  });

  it("tapping a bear sends it away before it bites", () => {
    const state = play();
    run(state, (s) => s.bears.some((b) => b.x > 0 && b.x < s.field.width));
    const bear = state.bears[0];
    const events = tap(state, bearCentre(state.field, bear), half);
    expect(events.map((e) => e.type)).toEqual(["shoo"]);
    expect(bear.state).toBe("fleeing");
    run(state, (s) => !s.bears.some((b) => b.id === bear.id));
    expect(state.lives).toBe(STARTING_LIVES);
  });

  it("a bear under the finger is shooed before a coin is caught", () => {
    const state = play();
    run(state, (s) => s.bears.some((b) => b.x > 0 && b.x < s.field.width));
    const at = bearCentre(state.field, state.bears[0]);
    state.coins.push({ id: 999, originX: at.x, x: at.x, y: at.y, ageMs: 0 });
    const events = tap(state, at, half);
    expect(events.map((e) => e.type)).toEqual(["shoo"]);
    expect(state.score).toBe(0);
  });

  it("a fleeing bear cannot be tapped again", () => {
    const state = play();
    run(state, (s) => s.bears.some((b) => b.x > 0 && b.x < s.field.width));
    const bear = state.bears[0];
    tap(state, bearCentre(state.field, bear), half);
    expect(tap(state, bearCentre(state.field, bear), half)).toEqual([]);
  });

  it("a bear whose plant was eaten goes for the next one", () => {
    const state = play();
    run(state, (s) => s.bears.length > 0);
    const bear = state.bears[0];
    const first = bear.targetSlot;
    state.plants[first] = null;
    step(state, FRAME, half);
    expect(bear.targetSlot).not.toBe(first);
    expect(state.plants[bear.targetSlot]).not.toBeNull();
  });
});

describe("the end", () => {
  it("is over when the lives run out", () => {
    const state = play();
    state.plants = state.plants.map(() => ({ level: 3, coinInMs: 5000, ageMs: 0 }));
    const events = run(state, (s) => s.over, 600_000);
    expect(state.lives).toBe(0);
    expect(events.filter((e) => e.type === "over")).toHaveLength(1);
  });

  it("is over when the last plant is eaten, whatever lives remain", () => {
    const state = play();
    state.lives = 10;
    run(state, (s) => s.over, 600_000);
    expect(plantCount(state)).toBe(0);
    expect(state.lives).toBeGreaterThan(0);
  });

  it("nothing moves and nothing scores after the end", () => {
    const state = play();
    run(state, (s) => s.over, 600_000);
    const score = state.score;
    expect(step(state, 1000, half)).toEqual([]);
    expect(tap(state, { x: 400, y: 200 }, half)).toEqual([]);
    expect(state.score).toBe(score);
  });
});

describe("the demo that plays by itself", () => {
  const demo = () => createGame(buildField(800, 400), "demo", half);

  it("never sends a bear and never ends", () => {
    const state = demo();
    for (let t = 0; t < 180_000; t += FRAME) step(state, FRAME, half);
    expect(state.bears).toHaveLength(0);
    expect(state.over).toBe(false);
    expect(state.lives).toBe(STARTING_LIVES);
  });

  it("collects its own coins, so the garden grows", () => {
    const state = demo();
    const start = plantCount(state);
    run(state, (s) => plantCount(s) > start);
    expect(state.score).toBeGreaterThan(0);
  });

  it("ignores the pointer", () => {
    const state = demo();
    run(state, (s) => s.coins.length > 0);
    const coin = state.coins[0];
    expect(tap(state, { x: coin.x, y: coin.y }, half)).toEqual([]);
  });

  it("starts over once the garden is full, instead of sitting still", () => {
    const state = demo();
    run(state, (s) => s.plants.every((p) => p?.level === 3), 3_600_000);
    run(state, (s) => plantCount(s) < SLOT_COUNT, 60_000);
    expect(plantCount(state)).toBe(3);
  });
});

describe("resizing", () => {
  it("keeps coins and bears in proportion when the canvas changes size", () => {
    const state = play();
    run(state, (s) => s.coins.length > 0 && s.bears.length > 0);
    const coinShare = state.coins[0].x / state.field.width;
    const bearShare = state.bears[0].x / state.field.width;
    resizeGame(state, buildField(400, 200));
    expect(state.coins[0].x / 400).toBeCloseTo(coinShare);
    expect(state.bears[0].x / 400).toBeCloseTo(bearShare);
    expect(state.field.width).toBe(400);
  });
});

describe("coins appear where the flower is", () => {
  it("a taller plant pays higher up", () => {
    const field = buildField(800, 400);
    expect(plantTop(field, 3, 3).y).toBeLessThan(plantTop(field, 3, 1).y);
  });

  it("a coin lives long enough to be caught", () => {
    expect(COIN_LIFE_MS).toBeGreaterThanOrEqual(2500);
  });
});
