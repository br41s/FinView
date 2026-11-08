import type { Severity, WorldEvent } from "./types";

/**
 * Event director (spec §6.3): turns a stream of events into a few readable on-screen
 * performances. Pure and clock-driven (`tick(state, dtMs)`), so a test can replay a burst
 * of 30 events deterministically and the renderer just obeys `started` / `ended`.
 *
 * The feed and the cards do not live here: an event stays in history whether or not its
 * performance ever plays. The director only decides what is *acted out*.
 */

export interface DirectorConfig {
  /** Concurrent performances of Normal severity. */
  maxNormal: number;
  /** Concurrent performances of any severity; Critical may use the last slots. */
  maxTotal: number;
  /** Critical events may ask the camera to fly there. Off unless the user opts in. */
  autoFocus: boolean;
  /** Quiet mode: ambient world only, nothing is acted out. */
  quiet: boolean;
}

export const DEFAULT_DIRECTOR_CONFIG: DirectorConfig = {
  maxNormal: 3,
  maxTotal: 6,
  autoFocus: false,
  quiet: false,
};

export interface Performance {
  id: string;
  assetId: string | null;
  events: WorldEvent[];
  severity: Severity;
  priority: number;
  startedAt: number;
  endsAt: number;
  replay: boolean;
  /** Only ever true for Critical with autoFocus on; the director never moves the camera itself. */
  requestFocus: boolean;
}

/** A queued event that has waited this long is no longer "live" and is dropped, not acted late. */
export const QUEUE_TTL_MS = 180_000;
/** Remembered dedupe keys; the oldest are forgotten past this, so a long session stays flat. */
export const MAX_SEEN = 2000;

export interface DirectorState {
  config: DirectorConfig;
  clock: number;
  paused: boolean;
  queue: WorldEvent[];
  /** Director clock at which each queued event (by id) was accepted, for the TTL. */
  queuedAt: ReadonlyMap<string, number>;
  active: Performance[];
  /** dedupeKeys already accepted, so polling the same observation twice acts it once. */
  seen: ReadonlySet<string>;
}

export interface TickResult {
  state: DirectorState;
  started: Performance[];
  /** Existing performances that absorbed a further event of the same company. */
  merged: Performance[];
  ended: Performance[];
}

const RANK: Record<Severity, number> = { normal: 0, important: 1, critical: 2 };

export function createDirector(config: Partial<DirectorConfig> = {}): DirectorState {
  return {
    config: { ...DEFAULT_DIRECTOR_CONFIG, ...config },
    clock: 0,
    paused: false,
    queue: [],
    queuedAt: new Map(),
    active: [],
    seen: new Set(),
  };
}

export function compareEvents(a: WorldEvent, b: WorldEvent): number {
  return (
    b.priorityScore - a.priorityScore ||
    Date.parse(a.occurredAt) - Date.parse(b.occurredAt) ||
    (a.id < b.id ? -1 : a.id > b.id ? 1 : 0)
  );
}

export function enqueue(state: DirectorState, events: readonly WorldEvent[]): DirectorState {
  const seen = new Set(state.seen);
  const fresh: WorldEvent[] = [];
  for (const e of events) {
    if (seen.has(e.dedupeKey)) continue;
    seen.add(e.dedupeKey);
    fresh.push(e);
  }
  // A Set iterates in insertion order, so the first keys are the oldest.
  for (const k of seen) {
    if (seen.size <= MAX_SEEN) break;
    seen.delete(k);
  }
  // Quiet mode still records the observation so leaving quiet does not replay a backlog.
  if (state.config.quiet || fresh.length === 0) return { ...state, seen };
  const queuedAt = new Map(state.queuedAt);
  for (const e of fresh) queuedAt.set(e.id, state.clock);
  return { ...state, seen, queuedAt, queue: [...state.queue, ...fresh].sort(compareEvents) };
}

export function setPaused(state: DirectorState, paused: boolean): DirectorState {
  return { ...state, paused };
}

