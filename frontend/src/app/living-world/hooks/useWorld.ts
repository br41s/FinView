import { useEffect, useRef, useState, type RefObject } from "react";
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
  const initial = useRef({ quality: o.quality, reducedMotion: o.reducedMotion });
  const [failed, setFailed] = useState<string | null>(null);
  const [stats, setStats] = useState<WorldStats | null>(null);

  useEffect(() => {
    cb.current = o.callbacks;
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
      handle = createWorld(canvas, initial.current, {
        onSelect: (id) => cb.current.onSelect(id),
        onHover: (id) => cb.current.onHover(id),
        onFocusKey: () => cb.current.onFocusKey(),
        onPerformance: (k, p) => cb.current.onPerformance(k, p),
        onContextLost: () => setFailed("Se ha perdido el contexto gráfico (WebGL)."),
        onStats: (s) => {
          setStats(s);
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
  }, [host, o.assets]);

  useEffect(() => {
    world.current?.setQuality(o.quality);
  }, [o.quality]);

  useEffect(() => {
    world.current?.setReducedMotion(o.reducedMotion);
  }, [o.reducedMotion]);

  return { world, failed, stats };
}
