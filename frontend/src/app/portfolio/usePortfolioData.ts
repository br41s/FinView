"use client";

import { useEffect, useState } from "react";

import { api } from "@/lib/api";

import type { Position, Summary } from "./types";

/**
 * The page's primary load, lifted out of PortfolioContent.
 *
 * Two phases: positions + summary without live prices first (must succeed,
 * or the page shows ErrorState), then the same two endpoints with prices
 * (best-effort — a failure leaves prices as "—" and `pricesLoaded` false).
 * `retry` re-runs both phases from scratch.
 */
export interface PortfolioData {
  positions: Position[];
  summary: Summary | null;
  loading: boolean;
  error: string | null;
  pricesLoaded: boolean;
  retry: () => void;
}

export function usePortfolioData(): PortfolioData {
  const [positions, setPositions] = useState<Position[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [pricesLoaded, setPricesLoaded] = useState(false);

  useEffect(() => {
    async function load() {
      setError(null);

      // Phase 1: positions + summary without live prices (must succeed)
      try {
        const [pos, sum] = await Promise.all([
          api.portfolio.positions(true) as Promise<Position[]>,
          api.portfolio.summary(true) as Promise<Summary>,
        ]);
        setPositions(pos);
        setSummary(sum);
        setLoading(false);
      } catch (e) {
        console.error("Failed to load portfolio:", e);
        setError("No se pudieron cargar los datos de la cartera. Comprueba tu conexión e inténtalo de nuevo.");
        setLoading(false);
        return;
      }

      // Phase 2: live prices (optional — failure leaves prices as "—")
      try {
        const [posWithPrices, sumWithPrices] = await Promise.all([
          api.portfolio.positions() as Promise<Position[]>,
          api.portfolio.summary() as Promise<Summary>,
        ]);
        setPositions(posWithPrices);
        setSummary(sumWithPrices);
        setPricesLoaded(true);
      } catch (e) {
        console.error("Failed to load live prices:", e);
        // non-critical — positions already shown without live prices
      }
    }
    load();
  }, [retryKey]);

  return {
    positions,
    summary,
    loading,
    error,
    pricesLoaded,
    retry: () => setRetryKey((k) => k + 1),
  };
}
