"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { type Exposure, shouldRefreshAgain } from "@/lib/exposure";

/**
 * Load the exposure once prices are in, then read any annual reports still
 * pending, one bounded backend step at a time, and reload after each step so
 * the charts fill in as reports are read.
 *
 * Waits for `ready` (prices loaded) so the backend's own position valuation hits
 * the price cache the positions call just filled instead of fetching in parallel.
 */
export function useExposure(ready: boolean) {
  const [exposure, setExposure] = useState<Exposure | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [stalled, setStalled] = useState(false);

  const load = useCallback(async () => {
    try {
      setExposure(await api.portfolio.exposure());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la exposición por sector y región");
    }
  }, []);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    (async () => {
      await load();
      setReading(true);
      try {
        for (;;) {
          if (cancelled) return;
          const step = await api.portfolio.refreshExposure();
          if (cancelled) return;
          if (step.checked > 0) await load();
          if (!shouldRefreshAgain(step)) {
            setStalled(step.pending > 0);
            break;
          }
        }
      } catch {
        // Reading reports is an enrichment: what is already stored still shows.
        if (!cancelled) setStalled(true);
      } finally {
        if (!cancelled) setReading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [ready, load]);

  return { exposure, error, reading, stalled, retry: load };
}
