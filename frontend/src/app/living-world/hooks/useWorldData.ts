"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "@/lib/api";
import { demoAssets } from "../model/fixtures";
import type { WorldAsset } from "../model/types";
import { toWorldAssets } from "../model/worldAssets";

/** What the screen says about the data under the town. */
export interface WorldMeta {
  /** ISO date of the newest cached price; null when nothing is priced. */
  pricesAsOf: string | null;
  positions: number;
  /** Positions with no price: drawn small and marked, never as zero. */
  unvalued: number;
  unclassified: number;
}

export type WorldData =
  | { status: "loading" }
  | { status: "error"; message: string; retry: () => void }
  | { status: "empty" }
  | {
      status: "ready";
      assets: WorldAsset[];
      meta: WorldMeta | null;
      refresh: () => void;
      refreshing: boolean;
      refreshFailed: boolean;
    };

/**
 * The town's assets. `demo` swaps the portfolio for the fictional Phase 0 holdings and
 * never fetches. A refresh keeps the town on screen: the new data replaces the old only
 * when it arrives, and a failed refresh leaves the old data in place and says so.
 */
export function useWorldData(demo: boolean): WorldData {
  const [loaded, setLoaded] = useState<{ assets: WorldAsset[]; meta: WorldMeta } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [refreshing, setRefreshing] = useState(false);
  const [refreshFailed, setRefreshFailed] = useState(false);
  const demoSet = useMemo(() => (demo ? demoAssets() : []), [demo]);
  // Ignores an answer that arrives after a newer request or an unmount.
  const latest = useRef(0);

  const load = useCallback(async (background: boolean) => {
    const mine = ++latest.current;
    if (background) setRefreshing(true);
    else setError(null);
    try {
      const res = await api.livingWorld.world();
      if (mine !== latest.current) return;
      setLoaded({
        assets: toWorldAssets(res),
        meta: {
          pricesAsOf: res.summary.prices_as_of,
          positions: res.summary.positions,
          unvalued: res.summary.positions - res.summary.valued,
          unclassified: res.summary.positions - res.summary.classified,
        },
      });
      setRefreshFailed(false);
    } catch (e) {
      if (mine !== latest.current) return;
      console.error("Failed to load the Living World:", e);
      if (background) setRefreshFailed(true);
      else setError("No se pudo cargar tu cartera. Comprueba tu conexión e inténtalo de nuevo.");
    } finally {
      if (mine === latest.current) setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    if (demo) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect -- the fetch's first step resets the error banner
    void load(false);
    return () => {
      // Intentionally the *current* counter: invalidates whatever request is in flight.
      // eslint-disable-next-line react-hooks/exhaustive-deps
      latest.current++;
    };
  }, [demo, load]);

  const refresh = useCallback(() => void load(true), [load]);
  const retry = useCallback(() => void load(false), [load]);

  if (demo) {
    return { status: "ready", assets: demoSet, meta: null, refresh: () => undefined, refreshing: false, refreshFailed: false };
  }
  if (loaded) {
    if (loaded.assets.length === 0) return { status: "empty" };
    return { status: "ready", ...loaded, refresh, refreshing, refreshFailed };
  }
  if (error) return { status: "error", message: error, retry };
  return { status: "loading" };
}
