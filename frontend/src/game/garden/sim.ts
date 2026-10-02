/**
 * The dividend garden's rules, with no canvas and no DOM in them.
 *
 * Plants sit in a row of plots and pay a coin every few seconds. The coin
 * floats up and is lost unless the player catches it; every third coin caught
 * is reinvested as a new plant or a bigger one, so a tended garden pays faster
 * and faster. Bears walk in from the sides, and a bear that reaches a plant
 * takes a bite out of it and costs a life. Tapping a bear sends it away.
 *
 * Everything here is plain data and arithmetic so it can be tested without a
 * browser. `components/GardenGame` owns the canvas, the pointer and the clock,
 * and calls `step` once per frame.
 *
 * The same simulation runs the animation shown before anyone plays: in `demo`
 * mode no bear comes, every coin is collected on its own, and a full garden
 * starts over, so the garden simply grows by itself.
 *
 * Distances are in CSS pixels of the canvas. `Field.unit` is the scale every
 * size and speed derives from, so the game feels the same on a phone and on a
 * wide monitor.
 */

import { bearsPerMinute } from './difficulty';

export interface Point {
  x: number;
  y: number;
}

export interface Field {
  readonly width: number;
  readonly height: number;
  /** One hundredth of the field's geometric mean side. */
  readonly unit: number;
  /** x of each plot, left to right. */
  readonly slots: readonly number[];
}

export type Level = 1 | 2 | 3;

export interface Plant {
  level: Level;
  /** Milliseconds until it pays its next coin. */
  coinInMs: number;
  /** Milliseconds since it was planted or last grew; drives the pop-in. */
  ageMs: number;
}

export interface Coin {
  readonly id: number;
  /** x it was paid at; the drawn x sways around it. */
  readonly originX: number;
  x: number;
  y: number;
  ageMs: number;
}

export type BearState = 'walking' | 'eating' | 'fleeing';

export interface Bear {
  readonly id: number;
  x: number;
  /** 1 walks right, -1 walks left. */
  dir: 1 | -1;
  state: BearState;
  targetSlot: number;
  eatMs: number;
}

export type GameMode = 'demo' | 'play';

export type GameEvent =
  | { type: 'coin'; at: Point }
  | { type: 'collect'; at: Point }
  | { type: 'miss'; at: Point }
  | { type: 'plant'; slot: number }
  | { type: 'grow'; slot: number }
  | { type: 'bonus'; at: Point }
  | { type: 'shoo'; at: Point }
  | { type: 'bite'; slot: number }
  | { type: 'over' };

export interface GameState {
  field: Field;
  readonly mode: GameMode;
  /** One entry per plot; null is bare soil. */
  plants: (Plant | null)[];
  coins: Coin[];
  bears: Bear[];
  score: number;
  /** Coins caught, which is what reinvestment counts; the score also holds bonuses. */
  caught: number;
  lives: number;
  elapsedMs: number;
  /** Milliseconds until the next bear walks in. */
  bearInMs: number;
  /** Demo only: how long the garden has been full. */
  fullMs: number;
  over: boolean;
  nextId: number;
}

export type Random = () => number;

export const SLOT_COUNT = 7;
export const STARTING_LIVES = 3;
/** Coins caught per reinvestment. */
export const REINVEST_EVERY = 3;
export const BONUS_POINTS = 2;
export const COIN_LIFE_MS = 3600;
/** Share of a coin's life after which the demo collects it. */
const DEMO_COLLECT_AT = 0.55;
/** A higher level pays sooner: that is the compounding. */
const COIN_INTERVAL_MS: Record<Level, number> = { 1: 4200, 2: 3000, 3: 2100 };
const BEAR_EAT_MS = 900;
const DEMO_FULL_MS = 5000;
const FIRST_BEAR_MS = 3500;

const COIN_RISE_UNITS_PER_S = 7;
const BEAR_SPEED_UNITS_PER_S = 9;
const BEAR_FLEE_UNITS_PER_S = 26;
const COIN_TAP_UNITS = 5;
const BEAR_TAP_UNITS = 6.5;

const PLAY_START_SLOTS = [2, 4];
const DEMO_START_SLOTS = [1, 3, 5];

export function buildField(width: number, height: number): Field {
  const unit = Math.sqrt(Math.max(1, width) * Math.max(1, height)) / 100;
  const slots = Array.from({ length: SLOT_COUNT }, (_, i) => (width * (i + 1)) / (SLOT_COUNT + 1));
  return { width, height, unit, slots };
}

/** Height of the ground at `x`: a low hill, highest in the middle. */
export function groundAt(field: Field, x: number): number {
  const t = Math.min(1, Math.max(0, x / Math.max(1, field.width)));
  return field.height * 0.8 - Math.sin(t * Math.PI) * field.height * 0.07;
}

/** How tall a plant of this level stands, in pixels. */
export function plantHeight(field: Field, level: Level): number {
  return field.unit * (5 + level * 4.5);
}

