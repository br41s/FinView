import { useSyncExternalStore } from "react";

/**
 * Wall clock as an external store, so components read "now" without calling Date.now()
 * during render. It ticks every 15 s: time windows (live / 24 h / 7 d) only need that.
 */
const TICK_MS = 15_000;

export function nowMs(): number {
  return Math.floor(Date.now() / TICK_MS) * TICK_MS;
}

function subscribe(onChange: () => void) {
  const id = window.setInterval(onChange, TICK_MS);
  return () => window.clearInterval(id);
}

export function useNow(): number {
  return useSyncExternalStore(subscribe, nowMs, () => 0);
}

const REDUCED = "(prefers-reduced-motion: reduce)";

function subscribeMotion(onChange: () => void) {
  const mq = window.matchMedia(REDUCED);
  mq.addEventListener("change", onChange);
  return () => mq.removeEventListener("change", onChange);
}

export function usePrefersReducedMotion(): boolean {
  return useSyncExternalStore(subscribeMotion, () => window.matchMedia(REDUCED).matches, () => false);
}
