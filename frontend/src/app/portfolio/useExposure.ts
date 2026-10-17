"use client";

import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { type ExposureRefresh, shouldRefreshAgain } from "@/lib/exposure";

/**
 * Load a report-derived view once prices are in, then read any annual reports
 * still pending, one bounded backend step at a time, and reload after each step
 * so the view fills in as reports are read.
 *
 * Waits for `ready` (prices loaded) so the backend's own position valuation hits
 * the price cache the positions call just filled instead of fetching in parallel.
 * Shared by the sector/region exposure and the AI exposure: same refresh contract.
 */
export function useAnnualReports<T>(
  ready: boolean,
  fetchView: () => Promise<T>,
  refreshStep: () => Promise<ExposureRefresh>,
  errorMessage: string,
) {
  const [view, setView] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState(false);
  const [stalled, setStalled] = useState(false);

  const load = useCallback(async () => {
    try {
      setView(await fetchView());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : errorMessage);
    }
  }, [fetchView, errorMessage]);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    (async () => {
      await load();
      setReading(true);
      try {
        for (;;) {
          if (cancelled) return;
          const step = await refreshStep();
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
  }, [ready, load, refreshStep]);

  return { view, error, reading, stalled, retry: load };
}

export function useExposure(ready: boolean) {
  const { view, ...rest } = useAnnualReports(
    ready,
    api.portfolio.exposure,
    api.portfolio.refreshExposure,
    "No se pudo cargar la exposición por sector y región",
  );
  return { exposure: view, ...rest };
}
