import { useEffect, useRef, useState, useSyncExternalStore, type RefObject } from "react";
import type { Quality } from "../engine/quality";
import { createWorld, type WorldCallbacks, type WorldHandle, type WorldStats } from "../engine/scene";
import type { WorldAsset } from "../model/types";

export function supportsWebGL(): boolean {
  try {
    const c = document.createElement("canvas");
    return !!(c.getContext("webgl2") || c.getContext("webgl"));
  } catch {
    return false;
  }
}

/**
 * Latest renderer stats outside React state: the footer label subscribes, so a sample every
 * 500 ms re-renders that label and not the whole shell.
 */
export interface StatsStore {
  get(): WorldStats | null;
  set(s: WorldStats): void;
  subscribe(fn: () => void): () => void;
}

function createStatsStore(): StatsStore {
  let value: WorldStats | null = null;
  const subs = new Set<() => void>();
  return {
    get: () => value,
    set(s) {
      value = s;
      subs.forEach((fn) => fn());
    },
    subscribe(fn) {
      subs.add(fn);
      return () => void subs.delete(fn);
    },
  };
}

export function useStats(store: StatsStore): WorldStats | null {
  return useSyncExternalStore(store.subscribe, store.get, () => null);
}

interface Options {
  assets: readonly WorldAsset[];
  quality: Quality;
  reducedMotion: boolean;
  callbacks: Omit<WorldCallbacks, "onContextLost">;
}

/**
 * Owns the renderer's lifetime. A fresh <canvas> is created per mount: a canvas whose
 * WebGL context was released cannot be reused, and React strict mode mounts twice.
 * Callbacks are read through a ref so a new closure never rebuilds the scene.
 */
export function useWorld(host: RefObject<HTMLDivElement | null>, o: Options) {
  const world = useRef<WorldHandle | null>(null);
  const cb = useRef(o.callbacks);
  // The scene is rebuilt when the assets change; it must come back with the user's current
  // quality and motion preference, not the ones from first mount.
  const latest = useRef({ quality: o.quality, reducedMotion: o.reducedMotion });
  const [failed, setFailed] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [statsStore] = useState(createStatsStore);

  useEffect(() => {
    cb.current = o.callbacks;
    latest.current = { quality: o.quality, reducedMotion: o.reducedMotion };
  });

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const canvas = document.createElement("canvas");
    canvas.tabIndex = 0;
    canvas.setAttribute("aria-label", "Mundo vivo: escena 3D de la cartera");
    canvas.style.cssText = "position:absolute;inset:0;width:100%;height:100%;display:block;outline:none;touch-action:none";
    el.appendChild(canvas);
    let handle: WorldHandle;
    try {
      handle = createWorld(canvas, latest.current, {
        onSelect: (id) => cb.current.onSelect(id),
        onHover: (id) => cb.current.onHover(id),
        onFocusKey: () => cb.current.onFocusKey(),
        onPerformance: (k, p) => cb.current.onPerformance(k, p),
        onContextLost: () => setFailed("Se ha perdido el contexto gráfico (WebGL)."),
        onCanBack: (can) => cb.current.onCanBack(can),
        onStats: (s) => {
          statsStore.set(s);
          setReady(true);
          cb.current.onStats(s);
        },
      });
    } catch (e) {
      // Runs in the effect but only after an async-free failure of the external system.
      queueMicrotask(() => setFailed(e instanceof Error ? e.message : "No se pudo iniciar WebGL."));
      canvas.remove();
      return;
    }
    handle.setAssets(o.assets);
    world.current = handle;
    // Dev-only handle for profiling in the console (FPS, draw calls); never in production.
    if (process.env.NODE_ENV !== "production") (window as unknown as { __livingWorld?: WorldHandle }).__livingWorld = handle;
    return () => {
      world.current = null;
      handle.dispose();
      canvas.remove();
    };
    // The renderer is rebuilt only when the set of assets changes.
  }, [host, o.assets, statsStore]);

  useEffect(() => {
    world.current?.setQuality(o.quality);
  }, [o.quality]);

  useEffect(() => {
    world.current?.setReducedMotion(o.reducedMotion);
  }, [o.reducedMotion]);

  return { world, failed, ready, statsStore };
}