/** Where a plant's flower is, which is where its coins appear. */
export function plantTop(field: Field, slot: number, level: Level): Point {
  const x = field.slots[slot];
  return { x, y: groundAt(field, x) - plantHeight(field, level) };
}

function newPlant(random: Random): Plant {
  return { level: 1, coinInMs: COIN_INTERVAL_MS[1] * (0.4 + 0.6 * random()), ageMs: 0 };
}

export function createGame(field: Field, mode: GameMode, random: Random = Math.random): GameState {
  const plants: (Plant | null)[] = Array.from({ length: SLOT_COUNT }, () => null);
  for (const slot of mode === 'demo' ? DEMO_START_SLOTS : PLAY_START_SLOTS) {
    plants[slot] = newPlant(random);
  }
  return {
    field,
    mode,
    plants,
    coins: [],
    bears: [],
    score: 0,
    caught: 0,
    lives: STARTING_LIVES,
    elapsedMs: 0,
    bearInMs: FIRST_BEAR_MS,
    fullMs: 0,
    over: false,
    nextId: 1,
  };
}

/** Plots in the order a reinvestment fills them: from the middle outwards. */
function slotsFromCentre(): number[] {
  const centre = (SLOT_COUNT - 1) / 2;
  return Array.from({ length: SLOT_COUNT }, (_, i) => i).sort(
    (a, b) => Math.abs(a - centre) - Math.abs(b - centre) || a - b,
  );
}

/**
 * Put caught coins back to work: a bare plot gets a seedling first, then the
 * smallest plant grows, and a garden with nothing left to grow pays a bonus.
 */
function reinvest(state: GameState, at: Point, random: Random): GameEvent {
  const free = slotsFromCentre().find((slot) => state.plants[slot] === null);
  if (free !== undefined) {
    state.plants[free] = newPlant(random);
    return { type: 'plant', slot: free };
  }
  let smallest = -1;
  state.plants.forEach((plant, slot) => {
    if (plant && plant.level < 3 && (smallest < 0 || plant.level < state.plants[smallest]!.level)) {
      smallest = slot;
    }
  });
  if (smallest >= 0) {
    const plant = state.plants[smallest]!;
    plant.level = (plant.level + 1) as Level;
    plant.ageMs = 0;
    return { type: 'grow', slot: smallest };
  }
  state.score += BONUS_POINTS;
  return { type: 'bonus', at };
}

function collect(state: GameState, coin: Coin, random: Random): GameEvent[] {
  state.coins = state.coins.filter((c) => c.id !== coin.id);
  state.score += 1;
  state.caught += 1;
  const at = { x: coin.x, y: coin.y };
  const events: GameEvent[] = [{ type: 'collect', at }];
  if (state.caught % REINVEST_EVERY === 0) events.push(reinvest(state, at, random));
  return events;
}

/** Where a bear is drawn and tapped: standing on the ground at its x. */
export function bearCentre(field: Field, bear: Bear): Point {
  return { x: bear.x, y: groundAt(field, bear.x) - field.unit * 3 };
}

/**
 * The player's tap or click. A bear under the finger is shooed before a coin
 * is caught: a bear about to bite is the more urgent of the two.
 */
export function tap(state: GameState, point: Point, random: Random = Math.random): GameEvent[] {
  if (state.over || state.mode !== 'play') return [];
  const { field } = state;

  const bear = state.bears.find((b) => {
    if (b.state === 'fleeing') return false;
    const c = bearCentre(field, b);
    return Math.hypot(c.x - point.x, c.y - point.y) <= field.unit * BEAR_TAP_UNITS;
  });
  if (bear) {
    bear.state = 'fleeing';
    // Back the way it came.
    bear.dir = bear.dir === 1 ? -1 : 1;
    return [{ type: 'shoo', at: bearCentre(field, bear) }];
  }

  let nearest: Coin | null = null;
  let best = field.unit * COIN_TAP_UNITS;
  for (const coin of state.coins) {
    const d = Math.hypot(coin.x - point.x, coin.y - point.y);
    if (d <= best) {
      best = d;
      nearest = coin;
    }
  }
  return nearest ? collect(state, nearest, random) : [];
}

function nearestPlantSlot(state: GameState, x: number): number {
  let found = -1;
  state.plants.forEach((plant, slot) => {
    if (!plant) return;
    if (found < 0 || Math.abs(state.field.slots[slot] - x) < Math.abs(state.field.slots[found] - x)) {
      found = slot;
    }
  });
  return found;
}

function spawnBear(state: GameState, random: Random): void {
  const fromLeft = random() < 0.5;
  const margin = state.field.unit * 6;
  const x = fromLeft ? -margin : state.field.width + margin;
  const targetSlot = nearestPlantSlot(state, x);
  if (targetSlot < 0) return;
  state.bears.push({
    id: state.nextId++,
    x,
    dir: fromLeft ? 1 : -1,
    state: 'walking',
    targetSlot,
    eatMs: 0,
  });
}