export function setConfig(state: DirectorState, patch: Partial<DirectorConfig>): DirectorState {
  const config = { ...state.config, ...patch };
  // Entering quiet mode drops what was waiting; running performances play out.
  return config.quiet
    ? { ...state, config, queue: [], queuedAt: new Map() }
    : { ...state, config };
}

function wantsFocus(config: DirectorConfig, severity: Severity): boolean {
  return config.autoFocus && severity === "critical";
}

function absorb(p: Performance, e: WorldEvent, clock: number, config: DirectorConfig): Performance {
  const severity = RANK[e.severity] > RANK[p.severity] ? e.severity : p.severity;
  return {
    ...p,
    events: [...p.events, e],
    severity,
    priority: Math.max(p.priority, e.priorityScore),
    endsAt: Math.max(p.endsAt, clock + e.displayDurationMs),
    requestFocus: wantsFocus(config, severity),
  };
}

function begin(e: WorldEvent, clock: number, config: DirectorConfig, replay: boolean): Performance {
  return {
    id: `perf:${e.id}${replay ? `@${clock}` : ""}`,
    assetId: e.assetId,
    events: [e],
    severity: e.severity,
    priority: e.priorityScore,
    startedAt: clock,
    endsAt: clock + e.displayDurationMs,
    replay,
    requestFocus: wantsFocus(config, e.severity),
  };
}

function hasRoom(active: readonly Performance[], e: WorldEvent, c: DirectorConfig): boolean {
  if (e.severity === "critical") return true;
  if (active.length >= c.maxTotal) return false;
  if (e.severity === "normal") {
    return active.filter((p) => p.severity === "normal").length < c.maxNormal;
  }
  return true;
}

/** Advance the clock. Paused → nothing moves, so a paused scene keeps every pose. */
export function tick(state: DirectorState, dtMs: number): TickResult {
  if (state.paused || dtMs <= 0) return { state, started: [], merged: [], ended: [] };

  const clock = state.clock + dtMs;
  const ended = state.active.filter((p) => p.endsAt <= clock);
  let active = state.active.filter((p) => p.endsAt > clock);
  const started: Performance[] = [];
  const merged = new Map<string, Performance>();
  const waiting: WorldEvent[] = [];
  const queuedAt = new Map<string, number>();

  for (const e of state.queue) {
    const since = state.queuedAt.get(e.id) ?? state.clock;
    if (clock - since > QUEUE_TTL_MS) continue;
    // Several events about one company become one scene; every card is kept.
    const i = e.assetId === null ? -1 : active.findIndex((p) => p.assetId === e.assetId);
    if (i >= 0) {
      const next = absorb(active[i], e, clock, state.config);
      active = active.map((p, j) => (j === i ? next : p));
      merged.set(next.id, next);
      continue;
    }
    if (hasRoom(active, e, state.config)) {
      const p = begin(e, clock, state.config, false);
      active = [...active, p];
      started.push(p);
    } else {
      waiting.push(e);
      queuedAt.set(e.id, since);
    }
  }

  // A performance started this tick and merged into later is reported once, as started.
  const startedIds = new Set(started.map((p) => p.id));
  const startedNow = started.map((p) => active.find((a) => a.id === p.id) ?? p);
  const mergedOnly = [...merged.values()].filter((p) => !startedIds.has(p.id));

  return {
    state: { ...state, clock, queue: waiting, queuedAt, active },
    started: startedNow,
    merged: mergedOnly,
    ended,
  };
}

/**
 * Re-enact an event without touching its facts. Bypasses the queue, the dedupe set and
 * quiet mode (the user asked for it), and merges into a live scene of the same company.
 */
export function replay(state: DirectorState, event: WorldEvent): TickResult {
  const i = event.assetId === null ? -1 : state.active.findIndex((p) => p.assetId === event.assetId);
  if (i >= 0) {
    const next = absorb(state.active[i], event, state.clock, state.config);
    return {
      state: { ...state, active: state.active.map((p, j) => (j === i ? next : p)) },
      started: [],
      merged: [next],
      ended: [],
    };
  }
  const p = begin(event, state.clock, state.config, true);
  return { state: { ...state, active: [...state.active, p] }, started: [p], merged: [], ended: [] };
}