function stepPlants(state: GameState, dtMs: number, random: Random, events: GameEvent[]): void {
  state.plants.forEach((plant, slot) => {
    if (!plant) return;
    plant.ageMs += dtMs;
    plant.coinInMs -= dtMs;
    if (plant.coinInMs > 0) return;
    plant.coinInMs = COIN_INTERVAL_MS[plant.level] * (0.8 + 0.4 * random());
    const at = plantTop(state.field, slot, plant.level);
    state.coins.push({ id: state.nextId++, originX: at.x, x: at.x, y: at.y, ageMs: 0 });
    events.push({ type: 'coin', at });
  });
}

function stepCoins(state: GameState, dtMs: number, random: Random, events: GameEvent[]): void {
  const { field } = state;
  for (const coin of [...state.coins]) {
    coin.ageMs += dtMs;
    coin.y -= (COIN_RISE_UNITS_PER_S * field.unit * dtMs) / 1000;
    coin.x = coin.originX + Math.sin(coin.ageMs / 420 + coin.id) * field.unit * 1.2;
    if (state.mode === 'demo' && coin.ageMs >= COIN_LIFE_MS * DEMO_COLLECT_AT) {
      events.push(...collect(state, coin, random));
    } else if (coin.ageMs >= COIN_LIFE_MS) {
      state.coins = state.coins.filter((c) => c.id !== coin.id);
      events.push({ type: 'miss', at: { x: coin.x, y: coin.y } });
    }
  }
}

function stepBears(state: GameState, dtMs: number, random: Random, events: GameEvent[]): void {
  const { field } = state;
  state.bearInMs -= dtMs;
  if (state.bearInMs <= 0) {
    spawnBear(state, random);
    state.bearInMs = 60_000 / bearsPerMinute(state.elapsedMs);
  }

  for (const bear of state.bears) {
    if (bear.state === 'fleeing') {
      bear.x += (bear.dir * BEAR_FLEE_UNITS_PER_S * field.unit * dtMs) / 1000;
      continue;
    }
    if (state.plants[bear.targetSlot] === null) {
      // Its plant is gone (another bear got there first): find the next one.
      const next = nearestPlantSlot(state, bear.x);
      if (next < 0) {
        bear.state = 'fleeing';
        continue;
      }
      bear.targetSlot = next;
      bear.state = 'walking';
    }
    const targetX = field.slots[bear.targetSlot];
    if (bear.state === 'walking') {
      bear.dir = targetX >= bear.x ? 1 : -1;
      const stepPx = (BEAR_SPEED_UNITS_PER_S * field.unit * dtMs) / 1000;
      if (Math.abs(targetX - bear.x) <= stepPx) {
        bear.x = targetX;
        bear.state = 'eating';
        bear.eatMs = BEAR_EAT_MS;
      } else {
        bear.x += bear.dir * stepPx;
      }
      continue;
    }
    bear.eatMs -= dtMs;
    if (bear.eatMs > 0) continue;
    const plant = state.plants[bear.targetSlot]!;
    if (plant.level === 1) state.plants[bear.targetSlot] = null;
    else plant.level = (plant.level - 1) as Level;
    state.lives -= 1;
    events.push({ type: 'bite', slot: bear.targetSlot });
    bear.state = 'fleeing';
    // Leave by the nearer edge.
    bear.dir = bear.x < field.width / 2 ? -1 : 1;
  }

  const margin = field.unit * 10;
  state.bears = state.bears.filter((b) => b.x > -margin && b.x < field.width + margin);

  if (state.lives <= 0 || state.plants.every((p) => p === null)) {
    state.lives = Math.max(0, state.lives);
    state.over = true;
    events.push({ type: 'over' });
  }
}

/** Advance the garden by `dtMs` and report what happened. */
export function step(state: GameState, dtMs: number, random: Random = Math.random): GameEvent[] {
  if (state.over) return [];
  const events: GameEvent[] = [];
  state.elapsedMs += dtMs;
  stepPlants(state, dtMs, random, events);
  stepCoins(state, dtMs, random, events);

  if (state.mode === 'play') {
    stepBears(state, dtMs, random, events);
    return events;
  }

  // Demo: once every plot holds a full-grown plant, start the garden over.
  const full = state.plants.every((p) => p !== null && p.level === 3);
  state.fullMs = full ? state.fullMs + dtMs : 0;
  if (state.fullMs >= DEMO_FULL_MS) {
    state.plants = state.plants.map((_, slot) => (DEMO_START_SLOTS.includes(slot) ? newPlant(random) : null));
    state.coins = [];
    state.fullMs = 0;
  }
  return events;
}

/** The canvas changed size: keep the garden, move everything in proportion. */
export function resizeGame(state: GameState, field: Field): void {
  const sx = field.width / Math.max(1, state.field.width);
  const sy = field.height / Math.max(1, state.field.height);
  for (const coin of state.coins) {
    coin.x *= sx;
    coin.y *= sy;
    (coin as { originX: number }).originX *= sx;
  }
  for (const bear of state.bears) bear.x *= sx;
  state.field = field;
}
